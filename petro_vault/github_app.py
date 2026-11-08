"""GitHub App do PetroVault (DV-573): leitura das origens sem chave de deploy.

Um admin da organização instala o App `petro-vault` uma vez, nos repositórios
escolhidos; depois disso, qualquer pessoa adiciona uma origem pela tela
escolhendo o repositório numa lista. Origem com repo `https://github.com/<dono>/<repo>`
é lida pelo App; `git@...` continua com a chave de deploy.

Só o curador tem a chave privada (/opt/curador/github-app.pem, copiada pelo
vault-init). Para cada fetch: JWT assinado com a chave (10 min) → token da
instalação (1 h) → `git fetch` por HTTPS com o token num cabeçalho passado
por variável de ambiente. O token não vai para a URL, o config do clone, o
log, o banco ou o prompt.

A lista de repositórios e ramos para a tela fica em `github_repos` (a API não
vê a chave): o curador atualiza quando a tela pede ou a cada LISTA_MAX_IDADE.
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from . import estado

API = "https://api.github.com"
APP_ID = os.environ.get("VAULT_GITHUB_APP_ID", "")
CHAVE = os.environ.get("VAULT_GITHUB_APP_CHAVE", "/opt/curador/github-app.pem")
REPO = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
LISTA_MAX_IDADE = 600  # s

_tokens = {}  # instalação -> (token, expira em); vale para um processo (uma rodada)


class ErroGitHub(Exception):
    pass


def do_app(repo):
    """(dono, repo) se a origem é lida pelo App, senão None."""
    m = REPO.match(repo or "")
    return (m.group(1), m.group(2)) if m else None


def configurado():
    return bool(APP_ID) and os.path.isfile(CHAVE) and os.path.getsize(CHAVE) > 0


def _b64(dados):
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _assinar(mensagem):
    """RS256 com a chave do App: `cryptography` se houver, senão o openssl."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        r = subprocess.run(["openssl", "dgst", "-sha256", "-sign", CHAVE], input=mensagem, capture_output=True)
        if r.returncode != 0:
            raise ErroGitHub("não consegui assinar com a chave do GitHub App (openssl)")
        return r.stdout
    with open(CHAVE, "rb") as f:
        chave = serialization.load_pem_private_key(f.read(), password=None)
    return chave.sign(mensagem, padding.PKCS1v15(), hashes.SHA256())


def _jwt():
    if not configurado():
        raise ErroGitHub("GitHub App não configurado no servidor (VAULT_GITHUB_APP_ID e a chave privada)")
    agora = int(time.time())
    cabeca = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    corpo = _b64(json.dumps({"iat": agora - 60, "exp": agora + 540, "iss": APP_ID}).encode())
    return f"{cabeca}.{corpo}.{_b64(_assinar(f'{cabeca}.{corpo}'.encode()))}"


