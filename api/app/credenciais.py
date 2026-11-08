"""Credenciais de cliente (DV-289): cada uma presa às tags que pode ler e escrever.

A chave só aparece na criação; o banco guarda o hash (SHA-256: a chave é
aleatória e longa, então não precisa de hash lento). A tag é conferida aqui,
no código, antes de qualquer conteúdo ser tocado.
"""
import datetime
import hashlib
import json
import secrets

from petro_vault.estado import TAG, agora, conectar

PREFIXO = "pv_"
WORKSPACE = "workspace"


class Todas(set):
    """Escopo do token de conexão (Vault System): qualquer tag válida, inclusive a de um vault que
    o primeiro `vs sync` vai criar. Ao listar, são os vaults ativos do workspace."""
    def __contains__(self, tag):
        return isinstance(tag, str) and bool(TAG.match(tag))


def _hash(chave):
    return hashlib.sha256(chave.encode()).hexdigest()


def validar_tags(tags):
    ruins = [t for t in tags if not TAG.match(t)]
    if ruins:
        raise ValueError(f"tag inválida (use minúsculas, números e hífen): {', '.join(ruins)}")
    return sorted(set(tags))


def criar(nome, ler, escrever, por=None, workspace=False):
    """Cria a credencial e devolve a chave (a única vez em que ela aparece). Com workspace, é o
    token de conexão da CLI: lê e escreve em todos os vaults e cria vaults no `vs sync`."""
    ler, escrever = ([], []) if workspace else (validar_tags(ler), validar_tags(escrever))
    chave = PREFIXO + secrets.token_urlsafe(32)
    with conectar() as db:
        db.execute("INSERT INTO credenciais (nome, hash, ler, escrever, criado_em, criado_por, escopo) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (nome, _hash(chave), json.dumps(ler), json.dumps(escrever), agora(),
                                                    por, WORKSPACE if workspace else "vaults"))
    return chave


def buscar(chave):
    """Credencial ativa da chave, ou None. Formato: {nome, ler: set, escrever: set}."""
    if not chave or not chave.startswith(PREFIXO):
        return None
    with conectar() as db:
        linha = db.execute("SELECT nome, ler, escrever, escopo, criado_por FROM credenciais "
                           "WHERE hash = ? AND revogada_em IS NULL", (_hash(chave),)).fetchone()
        if linha:
            _marcar_uso(db, linha["nome"])
            ativos = [l["tag"] for l in db.execute("SELECT tag FROM sistemas WHERE removido_em IS NULL ORDER BY tag")]
    if not linha:
        return None
    if linha["escopo"] == WORKSPACE:
        return {"nome": linha["nome"], "ler": Todas(ativos), "escrever": Todas(ativos), "workspace": True,
                "dono": linha["criado_por"]}
    return {"nome": linha["nome"], "ler": set(json.loads(linha["ler"])), "escrever": set(json.loads(linha["escrever"])),
            "workspace": False, "dono": linha["criado_por"]}


def _marcar_uso(db, nome):
    """Último uso (RF10), gravado no máximo uma vez por minuto por credencial."""
    agora_ = agora()
    antes = (datetime.datetime.fromisoformat(agora_) - datetime.timedelta(minutes=1)).isoformat(timespec="seconds")
    db.execute("UPDATE credenciais SET usado_em = ? WHERE nome = ? AND (usado_em IS NULL OR usado_em < ?)",
               (agora_, nome, antes))


def alterar_leitura(nome, ler):
    """Troca os vaults que a credencial lê, sem trocar a chave. Devolve quantas mudou (0 ou 1)."""
    ler = validar_tags(ler)
    with conectar() as db:
        return db.execute("UPDATE credenciais SET ler = ? WHERE nome = ? AND revogada_em IS NULL",
                          (json.dumps(ler), nome)).rowcount


def listar():
    with conectar() as db:
        return [dict(l) for l in db.execute("SELECT id, nome, ler, escrever, criado_em, criado_por, revogada_em, usado_em, escopo FROM credenciais ORDER BY id")]


def revogar(nome):
    with conectar() as db:
        return db.execute("UPDATE credenciais SET revogada_em = ? WHERE nome = ? AND revogada_em IS NULL",
                          (agora(), nome)).rowcount
