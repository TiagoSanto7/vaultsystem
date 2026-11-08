"""Templates para baixar: API (/v1/templates), bloqueio por segredo e a CLI vs."""
import importlib.util
import io
import json
import os
import pathlib
import stat
import subprocess
import zipfile

import pytest

from test_painel import tela  # noqa: F401 - fixture

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = b"FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\", \"main.py\"]\n"
COMPOSE = b"services:\n  app:\n    build: .\n    env_file: .env\n    environment:\n      DB_PASSWORD: ${DB_PASSWORD}\n"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


def _montar(tmp_path, sistemas, tag="template-docker", extra=None, leituras=None):
    from vault_system import estado, ingestao
    arquivos = {"README.md": b"# Templates docker\n",
                "python/Dockerfile": DOCKERFILE, "python/docker-compose.yml": COMPOSE,
                "python/.dockerignore": b".env\n__pycache__/\n", "python/.env.example": b"DB_PASSWORD=\n",
                "python/.env": b"DB_PASSWORD=supersecreta123\n", "python/scripts/entrar.sh": b"#!/bin/sh\nexec \"$@\"\n",
                "python/template.json": json.dumps({"descricao": "Python 3.12 com compose"}).encode(),
                "python/node_modules/x.js": b"x\n", "python/logo.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
                "python/pacote.bin": b"\x00\x01\x02",
                "laravel/Dockerfile": b"FROM php:8.3-fpm\n",
                "laravel/docker-compose.yml": b"services:\n  db:\n    environment:\n      DB_PASSWORD: segredo-de-verdade\n",
                **(extra or {})}
    trabalho = tmp_path / "trabalho"
    for c, b in arquivos.items():
        (trabalho / c).parent.mkdir(parents=True, exist_ok=True)
        (trabalho / c).write_bytes(b)
    (trabalho / "python/scripts/entrar.sh").chmod(0o755)
    _git("init", "-q", "-b", "main", cwd=trabalho)
    _git("add", "-f", ".", cwd=trabalho)
    _git("commit", "-q", "-m", "x", cwd=trabalho)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=trabalho, capture_output=True, text=True).stdout.strip()
    sistemas.criar({"tag": tag, "origens": [{"nome": "principal", "ramo": "main", "repo": "https://github.com/O/t",
                                             "leituras": leituras or [{"perfil": "referencia", "incluir": [],
                                                                       "excluir": []}]}]}, "x")
    clone = ingestao.dir_clone(tag, "principal")
    os.makedirs(os.path.dirname(clone), exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(trabalho), clone], check=True)
    with estado.conectar() as db:
        db.execute("UPDATE origens SET commit_processado = ? WHERE tag = ?", (commit, tag))
    return commit


def _cab(chave):
    return {"Authorization": f"Bearer {chave}"}


