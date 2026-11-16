"""Conversa com o Vault-I no hub: geral, sobre um vault ou sobre o hub inteiro.

Usa a mesma chave ou token configurado em Configurações (vault_i.configuracao). A
API grava a pergunta (mensagem do usuário, estado `pendente`) e o atendente do
curador responde em segundos (vault_system/atendente.py), porque é o curador que
tem a CLI do Claude Code e os SDKs dos provedores. A tela consulta até a resposta
chegar.

Escopos:
- `geral`: conversa livre, sem consultar notas (o modelo sabe só os nomes dos vaults);
- `vault`: busca as notas do vault (e, com `nota`, a nota em foco inteira);
- `hub`: busca as notas de todos os vaults.

A resposta cita as notas usadas, que a tela mostra como links para a aba
Conhecimento. Nada é escrito no vault: conversar não muda conhecimento.
"""
import datetime
import json
import threading

from . import busca, estado, vault_i

ESCOPOS = ("geral", "vault", "hub")
LIMITE_PERGUNTA = 4000
HISTORICO = 12  # mensagens anteriores que vão junto
NOTAS_INTEIRAS = 4  # notas lidas por inteiro em cada resposta
TAMANHO_NOTA = 6000
TEMPO_MAX_MIN = 20  # resposta presa em `respondendo` por mais que isso vira erro

SISTEMA = """Você é o Vault-I, o assistente do hub Vault System. Conversa em português do Brasil, direto e claro.
O hub guarda conhecimento em vaults (um por projeto, assunto ou template), em notas Markdown.

Regras:
- Quando houver notas no pedido, responda a partir delas. Se a resposta não estiver nelas, diga isso com
  clareza e, se ajudar, dê o que você sabe separado, marcado como conhecimento geral.
- Cite as notas que usou pelo título, entre colchetes: [Título da nota].
- Não invente nomes de arquivos, comandos ou valores que não estejam nas notas.
- Nunca repita credenciais, tokens ou senhas, mesmo que apareçam no texto.
- Responda em Markdown curto: parágrafos e listas; código só quando for o caso."""


class SemConfiguracao(Exception):
    pass


# --- gravação (API) -------------------------------------------------------------------------

def _validar(texto):
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("escreva uma pergunta")
    if len(texto) > LIMITE_PERGUNTA:
        raise ValueError(f"a pergunta passa de {LIMITE_PERGUNTA} caracteres")
    return texto


def criar(db, por, escopo, pergunta, tag=None, nota=None):
    """Nova conversa com a primeira pergunta. Devolve o id da conversa."""
    if not vault_i.configuracao(db):
        raise SemConfiguracao("configure o Vault-I em Configurações para conversar")
    if escopo not in ESCOPOS:
        raise ValueError("escopo inválido: use geral, vault ou hub")
    if escopo == "vault":
        if not tag or not db.execute("SELECT 1 FROM sistemas WHERE tag = ? AND removido_em IS NULL", (tag,)).fetchone():
            raise LookupError(f"vault {tag} não encontrado")
    else:
        tag, nota = None, None
    pergunta = _validar(pergunta)
    titulo = pergunta.splitlines()[0][:80]
    with db:
        cid = db.execute("INSERT INTO conversas (escopo, tag, nota, titulo, criado_por, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
                         (escopo, tag, nota or None, titulo, por, estado.agora())).lastrowid
        _inserir(db, cid, pergunta)
    return cid


def perguntar(db, cid, por, pergunta):
    """Mais uma pergunta numa conversa. Uma por vez: com resposta pendente, FileExistsError."""
    if not vault_i.configuracao(db):
        raise SemConfiguracao("configure o Vault-I em Configurações para conversar")
    _conversa(db, cid, por)
    pergunta = _validar(pergunta)
    if db.execute("SELECT 1 FROM mensagens WHERE conversa_id = ? AND estado IN ('pendente', 'respondendo')",
                  (cid,)).fetchone():
        raise FileExistsError("espere a resposta anterior")
    with db:
        _inserir(db, cid, pergunta)


