#!/usr/bin/env python3
"""vs: a linha de comando do Vault System.

Um arquivo só, com a biblioteca padrão do Python (3.8 ou mais novo). Instalar:

    Windows:              irm <hub>/v1/cli/install.ps1 | iex
    Linux, macOS e WSL:   curl -fsSL <hub>/v1/cli/install.sh | sh

Os comandos são em inglês e seguem um padrão só: vs <verbo> [objeto] [chave=valor ...] [--flag ...].
Referência completa: docs/commands.md no repositório do Vault System.

Commands:

  Conexão
    vs login [url=<hub>]                    conecta a um hub com o token de conexão (pedido sem aparecer na tela)
    vs login agent=claude                   configura o agente do vs sync --curate (token do claude setup-token)
    vs logout [agent=<agente>]              apaga o token do hub (ou a credencial do agente)
    vs whoami                               mostra o hub, o token e o dono do workspace

  Pasta do projeto
    vs init                                 prepara a pasta (AGENTS.md, .vs, VS.lock) sem ligar a um vault
    vs init vault=<nome>                    ...e liga a pasta a um vault (padrão mode=documented)
    vs init template=<tipo>                 ...e liga a template-<tipo>; cada subpasta é um template
        mode=literal|documented             literal só guarda os arquivos; documented importa também as notas do agente
        package=<nome>                      aplica o pacote de inicialização init:<nome> do hub
    vs sync                                 envia a pasta para o vault ligado no .vs
    vs sync vault=<nome>                    soma a pasta a um vault (o que outras pastas mandaram fica)
    vs sync template=<tipo>                 soma a pasta a template-<tipo> como um template
        name=<template>                     o nome do template (padrão: o nome da pasta)
        file=<zip>                          envia um ZIP pronto no lugar da pasta
        --dry-run                           só lista o que iria
        --curate                            antes de enviar, o agente da máquina cura a pasta seguindo o AGENTS.md
        agent=<agente>                      o agente do --curate (padrão: o do vs login agent=); hoje: claude

  Templates
    vs list templates [type=<tipo>]         lista os templates do hub
    vs add template <tipo:nome>             aplica um template na pasta
        dir=<pasta>                         em outra pasta
        --dry-run                           só mostra o que faria
        --force                             sobrescreve o que já existe

  Git (opcional)
    vs connect repo <url-ssh>               inicia o Git na pasta e adiciona o remoto vault

  CLI
    vs version                              esta versão e a do hub
    vs update                               baixa a CLI mais nova do hub
    vs help                                 este texto
    vaultsystem                             o painel de boas-vindas

Todo comando aceita --json (saída para scripts e agentes). dir=<pasta> roda o comando em outra
pasta. VS_TOKEN e VS_URL no ambiente têm prioridade sobre ~/.config/vaultsystem/config.json.
"""
import datetime
import getpass
import io
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

os.environ.setdefault("VS_CLI", "1")  # a CLI é sempre o vs do Vault System

VERSAO = "0.2.0"
REGISTRO = os.path.join(".vaultsystem", "templates.json")
INIT_PADRAO = """# AGENTS.md

<!-- vs:inicio (seção gerenciada pelo Vault System) -->
## Protocolo Vault System

Este projeto está ligado a um vault no hub do Vault System (veja `.vs`). Quem
envia é `vs sync`: ele empacota a pasta (respeitando o `.gitignore`) e manda
para o hub. No modo **documented** (literal + documentado), as notas descritas aqui entram no vault
**já curadas**, sem curador no hub. Mantenha as notas em dia sempre que mudar
o que elas explicam.

**Onde e como escrever.** Uma nota por assunto, em Markdown, em `docs/vs/`
(ou em outra pasta do projeto), com este cabeçalho:

```markdown
---
vs: regra
titulo: Desconto máximo do catálogo
origens:
  - app/precos.py
---
# Desconto máximo do catálogo

O desconto nunca passa de 15%: `preco_final` limita o valor recebido.
```

- `vs`: o tipo da nota. Servem para qualquer assunto (estudo, design, produto,
  código):
  - `conceito`: o que algo é, uma definição (ex.: "o que é um vetor").
  - `regra`: o que precisa valer sempre: uma propriedade, uma restrição, uma
    regra de negócio ou de estilo (ex.: "vetores equipolentes").
  - `orientacao`: como fazer algo, passo a passo (ex.: "como deslocar um vetor").
  - `elemento`: uma peça reutilizável: componente, token, ícone, fórmula.
  - `decisao`: o que foi decidido, por quê e o que ficou de fora.
  - `modulo`, `integracao`, `api`, `dado`: só para código: o que uma pasta faz,
    um serviço externo, uma rota, uma estrutura de dados.
  - `nota`: só se nada acima servir.
- `origens`: os arquivos do projeto que a nota explica, com o caminho a partir
  da raiz. O hub liga a nota à cópia de cada um. Arquivo que não existe sai da
  nota, com aviso.
- O corpo começa com `# Título`. Explique com as suas palavras e diga o porquê;
  os arquivos em si já vão junto, como estão. Trechos curtos podem ser citados.
- Para ligar uma nota a outra, use `[[nome-do-arquivo]]`, sem `.md`
  (ex.: `[[vetor-representacao]]`). O hub troca pelo endereço certo.
- **Nunca** escreva credenciais, tokens, senhas ou dados pessoais. O hub mascara
  o que tiver cara de segredo e avisa.

**Ao terminar uma mudança:** atualize ou crie as notas afetadas, apague as que
deixaram de valer e envie:

```bash
vs sync --dry-run   # confira a lista; as notas aparecem marcadas com *
vs sync
```

**Comandos que o agente usa** (referência completa: `vs help`):
- `vs sync`: envia esta pasta ao vault do `.vs`. Nunca rode `vs init` de novo
  numa pasta que já tem `.vs`, e não troque o vault ou o modo sem pedido.
- `vs sync --dry-run`: mostra o que iria, sem enviar.
- `vs list templates` e `vs add template <type:name>`: listam e aplicam
  templates do hub. Use `--dry-run` antes; nunca use `--force` sem pedido.
- Não use `--curate`: ele abre um agente para curar a pasta, e você já é o agente.
<!-- vs:fim -->

## Este projeto
"""


class Erro(Exception):
    pass


# --- configuração -------------------------------------------------------------------

def arquivo_config():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "vaultsystem", "config.json")