def test_lista_e_detalhes(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    commit = _montar(tmp_path, sistemas)
    _montar(tmp_path / "outro", sistemas, tag="refeitorio")  # vault sem o prefixo: não é template
    chave = cred.criar("qualquer", ["nada-a-ver"], [])  # decisão 3: qualquer credencial válida
    assert cliente.get("/v1/templates").status_code == 401
    r = cliente.get("/v1/templates", headers=_cab(chave))
    assert r.status_code == 200, r.text
    ts = r.json()["templates"]
    assert [t["id"] for t in ts] == ["docker:laravel", "docker:python"]
    py = ts[1]
    assert py == {"id": "docker:python", "tipo": "docker", "nome": "python", "vault": "template-docker",
                  "descricao": "Python 3.12 com compose", "arquivos": 6, "commit": commit, "bloqueado": None}
    assert cliente.get("/v1/templates", params={"tipo": "k8s"}, headers=_cab(chave)).json() == {"templates": []}
    assert cliente.get("/v1/templates", params={"tipo": "../x"}, headers=_cab(chave)).status_code == 400
    d = cliente.get("/v1/templates/docker/python", headers=_cab(chave)).json()
    caminhos = [f["path"] for f in d["files"]]
    # .env e node_modules ficam de fora pelo filtro de caminho; template.json não vai para o projeto.
    assert ".env" not in caminhos and ".env.example" in caminhos and "template.json" not in caminhos
    assert not any("node_modules" in c for c in caminhos)
    assert {"path": "scripts/entrar.sh", "size": 20, "executable": True} in d["files"]
    assert d["template_json"] == {"descricao": "Python 3.12 com compose"}
    assert cliente.get("/v1/templates/docker/nada", headers=_cab(chave)).status_code == 404
    from vault_system import templates
    for ruim in ("docker:..", "docker:.env", "../x:python", "docker", "Docker:python", "docker:py/thon"):
        with pytest.raises(ValueError):
            templates.separar(ruim)


def test_zip_e_bloqueio_por_segredo(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    commit = _montar(tmp_path, sistemas)
    chave = cred.criar("qualquer", [], [])
    r = cliente.get("/v1/templates/docker/python.zip", headers=_cab(chave))
    assert r.status_code == 200, r.text
    assert r.headers["x-commit"] == commit and r.headers["x-template"] == "docker:python"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    # pacote.bin: binário fora da lista do  não sai; logo.png sai.
    assert sorted(z.namelist()) == [".dockerignore", ".env.example", "Dockerfile", "docker-compose.yml",
                                    "logo.png", "scripts/entrar.sh"]
    assert z.read("Dockerfile") == DOCKERFILE and z.read("docker-compose.yml") == COMPOSE  # ${VAR} não é segredo
    assert (z.getinfo("scripts/entrar.sh").external_attr >> 16) & 0o111
    r = cliente.get("/v1/templates/docker/laravel.zip", headers=_cab(chave))
    assert r.status_code == 409 and "docker-compose.yml" in r.json()["detail"]
    assert cliente.get("/v1/templates/docker/python.zip").status_code == 401


def test_template_ignorado_na_arvore_nao_sai(tela, tmp_path):  # noqa: F811
    cliente, sistemas, cred = tela
    _montar(tmp_path, sistemas, leituras=[{"perfil": "referencia", "incluir": ["python/*"], "excluir": []}])
    chave = cred.criar("qualquer", [], [])
    assert [t["id"] for t in cliente.get("/v1/templates", headers=_cab(chave)).json()["templates"]] == ["docker:python"]
    assert cliente.get("/v1/templates/docker/laravel.zip", headers=_cab(chave)).status_code == 404


def test_cli_servida(tela):  # noqa: F811
    cliente, _, _ = tela
    r = cliente.get("/v1/cli/vs")
    assert r.status_code == 200 and r.content == (RAIZ / "cli/vs.py").read_bytes()
    assert cliente.get("/v1/cli").json()["versao"] == _pv().VERSAO


# --- CLI ------------------------------------------------------------------------------

def _pv():
    spec = importlib.util.spec_from_file_location("vs", RAIZ / "cli/vs.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def cli_vs(tela, tmp_path, monkeypatch):  # noqa: F811
    """A CLI falando com a API do teste (TestClient no lugar do urllib)."""
    cliente, sistemas, cred = tela
    _montar(tmp_path, sistemas)
    m = _pv()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("VS_TOKEN", raising=False)
    monkeypatch.setenv("VS_URL", "http://hub.teste")  # o pedir abaixo responde no lugar do hub

    def pedir(caminho, chave=None, url=None, bruto=False):
        r = cliente.get(caminho, headers=_cab(chave) if chave else {})
        if r.status_code == 401:
            raise m.Erro("token inválido ou revogado: rode vs login")
        if r.status_code >= 400:
            raise m.Erro(f"{r.json().get('detail')} (HTTP {r.status_code})")
        return (r.content, r.headers) if bruto else r.json()

    monkeypatch.setattr(m, "pedir", pedir)
    monkeypatch.setattr(m.getpass, "getpass", lambda _: cred.criar("cli", [], []))
    return m


def test_cli_login_e_add_template(cli_vs, tmp_path, monkeypatch, capsys):
    assert cli_vs.main(["list", "templates"]) == 1 and "vs login" in capsys.readouterr().err
    assert cli_vs.main(["login"]) == 0
    config = pathlib.Path(cli_vs.arquivo_config())
    assert stat.S_IMODE(config.stat().st_mode) == 0o600 and json.loads(config.read_text())["token"].startswith("vs_")
    capsys.readouterr()
    assert cli_vs.main(["list", "templates", "type=docker"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert "docker:python" in linhas[1] and "bloqueado" in linhas[0] and "bloqueado" not in linhas[1]

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    monkeypatch.chdir(projeto)
    assert cli_vs.main(["add", "template", "docker:python", "--dry-run"]) == 0
    assert "Nada foi escrito" in capsys.readouterr().out and list(projeto.iterdir()) == []

    assert cli_vs.main(["add", "template", "docker:python"]) == 0
    assert (projeto / "Dockerfile").read_bytes() == DOCKERFILE
    assert os.access(projeto / "scripts/entrar.sh", os.X_OK)
    reg = json.loads((projeto / ".vaultsystem/templates.json").read_text())["templates"]
    assert [t["id"] for t in reg] == ["docker:python"] and len(reg[0]["commit"]) == 40

    # De novo, sem mudança: arquivo igual ao do template não é conflito.
    assert cli_vs.main(["add", "template", "docker:python"]) == 0 and "= Dockerfile" in capsys.readouterr().out
    # Conflito: nada é escrito sem --force.
    (projeto / "Dockerfile").write_text("meu\n")
    capsys.readouterr()
    assert cli_vs.main(["add", "template", "docker:python"]) == 1
    erro = capsys.readouterr().err
    assert "Dockerfile" in erro and "--force" in erro and (projeto / "Dockerfile").read_text() == "meu\n"
    assert cli_vs.main(["add", "template", "docker:python", "--force"]) == 0
    assert (projeto / "Dockerfile").read_bytes() == DOCKERFILE

    # Outra pasta, e o template com segredo.
    assert cli_vs.main(["add", "template", "docker:python", "dir=infra"]) == 0 and (projeto / "infra/Dockerfile").exists()
    assert cli_vs.main(["add", "template", "docker:laravel"]) == 1 and "segredo" in capsys.readouterr().err
    assert cli_vs.main(["add", "template", "python"]) == 1


def test_cli_recusa_caminho_para_fora(cli_vs):
    for ruim in ("../x", "/etc/x", "a/../../x", "C:/x", "a\\b"):
        with pytest.raises(cli_vs.Erro):
            cli_vs._seguro(ruim)
    assert cli_vs._seguro("a/b.txt") == "a/b.txt"
