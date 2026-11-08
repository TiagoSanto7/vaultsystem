"""Atendente do curador: responde a tela em poucos segundos, sem
esperar o ciclo de 30 s. Olha o estado.db a cada INTERVALO segundos e atende:

- pedidos de árvore de um repositório do GitHub App (Novo vault);
- pedido de atualizar a lista de repositórios do App.

Só leitura no GitHub e escrita no estado.db; não mexe na fila nem no vault.
Roda em segundo plano no ciclo do curador (curador/ciclo.sh).
"""
import time

from . import arvore, estado, github_app

INTERVALO = 2


def uma_vez(db):
    arvore.atender(db)
    github_app.atualizar_lista(db)


def main():
    db = estado.conectar()
    print("[atendente] pronto")
    while True:
        try:
            uma_vez(db)
        except Exception as e:  # noqa: BLE001 - o atendente não para por um pedido ruim
            print(f"[atendente] erro: {e}")
        time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
