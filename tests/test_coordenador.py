"""Curador em paralelo (DV-606): vaults diferentes ao mesmo tempo, pull na frente, publicação só do que terminou."""
import importlib
import time

from test_curadoria import amb, git, nota  # noqa: F401 - fixture


def _segundo_vault(amb, tmp_path, texto):  # noqa: F811
    origem = tmp_path / "origem-lento"
    origem.mkdir()
    git(origem, "init", "-q", "-b", "main")
    git(origem, "config", "user.name", "t")
    git(origem, "config", "user.email", "t@t")
    (origem / "docs").mkdir()
    (origem / "docs/lento.md").write_text(texto)
    git(origem, "add", "-A")
    git(origem, "commit", "-q", "-m", "c")
    (tmp_path / "chaves" / "lento").write_text("chave falsa")
    with amb.db:
        amb.db.execute("INSERT INTO sistemas (tag, perfil, repo, ramo, incluir, excluir, criado_em, criado_por) "
                       "VALUES ('lento', 'documentos', ?, 'main', '[]', '[]', 'x', 't')", (str(origem),))


def _coordenador(tmp_path, monkeypatch, n):
    monkeypatch.setenv("VAULT_TRABALHO_DIR", str(tmp_path / "trabalho"))
    monkeypatch.setenv("VAULT_TESTE_DEMORA", "6")
    from petro_vault import coordenador
    importlib.reload(coordenador)
    publicados = []
    return coordenador, coordenador.Coordenador(n=n, publicar=lambda tags: publicados.append(sorted(tags))), publicados


def test_lote_lento_nao_segura_o_outro_vault(amb, tmp_path, monkeypatch):  # noqa: F811
    _segundo_vault(amb, tmp_path, "# Lento\n\nDEMORAR\n")
    amb.commit({"docs/rapido.md": "# Rápido\n"})
    _, c, publicados = _coordenador(tmp_path, monkeypatch, n=2)
    c.passo(amb.db)
    assert sorted(r["tag"] for r in c.rodando.values()) == ["docs", "lento"]  # os dois ao mesmo tempo
    fim = time.time() + 60
    while time.time() < fim and any(r["tag"] == "docs" for r in c.rodando.values()):
        time.sleep(0.2)
        c.passo(amb.db)
    assert not any(r["tag"] == "docs" for r in c.rodando.values()), "o vault rápido não terminou"
    assert any(r["tag"] == "lento" for r in c.rodando.values()), "o lento devia ainda estar rodando"
    assert publicados == [["docs"]]  # publica o que terminou, sem esperar (nem incluir) o outro
    assert (amb.vault / "sistemas/docs/documentos/docs/rapido.md").exists()
    c.esperar_todos(amb.db, limite=60)
    assert publicados == [["docs"], ["lento"]]
    assert (amb.vault / "sistemas/lento/documentos/docs/lento.md").exists()
    # Cada trabalhador com a sua pasta de lote e o seu HERMES_HOME; o histórico de cada um à parte.
    assert sorted(p.name for p in (tmp_path / "trabalho").iterdir()) == ["t1", "t2"]
    rodadas = amb.db.execute("SELECT tags, trabalhador, resultado FROM rodadas ORDER BY id").fetchall()
    assert {(r["tags"], r["trabalhador"]) for r in rodadas} == {('["docs"]', "t1"), ('["lento"]', "t2")}
    assert all(r["resultado"] == "concluída" for r in rodadas)


def test_pull_pedido_passa_na_frente_e_vault_em_curso_nao_repete(amb, tmp_path, monkeypatch):  # noqa: F811
    from petro_vault import estado
    _segundo_vault(amb, tmp_path, "# Lento\n")
    coordenador, c, _ = _coordenador(tmp_path, monkeypatch, n=1)
    assert [t for t, _ in c.fila(amb.db)] == ["docs", "lento"]  # agenda, em ordem
    with amb.db:
        amb.db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES ('lento', ?, 't')", (estado.agora(),))
    assert c.fila(amb.db)[0] == ("lento", "pull")
    c.rodando["t1"] = {"tag": "lento", "proc": None, "motivo": "pull", "desde": "x"}
    assert [t for t, _ in c.fila(amb.db)] == ["docs"]  # o mesmo vault nunca em dois trabalhadores
    c.rodando.clear()
    c.ultima = {"docs": time.time(), "lento": time.time()}
    assert c.fila(amb.db) == [("lento", "pull")]  # agenda em dia: só o pull


