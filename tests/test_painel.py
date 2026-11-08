"""Testes da API da tela: login do AD, selo e sinais, credenciais."""
import importlib
import json

import pytest
from fastapi.testclient import TestClient

ADMIN, SENHA = "tiago.santo", "certa"


class AdFalso:
    """Faz o papel do AD: só `tiago.santo` e `outra.pessoa` com a senha `certa`."""
    fora = False

    def autenticar(self, login, senha):
        from app import sessao
        if self.fora:
            raise sessao.AdIndisponivel("fora")
        login = sessao.normalizar(login)
        if login in ("tiago.santo", "outra.pessoa") and senha == SENHA:
            return sessao.Usuario(login=login, nome=login.title())
        return None


@pytest.fixture()
def tela(tmp_path, monkeypatch):
    monkeypatch.setenv("ESTADO_DIR", str(tmp_path))
    monkeypatch.setenv("VAULT_SESSAO_SEGREDO", "s" * 40)
    monkeypatch.setenv("VAULT_ADMINS", "Tiago.Santo, outro.admin")
    from app import credenciais, main, painel, sessao, sistemas
    for m in (credenciais, sistemas, sessao, painel, main):
        importlib.reload(m)
    sessao._erros.clear()
    main.app.state.ldap = AdFalso()
    return TestClient(main.app), sistemas, credenciais


def entrar(cliente, login=ADMIN, senha=SENHA):
    return cliente.post("/v1/painel/entrar", json={"login": login, "senha": senha})


def test_login_do_ad(tela):
    cliente, _, _ = tela
    assert cliente.get("/v1/painel/sistemas").status_code == 401
    assert entrar(cliente, senha="errada").status_code == 401
    assert entrar(cliente, senha="").status_code == 401
    r = entrar(cliente, "outra.pessoa")
    assert r.status_code == 403 and "Sem acesso" in r.json()["detail"]
    cliente.app.state.ldap.fora = True
    assert entrar(cliente).status_code == 503
    cliente.app.state.ldap.fora = False
    r = entrar(cliente, "EXEMPLO\\Tiago.Santo")
    assert r.status_code == 200 and r.json()["login"] == "tiago.santo"
    assert cliente.get("/v1/painel/eu").json()["login"] == "tiago.santo"
    cliente.post("/v1/painel/sair")
    assert cliente.get("/v1/painel/sistemas").status_code == 401


def test_bloqueio_apos_5_erros(tela):
    cliente, _, _ = tela
    for _ in range(5):
        assert entrar(cliente, senha="errada").status_code == 401
    assert entrar(cliente).status_code == 429  # nem a senha certa passa no bloqueio


def test_tela_desligada_sem_segredo(tmp_path, monkeypatch):
    monkeypatch.setenv("ESTADO_DIR", str(tmp_path))
    monkeypatch.delenv("VAULT_SESSAO_SEGREDO", raising=False)
    from app import main, painel, sessao
    for m in (sessao, painel, main):
        importlib.reload(m)
    cliente = TestClient(main.app)
    assert cliente.post("/v1/painel/entrar", json={"login": ADMIN, "senha": SENHA}).status_code == 503
    assert cliente.get("/saude").status_code == 200  # a API dos agentes segue


CADASTRO = {"tag": "sis", "origens": [{"repo": "git@github.com:minha-org/sis.git", "leituras": [{"perfil": "documentos"}]}]}


def _selo(cliente, tag="sis"):
    return cliente.get(f"/v1/painel/sistemas/{tag}").json()["selo"]["estado"]


