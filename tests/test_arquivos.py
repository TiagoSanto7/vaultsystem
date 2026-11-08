"""Arquivos binários dos vaults de Referência para baixar (DV-601): API, link assinado, MCP e painel."""
import io
import json
import os
import subprocess
import zipfile

from test_painel import entrar, tela  # noqa: F401 - fixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
FONTE = b"OTTO" + b"\x01" * 32


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


def _montar(tmp_path, sistemas, leituras=None):
    from petro_vault import estado, ingestao
    arquivos = {"README.md": b"# DS\n", "assets/Logo-P.png": PNG, "assets/fonts/Branding Bold.otf": FONTE,
                "assets/pacote.zip": b"PK\x03\x04", "assets/grande.png": b"\x89PNG" + b"\x00" * (5 * 1024 * 1024),
                "assets/node_modules/x.png": PNG, "docs/manual.pdf": b"%PDF-1.4\n"}
    trabalho = tmp_path / "trabalho"
    for c, b in arquivos.items():
        (trabalho / c).parent.mkdir(parents=True, exist_ok=True)
        (trabalho / c).write_bytes(b)
    _git("init", "-q", "-b", "main", cwd=trabalho)
    _git("add", ".", cwd=trabalho)
    _git("commit", "-q", "-m", "x", cwd=trabalho)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=trabalho, capture_output=True, text=True).stdout.strip()
    leituras = leituras or [{"perfil": "referencia-explicada", "incluir": ["assets/*", "README.md"], "excluir": []},
                            {"perfil": "documentos", "incluir": ["docs/*"], "excluir": []}]
    sistemas.criar({"tag": "ds", "origens": [{"nome": "principal", "ramo": "main", "repo": "https://github.com/O/ds",
                                              "leituras": leituras}]}, "x")
    clone = ingestao.dir_clone("ds", "principal")
    os.makedirs(os.path.dirname(clone), exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(trabalho), clone], check=True)
    with estado.conectar() as db:
        db.execute("UPDATE origens SET commit_processado = ? WHERE tag = 'ds'", (commit,))
    return commit


def _cab(chave):
    return {"Authorization": f"Bearer {chave}"}