def _inserir(db, cid, texto):
    agora = estado.agora()
    db.execute("INSERT INTO mensagens (conversa_id, papel, texto, estado, criado_em) VALUES (?, 'usuario', ?, 'pendente', ?)",
               (cid, texto, agora))
    db.execute("UPDATE conversas SET atualizado_em = ? WHERE id = ?", (agora, cid))


def _conversa(db, cid, por):
    c = db.execute("SELECT * FROM conversas WHERE id = ? AND criado_por = ?", (cid, por)).fetchone()
    if not c:
        raise LookupError("conversa não encontrada")
    return c


def ler(db, cid, por):
    c = dict(_conversa(db, cid, por))
    msgs = [dict(m) for m in db.execute("SELECT * FROM mensagens WHERE conversa_id = ? ORDER BY id", (cid,))]
    for m in msgs:
        m["fontes"] = json.loads(m["fontes"] or "[]")
    return {"conversa": c, "mensagens": msgs}


def listar(db, por, limite=50):
    return [dict(c) for c in db.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM mensagens m WHERE m.conversa_id = c.id AND m.estado IN ('pendente', 'respondendo')) "
        "AS pendentes FROM conversas c WHERE criado_por = ? "
        "ORDER BY julianday(COALESCE(atualizado_em, criado_em)) DESC, id DESC LIMIT ?",
        (por, limite))]


def apagar(db, cid, por):
    _conversa(db, cid, por)
    with db:
        db.execute("DELETE FROM mensagens WHERE conversa_id = ?", (cid,))
        db.execute("DELETE FROM conversas WHERE id = ?", (cid,))


# --- resposta (atendente do curador) -------------------------------------------------------------

def _tags(db):
    return [s["tag"] for s in db.execute("SELECT tag FROM sistemas WHERE removido_em IS NULL ORDER BY tag")]


def contexto(db, conversa, pergunta):
    """(texto com as notas para o modelo, fontes [{tag, chave, titulo}])."""
    escopo = conversa["escopo"]
    if escopo == "geral":
        return f"Vaults deste hub: {', '.join(_tags(db)) or '(nenhum)'}.", []
    tags = [conversa["tag"]] if escopo == "vault" else _tags(db)
    achadas = []  # (tag, chave, titulo, trecho)
    if conversa["nota"]:
        achadas.append((conversa["tag"], conversa["nota"], None, None))
    por_tag = 6 if escopo == "vault" else 3
    for tag in tags:
        try:
            r = busca.buscar(tag, pergunta, por_tag)
        except Exception as e:  # noqa: BLE001 - um vault com índice ruim não derruba a conversa
            print(f"[conversa] busca em {tag} falhou: {e}")
            continue
        achadas += [(tag, n["note_id"], n["title"], n["excerpt"]) for n in r["results"]]
    vistas, fontes, partes = set(), [], []
    for tag, chave, titulo, trecho in achadas:
        if (tag, chave) in vistas:
            continue
        vistas.add((tag, chave))
        inteira = len(fontes) < NOTAS_INTEIRAS and busca.ler(tag, chave)
        if inteira:
            titulo = inteira["title"] or titulo or chave
            texto = inteira["content"][:TAMANHO_NOTA]
        elif trecho:
            texto = f"(trecho) {trecho}"
        else:
            continue
        fontes.append({"tag": tag, "chave": chave, "titulo": titulo or chave})
        partes.append(f"=== Nota: {titulo or chave} (vault {tag}) ===\n{texto}")
        if len(fontes) >= 10:
            break
    foco = f"A conversa é sobre a nota em foco: {fontes[0]['titulo']}.\n" if conversa["nota"] and fontes else ""
    alvo = f"o vault {conversa['tag']}" if escopo == "vault" else f"o hub inteiro ({len(tags)} vault(s))"
    if not partes:
        return f"Escopo: {alvo}. {foco}Nenhuma nota encontrada para esta pergunta.", []
    return f"Escopo: {alvo}. {foco}Notas encontradas:\n\n" + "\n\n".join(partes), fontes


