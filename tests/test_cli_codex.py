"""O adaptador do Codex usa o protocolo MCP real com o binário do agente simulado."""
import io
import json
import os
from pathlib import Path
import runpy
import sys
import zipfile

import pytest


CLI = Path(__file__).resolve().parents[1] / "cli" / "vs.py"
CHAVE = "sk-proj-" + "x" * 24
NOTA = "---\nvs: regra\ntitulo: Preços\norigens:\n  - app.py\n---\n# Preços\n\nLimite de 15%.\n"

CODEX_FALSO = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

cenario = Path(__file__).with_name("cenario").read_text()
Path(__file__).with_name("iniciado").touch()
if sys.argv[-2:] == ["login", "status"]:
    sys.exit(1 if cenario == "sem-login" else 0)

assert "exec" in sys.argv and "--ignore-user-config" in sys.argv
assert "features.shell_tool=false" in sys.argv
assert "features.apps=false" in sys.argv and "features.hooks=false" in sys.argv
assert "features.view_image=false" in sys.argv
assert "mcp_servers.vs_curadoria.default_tools_approval_mode=\"approve\"" in sys.argv
assert "VS_TOKEN" not in os.environ and "VS_AGENT_TOKEN" not in os.environ
if cenario == "chave":
    assert os.environ["CODEX_API_KEY"] == "sk-proj-" + "x" * 24
else:
    assert "CODEX_API_KEY" not in os.environ
assert "AGENTS.md" in sys.stdin.read()
assert not Path("AGENTS.md").exists()

def evento(tipo, **dados):
    print(json.dumps({"type": tipo, **dados}))

if cenario != "sem-mcp":
    config = dict(arg.split("=", 1) for arg in sys.argv if arg.startswith("mcp_servers.vs_curadoria."))
    args = json.loads(config["mcp_servers.vs_curadoria.args"])
    exe = json.loads(config["mcp_servers.vs_curadoria.command"])
    with subprocess.Popen([exe, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as servidor:
        def pedir(metodo, params):
            servidor.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params}) + "\n")
            servidor.stdin.flush()
            r = json.loads(servidor.stdout.readline())
            assert r["id"] == 1 and "result" in r, r
            return r["result"]

        def chamar(nome, **args):
            return pedir("tools/call", {"name": nome, "arguments": args})

        def dados(resposta):
            assert not resposta.get("isError"), resposta
            return json.loads(resposta["content"][0]["text"])

        assert pedir("initialize", {"protocolVersion": "2025-11-25"})["capabilities"] == {"tools": {}}
        assert {t["name"] for t in pedir("tools/list", {})["tools"]} == {"listar_fontes", "ler_fonte", "propor_nota"}
        assert chamar("propor_nota", caminho="docs/vs/retirada.md", conteudo=None)["isError"]
        assert "Protocolo Vault System" in dados(chamar("ler_fonte", caminho="AGENTS.md"))["texto"]
        caminhos = dados(chamar("listar_fontes"))["caminhos"]
        assert "app.py" in caminhos and ".env" not in caminhos and "chave.pem" not in caminhos
        assert dados(chamar("ler_fonte", caminho="app.py"))["texto"] == "LIMITE = 15\n"
        assert chamar("ler_fonte", caminho="segredo.txt")["isError"]
        assert chamar("ler_fonte", caminho="../fora.txt")["isError"]
        assert chamar("propor_nota", caminho="app.py", conteudo="alterado")["isError"]
        assert chamar("propor_nota", caminho="docs/vs/../fora.md", conteudo=None)["isError"]
        assert chamar("propor_nota", caminho="docs/vs/link.md", conteudo=None)["isError"]
        nota = "---\nvs: regra\ntitulo: Preços\norigens:\n  - app.py\n---\n# Preços\n\nLimite de 15%.\n"
        dados(chamar("propor_nota", caminho="docs/vs/nova.md", conteudo=nota))
        assert dados(chamar("ler_fonte", caminho="docs/vs/nova.md"))["texto"] == nota
        dados(chamar("propor_nota", caminho="docs/vs/atualizada.md", conteudo=nota))
        dados(chamar("propor_nota", caminho="docs/vs/retirada.md", conteudo=None))
        if cenario == "nota-mudou":
            (Path(args[2]) / "docs/vs/atualizada.md").write_text("Edição concorrente\n")
        servidor.stdin.close()
        assert servidor.wait(timeout=5) == 0

