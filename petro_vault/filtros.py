"""Filtros da ingestão (DV-290): o que entra na fila e o que fica de fora.

Tudo em código, antes da fila: o curador (e o LLM) só recebe o que passou
daqui. Dois tipos de filtro:

- por caminho (`por_caminho`): padrões do cadastro, pastas de dependências,
  lockfiles e arquivos de segredo (`.env`, chaves, certificados). Valem também
  para arquivos removidos.
- por conteúdo (`por_conteudo`): binário, tamanho e chave privada no texto.
  Linhas com cara de token não tiram o arquivo: o valor é mascarado
  (`mascarar`).
"""
import fnmatch
import os
import re

LIMITE_BYTES = int(os.environ.get("VAULT_LIMITE_BYTES", 256 * 1024))
MASCARA = "«segredo-removido»"  # sem espaço: a máscara não casa de novo com ATRIBUICAO

PASTAS_FORA = {".git", ".github", "node_modules", "vendor", "bower_components", ".venv", "venv", "__pycache__"}
LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "poetry.lock", "Pipfile.lock", "uv.lock", "composer.lock", "Gemfile.lock", "Cargo.lock",
    "go.sum", "packages.lock.json", "mix.lock", "pubspec.lock",
}
ESTRUTURA_GIT = {".gitkeep", ".gitignore", ".gitattributes", ".gitmodules", ".keep"}
# Arquivos de segredo pelo nome. `.env.example` e afins entram (documentam as
# variáveis), mas passam pela máscara como qualquer outro.
ENV_EXEMPLO = {".env.example", ".env.sample", ".env.template", ".env.dist"}
NOMES_SEGREDO = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".pgpass", ".htpasswd",
    ".npmrc", ".pypirc", "credentials", "credentials.json", "secrets.json", "secrets.yaml",
    "secrets.yml", "terraform.tfstate", "terraform.tfstate.backup",
}
EXTENSOES_SEGREDO = {
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".crt", ".cer", ".der", ".p8",
    ".ppk", ".asc", ".gpg", ".kdbx", ".tfvars",
}

CHAVE_PRIVADA = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----")
# Valores com formato de token conhecido: some o valor inteiro.
TOKENS = [re.compile(p) for p in (
    r"AKIA[0-9A-Z]{16}",                                   # AWS
    r"gh[pousr]_[A-Za-z0-9]{36,}",                          # GitHub
    r"github_pat_[A-Za-z0-9_]{22,}",
    r"glpat-[A-Za-z0-9_-]{20,}",                            # GitLab
    r"xox[abposr]-[A-Za-z0-9-]{10,}",                       # Slack
    r"sk-ant-[A-Za-z0-9_-]{20,}",                           # Anthropic
    r"sk-[A-Za-z0-9_-]{20,}",                               # OpenAI e afins
    r"AIza[0-9A-Za-z_-]{35}",                               # Google
    r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",  # JWT
    r"pv_[A-Za-z0-9_-]{30,}",                               # credencial deste serviço
)]
# Atribuição a um nome com cara de segredo: some só o valor. Valor que é
# código (chamada, atributo, índice: `token = os.environ.get(...)`) ou
# referência (`$VAR`, `<valor>`) não é mascarado. Nem pseudo-classe de CSS
# (`.password-toggle:focus-visible{`): no vault de Referência (DV-600) o CSS
# vai como está, e a máscara estragava o código. Nem nome que termina em ponto
# (fim de frase num texto: `'Informe sua senha.':cond?...` num JavaScript).
PSEUDO_CSS = (r"(?:focus|hover|active|visited|checked|disabled|enabled|placeholder|not|is|where|has|first|last|"
              r"nth|only|before|after|invalid|valid|required|optional|read-only|read-write|empty|target|root|"
              r"autofill|-webkit-|-moz-)")
ATRIBUICAO = re.compile(
    r"""(?ix)
    (\b[\w.-]*(?:password|passwd|pwd|senha|secret|segredo|token|api[_-]?key|apikey|
       access[_-]?key|private[_-]?key|client[_-]?secret)[\w.-]*
     (?<!\.)["']?\s*[:=]\s*["']?)
    (?![$<%])(?!(?-i::?""" + PSEUDO_CSS + r"""[a-z-]*[\s,{:(.\[>+~)]))([^\s"',;()\[\]{}]{8,})(?![\w(\[]|\.\w)
    """)
# Senha dentro de URL: esquema://usuario:senha@host
URL_COM_SENHA = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s/:@]+:)([^\s/@]+)(@)", re.I)


def casa(caminho, padroes):
    """Padrão estilo glob sobre o caminho inteiro (`*` atravessa pastas) ou só
    sobre o nome do arquivo, quando o padrão não tem barra."""
    nome = caminho.rsplit("/", 1)[-1]
    for p in padroes:
        alvo = caminho if "/" in p else nome
        if fnmatch.fnmatchcase(alvo, p) or fnmatch.fnmatchcase(caminho, p):
            return True
    return False


def por_caminho(caminho, incluir=(), excluir=()):
    """Motivo para deixar o caminho de fora, ou None se ele passa."""
    partes = caminho.split("/")
    nome = partes[-1]
    if incluir and not casa(caminho, incluir):
        return "fora dos padrões de inclusão"
    if excluir and casa(caminho, excluir):
        return "padrão de exclusão do cadastro"
    if PASTAS_FORA.intersection(partes[:-1]):
        return "pasta de dependências"
    if nome in LOCKFILES:
        return "lockfile"
    if nome in ESTRUTURA_GIT:
        return "arquivo de estrutura do git"
    if nome == ".env" or (nome.startswith(".env.") and nome not in ENV_EXEMPLO) or nome.endswith(".env"):
        return "segredo (.env)"
    if nome in NOMES_SEGREDO or os.path.splitext(nome)[1].lower() in EXTENSOES_SEGREDO:
        return "segredo (chave ou certificado)"
    return None


def por_conteudo(dados):
    """(texto, None) se o conteúdo passa, ou (None, motivo)."""
    if len(dados) > LIMITE_BYTES:
        return None, f"acima de {LIMITE_BYTES} bytes"
    if b"\0" in dados[:8192]:
        return None, "binário"
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return None, "binário (não é UTF-8)"
    if CHAVE_PRIVADA.search(texto):
        return None, "segredo (chave privada no conteúdo)"
    if not texto.strip():
        return None, "vazio"
    return texto, None


def mascarar(texto):
    """Troca valores com cara de segredo por MASCARA. Devolve (texto, quantos)."""
    total = 0
    for padrao in TOKENS:
        texto, n = padrao.subn(MASCARA, texto)
        total += n
    trocas = 0

    def _valor(m):
        nonlocal trocas
        if m.group(2) == MASCARA:  # já mascarado por um token conhecido
            return m.group(0)
        trocas += 1
        return m.group(1) + MASCARA

    texto = ATRIBUICAO.sub(_valor, texto)

    def _url(m):
        nonlocal trocas
        if m.group(2) == MASCARA:  # senha de URL já mascarada não conta de novo (DV-604)
            return m.group(0)
        trocas += 1
        return m.group(1) + MASCARA + m.group(3)

    texto = URL_COM_SENHA.sub(_url, texto)
    return texto, total + trocas
