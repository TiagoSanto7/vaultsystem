"""Atendente do curador: responde a tela em poucos segundos, sem
esperar o ciclo de 30 s. Olha o estado.db a cada INTERVALO segundos e atende:

- pedidos de árvore de um repositório do GitHub App (Novo vault);
- pedido de atualizar a lista de repositórios do App;
- perguntas da conversa com o Vault-I (vault_system/conversa.py), em segundo plano.

Só leitura no GitHub e escrita no estado.db; não mexe na fila nem no vault.
Roda em segundo plano no ciclo do curador (curador/ciclo.sh).
"""
import time

from . import arvore, conversa, estado, github_app

INTERVALO = 2


def uma_vez(db):
    arvore.atender(db)
    github_app.atualizar_lista(db)
    if db.execute("SELECT 1 FROM mensagens WHERE estado = 'pendente' LIMIT 1").fetchone():
        conversa.atender()


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