evento("item.completed", item={"type": "agent_message", "text": "RESUMO: 1 criada, 1 atualizada, 1 apagada"})
evento("turn.completed")
sys.exit(7 if cenario == "falha" else 0)
'''


@pytest.fixture
def codex(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("VS_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("VS_TOKEN", "token-do-hub")
    monkeypatch.delenv("VS_AGENT_TOKEN", raising=False)
    programa = tmp_path / "codex"
    programa.write_text(f"#!{sys.executable}\n" + CODEX_FALSO, encoding="utf-8")
    programa.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)
    cenario = tmp_path / "cenario"
    cenario.write_text("sessao", encoding="utf-8")
    projeto = tmp_path / "projeto"
    (projeto / "docs/vs").mkdir(parents=True)
    (projeto / "app.py").write_text("LIMITE = 15\n", encoding="utf-8")
    (projeto / ".env").write_text("SENHA=teste\n", encoding="utf-8")
    (projeto / "chave.pem").touch()
    (projeto / "segredo.txt").write_text(CHAVE, encoding="utf-8")
    fora = tmp_path / "fora.txt"
    fora.write_text("fora do projeto", encoding="utf-8")
    (projeto / "docs/vs/link.md").symlink_to(fora)
    for nome in ("atualizada.md", "retirada.md"):
        (projeto / "docs/vs" / nome).write_text(NOTA.replace("15%", "10%"), encoding="utf-8")
    monkeypatch.chdir(projeto)
    vs = runpy.run_path(str(CLI))["main"]
    envios = []

    def enviar(tag, pacote, *_args):
        with zipfile.ZipFile(io.BytesIO(pacote)) as z:
            envios.append({n: z.read(n) for n in z.namelist()})
        return {"arquivos": len(envios[-1]), "commit": "0" * 40}

    monkeypatch.setitem(vs.__globals__, "_enviar", enviar)
    assert vs(["init", "vault=proj", "--json"]) == 0
    return vs, projeto, cenario, envios


@pytest.mark.parametrize("autenticacao", ["sessao", "chave"])
def test_codex_cura_e_envia(codex, autenticacao, monkeypatch, capsys):
    vs, projeto, cenario, envios = codex
    cenario.write_text(autenticacao, encoding="utf-8")
    if autenticacao == "chave":
        monkeypatch.setenv("VS_AGENT_TOKEN", CHAVE)
    assert vs(["login", "agent=codex", "--json"]) == 0
    capsys.readouterr()
    assert vs(["sync", "--curate", "--json"]) == 0
    resumo = json.loads(capsys.readouterr().out)["curadoria"]
    assert resumo["agent"] == "codex"
    assert resumo["criadas"] == ["docs/vs/nova.md"]
    assert resumo["atualizadas"] == ["docs/vs/atualizada.md"]
    assert resumo["apagadas"] == ["docs/vs/retirada.md"]
    assert envios[0]["docs/vs/nova.md"] == NOTA.encode()
    assert envios[0]["app.py"] == b"LIMITE = 15\n"
    assert (projeto.parent / "fora.txt").read_text() == "fora do projeto"


@pytest.mark.parametrize("motivo", ["falha", "sem-mcp", "sem-login", "nota-mudou"])
def test_codex_falha_sem_aplicar_nem_enviar(codex, motivo, capsys):
    vs, projeto, cenario, envios = codex
    cenario.write_text(motivo, encoding="utf-8")
    assert vs(["sync", "--curate", "agent=codex", "--dry-run"]) == 0
    assert not cenario.with_name("iniciado").exists()
    capsys.readouterr()
    assert vs(["sync", "--curate", "agent=codex"]) == 1
    erro = capsys.readouterr().err
    assert "nada foi enviado" in erro
    if motivo == "sem-login":
        assert "codex login" in erro
    assert not envios
    assert not (projeto / "docs/vs/nova.md").exists()
    assert (projeto / "docs/vs/retirada.md").is_file()
    if motivo == "nota-mudou":
        assert (projeto / "docs/vs/atualizada.md").read_text() == "Edição concorrente\n"


def test_codex_ausente(codex, monkeypatch, capsys):
    vs, _, _, envios = codex
    monkeypatch.setenv("PATH", "")
    assert vs(["login", "agent=codex"]) == 1
    assert "não está instalado" in capsys.readouterr().err
    assert vs(["sync", "--curate", "agent=codex"]) == 1
    assert "não está instalado" in capsys.readouterr().err
    assert not envios
