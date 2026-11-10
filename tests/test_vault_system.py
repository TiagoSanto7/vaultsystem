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
    assert eu["login"] == "tiago" and eu["curadoria"]["disponivel"] is False


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
    from vault_system import agente
    cab, corpo = agente.cabecalho("---\nvs: elemento # o tipo\norigens: [a.css, 'b.svg']\ntitulo: \"Cor\"\n---\n# X\n")
    assert cab == {"vs": "elemento", "origens": ["a.css", "b.svg"], "titulo": "Cor"} and corpo == "# X\n"
    cab, _ = agente.cabecalho(NOTA_REGRA)
    assert cab["origens"] == ["app/precos.py", "app/nao-existe.py"] and agente.do_agente(cab)
    assert not agente.do_agente(agente.cabecalho("---\ntitle: x\n---\n")[0])


def _processar(tag):
    from vault_system import agente, curadoria, estado, ingestao, literal, verificacao
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
    from vault_system import notas
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


CHAVE_FALSA = "sk-ant-teste-" + "x" * 30


def test_vault_i_configuracao_nunca_devolve_a_chave(tela):
    cliente, _, _ = tela
    entrar(cliente)
    v = cliente.get("/v1/painel/vault-i").json()
    assert v["configurada"] is False and [p["id"] for p in v["provedores"]] == ["anthropic", "claude-code", "openai"]
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "anthropic", "chave": ""}).status_code == 400
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "outro", "chave": CHAVE_FALSA}).status_code == 400
    r = cliente.put("/v1/painel/vault-i", json={"provedor": "anthropic", "chave": CHAVE_FALSA})
    assert r.status_code == 200 and r.json()["modelo"] == "claude-opus-5-5"
    assert CHAVE_FALSA not in r.text and r.json()["chave_final"] == "…xxxx"
    # trocar só o modelo mantém a chave; trocar de provedor pede chave nova
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "anthropic", "modelo": "claude-sonnet-5-5"}).json()["modelo"] == "claude-sonnet-5-5"
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "openai"}).status_code == 400
    assert cliente.get("/v1/painel/eu").json()["curadoria"]["disponivel"] is True
    assert cliente.delete("/v1/painel/vault-i").json()["configurada"] is False


def test_curadoria_so_sob_demanda_e_com_chave(tela):
    cliente, _, cred = tela
    h = {"Authorization": "Bearer " + cred.criar("autor", ["sem-chave"], ["sem-chave"])}
    r = cliente.put("/v1/sistemas/sem-chave/envio?modo=documentado&curar=true", content=zip_de({"a.py": "x\n"}), headers=h)
    assert r.json()["curadoria"]["estado"] == "indisponivel"  # sem chave: o envio passa, a curadoria não é pedida
    entrar(cliente)
    r = cliente.post("/v1/painel/sistemas/sem-chave/curadoria")
    assert r.status_code == 409 and "chave de API" in r.json()["detail"]
    cliente.put("/v1/painel/vault-i", json={"provedor": "anthropic", "chave": CHAVE_FALSA})
    from vault_system import estado, vault_i
    with estado.conectar() as db:
        assert vault_i.pendentes(db) == []  # com chave, nada acontece sozinho
    r = cliente.post("/v1/painel/sistemas/sem-chave/curadoria")
    assert r.status_code == 202 and r.json()["ja_havia"] is False
    assert cliente.post("/v1/painel/sistemas/sem-chave/curadoria").json()["ja_havia"] is True
    r = cliente.put("/v1/sistemas/sem-chave/envio?curar=true", content=zip_de({"a.py": "y\n"}), headers=h)
    assert r.json()["curadoria"]["estado"] == "pedida"
    with estado.conectar() as db:
        assert vault_i.pendentes(db) == ["sem-chave"]
    assert cliente.get("/v1/painel/sistemas/sem-chave").json()["curadoria"]["ultima"]["estado"] == "pedida"


