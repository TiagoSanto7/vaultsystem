"""Consulta ao conhecimento: busca e leitura por HTTP e MCP, presas à tag da credencial."""
import json

from vault_system import busca, estado
from test_api import api, cab  # noqa: F401 - fixture

A, B = "sistemas/sis-a", "sistemas/sis-b"


def nota(chave, corpo, origens=()):
    return (chave.split("/")[1], chave, chave.split("/")[2], corpo.split("\n", 1)[0].removeprefix("# "),
            json.dumps(list(origens)), f"---\norigens: {json.dumps(list(origens))}\n---\n{corpo}")


NOTAS = [
    nota(f"{A}/regras/limite-de-credito", "# Limite de crédito\n\nO pedido acima do limite vai para aprovação. "
         f"Ver [[{A}/modulos/pedido_service|o serviço de pedidos]].", ["app/pedido_service.py"]),
    nota(f"{A}/modulos/pedido_service", "# Serviço de pedidos\n\nA função calcular_total soma os itens.",
         ["app/pedido_service.py", "api:src/total.ts"]),
    nota(f"{A}/indices/regras", f"# Regras\n\n[[{A}/regras/limite-de-credito]] crédito crédito"),
    nota(f"{B}/regras/segredo-do-b", "# Segredo do B\n\nLimite de crédito do sistema B, que A não pode ver."),
]


def preparar(cred):
    with estado.conectar() as db:
        db.executemany("INSERT INTO notas_indice (tag, chave, pasta, titulo, origens, conteudo) VALUES (?, ?, ?, ?, ?, ?)",
                       NOTAS)
        for nome, repo in (("principal", "git@github.com:O/a.git"), ("api", "https://github.com/O/a-api")):
            db.execute("INSERT INTO origens (tag, nome, repo, ramo, leituras, commit_processado, criado_em) "
                       "VALUES ('sis-a', ?, ?, 'main', '[]', ?, 'x')", (nome, repo, f"c-{nome}"))
    return cred.criar("leitor-a", ["sis-a"], []), cred.criar("leitor-b", ["sis-b"], [])


def procurar(cliente, chave, **corpo):
    return cliente.post("/v1/knowledge/search", json={"system_id": "sis-a", **corpo}, headers=cab(chave))


def test_busca_por_http(api):  # noqa: F811
    cliente, cred = api
    a, b = preparar(cred)
    r = procurar(cliente, a, query="limite de crédito")
    assert r.status_code == 200
    res = r.json()
    # A tag A não vê nada da B, e o índice gerado (indices/) fica de fora.
    assert [x["note_id"] for x in res["results"]][0] == f"{A}/regras/limite-de-credito"
    assert all(x["note_id"].startswith(f"{A}/") and "/indices/" not in x["note_id"] for x in res["results"])
    primeira = res["results"][0]
    assert primeira["verification"] == "unverified" and "aprovação" in primeira["excerpt"]
    assert "[[" not in primeira["excerpt"]
    assert primeira["provenance"] == [{"repository": "https://github.com/O/a", "path": "app/pedido_service.py",
                                       "branch": "main", "commit": "c-principal",
                                       "url": "https://github.com/O/a/blob/c-principal/app/pedido_service.py"}]
    # Termo exato (nome de função) e acento: "credito" acha "crédito".
    assert procurar(cliente, a, query="calcular_total").json()["results"][0]["note_id"] == f"{A}/modulos/pedido_service"
    assert procurar(cliente, a, query="credito").json()["results"]
    # Pedir a tag B com a credencial A: 403, sem conteúdo.
    r = cliente.post("/v1/knowledge/search", json={"system_id": "sis-b", "query": "crédito"}, headers=cab(a))
    assert r.status_code == 403 and "Segredo" not in r.text
    assert cliente.post("/v1/knowledge/search", json={"system_id": "sis-a", "query": "x"}).status_code == 401
    # verified: nenhuma nota é verificada antes da .
    assert procurar(cliente, a, query="crédito", verification="verified").json()["results"] == []
    assert procurar(cliente, a, query="nada-disso-existe").json() == {"system_id": "sis-a", "results": [], "has_more": False}
    r = procurar(cliente, a, query="pedido", limit=1).json()
    assert len(r["results"]) == 1 and r["has_more"] is True


def test_busca_valida_o_corpo(api):  # noqa: F811
    cliente, cred = api
    a, _ = preparar(cred)
    for ruim in ({"query": "   "}, {"query": "x" * 501}, {"query": "x", "limit": 21}, {"query": "x", "limit": 0},
                 {"query": "x", "verification": "talvez"}, {"query": "x", "tags": ["a"]}):
        assert procurar(cliente, a, **ruim).status_code == 400, ruim
    # Sintaxe do FTS5 no texto não quebra a consulta: vira palavra comum.
    for texto in ('"aspas', "limite*", "NEAR(a b)", "a AND OR NOT", "col:limite", "-", "???"):
        assert procurar(cliente, a, query=texto).status_code == 200, texto