def test_selo_pela_precedencia(tela):
    from vault_system import estado
    cliente, sistemas, _ = tela
    entrar(cliente)
    r = cliente.post("/v1/painel/sistemas", json=CADASTRO)
    assert r.status_code == 201 and r.json()["selo"]["estado"] == "vazio"
    assert r.json()["cadastro"]["por"] == "tiago.santo"
    assert cliente.post("/v1/painel/sistemas", json=CADASTRO).status_code == 409
    p = cliente.post("/v1/painel/sistemas/sis/pull").json()
    assert _selo(cliente) == "processando"
    assert cliente.post("/v1/painel/sistemas/sis/pull").json()["ja_havia"] is True  # não duplica o pedido
    db = estado.conectar()
    with db:
        db.execute("UPDATE pulls SET atendido_em = 'x', resultado = ? WHERE id = ?",
                   (json.dumps({"itens": {}, "ignorados": [{"caminho": ".env", "motivo": "segredo (.env)"}],
                                "origens": {"principal": {"de": "a", "para": "b"}}}), p["pedido"]))
        db.execute("UPDATE origens SET commit_pendente = 'b', commit_processado = 'b', acesso_ok = 1, commits_atras = 0")
    assert _selo(cliente) == "em_dia"
    s = cliente.get("/v1/painel/sistemas").json()["sistemas"][0]
    assert s["sinais"]["ignorados"] == {"total": 1, "motivos": ["segredo"]}
    # Lote com erro na última rodada: com problema; uma rodada depois (sem lote), o erro antigo não prende o selo.
    with db:
        r1 = db.execute("INSERT INTO rodadas (modo, tags, inicio, fim, resultado) VALUES ('agenda', '[\"sis\"]', 'a', 'b', "
                        "'interrompida')").lastrowid
        db.execute("INSERT INTO lotes (rodada_id, tag, perfil, itens, inicio, fim, erro) "
                   "VALUES (?, 'sis', 'codigo', 3, 'a', 'b', 'interrompido')", (r1,))
    assert _selo(cliente) == "com_problema"
    with db:
        db.execute("INSERT INTO rodadas (modo, tags, inicio, fim, resultado) VALUES ('agenda', '[\"sis\"]', 'c', 'd', "
                   "'concluída')")
    assert _selo(cliente) == "em_dia"
    with db:
        db.execute("INSERT INTO verificacoes (tag, rodou_em, commits, total) VALUES ('sis', 'x', '{}', 2)")
    assert _selo(cliente) == "com_problema"
    with db:
        db.execute("UPDATE origens SET acesso_ok = 0, acesso_erro = 'Permission denied'")
    sist = cliente.get("/v1/painel/sistemas/sis").json()
    assert sist["selo"]["estado"] == "erro_acesso" and sist["origens"][0]["acesso"]["erro"] == "Permission denied"
    assert sist["origens"][0]["url"] == "https://github.com/minha-org/sis"
    assert cliente.delete("/v1/painel/sistemas/sis").status_code == 202
    assert _selo(cliente) == "removendo"


def _vault(sistemas, tag):
    sistemas.criar({"tag": tag, "origens": [{"nome": "principal", "ramo": "main", "repo": f"https://github.com/O/{tag}",
                                             "leituras": [{"perfil": "codigo", "incluir": [], "excluir": []}]}]}, "x")


def test_credencial_criada_pela_tela_funciona_e_revoga(tela):
    cliente, sistemas, _ = tela
    _vault(sistemas, "sis")
    entrar(cliente)
    r = cliente.post("/v1/painel/credenciais", json={"nome": "agente-x", "ler": ["sis"], "escrever": []})
    assert r.status_code == 201
    chave = r.json()["chave"]
    assert cliente.post("/v1/painel/credenciais", json={"nome": "agente-x"}).status_code == 409
    lista = cliente.get("/v1/painel/credenciais?tag=sis").json()
    assert lista[0]["criado_por"] == "tiago.santo" and "chave" not in lista[0]
    agente = TestClient(cliente.app)  # sem sessão: a porta dos agentes
    cab = {"Authorization": f"Bearer {chave}"}
    assert agente.get("/v1/sistemas/sis/acesso", headers=cab).status_code == 200
    assert agente.get("/v1/painel/credenciais", headers=cab).status_code == 401  # vs_ não abre a tela
    assert cliente.delete("/v1/painel/credenciais/agente-x").status_code == 200
    assert agente.get("/v1/sistemas/sis/acesso", headers=cab).status_code == 401