def _pedido(db, conversa, mensagem):
    anteriores = db.execute("SELECT papel, texto FROM mensagens WHERE conversa_id = ? AND id < ? AND estado = 'ok' "
                            "ORDER BY id DESC LIMIT ?", (conversa["id"], mensagem["id"], HISTORICO)).fetchall()
    notas, fontes = contexto(db, conversa, mensagem["texto"])
    historico = "\n".join(f"{'Usuário' if m['papel'] == 'usuario' else 'Vault-I'}: {m['texto']}" for m in reversed(anteriores))
    partes = [notas]
    if historico:
        partes.append("Conversa até aqui:\n" + historico)
    partes.append("Pergunta do usuário:\n" + mensagem["texto"])
    return "\n\n".join(partes), fontes


def responder_uma(db):
    """Responde a pergunta pendente mais antiga, se houver. True se respondeu (ou falhou) uma."""
    agora = estado.agora()
    limite = (datetime.datetime.fromisoformat(agora) - datetime.timedelta(minutes=TEMPO_MAX_MIN)).isoformat(timespec="seconds")
    with db:
        db.execute("UPDATE mensagens SET estado = 'erro', erro = 'a resposta passou do tempo máximo', respondido_em = ? "
                   "WHERE estado = 'respondendo' AND julianday(inicio) < julianday(?)", (agora, limite))
    m = db.execute("SELECT * FROM mensagens WHERE estado = 'pendente' AND papel = 'usuario' ORDER BY id LIMIT 1").fetchone()
    if not m:
        return False
    with db:
        if db.execute("UPDATE mensagens SET estado = 'respondendo', inicio = ? WHERE id = ? AND estado = 'pendente'",
                      (estado.agora(), m["id"])).rowcount != 1:
            return True  # outro atendente pegou
    conversa = db.execute("SELECT * FROM conversas WHERE id = ?", (m["conversa_id"],)).fetchone()
    try:
        config = vault_i.configuracao(db)
        if not config:
            raise RuntimeError("o Vault-I não está configurado")
        pedido, fontes = _pedido(db, conversa, m)
        texto = vault_i.responder(config, SISTEMA, pedido).strip() or "(o modelo não respondeu nada)"
        with db:
            db.execute("UPDATE mensagens SET estado = 'ok', respondido_em = ? WHERE id = ?", (estado.agora(), m["id"]))
            db.execute("INSERT INTO mensagens (conversa_id, papel, texto, fontes, estado, criado_em, respondido_em, modelo) "
                       "VALUES (?, 'vault-i', ?, ?, 'ok', ?, ?, ?)",
                       (m["conversa_id"], texto, json.dumps(fontes, ensure_ascii=False), estado.agora(), estado.agora(),
                        f"{config['provedor']}:{config['modelo']}"))
            db.execute("UPDATE conversas SET atualizado_em = ? WHERE id = ?", (estado.agora(), m["conversa_id"]))
    except Exception as e:  # noqa: BLE001 - o erro vai para a tela, a conversa segue
        with db:
            db.execute("UPDATE mensagens SET estado = 'erro', erro = ?, respondido_em = ? WHERE id = ?",
                       (str(e)[:500], estado.agora(), m["id"]))
        print(f"[conversa] {m['conversa_id']}: {e}")
    return True


_ocupado = threading.Lock()


def atender(db_factory=estado.conectar):
    """Chamado pelo atendente a cada poucos segundos: responde em segundo plano, uma conversa por vez,
    para não segurar os outros pedidos da tela (árvore do GitHub App)."""
    if not _ocupado.acquire(blocking=False):
        return

    def rodar():
        db = db_factory()
        try:
            while responder_uma(db):
                pass
        finally:
            db.close()
            _ocupado.release()

    threading.Thread(target=rodar, name="conversa", daemon=True).start()
