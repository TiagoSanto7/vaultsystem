# Curador: a imagem do Hermes (fixada no .env) mais a CLI oficial do Claude Code, que o
# Vault-I usa quando a curadoria é feita com o token do `claude setup-token`.
ARG HERMES_IMAGE=nousresearch/hermes-agent:v2026.9.11
FROM ${HERMES_IMAGE}
USER 0:0
RUN npm install -g --no-audit --no-fund @anthropic-ai/claude-code@2.1.310 && claude --version
