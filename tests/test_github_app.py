"""Testes do GitHub App (DV-573): origem https://github.com/... lida pelo App,
erros separados por causa e a lista de repositórios da tela."""
import importlib
import io
import json
import urllib.error

import pytest

from test_ingestao import ambiente, commit, escrever  # noqa: F401 - fixture
from test_painel import entrar, tela  # noqa: F401 - fixture


class Resposta(io.BytesIO):
    def __init__(self, status, corpo):
        super().__init__(json.dumps(corpo).encode())
        self.status = status


def github_falso(monkeypatch, gh, rotas):
    """urlopen falso: `rotas` é {(metodo, caminho sem query): (status, corpo[, cabeçalhos])}."""
    def urlopen(req, timeout=None):
        caminho = req.full_url.removeprefix(gh.API).split("?")[0]
        status, corpo, *cab = rotas[(req.get_method(), caminho)]
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "x", (cab or [{}])[0], io.BytesIO(json.dumps(corpo).encode()))
        return Resposta(status, corpo)
    monkeypatch.setattr(gh.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(gh, "_jwt", lambda: "jwt")
    gh._tokens.clear()


def test_origem_do_app_e_erros_separados(monkeypatch):
    from petro_vault import github_app as gh
    assert gh.do_app("https://github.com/PetrovinaS/petrotracker") == ("PetrovinaS", "petrotracker")
    assert gh.do_app("https://github.com/PetrovinaS/petrotracker.git") == ("PetrovinaS", "petrotracker")
    assert gh.do_app("git@github.com:PetrovinaS/x.git") is None
    assert gh.do_app("https://ghp_x@github.com/PetrovinaS/x") is None

    github_falso(monkeypatch, gh, {
        ("GET", "/repos/O/sem-app/installation"): (404, {"message": "Not Found"}),
        ("GET", "/repos/O/r/installation"): (200, {"id": 7}),
        ("POST", "/app/installations/7/access_tokens"): (201, {"token": "ghs_segredo", "expires_at": "x"}),
        ("GET", "/repos/O/limite/installation"): (403, {}, {"x-ratelimit-remaining": "0"}),
        ("GET", "/repos/O/fora/installation"): (502, {}),
    })
    with pytest.raises(gh.ErroGitHub, match="não está instalado em O/sem-app"):
        gh.token("O", "sem-app")
    with pytest.raises(gh.ErroGitHub, match="limite de requisições"):
        gh.token("O", "limite")
    with pytest.raises(gh.ErroGitHub, match="indisponível"):
        gh.token("O", "fora")
    env = gh.ambiente_git("O", "r")
    # O token vai num cabeçalho por variável de ambiente, nunca na URL do remoto.
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ") and "ghs_segredo" not in env["GIT_CONFIG_VALUE_0"]


def test_pull_de_origem_do_app_sem_app_configurado(ambiente, monkeypatch):  # noqa: F811
    origem, _, db, ingestao = ambiente
    escrever(origem, {"a.md": "a\n"})
    commit(origem, "1")
    monkeypatch.setattr(ingestao.github_app, "APP_ID", "")
    ingestao.estado.migrar_origens(db)
    with db:
        db.execute("UPDATE origens SET repo = 'https://github.com/O/r'")
        db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES ('sis', 'x', 'teste')")
    ingestao._atender(db, ["sis"])
    r = json.loads(db.execute("SELECT resultado FROM pulls").fetchone()["resultado"])
    assert "GitHub App não configurado" in r["erro"]
    o = db.execute("SELECT acesso_ok, acesso_erro FROM origens").fetchone()
    assert o["acesso_ok"] == 0 and "GitHub App não configurado" in o["acesso_erro"]


def test_ramo_que_nao_existe(ambiente):  # noqa: F811
    origem, _, db, ingestao = ambiente
    escrever(origem, {"a.md": "a\n"})
    commit(origem, "1")
    ingestao._atender(db, ["sis"])
    with db:
        db.execute("UPDATE origens SET ramo = 'nao-existe'")
        db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES ('sis', 'x', 'teste')")
    ingestao._atender(db, ["sis"])
    r = json.loads(db.execute("SELECT resultado FROM pulls").fetchone()["resultado"])
    assert r["erro"] == "o ramo nao-existe não existe no repositório"


def test_lista_de_repositorios_para_a_tela(tela, monkeypatch):  # noqa: F811
    cliente, _, _ = tela
    entrar(cliente)
    from petro_vault import estado, github_app as gh
    importlib.reload(gh)
    assert cliente.get("/v1/painel/github/repos").json() == {"repos": [], "atualizado_em": None, "erro": None, "pedido_em": None}
    assert cliente.post("/v1/painel/github/atualizar").status_code == 202
    assert cliente.get("/v1/painel/github/repos").json()["pedido_em"]

    github_falso(monkeypatch, gh, {
        ("GET", "/app/installations"): (200, [{"id": 7}]),
        ("POST", "/app/installations/7/access_tokens"): (201, {"token": "ghs_x"}),
        ("GET", "/installation/repositories"): (200, {"repositories": [
            {"full_name": "PetrovinaS/petrotracker", "default_branch": "main", "private": True}]}),
        ("GET", "/repos/PetrovinaS/petrotracker/branches"): (200, [{"name": "main"}, {"name": "dev"}]),
    })
    db = estado.conectar()
    gh.atualizar_lista(db)
    r = cliente.get("/v1/painel/github/repos").json()
    assert r["repos"] == [{"nome": "PetrovinaS/petrotracker", "repo": "https://github.com/PetrovinaS/petrotracker",
                           "ramo_padrao": "main", "privado": True, "ramos": ["main", "dev"]}]
    assert r["pedido_em"] is None and r["erro"] is None and r["atualizado_em"]
    gh.atualizar_lista(db)  # lista nova e sem pedido: não consulta o GitHub de novo
    monkeypatch.setattr(gh, "listar", lambda: (_ for _ in ()).throw(gh.ErroGitHub("GitHub indisponível (x)")))
    cliente.post("/v1/painel/github/atualizar")
    gh.atualizar_lista(db)
    r = cliente.get("/v1/painel/github/repos").json()
    assert r["erro"] == "GitHub indisponível (x)" and len(r["repos"]) == 1  # a lista anterior fica

    # Origem pelo App: aceita no cadastro, com link para o GitHub.
    cad = {"tag": "tracker", "origens": [{"repo": "https://github.com/PetrovinaS/petrotracker", "ramo": "main",
                                          "leituras": [{"perfil": "codigo"}]}]}
    r = cliente.post("/v1/painel/sistemas", json=cad)
    assert r.status_code == 201 and r.json()["origens"][0]["url"] == "https://github.com/PetrovinaS/petrotracker"