def ler_config():
    try:
        with open(arquivo_config(), encoding="utf-8") as f:
            c = json.load(f)
            return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def gravar_config(c):
    caminho = arquivo_config()
    os.makedirs(os.path.dirname(caminho), mode=0o700, exist_ok=True)
    tmp = caminho + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, caminho)


def url_base(config=None):
    c = ler_config() if config is None else config
    if os.environ.get("VS_CLI"):
        return (os.environ.get("VS_URL") or c.get("url") or "").rstrip("/")
    return (os.environ.get("VS_URL") or c.get("url") or "").rstrip("/")


def token(config=None):
    c = ler_config() if config is None else config
    chave = "VS_TOKEN"
    t = os.environ.get(chave) or c.get("token")
    if not t:
        raise Erro(f"sem token: rode vs login (ou defina {chave})")
    return t


# --- HTTP ---------------------------------------------------------------------------

def cli():
    """O nome do comando nas mensagens."""
    return "vs"


def pedir(caminho, chave=None, url=None, bruto=False, pacote=None, query=None):
    """GET na API (PUT com pacote): o JSON (ou, com bruto, (bytes, cabeçalhos))."""
    base = url or url_base()
    if not base:
        raise Erro("configure o servidor com vs login url=<endereço> ou VS_URL")
    req = urllib.request.Request(base + caminho + (query or ""),
                                 headers={"User-Agent": f"vs/{VERSAO}", "Accept": "*/*"})
    if pacote is not None:
        req.method = "PUT"
        req.data = pacote
        req.add_header("Content-Type", "application/zip")
    if chave:
        req.add_header("Authorization", f"Bearer {chave}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = r.read()
            return (dados, r.headers) if bruto else json.loads(dados.decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detalhe = json.loads(e.read().decode("utf-8")).get("detail")
        except Exception:
            detalhe = None
        if e.code == 401:
            raise Erro(f"token inválido ou revogado: rode {cli()} login") from None
        raise Erro(f"{detalhe or e.reason} (HTTP {e.code})") from None
    except urllib.error.URLError as e:
        raise Erro(f"não consegui falar com {url or url_base()}: {e.reason}") from None


# --- argumentos ---------------------------------------------------------------------

def separar_args(argv):
    """(posicionais, {chave: valor}, {flags})."""
    pos, params, flags = [], {}, set()
    for a in argv:
        if a.startswith("--"):
            flags.add(a[2:])
        elif "=" in a and not a.startswith("="):
            k, v = a.split("=", 1)
            params[k] = v
        else:
            pos.append(a)
    return pos, params, flags


def saida(obj, como_json, texto):
    print(json.dumps(obj, ensure_ascii=False, indent=2) if como_json else texto)


# --- comandos -----------------------------------------------------------------------

def cmd_login(pos, params, flags):
    if params.get("agent"):
        if set(params) - {"agent"}:
            raise Erro(f"uso: {cli()} login agent=<claude>")
        return _login_agente(params["agent"], flags)
    c = ler_config()
    url = (params.get("url") or url_base(c)).rstrip("/")
    if not url:
        raise Erro("informe o servidor com vs login url=<endereço>")
    chave = os.environ.get("VS_TOKEN") or getpass.getpass("Token (não aparece ao digitar): ").strip()
    if not chave:
        raise Erro("nenhum token informado")
    try:
        eu = pedir("/v1/eu", chave, url)  # 401 aqui vira "token inválido"
    except Erro as e:
        if "HTTP 404" not in str(e):
            raise
        pedir("/v1/templates", chave, url)  # hub antigo, sem /v1/eu
        eu = {}
    c.update({"url": url, "token": chave})
    gravar_config(c)
    tipo = "token de conexão do workspace" if eu.get("workspace") else "token de vaults"
    dono = f" de {eu['dono']}" if eu.get("dono") else ""
    saida({"ok": True, "url": url, "config": arquivo_config(), **eu}, "json" in flags,
          f"Conectado a {url} com o {tipo}{dono} ({eu.get('credencial', 'credencial')}).\n"
          f"Token guardado em {arquivo_config()} (só você lê).")


def cmd_whoami(pos, params, flags):
    eu = pedir("/v1/eu", token())
    texto = (f"hub     {url_base()}\n"
             f"token   {eu.get('credencial')} ({'conexão do workspace' if eu.get('workspace') else 'vaults marcados'})\n"
             f"dono    {eu.get('dono') or '(criado no terminal do servidor)'}\n"
             f"vaults  {', '.join(eu.get('vaults') or []) or '(nenhum ainda)'}")
    saida({**eu, "url": url_base()}, "json" in flags, texto)


# --- agentes locais (vs sync --curate) -----------------------------------------------------------
#
# Cada agente é um adaptador: como abrir sem conversa, que credencial usa e que permissões libera.
# O agente roda na pasta do projeto, só com ferramentas de ler e editar arquivos, e segue a seção do
# AGENTS.md para escrever as notas. Depois o vs confere as notas e envia.

PEDIDO_CURADORIA = """Você é o curador local do Vault System para esta pasta.
Siga a seção "Protocolo Vault System" do AGENTS.md desta pasta (entre <!-- vs:inicio --> e <!-- vs:fim -->).

Tarefa:
1. Leia os arquivos do projeto (respeite o .gitignore; ignore node_modules, builds e mídia).
2. Crie ou atualize as notas em docs/vs/, uma por assunto, com o cabeçalho do protocolo (vs:, titulo, origens).
3. Apague as notas que deixaram de valer e não mexa em mais nada fora de docs/vs/.
4. Nunca escreva credenciais, tokens, senhas ou dados pessoais.
5. Não rode comandos e não envie nada: quem envia é o vs, depois de você.

Ao terminar, responda só com uma linha: RESUMO: <notas criadas>, <notas atualizadas>, <notas apagadas>."""


class AgenteClaude:
    nome = "claude"
    rotulo = "Claude Code"
    binario = "claude"
    instalar = "npm install -g @anthropic-ai/claude-code"
    credencial = "token do claude setup-token (sk-ant-oat...)"

    def valida_token(self, token):
        if not token.startswith("sk-ant-oat"):
            raise Erro("esse não parece um token do claude setup-token (começa com sk-ant-oat)")

    def comando(self, exe):
        return [exe, "-p", "--output-format", "json",
                "--allowedTools", "Read,Glob,Grep,Write,Edit,MultiEdit",
                "--disallowedTools", "Bash,WebFetch,WebSearch,Task,NotebookEdit",
                "--permission-mode", "acceptEdits"]

    def ambiente(self, token):
        env = dict(os.environ)
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
            env.pop("ANTHROPIC_API_KEY", None)  # a chave de API teria precedência sobre o token
        return env

    def resultado(self, saida):
        """(ok, texto) a partir da saída de claude -p --output-format json."""
        try:
            d = json.loads(saida)
        except ValueError:
            return False, (saida or "").strip()[-300:] or "sem saída"
        texto = str(d.get("result") or "")
        if d.get("is_error"):
            if any(t in texto.lower() for t in ("oauth", "401", "invalid api key", "authentication", "/login")):
                return False, "login do Claude recusado: rode vs login agent=claude com um token novo"
            return False, texto[:300] or "erro do Claude Code"
        return True, texto


AGENTES = {a.nome: a for a in (AgenteClaude(),)}
EM_BREVE = {"codex": "Codex CLI", "gemini": "Gemini CLI", "cursor": "Cursor CLI", "opencode": "opencode"}


def _agente(nome):
    if nome in AGENTES:
        return AGENTES[nome]
    if nome in EM_BREVE:
        raise Erro(f"o agente {nome} ({EM_BREVE[nome]}) ainda não é suportado; por enquanto: {', '.join(AGENTES)}")
    raise Erro(f"agente desconhecido: {nome} (suportados: {', '.join(AGENTES)})")


def _login_agente(nome, flags):
    ag = _agente(nome)
    token = os.environ.get("VS_AGENT_TOKEN") or getpass.getpass(
        f"{ag.credencial} (Enter vazio usa o login que o {ag.rotulo} já tem nesta máquina): ").strip()
    if token:
        ag.valida_token(token)
    c = ler_config()
    c.setdefault("agents", {})[ag.nome] = {"token": token or None}
    c["agent"] = ag.nome
    gravar_config(c)
    instalado = shutil.which(ag.binario) is not None
    saida({"agent": ag.nome, "token": bool(token), "installed": instalado}, "json" in flags,
          f"Agente {ag.rotulo} configurado para o vs sync --curate"
          + (" (com token)." if token else " (usando o login que ele já tem).")
          + ("" if instalado else f"\nAviso: o {ag.rotulo} não está instalado. Instale com: {ag.instalar}"))
    return 0


def _curar_local(raiz, nome, flags):
    """Roda o agente na pasta para escrever as notas. Devolve um resumo."""
    if not os.path.isfile(os.path.join(raiz, "AGENTS.md")):
        raise Erro(f"esta pasta não tem AGENTS.md: rode {cli()} init antes de curar")
    ag = _agente(nome)
    exe = shutil.which(ag.binario)
    if not exe:
        raise Erro(f"o {ag.rotulo} não está instalado. Instale com: {ag.instalar}")
    token = ((ler_config().get("agents") or {}).get(ag.nome) or {}).get("token")
    if "json" not in flags:
        print(f"Curando com o {ag.rotulo}... (pode levar alguns minutos)", file=sys.stderr)
    antes = _fotografia_notas(raiz)
    try:
        r = subprocess.run(ag.comando(exe), input=PEDIDO_CURADORIA, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=raiz, env=ag.ambiente(token),
                           timeout=int(os.environ.get("VS_CURATE_TIMEOUT", "1800")))
    except subprocess.TimeoutExpired:
        raise Erro(f"o {ag.rotulo} passou do tempo máximo; nada foi enviado") from None
    ok, texto = ag.resultado(r.stdout or r.stderr)
    if not ok:
        raise Erro(f"a curadoria com o {ag.rotulo} falhou: {texto}; nada foi enviado")
    depois = _fotografia_notas(raiz)
    return {"agent": ag.nome, "resumo": texto.strip()[-300:],
            "criadas": sorted(set(depois) - set(antes)),
            "atualizadas": sorted(k for k in depois if k in antes and antes[k] != depois[k]),
            "apagadas": sorted(set(antes) - set(depois))}


def _fotografia_notas(raiz):
    """{caminho: conteúdo} das notas do agente (cabeçalho vs:) na pasta."""
    saida_ = {}
    for n in _arquivos_do_projeto(raiz):
        c = os.path.join(raiz, *n.split("/"))
        if n.lower().endswith(".md") and _e_nota(c):
            with open(c, "rb") as f:
                saida_[n] = f.read()
    return saida_


def cmd_logout(pos, params, flags):
    if params.get("agent"):
        c = ler_config()
        nome = params["agent"]
        (c.get("agents") or {}).pop(nome, None)
        if c.get("agent") == nome:
            c.pop("agent", None)
        gravar_config(c)
        saida({"ok": True, "agent": nome}, "json" in flags, f"Credencial do agente {nome} apagada.")
        return 0
    c = ler_config()
    c.pop("token", None)
    if os.path.exists(arquivo_config()):
        gravar_config(c)
    saida({"ok": True}, "json" in flags, "Token apagado.")


class Renomeado(Erro):
    pass


def _renomeado(novo):
    def cmd(pos, params, flags):
        raise Renomeado(f"este comando mudou: use {cli()} {novo}")
    return cmd


def cmd_list(pos, params, flags):
    if pos != ["templates"] or set(params) - {"type"} or flags - {"json"}:
        raise Erro(f"uso: {cli()} list templates [type=<type>] [--json]")
    return cmd_templates([params["type"]] if params.get("type") else [], {}, flags)


def cmd_connect(pos, params, flags):
    if len(pos) != 2 or pos[0] != "repo":
        raise Erro(f"uso: {cli()} connect repo <ssh-url>")
    return cmd_repo(["connect", pos[1]], params, flags)


def cmd_templates(pos, params, flags):
    tipo = pos[0] if pos else None
    r = (pedir("/v1/templates" + (f"?tipo={urllib.parse.quote(tipo)}" if tipo else ""), token())
         if not os.environ.get("VS_CLI") or url_base() else {})
    ts = r.get("templates", [])
    if os.environ.get("VS_CLI") and (not tipo or tipo == "init"):
        ts = [{"id": "init:padrao", "arquivos": 1, "commit": "local", "descricao": "Pacote inicial local"},
              *(t for t in ts if t["id"] != "init:padrao")]
    if not ts:
        texto = f"Nenhum template{' do tipo ' + tipo if tipo else ''}."
    else:
        largura = max(len(t["id"]) for t in ts)
        texto = "\n".join(f"{t['id']:<{largura}}  {t['arquivos']:>2} arquivo(s)  @ {t['commit'][:7]}"
                          + (f"  {t['descricao']}" if t.get("descricao") else "")
                          + ("  [bloqueado: tem segredo]" if t.get("bloqueado") else "") for t in ts)
    saida(ts, "json" in flags, texto)


def _seguro(nome):
    """O caminho do zip, se ele fica dentro da pasta de destino; senão Erro."""
    if not nome or nome.startswith("/") or "\\" in nome or ":" in nome:
        raise Erro(f"caminho inválido no pacote: {nome!r}")
    norm = posixpath.normpath(nome)
    if norm.startswith("../") or norm == ".." or norm != nome.rstrip("/") or any(
        parte.endswith((".", " ")) or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", parte.split(".")[0])
        for parte in norm.split("/")
    ):
        raise Erro(f"caminho inválido no pacote: {nome!r}")
    return norm


def _igual(caminho, dados):
    try:
        with open(caminho, "rb") as f:
            return f.read() == dados
    except OSError:
        return False


def _registrar(destino, ident, commit, nomes):
    caminho = _alvo(destino, _registro())
    try:
        with open(caminho, encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError):
        reg = {}
    lista = [t for t in reg.get("templates", []) if t.get("id") != ident]
    lista.append({"id": ident, "commit": commit, "arquivos": nomes,
                  "em": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                  "servidor": url_base()})
    reg["templates"] = sorted(lista, key=lambda t: t["id"])
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _registro():
    return ".vaultsystem/templates.json" if os.environ.get("VS_CLI") else REGISTRO


def _alvo(destino, rel):
    caminho = os.path.join(destino, *rel.split("/"))
    raiz = os.path.realpath(destino)
    if os.path.normcase(os.path.realpath(caminho)) != os.path.normcase(os.path.join(raiz, *rel.split("/"))):
        raise Erro(f"caminho redirecionado por link: {rel}")
    return caminho


def cmd_add(pos, params, flags):
    if len(pos) != 2 or pos[0] != "template":
        raise Erro(f"uso: {cli()} add template <type:name> [dir=<folder>] [--dry-run] [--force]")
    return _aplicar_template(pos[1], params, flags)


TAG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MODOS = ("literal", "documented")
# Como o hub chama cada modo.
MODO_NO_HUB = {"literal": "literal", "documented": "documentado"}
LIMITE_PACOTE = 10 * 1024 * 1024
# Nunca vão no vs sync, mesmo fora do .gitignore (o hub também filtra segredos e chaves).
FORA_DO_SYNC = {".git", ".vs", "vs.lock", ".vaultsystem", ".vaultsystem", "node_modules", ".venv", "venv",
                "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".turbo", ".idea",
                ".ds_store", "thumbs.db"}


def _nome_vault(texto):
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-") or "projeto"


TIPOS_ALVO = ("vault", "template")


def _alvo_nomeado(tipo, nome):
    """vault <nome> -> <nome>; template <tipo> -> template-<tipo>. Erro se o nome não serve."""
    nome = (nome or "").strip().lower()
    if tipo == "template" and nome.startswith("template-"):
        nome = nome[len("template-"):]
    if not TAG.fullmatch(nome):
        raise Erro(f"nome inválido: {nome!r} (use minúsculas, números e hífen, ex.: my-project ou design)")
    return nome if tipo == "vault" else "template-" + nome


USO_INIT = ("uso: vs init [vault=<name> | template=<type>] [mode=literal|documented] [package=<name>] "
            "[dir=<folder>] [--dry-run] [--force] [--json]")


def cmd_init(pos, params, flags):
    if pos:
        dica = (f"use {cli()} init {pos[0]}={pos[1]}" if len(pos) == 2 and pos[0] in TIPOS_ALVO
                else f"use {cli()} init package={pos[0]}" if len(pos) == 1 else USO_INIT)
        raise Erro(dica)
    pacote = params.pop("package", None) if "package" in params else None
    if pacote is not None and not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", pacote):
        raise Erro("nome de pacote inválido")
    if params.get("vault") and params.get("template"):
        raise Erro(f"use vault=<name> ou template=<type>, não os dois")
    if params.get("vault"):
        params = {**params, "vault": _alvo_nomeado("vault", params["vault"])}
    if params.get("template"):
        tipo = params["template"]
        params = {k: v for k, v in params.items() if k != "template"}
        params["vault"] = _alvo_nomeado("template", tipo)
    if set(params) - {"dir", "vault", "mode"} or flags - {"dry-run", "force", "json"}:
        raise Erro(USO_INIT)
    if params.get("vault") and not TAG.fullmatch(params["vault"]):
        raise Erro("nome de vault inválido: use minúsculas, números e hífen (ex.: meu-projeto)")
    if params.get("mode") and params["mode"] not in MODOS:
        raise Erro("modo inválido: use mode=literal ou mode=documented")
    return _aplicar_template("init:" + (pacote or "padrao"), params, flags, iniciar=True)


def _modo_do_vs(vs):
    """O modo gravado no .vs (aceita o formato antigo, com modo=documentado)."""
    modo = vs.get("mode") or {"documentado": "documented"}.get(vs.get("modo"), vs.get("modo"))
    return modo if modo in MODOS else None


def _ler_vs(raiz):
    """O manifesto .vs da pasta (dict), ou None se não existe."""
    try:
        with open(os.path.join(raiz, ".vs"), encoding="utf-8") as f:
            m = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise Erro(f"o arquivo .vs está ilegível: rode {cli()} init de novo") from None
    return m if isinstance(m, dict) else {}


def _arquivos_do_projeto(raiz):
    """Caminhos relativos (com /) do que vai no vs sync: o que o Git versionaria (respeita o .gitignore),
    ou a pasta inteira fora de um repositório. Sempre sem FORA_DO_SYNC e sem .env (o .env.example vai)."""
    nomes = None
    try:
        r = subprocess.run(["git", "-C", raiz, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if r.returncode == 0 and os.path.normcase(os.path.realpath(r.stdout.strip())) == os.path.normcase(os.path.realpath(raiz)):
            r = subprocess.run(["git", "-C", raiz, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                               capture_output=True)
            if r.returncode == 0:
                nomes = [n for n in r.stdout.decode("utf-8", "surrogateescape").split("\0") if n]
    except FileNotFoundError:
        pass
    if nomes is None:
        nomes = []
        for base, pastas, arquivos in os.walk(raiz):
            pastas[:] = sorted(p for p in pastas if p.casefold() not in FORA_DO_SYNC)
            for a in sorted(arquivos):
                nomes.append(os.path.relpath(os.path.join(base, a), raiz).replace(os.sep, "/"))
    saida = []
    for n in sorted(set(nomes)):
        partes = n.split("/")
        nome = partes[-1].casefold()
        if any(p.casefold() in FORA_DO_SYNC for p in partes):
            continue
        if (nome == ".env" or nome.startswith(".env.")) and nome != ".env.example":
            continue
        caminho = os.path.join(raiz, *partes)
        if os.path.isfile(caminho) and not os.path.islink(caminho):
            saida.append(n)
    return saida


def _empacotar(raiz, nomes, prefixo=None):
    buf, total = io.BytesIO(), 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in nomes:
            caminho = os.path.join(raiz, *n.split("/"))
            total += os.path.getsize(caminho)
            if total > LIMITE_PACOTE:
                raise Erro("o projeto passa de 10 MB: tire do envio o que não é conhecimento (build, mídia, "
                           "dados) pelo .gitignore")
            info = zipfile.ZipInfo((prefixo or "") + n, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            executavel = os.name != "nt" and os.access(caminho, os.X_OK)
            info.external_attr = (0o100755 if executavel else 0o100644) << 16
            with open(caminho, "rb") as f:
                z.writestr(info, f.read())
    return buf.getvalue()


def _e_nota(caminho):
    """O arquivo é uma nota do agente (cabeçalho com `vs:`)? Só para mostrar: quem decide é o hub."""
    try:
        with open(caminho, encoding="utf-8") as f:
            inicio = f.read(4096)
    except (OSError, UnicodeDecodeError):
        return False
    m = re.match(r"^﻿?---\r?\n(.*?)\r?\n---", inicio, re.S)
    return bool(m and re.search(r"(?m)^vs:\s*[a-z]+\s*(#.*)?$", m.group(1)))


def _enviar(tag, pacote, modo, curar=False, origem=None):
    query = "&".join(q for q in (f"mode={modo}" if modo else "", "curate=true" if curar else "",
                                  f"origin={origem}" if origem else "") if q)
    return pedir(f"/v1/sistemas/{tag}/envio", token(), pacote=pacote, query=f"?{query}" if query else None)


def _texto_curadoria(r):
    c = r.get("curadoria")
    if not c:
        return ""
    if c.get("estado") == "pedida":
        return f"\nCuradoria do Vault-I pedida (#{c.get('pedido')}): as notas aparecem no hub quando terminar."
    return f"\nCuradoria do Vault-I não pedida: {c.get('motivo')}"


USO_SYNC = ("uso: vs sync [vault=<name> | template=<type>] [name=<template>] [file=<zip>] "
            "[mode=literal|documented] [agent=<agente>] [dir=<folder>] [--dry-run] [--curate] [--json]")


def cmd_sync(pos, params, flags):
    if pos:
        dica = (f"use {cli()} sync {pos[0]}={pos[1]}" if len(pos) == 2 and pos[0] in TIPOS_ALVO
                else f"use {cli()} sync vault={pos[0]} file={pos[1]}" if len(pos) == 2 else USO_SYNC)
        raise Erro(dica)
    if params.get("vault") and params.get("template"):
        raise Erro("use vault=<name> ou template=<type>, não os dois")
    alvo = None
    for tipo in TIPOS_ALVO:
        if params.get(tipo):
            alvo = (tipo, _alvo_nomeado(tipo, params[tipo]))
    params = {k: v for k, v in params.items() if k not in TIPOS_ALVO}
    if params.get("name") and not (alvo and alvo[0] == "template"):
        raise Erro(f"name= só vale com template=: {cli()} sync template=<type> name=<template>")
    if params.get("file"):
        return _sync_zip(alvo, params, flags)
    return _sync_projeto(params, flags, alvo=alvo)


def _sync_zip(alvo, params, flags):
    """vs sync vault=<name> file=<zip>: envia um ZIP pronto (cria o vault no primeiro envio)."""
    if not alvo or set(params) - {"file", "mode"} or flags - {"json"}:
        raise Erro(f"uso: {cli()} sync vault=<nome> file=<zip> [mode=literal|documented] [--json]")
    modo = params.get("mode")
    if modo not in (None, *MODOS):
        raise Erro("modo inválido: use mode=literal ou mode=documented")
    with open(params["file"], "rb") as f:
        pacote = f.read(LIMITE_PACOTE + 1)
    if len(pacote) > LIMITE_PACOTE or not zipfile.is_zipfile(io.BytesIO(pacote)):
        raise Erro("informe um ZIP válido de até 10 MB")
    modo = modo or ("literal" if alvo[0] == "template" else "documented")
    r = _enviar(alvo[1], pacote, MODO_NO_HUB[modo])
    saida(r, "json" in flags, f"Enviado para {alvo[1]}: {r['arquivos']} arquivo(s) · revisão {r['commit'][:12]}."
                              f"{_texto_curadoria(r)}")
    return 0


def _sync_projeto(params, flags, alvo=None):
    if set(params) - {"dir", "mode", "name", "agent"} or flags - {"json", "dry-run", "curate"} or (params.get("mode") and not alvo):
        raise Erro(USO_SYNC)
    if params.get("mode") and params["mode"] not in MODOS:
        raise Erro("modo inválido: use mode=literal ou mode=documented")
    raiz = os.path.abspath(params.get("dir") or ".")
    vs = _ler_vs(raiz)
    origem = prefixo = None
    if alvo:
        # Destino escolhido na hora: o modo vem do parâmetro, do .vs (se for o mesmo vault) ou do padrão do tipo.
        tipo, tag = alvo
        propria = bool(vs and vs.get("vault") == tag)  # a pasta ligada a esse vault pelo vs init
        do_vs = _modo_do_vs(vs) if propria else None
        vs = {**(vs or {}), "vault": tag,
              "mode": params.get("mode") or do_vs or ("literal" if tipo == "template" else "documented")}
        if not propria:
            # Outra pasta: vira uma origem própria do vault e soma, sem apagar o que as outras enviaram.
            origem = _nome_vault(params.get("name") or os.path.basename(raiz))
            if origem == "envio-local":
                origem = "pasta-" + origem
            if tipo == "template":
                prefixo = origem + "/"  # num vault de template, a pasta inteira é um template: <tipo>:<pasta>
    if vs is None:
        raise Erro(f"esta pasta não tem .vs: rode {cli()} init vault=<name> (ou {cli()} sync vault=<name>)")
    tag, modo = vs.get("vault"), _modo_do_vs(vs)
    if not isinstance(tag, str) or not TAG.fullmatch(tag) or modo not in MODOS:
        raise Erro(f"esta pasta não está ligada a um vault: envie com {cli()} sync vault=<name> ou "
                   f"{cli()} sync template=<type> (ou ligue com {cli()} init vault=<name>)")
    hub = url_base()
    if vs.get("hub") and hub and vs["hub"].rstrip("/") != hub:
        raise Erro(f"esta pasta está ligada ao hub {vs['hub']}, e o login atual é de {hub}: "
                   f"rode {cli()} login url={vs['hub']}")
    curadoria = None
    if "curate" in flags:
        agente = params.get("agent") or ler_config().get("agent") or "claude"
        if "dry-run" in flags:
            print(f"--curate: o agente {agente} curaria a pasta antes do envio (nada roda no --dry-run).",
                  file=sys.stderr)
        else:
            curadoria = _curar_local(raiz, agente, flags)
    elif params.get("agent"):
        raise Erro("agent= só vale com --curate")
    nomes = _arquivos_do_projeto(raiz)
    if not nomes:
        raise Erro("nada para enviar nesta pasta")
    notas = [n for n in nomes if n.lower().endswith(".md") and _e_nota(os.path.join(raiz, *n.split("/")))]
    if "dry-run" in flags:
        r = {"vault": tag, "mode": modo, "hub": hub, "arquivos": [(prefixo or "") + n for n in nomes],
             "notas_do_agente": notas, "origin": origem, "dry_run": True}
        saida(r, "json" in flags,
              f"Simulação: {len(nomes)} arquivo(s) para {tag} ({modo}) em {hub or '(sem hub)'}\n"
              + "\n".join(f"  {'*' if n in notas else ' '} {n}" for n in nomes)
              + (f"\n* nota do agente ({len(notas)}): entra curada no modo documented" if notas else "")
              + "\nNada foi enviado (--dry-run).")
        return 0
    r = _enviar(tag, _empacotar(raiz, nomes, prefixo), MODO_NO_HUB[modo], False, origem)
    if curadoria:
        r["curadoria"] = curadoria
    r.update({"vault": tag, "mode": modo, "notas_do_agente": len(notas)})
    saida(r, "json" in flags,
          f"Enviado para {tag} ({modo}): {r['arquivos']} arquivo(s) · revisão {r['commit'][:12]}"
          + (f" · {len(notas)} nota(s) do agente" if notas and modo == "documented" else "")
          + f".\nO hub processa em instantes: {hub}/sistemas/{tag}"
          + (f"\nCuradoria local ({curadoria['agent']}): {len(curadoria['criadas'])} nota(s) nova(s), "
             f"{len(curadoria['atualizadas'])} atualizada(s), {len(curadoria['apagadas'])} apagada(s)."
             if curadoria else ""))
    return 0


def _aplicar_template(ident, params, flags, iniciar=False):
    tipo, _, nome = ident.partition(":")
    if not tipo or not nome:
        raise Erro("use tipo:nome, como docker:python")
    if ident == "init:padrao" and (iniciar or os.environ.get("VS_CLI")):
        pacote = io.BytesIO()
        with zipfile.ZipFile(pacote, "w") as z:
            z.writestr("AGENTS.md", INIT_PADRAO)
        dados, cab = pacote.getvalue(), {"X-Commit": "local"}
    else:
        dados, cab = pedir(f"/v1/templates/{urllib.parse.quote(tipo, safe='')}/{urllib.parse.quote(nome, safe='')}.zip",
                           token(), bruto=True)
    commit = cab.get("X-Commit") or ""
    destino = os.path.abspath(params.get("dir") or ".")
    forcar, simular = "force" in flags, "dry-run" in flags

    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        itens = [(i, _seguro(i.filename)) for i in z.infolist() if not i.is_dir()]
        _alvo(destino, _registro())
        gerenciados = {}
        if iniciar:
            hub = url_base()
            if hub:
                url = urllib.parse.urlsplit(hub)
                if (url.scheme not in ("https", "http") or not url.hostname or url.username is not None
                        or url.password is not None or url.query or url.fragment):
                    raise Erro("configure uma URL HTTP(S) do hub sem credenciais ou parâmetros")
            anterior = _ler_vs(destino) or {}
            vault = params.get("vault") or anterior.get("vault") or None
            modo_vault = params.get("mode") or _modo_do_vs(anterior) or (
                "literal" if (vault or "").startswith("template-") else "documented")
            conexao = None
            if hub and not simular:
                try:
                    eu = pedir("/v1/eu", token())
                    conexao = {"owner": eu.get("dono"), "token": eu.get("credencial"),
                               "workspace": bool(eu.get("workspace"))}
                except Erro as e:
                    print(f"{cli()}: aviso: sem conexão com o hub agora ({e}); o vínculo fica só com o endereço",
                          file=sys.stderr)
            anterior = {k: v for k, v in anterior.items() if k not in ("versao", "projeto", "modo", "conexao")}
            manifesto = {**anterior, "version": 3, "project": os.path.basename(destino), "hub": hub or None,
                         "vault": vault, "mode": modo_vault,
                         "connection": conexao or anterior.get("connection")}
            gerenciados = {".vs": json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
                          "VS.lock": "# Prévia do Vault System. A CLI ainda não consome este arquivo.\nversion = 0\n"}
            gi = _alvo(destino, ".gitignore")
            try:
                with open(gi, encoding="utf-8") as f:
                    antes = f.read()
            except FileNotFoundError:
                antes = ""
            if not any(l.strip() in ("VS.lock", "/VS.lock") for l in antes.splitlines()):
                gerenciados[".gitignore"] = antes + ("\n" if antes and not antes.endswith("\n") else "") + "/VS.lock\n"
            # AGENTS.md que já existe: só a seção gerenciada (vs:inicio ... vs:fim) é trocada ou acrescentada.
            agents = next(((i, r) for i, r in itens if r == "AGENTS.md"), None)
            existente = _alvo(destino, "AGENTS.md")
            if agents and os.path.isfile(existente):
                novo = z.read(agents[0]).decode("utf-8")
                bloco = re.search(r"<!-- vs:inicio.*?<!-- vs:fim -->\n?", novo, re.S)
                with open(existente, encoding="utf-8") as f:
                    atual = f.read()
                if bloco:
                    if re.search(r"<!-- vs:inicio.*?<!-- vs:fim -->\n?", atual, re.S):
                        mesclado = re.sub(r"<!-- vs:inicio.*?<!-- vs:fim -->\n?", lambda _: bloco.group(0), atual,
                                          count=1, flags=re.S)
                    else:
                        titulo = re.match(r"^#[^\n]*\n+", atual)
                        corte = titulo.end() if titulo else 0
                        mesclado = atual[:corte] + bloco.group(0) + "\n" + atual[corte:]
                    if mesclado != atual:
                        gerenciados["AGENTS.md"] = mesclado
                    itens = [(i, r) for i, r in itens if r != "AGENTS.md"]
            for rel in gerenciados:
                _alvo(destino, rel)
        plano, conflitos = [], []
        for info, rel in itens:
            raiz = rel.split("/")[0].casefold()
            reservados = {".git", ".vaultsystem", ".vaultsystem"}
            if iniciar:
                reservados.update((".vs", "vs.lock", ".gitignore"))
            if raiz in reservados:
                raise Erro(f"caminho reservado no template: {rel}")
            alvo = _alvo(destino, rel)
            if not os.path.lexists(alvo):
                acao = "novo"
            elif os.path.isfile(alvo) and not os.path.islink(alvo) and _igual(alvo, z.read(info)):
                acao = "igual"  # já está como no template: não é conflito
            else:
                acao = "sobrescreve"
                conflitos.append(rel)
            plano.append({"path": rel, "acao": acao})
        resultado = {"template": ident, "commit": commit, "destino": destino, "arquivos": plano,
                     "dry_run": simular}
        if conflitos and not forcar:
            resultado["conflitos"] = conflitos
            if "json" in flags:
                print(json.dumps(resultado, ensure_ascii=False, indent=2))
                return 1
            raise Erro("já existe(m) na pasta, nada foi escrito:\n  " + "\n  ".join(conflitos)
                       + "\nUse --force para sobrescrever, ou dir=<outra pasta>.")
        for rel in gerenciados:
            existe = os.path.lexists(_alvo(destino, rel))
            acao = {".gitignore": "acrescenta", ".vs": "atualiza", "AGENTS.md": "atualiza"}.get(rel, "mantido")
            plano.append({"path": rel, "acao": acao if existe else "novo"})
        if not simular:
            for (info, rel), p in zip(itens, plano):
                if p["acao"] == "igual":
                    continue
                alvo = os.path.join(destino, *rel.split("/"))
                os.makedirs(os.path.dirname(alvo), exist_ok=True)
                if os.path.islink(alvo):
                    os.unlink(alvo)  # não escreve através de link simbólico
                modo = (info.external_attr >> 16) & 0o777
                with open(alvo, "wb") as f:
                    f.write(z.read(info))
                if modo & stat.S_IXUSR:
                    os.chmod(alvo, os.stat(alvo).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            _registrar(destino, ident, commit, [rel for _, rel in itens])
            for rel, conteudo in gerenciados.items():
                alvo = _alvo(destino, rel)
                if rel == ".gitignore":
                    with open(alvo, "a", encoding="utf-8", newline="") as f:
                        f.write(conteudo[len(antes):])
                elif rel in (".vs", "AGENTS.md"):
                    with open(alvo, "w", encoding="utf-8", newline="\n") as f:
                        f.write(conteudo)
                else:
                    try:
                        with open(alvo, "x", encoding="utf-8") as f:
                            f.write(conteudo)
                    except FileExistsError:
                        pass

    marca = {"novo": "+", "sobrescreve": "~", "igual": "=", "mantido": "=", "acrescenta": "+", "atualiza": "~"}
    if iniciar:
        resultado.update({"vault": manifesto["vault"], "mode": manifesto["mode"], "hub": manifesto["hub"]})
    vinculo = ((f"\nPasta pronta, ainda sem vault. Envie com {cli()} sync vault=<name> ou {cli()} sync template=<type>."
                if not manifesto["vault"] else "") if iniciar else "")
    vinculo = vinculo or (f"\nProjeto ligado ao vault {manifesto['vault']} ({manifesto['mode']})"
               + (f" no hub {manifesto['hub']}" if manifesto["hub"] else " (sem hub: rode vs login)")
               + (f", workspace de {manifesto['connection']['owner']}" if (manifesto.get("connection") or {}).get("owner") else "")
               + f".\nPróximo passo: documente seguindo o AGENTS.md e rode {cli()} sync.") if iniciar else ""
    texto = (f"{'Simulação: ' if simular else ''}{ident} @ {commit[:7]} -> {destino}\n"
             + "\n".join(f"  {marca[p['acao']]} {p['path']}" for p in plano)
             + ("\nNada foi escrito (--dry-run)." if simular
                else f"\n{len(plano)} arquivo(s). Registro em {_registro()}.")
             + vinculo)
    saida(resultado, "json" in flags, texto)
    return 0


def cmd_versao(pos, params, flags):
    try:
        servidor = pedir("/v1/cli").get("versao")
    except Erro:
        servidor = None
    info = {"versao": VERSAO, "servidor": servidor, "url": url_base()}
    texto = f"{cli()} {VERSAO}"
    if servidor and servidor != VERSAO:
        texto += f"\nO hub tem a versão {servidor}. Atualize com: {cli()} update"
    saida(info, "json" in flags, texto)


def _script_atual():
    """O arquivo .py desta CLI (o que o instalador colocou na pasta do Vault System)."""
    caminho = os.path.realpath(__file__)
    if not caminho.endswith(".py") and not os.access(caminho, os.W_OK):
        raise Erro("não sei onde esta CLI está instalada; rode o instalador do hub de novo")
    return caminho


def cmd_update(pos, params, flags):
    """Baixa a CLI do hub (GET /v1/cli/vs, sem token) e troca este arquivo, se for mais nova ou diferente."""
    if pos or params or flags - {"json", "force"}:
        raise Erro(f"uso: {cli()} update [--force]")
    base = url_base()
    if not base:
        raise Erro(f"configure o hub antes: {cli()} login url=<endereço>")
    req = urllib.request.Request(base + "/v1/cli/vs", headers={"User-Agent": f"vs/{VERSAO}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            novo = r.read()
    except urllib.error.URLError as e:
        raise Erro(f"não consegui baixar a CLI de {base}: {getattr(e, 'reason', e)}") from None
    m = re.search(rb'^VERSAO = "([^"]+)"', novo, re.M)
    if not novo.startswith(b"#!") or not m:
        raise Erro("o hub não devolveu a CLI esperada; nada mudou")
    versao = m.group(1).decode()
    alvo = _script_atual()
    with open(alvo, "rb") as f:
        igual = f.read() == novo
    if igual and "force" not in flags:
        saida({"versao": versao, "atualizado": False}, "json" in flags, f"Já está na versão do hub ({versao}).")
        return 0
    tmp = alvo + ".novo"
    with open(tmp, "wb") as f:
        f.write(novo)
    os.replace(tmp, alvo)
    saida({"versao": versao, "antes": VERSAO, "atualizado": True, "arquivo": alvo}, "json" in flags,
          f"CLI atualizada: {VERSAO} -> {versao} ({alvo}).")
    return 0


LOGO = ["    .--------.", "   /  o    o  \\--o", "  |    \\  /    |", "  |     @------+--o",
        "  |    /  \\    |", "   \\  o    o  /--o", "    '--------'"]


def cmd_welcome(pos, params, flags):
    """O painel de boas-vindas do comando vaultsystem: marca, hub e sessão, e os primeiros comandos."""
    if os.name == "nt":
        os.system("")  # liga as cores ANSI no console do Windows
    cor = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    azul, ciano, cinza, fim = (("\033[34m", "\033[96m", "\033[37m", "\033[0m") if cor else ("", "", "", ""))
    c = ler_config()
    hub = url_base() or "(não configurado: vs login url=<hub>)"
    sessao = "token no ambiente" if os.environ.get("VS_TOKEN") else ("conectado" if c.get("token") else "sem token")
    info = ["Vault System  [VS CLI]", "Conhecimento distribuído.", "", f"versão    {VERSAO}",
            f"hub       {hub}", f"sessão    {sessao}", ""]
    lw = max(len(l) for l in LOGO) + 3
    w = max(len(l) for l in info)
    borda = "+" + "-" * (lw + w + 4) + "+"
    linhas = [azul + borda + fim]
    for i, l in enumerate(LOGO):
        linhas.append(f"{azul}|  {fim}{ciano}{l.ljust(lw)}{fim}{(ciano if i == 0 else cinza)}{info[i].ljust(w)}  {fim}{azul}|{fim}")
    linhas += [azul + borda + fim, "", f"{ciano}  Para começar{fim}"]
    passos = ["vs login", "vs init vault=<nome>", "vs sync", "vs list templates", "vs help"]
    linhas += [f"    > {p}" for p in passos]
    saida({"versao": VERSAO, "hub": url_base() or None, "sessao": sessao}, "json" in flags, "\n".join(linhas))
    return 0


def cmd_ajuda(pos, params, flags):
    ajuda = __doc__.split("Commands:\n", 1)[1].rstrip()
    print(ajuda)


def cmd_repo(pos, params, flags):
    if len(pos) != 2 or pos[0] != "connect" or params or flags - {"json"}:
        raise Erro("uso: vs connect repo ssh://git@servidor/projetos/demo.git")
    url = pos[1]
    if not re.fullmatch(r"(?:git@[A-Za-z0-9.-]+:|ssh://git@[A-Za-z0-9.-]+(?::[0-9]+)?/)[A-Za-z0-9._/-]+", url):
        raise Erro("informe a URL SSH do repositório com o usuário git")
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE"}}

    def git(*args, check=True):
        try:
            result = subprocess.run(["git", *args], env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
        except FileNotFoundError as exc:
            raise Erro("Git não encontrado. Instale o Git para conectar o projeto.") from exc
        if check and result.returncode:
            raise Erro(result.stderr.strip() or f"falha em git {args[0]}")
        return result

    repo = git("rev-parse", "--git-dir", check=False)
    if repo.returncode:
        if os.path.lexists(".git"):
            raise Erro(repo.stderr.strip() or "não foi possível abrir o repositório local")
        git("init", "--quiet")
    elif git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true" or git("rev-parse", "--show-prefix").stdout.strip():
        raise Erro("execute o comando na raiz de uma pasta de trabalho Git")

    remotes = git("remote").stdout.splitlines()
    if "vault" not in remotes:
        git("remote", "add", "vault", url)
    elif git("config", "--local", "--get-all", "remote.vault.url").stdout.splitlines() != [url]:
        raise Erro("o remoto vault já aponta para outro destino")
    saida({"remoto": "vault", "url": url}, "json" in flags,
          f"Remoto vault configurado: {url}")


COMANDOS = {"login": cmd_login, "logout": cmd_logout, "whoami": cmd_whoami,
            "init": cmd_init, "sync": cmd_sync,
            "list": cmd_list, "add": cmd_add,
            "connect": cmd_connect,
            "version": cmd_versao, "update": cmd_update, "help": cmd_ajuda, "welcome": cmd_welcome,
            # nomes antigos: avisam o novo
            "templates": _renomeado("list templates [type=<type>]"), "repo": _renomeado("connect repo <ssh-url>")}


def main(argv=None):
    nome = os.path.basename(sys.argv[0] or "").lower()
    if nome.startswith(("vs", "vaultsystem")):
        os.environ.setdefault("VS_CLI", "1")  # instalada como vs (ou vs.py): é a CLI do Vault System
    argv = sys.argv[1:] if argv is None else argv
    if nome.startswith("vaultsystem") and not argv:
        argv = ["welcome"]
    if not argv or argv[0] in ("-h", "--help"):
        cmd_ajuda([], {}, set())
        return 0
    if argv[0] == "--version":
        argv = ["version"]
    comando = COMANDOS.get(argv[0])
    if not comando:
        print(f"{cli()}: comando desconhecido: {argv[0]} (veja {cli()} help)", file=sys.stderr)
        return 2
    pos, params, flags = separar_args(argv[1:])
    try:
        return comando(pos, params, flags) or 0
    except Erro as e:
        print(f"{cli()}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"{cli()}: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
