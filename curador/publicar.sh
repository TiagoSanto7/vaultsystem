#!/bin/sh
# Publica o vault de conteúdo (DV-289): commit do que mudou e push. Sem
# mudança, não faz nada. Se o push falhar (rede, GitHub), o commit fica local
# e sobe na próxima rodada. Adaptado do publicar.sh do Petro Observer (DV-63).
#
# Com caminhos (`publicar.sh sistemas/a sistemas/b`, o coordenador do DV-606):
# só essas pastas e a base (_regras, _templates) entram no commit. Os outros
# vaults podem estar no meio de um lote noutro trabalhador e ficam de fora.
set -u
cd "${VAULT_DIR:-/opt/vault}" || exit 1
export GIT_SSH_COMMAND="ssh -i /opt/curador/vault-key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/opt/curador/known_hosts"
git config user.name "petro-vault-curador"
git config user.email "curador@petro-vault.local"
if [ "$#" -gt 0 ]; then
  for c in "$@" _regras _templates; do
    [ -e "$c" ] || git ls-files --error-unmatch "$c" >/dev/null 2>&1 && git add -A -- "$c"
  done
else
  git add -A
fi
if git diff --cached --quiet; then
  echo "[publicar] nada mudou"
else
  # Resumo por tag (sistemas/<tag>/...) e pelas pastas da base.
  resumo=$(git diff --cached --name-only | awk -F/ '{print ($1 == "sistemas" && NF > 2) ? $2 : $1}' | sort | uniq -c | awk '{printf "%s %s, ", $1, $2}' | sed 's/, $//')
  git commit -q -m "Curador: rodada de $(date '+%d/%m %H:%M') ($resumo)"
  echo "[publicar] commit: $(git log -1 --format='%h %s')"
fi
if [ -n "$(git log --oneline @{u}..HEAD 2>/dev/null)" ]; then
  # Sem rebase: com outro vault no meio de um lote, a pasta de trabalho não está limpa. O remoto só recebe
  # commit do curador; se o push for recusado, um merge traz o que faltar e tenta de novo.
  if git push -q 2>/dev/null || { git pull -q --no-rebase --no-edit && git push -q; }; then
    echo "[publicar] enviado ao repositório"
  else
    echo "[publicar] push falhou; tenta de novo na próxima rodada"
  fi
fi
