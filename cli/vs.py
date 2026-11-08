#!/usr/bin/env python3
"""vs: a linha de comando do Vault System.

Um arquivo só, com a biblioteca padrão do Python (3.8 ou mais novo). Instalar:

    Windows:              irm <hub>/v1/cli/install.ps1 | iex
    Linux, macOS e WSL:   curl -fsSL <hub>/v1/cli/install.sh | sh

Comandos:

    vs login [url=<endereço>]          conecta ao hub com o token de conexão (pergunta sem eco)
    vs logout                          apaga o token guardado
    vs whoami                          o hub, o token e o dono do workspace
    vs templates [tipo]                lista os templates (de um tipo ou todos)
    vs init [nome]                     prepara a pasta: AGENTS.md, .vs (vínculo com o hub) e VS.lock
        vault=<nome>                   o vault desta pasta no hub (padrão: o nome da pasta)
        modo=literal|documentado       padrão: documentado (vault template-*: literal)
    vs sync                            empacota a pasta e envia ao vault do .vs (cria no 1º envio)
        --dry-run                      só lista o que iria
        --curate                       pede a curadoria do Vault-I (precisa de chave de API no hub)
    vs sync <vault> <arquivo.zip>       envia um ZIP pronto para o vault
        modo=literal|documentado      cria o vault ao enviar o primeiro snapshot
    vs add template <tipo:nome>        baixa o template na pasta atual
        dir=<pasta>                    noutra pasta
        --dry-run                      só mostra o que faria
        --force                        sobrescreve o que já existe
    vs repo conectar <url-ssh>         inicializa o Git e configura o remoto vault
    vs version                         esta versão e a do servidor
    vs update                          baixa do hub a versão mais nova da CLI
    vs welcome                         o painel de boas-vindas (o comando vaultsystem)
    vs help                            este texto

Todo comando aceita --json (saída para script e agente). VS_TOKEN e VS_URL no
ambiente têm prioridade sobre ~/.config/vaultsystem/config.json.
"""
import datetime
import getpass
import io
import json
import os
import posixpath
import re
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
para o hub. No modo **documentado**, as notas descritas aqui entram no vault
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

- `vs`: o tipo da nota.
  - `elemento`: uma peça reutilizável (componente, token, ícone, tela).
  - `regra`: o que precisa valer sempre (de negócio, de uso, de estilo).
  - `orientacao`: como fazer ou montar algo, passo a passo.
  - `decisao`: o que foi decidido, por quê e o que ficou de fora.
  - `modulo`, `integracao`, `api`, `dado`: o código por pasta, serviço
    externo, rota e estrutura de dados.
  - `nota`: o que não se encaixa nos outros.
- `origens`: os arquivos do projeto que a nota explica, com o caminho a partir
  da raiz. O hub liga a nota à cópia de cada um. Arquivo que não existe sai da
  nota, com aviso.
- O corpo começa com `# Título`. Explique o comportamento e o porquê; os
  arquivos em si já vão junto, como estão. Trechos curtos podem ser citados.
- **Nunca** escreva credenciais, tokens, senhas ou dados pessoais. O hub mascara
  o que tiver cara de segredo e avisa.

**Ao terminar uma mudança:** atualize ou crie as notas afetadas, apague as que
deixaram de valer e rode `vs sync`.
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


def cmd_logout(pos, params, flags):
    c = ler_config()
    c.pop("token", None)
    if os.path.exists(arquivo_config()):
        gravar_config(c)
    saida({"ok": True}, "json" in flags, "Token apagado.")


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
        raise Erro("uso: vs add template <tipo:nome> [dir=<pasta>] [--dry-run] [--force]")
    return _aplicar_template(pos[1], params, flags)


TAG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MODOS = ("literal", "documentado")
LIMITE_PACOTE = 10 * 1024 * 1024
# Nunca vão no vs sync, mesmo fora do .gitignore (o hub também filtra segredos e chaves).
FORA_DO_SYNC = {".git", ".vs", "vs.lock", ".vaultsystem", ".vaultsystem", "node_modules", ".venv", "venv",
                "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".turbo", ".idea",
                ".ds_store", "thumbs.db"}