def _pedir(caminho, credencial, metodo="GET"):
    """(status, json). Erros que não dependem do caminho viram ErroGitHub com
    a causa separada: credencial recusada, limite do GitHub, indisponível."""
    req = urllib.request.Request(API + caminho, method=metodo, headers={
        "Authorization": f"Bearer {credencial}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "petro-vault"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ErroGitHub("o GitHub recusou a credencial do App (App ID ou chave privada errados)") from None
        if e.code == 429 or (e.code == 403 and e.headers.get("x-ratelimit-remaining") == "0"):
            raise ErroGitHub("limite de requisições do GitHub atingido; tenta de novo na próxima rodada") from None
        if e.code >= 500:
            raise ErroGitHub(f"GitHub indisponível (HTTP {e.code})") from None
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroGitHub(f"GitHub indisponível ({getattr(e, 'reason', e)})") from None


def _token_da_instalacao(instalacao):
    token, expira = _tokens.get(instalacao, (None, 0))
    if token and expira - time.time() > 300:
        return token
    status, r = _pedir(f"/app/installations/{instalacao}/access_tokens", _jwt(), "POST")
    if status != 201:
        raise ErroGitHub(f"o GitHub não deu o token da instalação (HTTP {status})")
    _tokens[instalacao] = (r["token"], time.time() + 3600)
    return r["token"]


def token(dono, repo):
    """Token de instalação que lê dono/repo (também para a árvore, DV-589)."""
    status, r = _pedir(f"/repos/{dono}/{repo}/installation", _jwt())
    if status == 404:
        raise ErroGitHub(f"o GitHub App não está instalado em {dono}/{repo}: o admin da organização "
                         "inclui o repositório na instalação do App")
    if status != 200:
        raise ErroGitHub(f"o GitHub não respondeu sobre a instalação em {dono}/{repo} (HTTP {status})")
    return _token_da_instalacao(r["id"])


def ambiente_git(dono, repo):
    """Variáveis de ambiente para o git ler dono/repo por HTTPS com o token."""
    basico = base64.b64encode(f"x-access-token:{token(dono, repo)}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basico}", "GIT_TERMINAL_PROMPT": "0"}


def arvore(dono, repo, ramo):
    """(commit, itens, truncado) do ramo, numa chamada (git/trees recursivo).
    itens: [{path, type, size}]. Repositório enorme vem truncado pelo GitHub."""
    tok = token(dono, repo)
    status, r = _pedir(f"/repos/{dono}/{repo}/branches/{urllib.parse.quote(ramo, safe='')}", tok)
    if status == 404:
        raise ErroGitHub(f"o ramo {ramo} não existe em {dono}/{repo}")
    if status != 200:
        raise ErroGitHub(f"o GitHub não respondeu sobre o ramo {ramo} (HTTP {status})")
    commit = r["commit"]["sha"]
    status, t = _pedir(f"/repos/{dono}/{repo}/git/trees/{commit}?recursive=1", tok)
    if status != 200:
        raise ErroGitHub(f"o GitHub não deu a árvore de {dono}/{repo} (HTTP {status})")
    return commit, t["tree"], bool(t.get("truncated"))


def _paginas(caminho, credencial, campo=None):
    itens, pagina = [], 1
    while True:
        sep = "&" if "?" in caminho else "?"
        status, r = _pedir(f"{caminho}{sep}per_page=100&page={pagina}", credencial)
        if status != 200:
            raise ErroGitHub(f"o GitHub não listou {caminho} (HTTP {status})")
        lote = r[campo] if campo else r
        itens += lote
        if len(lote) < 100:
            return itens
        pagina += 1


def listar():
    """Repositórios onde o App está instalado, com os ramos:
    [{nome, ramo_padrao, privado, ramos}]."""
    repos = []
    for inst in _paginas("/app/installations", _jwt()):
        tok = _token_da_instalacao(inst["id"])
        for r in _paginas("/installation/repositories", tok, "repositories"):
            ramos = [b["name"] for b in _paginas(f"/repos/{r['full_name']}/branches", tok)]
            repos.append({"nome": r["full_name"], "ramo_padrao": r["default_branch"],
                          "privado": bool(r["private"]), "ramos": ramos})
    return sorted(repos, key=lambda r: r["nome"].lower())


def atualizar_lista(db):
    """Atualiza `github_repos` se a tela pediu ou se a lista passou de
    LISTA_MAX_IDADE. Sem App configurado: só registra isso."""
    atual = {l["chave"]: json.loads(l["valor"]) for l in
             db.execute("SELECT chave, valor FROM curador_estado WHERE chave = 'github' AND valor IS NOT NULL")}
    g = atual.get("github") or {}
    idade = time.time() - g.get("em_ts", 0)
    if not g.get("pedido_em") and idade < LISTA_MAX_IDADE:
        return
    novo = {"em": estado.agora(), "em_ts": time.time(), "erro": None, "pedido_em": None}
    try:
        repos = listar()
        with db:
            db.execute("DELETE FROM github_repos")
            db.executemany("INSERT INTO github_repos (nome, ramo_padrao, privado, ramos) VALUES (?, ?, ?, ?)",
                           [(r["nome"], r["ramo_padrao"], int(r["privado"]), json.dumps(r["ramos"])) for r in repos])
        print(f"[github] {len(repos)} repositório(s) com o App instalado")
    except ErroGitHub as e:
        novo["erro"] = str(e)
        print(f"[github] lista não atualizada: {e}")
    with db:
        # A tela pode ter pedido de novo enquanto a lista era montada: o pedido fica.
        g2 = json.loads((db.execute("SELECT valor FROM curador_estado WHERE chave = 'github'").fetchone() or {"valor": "{}"})["valor"] or "{}")
        if g2.get("pedido_em") and g2.get("pedido_em") != g.get("pedido_em"):
            novo["pedido_em"] = g2["pedido_em"]
        db.execute("INSERT INTO curador_estado (chave, valor) VALUES ('github', ?) "
                   "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (json.dumps(novo, ensure_ascii=False),))
