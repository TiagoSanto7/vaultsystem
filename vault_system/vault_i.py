"""Vault-I (Vault Intelligence): curadoria interna do hub com uma chave de API, só sob demanda.

A chave (Claude ou OpenAI) é configurada em Configurações, no painel. A curadoria
**nunca é automática**: só roda quando alguém pede, pelo botão "Curar com Vault-I"
de um vault ou com `vs sync --curate`. Cada pedido vira uma linha em `curadorias`;
o curador (coordenador) passa o vault na frente e atende aqui, depois da ingestão.

O que o Vault-I escreve tem o mesmo formato das notas do agente local
(vault_system/agente.py): tipo, título, origens e corpo, nas pastas do tipo, com
`curada_por: vault-i` e o modelo no cabeçalho. A cada pedido, as notas anteriores
do Vault-I daquele vault são refeitas. Uma nota do agente com o mesmo caminho
prevalece (o Vault-I não sobrescreve o que o agente do projeto escreveu).

Sem chave configurada não há erro: o pedido nem é aceito, e o vault fica com o que
o código e o agente local fizeram.
"""
import json
import os
import re
import unicodedata

from . import agente, estado, filtros, historico, ingestao, literal, notas

CHAVE_CONFIG = "vault_i"
CURADA_POR = "vault-i"
PROVEDORES = {
    "anthropic": {"nome": "Claude (chave de API)", "modelo": "claude-opus-5-5"},
    "claude-code": {"nome": "Claude (token do claude setup-token)", "modelo": "claude-opus-5-5"},
    "openai": {"nome": "OpenAI (Codex)", "modelo": "gpt-5"},
}
LIMITE_ARQUIVO = 60 * 1024        # arquivo maior fica de fora (registrado no detalhe)
LIMITE_LOTE = 80_000              # caracteres de fonte por chamada ao modelo
LOTES_MAX = int(os.environ.get("VAULT_I_LOTES_MAX", "6"))  # teto de chamadas por pedido

ESQUEMA = {
    "type": "object",
    "properties": {
        "notas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": sorted({t for _, t in agente.TIPOS.values()})},
                    "titulo": {"type": "string"},
                    "origens": {"type": "array", "items": {"type": "string"}},
                    "corpo": {"type": "string"},
                },
                "required": ["tipo", "titulo", "origens", "corpo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["notas"],
    "additionalProperties": False,
}

SISTEMA = """Você é o Vault-I, o curador do Vault System. Recebe arquivos de um projeto e escreve notas de
conhecimento em português do Brasil para pessoas e agentes reutilizarem.

Regras:
- Uma nota por assunto. Tipos: elemento (peça reutilizável: componente, token, ícone, tela), regra (o que
  precisa valer sempre), orientacao (como fazer ou montar algo), decisao (o que foi decidido e por quê),
  modulo (o que uma pasta de código faz), integracao (serviço externo), api (rota), dado (estrutura de
  dados) e nota (o resto).
- `origens` lista os caminhos exatos, como vieram, dos arquivos que a nota explica. Nunca invente caminho.
- O corpo é Markdown e começa com `# <título>`. Explique o comportamento e o porquê; não copie arquivos
  inteiros (eles já estão no vault como estão). Trechos curtos podem ser citados.
- Nunca escreva credenciais, tokens, senhas ou dados pessoais.
- Não repita assuntos que já têm nota (a lista vem no pedido); escreva só o que acrescenta.
- Responda só com o JSON pedido."""


class SemConfiguracao(Exception):
    pass


# --- configuração -------------------------------------------------------------------

def configuracao(db):
    """{provedor, modelo, chave, atualizado_em, atualizado_por} ou None."""
    l = db.execute("SELECT valor, atualizado_em, atualizado_por FROM configuracoes WHERE chave = ?",
                   (CHAVE_CONFIG,)).fetchone()
    if not l:
        return None
    try:
        c = json.loads(l["valor"])
    except ValueError:
        return None
    if c.get("provedor") not in PROVEDORES or not c.get("chave"):
        return None
    return {**c, "atualizado_em": l["atualizado_em"], "atualizado_por": l["atualizado_por"]}


def disponivel(db):
    return configuracao(db) is not None


def publica(db):
    """O que a tela vê: nunca a chave, só os últimos caracteres."""
    c = configuracao(db)
    base = {"provedores": [{"id": k, **v} for k, v in PROVEDORES.items()]}
    if not c:
        return {**base, "configurada": False}
    return {**base, "configurada": True, "provedor": c["provedor"], "modelo": c["modelo"],
            "chave_final": "…" + c["chave"][-4:], "atualizado_em": c["atualizado_em"],
            "atualizado_por": c["atualizado_por"]}