def test_vault_i_escreve_notas_com_origem(tela, tmp_path, monkeypatch):
    from vault_system import estado, notas, vault_i
    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    tag = "precos"
    h = {"Authorization": "Bearer " + cred.criar("autor", [tag], [tag])}
    pacote = {"app/precos.py": "DESCONTO = 0.15\n", "docs/vs/desconto.md": NOTA_REGRA}
    cliente.put(f"/v1/sistemas/{tag}/envio?modo=documentado", content=zip_de(pacote), headers=h)
    (tmp_path / "vault" / "sistemas" / tag / "_meta").mkdir(parents=True)
    _processar(tag)
    vistos = []

    def chamar_falso(config, pedido):
        vistos.append(pedido)
        return [{"tipo": "modulo", "titulo": "Módulo de preços", "origens": ["app/precos.py", "inventado.py"],
                 "corpo": "Calcula preços."},
                {"tipo": "regra", "titulo": "Sem origem", "origens": ["nao/existe.py"], "corpo": "x"}]

    monkeypatch.setattr(vault_i, "chamar", chamar_falso)
    with estado.conectar() as db:
        vault_i.salvar(db, "anthropic", "", CHAVE_FALSA, "tiago")
        assert vault_i.atender(db, tag) is None  # nada pedido, nada feito
        vault_i.pedir(db, tag, "tiago", "painel")
        assert vault_i.atender(db, tag) == 1
        c = vault_i.listar(db, tag)[0]
    assert c["estado"] == "feita" and c["notas"] == 1
    assert "=== app/precos.py ===" in vistos[0] and "docs/vs/desconto.md" not in vistos[0]  # a nota do agente não vai
    assert "Desconto máximo" in vistos[0]  # o modelo vê o que já existe
    cab, corpo = notas.ler(str(tmp_path / "vault" / "sistemas" / tag / "modulos" / "modulo-de-precos.md"))
    assert cab["curada_por"] == "vault-i" and cab["origens"] == ["envio-local:app/precos.py"]
    assert cab["modelo"] == "anthropic:claude-opus-5-5" and corpo.startswith("# Módulo de preços")
    assert (tmp_path / "vault" / "sistemas" / tag / "regras" / "desconto.md").exists()  # a do agente fica
    with estado.conectar() as db:
        from vault_system import verificacao
        assert verificacao.verificar(db, tag) == []


