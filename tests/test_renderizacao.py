"""Aba Renderização: página do vault de Referência montada com tudo embutido."""
import base64
import json
import os
import subprocess

from test_painel import entrar, tela  # noqa: F401 - fixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
FONTE = b"OTTO" + b"\x01" * 32

HTML = """<!doctype html><html><head>
<link rel="stylesheet" href="../tokens/tokens.css">
<link rel="icon" href="../assets/Logo-P.png">
<style>@font-face{font-family:Branding;src:url('../assets/fonts/Branding Bold.otf')}</style>
</head><body>
<img src="../assets/Logo-P.png" alt="">
<img src="https://exemplo.com/x.png" alt="">
<img src="../assets/nao-existe.png" alt="">
<script src="app.js"></script>
<script>const s = '</scr' + 'ipt>';</script>
</body></html>"""


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


def _montar(tmp_path, sistemas):
    from vault_system import estado, ingestao, literal
    arquivos = {"vitrine/index.html": HTML.encode(), "tokens/tokens.css": b":root{--primary:#258D43}\n@import 'extra.css';",
                "tokens/extra.css": b".x{background:url(../assets/Logo-P.png)}", "vitrine/app.js": b"var a = '</script>';",
                "assets/Logo-P.png": PNG, "assets/fonts/Branding Bold.otf": FONTE}
    trabalho = tmp_path / "trabalho"
    for c, b in arquivos.items():
        (trabalho / c).parent.mkdir(parents=True, exist_ok=True)
        (trabalho / c).write_bytes(b)
    _git("init", "-q", "-b", "main", cwd=trabalho)
    _git("add", ".", cwd=trabalho)
    _git("commit", "-q", "-m", "x", cwd=trabalho)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=trabalho, capture_output=True, text=True).stdout.strip()
    sistemas.criar({"tag": "ds", "origens": [{"nome": "principal", "ramo": "main", "repo": "https://github.com/O/ds",
                                              "leituras": [{"perfil": "referencia", "incluir": [], "excluir": []}]}]}, "x")
    clone = ingestao.dir_clone("ds", "principal")
    os.makedirs(os.path.dirname(clone), exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(trabalho), clone], check=True)
    db = estado.conectar()
    with db:
        for c, b in arquivos.items():
            if c.startswith("assets/"):
                continue  # binário não vira nota
            db.execute("INSERT INTO notas_indice (tag, chave, pasta, titulo, tipo_nota, origens, commit_origem, conteudo) "
                       "VALUES ('ds', ?, 'referencia', ?, 'referencia', ?, ?, ?)",
                       (f"sistemas/ds/referencia/{c}", c.split("/")[-1], json.dumps([c]), commit,
                        "---\ntipo_nota: referencia\n---\n" + literal.corpo_de(c, b.decode())))
    return commit


def test_pagina_com_tudo_embutido(tela, tmp_path):  # noqa: F811
    cliente, sistemas, _ = tela
    _montar(tmp_path, sistemas)
    entrar(cliente)
    r = cliente.get("/v1/painel/sistemas/ds/renderizar", params={"pagina": "referencia/vitrine/index.html"})
    assert r.status_code == 200, r.text
    d = r.json()
    h = d["html"]
    png = "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert '<style data-arquivo="tokens/tokens.css">' in h and "--primary:#258D43" in h
    assert "../tokens/tokens.css" not in h
    assert ".x{background:url(\"" + png + "\")}" in h  # @import embutido, com o url() relativo a ele
    assert 'href="' + png + '"' in h and 'src="' + png + '"' in h
    assert "data:font/otf;base64," + base64.b64encode(FONTE).decode() in h
    assert '<script data-arquivo="vitrine/app.js">' in h and "var a = '<\\/script>';" in h
    assert 'src="https://exemplo.com/x.png"' in h  # externo fica como está
    assert any("nao-existe.png" in a and "não está no commit" in a for a in d["avisos"])
    assert set(d["usados"]) >= {"tokens/tokens.css", "tokens/extra.css", "assets/Logo-P.png", "vitrine/app.js"}


def test_extras_e_erros(tela, tmp_path):  # noqa: F811
    cliente, sistemas, _ = tela
    _montar(tmp_path, sistemas)
    entrar(cliente)
    url = "/v1/painel/sistemas/ds/renderizar"
    r = cliente.get(url, params={"pagina": "referencia/vitrine/index.html", "extra": ["referencia/tokens/extra.css"]})
    h = r.json()["html"]
    assert h.index('<style data-arquivo="tokens/extra.css">') < h.index("</head>")
    assert cliente.get(url, params={"pagina": "referencia/tokens/tokens.css"}).status_code == 422  # não é HTML
    assert cliente.get(url, params={"pagina": "referencia/nada.html"}).status_code == 422
    r = cliente.get(url, params={"pagina": "referencia/vitrine/index.html", "extra": ["referencia/vitrine/index.html"]})
    assert r.status_code == 422
    assert cliente.get("/v1/painel/sistemas/outro/renderizar", params={"pagina": "x"}).status_code == 404


def test_caminho_que_sai_da_origem_vira_aviso():
    from app import renderizacao
    m = renderizacao.Montador.__new__(renderizacao.Montador)
    m.avisos, m.usados, m._datas, m.total, m.origens = [], [], {}, 0, {}
    assert m.resolver(("principal", "a/b.html"), "https://x/y.png") is None
    assert m.resolver(("principal", "a/b.html"), "../c/d%20e.png?v=1") == ("principal", "c/d e.png")
    assert m.data_uri(("principal", "a/b.html"), "../../fora.png", "abc1234") is None
    assert m.avisos == ["a/b.html: ../../fora.png: sai da origem"]
