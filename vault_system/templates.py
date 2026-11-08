"""Templates para baixar pela CLI (`vs add template docker:python`).

Um template é uma pasta de um vault cujo nome começa com `template-`:
`docker:python` é a pasta `python/` do vault `template-docker` (um vault por
tipo; o prefixo fica travado no cadastro). O pacote sai do clone bare da
origem, no commit processado, como os arquivos do entra o arquivo que
alguma leitura do vault aceita (os mesmos filtros de caminho da ingestão, então
`.env`, chaves e certificados nunca saem; `.env.example` sai).

Template não carrega segredo: um arquivo de texto em que a máscara da ingestão
acharia algo (token, senha atribuída, chave privada, senha em URL) bloqueia o
template inteiro, com o nome do arquivo no erro. Binário só sai se a extensão
for das permitidas no  (imagem, fonte, PDF).

`template.json` na pasta é opcional e não vai para o projeto: descreve o
template (`descricao`; as variáveis entram depois).
"""
import io
import json
import re
import subprocess
import zipfile

from . import arquivos, filtros, ingestao

PREFIXO = "template-"
TIPO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NOME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
META = "template.json"
LIMITE_ARQUIVO = 1024 * 1024
LIMITE_PACOTE = 10 * 1024 * 1024


class NaoEncontrado(Exception):
    pass


class Bloqueado(Exception):
    pass


def separar(ident):
    """'docker:python' -> ('docker', 'python'), ou ValueError."""
    tipo, _, nome = (ident or "").partition(":")
    if not TIPO.match(tipo) or not NOME.match(nome) or ".." in nome:
        raise ValueError("use tipo:nome, como docker:python")
    return tipo, nome


def _origens(db, tipo=None):
    """(tipo, tag, origem) de cada origem ativa de vault de template, já processada."""
    if tipo is not None:
        filtro, params = "tag = ?", (PREFIXO + tipo,)
    else:
        filtro, params = "tag LIKE ?", (PREFIXO + "%",)
    for o in db.execute(f"SELECT * FROM origens WHERE {filtro} AND removida_em IS NULL "
                        "ORDER BY tag, nome != 'principal', nome", params):
        if o["commit_processado"] and o["tag"].startswith(PREFIXO):
            yield o["tag"][len(PREFIXO):], o["tag"], o


def _arquivos_da_origem(tag, o):
    """{pasta de topo: [(caminho dentro dela, caminho na origem, blob, tamanho, executável)]}."""
    leituras = json.loads(o["leituras"] or "[]")
    pastas = {}
    for caminho, blob, tamanho, modo in _ls_tree(tag, o["nome"], o["commit_processado"]):
        if "/" not in caminho:
            continue  # arquivo solto na raiz (README do repositório) não é template
        pasta, dentro = caminho.split("/", 1)
        if not NOME.match(pasta) or ingestao.leitura_de(caminho, leituras, cru=True)[0] is None:
            continue
        pastas.setdefault(pasta, []).append((dentro, caminho, blob, tamanho, modo == "100755"))
    return pastas


def _ls_tree(tag, origem, commit):
    """(caminho, blob, tamanho, modo) de cada arquivo comum do commit (o modo guarda o executável)."""
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
            yield caminho, blob, int(tamanho), modo


def _ler(tag, o, caminho):
    dados, motivo = arquivos.ler_blob(tag, o["nome"], o["commit_processado"], caminho, limite=LIMITE_ARQUIVO)
    if dados is None:
        raise NaoEncontrado(f"{caminho}: {motivo}")
    return dados


def _meta(tag, o, itens):
    for dentro, caminho, *_ in itens:
        if dentro == META:
            try:
                m = json.loads(_ler(tag, o, caminho).decode("utf-8"))
                return m if isinstance(m, dict) else {}
            except (ValueError, UnicodeDecodeError, NaoEncontrado):
                return {}
    return {}


