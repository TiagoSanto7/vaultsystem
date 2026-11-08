"""Banco de estado do serviço (estado.db): uma conexão e o esquema, num lugar só.

Usado pela API (credenciais, cadastro, pedidos de pull) e pelo curador
(ingestão e fila). Só biblioteca padrão, porque o curador roda na imagem do
Hermes e não instala nada.
"""
import datetime
import json
import os
import re
import sqlite3

FUSO = datetime.timezone(datetime.timedelta(hours=-4))  # Cuiabá (America/Cuiaba, sem horário de verão; DV-291)
TAG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS credenciais (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL UNIQUE,
    ler TEXT NOT NULL,
    escrever TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    revogada_em TEXT);

-- Um sistema por tag. commit_processado só avança quando o curador registra
-- todos os itens do diff (DV-291); até lá, o último diff enfileirado fica em
-- commit_pendente, e o próximo pull parte dele.
CREATE TABLE IF NOT EXISTS sistemas (
    tag TEXT PRIMARY KEY,
    perfil TEXT NOT NULL,
    repo TEXT NOT NULL,
    ramo TEXT NOT NULL,
    incluir TEXT NOT NULL,
    excluir TEXT NOT NULL,
    commit_processado TEXT,
    commit_pendente TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT NOT NULL);

-- Um item por arquivo. estado: na_fila, substituido (um item mais novo do
-- mesmo caminho entrou antes de o curador ver este) e registrado (o curador
-- registrou em _meta/registro.md, ou o código resolveu sem LLM; DV-291).
-- lote: caminho do conteúdo filtrado, relativo a estado/lotes/.
-- revisar (DV-291, só em removido): JSON com as notas que o código já tirou
-- do vault e as que o curador precisa revisar; preenchido uma vez só.
CREATE TABLE IF NOT EXISTS fila (
    id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL,
    acao TEXT NOT NULL CHECK (acao IN ('adicionado', 'modificado', 'removido')),
    caminho TEXT NOT NULL,
    commit_origem TEXT NOT NULL,
    lote TEXT,
    motivo TEXT,
    estado TEXT NOT NULL DEFAULT 'na_fila',
    criado_em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS fila_tag_estado ON fila (tag, estado);

-- Origens de um sistema (DV-292): a tag é o sistema; cada origem é um
-- repositório e ramo, com a própria chave só leitura, o próprio clone e os
-- próprios commits. leituras: lista JSON de {perfil, incluir, excluir}; cada
-- arquivo vai para a primeira leitura que o aceita (ex.: docs/ com perfil
-- documentos e o resto com perfil codigo, no mesmo repositório). A origem
-- `principal` usa a chave e o clone com o nome da tag (como na DV-290); as
-- outras, `<tag>--<nome>`. As colunas repo, ramo, perfil, incluir, excluir e
-- commit_* de `sistemas` ficam só como histórico da DV-290.
CREATE TABLE IF NOT EXISTS origens (
    id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL,
    nome TEXT NOT NULL,
    repo TEXT NOT NULL,
    ramo TEXT NOT NULL,
    leituras TEXT NOT NULL,
    commit_processado TEXT,
    commit_pendente TEXT,
    criado_em TEXT NOT NULL,
    UNIQUE (tag, nome));

-- Histórico do curador (DV-547), para a tela: cada rodada (todos ou pedidos),
-- cada lote (uma tag e um perfil) e os avisos do código.
CREATE TABLE IF NOT EXISTS rodadas (
    id INTEGER PRIMARY KEY,
    modo TEXT NOT NULL,
    tags TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT,
    resultado TEXT);
CREATE TABLE IF NOT EXISTS lotes (
    id INTEGER PRIMARY KEY,
    rodada_id INTEGER,
    tag TEXT NOT NULL,
    perfil TEXT NOT NULL,
    itens INTEGER NOT NULL,
    registrados INTEGER,
    inicio TEXT NOT NULL,
    fim TEXT,
    codigo INTEGER,
    erro TEXT,
    saida TEXT);
CREATE INDEX IF NOT EXISTS lotes_tag ON lotes (tag, id);
CREATE TABLE IF NOT EXISTS avisos (
    id INTEGER PRIMARY KEY,
    rodada_id INTEGER,
    lote_id INTEGER,
    tag TEXT NOT NULL,
    tipo TEXT NOT NULL,
    nota TEXT,
    detalhe TEXT NOT NULL,
    em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS avisos_tag ON avisos (tag, id);
-- Estado do curador agora: rodada e lote em curso, próxima rodada (chave/valor JSON).
CREATE TABLE IF NOT EXISTS curador_estado (
    chave TEXT PRIMARY KEY,
    valor TEXT);

-- Índice das notas e verificação (DV-547): o curador grava ao fim de cada
-- rodada, a API só lê. Assim a API continua sem montar o vault. É também a
-- base da busca (DV-293).
CREATE TABLE IF NOT EXISTS notas_indice (
    tag TEXT NOT NULL,
    chave TEXT NOT NULL,
    pasta TEXT NOT NULL,
    titulo TEXT,
    tipo_nota TEXT,
    origens TEXT,
    commit_origem TEXT,
    criado_em TEXT,
    atualizado_em TEXT,
    conteudo TEXT NOT NULL,
    PRIMARY KEY (tag, chave));
CREATE TABLE IF NOT EXISTS meta_tag (
    tag TEXT NOT NULL,
    nome TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    PRIMARY KEY (tag, nome));
CREATE TABLE IF NOT EXISTS verificacoes (
    tag TEXT PRIMARY KEY,
    rodou_em TEXT NOT NULL,
    commits TEXT NOT NULL,
    total INTEGER NOT NULL);
-- Um problema da verificação; `desde` é a primeira vez que apareceu.
CREATE TABLE IF NOT EXISTS problemas (
    tag TEXT NOT NULL,
    chave TEXT NOT NULL,
    tipo TEXT NOT NULL,
    nota TEXT,
    detalhe TEXT NOT NULL,
    desde TEXT NOT NULL,
    PRIMARY KEY (tag, chave));

-- Preferências de cada pessoa da tela (DV-548): quando viu a apresentação de
-- três passos (no servidor, para valer em qualquer computador).
CREATE TABLE IF NOT EXISTS preferencias (
    login TEXT PRIMARY KEY,
    apresentacao_vista_em TEXT);

-- Pedido de pull: a API registra, o curador atende (só ele tem as chaves das
-- origens). resultado: JSON com commits, itens e ignorados, ou o erro.
CREATE TABLE IF NOT EXISTS pulls (
    id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL,
    pedido_em TEXT NOT NULL,
    pedido_por TEXT NOT NULL,
    atendido_em TEXT,
    resultado TEXT);

-- Repositórios onde o GitHub App está instalado (DV-573), para a tela escolher
-- ao adicionar uma origem. O curador grava (só ele tem a chave do App); a API lê.
-- ramos: lista JSON. Quando e com que erro foi a última atualização: chave
-- `github` de curador_estado.
-- Pedido de árvore de um repositório do App (DV-589), para classificar as
-- pastas no "Novo vault": a API grava, o atendente do curador responde em
-- poucos segundos. resultado: JSON com commit, arquivos e sugestão, ou o erro.
CREATE TABLE IF NOT EXISTS arvores (
    id INTEGER PRIMARY KEY,
    repo TEXT NOT NULL,
    ramo TEXT NOT NULL,
    pedido_em TEXT NOT NULL,
    pedido_por TEXT NOT NULL,
    atendido_em TEXT,
    resultado TEXT);

CREATE TABLE IF NOT EXISTS github_repos (
    nome TEXT PRIMARY KEY,
    ramo_padrao TEXT,
    privado INTEGER,
    ramos TEXT NOT NULL);
"""


def dir_estado():
    return os.environ.get("ESTADO_DIR", "/opt/estado")


def agora():
    return datetime.datetime.now(FUSO).isoformat(timespec="seconds")


# Colunas acrescentadas depois da criação da tabela (o CREATE TABLE IF NOT
# EXISTS não muda tabela que já existe): (tabela, coluna, definição).
# sistemas.removido_em (DV-291): a API marca o pedido de remoção; o curador
# apaga a pasta da tag no vault, o clone, os lotes e o cadastro.
# fila.origem e fila.perfil (DV-292): de que origem e leitura veio o item.
# DV-547 (tela): fila.tentativas (vezes que o item foi a um lote sem ser
# registrado: "parado"), estado de acesso e commits de cada origem, e quem
# criou cada credencial.
# DV-584: fila.erro (o último erro do lote do item) e fila.parado_em (o item
# falhou VAULT_TENTATIVAS_MAX vezes e saiu dos lotes; continua na fila, então
# o commit da origem não avança, até alguém pedir de novo pela tela).
# DV-554: origens.leituras_antes (as leituras que o vault reflete, até a
# ingestão reconciliar com as novas) e origens.removida_em (pedido de remoção
# da origem; o curador apaga o cadastro quando a fila dela esvazia).
# DV-589: origens.classificacao (a classificação por pasta feita na árvore,
# de onde vieram as leituras; para editar pela árvore depois).
COLUNAS_NOVAS = [("fila", "revisar", "TEXT"), ("sistemas", "removido_em", "TEXT"),
                 ("fila", "origem", "TEXT"), ("fila", "perfil", "TEXT"),
                 ("fila", "tentativas", "INTEGER NOT NULL DEFAULT 0"),
                 ("origens", "acesso_ok", "INTEGER"), ("origens", "acesso_em", "TEXT"),
                 ("origens", "acesso_erro", "TEXT"), ("origens", "commits_atras", "INTEGER"),
                 ("origens", "data_pendente", "TEXT"), ("origens", "data_processado", "TEXT"),
                 ("credenciais", "criado_por", "TEXT"), ("fila", "erro", "TEXT"), ("fila", "parado_em", "TEXT"),
                 ("origens", "leituras_antes", "TEXT"), ("origens", "removida_em", "TEXT"),
                 ("origens", "classificacao", "TEXT"), ("credenciais", "usado_em", "TEXT"),
                 ("rodadas", "trabalhador", "TEXT")]
ATIVOS = "SELECT tag FROM sistemas WHERE removido_em IS NULL ORDER BY tag"


def conectar():
    os.makedirs(dir_estado(), exist_ok=True)
    db = sqlite3.connect(os.path.join(dir_estado(), "estado.db"), timeout=30)
    db.row_factory = sqlite3.Row
    # Vários trabalhadores do curador e a API ao mesmo tempo (DV-606): leitura não bloqueia escrita.
    if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
        try:
            db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
    db.executescript(ESQUEMA)
    for tabela, coluna, definicao in COLUNAS_NOVAS:
        if coluna not in {l["name"] for l in db.execute(f"PRAGMA table_info({tabela})")}:
            try:
                db.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
                db.commit()
            except sqlite3.OperationalError as e:  # a API e o curador ao mesmo tempo
                if "duplicate column" not in str(e):
                    raise
    migrar_origens(db)
    return db


def migrar_origens(db):
    """Sistema da DV-290/291 (uma origem) ganha a origem `principal`, com os
    mesmos commits; itens antigos da fila ficam com essa origem e o perfil do
    sistema. Idempotente."""
    sem = db.execute("SELECT * FROM sistemas s WHERE NOT EXISTS (SELECT 1 FROM origens o WHERE o.tag = s.tag)").fetchall()
    if not sem and not db.execute("SELECT 1 FROM fila WHERE origem IS NULL LIMIT 1").fetchone():
        return
    with db:
        for s in sem:
            leituras = [{"perfil": s["perfil"], "incluir": json.loads(s["incluir"]), "excluir": json.loads(s["excluir"])}]
            db.execute("INSERT OR IGNORE INTO origens (tag, nome, repo, ramo, leituras, commit_processado, "
                       "commit_pendente, criado_em) VALUES (?, 'principal', ?, ?, ?, ?, ?, ?)",
                       (s["tag"], s["repo"], s["ramo"], json.dumps(leituras, ensure_ascii=False),
                        s["commit_processado"], s["commit_pendente"], s["criado_em"]))
        db.execute("UPDATE fila SET origem = 'principal', perfil = (SELECT perfil FROM sistemas WHERE "
                   "sistemas.tag = fila.tag) WHERE origem IS NULL")


def ref(origem, caminho):
    """Como um arquivo de origem aparece no campo `origens` das notas: só o
    caminho na origem `principal`; `<origem>:<caminho>` nas outras."""
    return caminho if origem == "principal" else f"{origem}:{caminho}"


def separar_ref(texto):
    origem, _, caminho = texto.partition(":")
    return (origem, caminho) if caminho and TAG.match(origem) else ("principal", texto)


def url_repo(repo):
    m = re.match(r"^(?:git@([^:]+):|ssh://git@([^/:]+)(?::\d+)?/|https://(github\.com)/)(.+?)(?:\.git)?/?$", repo or "")
    return f"https://{m.group(1) or m.group(2) or m.group(3)}/{m.group(4)}" if m else None


def url_commit(repo, commit):
    base = url_repo(repo)
    return f"{base}/commit/{commit}" if base and commit else None


def url_arquivo(repo, commit, caminho):
    base = url_repo(repo)
    return f"{base}/blob/{commit}/{caminho}" if base and commit else None


def proveniencia(origens, refs, commit_origem):
    """De onde veio uma nota: cada ref do campo `origens` com repositório,
    ramo, commit e link. `origens`: {nome: linha da tabela origens}. O
    `commit_origem` da nota só vale quando ela vem de uma origem só; senão, o
    último commit processado de cada origem."""
    de_quais = {separar_ref(r)[0] for r in refs}
    saida = []
    for r in refs:
        nome, caminho = separar_ref(r)
        o = origens.get(nome)
        commit = commit_origem if len(de_quais) == 1 and commit_origem else \
            (o["commit_processado"] or o["commit_pendente"] if o else None)
        saida.append({"ref": r, "origem": nome, "caminho": caminho, "repo": o["repo"] if o else None,
                      "ramo": o["ramo"] if o else None, "commit": commit,
                      "url": url_arquivo(o["repo"], commit, caminho) if o else None})
    return saida


def nome_clone(tag, origem):
    """Nome da chave de deploy e do clone de uma origem."""
    return tag if origem == "principal" else f"{tag}--{origem}"