def salvar(db, provedor, modelo, chave, por):
    """Grava a configuração. Chave vazia mantém a que já existe (troca só o provedor ou o modelo)."""
    if provedor not in PROVEDORES:
        raise ValueError("provedor inválido: use anthropic ou openai")
    modelo = (modelo or "").strip() or PROVEDORES[provedor]["modelo"]
    if not re.fullmatch(r"[A-Za-z0-9._:/-]{2,80}", modelo):
        raise ValueError("modelo inválido")
    chave = (chave or "").strip()
    if not chave:
        atual = configuracao(db)
        if not atual or atual["provedor"] != provedor:
            raise ValueError("informe a chave de API")
        chave = atual["chave"]
    if len(chave) < 20 or any(c.isspace() for c in chave):
        raise ValueError("essa chave não parece uma chave de API")
    if provedor == "claude-code" and not chave.startswith("sk-ant-oat"):
        raise ValueError("esse não parece um token do claude setup-token (começa com sk-ant-oat)")
    if provedor == "anthropic" and chave.startswith("sk-ant-oat"):
        raise ValueError("isso é um token do claude setup-token: escolha o provedor Claude (token do claude setup-token)")
    with db:
        db.execute("INSERT INTO configuracoes (chave, valor, atualizado_em, atualizado_por) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em, "
                   "atualizado_por = excluded.atualizado_por",
                   (CHAVE_CONFIG, json.dumps({"provedor": provedor, "modelo": modelo, "chave": chave}),
                    estado.agora(), por))


def remover(db):
    with db:
        return db.execute("DELETE FROM configuracoes WHERE chave = ?", (CHAVE_CONFIG,)).rowcount


# --- pedidos ------------------------------------------------------------------------

def pedir(db, tag, por, via):
    """Registra um pedido de curadoria (ou devolve o que já está pendente). SemConfiguracao sem chave."""
    if not disponivel(db):
        raise SemConfiguracao("Vault-I sem chave de API: configure em Configurações, no hub.")
    with db:
        p = db.execute("SELECT id FROM curadorias WHERE tag = ? AND estado IN ('pedida', 'em_curso') "
                       "ORDER BY id LIMIT 1", (tag,)).fetchone()
        if p:
            return p["id"], True
        cur = db.execute("INSERT INTO curadorias (tag, pedido_em, pedido_por, via) VALUES (?, ?, ?, ?)",
                         (tag, estado.agora(), por, via))
        return cur.lastrowid, False


def pendentes(db):
    return [l["tag"] for l in db.execute(
        "SELECT c.tag, MIN(c.pedido_em) AS em FROM curadorias c JOIN sistemas s ON s.tag = c.tag "
        "WHERE c.estado = 'pedida' AND s.removido_em IS NULL GROUP BY c.tag ORDER BY em")]


def listar(db, tag, limite=10):
    return [dict(l) for l in db.execute("SELECT * FROM curadorias WHERE tag = ? ORDER BY id DESC LIMIT ?",
                                        (tag, limite))]


# --- arquivos do snapshot -------------------------------------------------------------

def _fontes(db, tag):
    """[(origem, caminho, texto)] dos arquivos de texto do snapshot processado (máscara de segredo aplicada),
    sem as notas do agente; e a lista do que ficou de fora."""
    saida, fora = [], []
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome", (tag,)).fetchall():
        commit, clone = o["commit_processado"], ingestao.dir_clone(tag, o["nome"])
        if not commit or not os.path.isdir(os.path.join(clone, "objects")):
            continue
        for caminho, blob, modo in ingestao.arvore(clone, commit):
            if modo in ("120000", "160000"):
                continue
            if int(ingestao._git(["cat-file", "-s", blob], cwd=clone)) > LIMITE_ARQUIVO:
                fora.append(f"{caminho} (grande)")
                continue
            texto, motivo = filtros.por_conteudo(ingestao._git(["cat-file", "blob", blob], cwd=clone, binario=True))
            if motivo:
                continue  # binário ou segredo que não dá para mascarar
            texto, _ = filtros.mascarar(texto.replace("\r\n", "\n"))
            if caminho.lower().endswith(".md") and agente.do_agente(agente.cabecalho(texto)[0]):
                continue  # nota do agente: já entra curada
            saida.append((o["nome"], caminho, texto))
    return saida, fora