def test_token_com_varios_vaults(tela):
    """um token lê os vaults marcados; dá para trocar a lista sem trocar a chave."""
    cliente, sistemas, _ = tela
    for tag in ("app-a", "app-b", "app-c"):
        _vault(sistemas, tag)
    entrar(cliente)
    assert cliente.get("/v1/painel/eu").json()["url_publica"] == "http://127.0.0.1:8670"
    r = cliente.post("/v1/painel/credenciais", json={"nome": "portal", "ler": ["app-a", "nao-existe"], "escrever": []})
    assert r.status_code == 400 and "nao-existe" in r.json()["detail"]
    chave = cliente.post("/v1/painel/credenciais", json={"nome": "portal", "ler": ["app-a", "app-b"]}).json()["chave"]
    agente = TestClient(cliente.app)
    cab = {"Authorization": f"Bearer {chave}"}

    def vaults():
        r = agente.post("/mcp", headers=cab, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                  "params": {"name": "list_systems", "arguments": {}}})
        return [v["system_id"] for v in r.json()["result"]["structuredContent"]["systems"]]

    def busca(tag):
        return agente.post("/v1/knowledge/search", headers=cab, json={"system_id": tag, "query": "x"}).status_code

    assert vaults() == ["app-a", "app-b"] and (busca("app-b"), busca("app-c")) == (200, 403)
    token = cliente.get("/v1/painel/credenciais").json()[0]
    assert token["usado_em"]  # gravado na primeira chamada
    r = cliente.patch("/v1/painel/credenciais/portal", json={"ler": ["app-b", "app-c"]})
    assert r.status_code == 200 and r.json()["ler"] == ["app-b", "app-c"]
    assert vaults() == ["app-b", "app-c"] and (busca("app-a"), busca("app-c")) == (403, 200)
    assert cliente.patch("/v1/painel/credenciais/portal", json={"ler": []}).status_code == 422
    assert cliente.patch("/v1/painel/credenciais/portal", json={"ler": ["nao-existe"]}).status_code == 400
    assert cliente.patch("/v1/painel/credenciais/outro", json={"ler": ["app-a"]}).status_code == 404
    assert agente.patch("/v1/painel/credenciais/portal", headers=cab, json={"ler": ["app-a"]}).status_code == 401
    cliente.delete("/v1/painel/credenciais/portal")
    assert cliente.patch("/v1/painel/credenciais/portal", json={"ler": ["app-a"]}).status_code == 404


def test_links_do_github():
    from app import painel
    assert painel.url_repo("git@github.com:minha-org/x.git") == "https://github.com/minha-org/x"
    assert painel.url_repo("ssh://git@github.com/minha-org/x.git") == "https://github.com/minha-org/x"
    assert painel.url_arquivo("git@github.com:O/r.git", "abc", "docs/a.md") == "https://github.com/O/r/blob/abc/docs/a.md"


def test_apresentacao_vista_fica_no_servidor(tela):
    cliente, _, _ = tela
    entrar(cliente)
    assert cliente.get("/v1/painel/eu").json()["apresentacao_vista_em"] is None
    r = cliente.put("/v1/painel/eu/apresentacao", json={"vista": True})
    assert r.status_code == 200 and r.json()["apresentacao_vista_em"]
    assert cliente.get("/v1/painel/eu").json()["apresentacao_vista_em"] == r.json()["apresentacao_vista_em"]
    cliente.put("/v1/painel/eu/apresentacao", json={"vista": False})  # rever pelo perfil
    assert cliente.get("/v1/painel/eu").json()["apresentacao_vista_em"] is None


