"""Vault System: conta local no hub, token de conexão (vs login), vs init/vs sync e notas do agente
importadas como curadas, sem curador no hub."""
import io
import json
import os
import subprocess
import sys
import zipfile

from test_envios import zip_de
from test_painel import entrar, tela  # noqa: F401

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NOTA_REGRA = """---
vs: regra
titulo: Desconto máximo
origens:
  - app/precos.py
  - app/nao-existe.py
---
O desconto nunca passa de 15%.
"""


def test_conta_local_entra_sem_ad(tela):
    cliente, _, _ = tela
    from app import sessao
    cliente.app.state.ldap = None  # sem AD configurado
    sessao.criar_usuario("Tiago", "senha-forte-1", "Tiago")
    assert entrar(cliente, "tiago", "errada").status_code == 401
    r = entrar(cliente, "tiago", "senha-forte-1")
    assert r.status_code == 200 and r.json()["login"] == "tiago"
    eu = cliente.get("/v1/painel/eu").json()
    assert eu["login"] == "tiago" and eu["curadoria"] == {"disponivel": False, "provedor": None}


def test_conta_inicial_pelo_ambiente(tela, monkeypatch):
    cliente, _, _ = tela
    from app import sessao
    cliente.app.state.ldap = None
    monkeypatch.setenv("VAULT_ADMIN_LOGIN", "dono")
    monkeypatch.setenv("VAULT_ADMIN_SENHA", "uma-senha-boa")
    assert sessao.garantir_admin_do_ambiente() == "dono"
    assert sessao.garantir_admin_do_ambiente() is None  # já existe: não troca a senha
    assert entrar(cliente, "dono", "uma-senha-boa").status_code == 200


def test_token_de_conexao_cria_vault_e_diz_o_dono(tela):
    cliente, _, _ = tela
    entrar(cliente)
    r = cliente.post("/v1/painel/credenciais", json={"nome": "meu-notebook", "workspace": True})
    assert r.status_code == 201 and r.json()["workspace"] is True
    h = {"Authorization": "Bearer " + r.json()["chave"]}
    eu = cliente.get("/v1/eu", headers=h).json()
    assert eu == {"credencial": "meu-notebook", "workspace": True, "dono": "tiago.santo",
                  "hub": eu["hub"], "vaults": []}
    envio = cliente.put("/v1/sistemas/novo-projeto/envio?modo=documentado", content=zip_de({"a.md": "# A\n"}),
                        headers=h)
    assert envio.status_code == 200, envio.text
    assert cliente.get("/v1/eu", headers=h).json()["vaults"] == ["novo-projeto"]
    assert cliente.get("/v1/sistemas/novo-projeto/acesso", headers=h).status_code == 200
    lista = cliente.get("/v1/painel/credenciais?tag=novo-projeto").json()
    assert [c["nome"] for c in lista] == ["meu-notebook"]


def test_cabecalho_do_agente():
    from petro_vault import agente
    cab, corpo = agente.cabecalho("---\nvs: elemento # o tipo\norigens: [a.css, 'b.svg']\ntitulo: \"Cor\"\n---\n# X\n")
    assert cab == {"vs": "elemento", "origens": ["a.css", "b.svg"], "titulo": "Cor"} and corpo == "# X\n"
    cab, _ = agente.cabecalho(NOTA_REGRA)
    assert cab["origens"] == ["app/precos.py", "app/nao-existe.py"] and agente.do_agente(cab)
    assert not agente.do_agente(agente.cabecalho("---\ntitle: x\n---\n")[0])


def _processar(tag):
    from petro_vault import agente, curadoria, estado, ingestao, literal, verificacao
    with estado.conectar() as db:
        ingestao.ingerir(db, {"tag": tag})
        literal.copiar(db, tag)
        curadoria.avancar(db, tag)
        agente.importar(db, tag)
        verificacao.indices(tag)
        problemas = verificacao.verificar(db, tag)
        verificacao.indexar(db, tag)
    return problemas


def test_notas_do_agente_entram_curadas(tela, tmp_path, monkeypatch):
    from petro_vault import notas
    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    tag = "precos"
    h = {"Authorization": "Bearer " + cred.criar("autor", [tag], [tag])}
    pacote = {"app/precos.py": "DESCONTO = 0.15\n", "docs/vs/desconto.md": NOTA_REGRA, "README.md": "# Preços\n"}
    assert cliente.put(f"/v1/sistemas/{tag}/envio?modo=documentado", content=zip_de(pacote), headers=h).status_code == 200
    (tmp_path / "vault" / "sistemas" / tag / "_meta").mkdir(parents=True)
    problemas = _processar(tag)
    assert problemas == []
    nota = tmp_path / "vault" / "sistemas" / tag / "regras" / "desconto.md"
    cab, corpo = notas.ler(str(nota))
    assert cab["tipo_nota"] == "regra" and cab["curada_por"] == "agente"
    assert cab["origens"] == ["envio-local:app/precos.py"] and cab["nota_origem"] == "envio-local:docs/vs/desconto.md"
    assert corpo.startswith("# Desconto máximo\n") and "[[sistemas/precos/referencia/envio-local/app/precos.py]]" in corpo
    # a tela conta as notas do agente; a busca acha a nota
    entrar(cliente)
    v = cliente.get(f"/v1/painel/sistemas/{tag}").json()
    assert v["modo"] == "documentado" and v["notas_do_agente"] == 1
    r = cliente.post("/v1/knowledge/search", json={"system_id": tag, "query": "desconto"}, headers=h).json()
    assert any(x["note_id"] == f"sistemas/{tag}/regras/desconto" for x in r["results"])
    # o agente apagou a nota: no próximo envio ela sai do vault
    del pacote["docs/vs/desconto.md"]
    assert cliente.put(f"/v1/sistemas/{tag}/envio", content=zip_de(pacote), headers=h).status_code == 200
    _processar(tag)
    assert not nota.exists()