def _lotes(fontes):
    lote, tamanho = [], 0
    for f in fontes:
        n = len(f[2]) + len(f[1]) + 32
        if lote and tamanho + n > LIMITE_LOTE:
            yield lote
            lote, tamanho = [], 0
        lote.append(f)
        tamanho += n
    if lote:
        yield lote


def _pedido(tag, lote, existentes):
    partes = [f"Vault `{tag}`. Notas que já existem (não repita): "
              + (", ".join(existentes) if existentes else "nenhuma") + ".", "", "Arquivos:"]
    for _origem, caminho, texto in lote:
        partes += ["", f"=== {caminho} ===", texto]
    return "\n".join(partes)


# --- chamada ao modelo ------------------------------------------------------------------

def chamar(config, pedido):
    """Chama o modelo configurado e devolve a lista de notas (dicts do ESQUEMA)."""
    if config["provedor"] == "anthropic":
        import anthropic
        cliente = anthropic.Anthropic(api_key=config["chave"])
        try:
            r = cliente.messages.create(
                model=config["modelo"], max_tokens=16000, system=SISTEMA,
                thinking={"type": "adaptive"}, output_config={"effort": "high", "format": {
                    "type": "json_schema", "schema": ESQUEMA}},
                messages=[{"role": "user", "content": pedido}])
        except anthropic.AuthenticationError:
            raise RuntimeError("chave de API recusada pela Anthropic") from None
        except anthropic.RateLimitError:
            raise RuntimeError("limite de uso da Anthropic atingido; tente de novo mais tarde") from None
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Anthropic respondeu {e.status_code}: {e.message}") from None
        except anthropic.APIConnectionError:
            raise RuntimeError("sem conexão com a API da Anthropic") from None
        if r.stop_reason == "refusal":
            raise RuntimeError("o modelo recusou este lote")
        if r.stop_reason == "max_tokens":
            raise RuntimeError("a resposta do modelo passou do limite de tamanho")
        texto = next((b.text for b in r.content if b.type == "text"), "")
    elif config["provedor"] == "openai":
        import openai
        cliente = openai.OpenAI(api_key=config["chave"])
        try:
            r = cliente.responses.create(
                model=config["modelo"], instructions=SISTEMA, input=pedido,
                text={"format": {"type": "json_schema", "name": "notas", "schema": ESQUEMA, "strict": True}})
        except openai.AuthenticationError:
            raise RuntimeError("chave de API recusada pela OpenAI") from None
        except openai.RateLimitError:
            raise RuntimeError("limite de uso da OpenAI atingido; tente de novo mais tarde") from None
        except openai.APIStatusError as e:
            raise RuntimeError(f"OpenAI respondeu {e.status_code}") from None
        except openai.APIConnectionError:
            raise RuntimeError("sem conexão com a API da OpenAI") from None
        texto = r.output_text
    elif config["provedor"] == "claude-code":
        texto = _claude_code(config, pedido)
    else:
        raise RuntimeError(f"provedor desconhecido: {config['provedor']}")
    try:
        return json.loads(_so_json(texto))["notas"]
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("o modelo não devolveu o JSON esperado") from None


def responder(config, sistema, pedido):
    """Resposta em texto livre (conversa do hub, vault_system/conversa.py), com o mesmo provedor da curadoria."""
    if config["provedor"] == "anthropic":
        import anthropic
        cliente = anthropic.Anthropic(api_key=config["chave"])
        try:
            r = cliente.messages.create(model=config["modelo"], max_tokens=8000, system=sistema,
                                        thinking={"type": "adaptive"}, messages=[{"role": "user", "content": pedido}])
        except anthropic.AuthenticationError:
            raise RuntimeError("chave de API recusada pela Anthropic") from None
        except anthropic.RateLimitError:
            raise RuntimeError("limite de uso da Anthropic atingido; tente de novo mais tarde") from None
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Anthropic respondeu {e.status_code}: {e.message}") from None
        except anthropic.APIConnectionError:
            raise RuntimeError("sem conexão com a API da Anthropic") from None
        if r.stop_reason == "refusal":
            raise RuntimeError("o modelo recusou responder")
        return "".join(b.text for b in r.content if b.type == "text")
    if config["provedor"] == "openai":
        import openai
        cliente = openai.OpenAI(api_key=config["chave"])
        try:
            r = cliente.responses.create(model=config["modelo"], instructions=sistema, input=pedido)
        except openai.AuthenticationError:
            raise RuntimeError("chave de API recusada pela OpenAI") from None
        except openai.RateLimitError:
            raise RuntimeError("limite de uso da OpenAI atingido; tente de novo mais tarde") from None
        except openai.APIStatusError as e:
            raise RuntimeError(f"OpenAI respondeu {e.status_code}") from None
        except openai.APIConnectionError:
            raise RuntimeError("sem conexão com a API da OpenAI") from None
        return r.output_text
    if config["provedor"] == "claude-code":
        return _claude_code(config, pedido, sistema)
    raise RuntimeError(f"provedor desconhecido: {config['provedor']}")


