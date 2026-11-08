"""Rodada do curador (DV-291): ingestão, curadoria, índices e verificador.

  python -m petro_vault.rodada todos     a rodada de VAULT_INTERVALO: todos os sistemas
  python -m petro_vault.rodada pedidos   só os sistemas com pull pedido pela API
  python -m petro_vault.rodada tag <tag> [pull|agenda]
                                         um vault só: o que cada trabalhador do coordenador roda
                                         (DV-606); sem remoções de cadastro nem lista do GitHub

As duas começam pelas remoções de cadastro pedidas pela API e pela lista de
repositórios do GitHub App, quando a tela pediu ou está velha (DV-573).

Sai com 0 se algo foi feito (o ciclo publica em seguida) e com 3 se não havia
nada a fazer (modo pedidos sem pedido).
"""
import fcntl
import os
import shutil
import sys

from . import curadoria, estado, github_app, historico, ingestao, notas, vault_i, verificacao


def remover_cadastros(db, pular=()):
    """Sistemas com remoção pedida pela API (DELETE /v1/sistemas/<tag>): sai a
    pasta da tag no vault (o publicar faz o commit), o clone, os lotes, a fila,
    os pulls, o índice de notas (busca e MCP), avisos, verificação e o
    cadastro. As rodadas ficam (são de várias tags). A chave de deploy no host
    fica (apagar à mão)."""
    tags = [l["tag"] for l in db.execute("SELECT tag FROM sistemas WHERE removido_em IS NOT NULL")
            if l["tag"] not in pular]  # vault que um trabalhador está curando sai na volta seguinte (DV-606)
    for tag in tags:
        pastas = [notas.pasta_tag(tag), os.path.join(estado.dir_estado(), "lotes", tag)]
        pastas += [ingestao.dir_clone(tag, o["nome"]) for o in db.execute("SELECT nome FROM origens WHERE tag = ?", (tag,))]
        for pasta in pastas:
            shutil.rmtree(pasta, ignore_errors=True)
        with db:
            # Tudo o que é da tag (DV-600, 03/11): sem isso, o vault recriado com a mesma tag herdava as notas
            # da busca/MCP, os avisos, os lotes e a verificação do anterior.
            for tabela in ("fila", "pulls", "origens", "notas_indice", "meta_tag", "verificacoes", "problemas",
                           "avisos", "lotes", "sistemas"):
                db.execute(f"DELETE FROM {tabela} WHERE tag = ?", (tag,))
        print(f"[rodada] cadastro removido: {tag} (pasta no vault, clone, lotes e fila)")
    return tags


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:] or ["pedidos"]
    modo = args[0]
    if modo == "tag" and len(args) >= 2:
        return um_vault(args[1], args[2] if len(args) > 2 else "agenda")
    if modo not in ("todos", "pedidos"):
        sys.exit(__doc__)
    db = estado.conectar()
    with open(os.path.join(estado.dir_estado(), "ingestao.lock"), "w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        removidos = remover_cadastros(db)
        github_app.atualizar_lista(db)  # lista de repositórios da tela (DV-573)
        if modo == "todos":
            tags = [l["tag"] for l in db.execute(estado.ATIVOS)]
        else:
            tags = [l["tag"] for l in db.execute(
                "SELECT DISTINCT p.tag FROM pulls p JOIN sistemas s ON s.tag = p.tag "
                "WHERE p.atendido_em IS NULL AND s.removido_em IS NULL ORDER BY p.tag")]
        if not tags:
            if modo == "todos":
                historico.fechar_rodada(db, "nenhum sistema", historico.intervalo())
            return 3 if modo == "pedidos" and not removidos else 0
        historico.abrir_rodada(db, modo, tags)
        ingestao._atender(db, tags)
    resultado = "erro"
    try:
        falhou = curadoria.main(tags)  # um sistema com erro não impede a verificação dos outros
        for t in tags:
            vault_i.atender(db, t)  # Vault-I: só o que foi pedido (painel ou vs sync --curate)
        problemas = verificacao.main(tags)
        resultado = "erro" if falhou else "com problemas na verificação" if problemas else "concluída"
    finally:
        historico.fechar_rodada(db, resultado, historico.intervalo() if modo == "todos" else None)
    return 0


def um_vault(tag, motivo="agenda"):
    """Uma rodada de um vault só (DV-606): ingestão, curadoria e verificação. O coordenador garante que o mesmo
    vault não roda em dois trabalhadores; a ingestão (fetch e fila) continua em série entre eles, porque é curta."""
    db = estado.conectar()
    s = db.execute("SELECT removido_em FROM sistemas WHERE tag = ?", (tag,)).fetchone()
    if not s or s["removido_em"]:
        return 3
    historico.abrir_rodada(db, motivo, [tag])
    with open(os.path.join(estado.dir_estado(), "ingestao.lock"), "w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        ingestao._atender(db, [tag])
    resultado = "erro"
    try:
        falhou = curadoria.main([tag])
        vault_i.atender(db, tag)  # Vault-I: só o que foi pedido (painel ou vs sync --curate)
        problemas = verificacao.main([tag])
        resultado = "erro" if falhou else "com problemas na verificação" if problemas else "concluída"
    finally:
        historico.fechar_rodada(db, resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
