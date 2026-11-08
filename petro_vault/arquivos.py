"""Arquivos binários dos vaults de Referência (DV-601): fontes, imagens e PDF
para baixar pela API, pelo MCP e pela tela.

Binário não vira nota (não passa pelo filtro de segredo nem pelo curador). A
lista sai do clone bare de cada origem, no commit processado: entra o arquivo
de uma leitura de Referência (`referencia` ou `referencia-explicada`) que passa
nos filtros de caminho da ingestão, tem extensão de PERMITIDOS e até LIMITE
bytes. A lista fechada de extensões é a proteção: nada de .zip, .exe, .env ou
chave sai por aqui. Os bytes vêm do clone no momento do download.

Link assinado (MCP): HMAC-SHA256 de tag, origem, caminho e validade, com a
chave de VAULT_CHAVE_LINKS ou, sem ela, de estado/links.chave (criada na
primeira vez). Vale VALIDADE segundos e não pede credencial, para o agente
baixar com `curl -o`.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import posixpath
import re
import secrets
import subprocess
import time
import zipfile

from . import estado, ingestao, literal

PERMITIDOS = {
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".pdf": "application/pdf",
}
LIMITE = 5 * 1024 * 1024
LIMITE_PACOTE = 40 * 1024 * 1024
VALIDADE = 15 * 60
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")


class NaoEncontrado(Exception):
    pass


def tipo(caminho):
    return PERMITIDOS.get(posixpath.splitext(caminho)[1].lower())


def ler_blob(tag, origem, commit, caminho, limite=LIMITE):
    """Bytes do arquivo no clone da origem, no commit: (bytes, None) ou (None, motivo)."""
    if not commit or not _COMMIT.match(commit):
        return None, "sem commit da origem"
    clone, alvo = ingestao.dir_clone(tag, origem), f"{commit}:{caminho}"
    try:
        r = subprocess.run(["git", "--git-dir", clone, "cat-file", "-s", alvo], capture_output=True, timeout=10)
        if r.returncode != 0:
            return None, f"não está no commit {commit[:7]}"
        tamanho = int(r.stdout)
        if limite is not None and tamanho > limite:
            return None, f"tem {tamanho // 1024} KB (limite {limite // 1024 // 1024} MB)"
        r = subprocess.run(["git", "--git-dir", clone, "cat-file", "blob", alvo], capture_output=True, timeout=30)
    except FileNotFoundError:
        return None, "git indisponível na API"
    except (subprocess.TimeoutExpired, ValueError):
        return None, "não consegui ler do clone"
    if r.returncode != 0:
        return None, "não consegui ler do clone"
    return r.stdout, None


def _ls_tree(tag, origem, commit):
    """(caminho, blob, tamanho) de cada arquivo comum do commit."""
    clone = ingestao.dir_clone(tag, origem)
    try:
        r = subprocess.run(["git", "--git-dir", clone, "ls-tree", "-r", "-l", "-z", "--full-tree", commit],
                           capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if r.returncode != 0:
        return
    for linha in r.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if not linha:
            continue
        meta, caminho = linha.split("\t", 1)
        modo, tipo_obj, blob, tamanho = meta.split()
        if tipo_obj == "blob" and modo in ("100644", "100755") and tamanho.isdigit():
            yield caminho, blob, int(tamanho)


def listar(db, tag, pasta=None):
    """Os arquivos para baixar do vault: [{origem, caminho, tipo, tamanho, commit, blob}], por origem e caminho."""
    saida = []
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome", (tag,)):
        commit, leituras = o["commit_processado"], json.loads(o["leituras"] or "[]")
        if not commit or not any(l.get("perfil") in literal.PERFIS_COPIADOS for l in leituras):
            continue
        for caminho, blob, tamanho in _ls_tree(tag, o["nome"], commit):
            t = tipo(caminho)
            if not t or tamanho > LIMITE or (pasta and not (caminho + "/").startswith(pasta.strip("/") + "/")):
                continue
            perfil, _ = ingestao.leitura_de(caminho, leituras)
            if perfil in literal.PERFIS_COPIADOS:
                saida.append({"origem": o["nome"], "caminho": caminho, "tipo": t, "tamanho": tamanho,
                              "commit": commit, "blob": blob})
    return saida


def achar(db, tag, origem, caminho):
    """O item da lista (só o que está nela sai), ou NaoEncontrado."""
    for a in listar(db, tag):
        if a["origem"] == origem and a["caminho"] == caminho:
            return a
    raise NaoEncontrado(f"{estado.ref(origem, caminho)}: não é um arquivo para baixar deste vault")


def ler(db, tag, origem, caminho):
    """(item, bytes) de um arquivo da lista, ou NaoEncontrado."""
    a = achar(db, tag, origem, caminho)
    dados, motivo = ler_blob(tag, origem, a["commit"], caminho)
    if dados is None:
        raise NaoEncontrado(f"{caminho}: {motivo}")
    return a, dados


def pacote(db, tag, pasta=None):
    """Zip dos arquivos (com a pasta da origem; outra origem fica em <origem>/), ou NaoEncontrado."""
    itens = listar(db, tag, pasta)
    if not itens:
        raise NaoEncontrado("nenhum arquivo para baixar" + (f" em {pasta}" if pasta else ""))
    if sum(a["tamanho"] for a in itens) > LIMITE_PACOTE:
        raise NaoEncontrado(f"o pacote passa de {LIMITE_PACOTE // 1024 // 1024} MB: escolha uma pasta")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in itens:
            dados, motivo = ler_blob(tag, a["origem"], a["commit"], a["caminho"])
            if dados is None:
                raise NaoEncontrado(f"{a['caminho']}: {motivo}")
            z.writestr(a["caminho"] if a["origem"] == "principal" else f"{a['origem']}/{a['caminho']}", dados)
    return buf.getvalue()


# --- link assinado ------------------------------------------------------------------

def _chave():
    env = os.environ.get("VAULT_CHAVE_LINKS")
    if env:
        return env.encode()
    caminho = os.path.join(estado.dir_estado(), "links.chave")
    try:
        with open(caminho, "rb") as f:
            return f.read()
    except FileNotFoundError:
        chave = secrets.token_bytes(32)
        try:
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # outro processo criou antes
            with open(caminho, "rb") as f:
                return f.read()
        with os.fdopen(fd, "wb") as f:
            f.write(chave)
        return chave


def _mac(tag, origem, caminho, expira):
    msg = "\n".join((tag, origem, caminho, str(expira))).encode()
    return base64.urlsafe_b64encode(hmac.new(_chave(), msg, hashlib.sha256).digest()).decode().rstrip("=")


def assinar(tag, origem, caminho, agora=None):
    """(expira, assinatura) para o link de download."""
    expira = int(agora if agora is not None else time.time()) + VALIDADE
    return expira, _mac(tag, origem, caminho, expira)


def conferir(tag, origem, caminho, expira, assinatura, agora=None):
    """None se o link vale, ou o motivo."""
    try:
        expira = int(expira)
    except (TypeError, ValueError):
        return "link inválido"
    if expira < int(agora if agora is not None else time.time()):
        return "link vencido: peça outro (get_file)"
    if expira > int(agora if agora is not None else time.time()) + VALIDADE:
        return "link inválido"
    if not hmac.compare_digest(_mac(tag, origem, caminho, expira), assinatura or ""):
        return "link inválido"
    return None
