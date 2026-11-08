#!/usr/bin/env python3
"""pv: a linha de comando do PetroVault (DV-607).

Um arquivo só, com a biblioteca padrão do Python (3.8 ou mais novo). Instalar:

    curl -fsSL http://10.2.2.31:8670/v1/cli/pv -o ~/.local/bin/pv
    chmod +x ~/.local/bin/pv

Comandos:

    pv login [url=<endereço>]          guarda o token pv_ (pergunta sem eco)
    pv logout                          apaga o token guardado
    pv templates [tipo]                lista os templates (de um tipo ou todos)
    pv init [nome]                     aplica o template init:padrao ou init:<nome>
    pv sync <vault> <arquivo.zip>       envia um snapshot para o vault
        modo=literal|documentado      cria o vault ao enviar o primeiro snapshot
    pv add template <tipo:nome>        baixa o template na pasta atual
        dir=<pasta>                    noutra pasta
        --dry-run                      só mostra o que faria
        --force                        sobrescreve o que já existe
    pv repo conectar <url-ssh>         inicializa o Git e configura o remoto vault
    pv versao                          esta versão e a do servidor
    pv ajuda                           este texto

Todo comando aceita --json (saída para script e agente). PV_TOKEN e PV_URL no
ambiente têm prioridade sobre ~/.config/petrovault/config.json.
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

VERSAO = "0.1.0"
URL_PADRAO = "http://10.2.2.31:8670"
REGISTRO = os.path.join(".petrovault", "templates.json")
INIT_PADRAO = """# AGENTS.md

## Protocolo Vault System (seção gerenciada)

Recomendação: mantenha esta seção para que o hub reconheça o padrão de documentação.
Registre decisões e comportamento em Markdown em `docs/`, com um assunto por nota.
Indique os caminhos de origem e, quando disponível, o commit correspondente.
Nunca inclua credenciais. Use a seção abaixo para regras próprias do projeto.

