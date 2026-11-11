"""Testes da curadoria: o código garante tag, origem e datas; a
remoção na origem tira a nota do vault; o plugin prende o curador à tag.

O curador é o tests/hermes_falso.py, que passa pelo plugin de verdade.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def amb(tmp_path, monkeypatch):
    vault, estado_dir, chaves, home = (tmp_path / n for n in ("vault", "estado", "chaves", "home"))
    for p in (vault, chaves, home):
        p.mkdir()
    (chaves / "docs").write_text("chave falsa")
    hermes = tmp_path / "hermes"
    hermes.write_text(f"#!/bin/sh\nexec {sys.executable} {RAIZ}/tests/hermes_falso.py \"$@\"\n")
    hermes.chmod(0o755)
    for k, v in {"ESTADO_DIR": estado_dir, "VAULT_DIR": vault, "VAULT_ORIGENS_CHAVES_DIR": chaves,
                 "HERMES_HOME": home, "HERMES_BIN": hermes, "VAULT_LOTE_DIR": tmp_path / "lote",
                 "VAULT_PLUGIN_LOG": tmp_path / "plugin.log", "VAULT_PERFIS_DIR": f"{RAIZ}/curador/perfil",
                 "CLAUDE_CODE_OAUTH_TOKEN": "t" * 60, "VAULT_LOTE": "2"}.items():
        monkeypatch.setenv(k, str(v))
    from vault_system import curadoria, estado, filtros, ingestao, notas, verificacao
    for m in (filtros, ingestao, notas, curadoria, verificacao):
        importlib.reload(m)

    origem = tmp_path / "origem"
    origem.mkdir()
    git(origem, "init", "-q", "-b", "main")
    git(origem, "config", "user.name", "t")
    git(origem, "config", "user.email", "t@t")
    db = estado.conectar()
    with db:
        db.execute("INSERT INTO sistemas (tag, perfil, repo, ramo, incluir, excluir, criado_em, criado_por) "
                   "VALUES ('docs', 'documentos', ?, 'main', '[]', '[]', 'x', 't')", (str(origem),))

    class A:
        pass
    a = A()
    a.origem, a.vault, a.db, a.log = origem, vault, db, tmp_path / "plugin.log"
    a.curadoria, a.ingestao, a.verificacao, a.notas = curadoria, ingestao, verificacao, notas

    def commit(arquivos, remover=()):
        for caminho, texto in arquivos.items():
            (origem / caminho).parent.mkdir(parents=True, exist_ok=True)
            (origem / caminho).write_text(texto)
        for caminho in remover:
            git(origem, "rm", "-q", caminho)
        git(origem, "add", "-A")
        git(origem, "commit", "-q", "-m", "c")
        return git(origem, "rev-parse", "HEAD").strip()

    def rodada():
        ingestao._atender(db, ["docs"])
        curadoria.main(["docs"])
        return verificacao.verificar(db, "docs") if verificacao.indices("docs") is None else None

    a.commit, a.rodada = commit, rodada
    return a


def nota(a, rel):
    return a.notas.ler(a.vault / "sistemas" / "docs" / rel)


def test_fila_vira_notas_com_cabecalho_do_codigo(amb):
    c1 = amb.commit({"docs/a.md": "---\ntipo: processo\nresponsavel: Ana\n---\n# A\nconteúdo a\n",
                     "docs/b.md": "conteúdo b\n", "docs/c.txt": "ESPECIAL c\n"})
    erros = amb.rodada()
    assert erros == []
    cab, corpo = nota(amb, "documentos/docs/a.md")
    # O curador escreveu sistema e criado_em errados; o código corrigiu.
    assert cab["sistema"] == "docs" and cab["tipo_nota"] == "documento"
    assert cab["origens"] == ["docs/a.md"] and cab["commit_origem"] == c1
    assert cab["criado_em"] != "1999" and cab["criado_em"].endswith("+00:00")
    assert cab["origem_tipo"] == "processo" and cab["origem_responsavel"] == "Ana"
    assert nota(amb, "documentos/docs/c.txt.md")[0]["origens"] == ["docs/c.txt"]
    geral = nota(amb, "assuntos/geral.md")[0]
    assert geral["tipo_nota"] == "assunto" and geral["origens"] == ["docs/a.md", "docs/b.md"]
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0
    s = amb.db.execute("SELECT commit_processado FROM origens").fetchone()
    assert s["commit_processado"] == c1
    assert json.loads((amb.vault / "sistemas/docs/_meta/origem.json").read_text())["origens"][0]["commit_processado"] == c1
    assert "Nenhum problema" in (amb.vault / "sistemas/docs/_meta/verificacao.md").read_text()
    assert "[[sistemas/docs/documentos/docs/a]]" in (amb.vault / "sistemas/docs/indices/documentos.md").read_text()


def test_arquivo_apagado_na_origem_some_do_vault(amb, monkeypatch):
    amb.commit({"docs/a.md": "a\n", "docs/b.md": "b\n", "docs/c.md": "ESPECIAL c\n"})
    assert amb.rodada() == []
    criado = nota(amb, "assuntos/geral.md")[0]["criado_em"]
    monkeypatch.setenv("VAULT_TESTE_DORMIR", "1")
    c2 = amb.commit({}, remover=["docs/b.md", "docs/c.md"])
    assert amb.rodada() == []
    assert not (amb.vault / "sistemas/docs/documentos/docs/b.md").exists()
    # `especial` só tinha c como origem: o código apagou sem LLM.
    assert not (amb.vault / "sistemas/docs/assuntos/especial.md").exists()
    geral = nota(amb, "assuntos/geral.md")[0]
    # O curador reescreveu o assunto sem os campos do código: o criado_em antigo volta.
    assert geral["criado_em"] == criado and geral["atualizado_em"] > criado
    assert geral["origens"] == ["docs/a.md"]
    assert geral["evidencias"] == ["[[sistemas/docs/documentos/docs/a]]"]
    assert amb.db.execute("SELECT commit_processado FROM origens").fetchone()[0] == c2
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0


def test_item_sem_registro_fica_na_fila(amb):
    c1 = amb.commit({"docs/a.md": "a\n", "docs/b.md": "NAO-REGISTRAR b\n"})
    amb.rodada()
    fila = amb.db.execute("SELECT caminho FROM fila WHERE estado = 'na_fila'").fetchall()
    assert [l["caminho"] for l in fila] == ["docs/b.md"]
    s = amb.db.execute("SELECT commit_processado, commit_pendente FROM origens").fetchone()
    assert s["commit_processado"] is None and s["commit_pendente"] == c1


def test_plugin_bloqueia_fora_da_tag(amb):
    amb.commit({"docs/a.md": "INVADIR a\n"})
    amb.rodada()
    assert not (amb.vault / "sistemas/outra-tag").exists()
    assert not (amb.vault / "_regras").exists()
    log = [json.loads(l) for l in amb.log.read_text().splitlines()]
    bloqueados = {l["caminho"] for l in log if l["decisao"] == "bloqueado"}
    assert str(amb.vault / "sistemas/outra-tag/invasao.md") in bloqueados
    assert str(amb.vault / "_regras/comum.md") in bloqueados
    assert all(l["tag"] == "docs" for l in log)


def test_sem_token_itens_ficam(amb, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    amb.commit({"docs/a.md": "a\n"})
    amb.rodada()
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 1
    assert not (amb.vault / "sistemas/docs/documentos").exists()


def test_verificador_acha_problemas(amb):
    amb.commit({"docs/a.md": "a\n", "docs/b.md": "b\n"})
    assert amb.rodada() == []
    a = amb.vault / "sistemas/docs/documentos/docs/a.md"
    cab, corpo = amb.notas.ler(a)
    cab["origens"] = ["docs/nao-existe.md"]
    del cab["criado_em"]
    amb.notas.escrever(a, cab, corpo + "\n[[sistemas/docs/assuntos/fantasma]] [[sistemas/outra/x]]\n")
    erros = amb.verificacao.verificar(amb.db, "docs")
    texto = "\n".join(erros)
    assert "cabeçalho sem criado_em" in texto
    assert "link quebrado" in texto and "fantasma" in texto
    assert "link para outra tag" in texto
    assert "docs/nao-existe.md" in texto


@pytest.mark.parametrize("ferramenta,caminho,bloqueia", [
    ("read_file", "/v/_regras/comum.md", False),
    ("read_file", "/v/_templates/documentos/documento.md", False),
    ("read_file", "/v/_templates/codigo/x.md", True),
    ("read_file", "/lote/item-1.md", False),
    ("read_file", "/v/sistemas/docs/assuntos/x.md", False),
    ("read_file", "/v/sistemas/outra/x.md", True),
    ("read_file", "/estado/estado.db", True),
    ("search_files", "/v/sistemas/docs", False),
    ("write_file", "/v/sistemas/docs/documentos/a.md", False),
    ("write_file", "/v/sistemas/docs/assuntos/a.md", False),
    ("patch", "/v/sistemas/docs/_meta/registro.md", False),
    ("write_file", "/v/sistemas/docs/_meta/origem.json", True),
    ("write_file", "/v/sistemas/docs/indices/a.md", True),
    ("write_file", "/v/sistemas/docs/outra-pasta/a.md", True),
    ("write_file", "/v/sistemas/docs/../outra/a.md", True),
    ("write_file", "/lote/item-1.md", True),
    ("write_file", "relativo.md", True),
    ("terminal", "/v/sistemas/docs", True),
])
def test_plugin_regras(monkeypatch, ferramenta, caminho, bloqueia):
    _plugin_decide(monkeypatch, "documentos", ferramenta, caminho, bloqueia)


@pytest.mark.parametrize("ferramenta,caminho,bloqueia", [
    ("read_file", "/v/sistemas/docs/referencia/componentes/botoes.md", True),  # linhas deslocadas pelo cabeçalho
    ("search_files", "/v/sistemas/docs/referencia", True),
    ("read_file", "/lote/fontes/componentes/botoes.md", False),
    ("read_file", "/v/sistemas/docs/guias/botoes.md", False),
    ("write_file", "/v/sistemas/docs/guias/botoes.md", False),
    ("write_file", "/v/sistemas/docs/referencia/x.md", True),
])
def test_plugin_regras_referencia_explicada(monkeypatch, ferramenta, caminho, bloqueia):
    _plugin_decide(monkeypatch, "referencia-explicada", ferramenta, caminho, bloqueia)


def _plugin_decide(monkeypatch, perfil, ferramenta, caminho, bloqueia):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "plugin_t", f"{RAIZ}/curador/perfil/plugins/vault-system-curador/__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    for k, v in {"VAULT_SYSTEM_TAG": "docs", "VAULT_SYSTEM_PERFIL": perfil, "VAULT_SYSTEM_VAULT": "/v",
                 "VAULT_SYSTEM_LOTE_DIR": "/lote"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("VAULT_SYSTEM_PLUGIN_LOG", raising=False)
    assert (plugin.decidir(ferramenta, {"path": caminho}) is not None) == bloqueia


def test_links_da_origem_e_sem_commit_vazio(amb):
    amb.commit({"docs/a.md": "Ver [[docs/b]], [[docs/b.md|o B]] e [[equipamentos/x]].\n", "docs/b.md": "b\n"})
    assert amb.rodada() == []
    _, corpo = nota(amb, "documentos/docs/a.md")
    assert "[[sistemas/docs/documentos/docs/b]]" in corpo      # existe no vault: link completo
    assert "[[sistemas/docs/documentos/docs/b|o B]]" in corpo
    assert "`equipamentos/x`" in corpo and "[[equipamentos/x]]" not in corpo  # não existe: texto
    # Rodada sem nada novo: índices e verificação não mudam (sem commit vazio no vault).
    arquivos = [amb.vault / "sistemas/docs" / p for p in ("indices/documentos.md", "indices/assuntos.md",
                                                          "_meta/verificacao.md")]
    antes = [f.read_text() for f in arquivos]
    import time
    time.sleep(1.1)
    assert amb.rodada() == []
    assert [f.read_text() for f in arquivos] == antes


def test_remover_cadastro(amb):
    from vault_system import rodada
    amb.commit({"docs/a.md": "a\n"})
    assert amb.rodada() == []
    assert (amb.vault / "sistemas/docs").is_dir()
    amb.verificacao.indexar(amb.db, "docs")  # índice de notas (busca e MCP) da tag
    assert amb.db.execute("SELECT COUNT(*) FROM notas_indice WHERE tag = 'docs'").fetchone()[0] > 0
    with amb.db:
        amb.db.execute("UPDATE sistemas SET removido_em = 'x' WHERE tag = 'docs'")
    assert rodada.main(["pedidos"]) == 0  # houve remoção: o ciclo publica
    assert not (amb.vault / "sistemas/docs").exists()
    # Nada da tag fica: o vault recriado com a mesma tag não herda notas na busca/MCP nem avisos.
    for tabela in ("sistemas", "fila", "pulls", "origens", "notas_indice", "meta_tag", "verificacoes", "problemas",
                   "avisos", "lotes"):
        assert amb.db.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == 0
    assert rodada.main(["pedidos"]) == 3  # nada mais a fazer


def _duas_leituras(amb):
    """docs/ com perfil documentos; o resto do mesmo repositório com perfil codigo."""
    from vault_system import estado
    estado.migrar_origens(amb.db)
    leituras = [{"perfil": "documentos", "incluir": ["docs/*"], "excluir": []},
                {"perfil": "codigo", "incluir": [], "excluir": []}]
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras = ? WHERE tag = 'docs'", (json.dumps(leituras),))


def test_referencia_copia_como_esta_sem_llm(amb):
    """o arquivo vira nota como está, por código; o curador (LLM) nem é chamado."""
    from vault_system import estado
    estado.migrar_origens(amb.db)
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras = ? WHERE tag = 'docs'", (json.dumps(
            [{"perfil": "referencia", "incluir": [], "excluir": ["assets/**"]}]),))
    md = ("---\ncomponente: botao\ntokens: [\"cor-primaria\"]\n---\n# Botão\n\nVer [[outra]] e [o guia](../guia.md).\n\n"
          "```css\n.btn { color: #258D43; border-radius: 9px; }\n```\n")
    css = ":root {\n  --brand-green: #258D43;\n}\n"
    c1 = amb.commit({"componentes/botao.md": md, "tokens/tokens.css": css, "assets/logo.svg": "<svg/>"})
    assert amb.rodada() == []
    assert not amb.log.exists()  # nenhuma chamada ao curador
    cab, corpo = nota(amb, "referencia/componentes/botao.md")
    assert corpo == md  # exatamente o arquivo, com o cabeçalho dele e o link como estava
    assert cab["sistema"] == "docs" and cab["tipo_nota"] == "referencia" and cab["origens"] == ["componentes/botao.md"]
    assert cab["commit_origem"] == c1 and cab["literal"] == "true" and cab["hash_literal"]
    assert nota(amb, "referencia/tokens/tokens.css.md")[1] == "# tokens.css\n\n```css\n" + css + "```\n"
    assert not (amb.vault / "sistemas/docs/referencia/assets").exists()
    assert "copiado como está" in (amb.vault / "sistemas/docs/_meta/registro.md").read_text()
    assert amb.db.execute("SELECT commit_processado FROM origens").fetchone()[0] == c1
    criado = cab["criado_em"]

    # Mudou na origem: a nota acompanha; apagou: a nota sai.
    c2 = amb.commit({"componentes/botao.md": md.replace("9px", "8px")}, remover=["tokens/tokens.css"])
    assert amb.rodada() == []
    cab, corpo = nota(amb, "referencia/componentes/botao.md")
    assert "8px" in corpo and cab["commit_origem"] == c2 and cab["criado_em"] == criado
    assert not (amb.vault / "sistemas/docs/referencia/tokens/tokens.css.md").exists()
    assert not amb.log.exists()

    # Editar a nota no vault (e não na origem) é acusado.
    c = amb.vault / "sistemas/docs/referencia/componentes/botao.md"
    amb.notas.escrever(c, cab, corpo.replace("8px", "12px"))
    assert any("nota literal editada" in e for e in amb.verificacao.verificar(amb.db, "docs"))


def test_referencia_explicada_guia_com_trechos_colados_pelo_codigo(amb):
    """ fase 2: cópia literal + guia do curador; o código do guia vem só por trecho."""
    from vault_system import estado
    estado.migrar_origens(amb.db)
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras = ? WHERE tag = 'docs'", (json.dumps(
            [{"perfil": "referencia-explicada", "incluir": [], "excluir": []}]),))
    html = ('<html><body>\n<section id="botoes"><button class="btn primary">Salvar</button></section>\n'
            '<section id="cores"><i>verde</i></section>\n</body></html>\n')
    c1 = amb.commit({"vitrine/index.html": html})
    assert amb.rodada() == []
    assert nota(amb, "referencia/vitrine/index.html.md")[1] == "# index.html\n\n```html\n" + html + "```\n"
    cab, corpo = nota(amb, "guias/index.md")
    assert cab["sistema"] == "docs" and cab["tipo_nota"] == "guia" and cab["origens"] == ["vitrine/index.html"]
    assert cab["commit_origem"] == c1
    trecho = ('<!-- trecho: vitrine/index.html#botoes -->\n```html\n'
              '<section id="botoes"><button class="btn primary">Salvar</button></section>\n```\n<!-- /trecho -->\n')
    assert trecho in corpo
    assert ".btn{color:red}" not in corpo  # o código escrito pelo curador saiu
    assert "[[sistemas/docs/referencia/vitrine/index.html]]" in corpo
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0

    # A origem muda: o trecho do guia acompanha na rodada seguinte, sem precisar do curador mexer.
    amb.commit({"vitrine/index.html": html.replace("Salvar", "Gravar")})
    assert amb.rodada() == []
    assert "Gravar</button>" in nota(amb, "guias/index.md")[1] and "Salvar" not in nota(amb, "guias/index.md")[1]

    # Trecho editado à mão no vault é acusado.
    g = amb.vault / "sistemas/docs/guias/index.md"
    cab, corpo = amb.notas.ler(g)
    amb.notas.escrever(g, cab, corpo.replace("Gravar", "Outro") + "\n```js\nalert(1)\n```\n")
    erros = "\n".join(amb.verificacao.verificar(amb.db, "docs"))
    assert "não bate com a origem" in erros and "código escrito à mão" in erros

    # Arquivo apagado: some a nota literal, e o guia que só vinha dele sai.
    amb.commit({"outro.md": "# Outro\n"}, remover=["vitrine/index.html"])
    amb.rodada()
    assert not (amb.vault / "sistemas/docs/referencia/vitrine/index.html.md").exists()


def test_trecho_de_md_usa_linhas_do_arquivo_e_linguagem_do_bloco(amb):
    """ (03/11): numa fonte .md o trecho sai com a linguagem do bloco de onde veio, as linhas são as do
    arquivo (o lote traz a cópia numerada em fontes/) e o id inexistente diz os ids que existem."""
    from vault_system import curadoria, estado, literal
    estado.migrar_origens(amb.db)
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras = ? WHERE tag = 'docs'", (json.dumps(
            [{"perfil": "referencia-explicada", "incluir": [], "excluir": []}]),))
    md = ("---\ncomponente: botoes\n---\n# Botões\n\n## Código\n\n```html\n"   # L1-L8
          '<button class="btn" id="salvar">Salvar</button>\n```\n\n### CSS\n```css\n'  # L9-L13
          ".btn{color:green}\n.btn:hover{color:red}\n```\n")                          # L14-L16
    amb.commit({"componentes/botoes.md": md})
    amb.rodada()
    trecho = literal.trecho
    assert trecho("docs", "componentes/botoes.md:L14-L15") == (".btn{color:green}\n.btn:hover{color:red}", "css")
    assert trecho("docs", "componentes/botoes.md:L13-L16")[1] is None  # o bloco inteiro sai como está
    assert trecho("docs", "componentes/botoes.md:L12-L14")[1] == "markdown"  # corta um bloco: fica numa cerca
    assert trecho("docs", "componentes/botoes.md#salvar")[1] == "html"
    # Linha de crases pega junto na borda (o curador erra por uma): sai só o conteúdo do bloco.
    assert trecho("docs", "componentes/botoes.md:L14-L16") == (".btn{color:green}\n.btn:hover{color:red}", "css")
    assert trecho("docs", "componentes/botoes.md:L13-L15") == (".btn{color:green}\n.btn:hover{color:red}", "css")
    # Só a linha de crases (abertura ou fechamento): o curador quis o bloco; sai o bloco inteiro.
    assert trecho("docs", "componentes/botoes.md:L16") == (".btn{color:green}\n.btn:hover{color:red}", "css")
    assert trecho("docs", "componentes/botoes.md:L13") == (".btn{color:green}\n.btn:hover{color:red}", "css")
    texto, motivo = trecho("docs", "componentes/botoes.md#botoes-css")
    assert texto is None and "ids que existem: salvar" in motivo
    corpo, _ = literal.colar("docs", "<!-- trecho: componentes/botoes.md:L13-L16 -->\n")
    assert corpo == "<!-- trecho: componentes/botoes.md:L13-L16 -->\n" + "\n".join(md.split("\n")[12:16]) \
        + "\n<!-- /trecho -->\n"
    assert literal.conferir_guia("docs", "g", corpo) == []
    # Marcador de um arquivo chamado tokens.* não é segredo (`tokens.json:L1-L9` parecia `token: valor`).
    g = amb.vault / "sistemas/docs/guias/tokens.md"
    amb.notas.escrever(g, {"resumo": "x"}, "<!-- trecho: tokens/tokens.json:L233-L339 -->\n")
    assert "possível segredo" not in "\n".join(amb.verificacao.verificar(amb.db, "docs"))
    g.unlink()
    cortado, _ = literal.colar("docs", "<!-- trecho: componentes/botoes.md:L12-L14 -->\n")
    assert [e[0] for e in literal.conferir_guia("docs", "g", cortado)] == ["trecho_corta_bloco"]

    # O lote traz a cópia numerada do arquivo (linhas do arquivo, não da nota) e os ids.
    item = amb.db.execute("SELECT * FROM fila ORDER BY id DESC LIMIT 1").fetchone()
    [arq] = curadoria.montar_lote("docs", "referencia-explicada", [dict(item)])
    assert "- ids HTML deste arquivo (só estes valem em #<id>): salvar" in open(arq).read()
    fonte = open(os.path.join(curadoria.LOTE_DIR, "fontes", "componentes/botoes.md")).read().split("\n")
    assert fonte[13] == "   14| .btn{color:green}"


@pytest.mark.parametrize("perfil", ["codigo", "referencia-explicada"])
def test_infra_vira_notas_com_fatos_do_codigo(amb, perfil):
    """o arquivo de container vira infra/<serviço>.md e a visão geral; os fatos do cabeçalho são do código,
    acompanham o arquivo e o serviço que some é acusado. Na Referência, o arquivo continua literal também."""
    if perfil == "codigo":
        _duas_leituras(amb)
    else:
        from vault_system import estado
        estado.migrar_origens(amb.db)
        with amb.db:
            amb.db.execute("UPDATE origens SET leituras = ? WHERE tag = 'docs'", (json.dumps(
                [{"perfil": perfil, "incluir": [], "excluir": []}]),))
    compose = ("services:\n  vitrine:\n    build: .\n    container_name: template-ds\n    ports:\n      - \"8006:80\"\n"
               "    env_file: [.env]\n    environment:\n      - SENHA=NaoPodeAparecer\n")
    amb.commit({"docker-compose.yml": compose, "Dockerfile": "FROM nginx:1.27\nEXPOSE 80\nCOPY nginx.conf /etc/x\n",
                "nginx.conf": "server { listen 80; location = /health { return 200; } }\n",
                ".env.example": "DATABASE_URL=mysql://app:OutraSenha@10.2.2.6:3306/x\n"})
    assert amb.rodada() == []
    cab, corpo = nota(amb, "infra/vitrine.md")
    assert cab["tipo_nota"] == "infra" and cab["servico"] == "vitrine" and cab["container"] == "template-ds"
    assert cab["portas"] == ["8006:80"]  # o "1:1" do curador foi trocado pelo do arquivo
    assert cab["origens"] == ["docker-compose.yml", "Dockerfile", "nginx.conf"] and "fontes" not in cab
    assert cab["proxy"] == ["= /health → return 200"] and "NaoPodeAparecer" not in str(cab)
    # o .env.example (mesmo fora das leituras) dá o banco externo, só tipo e host:porta.
    assert cab["externos"] == ["MySQL"] and "OutraSenha" not in open(
        amb.vault / "sistemas/docs/infra/vitrine.md").read()
    assert "[[sistemas/docs/infra/vitrine]]" in nota(amb, "infra/visao-geral.md")[1]
    if perfil != "codigo":
        assert str(nota(amb, "referencia/docker-compose.yml.md")[0]["literal"]).lower() == "true"
        # O marcador de trecho na nota de infra ganha o arquivo colado, como nos guias.
        assert "<!-- trecho: docker-compose.yml:L1-L2 -->\n```yaml\nservices:\n  vitrine:\n```" in corpo
        assert not (amb.vault / "sistemas/docs/guias/docker-compose.md").exists()
    assert not (amb.vault / "sistemas/docs/modulos/raiz.md").exists() or \
        "docker-compose" not in nota(amb, "modulos/raiz.md")[1]  # infra não vai para o módulo

    # Vault de antes do  (arquivos já processados, sem infra/): entra na fila uma vez e ganha as notas.
    import shutil
    shutil.rmtree(amb.vault / "sistemas/docs/infra")
    amb.rodada()
    assert nota(amb, "infra/vitrine.md")[0]["portas"] == ["8006:80"]
    shutil.rmtree(amb.vault / "sistemas/docs/infra")
    amb.rodada()
    assert not (amb.vault / "sistemas/docs/infra").exists()  # uma vez só: não volta para a fila

    amb.commit({"docker-compose.yml": compose + "\n"})  # mudou: o curador documenta de novo
    amb.rodada()

    # Nota de infra que ficou sem o cabeçalho do código (lote interrompido): a rodada completa, não apaga.
    g = amb.vault / "sistemas/docs/infra/vitrine.md"
    amb.notas.escrever(g, {"resumo": "Serviço"}, amb.notas.ler(g)[1])
    amb.commit({"LEIA.txt": "x\n"})
    amb.rodada()
    cab = nota(amb, "infra/vitrine.md")[0]
    assert cab["sistema"] == "docs" and cab["tipo_nota"] == "infra" and cab["origens"] and cab["criado_em"]

    # O arquivo muda e o curador não mexe na nota: o cabeçalho acompanha na rodada.
    amb.commit({"docker-compose.yml": compose.replace("8006:80", "8010:80")})
    amb.rodada()
    assert nota(amb, "infra/vitrine.md")[0]["portas"] == ["8010:80"]

    # O serviço some do compose: a nota é acusada.
    amb.commit({"docker-compose.yml": compose.replace("vitrine:", "outro:")})
    amb.rodada()
    assert "infra de um serviço que não existe" in "\n".join(amb.verificacao.verificar(amb.db, "docs"))


def test_codigo_vira_conhecimento_com_origens_conferidas(amb):
    _duas_leituras(amb)
    amb.commit({"docs/a.md": "manual\n", "src/x.py": "# REGRA: limite-de-peso\ndef f(): pass\n",
                "src/y.py": "def g(): pass\n"})
    assert amb.rodada() == []
    # docs/ foi para o perfil documentos; src/ para o código, num lote só (uma pasta).
    assert nota(amb, "documentos/docs/a.md")[0]["origens"] == ["docs/a.md"]
    mod = nota(amb, "modulos/src.md")[0]
    assert mod["tipo_nota"] == "modulo" and mod["sistema"] == "docs"
    assert mod["origens"] == ["src/x.py", "src/y.py"]  # a fonte inventada foi descartada
    assert "fontes" not in mod
    regra = nota(amb, "regras/limite-de-peso.md")[0]
    assert regra["tipo_nota"] == "regra" and regra["origens"] == ["src/x.py"]
    assert regra["commit_origem"] and "fontes" not in regra
    assert "## modulos" in (amb.vault / "sistemas/docs/indices/codigo.md").read_text()


def test_mudanca_num_arquivo_so_atualiza_notas_ligadas(amb):
    _duas_leituras(amb)
    amb.commit({"src/x.py": "# REGRA: limite-de-peso\n", "src/y.py": "# REGRA: prazo\n"})
    assert amb.rodada() == []
    regra_x = (amb.vault / "sistemas/docs/regras/limite-de-peso.md").read_text()
    amb.commit({"src/y.py": "# REGRA: prazo\n# mudou\n"})
    assert amb.rodada() == []
    assert (amb.vault / "sistemas/docs/regras/limite-de-peso.md").read_text() == regra_x  # não ligada a y
    assert nota(amb, "regras/prazo.md")[0]["origens"] == ["src/y.py"]
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0


def test_codigo_apagado_tira_a_regra_e_revisa_o_modulo(amb):
    _duas_leituras(amb)
    amb.commit({"src/x.py": "# REGRA: limite-de-peso\n", "src/y.py": "def g(): pass\n"})
    assert amb.rodada() == []
    amb.commit({}, remover=["src/x.py"])
    assert amb.rodada() == []
    assert not (amb.vault / "sistemas/docs/regras/limite-de-peso.md").exists()  # só vinha de x: o código apagou
    assert nota(amb, "modulos/src.md")[0]["origens"] == ["src/y.py"]


def test_segunda_origem_e_segredo_no_verificador(amb, tmp_path):
    from vault_system import estado
    estado.migrar_origens(amb.db)
    outra = tmp_path / "outra"
    outra.mkdir()
    git(outra, "init", "-q", "-b", "main")
    git(outra, "config", "user.name", "t")
    git(outra, "config", "user.email", "t@t")
    (outra / "docs").mkdir()
    (outra / "docs" / "b.md").write_text("doc da outra origem\n")
    git(outra, "add", "-A")
    git(outra, "commit", "-q", "-m", "c")
    (tmp_path / "chaves" / "docs--extra").write_text("chave falsa")
    with amb.db:
        amb.db.execute("INSERT INTO origens (tag, nome, repo, ramo, leituras, criado_em) VALUES "
                       "('docs', 'extra', ?, 'main', ?, 'x')",
                       (str(outra), json.dumps([{"perfil": "documentos", "incluir": [], "excluir": []}])))
    amb.commit({"docs/a.md": "a\n"})
    assert amb.rodada() == []
    b = nota(amb, "documentos/extra/docs/b.md")[0]
    assert b["origens"] == ["extra:docs/b.md"]
    assert "extra:docs/b.md" in nota(amb, "assuntos/geral.md")[0]["origens"]
    origens = json.loads((amb.vault / "sistemas/docs/_meta/origem.json").read_text())["origens"]
    assert [o["nome"] for o in origens] == ["principal", "extra"] and all(o["commit_processado"] for o in origens)
    # Segredo escrito numa nota (por qualquer caminho) é acusado.
    a = amb.vault / "sistemas/docs/documentos/docs/a.md"
    a.write_text(a.read_text() + "\ntoken: ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8" + "\n")
    assert any("possível segredo" in e for e in amb.verificacao.verificar(amb.db, "docs"))


def test_rodada_completa_vista_pela_tela(amb, monkeypatch):
    """a rodada grava histórico, índice das notas e verificação no
    banco, e a tela lê tudo dali, sem montar o vault."""
    from vault_system import historico, ingestao, rodada
    importlib.reload(historico)
    importlib.reload(rodada)
    amb.commit({"docs/a.md": "a [[nao-existe]]\n", "docs/b.md": "NAO-REGISTRAR b\n"})
    assert rodada.main(["todos"]) == 0
    r = amb.db.execute("SELECT * FROM rodadas ORDER BY id DESC LIMIT 1").fetchone()
    assert r["modo"] == "todos" and r["fim"] and json.loads(r["tags"]) == ["docs"]
    lote = amb.db.execute("SELECT * FROM lotes WHERE rodada_id = ?", (r["id"],)).fetchone()
    assert (lote["itens"], lote["registrados"]) == (2, 1) and "sem registro" in lote["erro"]
    # b volta na mesma rodada, sozinho, e falha de novo (2 falhas: a rodada para a tag).
    assert amb.db.execute("SELECT tentativas FROM fila WHERE caminho = 'docs/b.md' AND estado = 'na_fila'").fetchone()[0] == 2
    o = amb.db.execute("SELECT * FROM origens").fetchone()
    assert o["acesso_ok"] == 1 and o["data_pendente"] and o["commits_atras"] == 1
    assert amb.db.execute("SELECT COUNT(*) FROM notas_indice WHERE tag = 'docs'").fetchone()[0] >= 2
    assert historico.ler_estado(amb.db)["proxima_rodada"]

    # A tela, com o mesmo estado.db.
    monkeypatch.setenv("VAULT_SESSAO_SEGREDO", "s" * 40)
    monkeypatch.setenv("VAULT_ADMINS", "tiago.santo")
    from fastapi.testclient import TestClient
    from app import credenciais, main, painel, sessao, sistemas
    for m in (credenciais, sistemas, sessao, painel, main):
        importlib.reload(m)
    from test_painel import AdFalso
    main.app.state.ldap = AdFalso()
    c = TestClient(main.app)
    assert c.post("/v1/painel/entrar", json={"login": "tiago.santo", "senha": "certa"}).status_code == 200
    s = c.get("/v1/painel/sistemas/docs").json()
    # Com problema vem antes de processando (tela-plano.md 2.2): o lote deixou um item sem registro.
    assert s["selo"]["estado"] == "com_problema" and "lote do curador com erro" in s["selo"]["texto"]
    assert s["sinais"]["fila"] == {"itens": 1, "parados": 0}
    rod = c.get("/v1/painel/sistemas/docs/rodadas").json()["rodadas"][0]
    assert (rod["itens"], rod["registrados"], rod["com_erro"]) == (3, 1, 2)  # [a, b] e depois [b]
    arvore = c.get("/v1/painel/sistemas/docs/notas").json()["pastas"]
    assert {p["pasta"] for p in arvore} >= {"documentos", "assuntos"}
    nota = c.get("/v1/painel/sistemas/docs/notas/documentos/docs/a").json()
    assert nota["origens"][0]["caminho"] == "docs/a.md" and "Doc item" in nota["conteudo"]
    assert c.get("/v1/painel/sistemas/docs/notas/documentos/nao/existe").status_code == 404
    v = c.get("/v1/painel/sistemas/docs/verificacao").json()
    assert v["estado"] in ("limpa", "com_problema") and v["rodou_em"]
    assert "item-" in c.get("/v1/painel/sistemas/docs/registro").json()["conteudo"]
    # Segunda rodada: b.md volta, é registrado; o problema que sumir sai, e `desde` dos que ficam não muda.
    desde = {p["detalhe"]: p["desde"] for p in v["problemas"]}
    amb.commit({"docs/b.md": "b, agora registrável\n"})
    assert rodada.main(["todos"]) == 0
    v2 = c.get("/v1/painel/sistemas/docs/verificacao").json()
    for p in v2["problemas"]:
        if p["detalhe"] in desde:
            assert p["desde"] == desde[p["detalhe"]]
    assert c.get("/v1/painel/sistemas/docs").json()["sinais"]["fila"]["itens"] == 0


def _com(amb, monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    importlib.reload(amb.curadoria)


def test_lote_que_trava_e_dividido_e_a_fila_segue(amb, monkeypatch):
    """ (refeitorio, 27/10): um arquivo que derruba o lote não trava a
    fila. O lote cai pela metade a cada tentativa, quem falhou vai para o fim
    da fila e, isolado, o arquivo fica parado; o resto vira nota."""
    from vault_system import historico
    _com(amb, monkeypatch, VAULT_TENTATIVAS_MAX=2, VAULT_FALHAS_MAX=5)
    c1 = amb.commit({"docs/a.md": "a\n", "docs/b.md": "TRAVAR b\n", "docs/c.md": "c\n", "docs/d.md": "d\n"})
    importlib.reload(historico)
    amb.rodada()
    lotes = [(l["itens"], l["registrados"]) for l in amb.db.execute("SELECT * FROM lotes ORDER BY id")]
    # [a, b] falha; [c, d] passa; a e b, com 1 tentativa, vão um por lote.
    assert lotes == [(2, 0), (2, 2), (1, 1), (1, 0)]
    for doc in ("a", "c", "d"):
        assert (amb.vault / f"sistemas/docs/documentos/docs/{doc}.md").exists()
    b = amb.db.execute("SELECT * FROM fila WHERE estado = 'na_fila'").fetchall()
    assert [i["caminho"] for i in b] == ["docs/b.md"]
    assert b[0]["parado_em"] and b[0]["tentativas"] == 2 and "código 124" not in b[0]["erro"]
    assert "tempo esgotado" in b[0]["erro"]
    aviso = amb.db.execute("SELECT * FROM avisos WHERE tipo = 'item_parado'").fetchone()
    assert "docs/b.md" in aviso["detalhe"]
    # Parado continua na fila: o commit não avança, e a rodada seguinte não gasta nada com ele.
    o = amb.db.execute("SELECT commit_processado, commit_pendente FROM origens").fetchone()
    assert o["commit_processado"] is None and o["commit_pendente"] == c1
    amb.rodada()
    assert amb.db.execute("SELECT COUNT(*) FROM lotes").fetchone()[0] == 4


def test_teto_de_falhas_por_rodada(amb, monkeypatch):
    _com(amb, monkeypatch, VAULT_FALHAS_MAX=1)
    amb.commit({"docs/a.md": "TRAVAR a\n", "docs/b.md": "b\n", "docs/c.md": "c\n"})
    amb.rodada()
    assert amb.db.execute("SELECT COUNT(*) FROM lotes").fetchone()[0] == 1
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 3
    # Na rodada seguinte, quem falhou vai para o fim: c passa antes do lote de a.
    amb.rodada()
    assert (amb.vault / "sistemas/docs/documentos/docs/c.md").exists()


def test_codigo_dividido_por_tentativas(amb, monkeypatch):
    """Perfil código: a mesma pasta, com o lote cortado pela metade a cada tentativa."""
    _com(amb, monkeypatch, VAULT_LOTE_CODIGO=4)
    db = amb.db
    with db:
        for n in range(6):
            db.execute("INSERT INTO fila (tag, origem, perfil, acao, caminho, commit_origem, criado_em, tentativas) "
                       "VALUES ('docs', 'principal', 'codigo', 'adicionado', ?, 'c', 'x', ?)",
                       (f"src/{n}.py", 1 if n < 3 else 0))
    perfil, itens = amb.curadoria.proximo_lote(db, "docs")
    assert perfil == "codigo" and [i["caminho"] for i in itens] == ["src/3.py", "src/4.py", "src/5.py"]
    with db:
        db.execute("UPDATE fila SET estado = 'registrado' WHERE tentativas = 0")
    _, itens = amb.curadoria.proximo_lote(db, "docs")
    assert [i["caminho"] for i in itens] == ["src/0.py", "src/1.py"]  # 4 >> 1


def _editar(amb, leituras, origem="principal"):
    from app import sistemas as cadastro
    from vault_system import estado
    estado.migrar_origens(amb.db)
    assert cadastro.editar_origem("docs", origem, "main", leituras)


def test_excluir_e_incluir_de_novo_uma_pasta(amb):
    """pronto quando: excluir uma pasta tira as notas dela no pull
    seguinte, com o verificador limpo; incluir de novo traz de volta."""
    amb.commit({"docs/a.md": "a\n", "docs/b.md": "b\n", "rascunho/c.md": "ESPECIAL c\n"})
    assert amb.rodada() == []
    assert (amb.vault / "sistemas/docs/documentos/rascunho/c.md").exists()
    tudo = [{"perfil": "documentos", "incluir": [], "excluir": []}]
    _editar(amb, [{"perfil": "documentos", "incluir": [], "excluir": ["rascunho/**"]}])
    assert amb.rodada() == []  # sem commit novo: só a reconciliação
    assert not (amb.vault / "sistemas/docs/documentos/rascunho/c.md").exists()
    assert not (amb.vault / "sistemas/docs/assuntos/especial.md").exists()  # só vinha de c
    assert (amb.vault / "sistemas/docs/documentos/docs/a.md").exists()
    o = amb.db.execute("SELECT * FROM origens").fetchone()
    assert o["leituras_antes"] is None and o["commit_processado"] == o["commit_pendente"]
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0
    _editar(amb, tudo)
    assert amb.rodada() == []
    assert nota(amb, "documentos/rascunho/c.md")[0]["origens"] == ["rascunho/c.md"]
    assert "rascunho/c.md" in nota(amb, "assuntos/especial.md")[0]["origens"]


def test_arquivo_muda_de_leitura(amb):
    """docs/ passa de documentos para código: sai das notas de documento e
    entra nas de código, sem que o removido apague a nota nova."""
    amb.commit({"docs/a.md": "# REGRA: prazo\n", "outro/b.md": "b\n"})
    assert amb.rodada() == []
    assert (amb.vault / "sistemas/docs/documentos/docs/a.md").exists()
    _editar(amb, [{"perfil": "codigo", "incluir": ["docs/**"], "excluir": []},
                  {"perfil": "documentos", "incluir": [], "excluir": []}])
    # Commit novo que muda o arquivo na mesma ingestão: o removido do perfil antigo fica.
    amb.commit({"docs/a.md": "# REGRA: prazo\n# mudou\n"})
    assert amb.rodada() == []
    assert not (amb.vault / "sistemas/docs/documentos/docs/a.md").exists()
    assert nota(amb, "regras/prazo.md")[0]["origens"] == ["docs/a.md"]
    assert nota(amb, "modulos/docs.md")[0]["origens"] == ["docs/a.md"]
    assert nota(amb, "assuntos/geral.md")[0]["origens"] == ["outro/b.md"]
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0


def test_remover_uma_origem(amb, tmp_path):
    from app import sistemas as cadastro
    from vault_system import estado
    estado.migrar_origens(amb.db)
    outra = tmp_path / "outra"
    outra.mkdir()
    git(outra, "init", "-q", "-b", "main")
    git(outra, "config", "user.name", "t")
    git(outra, "config", "user.email", "t@t")
    (outra / "b.md").write_text("ESPECIAL da outra\n")
    git(outra, "add", "-A")
    git(outra, "commit", "-q", "-m", "c")
    (tmp_path / "chaves" / "docs--extra").write_text("chave falsa")
    with amb.db:
        amb.db.execute("INSERT INTO origens (tag, nome, repo, ramo, leituras, criado_em) VALUES "
                       "('docs', 'extra', ?, 'main', ?, 'x')",
                       (str(outra), json.dumps([{"perfil": "documentos", "incluir": [], "excluir": []}])))
    amb.commit({"a.md": "a\n"})
    assert amb.rodada() == []
    assert (amb.vault / "sistemas/docs/documentos/extra/b.md").exists()
    assert cadastro.remover_origem("docs", "principal") is True
    assert cadastro.remover_origem("docs", "extra") == "ultima"
    assert amb.rodada() == []
    assert not (amb.vault / "sistemas/docs/documentos/a.md").exists()
    assert (amb.vault / "sistemas/docs/documentos/extra/b.md").exists()
    assert [o["nome"] for o in amb.db.execute("SELECT nome FROM origens")] == ["extra"]
    assert not os.path.exists(amb.ingestao.dir_clone("docs", "principal"))


def test_rodada_aberta_por_curador_parado_fecha_como_interrompida(amb):
    """27/10: o curador parado no meio do lote deixava a rodada e o lote "em curso" para sempre."""
    from vault_system import historico
    importlib.reload(historico)
    historico.abrir_rodada(amb.db, "todos", ["docs"])
    lote = historico.abrir_lote(amb.db, "docs", "codigo", 12)
    parada = historico.RODADA
    historico.abrir_rodada(amb.db, "todos", ["docs"])  # o curador religado
    r = amb.db.execute("SELECT fim, resultado FROM rodadas WHERE id = ?", (parada,)).fetchone()
    assert r["fim"] and r["resultado"] == "interrompida"
    l = amb.db.execute("SELECT fim, erro FROM lotes WHERE id = ?", (lote,)).fetchone()
    assert l["fim"] and "interrompido" in l["erro"]
    assert amb.db.execute("SELECT fim FROM rodadas WHERE id = ?", (historico.RODADA,)).fetchone()[0] is None


def test_reconciliacao_nao_apaga_o_lote_do_outro_perfil(amb):
    """27/10: docs/ ainda na fila como código passa para documentos; o removido
    de código apagava o arquivo do lote que o adicionado de documentos usa (o
    mesmo caminho) e toda rodada caía no montar_lote."""
    _editar(amb, [{"perfil": "codigo", "incluir": [], "excluir": []}])
    amb.commit({"docs/a.md": "# REGRA: prazo\n", "src/b.py": "b = 1\n"})
    amb.ingestao._atender(amb.db, ["docs"])  # na fila como código, sem curadoria ainda
    _editar(amb, [{"perfil": "documentos", "incluir": ["docs/**"], "excluir": []},
                  {"perfil": "codigo", "incluir": [], "excluir": []}])
    assert amb.rodada() == []
    assert nota(amb, "documentos/docs/a.md")[0]["origens"] == ["docs/a.md"]
    assert amb.db.execute("SELECT COUNT(*) FROM fila WHERE estado = 'na_fila'").fetchone()[0] == 0


def test_arquivo_do_lote_que_sumiu_e_refeito(amb):
    amb.commit({"docs/a.md": "a\n"})
    amb.ingestao._atender(amb.db, ["docs"])
    lote = amb.db.execute("SELECT lote FROM fila WHERE estado = 'na_fila'").fetchone()[0]
    caminho = os.path.join(os.environ["ESTADO_DIR"], "lotes", lote)
    os.remove(caminho)
    assert amb.rodada() == []
    assert (amb.vault / "sistemas/docs/documentos/docs/a.md").exists()


def test_nota_de_lote_interrompido(amb):
    """Curador desligado no meio do lote: as notas que ele já tinha escrito
    ficavam sem os campos do código (só `fontes`), fora da remoção e da
    reconciliação. Com fonte de código válida, o cabeçalho é completado; sem,
    a nota sai e o link para ela vira texto."""
    _editar(amb, [{"perfil": "documentos", "incluir": ["docs/**"], "excluir": []},
                  {"perfil": "codigo", "incluir": [], "excluir": []}])
    amb.commit({"docs/a.md": "a\n", "src/b.py": "b = 1\n"})
    assert amb.rodada() == []
    regras = amb.vault / "sistemas/docs/regras"
    regras.mkdir(exist_ok=True)
    (regras / "do-codigo.md").write_text('---\nresumo: "x"\nfontes: ["src/b.py"]\n---\n# Do código\n')
    (regras / "do-documento.md").write_text('---\nresumo: "y"\nfontes: ["docs/a.md"]\n---\n# Do documento\n')
    (regras / "cita.md").write_text('---\nresumo: "z"\nfontes: ["src/b.py"]\n---\n# Cita\n'
                                    "ver [[sistemas/docs/regras/do-documento]]\n")
    assert amb.rodada() == []
    cab = nota(amb, "regras/do-codigo.md")[0]
    assert cab["sistema"] == "docs" and cab["tipo_nota"] == "regra" and cab["origens"] == ["src/b.py"]
    assert "fontes" not in cab
    assert not (regras / "do-documento.md").exists()
    assert "`do-documento`" in nota(amb, "regras/cita.md")[1]
    avisos = [a[0] for a in amb.db.execute("SELECT tipo FROM avisos")]
    assert avisos.count("nota_interrompida") == 3


def test_link_com_md_no_fim_vira_a_chave_da_nota(amb):
    """28/10: o curador copiou o caminho do arquivo da nota no link do assunto
    (`.../documentos/docs/a.md`); a chave é sem `.md`, o link ficava quebrado
    e o documento, órfão."""
    amb.commit({"docs/a.md": "a\n"})
    assert amb.rodada() == []
    c = amb.vault / "sistemas/docs/assuntos/geral.md"
    texto = c.read_text().replace("[[sistemas/docs/documentos/docs/a]]", "[[sistemas/docs/documentos/docs/a.md]]")
    c.write_text(texto + "\nVer [[sistemas/docs/documentos/docs/nao-existe.md]].\n")
    amb.curadoria.normalizar_links("docs")
    texto = c.read_text()
    assert "[[sistemas/docs/documentos/docs/a]]" in texto and "docs/a.md]]" not in texto
    assert "[[sistemas/docs/documentos/docs/nao-existe.md]]" in texto  # sem nota: fica, o verificador acusa


def test_codigo_com_copia_literal(amb):
    """código + cópia literal. O curador escreve o conhecimento (fila de código); a cópia em referencia/
    e o bloco Arquivos nas notas de código são do código. Trocar código ↔ código + cópia não enfileira nada."""
    def leituras(classe):
        return [{"perfil": "documentos", "incluir": ["docs/*"], "excluir": []}, {"perfil": classe, "incluir": [], "excluir": []}]

    def fila():
        return amb.db.execute("SELECT COUNT(*) FROM fila").fetchone()[0]

    _editar(amb, leituras("codigo-literal"))
    with amb.db:
        amb.db.execute("UPDATE origens SET leituras_antes = NULL")
    x = "# REGRA: limite-de-peso\nBANCO = 'mysql://app:senha-do-banco@db:3306/r'\ndef f(): pass\n"
    c1 = amb.commit({"docs/a.md": "manual\n", "src/x.py": x, "src/y.py": "def g(): pass\n",
                     "src/build.bat": "@echo off\r\nset X=1\r\n"})  # quebra de linha do Windows
    assert amb.rodada() == []
    assert "\r" not in nota(amb, "referencia/src/build.bat.md")[1]  # 04/11: o \r fazia o hash não bater
    cab, corpo = nota(amb, "referencia/src/x.py.md")
    assert cab["copia_codigo"] == "true" and cab["origens"] == ["src/x.py"] and cab["commit_origem"] == c1
    assert corpo.startswith("# x.py\n\n```python\n") and "def f(): pass" in corpo
    assert "senha-do-banco" not in corpo  # os mesmos filtros de segredo da ingestão
    assert not (amb.vault / "sistemas/docs/referencia/docs").exists()  # docs/ é documentos: sem cópia
    mod = (amb.vault / "sistemas/docs/modulos/src.md").read_text()
    assert "<!-- arquivos -->" in mod and "[[sistemas/docs/referencia/src/x.py]]" in mod
    assert "[[sistemas/docs/referencia/src/y.py]]" in mod
    regra = (amb.vault / "sistemas/docs/regras/limite-de-peso.md").read_text()
    assert "[[sistemas/docs/referencia/src/x.py]]" in regra and "src/y.py]]" not in regra
    antes = fila()
    assert amb.rodada() == [] and fila() == antes  # rodada sem mudança: nada novo, nada regravado
    assert (amb.vault / "sistemas/docs/modulos/src.md").read_text() == mod

    # Código ↔ código + cópia literal: só as cópias e os blocos mudam; a fila não ganha item.
    _editar(amb, leituras("codigo"))
    assert amb.rodada() == [] and fila() == antes
    assert not list((amb.vault / "sistemas/docs/referencia").rglob("*.md"))
    assert "<!-- arquivos -->" not in (amb.vault / "sistemas/docs/modulos/src.md").read_text()
    assert nota(amb, "modulos/src.md")[0]["origens"] == ["src/build.bat", "src/x.py", "src/y.py"]  # o conhecimento fica
    _editar(amb, leituras("codigo-literal"))
    assert amb.rodada() == [] and fila() == antes
    assert (amb.vault / "sistemas/docs/referencia/src/x.py.md").exists()

    # Arquivo mudou: a cópia acompanha; apagado: a cópia e o link saem.
    c2 = amb.commit({"src/y.py": "def g(): return 2\n"}, remover=["src/x.py"])
    assert amb.rodada() == []
    cab, corpo = nota(amb, "referencia/src/y.py.md")
    assert "return 2" in corpo and cab["commit_origem"] == c2
    assert not (amb.vault / "sistemas/docs/referencia/src/x.py.md").exists()
    assert "src/x.py]]" not in (amb.vault / "sistemas/docs/modulos/src.md").read_text()

    # A cópia editada no vault é acusada como as outras notas literais, e a rodada seguinte a refaz.
    c = amb.vault / "sistemas/docs/referencia/src/y.py.md"
    amb.notas.escrever(c, cab, corpo.replace("return 2", "return 3"))
    assert any("nota literal editada" in e for e in amb.verificacao.verificar(amb.db, "docs"))
    assert amb.rodada() == [] and "return 2" in nota(amb, "referencia/src/y.py.md")[1]


def test_cabecalho_com_aspas_sobrevive_a_regravacao(amb, tmp_path):
    """ (04/11): ler desfaz o escape de escrever; antes, cada regravação dobrava as barras."""
    c = tmp_path / "n.md"
    resumo = 'Devolve saude_coleta "n/a": não trava o ciclo (C:\\temp)'
    amb.notas.escrever(c, {"resumo": resumo, "outro": "'simples'"}, "# n\n")
    for _ in range(3):
        cab, corpo = amb.notas.ler(c)
        amb.notas.escrever(c, cab, corpo)
    assert amb.notas.ler(c)[0]["resumo"] == resumo


def test_consertar_cabecalho_com_escape_repetido(amb):
    """04/11: o resumo regravado antes da correção ficou com barras a mais; a leitura desfaz e o comando limpa o arquivo."""
    c = amb.vault / "sistemas/docs/regras/r.md"
    c.parent.mkdir(parents=True)
    c.write_text('---\nresumo: "devolve \\\\\\\\\\\\\\"n/a\\\\\\\\\\\\\\" sem travar"\n---\n# r\n', encoding="utf-8")
    assert amb.notas.ler(c)[0]["resumo"] == 'devolve "n/a" sem travar'
    assert amb.notas.main(["consertar-cabecalhos", "docs"]) == 0
    assert c.read_text(encoding="utf-8") == '---\nresumo: devolve "n/a" sem travar\n---\n# r\n'
    assert amb.notas.consertar_cabecalhos("docs") == []  # já limpo: não regrava
