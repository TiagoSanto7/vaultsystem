#!/bin/sh
# Ciclo do curador. Uma rodada:
#   1. ingestão  (sem LLM, DV-290): fetch, diff, filtros e fila de cada sistema
#   2. curadoria (LLM só no passo organizar, DV-291): remoções, lotes por tag,
#                pós-lote (cabeçalho, notas vazias, registro, commit processado)
#   3. índices e verificador por tag (sem LLM)
#   4. base      (sem LLM): _regras/ e _templates/ iguais às do repositório
#   5. publicar:            commit e push para o vault de conteúdo
# Os passos 1 a 3 são o `python -m petro_vault.rodada`.
#
# Desde o DV-606, quem roda é o coordenador (petro_vault/coordenador.py): até
# VAULT_TRABALHADORES vaults ao mesmo tempo (padrão 3), cada um num processo
# com pasta de lote e HERMES_HOME próprios. Pull pedido pela API passa na
# frente; cada vault volta pela agenda a cada VAULT_INTERVALO s (padrão 900).
# A publicação (base + commit + push) é em série e só das pastas dos vaults
# que terminaram. `ciclo.sh uma-vez` ainda roda a rodada antiga, sequencial.
#
# Em segundo plano, o atendente (DV-589) responde a tela em poucos segundos:
# árvore de um repositório do GitHub App e a lista de repositórios.
set -u
PY=/opt/hermes/.venv/bin/python
D=/opt/petro-vault/curador

publicar() {
  $PY $D/base.py || echo "[curador] base falhou"
  sh $D/publicar.sh || echo "[curador] publicação falhou"
}
rodada() {
  echo "[curador] rodada $(date '+%d/%m %H:%M')"
  $PY -m petro_vault.rodada todos || echo "[curador] rodada com problemas (ver acima)"
  publicar
}
if [ "${1:-}" = "uma-vez" ]; then rodada; exit 0; fi
( while :; do $PY -u -m petro_vault.atendente; echo "[curador] atendente parou; volta em 5 s"; sleep 5; done ) &
# O coordenador não termina; se cair, volta em 5 s (o que estava aberto fecha como interrompido).
while :; do
  $PY -u -m petro_vault.coordenador
  echo "[curador] coordenador parou; volta em 5 s"
  sleep 5
done
