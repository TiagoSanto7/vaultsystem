#!/bin/sh
# Instalador da VS CLI (Vault System) para Linux, macOS e WSL.
#
#   curl -fsSL {{HUB}}/v1/cli/install.sh | sh
#
# Baixa a CLI deste hub para ~/.local/share/vaultsystem e cria os comandos `vs` e
# `vaultsystem` em ~/.local/bin. Já deixa o endereço do hub configurado: depois é
# só `vs login` e colar o token de conexão.
#
# Variáveis opcionais: VS_HUB (outro hub), VS_INSTALL_DIR, VS_BIN_DIR.
set -eu
HUB=${VS_HUB:-{{HUB}}}
HUB=${HUB%/}
DIR=${VS_INSTALL_DIR:-$HOME/.local/share/vaultsystem}
BIN=${VS_BIN_DIR:-$HOME/.local/bin}

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    PY=$(command -v "$c"); break
  fi
done
[ -n "$PY" ] || { echo "A VS CLI precisa do Python 3.8 ou mais novo." >&2; exit 1; }

mkdir -p "$DIR" "$BIN"
echo "Baixando a VS CLI de $HUB ..."
curl -fsSL "$HUB/v1/cli/vs" -o "$DIR/vs.py.novo"
head -1 "$DIR/vs.py.novo" | grep -q '^#!.*python' || { rm -f "$DIR/vs.py.novo"; echo "O hub $HUB não devolveu a CLI." >&2; exit 1; }
mv "$DIR/vs.py.novo" "$DIR/vs.py"

cat > "$BIN/vs" <<EOF
#!/bin/sh
VS_CLI=1 exec "$PY" "$DIR/vs.py" "\$@"
EOF
cat > "$BIN/vaultsystem" <<EOF
#!/bin/sh
VS_CLI=1 exec "$PY" "$DIR/vs.py" welcome "\$@"
EOF
chmod +x "$BIN/vs" "$BIN/vaultsystem"

CFG_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/vaultsystem
mkdir -p "$CFG_DIR"
"$PY" - "$CFG_DIR/config.json" "$HUB" <<'EOF'
import json, os, sys
caminho, hub = sys.argv[1], sys.argv[2]
try:
    with open(caminho, encoding="utf-8") as f:
        c = json.load(f)
except (OSError, ValueError):
    c = {}
c.setdefault("url", hub)
fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(c, f, indent=2)
EOF

echo
echo "VS CLI instalada."
echo "  vs login          conecta ao hub $HUB (cole o token de conexão da aba Tokens)"
echo "  vs init vault=<name>, then vs sync"
echo "  vaultsystem       o painel de boas-vindas"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Coloque $BIN no PATH: echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.bashrc" ;;
esac
