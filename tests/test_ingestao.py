"""Testes da ingestão (DV-290): a fila é o diff real, e segredo não chega ao lote."""
import importlib
import json
import subprocess

import pytest

TOKEN_FALSO = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    estado_dir, chaves = tmp_path / "estado", tmp_path / "chaves"
    chaves.mkdir()
    (chaves / "sis").write_text("chave de teste (o repositório é local, não usa ssh)")
    monkeypatch.setenv("ESTADO_DIR", str(estado_dir))
    monkeypatch.setenv("VAULT_ORIGENS_CHAVES_DIR", str(chaves))
    from petro_vault import estado, filtros, ingestao
    importlib.reload(filtros)
    importlib.reload(ingestao)

    origem = tmp_path / "origem"
    origem.mkdir()
    git(origem, "init", "-q", "-b", "main")
    git(origem, "config", "user.name", "teste")
    git(origem, "config", "user.email", "teste@teste")
    db = estado.conectar()
    with db:
        db.execute("INSERT INTO sistemas (tag, perfil, repo, ramo, incluir, excluir, criado_em, criado_por) "
                   "VALUES ('sis', 'documentos', ?, 'main', '[]', ?, 'x', 'teste')",
                   (str(origem), json.dumps(["rascunhos/*"])))
    return origem, estado_dir, db, ingestao


def escrever(origem, arquivos):
    for caminho, conteudo in arquivos.items():
        alvo = origem / caminho
        alvo.parent.mkdir(parents=True, exist_ok=True)
        (alvo.write_bytes if isinstance(conteudo, bytes) else alvo.write_text)(conteudo)


def commit(origem, msg):
    git(origem, "add", "-A")
    git(origem, "commit", "-q", "-m", msg)
    return git(origem, "rev-parse", "HEAD").strip()


def rodar(db, ingestao):
    ingestao._atender(db, ["sis"])
    return db.execute("SELECT acao, caminho, commit_origem, lote, motivo FROM fila WHERE estado = 'na_fila' ORDER BY id").fetchall()


def esperado_do_git(origem, de, para):
    """O que o `git diff --name-status --find-renames` real diz, com renomeado
    expandido em removido + adicionado."""
    nomes = {"A": "adicionado", "M": "modificado", "D": "removido"}
    saida = set()
    for linha in git(origem, "diff", "--name-status", "--find-renames", de, para).splitlines():
        partes = linha.split("\t")
        if partes[0].startswith("R"):
            saida |= {("removido", partes[1]), ("adicionado", partes[2])}
        else:
            saida.add((nomes[partes[0][0]], partes[1]))
    return saida


def test_dois_commits_fila_igual_ao_diff_real(ambiente):
    origem, estado_dir, db, ingestao = ambiente
    escrever(origem, {
        "README.md": "# Sistema\n",
        "docs/manual.md": "Manual de uso.\n" * 30,
        "docs/antigo.md": "Documento que vai ser renomeado, com bastante texto igual.\n" * 20,
        "docs/vai-sair.md": "Este sai no segundo commit.\n",
        "config/.env": f"DB_PASSWORD=senha-real-123\nGITHUB_TOKEN={TOKEN_FALSO}\n",
        "config/app.yml": f"github_token: {TOKEN_FALSO}\nbanco: postgres://app:SenhaForte99@db:5432/app\n",
        "certs/servidor.pem": "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n",
        "node_modules/lib/index.js": "module.exports = 1\n",
        "package-lock.json": "{}\n",
        "imagem.png": b"\x89PNG\r\n\x1a\n\0\0\0binario",
        "rascunhos/ideia.md": "excluído pelo cadastro\n",
    })
    c1 = commit(origem, "primeiro")

    itens = rodar(db, ingestao)
    assert {(i["acao"], i["caminho"]) for i in itens} == {
        ("adicionado", p) for p in ("README.md", "docs/manual.md", "docs/antigo.md", "docs/vai-sair.md", "config/app.yml")}
    assert all(i["commit_origem"] == c1 for i in itens)
    sistema = db.execute("SELECT commit_pendente, commit_processado FROM origens").fetchone()
    assert sistema["commit_pendente"] == c1 and sistema["commit_processado"] is None

    # Segundo commit: modifica, renomeia, remove e adiciona.
    escrever(origem, {"docs/manual.md": "Manual de uso, revisto.\n" * 30, "docs/novo.md": "Novo.\n"})
    git(origem, "mv", "docs/antigo.md", "docs/renomeado.md")
    git(origem, "rm", "-q", "docs/vai-sair.md")
    c2 = commit(origem, "segundo")

    db.execute("UPDATE fila SET estado = 'registrado'")  # como se o curador tivesse visto o 1º
    db.commit()
    itens = rodar(db, ingestao)
    obtido = {(i["acao"], i["caminho"]) for i in itens}
    assert obtido == esperado_do_git(origem, c1, c2)
    assert obtido == {("modificado", "docs/manual.md"), ("adicionado", "docs/novo.md"),
                      ("removido", "docs/antigo.md"), ("adicionado", "docs/renomeado.md"),
                      ("removido", "docs/vai-sair.md")}
    assert all(i["commit_origem"] == c2 for i in itens)
    assert all(i["lote"] is None for i in itens if i["acao"] == "removido")


