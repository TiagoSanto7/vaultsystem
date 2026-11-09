# Vault System local

Hub (API + tela) e o processador de vaults rodando no Docker da máquina, sem
GitHub, sem AD e sem curador com IA. O vault de conteúdo é um repositório git
local em `local/dados/conteudo.git`.

## Subir

Na raiz do projeto, com o Docker Desktop ligado:

```sh
py -3 local/preparar.py --login <username>
docker compose --env-file local/.env -f docker-compose.yml -f local/docker-compose.local.yml up -d --build
```

O `preparar.py` roda uma vez e cria o `local/.env` (fora do git), com a senha da
primeira conta do hub em `VAULT_ADMIN_SENHA`. O hub abre em
http://127.0.0.1:8790.

## Fluxo principal

1. Entre no hub e crie um **token de conexão** na aba Tokens.
2. No terminal: `vs login url=http://127.0.0.1:8790` e cole o token.
3. Na pasta do projeto: `vs init vault=<nome>` (modo padrão: literal +
   documentado, `mode=documented`; `mode=literal` só copia os arquivos). Isso grava o `.vs`
   (vínculo com o hub e o dono do workspace) e o protocolo no `AGENTS.md`.
4. O agente escreve as notas seguindo o `AGENTS.md` (cabeçalho `vs:`).
5. `vs sync` envia. O primeiro envio cria o vault; as notas entram já curadas.
   `vs sync --dry-run` mostra o que iria e quais arquivos são notas.

Exemplo pronto: `exemplos/template-design` é o template `design:default` (o
design system do Vault System, com 9 notas). Nessa pasta, rode
`vs init template=design` e `vs sync`; depois, em outra pasta,
`vs add template design:default`.

## Curadoria interna (Vault-I)

A chave de API (Claude ou OpenAI) é configurada no painel, em Configurações. Sem
ela não há curadoria no hub, e isso não é erro: o vault fica com os arquivos e as
notas do agente. A curadoria nunca roda sozinha: só pelo botão "Curar com
Vault-I" de um vault. (O `vs sync --curate` é outra coisa: cura na sua máquina, com o seu agente.)

## Parar e limpar

```sh
docker compose --env-file local/.env -f docker-compose.yml -f local/docker-compose.local.yml stop
docker compose --env-file local/.env -f docker-compose.yml -f local/docker-compose.local.yml down -v
```

O `down -v` apaga o estado do hub (contas, tokens e vaults). O vault de conteúdo
continua em `local/dados`; apague a pasta para começar do zero.