def test_indice_acompanha_a_rodada(api):  # noqa: F811
    cliente, cred = api
    a, _ = preparar(cred)
    assert procurar(cliente, a, query="marmita").json()["results"] == []
    # O curador apaga e reinsere as notas da tag a cada rodada.
    with estado.conectar() as db:
        db.execute("DELETE FROM notas_indice WHERE tag = 'sis-a'")
        db.execute("INSERT INTO notas_indice (tag, chave, pasta, titulo, conteudo) VALUES (?, ?, ?, ?, ?)",
                   ("sis-a", f"{A}/regras/marmita", "regras", "Marmita", "# Marmita\n\nRetirada de marmita."))
    assert [x["note_id"] for x in procurar(cliente, a, query="marmita").json()["results"]] == [f"{A}/regras/marmita"]
    assert procurar(cliente, a, query="crédito").json()["results"] == []
    with estado.conectar() as db, busca.conectar() as db_busca:
        assert busca.atualizar(db, db_busca, "sis-a") is False  # sem mudança, não refaz


def test_ler_nota(api):  # noqa: F811
    cliente, cred = api
    a, b = preparar(cred)
    r = cliente.get(f"/v1/notas/{A}/modulos/pedido_service.md", headers=cab(a))
    assert r.status_code == 200
    n = r.json()
    assert n["title"] == "Serviço de pedidos" and n["content"].startswith("# Serviço de pedidos")
    assert [p["commit"] for p in n["provenance"]] == ["c-principal", "c-api"]  # duas origens: o commit de cada uma
    assert cliente.get(f"/v1/notas/{B}/regras/segredo-do-b", headers=cab(a)).status_code == 403
    assert cliente.get(f"/v1/notas/{B}/regras/segredo-do-b", headers=cab(b)).status_code == 200
    assert cliente.get(f"/v1/notas/{A}/regras/nao-existe", headers=cab(a)).status_code == 404
    assert cliente.get("/v1/notas/qualquer/coisa", headers=cab(a)).status_code == 400
    assert cliente.get(f"/v1/notas/{A}/regras/limite-de-credito").status_code == 401


def rpc(cliente, chave, metodo, params=None, id_=1):
    msg = {"jsonrpc": "2.0", "method": metodo, **({"params": params} if params is not None else {})}
    if id_ is not None:
        msg["id"] = id_
    return cliente.post("/mcp", json=msg, headers=cab(chave) if chave else {})


def chamar(cliente, chave, nome, **args):
    return rpc(cliente, chave, "tools/call", {"name": nome, "arguments": args}).json()["result"]


def test_mcp(api):  # noqa: F811
    cliente, cred = api
    a, _ = preparar(cred)
    assert rpc(cliente, None, "initialize").status_code == 401
    r = rpc(cliente, a, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "teste", "version": "1"}}).json()["result"]
    assert r["protocolVersion"] == "2025-06-18" and "tools" in r["capabilities"]
    assert rpc(cliente, a, "initialize", {"protocolVersion": "1999-01-01"}).json()["result"]["protocolVersion"] == "2025-11-25"
    assert rpc(cliente, a, "notifications/initialized", id_=None).status_code == 202
    nomes = [f["name"] for f in rpc(cliente, a, "tools/list").json()["result"]["tools"]]
    assert nomes == ["list_systems", "search_knowledge", "read_note", "list_files", "get_file"]  # arquivos: 
    assert chamar(cliente, a, "list_systems")["structuredContent"] == {"systems": [{"system_id": "sis-a", "notes": 2}]}
    r = chamar(cliente, a, "search_knowledge", system_id="sis-a", query="calcular_total")
    assert r["isError"] is False and r["structuredContent"]["results"][0]["note_id"] == f"{A}/modulos/pedido_service"
    assert json.loads(r["content"][0]["text"]) == r["structuredContent"]
    r = chamar(cliente, a, "read_note", note_id=f"{A}/regras/limite-de-credito")
    assert "aprovação" in r["structuredContent"]["content"]
    # Tag B pedida com a credencial A: erro da ferramenta, sem conteúdo do B.
    for nome, args in (("search_knowledge", {"system_id": "sis-b", "query": "crédito"}),
                       ("read_note", {"note_id": f"{B}/regras/segredo-do-b"})):
        r = chamar(cliente, a, nome, **args)
        assert r["isError"] is True and "Segredo" not in json.dumps(r) and "structuredContent" not in r
    assert chamar(cliente, a, "search_knowledge", system_id="sis-a", query="x", limit=99)["isError"] is True
    assert rpc(cliente, a, "tools/call", {"name": "apagar_tudo"}).json()["error"]["code"] == -32602
    assert rpc(cliente, a, "resources/list").json()["error"]["code"] == -32601
    assert cliente.get("/mcp", headers=cab(a)).status_code == 405
