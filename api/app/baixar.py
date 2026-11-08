"""Download dos arquivos binários dos vaults de Referência: o que é
comum às rotas da API (credencial `vs_` ou link assinado), do painel e do MCP.
A regra de quais arquivos saem está em vault_system/arquivos.py."""
import os
import posixpath
from urllib.parse import quote, urlencode

from fastapi import HTTPException, Response

from vault_system import arquivos

# O arquivo vem de um repositório de origem: nunca roda na origem da tela (SVG com script, PDF).
CABECALHOS = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox",
              "Cache-Control": "private, max-age=300"}


def url_publica():
    return os.environ.get("VAULT_URL_PUBLICA", "http://127.0.0.1:8670").rstrip("/")


def caminho_url(tag, origem, caminho, **extra):
    q = ({} if origem == "principal" else {"origem": origem}) | extra
    return f"/v1/arquivos/{tag}/{quote(caminho)}" + (f"?{urlencode(q)}" if q else "")


def publico(tag, a):
    """O item da lista como sai na API e no MCP."""
    return {"path": a["caminho"], "origin": a["origem"], "type": a["tipo"], "size": a["tamanho"],
            "commit": a["commit"], "download_url": url_publica() + caminho_url(tag, a["origem"], a["caminho"])}


def link_assinado(tag, a):
    expira, assinatura = arquivos.assinar(tag, a["origem"], a["caminho"])
    return expira, url_publica() + caminho_url(tag, a["origem"], a["caminho"], exp=expira, sig=assinatura)


def _disposicao(nome):
    seguro = "".join(c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in nome)
    return f"attachment; filename=\"{seguro}\"; filename*=UTF-8''{quote(nome)}"


def arquivo(db, tag, origem, caminho):
    try:
        a, dados = arquivos.ler(db, tag, origem, caminho)
    except arquivos.NaoEncontrado as e:
        raise HTTPException(404, str(e)) from None
    return Response(dados, media_type=a["tipo"], headers={
        **CABECALHOS, "Content-Disposition": _disposicao(posixpath.basename(caminho)), "X-Commit": a["commit"]})


def pacote(db, tag, pasta):
    try:
        dados = arquivos.pacote(db, tag, pasta)
    except arquivos.NaoEncontrado as e:
        raise HTTPException(404, str(e)) from None
    nome = f"{tag}-{pasta.strip('/').replace('/', '-')}.zip" if pasta else f"{tag}-arquivos.zip"
    return Response(dados, media_type="application/zip",
                    headers={**CABECALHOS, "Content-Disposition": _disposicao(nome)})
