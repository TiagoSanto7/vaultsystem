"""Busca por texto completo no vault (DV-293).

O índice (SQLite FTS5, em `estado/busca.db`) é derivado: sai do `notas_indice`
que o curador grava a cada rodada e pode ser apagado a qualquer momento. Antes
de cada busca, o código confere a marca da tag (quantas notas e o maior rowid:
o curador apaga e reinsere as notas a cada rodada, então a marca muda) e, se
mudou, refaz o índice da tag. Assim o curador não precisa saber da busca.

A tag chega aqui já conferida contra a credencial (api/app/main.py); aqui ela é
só o filtro da consulta SQL.

A busca devolve trechos das notas, nunca uma resposta escrita por IA. O estado
editorial de cada nota (`verification`) vem da DV-575; até lá, toda nota é
`unverified`.
"""
import json
import os
import re
import sqlite3
import threading

from . import estado, notas

LIMITE = 5
LIMITE_MAX = 20
PALAVRAS_TRECHO = 32
ESQUEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS notas USING fts5(
    tag UNINDEXED, chave UNINDEXED, estado UNINDEXED, titulo, caminho, corpo,
    tokenize = 'unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS marcas (tag TEXT PRIMARY KEY, marca TEXT NOT NULL);
"""
# Peso de cada coluna no bm25, na ordem da tabela: o título vale mais que o
# nome do arquivo, que vale mais que o texto.
PESOS = "0, 0, 0, 8.0, 4.0, 1.0"
PALAVRA = re.compile(r"\w+")
_trava = threading.Lock()


def conectar():
    os.makedirs(estado.dir_estado(), exist_ok=True)
    db = sqlite3.connect(os.path.join(estado.dir_estado(), "busca.db"), timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(ESQUEMA)
    return db


def _sem_links(corpo):
    """Texto para o índice e para o trecho: o link vira o rótulo dele (ou o
    nome da nota), e sai o título, que já tem coluna própria."""
    corpo = notas.TITULO.sub("", corpo, count=1)
    return re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]",
                  lambda m: m.group(2) or m.group(1).rsplit("/", 1)[-1], corpo).strip()


def _estado(cab):
    # DV-575 define os estados (em revisão, verificada, arquivada). Até lá, nenhuma nota é verificada.
    return cab.get("verificacao") or "unverified"


def _marca(db_estado, tag):
    n, maior = db_estado.execute("SELECT COUNT(*), MAX(rowid) FROM notas_indice WHERE tag = ?", (tag,)).fetchone()
    return f"{n}:{maior}"


def atualizar(db_estado, db, tag):
    """Refaz o índice da tag se as notas mudaram desde a última vez."""
    marca = _marca(db_estado, tag)
    with _trava:
        atual = db.execute("SELECT marca FROM marcas WHERE tag = ?", (tag,)).fetchone()
        if atual and atual["marca"] == marca:
            return False
        with db:
            db.execute("DELETE FROM notas WHERE tag = ?", (tag,))
            for n in db_estado.execute("SELECT chave, conteudo FROM notas_indice WHERE tag = ? AND pasta != 'indices'",
                                       (tag,)):
                cab, corpo = notas.separar(n["conteudo"])
                nome = n["chave"].rsplit("/", 1)[-1]
                db.execute("INSERT INTO notas (tag, chave, estado, titulo, caminho, corpo) VALUES (?, ?, ?, ?, ?, ?)",
                           (tag, n["chave"], _estado(cab), notas.titulo(corpo, nome),
                            n["chave"].removeprefix(f"sistemas/{tag}/"), _sem_links(corpo)))
            db.execute("INSERT INTO marcas (tag, marca) VALUES (?, ?) ON CONFLICT(tag) DO UPDATE SET marca = excluded.marca",
                       (tag, marca))
    return True


def consulta_fts(texto):
    """Cada palavra vira um termo entre aspas (nada da sintaxe do FTS5 passa),
    unidos por OR: o bm25 põe no topo a nota que tem mais termos, e um nome
    exato (ex.: pedido_service) vira frase e casa as palavras juntas."""
    termos = PALAVRA.findall(texto)
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(termos)) or None


def _origens(db_estado, tag):
    return {o["nome"]: o for o in db_estado.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL",
                                                    (tag,))}


def _prov(origens, linha):
    return [{"repository": estado.url_repo(p["repo"]) or p["repo"], "path": p["caminho"], "branch": p["ramo"],
             "commit": p["commit"], "url": p["url"]}
            for p in estado.proveniencia(origens, json.loads(linha["origens"] or "[]"), linha["commit_origem"])]


def buscar(tag, texto, limite=LIMITE, verificacao="all"):
    """{system_id, results, has_more}. `verificacao`: "all" ou "verified"."""
    limite = max(1, min(int(limite), LIMITE_MAX))
    saida = {"system_id": tag, "results": [], "has_more": False}
    consulta = consulta_fts(texto)
    if not consulta:
        return saida
    with estado.conectar() as db_estado, conectar() as db:
        atualizar(db_estado, db, tag)
        filtro = " AND estado = 'verified'" if verificacao == "verified" else ""
        achadas = db.execute(
            f"SELECT chave, estado, titulo, snippet(notas, 5, '', '', '…', {PALAVRAS_TRECHO}) AS trecho FROM notas "
            f"WHERE notas MATCH ? AND tag = ?{filtro} ORDER BY bm25(notas, {PESOS}) LIMIT ?",
            (consulta, tag, limite + 1)).fetchall()
        saida["has_more"] = len(achadas) > limite
        origens = _origens(db_estado, tag)
        for a in achadas[:limite]:
            n = db_estado.execute("SELECT origens, commit_origem, atualizado_em FROM notas_indice WHERE tag = ? AND chave = ?",
                                  (tag, a["chave"])).fetchone()
            saida["results"].append({"note_id": a["chave"], "title": a["titulo"], "excerpt": a["trecho"],
                                     "verification": a["estado"], "updated_at": n["atualizado_em"] if n else None,
                                     "provenance": _prov(origens, n) if n else []})
    return saida


def ler(tag, chave):
    """A nota inteira (o texto em markdown, sem o cabeçalho), ou None."""
    with estado.conectar() as db_estado:
        n = db_estado.execute("SELECT * FROM notas_indice WHERE tag = ? AND chave = ?", (tag, chave)).fetchone()
        if not n:
            return None
        cab, corpo = notas.separar(n["conteudo"])
        return {"system_id": tag, "note_id": chave, "title": n["titulo"], "folder": n["pasta"],
                "verification": _estado(cab), "updated_at": n["atualizado_em"],
                "provenance": _prov(_origens(db_estado, tag), n), "content": corpo.strip()}