def test_modo_literal_nao_importa_notas(tela, tmp_path, monkeypatch):
    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    h = {"Authorization": "Bearer " + cred.criar("autor", ["lit"], ["lit"])}
    pacote = zip_de({"app/precos.py": "x = 1\n", "docs/vs/desconto.md": NOTA_REGRA})
    assert cliente.put("/v1/sistemas/lit/envio?modo=literal", content=pacote, headers=h).status_code == 200
    (tmp_path / "vault" / "sistemas" / "lit" / "_meta").mkdir(parents=True)
    _processar("lit")
    assert not (tmp_path / "vault" / "sistemas" / "lit" / "regras").exists()


def test_curadoria_interna_so_com_chave(tela):
    cliente, sistemas_, cred = tela
    h = {"Authorization": "Bearer " + cred.criar("autor", ["sem-chave"], ["sem-chave"])}
    cliente.put("/v1/sistemas/sem-chave/envio?modo=documentado", content=zip_de({"a.py": "x\n"}), headers=h)
    entrar(cliente)
    r = cliente.post("/v1/painel/sistemas/sem-chave/curadoria")
    assert r.status_code == 409 and "chave de API" in r.json()["detail"]
    from petro_vault import estado, historico
    with estado.conectar() as db:
        historico._definir(db, "curadoria", {"disponivel": True, "provedor": "hermes"})
    r = cliente.post("/v1/painel/sistemas/sem-chave/curadoria")
    assert r.status_code == 202 and r.json()["perfil"] == "codigo-literal"
    assert cliente.post("/v1/painel/sistemas/sem-chave/curadoria").status_code == 409  # já curado


def test_sem_chave_de_api_a_fila_nao_vira_laco(monkeypatch, tmp_path):
    from petro_vault import coordenador, curadoria, estado
    monkeypatch.setenv("ESTADO_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_CURADORIA_PROVEDOR", raising=False)
    assert not curadoria.disponivel()
    with estado.conectar() as db:
        db.execute("INSERT INTO sistemas (tag, perfil, repo, ramo, incluir, excluir, criado_em, criado_por) "
                   "VALUES ('t', 'codigo', 'r', 'main', '[]', '[]', 'x', 'y')")
        db.execute("INSERT INTO fila (tag, acao, caminho, commit_origem, criado_em) VALUES ('t', 'adicionado', 'a', 'c', 'x')")
        c = coordenador.Coordenador(publicar=lambda tags: None)
        c.ultima["t"] = coordenador._agora()  # acabou de rodar
        assert c.fila(db) == []
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t" * 60)
        assert c.fila(db) == [("t", "fila")]


# --- CLI ------------------------------------------------------------------------------

def _vs(args, cwd, env):
    return subprocess.run([sys.executable, os.path.join(RAIZ, "cli", "pv.py"), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_vs_init_e_sync_dry_run(tmp_path):
    projeto = tmp_path / "Meu Projeto"
    (projeto / "app").mkdir(parents=True)
    (projeto / "app" / "precos.py").write_text("x = 1\n")
    (projeto / ".env").write_text("SEGREDO=1\n")
    (projeto / "node_modules").mkdir()
    (projeto / "node_modules" / "lib.js").write_text("x")
    (projeto / "AGENTS.md").write_text("# AGENTS.md\n\nRegras minhas.\n")
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "VS_URL": "", "PYTHONUTF8": "1"}
    env.pop("VS_TOKEN", None)
    r = _vs(["init"], projeto, env)
    assert r.returncode == 0, r.stderr
    vs = json.loads((projeto / ".vs").read_text())
    assert vs["vault"] == "meu-projeto" and vs["modo"] == "documentado" and vs["versao"] == 2
    agents = (projeto / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# AGENTS.md\n\n<!-- vs:inicio") and "Regras minhas." in agents  # só a seção gerenciada
    assert _vs(["init", "vault=Outro_Nome"], projeto, env).returncode == 1
    assert _vs(["init", "vault=template-design"], projeto, env).returncode == 0
    vs = json.loads((projeto / ".vs").read_text())
    assert vs["vault"] == "template-design" and vs["modo"] == "documentado"  # o modo já escolhido fica
    (projeto / "docs").mkdir()
    (projeto / "docs" / "regra.md").write_text(NOTA_REGRA, encoding="utf-8")
    r = _vs(["sync", "--dry-run", "--json"], projeto, env)
    assert r.returncode == 0, r.stderr
    plano = json.loads(r.stdout)
    assert plano["arquivos"] == [".gitignore", "AGENTS.md", "app/precos.py", "docs/regra.md"]
    assert plano["notas_do_agente"] == ["docs/regra.md"]


def test_vs_sync_sem_init(tmp_path):
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    r = _vs(["sync"], tmp_path, env)
    assert r.returncode == 1 and r.stderr.startswith("vs: esta pasta não tem .vs")


def test_pacote_do_sync_e_zip_valido(tmp_path):
    sys.path.insert(0, os.path.join(RAIZ, "cli"))
    try:
        import pv
    finally:
        sys.path.pop(0)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.txt").write_text("oi")
    with zipfile.ZipFile(io.BytesIO(pv._empacotar(str(tmp_path), ["a/b.txt"]))) as z:
        assert z.namelist() == ["a/b.txt"] and z.read("a/b.txt") == b"oi"