def test_origem_nova_pela_tela(tela):
    cliente, sistemas, _ = tela
    entrar(cliente)
    cad = {"tag": "sis", "origens": [{"repo": "git@github.com:Org/codigo.git",
                                      "leituras": [{"perfil": "codigo"}]}]}
    assert cliente.post("/v1/painel/sistemas", json=cad).status_code == 201
    doc = {"nome": "documentacao", "repo": "git@github.com:Org/docs.git", "leituras": [{"perfil": "documentos"}]}
    r = cliente.post("/v1/painel/sistemas/sis/origens", json=doc)
    assert r.status_code == 201 and [o["nome"] for o in r.json()["origens"]] == ["principal", "documentacao"]
    assert cliente.post("/v1/painel/sistemas/sis/origens", json=doc).status_code == 409
    ruim = {**doc, "nome": "outra", "repo": "https://ghp_token@github.com/Org/docs"}
    assert cliente.post("/v1/painel/sistemas/sis/origens", json=ruim).status_code == 400
    assert cliente.post("/v1/painel/sistemas/nao-existe/origens", json=doc).status_code == 404
    assert r.json()["sinais"]["notas"] == 0

    # editar ramo e leituras pede um pull; as leituras de antes ficam até a ingestão.
    nova = {"ramo": "dev", "leituras": [{"perfil": "documentos", "incluir": ["docs/**"]}, {"perfil": "codigo"}]}
    r = cliente.put("/v1/painel/sistemas/sis/origens/principal", json=nova)
    assert r.status_code == 200 and r.json()["pull_pendente"]
    o = r.json()["origens"][0]
    assert o["ramo"] == "dev" and o["leituras"][0]["incluir"] == ["docs/**"] and o["leituras_antes"][0]["perfil"] == "codigo"
    # Segunda edição antes do pull: continuam as leituras de antes (as que o vault reflete).
    r = cliente.put("/v1/painel/sistemas/sis/origens/principal", json={"leituras": [{"perfil": "documentos"}]})
    assert r.json()["origens"][0]["leituras_antes"][0]["perfil"] == "codigo"
    assert cliente.put("/v1/painel/sistemas/sis/origens/principal", json={"ramo": "../x", "leituras": [{"perfil": "documentos"}]}).status_code == 400
    assert cliente.put("/v1/painel/sistemas/sis/origens/principal", json={"leituras": []}).status_code == 422
    colado = {"leituras": [{"perfil": "documentos", "incluir": ["docs/**<br>**/*.md"]}]}
    assert cliente.put("/v1/painel/sistemas/sis/origens/principal", json=colado).status_code == 400
    assert cliente.put("/v1/painel/sistemas/sis/origens/nao-existe", json=nova).status_code == 404
    # o mesmo repositório passa da chave de deploy para o GitHub App (e volta); outro, não.
    app = {**nova, "repo": "https://github.com/org/Codigo"}
    r = cliente.put("/v1/painel/sistemas/sis/origens/principal", json=app)
    assert r.status_code == 200 and r.json()["origens"][0]["repo"] == "https://github.com/org/Codigo"
    r = cliente.put("/v1/painel/sistemas/sis/origens/principal", json={**nova, "repo": "git@github.com:Org/codigo.git"})
    assert r.json()["origens"][0]["repo"] == "git@github.com:Org/codigo.git"
    assert cliente.put("/v1/painel/sistemas/sis/origens/principal", json=nova).json()["origens"][0]["repo"] == "git@github.com:Org/codigo.git"
    for outro in ("https://github.com/Org/docs", "https://github.com/Org/codigo-novo", "git@gitlab.com:Org/codigo.git"):
        assert cliente.put("/v1/painel/sistemas/sis/origens/principal", json={**nova, "repo": outro}).status_code == 400
    # Remover: não a única; a removida aparece como "removendo" e não pode ser editada.
    r = cliente.delete("/v1/painel/sistemas/sis/origens/documentacao")
    assert r.status_code == 202 and r.json()["origens"][1]["situacao"] == "removendo"
    assert cliente.put("/v1/painel/sistemas/sis/origens/documentacao", json=nova).status_code == 404
    assert cliente.delete("/v1/painel/sistemas/sis/origens/principal").status_code == 409