def test_lista_so_binarios_de_referencia_permitidos(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    commit = _montar(tmp_path, sistemas)
    chave = cred.criar("app", ["ds"], [])
    r = cliente.get("/v1/sistemas/ds/arquivos", headers=_cab(chave))
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    # Fora: .zip (extensão), grande.png (> 5 MB), node_modules/ (filtro de caminho da ingestão), o PDF de uma leitura de documentos
    # e o README (texto: vira nota).
    assert [f["path"] for f in files] == ["assets/Logo-P.png", "assets/fonts/Branding Bold.otf"]
    assert files[0] == {"path": "assets/Logo-P.png", "origin": "principal", "type": "image/png", "size": len(PNG),
                        "commit": commit, "download_url": "http://10.2.2.31:8670/v1/arquivos/ds/assets/Logo-P.png"}
    assert cliente.get("/v1/sistemas/ds/arquivos", params={"pasta": "assets/fonts"},
                       headers=_cab(chave)).json()["files"][0]["path"] == "assets/fonts/Branding Bold.otf"
    # Sem credencial, ou com credencial de outro vault.
    assert cliente.get("/v1/sistemas/ds/arquivos").status_code == 401
    assert cliente.get("/v1/sistemas/ds/arquivos", headers=_cab(cred.criar("outro", ["x"], []))).status_code == 403


def test_baixar_com_credencial_e_pacote(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    _montar(tmp_path, sistemas)
    chave = cred.criar("app", ["ds"], [])
    r = cliente.get("/v1/arquivos/ds/assets/fonts/Branding%20Bold.otf", headers=_cab(chave))
    assert r.status_code == 200 and r.content == FONTE
    assert r.headers["content-type"] == "font/otf"
    assert "attachment" in r.headers["content-disposition"] and "Branding%20Bold.otf" in r.headers["content-disposition"]
    assert "sandbox" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"
    for caminho in ("assets/pacote.zip", "assets/grande.png", "docs/manual.pdf", "README.md", "../ds/README.md"):
        assert cliente.get(f"/v1/arquivos/ds/{caminho}", headers=_cab(chave)).status_code == 404, caminho
    assert cliente.get("/v1/arquivos/ds/assets/Logo-P.png").status_code == 401
    r = cliente.get("/v1/sistemas/ds/arquivos.zip", params={"pasta": "assets"}, headers=_cab(chave))
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["assets/Logo-P.png", "assets/fonts/Branding Bold.otf"]
    assert z.read("assets/Logo-P.png") == PNG
    assert cliente.get("/v1/sistemas/ds/arquivos.zip", params={"pasta": "nada"}, headers=_cab(chave)).status_code == 404


def test_link_assinado(tela, tmp_path, monkeypatch):  # noqa: F811
    from petro_vault import arquivos
    cliente, sistemas, _ = tela
    _montar(tmp_path, sistemas)
    expira, sig = arquivos.assinar("ds", "principal", "assets/Logo-P.png")
    url = "/v1/arquivos/ds/assets/Logo-P.png"
    r = cliente.get(url, params={"exp": expira, "sig": sig})
    assert r.status_code == 200 and r.content == PNG
    # Assinatura de outro arquivo, adulterada, vencida ou com validade esticada: 403.
    assert cliente.get("/v1/arquivos/ds/assets/fonts/Branding%20Bold.otf",
                       params={"exp": expira, "sig": sig}).status_code == 403
    assert cliente.get(url, params={"exp": expira, "sig": sig[:-2] + "xx"}).status_code == 403
    assert cliente.get(url, params={"exp": expira + 3600, "sig": sig}).status_code == 403
    velho, sig_velho = arquivos.assinar("ds", "principal", "assets/Logo-P.png", agora=1000)
    r = cliente.get(url, params={"exp": velho, "sig": sig_velho})
    assert r.status_code == 403 and "vencido" in r.json()["detail"]
    # A chave fica no estado e vale entre reinícios; com VAULT_CHAVE_LINKS, a assinatura muda.
    assert (tmp_path / "links.chave").exists()
    monkeypatch.setenv("VAULT_CHAVE_LINKS", "outra")
    assert cliente.get(url, params={"exp": expira, "sig": sig}).status_code == 403


def _mcp(cliente, chave, nome, args):
    r = cliente.post("/mcp", headers=_cab(chave), json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                         "params": {"name": nome, "arguments": args}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_mcp_lista_e_da_link_com_curl(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    _montar(tmp_path, sistemas)
    chave = cred.criar("agente", ["ds"], [])
    nomes = [f["name"] for f in cliente.post("/mcp", headers=_cab(chave), json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]]
    assert {"list_files", "get_file"} <= set(nomes)
    res = _mcp(cliente, chave, "list_files", {"system_id": "ds", "folder": "assets/fonts"})
    assert [f["path"] for f in res["structuredContent"]["files"]] == ["assets/fonts/Branding Bold.otf"]
    res = _mcp(cliente, chave, "get_file", {"system_id": "ds", "path": "assets/Logo-P.png"})
    d = res["structuredContent"]
    assert d["url"].startswith("http://10.2.2.31:8670/v1/arquivos/ds/assets/Logo-P.png?exp=")
    assert d["curl"] == f'curl -fsSL -o "Logo-P.png" "{d["url"]}"'
    assert [c["type"] for c in res["content"]] == ["text", "image"]  # imagem pequena vem para o agente ver
    caminho = d["url"].removeprefix("http://10.2.2.31:8670")
    assert cliente.get(caminho).content == PNG  # o link funciona sem credencial
    font = _mcp(cliente, chave, "get_file", {"system_id": "ds", "path": "assets/fonts/Branding Bold.otf"})
    assert [c["type"] for c in font["content"]] == ["text"] and "Branding%20Bold.otf" in font["structuredContent"]["url"]
    # Arquivo fora da lista e vault sem acesso: erro da ferramenta, sem link.
    assert _mcp(cliente, chave, "get_file", {"system_id": "ds", "path": "assets/pacote.zip"})["isError"]
    outro = _mcp(cliente, cred.criar("outro", ["x"], []), "get_file", {"system_id": "ds", "path": "assets/Logo-P.png"})
    assert outro["isError"] and "url" not in json.dumps(outro)


def test_painel_lista_e_baixa(tela, tmp_path):  # noqa: F811
    cliente, sistemas, _ = tela
    _montar(tmp_path, sistemas)
    assert cliente.get("/v1/painel/sistemas/ds/arquivos").status_code == 401
    entrar(cliente)
    d = cliente.get("/v1/painel/sistemas/ds/arquivos").json()
    assert [a["caminho"] for a in d["arquivos"]] == ["assets/Logo-P.png", "assets/fonts/Branding Bold.otf"]
    r = cliente.get("/v1/painel/sistemas/ds/arquivos/baixar", params={"caminho": "assets/Logo-P.png"})
    assert r.status_code == 200 and r.content == PNG
    assert cliente.get("/v1/painel/sistemas/ds/arquivos.zip").status_code == 200


def test_vault_sem_referencia_nao_tem_arquivos(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    _montar(tmp_path, sistemas, leituras=[{"perfil": "codigo", "incluir": [], "excluir": []}])
    assert cliente.get("/v1/sistemas/ds/arquivos", headers=_cab(cred.criar("app", ["ds"], []))).json()["files"] == []


def test_painel_infra(tela, tmp_path):  # noqa: F811
    """DV-603: a rota do mapa de infraestrutura lê os arquivos de container do clone."""
    cliente, sistemas, _ = tela
    _montar(tmp_path, sistemas)  # sem arquivo de container
    entrar(cliente)
    r = cliente.get("/v1/painel/sistemas/ds/infra")
    assert r.status_code == 200 and r.json()["servicos"] == []
    assert cliente.get("/v1/painel/sistemas/nao-existe/infra").status_code == 404
