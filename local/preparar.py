"""Prepara o ambiente local do Vault System (uma vez): local/.env e local/dados.

    py -3 local/preparar.py [--porta 8790] [--login tiago]

Cria o vault de conteúdo como repositório git local, uma chave de deploy de
mentira (o vault local não usa SSH), a pasta de chaves das origens (vazia) e o
.env com um segredo de sessão e a senha da primeira conta do hub, gerados aqui.
A senha aparece só no local/.env (fora do git). Não sobrescreve nada que exista.
"""
import argparse
import os
import secrets
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(AQUI, "dados")


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--porta", default="8790")
    p.add_argument("--login", default="admin")
    a = p.parse_args()
    os.makedirs(os.path.join(DADOS, "origens"), exist_ok=True)
    chave = os.path.join(DADOS, "deploy-key")
    if not os.path.exists(chave):
        with open(chave, "w") as f:
            f.write("sem uso no ambiente local\n")
    repo = os.path.join(DADOS, "conteudo.git")
    if not os.path.isdir(repo):
        git("init", "-q", "--bare", "-b", "main", repo)
        with tempfile.TemporaryDirectory() as t:
            git("init", "-q", "-b", "main", t)
            with open(os.path.join(t, "README.md"), "w", encoding="utf-8") as f:
                f.write("# Vault de conteúdo (ambiente local)\n")
            git("add", ".", cwd=t)
            git("-c", "user.name=vault-system-local", "-c", "user.email=vault@localhost", "commit", "-qm", "início", cwd=t)
            git("push", "-q", repo, "main", cwd=t)
    env = os.path.join(AQUI, ".env")
    if os.path.exists(env):
        print(f"{env} já existe: nada mudou.")
        return 0
    senha = secrets.token_urlsafe(12)
    linhas = {
        "COMPOSE_PROJECT_NAME": "vault-system-local",
        "API_PORTA": a.porta, "API_BIND": "127.0.0.1",
        "VAULT_URL_PUBLICA": f"http://127.0.0.1:{a.porta}",
        "VAULT_ADMIN_LOGIN": a.login, "VAULT_ADMIN_SENHA": senha, "VAULT_ADMIN_NOME": a.login,
        "VAULT_SESSAO_SEGREDO": secrets.token_urlsafe(48),
        "VAULT_AMBIENTE": "local",
        "VAULT_REPO": "/srv/conteudo.git",
        "VAULT_DEPLOY_KEY_FILE": chave.replace(os.sep, "/"),
        "VAULT_ORIGENS_CHAVES_DIR": os.path.join(DADOS, "origens").replace(os.sep, "/"),
        "VAULT_GITHUB_APP_ID": "",
        "VAULT_INTERVALO": "300",
        "VAULT_CURADORIA_PROVEDOR": "", "VAULT_CURADORIA_CHAVE": "", "VAULT_CLAUDE_CODE_OAUTH_TOKEN": "",
    }
    with open(env, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Gerado por local/preparar.py. Fora do git.\n")
        f.writelines(f"{k}={v}\n" for k, v in linhas.items())
    print(f"Pronto: {env}\nConta do hub: {a.login} (a senha está em VAULT_ADMIN_SENHA, nesse arquivo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