def test_sem_chave_de_api_a_fila_nao_vira_laco(monkeypatch, tmp_path):
    from vault_system import coordenador, curadoria, estado
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
    return subprocess.run([sys.executable, os.path.join(RAIZ, "cli", "vs.py"), *args], cwd=cwd, env=env,
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
    assert vs["vault"] is None and vs["mode"] == "documented" and vs["version"] == 3  # vs init sem vault= não liga a nada
    agents = (projeto / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# AGENTS.md\n\n<!-- vs:inicio") and "Regras minhas." in agents  # só a seção gerenciada
    assert _vs(["init", "vault=Outro_Nome"], projeto, env).returncode == 1
    assert _vs(["init", "vault=template-design"], projeto, env).returncode == 0
    vs = json.loads((projeto / ".vs").read_text())
    assert vs["vault"] == "template-design" and vs["mode"] == "documented"  # o modo já escolhido fica
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
        import vs as cli_vs
    finally:
        sys.path.pop(0)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.txt").write_text("oi")
    with zipfile.ZipFile(io.BytesIO(cli_vs._empacotar(str(tmp_path), ["a/b.txt"]))) as z:
        assert z.namelist() == ["a/b.txt"] and z.read("a/b.txt") == b"oi"


def test_instaladores_da_cli_com_o_endereco_do_hub(tela, monkeypatch):
    cliente, _, _ = tela
    monkeypatch.setenv("VAULT_URL_PUBLICA", "http://hub.exemplo:8790")
    ps = cliente.get("/v1/cli/install.ps1")
    assert ps.status_code == 200 and "irm http://hub.exemplo:8790/v1/cli/install.ps1 | iex" in ps.text
    assert "{{HUB}}" not in ps.text and "\r\n" in ps.text
    sh = cliente.get("/v1/cli/install.sh")
    assert sh.status_code == 200 and "HUB=${VS_HUB:-http://hub.exemplo:8790}" in sh.text
    assert cliente.get("/v1/cli/qualquer.txt").status_code == 404
    vs = cliente.get("/v1/cli/vs")
    assert vs.status_code == 200 and vs.text.startswith("#!")


def test_cli_so_com_nomes_em_ingles(tmp_path):
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "VS_URL": "", "PYTHONUTF8": "1"}
    env.pop("VS_TOKEN", None)
    assert _vs(["init", "modo=literal"], tmp_path, env).returncode == 1  # parâmetro em português não existe
    assert _vs(["init", "mode=documentado"], tmp_path, env).returncode == 1
    assert _vs(["init", "vault=lit", "mode=literal"], tmp_path, env).returncode == 0
    assert json.loads((tmp_path / ".vs").read_text())["mode"] == "literal"
    for velho in ("versao", "ajuda"):
        assert _vs([velho], tmp_path, env).returncode == 2
    ajuda = _vs(["help"], tmp_path, env).stdout
    assert "mode=literal|documented" in ajuda and "connect repo" in ajuda and "modo=" not in ajuda


TOKEN_SETUP = "sk-ant-oat01-" + "y" * 40


def test_vault_i_aceita_token_do_claude_setup_token(tela, monkeypatch):
    cliente, _, _ = tela
    entrar(cliente)
    assert "claude-code" in [p["id"] for p in cliente.get("/v1/painel/vault-i").json()["provedores"]]
    # cada credencial no provedor certo
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "claude-code", "chave": CHAVE_FALSA}).status_code == 400
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "anthropic", "chave": TOKEN_SETUP}).status_code == 400
    r = cliente.put("/v1/painel/vault-i", json={"provedor": "claude-code", "chave": TOKEN_SETUP})
    assert r.status_code == 200 and TOKEN_SETUP not in r.text and r.json()["modelo"] == "claude-opus-5-5"

    from vault_system import vault_i
    chamadas = []

    class Resultado:
        returncode = 0
        stderr = ""
        stdout = json.dumps({"type": "result", "is_error": False,
                             "result": '```json\n{"notas": [{"tipo": "regra", "titulo": "T", "origens": ["a.py"], "corpo": "x"}]}\n```'})

    def run(cmd, **kw):
        chamadas.append((cmd, kw))
        return Resultado()

    import subprocess
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "nao-deve-vazar")
    notas_ = vault_i.chamar({"provedor": "claude-code", "modelo": "claude-opus-5-5", "chave": TOKEN_SETUP}, "pedido")
    assert notas_[0]["titulo"] == "T"
    cmd, kw = chamadas[0]
    assert cmd[:4] == ["claude", "-p", "--output-format", "json"] and "--disallowedTools" in cmd
    assert kw["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN_SETUP and "ANTHROPIC_API_KEY" not in kw["env"]
    assert kw["input"] == "pedido"
    Resultado.stdout = json.dumps({"type": "result", "is_error": True, "result": "Invalid API key · Please run /login"})
    try:
        vault_i.chamar({"provedor": "claude-code", "modelo": "claude-opus-5-5", "chave": TOKEN_SETUP}, "pedido")
        assert False
    except RuntimeError as e:
        assert "recusado" in str(e)


def test_template_leva_arquivos_de_audio(tela, tmp_path, monkeypatch):
    from vault_system import curadoria, estado, ingestao, literal
    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    tag = "template-design"
    h = {"Authorization": "Bearer " + cred.criar("autor", [tag], [tag])}
    som = b"ID3\x03\x00\x00\x00" + bytes(range(256)) * 4
    pacote = zip_de({"motion-vs/public/sfx/key.mp3": som, "motion-vs/README.md": "# Motion\n"})
    r = cliente.put(f"/v1/sistemas/{tag}/envio?mode=documented", content=pacote, headers=h)
    assert r.status_code == 200 and r.json()["arquivos"] == 2, r.text
    (tmp_path / "vault" / "sistemas" / tag / "_meta").mkdir(parents=True)
    with estado.conectar() as db:
        ingestao.ingerir(db, {"tag": tag})
        literal.copiar(db, tag)
        curadoria.avancar(db, tag)
    z = cliente.get("/v1/templates/design/motion-vs.zip", headers=h)
    assert z.status_code == 200, z.text
    with zipfile.ZipFile(io.BytesIO(z.content)) as arq:
        assert arq.read("public/sfx/key.mp3") == som


def test_vs_init_e_sync_por_vault_ou_template(tmp_path):
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "VS_URL": "", "PYTHONUTF8": "1"}
    env.pop("VS_TOKEN", None)
    (tmp_path / "t").mkdir()
    assert _vs(["init", "template=design"], tmp_path / "t", env).returncode == 0
    vs = json.loads((tmp_path / "t" / ".vs").read_text())
    assert vs["vault"] == "template-design" and vs["mode"] == "literal"
    (tmp_path / "v").mkdir()
    assert _vs(["init", "vault=my-project"], tmp_path / "v", env).returncode == 0
    vs = json.loads((tmp_path / "v" / ".vs").read_text())
    assert vs["vault"] == "my-project" and vs["mode"] == "documented"
    assert _vs(["init", "vault"], tmp_path / "v", env).returncode == 1
    assert _vs(["init", "template=Nome Ruim!"], tmp_path / "v", env).returncode == 1
    r = _vs(["sync", "template=motion", "--dry-run", "--json"], tmp_path / "v", env)
    assert r.returncode == 0, r.stderr
    plano = json.loads(r.stdout)
    assert plano["vault"] == "template-motion" and plano["mode"] == "literal"  # o .vs da pasta não muda
    assert json.loads((tmp_path / "v" / ".vs").read_text())["vault"] == "my-project"


