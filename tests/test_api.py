"""Testes da API: a tag é garantida no código."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("ESTADO_DIR", str(tmp_path))
    from app import credenciais, main, sistemas
    importlib.reload(credenciais)
    importlib.reload(sistemas)
    importlib.reload(main)
    return TestClient(main.app), credenciais


def cab(chave):
    return {"Authorization": f"Bearer {chave}"}


def test_saude(api):
    cliente, _ = api
    assert cliente.get("/saude").json() == {"ok": True}


def test_sem_credencial_ou_invalida(api):
    cliente, _ = api
    assert cliente.get("/v1/sistemas/a/acesso").status_code == 401
    assert cliente.get("/v1/sistemas/a/acesso", headers=cab("vs_inventada")).status_code == 401


def test_tag_presa_a_credencial(api):
    cliente, cred = api
    chave = cred.criar("cliente-a", ["sistema-a"], ["sistema-a"])
    so_leitura = cred.criar("leitor", ["sistema-a", "sistema-b"], [])
    assert cliente.get("/v1/sistemas/sistema-a/acesso", headers=cab(chave)).status_code == 200
    assert cliente.get("/v1/sistemas/sistema-b/acesso", headers=cab(chave)).status_code == 403
    assert cliente.get("/v1/sistemas/sistema-a/acesso?modo=escrever", headers=cab(chave)).status_code == 200
    assert cliente.get("/v1/sistemas/sistema-b/acesso", headers=cab(so_leitura)).status_code == 200
    assert cliente.get("/v1/sistemas/sistema-a/acesso?modo=escrever", headers=cab(so_leitura)).status_code == 403


def test_tag_invalida(api):
    cliente, cred = api
    chave = cred.criar("c", ["a"], [])
    assert cliente.get("/v1/sistemas/A_B/acesso", headers=cab(chave)).status_code == 400
    with pytest.raises(ValueError):
        cred.criar("d", ["Com Espaço"], [])


def test_revogada_e_hash(api, tmp_path):
    cliente, cred = api
    chave = cred.criar("c", ["a"], [])
    assert chave not in (tmp_path / "estado.db").read_bytes().decode("latin-1")
    cred.revogar("c")
    assert cliente.get("/v1/sistemas/a/acesso", headers=cab(chave)).status_code == 401


def test_ultimo_uso_respeita_um_minuto_com_data_antiga(api, monkeypatch):
    cliente, cred = api
    chave = cred.criar("leitor", ["a"], [])
    usado_em = "2026-11-10T20:00:00-04:00"
    with cred.conectar() as db:
        db.execute("UPDATE credenciais SET usado_em = ? WHERE nome = 'leitor'", (usado_em,))

    monkeypatch.setattr(cred, "agora", lambda: "2026-11-11T00:01:00+00:00")
    assert cliente.get("/v1/sistemas/a/acesso", headers=cab(chave)).status_code == 200
    assert cred.listar()[0]["usado_em"] == usado_em

    monkeypatch.setattr(cred, "agora", lambda: "2026-11-11T00:01:01+00:00")
    assert cliente.get("/v1/sistemas/a/acesso", headers=cab(chave)).status_code == 200
    assert cred.listar()[0]["usado_em"] == "2026-11-11T00:01:01+00:00"


CADASTRO = {"tag": "sistema-a", "perfil": "documentos", "repo": "git@github.com:minha-org/origem.git"}


def test_cadastro_e_pull_exigem_tag_na_escrita(api):
    cliente, cred = api
    escritor = cred.criar("escritor", ["sistema-a"], ["sistema-a"])
    leitor = cred.criar("leitor", ["sistema-a"], [])
    outro = cred.criar("outro", ["sistema-b"], ["sistema-b"])
    for chave in (leitor, outro):
        assert cliente.post("/v1/sistemas", json=CADASTRO, headers=cab(chave)).status_code == 403
        assert cliente.post("/v1/sistemas/sistema-a/pull", headers=cab(chave)).status_code == 403
    assert cliente.post("/v1/sistemas", json=CADASTRO).status_code == 401
    r = cliente.post("/v1/sistemas", json=CADASTRO, headers=cab(escritor))
    assert r.status_code == 201 and r.json()["origens"][0]["ramo"] == "main" and r.json()["origens"][0]["commit_processado"] is None
    assert cliente.post("/v1/sistemas", json=CADASTRO, headers=cab(escritor)).status_code == 409
    r = cliente.post("/v1/sistemas/sistema-a/pull", headers=cab(escritor))
    assert r.status_code == 202
    p = cliente.get(f"/v1/sistemas/sistema-a/pulls/{r.json()['pedido']}", headers=cab(leitor))
    assert p.status_code == 200 and p.json()["estado"] == "pedido"
    assert cliente.get("/v1/sistemas/sistema-a", headers=cab(outro)).status_code == 403
    assert cliente.get("/v1/sistemas/sistema-a/fila", headers=cab(leitor)).json() == []
    assert cliente.post("/v1/sistemas/sistema-b/pull", headers=cab(outro)).status_code == 404


def test_cadastro_invalido(api):
    cliente, cred = api
    chave = cred.criar("e", [], ["sistema-a"])
    for ruim in ({"repo": "https://user:token@github.com/x/y.git"}, {"repo": "/etc"}, {"repo": "file:///etc"},
                 {"perfil": "Código"}, {"ramo": "../x"}, {"incluir": [""]}):
        r = cliente.post("/v1/sistemas", json={**CADASTRO, **ruim}, headers=cab(chave))
        assert r.status_code in (400, 422), ruim


def test_remover_sistema(api):
    cliente, cred = api
    escritor = cred.criar("escritor", ["sistema-a"], ["sistema-a"])
    leitor = cred.criar("leitor", ["sistema-a"], [])
    cliente.post("/v1/sistemas", json=CADASTRO, headers=cab(escritor))
    assert cliente.delete("/v1/sistemas/sistema-a", headers=cab(leitor)).status_code == 403
    assert cliente.delete("/v1/sistemas/sistema-b", headers=cab(escritor)).status_code == 403
    assert cliente.delete("/v1/sistemas/sistema-a", headers=cab(escritor)).status_code == 202
    assert cliente.get("/v1/sistemas/sistema-a", headers=cab(leitor)).json()["removido_em"]
    assert cliente.post("/v1/sistemas/sistema-a/pull", headers=cab(escritor)).status_code == 409


def test_cadastro_com_varias_origens(api):
    cliente, cred = api
    chave = cred.criar("e", ["obs"], ["obs"])
    corpo = {"tag": "obs", "origens": [{"repo": "git@github.com:minha-org/obs.git", "leituras": [
        {"perfil": "documentos", "incluir": ["docs/*"]}, {"perfil": "codigo", "excluir": ["tests/*"]}]}]}
    r = cliente.post("/v1/sistemas", json=corpo, headers=cab(chave))
    assert r.status_code == 201
    o = r.json()["origens"]
    assert o[0]["nome"] == "principal" and [l["perfil"] for l in o[0]["leituras"]] == ["documentos", "codigo"]
    extra = {"nome": "manual", "repo": "git@github.com:minha-org/obs-docs.git",
             "leituras": [{"perfil": "documentos"}]}
    r = cliente.post("/v1/sistemas/obs/origens", json=extra, headers=cab(chave))
    assert r.status_code == 201 and [x["nome"] for x in r.json()["origens"]] == ["principal", "manual"]
    assert cliente.post("/v1/sistemas/obs/origens", json=extra, headers=cab(chave)).status_code == 409
    leitor = cred.criar("l", ["obs"], [])
    assert cliente.post("/v1/sistemas/obs/origens", json=extra, headers=cab(leitor)).status_code == 403
    ruim = {**corpo, "tag": "obs", "origens": [{**corpo["origens"][0], "nome": "A B"}]}
    assert cliente.post("/v1/sistemas", json={**ruim, "tag": "obs2"}, headers=cab(cred.criar("x", [], ["obs2"]))).status_code == 400