## Este projeto
"""


class Erro(Exception):
    pass


# --- configuração -------------------------------------------------------------------

def arquivo_config():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "vaultsystem" if os.environ.get("VS_CLI") else "petrovault", "config.json")


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
    return (os.environ.get("PV_URL") or c.get("url") or URL_PADRAO).rstrip("/")


def token(config=None):
    c = ler_config() if config is None else config
    chave = "VS_TOKEN" if os.environ.get("VS_CLI") else "PV_TOKEN"
    t = os.environ.get(chave) or c.get("token")
    if not t:
        raise Erro(f"sem token: rode {'vs' if chave == 'VS_TOKEN' else 'pv'} login (ou defina {chave})")
    return t


# --- HTTP ---------------------------------------------------------------------------

def pedir(caminho, chave=None, url=None, bruto=False, pacote=None):
    """GET na API: o JSON (ou, com bruto, (bytes, cabeçalhos))."""
    base = url or url_base()
    if not base:
        raise Erro("configure o servidor com vs login url=<endereço> ou VS_URL")
    req = urllib.request.Request(base + caminho,
                                 headers={"User-Agent": f"pv/{VERSAO}", "Accept": "*/*"})
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
            raise Erro("token inválido ou revogado: rode pv login") from None
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
    chave = os.environ.get("VS_TOKEN" if os.environ.get("VS_CLI") else "PV_TOKEN") or getpass.getpass("Token (não aparece ao digitar): ").strip()
    if not chave:
        raise Erro("nenhum token informado")
    pedir("/v1/templates", chave, url)  # 401 aqui vira "token inválido"
    c.update({"url": url, "token": chave})
    gravar_config(c)
    saida({"ok": True, "url": url, "config": arquivo_config()}, "json" in flags,
          f"Token guardado em {arquivo_config()} (só você lê). Servidor: {url}")


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
        raise Erro("uso: pv add template <tipo:nome> [dir=<pasta>] [--dry-run] [--force]")
    return _aplicar_template(pos[1], params, flags)


def cmd_init(pos, params, flags):
    if len(pos) > 1 or set(params) - {"dir"} or flags - {"dry-run", "force", "json"}:
        raise Erro("uso: vs init [nome] [dir=<pasta>] [--dry-run] [--force] [--json]")
    return _aplicar_template("init:" + (pos[0] if pos else "padrao"), params, flags, iniciar=True)


def cmd_sync(pos, params, flags):
    modo = params.get("modo")
    if (len(pos) != 2 or set(params) - {"modo"} or modo not in (None, "literal", "documentado")
            or flags - {"json"} or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", pos[0])):
        raise Erro("uso: vs sync <vault> <arquivo.zip> [modo=literal|documentado] [--json]")
    tag, caminho = pos
    limite = 10 * 1024 * 1024
    with open(caminho, "rb") as f:
        pacote = f.read(limite + 1)
    if len(pacote) > limite or not zipfile.is_zipfile(io.BytesIO(pacote)):
        raise Erro("informe um ZIP válido de até 10 MB")
    query = f"?modo={modo}" if modo else ""
    r = pedir(f"/v1/sistemas/{tag}/envio{query}", token(), pacote=pacote)
    saida(r, "json" in flags, f"Snapshot recebido: {r['arquivos']} arquivo(s) · {r['commit'][:12]}. Processamento solicitado.")


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
            manifesto = {"versao": 1, "projeto": os.path.basename(destino), "hub": hub or None}
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
            for rel in gerenciados:
                _alvo(destino, rel)
        plano, conflitos = [], []
        for info, rel in itens:
            raiz = rel.split("/")[0].casefold()
            reservados = {".git", ".vaultsystem", ".petrovault"}
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
            plano.append({"path": rel, "acao": ("acrescenta" if rel == ".gitignore" else "mantido") if existe else "novo"})
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
                else:
                    try:
                        with open(alvo, "x", encoding="utf-8") as f:
                            f.write(conteudo)
                    except FileExistsError:
                        pass

    marca = {"novo": "+", "sobrescreve": "~", "igual": "=", "mantido": "=", "acrescenta": "+"}
    texto = (f"{'Simulação: ' if simular else ''}{ident} @ {commit[:7]} -> {destino}\n"
             + "\n".join(f"  {marca[p['acao']]} {p['path']}" for p in plano)
             + ("\nNada foi escrito (--dry-run)." if simular
                else f"\n{len(plano)} arquivo(s). Registro em {_registro()}."
                     + ("\nProjeto inicializado. O vínculo com o hub fica em .vs." if iniciar else "")))
    saida(resultado, "json" in flags, texto)
    return 0


def cmd_versao(pos, params, flags):
    try:
        servidor = pedir("/v1/cli").get("versao")
    except Erro:
        servidor = None
    info = {"versao": VERSAO, "servidor": servidor, "url": url_base()}
    texto = f"pv {VERSAO}"
    if servidor and servidor != VERSAO:
        texto += (f"\nO servidor tem a versão {servidor}. Atualize:\n"
                  f"  curl -fsSL {url_base()}/v1/cli/pv -o {os.path.abspath(sys.argv[0])}")
    saida(info, "json" in flags, texto)


def cmd_ajuda(pos, params, flags):
    ajuda = __doc__.split("Comandos:\n", 1)[1].strip() if os.environ.get("VS_CLI") else __doc__.split("\n\n", 1)[1].strip()
    if os.environ.get("VS_CLI"):
        ajuda = ajuda.replace("pv ", "vs ").replace("PV_TOKEN e PV_URL", "VS_TOKEN e VS_URL").replace("/petrovault/", "/vaultsystem/")
    print(ajuda)


def cmd_repo(pos, params, flags):
    if len(pos) != 2 or pos[0] != "conectar" or params or flags - {"json"}:
        raise Erro("use pv repo conectar ssh://git@servidor/projetos/demo.git")
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


COMANDOS = {"login": cmd_login, "logout": cmd_logout, "templates": cmd_templates, "add": cmd_add,
            "init": cmd_init,
            "sync": cmd_sync,
            "repo": cmd_repo,
            "versao": cmd_versao, "version": cmd_versao, "ajuda": cmd_ajuda, "help": cmd_ajuda}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        cmd_ajuda([], {}, set())
        return 0
    if argv[0] == "--version":
        argv = ["versao"]
    comando = COMANDOS.get(argv[0])
    if not comando:
        print(f"pv: comando desconhecido: {argv[0]} (veja pv ajuda)", file=sys.stderr)
        return 2
    pos, params, flags = separar_args(argv[1:])
    try:
        return comando(pos, params, flags) or 0
    except Erro as e:
        print(f"pv: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"pv: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