def test_trabalhador_que_caiu_nao_fecha_a_rodada_dos_outros(amb):  # noqa: F811
    from petro_vault import historico
    with amb.db:
        amb.db.execute("INSERT INTO rodadas (modo, tags, inicio, trabalhador) VALUES ('agenda', '[\"a\"]', 'x', 't1')")
        amb.db.execute("INSERT INTO rodadas (modo, tags, inicio, trabalhador) VALUES ('agenda', '[\"b\"]', 'x', 't2')")
    historico.interromper(amb.db, "t1")
    abertas = [r["trabalhador"] for r in amb.db.execute("SELECT trabalhador FROM rodadas WHERE fim IS NULL")]
    assert abertas == ["t2"]
    historico.interromper(amb.db, "*")  # o coordenador ao subir: tudo o que estava aberto
    assert amb.db.execute("SELECT COUNT(*) FROM rodadas WHERE fim IS NULL").fetchone()[0] == 0


def test_publicar_so_as_pastas_pedidas(tmp_path, monkeypatch):
    """O commit leva só os vaults que terminaram (e a base); o que está no meio de um lote fica de fora."""
    import os
    import subprocess
    remoto, vault = tmp_path / "remoto.git", tmp_path / "vault"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remoto))
    git(tmp_path, "clone", "-q", str(remoto), str(vault))
    for c in ("sistemas/a/x.md", "sistemas/b/y.md", "_regras/comum.md"):
        (vault / c).parent.mkdir(parents=True, exist_ok=True)
        (vault / c).write_text("v1\n")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "inicio")
    git(vault, "push", "-q", "origin", "main")
    (vault / "sistemas/a/x.md").write_text("v2\n")
    (vault / "sistemas/b/y.md").write_text("pela metade\n")  # outro trabalhador no meio do lote
    (vault / "_regras/comum.md").write_text("regra nova\n")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run(["sh", f"{raiz}/curador/publicar.sh", "sistemas/a"], capture_output=True, text=True,
                       env={**os.environ, "VAULT_DIR": str(vault)})
    assert "enviado ao repositório" in r.stdout, r.stdout + r.stderr
    enviados = git(vault, "show", "--name-only", "--format=", "origin/main").split()
    assert enviados == ["_regras/comum.md", "sistemas/a/x.md"]
    assert git(vault, "status", "--porcelain").strip() == "M sistemas/b/y.md"  # continua lá, para a vez dele


def test_vault_sozinho_com_fila_volta_na_hora_e_cede_a_vez_se_tem_outro(amb, tmp_path, monkeypatch):  # noqa: F811
    """Acabou a fatia e ainda tem fila: sem ninguém esperando, volta logo; com outro vault na agenda, vai depois."""
    from petro_vault import estado
    _segundo_vault(amb, tmp_path, "# Lento\n")
    _, c, _ = _coordenador(tmp_path, monkeypatch, n=1)
    with amb.db:
        amb.db.execute("INSERT INTO fila (tag, origem, perfil, acao, caminho, commit_origem, criado_em, estado) "
                       "VALUES ('docs', 'principal', 'documentos', 'adicionado', 'a.md', 'x', ?, 'na_fila')",
                       (estado.agora(),))
    agora = time.time()
    c.ultima = {"docs": agora, "lento": agora}  # docs acabou de rodar a fatia; lento em dia
    assert c.fila(amb.db) == [("docs", "fila")]  # sozinho: volta na hora
    c.ultima["lento"] = 0  # lento venceu na agenda
    assert c.fila(amb.db) == [("lento", "agenda"), ("docs", "fila")]  # o outro passa na frente