def test_outra_pasta_soma_ao_template_sem_apagar(tela, tmp_path, monkeypatch):
    from vault_system import curadoria, estado, ingestao, literal
    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    tag = "template-design"
    h = {"Authorization": "Bearer " + cred.criar("autor", [tag], [tag])}
    base = zip_de({"default/tokens.css": ":root{}\n", "motion-vs/README.md": "# Motion\n"})
    assert cliente.put(f"/v1/sistemas/{tag}/envio?mode=documented", content=base, headers=h).status_code == 200
    # outra pasta, enviada como o template "instagram", soma ao vault; a pasta ligada continua igual
    posts = zip_de({"instagram/README.md": "# Posts\n", "instagram/regras.md": "x\n"})
    r = cliente.put(f"/v1/sistemas/{tag}/envio?mode=literal&origin=instagram", content=posts, headers=h)
    assert r.status_code == 200 and r.json()["origem"] == "instagram", r.text
    (tmp_path / "vault" / "sistemas" / tag / "_meta").mkdir(parents=True)
    with estado.conectar() as db:
        ingestao.ingerir(db, {"tag": tag})
        literal.copiar(db, tag)
        curadoria.avancar(db, tag)
        assert db.execute("SELECT modo FROM sistemas WHERE tag = ?", (tag,)).fetchone()[0] == "documentado"
    ids = [t["id"] for t in cliente.get("/v1/templates", headers=h).json()["templates"]]
    assert ids == ["design:default", "design:instagram", "design:motion-vs"]
    # reenviar a pasta ligada não apaga o template que veio da outra pasta
    assert cliente.put(f"/v1/sistemas/{tag}/envio", content=base, headers=h).status_code == 200
    with estado.conectar() as db:
        ingestao.ingerir(db, {"tag": tag})
        literal.copiar(db, tag)
        curadoria.avancar(db, tag)
    assert "design:instagram" in [t["id"] for t in cliente.get("/v1/templates", headers=h).json()["templates"]]


def test_vs_sync_template_de_outra_pasta_vira_um_template(tmp_path):
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "VS_URL": "", "PYTHONUTF8": "1"}
    env.pop("VS_TOKEN", None)
    pasta = tmp_path / "Posts Instagram"
    (pasta / "docs").mkdir(parents=True)
    (pasta / "docs" / "como.md").write_text("# Como\n")
    assert _vs(["init"], pasta, env).returncode == 0
    r = _vs(["sync"], pasta, env)
    assert r.returncode == 1 and "não está ligada" in r.stderr
    plano = json.loads(_vs(["sync", "template=design", "--dry-run", "--json"], pasta, env).stdout)
    assert plano["vault"] == "template-design" and plano["origin"] == "posts-instagram"
    assert "posts-instagram/docs/como.md" in plano["arquivos"]
    plano = json.loads(_vs(["sync", "template=design", "name=instagram", "--dry-run", "--json"], pasta, env).stdout)
    assert plano["origin"] == "instagram" and "instagram/docs/como.md" in plano["arquivos"]



def test_comandos_antigos_avisam_o_nome_novo(tmp_path):
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "VS_URL": "", "PYTHONUTF8": "1"}
    env.pop("VS_TOKEN", None)
    casos = {("templates",): "list templates", ("repo", "connect", "git@x:y.git"): "connect repo",
             ("init", "vault", "a"): "init vault=a", ("init", "pacote"): "init package=pacote",
             ("sync", "vault", "a"): "sync vault=a", ("sync", "a", "b.zip"): "sync vault=a file=b.zip"}
    for args, novo in casos.items():
        r = _vs(list(args), tmp_path, env)
        assert r.returncode == 1 and novo in r.stderr, (args, r.stderr)
    ajuda = _vs(["help"], tmp_path, env).stdout
    for cmd in ("vs list templates", "vs connect repo", "vs init template=<tipo>", "vs sync vault=<nome>", "file=<zip>"):
        assert cmd in ajuda