def _nome_vault(texto):
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-") or "projeto"


def cmd_init(pos, params, flags):
    if len(pos) > 1 or set(params) - {"dir", "vault", "modo"} or flags - {"dry-run", "force", "json"}:
        raise Erro(f"uso: {cli()} init [nome] [vault=<nome>] [modo=literal|documentado] [dir=<pasta>] "
                   "[--dry-run] [--force] [--json]")
    if params.get("vault") and not TAG.fullmatch(params["vault"]):
        raise Erro("nome de vault inválido: use minúsculas, números e hífen (ex.: meu-projeto)")
    if params.get("modo") and params["modo"] not in MODOS:
        raise Erro("modo inválido: use modo=literal ou modo=documentado")
    return _aplicar_template("init:" + (pos[0] if pos else "padrao"), params, flags, iniciar=True)


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


def _empacotar(raiz, nomes):
    buf, total = io.BytesIO(), 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in nomes:
            caminho = os.path.join(raiz, *n.split("/"))
            total += os.path.getsize(caminho)
            if total > LIMITE_PACOTE:
                raise Erro("o projeto passa de 10 MB: tire do envio o que não é conhecimento (build, mídia, "
                           "dados) pelo .gitignore")
            info = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0))
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


def _enviar(tag, pacote, modo, curar=False):
    query = "&".join(q for q in (f"modo={modo}" if modo else "", "curar=true" if curar else "") if q)
    return pedir(f"/v1/sistemas/{tag}/envio", token(), pacote=pacote, query=f"?{query}" if query else None)


def _texto_curadoria(r):
    c = r.get("curadoria")
    if not c:
        return ""
    if c.get("estado") == "pedida":
        return f"\nCuradoria do Vault-I pedida (#{c.get('pedido')}): as notas aparecem no hub quando terminar."
    return f"\nCuradoria do Vault-I não pedida: {c.get('motivo')}"


def cmd_sync(pos, params, flags):
    if not pos:
        return _sync_projeto(params, flags)
    modo = params.get("modo")
    if (len(pos) != 2 or set(params) - {"modo"} or modo not in (None, *MODOS)
            or flags - {"json", "curate"} or not TAG.fullmatch(pos[0])):
        raise Erro(f"uso: {cli()} sync [--dry-run] [--curate]   (na pasta preparada pelo {cli()} init)\n"
                   f"  ou: {cli()} sync <vault> <arquivo.zip> [modo=literal|documentado] [--curate] [--json]")
    tag, caminho = pos
    with open(caminho, "rb") as f:
        pacote = f.read(LIMITE_PACOTE + 1)
    if len(pacote) > LIMITE_PACOTE or not zipfile.is_zipfile(io.BytesIO(pacote)):
        raise Erro("informe um ZIP válido de até 10 MB")
    r = _enviar(tag, pacote, modo, "curate" in flags)
    saida(r, "json" in flags, f"Snapshot recebido: {r['arquivos']} arquivo(s) · {r['commit'][:12]}. "
                              f"Processamento solicitado.{_texto_curadoria(r)}")


