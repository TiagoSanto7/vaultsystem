"""Reparo de reclassificação: volta ao publicado, sem fila e sem LLM."""
import json

from test_curadoria import amb, git  # noqa: F401 - fixture


def test_desfaz_reclassificacao_e_volta_ao_publicado(amb, capsys):  # noqa: F811
    from vault_system import estado, reparar
    estado.migrar_origens(amb.db)
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras = ? WHERE tag = 'docs'", (json.dumps(
            [{"perfil": "documentos", "incluir": ["docs/*"], "excluir": []},
             {"perfil": "codigo", "incluir": [], "excluir": []}]),))
    amb.commit({"docs/a.md": "manual\n", "src/x.py": "def f(): pass\n"})
    assert amb.rodada() == []
    # O vault publicado: o repositório do vault com um commit (o publicar.sh faz isso no curador).
    git(amb.vault, "init", "-q", "-b", "main")
    git(amb.vault, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(amb.vault, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "publicado")
    publicadas = json.loads((amb.vault / "sistemas/docs/_meta/origem.json").read_text())["origens"][0]["leituras"]
    modulo = (amb.vault / "sistemas/docs/modulos/src.md").read_text()

    # A reclassificação (como a tela faz): tudo para referência + explicação; a ingestão enche a fila.
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras_antes = leituras, leituras = ? WHERE tag = 'docs'", (json.dumps(
            [{"perfil": "referencia-explicada", "incluir": [], "excluir": []}]),))
    amb.ingestao._atender(amb.db, ["docs"])
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE tag = 'docs' AND estado = 'na_fila'").fetchone()[0] > 0
    (amb.vault / "sistemas/docs/modulos/src.md").write_text("estragado pelo meio do lote\n")
    (amb.vault / "sistemas/docs/referencia").mkdir(exist_ok=True)
    (amb.vault / "sistemas/docs/referencia/x.py.md").write_text("cópia não publicada\n")

    # Simulação: mostra e não muda nada.
    reparar.main(["docs"])
    saida = capsys.readouterr().out
    assert "referencia-explicada" in saida and "nada foi mudado" in saida
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE tag = 'docs' AND estado = 'na_fila'").fetchone()[0] > 0

    reparar.main(["docs", "--aplicar"])
    o = amb.db.execute("SELECT leituras, leituras_antes FROM origens WHERE tag = 'docs'").fetchone()
    assert json.loads(o["leituras"]) == publicadas and o["leituras_antes"] is None  # sem reconciliação
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE tag = 'docs' AND estado = 'na_fila'").fetchone()[0] == 0
    assert (amb.vault / "sistemas/docs/modulos/src.md").read_text() == modulo
    assert not (amb.vault / "sistemas/docs/referencia/x.py.md").exists()
    assert git(amb.vault, "status", "--porcelain").strip() == ""
    # Ingestão seguinte não gera nada: as leituras são as que o vault já reflete.
    amb.ingestao._atender(amb.db, ["docs"])
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE tag = 'docs' AND estado = 'na_fila'").fetchone()[0] == 0