def test_tela_servida_pela_api(tela, tmp_path, monkeypatch):
    cliente, _, _ = tela
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<div id=raiz></div>")
    (web / "assets" / "app-123.js").write_text("ok")
    (tmp_path / "segredo.txt").write_text("não")
    from app import main
    monkeypatch.setattr(main, "WEB", str(web))
    r = cliente.get("/sistemas/sis/fontes")  # rota do React: devolve o index.html
    assert r.status_code == 200 and "raiz" in r.text and r.headers["cache-control"] == "no-cache"
    r = cliente.get("/assets/app-123.js")
    assert r.text == "ok" and "immutable" in r.headers["cache-control"]
    assert "não" not in cliente.get("/../segredo.txt").text
    assert "não" not in cliente.get("/%2e%2e/segredo.txt").text
    assert cliente.get("/v1/rota-que-nao-existe").status_code == 404
    assert cliente.get("/saude").json() == {"ok": True}


def test_rodadas_sem_trabalho_ficam_de_fora(tela):
    """A lista de rodadas mostra por padrão só as que leram algo da tag, paginada."""
    from vault_system import estado
    cliente, _, _ = tela
    entrar(cliente)
    assert cliente.post("/v1/painel/sistemas", json=CADASTRO).status_code == 201
    db = estado.conectar()
    with db:
        for i in range(1, 26):
            db.execute("INSERT INTO rodadas (id, modo, tags, inicio, fim, resultado) VALUES (?, 'auto', '[\"sis\"]', 'x', 'y', 'ok')",
                       (i,))
            if i % 2:  # 13 rodadas com lote da tag
                db.execute("INSERT INTO lotes (rodada_id, tag, perfil, itens, inicio) VALUES (?, 'sis', 'documentos', 1, 'x')", (i,))
    r = cliente.get("/v1/painel/sistemas/sis/rodadas").json()
    assert r["total"] == 13 and len(r["rodadas"]) == 10 and r["rodadas"][0]["id"] == 25
    assert all(x["lotes"] for x in r["rodadas"])
    r = cliente.get("/v1/painel/sistemas/sis/rodadas?todas=true&limite=20").json()
    assert r["total"] == 25 and len(r["rodadas"]) == 20


def test_fila_paginada_com_parados_primeiro(tela):
    from vault_system import estado
    cliente, _, _ = tela
    entrar(cliente)
    assert cliente.post("/v1/painel/sistemas", json=CADASTRO).status_code == 201
    db = estado.conectar()
    with db:
        for i in range(45):
            db.execute("INSERT INTO fila (tag, acao, caminho, commit_origem, criado_em, origem, perfil, tentativas, "
                       "erro, parado_em) VALUES ('sis', 'adicionado', ?, 'c', 'x', 'principal', 'documentos', ?, ?, ?)",
                       (f"docs/{i}.md", *((5, "tempo esgotado", "y") if i == 40 else (1, "sem registro", None)
                                          if i == 30 else (0, None, None))))
    f = cliente.get("/v1/painel/sistemas/sis/fila").json()
    assert f["total"] == 45 and f["parados"] == 1 and len(f["itens"]) == 20
    # Parado primeiro, depois quem já falhou.
    assert f["itens"][0]["caminho"] == "docs/40.md" and f["itens"][0]["parado"] and f["itens"][0]["erro"] == "tempo esgotado"
    assert f["itens"][1]["caminho"] == "docs/30.md" and not f["itens"][1]["parado"]
    assert len(cliente.get("/v1/painel/sistemas/sis/fila?limite=40").json()["itens"]) == 40
    assert "1 item(ns) parado(s)" in cliente.get("/v1/painel/sistemas/sis").json()["selo"]["texto"]

    # pedir de novo zera as tentativas; só vale para item parado.
    item = f["itens"][0]["id"]
    assert cliente.post(f"/v1/painel/sistemas/sis/fila/{item}/retomar").status_code == 200
    l = db.execute("SELECT tentativas, erro, parado_em FROM fila WHERE id = ?", (item,)).fetchone()
    assert tuple(l) == (0, None, None)
    assert cliente.post(f"/v1/painel/sistemas/sis/fila/{item}/retomar").status_code == 404
    assert cliente.get("/v1/painel/sistemas/sis/fila").json()["parados"] == 0