def _so_json(texto):
    """O objeto JSON da resposta, mesmo que venha entre cercas de código ou com texto em volta."""
    texto = (texto or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.S)
    if m:
        return m.group(1)
    i, j = texto.find("{"), texto.rfind("}")
    return texto[i:j + 1] if i >= 0 and j > i else texto


CLAUDE_BIN = os.environ.get("VAULT_I_CLAUDE_BIN", "claude")
SEM_FERRAMENTAS = "Bash,Edit,Write,MultiEdit,NotebookEdit,Read,Glob,Grep,LS,WebFetch,WebSearch,Task,TodoWrite"


def _claude_code(config, pedido, instrucao=None):
    """Token do `claude setup-token`: roda a CLI oficial do Claude Code em modo não interativo (`claude -p`),
    numa pasta vazia e sem ferramentas, só para gerar o JSON das notas."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="vault-i-") as pasta:
        env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": config["chave"], "HOME": pasta,
               "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        env.pop("ANTHROPIC_API_KEY", None)  # a chave de API teria precedência sobre o token
        instrucao = instrucao or (SISTEMA + "\n\nResponda só com um objeto JSON neste esquema, sem texto antes ou depois:\n"
                     + json.dumps(ESQUEMA, ensure_ascii=False))
        try:
            r = subprocess.run([CLAUDE_BIN, "-p", "--output-format", "json", "--model", config["modelo"],
                                "--system-prompt", instrucao, "--disallowedTools", SEM_FERRAMENTAS],
                               input=pedido, capture_output=True, text=True, encoding="utf-8", cwd=pasta, env=env,
                               timeout=int(os.environ.get("VAULT_I_TEMPO_MAX", "900")))
        except FileNotFoundError:
            raise RuntimeError("a CLI do Claude Code não está instalada no curador") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError("o Claude Code passou do tempo máximo") from None
    try:
        saida = json.loads(r.stdout)
    except ValueError:
        detalhe = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["sem saída"]
        raise RuntimeError(f"o Claude Code falhou: {detalhe[0][:200]}") from None
    if saida.get("is_error"):
        texto = str(saida.get("result") or saida.get("subtype") or "erro")
        if any(p in texto.lower() for p in ("invalid api key", "oauth", "unauthorized", "401", "authentication")):
            raise RuntimeError("token do claude setup-token recusado")
        raise RuntimeError(f"o Claude Code respondeu com erro: {texto[:200]}")
    return saida.get("result") or ""


# --- escrever ---------------------------------------------------------------------------

def _do_vault_i(tag):
    saida = {}
    for pasta in agente.PASTAS:
        for c in notas.todas(tag, (pasta,)).values():
            if notas.ler(c)[0].get("curada_por") == CURADA_POR:
                saida[c] = True
    return saida


def _escrever(db, tag, config, nota, por_caminho, commits, usados):
    tipo = str(nota.get("tipo") or "").strip().lower()
    if tipo not in agente.TIPOS:
        return None
    pasta, tipo_nota = agente.TIPOS[tipo]
    origens = [estado.ref(por_caminho[p][0], p) for p in dict.fromkeys(nota.get("origens") or []) if p in por_caminho]
    if not origens:
        return None  # sem origem real, a nota não entra (o verificador acusaria)
    titulo = str(nota.get("titulo") or "").strip()[:120] or "Nota"
    corpo, _ = filtros.mascarar(str(nota.get("corpo") or ""))
    if not notas.TITULO.search(corpo):
        corpo = f"# {titulo}\n\n" + corpo.lstrip("\n")
    ligacoes = []
    for ref in origens:
        o, p = estado.separar_ref(ref)
        lit = literal.nota_literal(tag, o, p)
        if os.path.exists(lit):
            ligacoes.append(f"- [[{notas.chave(lit)}]]")
    if ligacoes:
        corpo = corpo.rstrip("\n") + "\n\n<!-- arquivos -->\n## Arquivos de origem\n\n" + "\n".join(ligacoes) + "\n"
    sem_acento = unicodedata.normalize("NFKD", titulo.lower()).encode("ascii", "ignore").decode()
    nome = re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")[:60].strip("-") or "nota"
    base = nome
    i = 2
    while (pasta, nome) in usados or os.path.exists(os.path.join(notas.pasta_tag(tag), pasta, nome + ".md")):
        nome = f"{base}-{i}"
        i += 1
    usados.add((pasta, nome))
    destino = os.path.join(notas.pasta_tag(tag), pasta, nome + ".md")
    origem0 = estado.separar_ref(origens[0])[0]
    agora = estado.agora()
    notas.escrever(destino, {"sistema": tag, "tipo_nota": tipo_nota, "origens": origens,
                             "commit_origem": commits.get(origem0), "criado_em": agora, "atualizado_em": agora,
                             "curada_por": CURADA_POR, "modelo": f"{config['provedor']}:{config['modelo']}"}, corpo)
    return destino


def atender(db, tag):
    """Atende o pedido pendente de curadoria do vault, se houver. Devolve o número de notas escritas ou None."""
    p = db.execute("SELECT id FROM curadorias WHERE tag = ? AND estado = 'pedida' ORDER BY id LIMIT 1",
                   (tag,)).fetchone()
    if not p:
        return None
    config = configuracao(db)
    with db:
        db.execute("UPDATE curadorias SET estado = ?, inicio = ? WHERE id = ?",
                   ("em_curso" if config else "erro", estado.agora(), p["id"]))
    if not config:
        with db:
            db.execute("UPDATE curadorias SET fim = ?, erro = ? WHERE id = ?",
                       (estado.agora(), "Vault-I sem chave de API no momento da curadoria", p["id"]))
        return None
    print(f"[vault-i] {tag}: curadoria pedida (#{p['id']}), {config['provedor']}:{config['modelo']}")
    try:
        fontes, fora = _fontes(db, tag)
        commits = {o["nome"]: o["commit_processado"] for o in db.execute("SELECT * FROM origens WHERE tag = ?", (tag,))}
        por_caminho = {c: (o, t) for o, c, t in fontes}
        antigas = _do_vault_i(tag)
        for c in antigas:
            os.remove(c)  # o Vault-I refaz as notas dele a cada pedido
        existentes = sorted(notas.titulo(notas.ler(c)[1], os.path.basename(c)[:-3])
                            for pasta in agente.PASTAS for c in notas.todas(tag, (pasta,)).values())
        lotes = list(_lotes(fontes))
        escritas, usados, erros = [], set(), []
        for n, lote in enumerate(lotes[:LOTES_MAX]):
            try:
                resposta = chamar(config, _pedido(tag, lote, existentes + [os.path.basename(e)[:-3] for e in escritas]))
            except RuntimeError as e:
                erros.append(f"lote {n + 1}: {e}")
                if "recusada" in str(e) or "sem conexão" in str(e):
                    break
                continue
            for nota in resposta:
                destino = _escrever(db, tag, config, nota, por_caminho, commits, usados)
                if destino:
                    escritas.append(destino)
        detalhe = {"arquivos": len(fontes), "lotes": len(lotes), "lotes_feitos": min(len(lotes), LOTES_MAX),
                   "fora": fora[:50], "erros": erros}
        if len(lotes) > LOTES_MAX:
            detalhe["aviso"] = f"o vault tem {len(lotes)} lotes; o Vault-I curou os {LOTES_MAX} primeiros"
        resultado = "erro" if erros and not escritas else "feita"
        with db:
            db.execute("UPDATE curadorias SET estado = ?, fim = ?, notas = ?, erro = ?, detalhe = ? WHERE id = ?",
                       (resultado, estado.agora(), len(escritas), "; ".join(erros) or None,
                        json.dumps(detalhe, ensure_ascii=False), p["id"]))
        if erros:
            historico.aviso(db, tag, "vault_i", "; ".join(erros))
        print(f"[vault-i] {tag}: {len(escritas)} nota(s) escrita(s); {len(erros)} lote(s) com erro")
        return len(escritas)
    except Exception as e:  # noqa: BLE001 - o pedido fecha com erro; a rodada segue
        with db:
            db.execute("UPDATE curadorias SET estado = 'erro', fim = ?, erro = ? WHERE id = ?",
                       (estado.agora(), f"erro interno: {e}", p["id"]))
        print(f"[vault-i] {tag}: erro na curadoria: {e}")
        return None