def test_segredo_nao_chega_ao_lote(ambiente):
    origem, estado_dir, db, ingestao = ambiente
    escrever(origem, {
        ".env": "SENHA=nao-pode-aparecer-1\n",
        "deploy/prod.env": "SENHA=nao-pode-aparecer-2\n",
        "chaves/id_ed25519": "nao-pode-aparecer-3\n",
        "docs/chave.txt": "-----BEGIN OPENSSH PRIVATE KEY-----\nnao-pode-aparecer-4\n-----END OPENSSH PRIVATE KEY-----\n",
        "docs/integracao.md": f"Use o token {TOKEN_FALSO} no cabeçalho.\napi_key = \"sk-fake-0123456789abcdefghijkl\"\n"
                              "senha: Segredo#Forte2026\ntoken = os.environ.get(\"API_TOKEN\")\n",
        ".env.example": "SENHA=troque-por-uma-senha-real\n",
    })
    commit(origem, "segredos")
    itens = rodar(db, ingestao)
    assert {i["caminho"] for i in itens} == {"docs/integracao.md", ".env.example"}

    lotes = estado_dir / "lotes"
    tudo = "".join(p.read_text() for p in lotes.rglob("*") if p.is_file())
    for proibido in ("nao-pode-aparecer", TOKEN_FALSO, "sk-fake-0123456789", "Segredo#Forte2026", "troque-por-uma-senha-real"):
        assert proibido not in tudo
    integracao = (lotes / itens[0]["lote"]).read_text() if itens[0]["caminho"] == "docs/integracao.md" else \
        (lotes / itens[1]["lote"]).read_text()
    assert "«segredo-removido»" in integracao
    assert 'token = os.environ.get("API_TOKEN")' in integracao  # código não é mascarado
    # O clone é bare: nenhum arquivo da origem existe como arquivo no disco.
    assert not list((estado_dir / "origens" / "sis").rglob(".env"))


def test_modificado_que_deixa_de_passar_vira_removido_e_substitui(ambiente, monkeypatch):
    origem, estado_dir, db, ingestao = ambiente
    escrever(origem, {"docs/a.md": "pequeno\n"})
    commit(origem, "1")
    rodar(db, ingestao)
    monkeypatch.setattr(ingestao.filtros, "LIMITE_BYTES", 100)
    escrever(origem, {"docs/a.md": "grande\n" * 100})
    commit(origem, "2")
    itens = rodar(db, ingestao)
    # O item de 'adicionado' que o curador ainda não viu foi substituído.
    assert [(i["acao"], i["caminho"]) for i in itens] == [("removido", "docs/a.md")]
    assert "deixou de passar" in itens[0]["motivo"]
    assert not [p for p in (estado_dir / "lotes").rglob("*") if p.is_file()]


def test_sem_mudanca_e_erro_de_chave(ambiente, tmp_path):
    origem, estado_dir, db, ingestao = ambiente
    escrever(origem, {"a.md": "a\n"})
    commit(origem, "1")
    rodar(db, ingestao)
    with db:
        db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES ('sis', 'x', 'teste')")
    ingestao._atender(db, ["sis"])
    r = json.loads(db.execute("SELECT resultado FROM pulls").fetchone()["resultado"])
    assert r.get("nada_novo") is True
    (tmp_path / "chaves" / "sis").unlink()
    with db:
        db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES ('sis', 'x', 'teste')")
    ingestao._atender(db, ["sis"])
    r = json.loads(db.execute("SELECT resultado FROM pulls ORDER BY id DESC").fetchone()["resultado"])
    assert "chave de deploy da origem não encontrada" in r["erro"]


def test_mascara_nao_estraga_css():
    """DV-600: pseudo-classe de CSS num seletor com "password"/"token" não é segredo
    (o vault de Referência copia o CSS como está); valor de verdade continua mascarado."""
    from petro_vault import filtros
    for css in (".password-toggle:focus-visible{outline:none}", ".password-field:placeholder-shown, .x{}",
                "input.token-input:-webkit-autofill{}", ".senha:not(.vazia){}", ".token:hover .x{}",
                "passErr=!pass?'Informe sua senha.':pass.length<6?'A senha deve ter'"):
        assert filtros.mascarar(css) == (css, 0), css
    for segredo in ("password: hunter2hunter2", "client_secret=focusABCDEF123456", "secret: focus12345678",
                    "password=hoverhoverhover", "db.password: Sup3rS3cr3t!"):
        assert filtros.mascarar(segredo)[1] == 1, segredo



def test_mascarar_e_idempotente():
    """Texto já mascarado não conta de novo (o .env.example literal não vira "possível segredo", DV-604)."""
    from petro_vault import filtros
    texto, n = filtros.mascarar("DATABASE_URL=mysql://app:S3nh4@10.2.2.6:3306/x\nTOKEN=abcdefghij123\n")
    assert n == 2 and "S3nh4" not in texto and "abcdefghij123" not in texto
    assert "10.2.2.6:3306" in texto  # o host fica
    assert filtros.mascarar(texto) == (texto, 0)
