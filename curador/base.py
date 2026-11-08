"""Base do vault (DV-289): espelha vault-base/ do repositório em /opt/vault.

Sem LLM. As pastas da base (_regras/, _templates/) ficam iguais às do
repositório do serviço: arquivo novo ou mudado é copiado, arquivo que saiu da
base é apagado. O resto do vault (sistemas/, README.md) não é tocado.
"""
import filecmp
import os
import shutil
import sys

BASE = os.environ.get("VAULT_BASE_DIR", "/opt/petro-vault/vault-base")
VAULT = os.environ.get("VAULT_DIR", "/opt/vault")
PASTAS = ("_regras", "_templates")


def arquivos(raiz):
    saida = set()
    for base, _dirs, nomes in os.walk(raiz):
        for nome in nomes:
            saida.add(os.path.relpath(os.path.join(base, nome), raiz))
    return saida


def main():
    mudou = 0
    for pasta in PASTAS:
        origem, destino = os.path.join(BASE, pasta), os.path.join(VAULT, pasta)
        if not os.path.isdir(origem):
            print(f"[base] {origem} não existe", file=sys.stderr)
            return 1
        os.makedirs(destino, exist_ok=True)
        na_base, no_vault = arquivos(origem), arquivos(destino)
        for rel in sorted(na_base):
            a, b = os.path.join(origem, rel), os.path.join(destino, rel)
            if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copyfile(a, b)
                print(f"[base] atualizado: {pasta}/{rel}")
                mudou += 1
        for rel in sorted(no_vault - na_base):
            os.remove(os.path.join(destino, rel))
            print(f"[base] removido (saiu da base): {pasta}/{rel}")
            mudou += 1
    print(f"[base] {mudou} arquivo(s) mudado(s)" if mudou else "[base] já igual à base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
