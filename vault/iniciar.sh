#!/bin/sh
# Serviço vault-init (DV-289): clona o vault de conteúdo no volume na primeira
# subida, ou atualiza (só fast-forward) se já existir, e entrega os volumes ao
# usuário 10000 (curador e API). Roda uma vez e termina. Adaptado do
# vault-init do Petro Observer (DV-63).
#
# A chave de deploy é montada só aqui, em /run/vault-key. O curador recebe uma
# cópia no volume dele (para o push); a API nunca a vê. O mesmo vale para as
# chaves só leitura das origens (/run/origens-chaves/<tag>, DV-290).
set -eu
DESTINO=/opt/vault
: "${VAULT_REPO:?VAULT_REPO vazio no .env}"
export GIT_SSH_COMMAND="ssh -i /run/vault-key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/known_hosts"
git config --global --add safe.directory "$DESTINO"

if [ -d "$DESTINO/.git" ]; then
  echo "[vault-init] atualizando $DESTINO"
  git -C "$DESTINO" pull --ff-only
else
  echo "[vault-init] clonando $VAULT_REPO"
  rm -rf "$DESTINO.tmp"
  git clone "$VAULT_REPO" "$DESTINO.tmp"
  # O volume já existe como diretório: move o conteúdo para dentro dele.
  cp -a "$DESTINO.tmp/." "$DESTINO/"
  rm -rf "$DESTINO.tmp"
fi
chown -R 10000:10000 "$DESTINO" /opt/estado /opt/curador
install -o 10000 -g 10000 -m 600 /run/vault-key /opt/curador/vault-key
# Chaves só leitura das origens (DV-290): uma por tag, com o nome da tag.
# O diretório é espelhado: chave que saiu do host sai do curador.
rm -rf /opt/curador/origens
install -d -o 10000 -g 10000 -m 700 /opt/curador/origens
for chave in /run/origens-chaves/*; do
  [ -f "$chave" ] || continue
  case "${chave##*/}" in *.pub) continue ;; esac
  install -o 10000 -g 10000 -m 600 "$chave" "/opt/curador/origens/${chave##*/}"
  echo "[vault-init] chave da origem: ${chave##*/}"
done
# Chave privada do GitHub App (DV-573), se houver: só o curador a recebe.
rm -f /opt/curador/github-app.pem
if [ -s /run/github-app.pem ]; then
  install -o 10000 -g 10000 -m 600 /run/github-app.pem /opt/curador/github-app.pem
  echo "[vault-init] chave do GitHub App copiada"
fi
echo "[vault-init] pronto: $(git -C "$DESTINO" log -1 --format='%h %s')"
