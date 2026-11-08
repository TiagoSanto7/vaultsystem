# VS CLI

A `vs` leva o Vault System para o terminal. Com ela, uma pasta de projeto vira
um vault no hub: os arquivos entram como estão e as notas que o agente do
projeto escreveu entram já curadas, cada uma ligada aos arquivos de onde veio.
Git é opcional.

## Instalar

Um comando instala a `vs` e o `vaultsystem` no seu usuário, sem administrador,
já apontando para este hub. Precisa do Python 3.8 ou mais novo.

**Windows (PowerShell):**

```
irm {{URL}}/v1/cli/install.ps1 | iex
```

Instala em `%LOCALAPPDATA%\VaultSystem` e põe `%LOCALAPPDATA%\VaultSystem\bin`
no PATH do seu usuário. Abra um terminal novo depois.

**Linux, macOS e WSL:**

```
curl -fsSL {{URL}}/v1/cli/install.sh | sh
```

Instala em `~/.local/share/vaultsystem` e cria `vs` e `vaultsystem` em
`~/.local/bin` (se ela não estiver no PATH, o instalador mostra a linha para o
`~/.bashrc`).

Para atualizar depois: `vs update`. `vs version` compara com a versão do hub.

## Conectar ao hub

Crie um **token de conexão** na aba Tokens e rode:

```
vs login url={{URL}}
```

A `vs` pede o token sem mostrar na tela e o guarda em
`~/.config/vaultsystem/config.json`, que só você lê. O token de conexão é do
seu workspace: lê e envia a todos os vaults e cria um vault no primeiro
envio. `vs whoami` mostra o hub, o token e o dono do workspace.

Em CI ou num agente, use as variáveis `VS_URL` e `VS_TOKEN` no lugar do login.

## Ligar a pasta a um vault

Na raiz do projeto:

```
vs init vault=meu-projeto
```

O `vs init` grava três coisas:

- `.vs`: o vínculo com o hub (endereço, vault, modo e dono do workspace).
- `AGENTS.md`: a seção gerenciada com o protocolo de documentação para o
  agente. Se o arquivo já existe, só essa seção muda.
- `VS.lock` (prévia) e a linha dele no `.gitignore`.

Modos: **literal + documentado** (padrão) guarda os arquivos e importa as
notas do agente (`mode=documented`). **Literal** (`mode=literal`) só guarda os arquivos; é o padrão
de um vault de template (`vault=template-<tipo>`).

## Documentar com o agente

O agente do projeto (Claude Code, Codex ou outro) lê o `AGENTS.md` e escreve
uma nota por assunto, em Markdown, com este cabeçalho:

```
---
vs: regra
titulo: Desconto máximo do catálogo
origens:
  - app/precos.py
---
# Desconto máximo do catálogo

O desconto nunca passa de 15%: preco_final limita o valor recebido.
```

Tipos (`vs:`): `elemento`, `regra`, `orientacao`, `decisao`, `modulo`,
`integracao`, `api`, `dado` e `nota`. `origens` são os arquivos que a nota
explica, a partir da raiz do projeto.

## Enviar

```
vs sync
```

Empacota a pasta (respeitando o `.gitignore`; `.env`, `node_modules` e
afins nunca vão) e envia ao vault do `.vs`. O primeiro envio cria o vault. O
hub processa em instantes: as notas do agente aparecem na aba Conhecimento,
com a verificação feita pelo código.

`vs sync --dry-run` lista o que iria e marca com `*` as notas do agente.

Um ZIP pronto também pode ir direto: `vs sync <vault> <arquivo.zip>
mode=documented`.

## Templates

Um template é uma pasta de um vault `template-<tipo>`. `design:default` é a
pasta `default/` do vault `template-design`.

```
vs templates
vs add template design:default
vs add template design:default dir=interface --dry-run
```

`add template` nunca sobrescreve sem `--force` e registra a revisão aplicada em
`.vaultsystem/templates.json`.

## Curadoria no hub (Vault-I)

O Vault-I é a curadoria interna do hub, com a chave de API do Claude ou da
OpenAI configurada em **Configurações** (menu do avatar). Ela **nunca roda
sozinha**: só quando você pede, pelo botão **Curar com Vault-I** de um vault ou
no envio:

```
vs sync --curate
```

Sem chave, isso não é erro: o envio passa normalmente e o vault fica com os
arquivos e as notas do agente. As notas do Vault-I levam `curada_por: vault-i` e
são refeitas a cada pedido; as notas do agente do projeto têm prioridade.

## Todos os comandos

```
vs login [url=<hub>]               conecta ao hub com o token de conexão
vs logout                          apaga o token guardado
vs whoami                          hub, token e dono do workspace
vs init [nome] vault=<v> mode=<m>  liga a pasta a um vault
vs sync [--dry-run]                envia a pasta ao vault do .vs
vs sync <vault> <zip> [mode=…]     envia um ZIP pronto
vs templates [tipo]                lista os templates
vs add template <tipo:nome>        aplica um template na pasta
vs version                         esta versão e a do hub
vs help                            ajuda
```

Todo comando aceita `--json`, para script e agente.
