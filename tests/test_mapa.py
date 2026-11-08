"""Mapa de relações: só o que está no índice das notas."""
import json

from vault_system import estado, mapa
from test_painel import entrar, tela  # noqa: F401 - fixture

T = "sistemas/r"
ORIGENS = [{"nome": "principal", "repo": "https://github.com/O/r"}, {"nome": "api", "repo": "git@github.com:O/api.git"}]


def nota(chave, corpo="", **cab):
    linhas = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in cab.items())
    pasta = chave.split("/")[2]
    return {"chave": chave, "pasta": pasta, "titulo": chave.rsplit("/", 1)[-1],
            "conteudo": f"---\n{linhas}\n---\n# {chave.rsplit('/', 1)[-1]}\n\n{corpo}"}


NOTAS = [
    nota(f"{T}/documentos/spec", f"Ver [[{T}/assuntos/pedidos]] e [[{T}/regras/limite]].", origens=["docs/spec.md"]),
    nota(f"{T}/assuntos/pedidos", f"Assunto. Cita [[{T}/documentos/spec|a spec]].", origens=["docs/spec.md"],
         evidencias=[f"[[{T}/documentos/spec]]"]),
    nota(f"{T}/regras/limite", f"Usa [[{T}/modulos/app]]. Link quebrado: [[{T}/regras/nao-existe]].",
         origens=["app/regra.py", "api:src/limite.ts"]),
    nota(f"{T}/modulos/app", f"Aplica [[{T}/regras/limite]].", origens=["app/__init__.py"]),
    nota(f"{T}/indices/codigo", f"[[{T}/modulos/app]] [[{T}/regras/limite]]"),
]


def grafo():
    return mapa.Grafo("r", ORIGENS, NOTAS)


def test_relacoes_saem_so_do_indice():
    g = grafo()
    # documenta: o documento nas evidências do assunto; o link mútuo não vira menciona.
    assert g.arestas[(f"{T}/documentos/spec", f"{T}/assuntos/pedidos")] == "documenta"
    assert (f"{T}/assuntos/pedidos", f"{T}/documentos/spec") not in g.arestas
    assert g.arestas[(f"{T}/documentos/spec", f"{T}/regras/limite")] == "menciona"
    # Link quebrado e índice gerado ficam de fora.
    assert all("nao-existe" not in b and "indices" not in a + b for a, b in g.arestas)
    assert g.totais() == {"notas": 4, "pastas": {"documentos": 1, "assuntos": 1, "modulos": 1, "regras": 1},
                          "relacoes": {"fundamenta": 5, "documenta": 1, "menciona": 3}}


def test_vizinhanca_de_cada_tipo_de_no():
    g = grafo()
    v = g.vizinhanca("sistema")
    assert [n["id"] for n in v["nos"]] == ["origem:principal", "origem:api", "pasta:documentos", "pasta:assuntos",
                                           "pasta:modulos", "pasta:regras"]
    assert v["nos"][1]["rotulo"] == "O/api"
    v = g.vizinhanca("origem:api")
    assert {(a["de"], a["para"], a["relacao"], a.get("n")) for a in v["arestas"]} == {
        ("origem:api", "sistema", "compõe", None), ("origem:api", "pasta:regras", "fundamenta", 1)}
    v = g.vizinhanca(f"nota:{T}/regras/limite")
    rel = {(r["chave"], r["relacao"], r["sentido"]) for r in v["relacoes"]}
    assert rel == {(f"{T}/modulos/app", "menciona", "ambos"), (f"{T}/documentos/spec", "menciona", "entra")}
    assert v["arquivos"] == [{"origem": "api", "repo": "O/api", "caminhos": ["src/limite.ts"]},
                             {"origem": "principal", "repo": "O/r", "caminhos": ["app/regra.py"]}]
    lados = {n["id"]: n["lado"] for n in v["nos"]}
    assert lados[f"nota:{T}/documentos/spec"] == "esquerda" and lados[f"nota:{T}/modulos/app"] == "direita"
    assert g.vizinhanca("nota:nao/existe") is None


def test_limite_e_expansao():
    regras = [nota(f"{T}/regras/r{i:02d}", f"[[{T}/modulos/app]]") for i in range(30)]
    g = mapa.Grafo("r", ORIGENS, NOTAS + regras)
    v = g.vizinhanca("pasta:regras", limite=10)
    assert (v["notas_vizinhas"], v["notas_mostradas"]) == (31, 10)
    assert [n["id"] for n in v["nos"] if n["tipo"] == "nota"][0] == f"nota:{T}/regras/limite"  # a mais ligada primeiro
    v = g.vizinhanca(f"nota:{T}/modulos/app", limite=5)
    assert (v["notas_vizinhas"], v["notas_mostradas"], len(v["relacoes"])) == (31, 5, 31)  # a lista em texto tem todas


def test_mapa_pela_tela(tela):  # noqa: F811
    cliente, sistemas, _ = tela
    sistemas.criar({"tag": "r", "origens": [{"nome": "principal", "ramo": "main", "repo": "https://github.com/O/r",
                                             "leituras": [{"perfil": "codigo", "incluir": [], "excluir": []}]}]}, "x")
    assert cliente.get("/v1/painel/sistemas/r/mapa").status_code == 401
    entrar(cliente)
    with estado.conectar() as db:
        for n in NOTAS:
            db.execute("INSERT INTO notas_indice (tag, chave, pasta, titulo, conteudo) VALUES ('r', ?, ?, ?, ?)",
                       (n["chave"], n["pasta"], n["titulo"], n["conteudo"]))
    r = cliente.get("/v1/painel/sistemas/r/mapa").json()
    # O total do mapa bate com o contador de notas do vault (sem os índices).
    assert r["totais"]["notas"] == cliente.get("/v1/painel/sistemas/r").json()["sinais"]["notas"] == 4
    r = cliente.get("/v1/painel/sistemas/r/mapa", params={"foco": f"nota:{T}/assuntos/pedidos"}).json()
    assert r["relacoes"] == [{"chave": f"{T}/documentos/spec", "titulo": "spec", "pasta": "documentos",
                              "relacao": "documenta", "sentido": "entra"}]
    assert cliente.get("/v1/painel/sistemas/r/mapa", params={"foco": "pasta:nada"}).status_code == 404
    assert cliente.get("/v1/painel/sistemas/x/mapa").status_code == 404


def test_grafo_inteiro(tela):  # noqa: F811
    cliente, sistemas, _ = tela
    sistemas.criar({"tag": "r", "origens": [{"nome": "principal", "ramo": "main", "repo": "https://github.com/O/r",
                                             "leituras": [{"perfil": "codigo", "incluir": [], "excluir": []}]}]}, "x")
    entrar(cliente)
    with estado.conectar() as db:
        for n in NOTAS:
            db.execute("INSERT INTO notas_indice (tag, chave, pasta, titulo, conteudo) VALUES ('r', ?, ?, ?, ?)",
                       (n["chave"], n["pasta"], n["titulo"], n["conteudo"]))
    r = cliente.get("/v1/painel/sistemas/r/mapa/grafo").json()
    assert len(r["nos"]) == r["totais"]["notas"] == 4
    nomes = [n["chave"].rsplit("/", 1)[-1] for n in r["nos"]]
    pares = {(nomes[a], nomes[b], rel) for a, b, rel in r["arestas"]}
    assert pares == {("spec", "pedidos", "documenta"), ("spec", "limite", "menciona"),
                     ("limite", "app", "menciona"), ("app", "limite", "menciona")}
