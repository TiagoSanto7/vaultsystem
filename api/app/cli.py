"""Gestão de credenciais pela linha de comando (DV-289).

Dentro do container da API:
  python -m app.cli criar <nome> --ler tag1,tag2 --escrever tag1
  python -m app.cli listar
  python -m app.cli revogar <nome>

A chave aparece só na criação. Guarde-a no .env do cliente; aqui fica só o hash.
"""
import argparse
import sys

from . import credenciais


def _tags(texto):
    return [t.strip() for t in texto.split(",") if t.strip()]


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("criar")
    c.add_argument("nome")
    c.add_argument("--ler", default="")
    c.add_argument("--escrever", default="")
    sub.add_parser("listar")
    r = sub.add_parser("revogar")
    r.add_argument("nome")
    a = p.parse_args(argv)

    if a.comando == "criar":
        try:
            chave = credenciais.criar(a.nome, _tags(a.ler), _tags(a.escrever))
        except ValueError as e:
            sys.exit(str(e))
        print(f"Credencial '{a.nome}' criada. Chave (aparece só agora):\n{chave}")
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