def _sync_projeto(params, flags):
    if set(params) - {"dir"} or flags - {"json", "dry-run", "curate"}:
        raise Erro(f"uso: {cli()} sync [dir=<pasta>] [--dry-run] [--curate] [--json]")
    raiz = os.path.abspath(params.get("dir") or ".")
    vs = _ler_vs(raiz)
    if vs is None:
        raise Erro(f"esta pasta não tem .vs: rode {cli()} init vault=<nome> primeiro")
    tag, modo = vs.get("vault"), vs.get("modo")
    if not isinstance(tag, str) or not TAG.fullmatch(tag) or modo not in MODOS:
        raise Erro(f"o .vs não diz o vault e o modo: rode {cli()} init vault=<nome> modo=literal|documentado")
    hub = url_base()
    if vs.get("hub") and hub and vs["hub"].rstrip("/") != hub:
        raise Erro(f"esta pasta está ligada ao hub {vs['hub']}, e o login atual é de {hub}: "
                   f"rode {cli()} login url={vs['hub']}")
    nomes = _arquivos_do_projeto(raiz)
    if not nomes:
        raise Erro("nada para enviar nesta pasta")
    notas = [n for n in nomes if n.lower().endswith(".md") and _e_nota(os.path.join(raiz, *n.split("/")))]
    if "dry-run" in flags:
        r = {"vault": tag, "modo": modo, "hub": hub, "arquivos": nomes, "notas_do_agente": notas, "dry_run": True}
        saida(r, "json" in flags,
              f"Simulação: {len(nomes)} arquivo(s) para {tag} ({modo}) em {hub or '(sem hub)'}\n"
              + "\n".join(f"  {'*' if n in notas else ' '} {n}" for n in nomes)
              + (f"\n* nota do agente ({len(notas)}): entra curada no modo documentado" if notas else "")
              + "\nNada foi enviado (--dry-run).")
        return 0
    r = _enviar(tag, _empacotar(raiz, nomes), modo, "curate" in flags)
    r.update({"vault": tag, "modo": modo, "notas_do_agente": len(notas)})
    saida(r, "json" in flags,
          f"Enviado para {tag} ({modo}): {r['arquivos']} arquivo(s) · revisão {r['commit'][:12]}"
          + (f" · {len(notas)} nota(s) do agente" if notas and modo == "documentado" else "")
          + f".\nO hub processa em instantes: {hub}/sistemas/{tag}" + _texto_curadoria(r))
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
            vault = params.get("vault") or anterior.get("vault") or _nome_vault(os.path.basename(destino))
            modo_vault = params.get("modo") or anterior.get("modo") or (
                "literal" if vault.startswith("template-") else "documentado")
            conexao = None
            if hub and not simular:
                try:
                    eu = pedir("/v1/eu", token())
                    conexao = {"dono": eu.get("dono"), "credencial": eu.get("credencial"),
                               "workspace": bool(eu.get("workspace"))}
                except Erro as e:
                    print(f"{cli()}: aviso: sem conexão com o hub agora ({e}); o vínculo fica só com o endereço",
                          file=sys.stderr)
            manifesto = {**anterior, "versao": 2, "projeto": os.path.basename(destino), "hub": hub or None,
                         "vault": vault, "modo": modo_vault, "conexao": conexao or anterior.get("conexao")}
            gerenciados = {".vs": json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
                          "VS.lock": "# Prévia do Vault System. A CLI ainda não consome este arquivo.\nversao = 0\n"}
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
        resultado.update({"vault": manifesto["vault"], "modo": manifesto["modo"], "hub": manifesto["hub"]})
    vinculo = (f"\nProjeto ligado ao vault {manifesto['vault']} ({manifesto['modo']})"
               + (f" no hub {manifesto['hub']}" if manifesto["hub"] else " (sem hub: rode vs login)")
               + (f", workspace de {manifesto['conexao']['dono']}" if (manifesto.get("conexao") or {}).get("dono") else "")
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
    passos = ["vs login", "vs init vault=<nome>", "vs sync", "vs add template design:default", "vs help"]
    linhas += [f"    > {p}" for p in passos]
    saida({"versao": VERSAO, "hub": url_base() or None, "sessao": sessao}, "json" in flags, "\n".join(linhas))
    return 0


def cmd_ajuda(pos, params, flags):
    ajuda = __doc__.split("Comandos:\n", 1)[1].strip()
    print(ajuda)


def cmd_repo(pos, params, flags):
    if len(pos) != 2 or pos[0] != "conectar" or params or flags - {"json"}:
        raise Erro("use vs repo conectar ssh://git@servidor/projetos/demo.git")
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


COMANDOS = {"login": cmd_login, "logout": cmd_logout, "whoami": cmd_whoami, "templates": cmd_templates, "add": cmd_add,
            "init": cmd_init,
            "sync": cmd_sync,
            "repo": cmd_repo,
            "update": cmd_update, "welcome": cmd_welcome,
            "versao": cmd_versao, "version": cmd_versao, "ajuda": cmd_ajuda, "help": cmd_ajuda}


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
        argv = ["versao"]
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