STUB_CLAUDE = """#!/bin/sh
# claude falso: confere o que o vs pediu e escreve uma nota em docs/vs/
cat > "$PWD/pedido.txt"
echo "$@" > "$PWD/args.txt"
echo "${CLAUDE_CODE_OAUTH_TOKEN:-sem-token}" > "$PWD/token.txt"
mkdir -p docs/vs
printf -- '---\nvs: regra\ntitulo: Regra\norigens:\n  - app.py\n---\n# Regra\n' > docs/vs/regra.md
echo '{"type":"result","is_error":false,"result":"RESUMO: 1 criada, 0 atualizadas, 0 apagadas"}'
"""


def test_curate_local_roda_o_agente_na_pasta(tmp_path, monkeypatch):
    import stat as st
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    stub = bin_ / "claude"
    stub.write_text(STUB_CLAUDE)
    stub.chmod(stub.stat().st_mode | st.S_IXUSR)
    env = {**os.environ, "VS_CLI": "1", "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "VS_URL": "http://127.0.0.1:9",
           "PYTHONUTF8": "1", "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", "VS_TOKEN": "vs_x",
           "VS_AGENT_TOKEN": "sk-ant-oat01-" + "z" * 30}
    pasta = tmp_path / "proj"
    pasta.mkdir()
    (pasta / "app.py").write_text("x = 1\n")
    # sem AGENTS.md: pede o init
    r = _vs(["sync", "vault=proj", "--curate"], pasta, env)
    assert r.returncode == 1 and "AGENTS.md" in r.stderr
    assert _vs(["login", "agent=claude"], pasta, env).returncode == 0
    assert _vs(["login", "agent=codex"], pasta, env).returncode == 1  # ainda não suportado
    assert _vs(["init", "vault=proj"], pasta, env).returncode == 0
    # --dry-run não roda o agente
    assert _vs(["sync", "--curate", "--dry-run"], pasta, env).returncode == 0
    assert not (pasta / "docs" / "vs" / "regra.md").exists()
    r = _vs(["sync", "--curate"], pasta, env)  # o envio falha (sem hub), mas a curadoria já rodou
    assert (pasta / "docs" / "vs" / "regra.md").exists()
    assert "AGENTS.md" in (pasta / "pedido.txt").read_text()
    args = (pasta / "args.txt").read_text()
    assert "-p" in args and "acceptEdits" in args and "Bash" in args  # Bash vai em disallowedTools
    assert (pasta / "token.txt").read_text().strip().startswith("sk-ant-oat01-")
    assert "não consegui falar" in r.stderr


def test_estudo_curado_links_resolvidos_e_sem_duplicar(tela, tmp_path, monkeypatch):
    from vault_system import notas
    cliente, _, cred = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    tag = "estudos"
    h = {"Authorization": "Bearer " + cred.criar("autor", [tag], [tag])}
    conceito = "---\nvs: conceito\ntitulo: O que é um vetor\norigens:\n  - vetores.md\n---\n# O que é um vetor\n\nVeja [[vetores-equipolentes]] e [[docs/vs/nada.md]].\n"
    regra = "---\nvs: regra\ntitulo: Vetores equipolentes\norigens:\n  - vetores.md\n---\n# Vetores equipolentes\n\nVolte a [[vetor-conceito|definição]].\n"
    pacote = {"vetores.md": "# Vetores\n", "AGENTS.md": "# AGENTS.md\n", "docs/vs/vetor-conceito.md": conceito,
              "docs/vs/vetores-equipolentes.md": regra}
    r = cliente.put(f"/v1/sistemas/{tag}/envio?mode=documented&origin=vetores", content=zip_de(pacote), headers=h)
    assert r.status_code == 200, r.text
    (tmp_path / "vault" / "sistemas" / tag / "_meta").mkdir(parents=True)
    problemas = _processar(tag)
    base = tmp_path / "vault" / "sistemas" / tag
    _, corpo = notas.ler(str(base / "conceitos" / "vetor-conceito.md"))
    assert f"[[sistemas/{tag}/regras/vetores-equipolentes]]" in corpo and "[[docs/vs/nada.md]]" in corpo
    _, corpo = notas.ler(str(base / "regras" / "vetores-equipolentes.md"))
    assert f"[[sistemas/{tag}/conceitos/vetor-conceito|definição]]" in corpo
    referencia = sorted(p.name for p in (base / "referencia").rglob("*.md"))
    assert referencia == ["vetores.md.md"] or referencia == ["vetores.md"], referencia  # sem AGENTS.md e sem as notas
    assert not (base / "indices" / "codigo.md").exists()
    assert [p for p in problemas if "link quebrado" in p] == [f"link quebrado: `sistemas/{tag}/conceitos/vetor-conceito` → `docs/vs/nada.md`"]
