import io
import zipfile

from test_painel import entrar, tela  # noqa: F401


def zip_de(arquivos):
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return pacote.getvalue()


def test_painel_e_cli_compartilham_catalogo(tela, tmp_path, monkeypatch):
    from vault_system import curadoria, estado, ingestao, literal

    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    tag = "template-docker"
    pacote = zip_de({"python/Dockerfile": "FROM python:3.12\n", "python/.env": "excluir"})
    assert cliente.post(f"/v1/painel/envios/{tag}?modo=literal", content=pacote).status_code == 401
    assert entrar(cliente).status_code == 200
    r = cliente.post(f"/v1/painel/envios/{tag}?modo=literal", content=pacote)
    assert r.status_code == 201, r.text
    assert r.json()["arquivos"] == 1
    leitura = {"Authorization": "Bearer " + cred.criar("leitura", [tag], [])}
    escrita = {"Authorization": "Bearer " + cred.criar("escrita", [tag], [tag])}
    assert cliente.put(f"/v1/sistemas/{tag}/envio", content=pacote, headers=leitura).status_code == 403
    novo = zip_de({"python/Dockerfile": "FROM python:3.13\n"})
    envio = cliente.put(f"/v1/sistemas/{tag}/envio", content=novo, headers=escrita)
    assert envio.status_code == 200, envio.text
    assert envio.json()["commit"] != r.json()["commit"]
    (tmp_path / "vault" / "sistemas" / tag / "_meta").mkdir(parents=True)
    with estado.conectar() as db:
        ingestao.ingerir(db, {"tag": tag})
        literal.copiar(db, tag)
        curadoria.avancar(db, tag)
    assert cliente.get("/v1/painel/cli").json() == cliente.get("/v1/templates", headers=leitura).json()
    resposta = cliente.get("/v1/painel/cli/templates/docker/python")
    assert resposta.status_code == 200, resposta.text
    detalhe = resposta.json()
    assert detalhe["id"] == "docker:python" and detalhe["files"][0]["path"] == "Dockerfile"
    download = cliente.get("/v1/templates/docker/python.zip", headers=leitura)
    assert download.status_code == 200, download.text
    with zipfile.ZipFile(io.BytesIO(download.content)) as z:
        assert z.namelist() == ["Dockerfile"]
        assert z.read("Dockerfile") == b"FROM python:3.13\n"


def test_cli_cria_vault_documentado_e_recusa_traversal(tela):
    from vault_system import estado, ingestao

    cliente, _, cred = tela
    tag = "meu-vault"
    headers = {"Authorization": "Bearer " + cred.criar("autor", [tag], [tag])}
    url = f"/v1/sistemas/{tag}/envio?modo=documentado"
    assert cliente.put(url, content=zip_de({"../fora": "x"}), headers=headers).status_code == 400
    r = cliente.put(url, content=zip_de({"src/main.py": "print('hello')\n"}), headers=headers)
    assert r.status_code == 200, r.text
    with estado.conectar() as db:
        ingestao.ingerir(db, {"tag": tag})
        # Vault System: documentado copia como está (sem LLM) e importa as notas do agente; a curadoria
        # interna é uma ação à parte, só com chave de API.
        assert db.execute("SELECT perfil FROM fila WHERE tag = ?", (tag,)).fetchone()[0] == "referencia"
        assert db.execute("SELECT modo FROM sistemas WHERE tag = ?", (tag,)).fetchone()[0] == "documentado"
    # o mesmo modo de novo só atualiza; outro modo é recusado
    assert cliente.put(url, content=zip_de({"src/main.py": "print('oi')\n"}), headers=headers).status_code == 200
    assert cliente.put(f"/v1/sistemas/{tag}/envio?modo=literal", content=zip_de({"a.md": "x"}),
                       headers=headers).status_code == 409


def test_painel_soma_origem_por_envio(tela, tmp_path, monkeypatch):
    from vault_system import estado

    cliente, _, _ = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    assert entrar(cliente).status_code == 200
    assert cliente.post("/v1/painel/envios/estudos?modo=documentado", content=zip_de({"a.md": "# A\n"})).status_code == 201
    # pasta enviada pelo painel: vira uma origem nova e soma ao vault, sem trocar o modo
    r = cliente.post("/v1/painel/envios/estudos?origem=vetores", content=zip_de({"vetores.md": "# Vetores\n"}))
    assert r.status_code == 201, r.text
    # nova versão da mesma origem e do envio principal (sem origem=)
    assert cliente.post("/v1/painel/envios/estudos?origem=vetores", content=zip_de({"vetores.md": "# V2\n"})).status_code == 201
    assert cliente.post("/v1/painel/envios/estudos", content=zip_de({"a.md": "# A2\n"})).status_code == 201
    assert cliente.post("/v1/painel/envios/estudos?origem=envio-local", content=zip_de({"x.md": "x"})).status_code == 400
    with estado.conectar() as db:
        nomes = [o["nome"] for o in db.execute("SELECT nome FROM origens WHERE tag = 'estudos' ORDER BY id")]
        modo = db.execute("SELECT modo FROM sistemas WHERE tag = 'estudos'").fetchone()["modo"]
    assert nomes == ["envio-local", "vetores"] and modo == "documentado"
