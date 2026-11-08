#!/bin/sh
# Grava o token do curador (DV-291) no .env, sem mostrar na tela.
# Uso, na raiz do repositório: sh scripts/token-curador.sh
#
# Cole o token (de `claude setup-token`) e tecle Enter numa linha vazia. Se o
# terminal quebrar o token em várias linhas ao colar, as linhas são juntadas.
# Só a linha VAULT_CLAUDE_CODE_OAUTH_TOKEN do .env muda; as outras chaves são
# conferidas antes e depois.
set -eu
ENV=.env
[ -f "$ENV" ] || { echo "rode na raiz do petro-vault (não achei o .env)"; exit 1; }
echo "Cole o token e tecle Enter numa linha vazia:"
stty -echo 2>/dev/null || true
token=""
while IFS= read -r linha; do
  [ -z "$linha" ] && break
  token="$token$linha"
done
stty echo 2>/dev/null || true
token=$(printf '%s' "$token" | tr -d ' \t\r\n')
case "$token" in
  sk-ant-oat*) ;;
  *) echo "isso não parece um token de setup-token (esperado sk-ant-oat...); nada mudou"; exit 1 ;;
esac
antes=$(grep -oE '^[A-Z_]+=' "$ENV" | sort)
tmp=$(mktemp "$ENV.XXXXXX")
if grep -q '^VAULT_CLAUDE_CODE_OAUTH_TOKEN=' "$ENV"; then
  awk -v t="$token" '/^VAULT_CLAUDE_CODE_OAUTH_TOKEN=/ {print "VAULT_CLAUDE_CODE_OAUTH_TOKEN=" t; next} {print}' "$ENV" > "$tmp"
else
  { cat "$ENV"; printf '\n# --- Curadoria com LLM (DV-291) ---\nVAULT_CLAUDE_CODE_OAUTH_TOKEN=%s\n' "$token"; } > "$tmp"
fi
chmod 600 "$tmp"
depois=$(grep -oE '^[A-Z_]+=' "$tmp" | sort | grep -v '^VAULT_CLAUDE_CODE_OAUTH_TOKEN=$')
if [ "$(printf '%s\n' "$antes" | grep -v '^VAULT_CLAUDE_CODE_OAUTH_TOKEN=$')" != "$depois" ]; then
  rm -f "$tmp"; echo "as outras chaves do .env mudariam; nada foi gravado"; exit 1
fi
mv "$tmp" "$ENV"
echo "token gravado (${#token} caracteres, termina em ...$(printf '%s' "$token" | tail -c 4))."
