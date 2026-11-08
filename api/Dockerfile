# API do vault-system. Usuário 10000, o mesmo do curador, para os dois
# lerem o volume de estado. Contexto do build: a raiz do repositório (para o
# pacote vault_system/, compartilhado com o curador); ver .dockerignore.

# Tela: React compilado aqui e copiado para a imagem final; a API
# serve os arquivos na mesma origem (api/app/main.py).
FROM node:22.11.0-slim AS tela
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /opt/api
# git: a aba Renderização lê imagens e fontes do clone bare das origens.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY vault_system ./vault_system
COPY api/app ./app
# CLI: a API serve a CLI em /v1/cli/vs e os instaladores em /v1/cli/install.ps1 e install.sh.
COPY cli ./cli
COPY --from=tela /web/dist ./web
USER 10000:10000
ENV ESTADO_DIR=/opt/estado
ENV VAULT_WEB_DIR=/opt/api/web
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
