"""Cadastro de sistemas e pedidos de pull.

Um sistema (tag) tem uma ou mais origens; cada origem é um repositório e
ramo, com uma ou mais leituras ({perfil, incluir, excluir}). O cadastro
antigo, com repo/perfil/incluir/excluir no topo, continua valendo: vira a
origem `principal` com uma leitura.

A API só grava no estado.db: quem clona, faz o diff e enche a fila é a
ingestão, no curador (vault_system/ingestao.py), o único container com as
chaves de deploy das origens. O pull manual vira um pedido que o curador
atende em até 30 segundos.
"""
import json
import re
import sqlite3

from vault_system.estado import TAG, agora, conectar

PERFIS_FIXOS = ("documentos", "codigo")
# SSH (chave de deploy só leitura por repositório) ou https://github.com/<dono>/<repo>,
# lido pelo GitHub App. Nada de token na URL nem caminho local.
REPO = re.compile(r"^((git@[A-Za-z0-9.-]+:|ssh://git@[A-Za-z0-9.-]+(:\d+)?/)[A-Za-z0-9._/-]+?(\.git)?"
                  r"|https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?)$")
# Dono/repo do GitHub nas duas formas de endereço (SSH e GitHub App).
DONO_REPO = re.compile(r"^(?:git@github\.com:|ssh://git@github\.com(?::\d+)?/|https://github\.com/)"
                       r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$")
RAMO = re.compile(r"^(?!.*\.\.)(?!/)(?!.*/$)[A-Za-z0-9._/-]+$")


def mesmo_repo(a, b):
    """Os dois endereços são o mesmo repositório do GitHub (ex.: o SSH da
    chave de deploy e o https do GitHub App)? Dono e repo sem diferença de
    maiúsculas, como o GitHub trata."""
    ma, mb = DONO_REPO.match(a), DONO_REPO.match(b)
    return bool(ma and mb and ma.group(1).lower() == mb.group(1).lower())


def normalizar(dados):
    """Cadastro no formato antigo (repo e perfil no topo) vira uma origem
    `principal` com uma leitura."""
    if dados.get("origens"):
        return dados
    return {**dados, "origens": [{"nome": "principal", "repo": dados.get("repo") or "", "ramo": dados.get("ramo") or "main",
                                  "leituras": [{"perfil": dados.get("perfil") or "", "incluir": dados.get("incluir") or [],
                                                "excluir": dados.get("excluir") or []}]}]}


def validar_origem(o, prefixo="origem"):
    erros = []
    if not TAG.match(o["nome"]):
        erros.append(f"{prefixo}: nome em minúsculas, números e hífen")
    if not REPO.match(o["repo"]):
        erros.append(f"{prefixo} {o['nome']}: repo deve ser https://github.com/Org/repo (GitHub App) "
                     "ou URL SSH (git@github.com:Org/repo.git)")
    if not RAMO.match(o["ramo"]):
        erros.append(f"{prefixo} {o['nome']}: ramo inválido")
    if not o["leituras"]:
        erros.append(f"{prefixo} {o['nome']}: pelo menos uma leitura")
    for l in o["leituras"]:
        if not TAG.match(l["perfil"]):
            erros.append(f"{prefixo} {o['nome']}: perfil {', '.join(PERFIS_FIXOS)} ou um perfil próprio "
                         "(minúsculas e hífen)")
        for campo in ("incluir", "excluir"):
            if any(not p or len(p) > 200 for p in l[campo]):
                erros.append(f"{prefixo} {o['nome']}: {campo} com padrões vazios ou longos demais")
            # "docs/**<br>**/*.md" colado de uma tabela (27/10, refeitorio): não casa com nada.
            if any(c in p for p in l[campo] for c in "<>\n"):
                erros.append(f"{prefixo} {o['nome']}: {campo} com < ou > num padrão; use um padrão por linha")
    return erros


def validar(dados):
    """Confere o cadastro (já normalizado); devolve a lista de problemas."""
    erros = [] if TAG.match(dados["tag"]) else ["tag: use minúsculas, números e hífen"]
    nomes = [o["nome"] for o in dados["origens"]]
    if len(set(nomes)) != len(nomes):
        erros.append("origens: nomes repetidos")
    for o in dados["origens"]:
        erros += validar_origem(o)
    return erros


def _gravar_origem(db, tag, o):
    leituras = [{"perfil": l["perfil"], "incluir": l["incluir"], "excluir": l["excluir"]} for l in o["leituras"]]
    classificacao = json.dumps(o["classificacao"], ensure_ascii=False) if o.get("classificacao") else None
    db.execute("INSERT INTO origens (tag, nome, repo, ramo, leituras, classificacao, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (tag, o["nome"], o["repo"], o["ramo"], json.dumps(leituras, ensure_ascii=False), classificacao, agora()))


def criar(dados, por):
    """Grava o cadastro e as origens. Devolve False se a tag já existe. As
    colunas antigas de `sistemas` ficam com a primeira origem e leitura."""
    o, l = dados["origens"][0], dados["origens"][0]["leituras"][0]
    try:
        with conectar() as db:
            db.execute("INSERT INTO sistemas (tag, perfil, repo, ramo, incluir, excluir, criado_em, criado_por) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (dados["tag"], l["perfil"], o["repo"], o["ramo"], json.dumps(l["incluir"]),
                        json.dumps(l["excluir"]), agora(), por))
            for origem in dados["origens"]:
                _gravar_origem(db, dados["tag"], origem)
    except sqlite3.IntegrityError:
        return False
    return True


def acrescentar_origem(tag, origem):
    """Nova origem num sistema que já existe. False se o nome já existe."""
    try:
        with conectar() as db:
            _gravar_origem(db, tag, origem)
    except sqlite3.IntegrityError:
        return False
    return True


def editar_origem(tag, nome, ramo, leituras, repo=None, classificacao=None):
    """Novo ramo e novas leituras e, do mesmo repositório, o
    endereço (SSH ou GitHub App): o clone é o mesmo, a ingestão só
    troca a URL do remote. A classificação da árvore vai junto; editar
    pelo formulário de leituras a apaga (ela não descreveria mais as leituras). As leituras de antes ficam em
    `leituras_antes` até a ingestão reconciliar a fila e o vault com as novas
    (num segundo editar antes disso, continuam as primeiras: são as que o
    vault reflete). False se a origem não existe ou já foi removida."""
    novas = json.dumps([{"perfil": l["perfil"], "incluir": l["incluir"], "excluir": l["excluir"]} for l in leituras],
                       ensure_ascii=False)
    with conectar() as db:
        return db.execute("UPDATE origens SET repo = COALESCE(?, repo), ramo = ?, leituras = ?, classificacao = ?, "
                          "leituras_antes = COALESCE(leituras_antes, leituras) WHERE tag = ? AND nome = ? AND removida_em IS NULL",
                          (repo, ramo, novas, json.dumps(classificacao, ensure_ascii=False) if classificacao else None, tag, nome)).rowcount > 0


def remover_origem(tag, nome):
    """Pede a remoção de uma origem: sem leituras, tudo o que veio
    dela sai do vault no próximo pull, e o curador apaga o cadastro quando a
    fila dela esvazia. "ultima" se é a única origem (remova o sistema),
    None se não existe, True se pediu."""
    with conectar() as db:
        ativas = [o["nome"] for o in db.execute("SELECT nome FROM origens WHERE tag = ? AND removida_em IS NULL", (tag,))]
        if nome not in ativas:
            return None
        if len(ativas) == 1:
            return "ultima"
        db.execute("UPDATE origens SET removida_em = ?, leituras_antes = COALESCE(leituras_antes, leituras), "
                   "leituras = '[]' WHERE tag = ? AND nome = ?", (agora(), tag, nome))
    return True


def ler(tag):
    """Cadastro, commits, contagem da fila e o último pull; None se não existe."""
    with conectar() as db:
        s = db.execute("SELECT * FROM sistemas WHERE tag = ?", (tag,)).fetchone()
        if not s:
            return None
        fila = {l["acao"]: l["n"] for l in db.execute(
            "SELECT acao, COUNT(*) n FROM fila WHERE tag = ? AND estado = 'na_fila' GROUP BY acao", (tag,))}
        ultimo = db.execute("SELECT id FROM pulls WHERE tag = ? ORDER BY id DESC LIMIT 1", (tag,)).fetchone()
        origens = db.execute("SELECT * FROM origens WHERE tag = ? ORDER BY id", (tag,)).fetchall()
    saida = {k: s[k] for k in ("tag", "criado_em", "criado_por", "removido_em")}
    saida["origens"] = [{"nome": o["nome"], "repo": o["repo"], "ramo": o["ramo"], "leituras": json.loads(o["leituras"]),
                         "classificacao": json.loads(o["classificacao"]) if o["classificacao"] else None,
                         "commit_processado": o["commit_processado"], "commit_pendente": o["commit_pendente"],
                         "reconciliacao_pendente": o["leituras_antes"] is not None, "removida_em": o["removida_em"]}
                        for o in origens]
    saida["fila"] = fila
    saida["ultimo_pull"] = ler_pull(tag, ultimo["id"]) if ultimo else None
    return saida


def marcar_remocao(tag, por):
    """Pede a remoção; o curador apaga em até 30 s. False se não existe."""
    with conectar() as db:
        return db.execute("UPDATE sistemas SET removido_em = ? WHERE tag = ? AND removido_em IS NULL",
                          (agora(), tag)).rowcount > 0


def fila(tag):
    """Itens na fila da tag (sem o conteúdo, que fica em estado/lotes/)."""
    with conectar() as db:
        return [dict(l) for l in db.execute(
            "SELECT id, acao, caminho, commit_origem, lote, motivo, criado_em FROM fila "
            "WHERE tag = ? AND estado = 'na_fila' ORDER BY id", (tag,))]


def pedir_pull(tag, por):
    with conectar() as db:
        return db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES (?, ?, ?)",
                          (tag, agora(), por)).lastrowid


def ler_pull(tag, pid):
    with conectar() as db:
        p = db.execute("SELECT * FROM pulls WHERE tag = ? AND id = ?", (tag, pid)).fetchone()
    if not p:
        return None
    saida = dict(p)
    saida["resultado"] = json.loads(p["resultado"]) if p["resultado"] else None
    saida["estado"] = "atendido" if p["atendido_em"] else "pedido"
    return saida
