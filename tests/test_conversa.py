import io
import zipfile

from test_painel import entrar, tela  # noqa: F401

CHAVE = "sk-ant-api03-" + "x" * 40


def _zip(arquivos):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in arquivos.items():
            z.writestr(n, d)
    return b.getvalue()


def test_conversa_com_o_vault_i(tela, tmp_path, monkeypatch):
    from vault_system import busca, conversa, estado, vault_i

    cliente, _, _ = tela
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    assert entrar(cliente).status_code == 200
    # sem Vault-I configurado, não abre conversa
    assert cliente.get("/v1/painel/conversas").json() == {"disponivel": False, "conversas": []}
    r = cliente.post("/v1/painel/conversas", json={"escopo": "hub", "pergunta": "oi"})
    assert r.status_code == 409 and "Configurações" in r.json()["detail"]
    assert cliente.put("/v1/painel/vault-i", json={"provedor": "anthropic", "chave": CHAVE}).status_code == 200
    assert cliente.post("/v1/painel/envios/estudos?modo=documentado", content=_zip({"a.md": "# A\n"})).status_code == 201

    assert cliente.post("/v1/painel/conversas", json={"escopo": "vault", "tag": "nao-existe", "pergunta": "x"}).status_code == 404
    assert cliente.post("/v1/painel/conversas", json={"escopo": "hub", "pergunta": "  "}).status_code == 400
    r = cliente.post("/v1/painel/conversas", json={"escopo": "vault", "tag": "estudos",
                                                   "nota": "sistemas/estudos/conceitos/vetor", "pergunta": "O que é um vetor?"})
    assert r.status_code == 201, r.text
    c = r.json()
    cid = c["conversa"]["id"]
    assert c["conversa"]["titulo"] == "O que é um vetor?" and c["mensagens"][0]["estado"] == "pendente"
    # uma pergunta por vez
    assert cliente.post(f"/v1/painel/conversas/{cid}/mensagens", json={"pergunta": "e mais?"}).status_code == 409

    pedidos = []
    monkeypatch.setattr(busca, "buscar", lambda tag, texto, limite=5, verificacao="all": {"results": [
        {"note_id": "sistemas/estudos/regras/equipolentes", "title": "Vetores equipolentes", "excerpt": "mesmo módulo"}]})
    notas = {"sistemas/estudos/conceitos/vetor": "Um vetor é um segmento orientado.",
             "sistemas/estudos/regras/equipolentes": "Mesmo módulo, direção e sentido."}
    monkeypatch.setattr(busca, "ler", lambda tag, chave: {"title": chave.rsplit("/", 1)[-1], "content": notas[chave]})
    monkeypatch.setattr(vault_i, "responder", lambda config, sistema, pedido: pedidos.append(pedido) or "Um vetor é [vetor].")
    with estado.conectar() as db:
        assert conversa.responder_uma(db) is True
        assert conversa.responder_uma(db) is False
    assert "segmento orientado" in pedidos[0] and "Mesmo módulo" in pedidos[0] and "O que é um vetor?" in pedidos[0]
    m = cliente.get(f"/v1/painel/conversas/{cid}").json()["mensagens"]
    assert [x["papel"] for x in m] == ["usuario", "vault-i"] and m[0]["estado"] == "ok"
    assert m[1]["texto"] == "Um vetor é [vetor]." and m[1]["modelo"].startswith("anthropic:")
    assert [f["chave"] for f in m[1]["fontes"]] == ["sistemas/estudos/conceitos/vetor", "sistemas/estudos/regras/equipolentes"]

    # segunda pergunta leva a conversa até aqui; erro do modelo vai para a mensagem
    assert cliente.post(f"/v1/painel/conversas/{cid}/mensagens", json={"pergunta": "E equipolentes?"}).status_code == 201

    def falha(config, sistema, pedido):
        pedidos.append(pedido)
        raise RuntimeError("token recusado")
    monkeypatch.setattr(vault_i, "responder", falha)
    with estado.conectar() as db:
        conversa.responder_uma(db)
    assert "Vault-I: Um vetor é [vetor]." in pedidos[1]
    m = cliente.get(f"/v1/painel/conversas/{cid}").json()["mensagens"]
    assert m[-1]["estado"] == "erro" and m[-1]["erro"] == "token recusado"

    # conversa geral não busca notas; cada conversa é de quem criou
    monkeypatch.setattr(busca, "buscar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não busca")))
    monkeypatch.setattr(vault_i, "responder", lambda config, sistema, pedido: "Oi!")
    g = cliente.post("/v1/painel/conversas", json={"escopo": "geral", "tag": "estudos", "pergunta": "Oi"}).json()
    assert g["conversa"]["tag"] is None
    with estado.conectar() as db:
        conversa.responder_uma(db)
    lista = cliente.get("/v1/painel/conversas").json()
    assert lista["disponivel"] is True and [c["id"] for c in lista["conversas"]] == [g["conversa"]["id"], cid]
    assert cliente.delete(f"/v1/painel/conversas/{cid}").status_code == 204
    assert cliente.get(f"/v1/painel/conversas/{cid}").status_code == 404


def test_datas_antigas_na_ordem_das_conversas_e_no_prazo(tmp_path, monkeypatch):
    from vault_system import conversa, estado

    monkeypatch.setenv("ESTADO_DIR", str(tmp_path))
    monkeypatch.setattr(estado, "agora", lambda: "2026-11-11T00:20:00+00:00")
    datas = [("Mais recente", "2026-11-10T20:00:00-04:00"), ("Mais antiga", "2026-11-10T23:59:00+00:00")]
    with estado.conectar() as db:
        for titulo, inicio in datas:
            cid = db.execute(
                "INSERT INTO conversas (escopo, titulo, criado_por, criado_em) VALUES ('geral', ?, 'ana', ?)",
                (titulo, inicio),
            ).lastrowid
            db.execute(
                "INSERT INTO mensagens (conversa_id, papel, texto, estado, criado_em, inicio) "
                "VALUES (?, 'usuario', ?, 'respondendo', ?, ?)",
                (cid, titulo, inicio, inicio),
            )

        assert [c["titulo"] for c in conversa.listar(db, "ana")] == ["Mais recente", "Mais antiga"]
        assert conversa.responder_uma(db) is False
        assert [tuple(m) for m in db.execute("SELECT texto, estado FROM mensagens ORDER BY id")] == [
            ("Mais recente", "respondendo"), ("Mais antiga", "erro"),
        ]
