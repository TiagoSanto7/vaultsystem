"""Gestão de credenciais pela linha de comando (DV-289).

Dentro do container da API:
  python -m app.cli criar <nome> --ler tag1,tag2 --escrever tag1
  python -m app.cli criar <nome> --workspace        token de conexão da CLI (vs login)
  python -m app.cli usuario <login> [--nome "Nome"]  conta local do hub (senha pedida sem eco,
                                                     ou pela entrada padrão com --senha-stdin)
  python -m app.cli listar
  python -m app.cli revogar <nome>

A chave aparece só na criação. Guarde-a no .env do cliente; aqui fica só o hash.
"""
import argparse
import getpass
import sys

from . import credenciais, sessao


def _tags(texto):
    return [t.strip() for t in texto.split(",") if t.strip()]


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("criar")
    c.add_argument("nome")
    c.add_argument("--ler", default="")
    c.add_argument("--escrever", default="")
    c.add_argument("--workspace", action="store_true")
    u = sub.add_parser("usuario")
    u.add_argument("login")
    u.add_argument("--nome")
    u.add_argument("--senha-stdin", action="store_true")
    sub.add_parser("listar")
    r = sub.add_parser("revogar")
    r.add_argument("nome")
    a = p.parse_args(argv)

    if a.comando == "criar":
        try:
            chave = credenciais.criar(a.nome, _tags(a.ler), _tags(a.escrever), workspace=a.workspace)
        except ValueError as e:
            sys.exit(str(e))
        print(f"Credencial '{a.nome}' criada. Chave (aparece só agora):\n{chave}")
    elif a.comando == "usuario":
        senha = sys.stdin.readline().rstrip("\r\n") if a.senha_stdin else getpass.getpass("Senha (não aparece): ")
        try:
            login = sessao.criar_usuario(a.login, senha, a.nome)
        except ValueError as e:
            sys.exit(str(e))
        print(f"Conta local '{login}' pronta. Entre no hub com esse login.")
    elif a.comando == "listar":
        for l in credenciais.listar():
            estado = f"revogada em {l['revogada_em']}" if l["revogada_em"] else "ativa"
            print(f"{l['nome']}: ler {l['ler']}, escrever {l['escrever']}, criada em {l['criado_em']}, {estado}")
    elif a.comando == "revogar":
        if not credenciais.revogar(a.nome):
            sys.exit(f"nenhuma credencial ativa com o nome {a.nome}")
        print(f"Credencial '{a.nome}' revogada.")


if __name__ == "__main__":
    main()