def _preparar(tag, o, itens):
    """(saem, bloqueios): saem = [(caminho no template, bytes, executável)]; bloqueios = ['arquivo: motivo']."""
    saem, bloqueios = [], []
    for dentro, caminho, _, tamanho, executavel in sorted(itens):
        if dentro == META:
            continue
        if tamanho > LIMITE_ARQUIVO:
            bloqueios.append(f"{dentro}: passa de {LIMITE_ARQUIVO // 1024} KB")
            continue
        dados = _ler(tag, o, caminho)
        motivo = _conferir(caminho, dados)
        if motivo == "pular":
            continue
        if motivo:
            bloqueios.append(f"{dentro}: {motivo}")
        else:
            saem.append((dentro, dados, executavel))
    return saem, bloqueios


def _resumo(tipo, tag, o, nome, itens):
    meta = _meta(tag, o, itens)
    saem, bloqueios = _preparar(tag, o, itens)
    return {"id": f"{tipo}:{nome}", "tipo": tipo, "nome": nome, "vault": tag,
            "descricao": str(meta.get("descricao") or ""), "arquivos": len(saem),
            "commit": o["commit_processado"],
            "bloqueado": ("não pode carregar segredo: " + "; ".join(bloqueios)) if bloqueios else None}


def listar(db, tipo=None):
    """Os templates: [{id, tipo, nome, vault, descricao, arquivos, commit}], por id."""
    vistos, saida = set(), []
    for t, tag, o in _origens(db, tipo):
        for nome, itens in _arquivos_da_origem(tag, o).items():
            if (t, nome) not in vistos:  # a mesma pasta em outra origem: vale a primeira (principal)
                vistos.add((t, nome))
                saida.append(_resumo(t, tag, o, nome, itens))
    return sorted(saida, key=lambda x: x["id"])


def _achar(db, tipo, nome):
    for t, tag, o in _origens(db, tipo):
        itens = _arquivos_da_origem(tag, o).get(nome)
        if itens:
            return t, tag, o, itens
    raise NaoEncontrado(f"template {tipo}:{nome} não existe (veja vs templates {tipo})")


def _conferir(caminho, dados):
    """None se o arquivo pode sair; 'pular' para binário fora da lista; ou o motivo do bloqueio."""
    if b"\0" in dados[:8192]:
        return None if arquivos.tipo(caminho) else "pular"
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return None if arquivos.tipo(caminho) else "pular"
    if filtros.CHAVE_PRIVADA.search(texto):
        return "chave privada no conteúdo"
    if filtros.mascarar(texto)[1]:
        return "valor com cara de segredo (token, senha ou senha em URL)"
    return None


def detalhes(db, tipo, nome):
    """O template com a lista de arquivos que saem: {..., files: [{path, size, executable}], template_json}."""
    t, tag, o, itens = _achar(db, tipo, nome)
    r = _resumo(t, tag, o, nome, itens)
    saem, _ = _preparar(tag, o, itens)
    r["files"] = [{"path": d, "size": len(b), "executable": x} for d, b, x in saem]
    r["template_json"] = _meta(tag, o, itens)
    return r


def pacote(db, tipo, nome):
    """(resumo, bytes do zip) com os arquivos relativos à pasta do template.
    NaoEncontrado se não existe; Bloqueado se algum arquivo tem segredo ou é grande demais."""
    t, tag, o, itens = _achar(db, tipo, nome)
    saem, bloqueios = _preparar(tag, o, itens)
    if bloqueios:
        raise Bloqueado(f"template {tipo}:{nome} bloqueado, não pode carregar segredo: " + "; ".join(bloqueios))
    if not saem:
        raise NaoEncontrado(f"template {tipo}:{nome} não tem arquivos para baixar")
    if sum(len(b) for _, b, _ in saem) > LIMITE_PACOTE:
        raise Bloqueado(f"o template passa de {LIMITE_PACOTE // 1024 // 1024} MB")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for dentro, dados, executavel in saem:
            info = zipfile.ZipInfo(dentro, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if executavel else 0o100644) << 16
            z.writestr(info, dados)
    return _resumo(t, tag, o, nome, itens), buf.getvalue()
