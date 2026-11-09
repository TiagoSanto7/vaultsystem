<p align="center">
  <img src="assets/vault-system-banner.svg" alt="Vault System — Conhecimento distribuído" width="960">
</p>

<h1 align="center">Vault System</h1>
<p align="center"><strong>Conhecimento distribuído para pessoas, agentes e ferramentas.</strong></p>
<p align="center"><a href="#como-funciona">Como funciona</a> · <a href="#do-projeto-ao-hub">Do projeto ao hub</a> · <a href="#comandos">Comandos</a> · <a href="#acessos">Acessos</a> · <a href="#estado-do-projeto">Estado do projeto</a></p>

Vault System reúne conhecimento que vive espalhado entre código, documentação e decisões de projeto. Ele relaciona essas informações com suas fontes e ajuda a levar o contexto certo para pessoas, agentes e ferramentas.

## Como funciona

| Etapa | O que acontece |
| --- | --- |
| **01 · Reunir** | Código, documentos e decisões entram na órbita do projeto. |
| **02 · Conectar** | As relações entre as fontes dão contexto a cada informação. |
| **03 · Distribuir** | Pessoas, agentes e ferramentas reaproveitam esse contexto onde trabalham. |

## Do projeto ao hub

O **hub** é o servidor do seu workspace: guarda os vaults, mostra as notas e emite os acessos. A **VS CLI** liga cada pasta de projeto a um vault no hub. Git é opcional: o que sobe é a própria pasta.

```text
 Projeto (sua máquina)                         Hub (workspace)
 ─────────────────────                         ───────────────
 vs login   ── token de conexão ─────────────▶ confere o token e o dono
 vs init    ── grava .vs e AGENTS.md
 agente     ── escreve as notas (vs: regra, elemento, …)
 vs sync    ── pacote da pasta ──────────────▶ cria ou atualiza o vault
                                               arquivos como estão + notas curadas
                                               verificação de origem e de segredo
                                                        │
                       ┌────────────────────────────────┼─────────────────────────────┐
                       ▼                                ▼                             ▼
                 Painel (pessoas)              MCP e API (agentes, apps)     vs add template (outros projetos)
```

1. **Instalar a CLI.** No painel, aba VS CLI, um comando instala `vs` e `vaultsystem` no seu usuário, já apontando para o hub:
   - Windows: `irm <hub>/v1/cli/install.ps1 | iex`
   - Linux, macOS e WSL: `curl -fsSL <hub>/v1/cli/install.sh | sh`
2. **Conectar.** Na aba Tokens, crie um **token de conexão** e rode `vs login`. O token fica guardado só no seu usuário (`~/.config/vaultsystem/config.json`). `vs whoami` mostra o hub e o dono do workspace.
3. **Ligar a pasta.** `vs init vault=meu-projeto` grava o vínculo em `.vs` e acrescenta ao `AGENTS.md` o protocolo de documentação. O modo padrão é **literal + documentado** (`mode=documented`); `mode=literal` só guarda os arquivos. Para templates, `vs init template=design` liga a pasta ao vault `template-design`: cada subpasta é um template (`design:default`, `design:motion-vs`…), e o modo padrão é `literal`. Sem `vault=` nem `template=`, o `vs init` só prepara a pasta.
4. **Documentar.** O agente do projeto (Claude Code, Codex ou outro) lê o `AGENTS.md` e escreve uma nota por assunto, com o tipo e os arquivos de origem no cabeçalho.
5. **Enviar.** `vs sync` empacota a pasta, respeitando o `.gitignore` (`.env`, `node_modules` e afins nunca vão), e envia. O primeiro envio cria o vault. Os arquivos entram como estão e as notas do agente entram **já curadas**, ligadas à origem. Arquivo com cara de segredo bloqueia o envio. `vs sync --dry-run` lista o que iria.
6. **Distribuir.** O conhecimento do vault fica disponível para:
   - **pessoas**, no painel;
   - **agentes e aplicações**, pelo MCP e pela API, com um token de leitura;
   - **outros projetos**, como template: `vs add template design:default` aplica uma pasta de um vault `template-*`.

**Várias pastas, um vault.** Cada pasta que envia é uma origem do vault e só troca o que é dela. `vs sync vault=<nome>` soma a pasta atual a um vault (e cria o vault se ele não existir). `vs sync template=design name=instagram` soma a pasta ao `template-design` como o template `design:instagram`; sem `name=`, vale o nome da pasta. `file=<zip>` manda um ZIP pronto no lugar da pasta.

**Curadoria (opcional).** Sem agente na sessão, `vs sync --curate` abre o agente da sua máquina (hoje, o Claude Code; configure com `vs login agent=claude`), que escreve as notas seguindo o `AGENTS.md` antes do envio. No hub, o Vault-I faz o mesmo com uma chave de API ou o token do `claude setup-token`, configurados em Configurações, e só roda pelo botão **Curar com Vault-I** do vault. Nenhuma curadoria roda sozinha.

### Comandos

Os comandos são sempre em inglês e seguem um padrão só: `vs <verbo> [objeto] [chave=valor ...] [--flag ...]`. A referência completa, com cada parâmetro e os comandos renomeados, está em [docs/commands.md](docs/commands.md).

| Comando | O que faz |
| --- | --- |
| `vs login [url=<hub>]` | Conecta a um hub com o token de conexão. |
| `vs logout` / `vs whoami` | Apaga o token guardado / mostra o hub, o token e o dono. |
| `vs login agent=claude` | Configura o agente do `vs sync --curate`. |
| `vs init` | Prepara a pasta (`AGENTS.md`, `.vs`, `VS.lock`) sem ligar a um vault. |
| `vs init vault=<nome>` | Prepara e liga a pasta a um vault (padrão `mode=documented`). |
| `vs init template=<tipo>` | Prepara e liga a `template-<tipo>`; cada subpasta é um template (padrão `mode=literal`). |
| `vs sync` | Envia a pasta para o vault ligado no `.vs`. |
| `vs sync vault=<nome>` | Soma a pasta a um vault; o que outras pastas mandaram fica. |
| `vs sync template=<tipo> [name=<template>]` | Soma a pasta a `template-<tipo>` como um template. |
| `vs list templates [type=<tipo>]` | Lista os templates do hub. |
| `vs add template <tipo:nome>` | Aplica um template na pasta. |
| `vs connect repo <url-ssh>` | Inicia o Git e adiciona o remoto `vault` (opcional). |
| `vs version` / `vs update` / `vs help` | Versão / CLI mais nova do hub / todos os comandos. |
| `vaultsystem` | Abre o painel de boas-vindas. |

Flags: `--dry-run` (só mostra), `--curate` (o agente da máquina cura a pasta antes do `sync`), `--force` (sobrescreve, no `init` e no `add template`), `--json` (em todos).

## Acessos

| Quem | Como entra | O que pode |
| --- | --- | --- |
| **Pessoa no painel** | Usuário e senha de uma conta do hub. A primeira conta nasce na instalação; as outras, no servidor. Sessão de 12 horas. | Ver os vaults e as notas, criar e revogar tokens, configurar o Vault-I e pedir curadoria. |
| **Terminal e agente do projeto** | **Token de conexão**, criado no painel e usado no `vs login`. | Enviar e ler todos os vaults do workspace e criar vaults no primeiro `vs sync`. |
| **Agentes e aplicações** | **Token de leitura**, criado no painel com os vaults marcados. | Consultar só aqueles vaults, pelo MCP (`search_knowledge`, `read_note`, …) ou pela API. |

Todo token começa com `vs_`, aparece **uma vez só** na criação e fica guardado no hub apenas como hash. Revogar um token no painel corta o acesso na chamada seguinte.

## Estado do projeto

Primeira versão executável: o hub (API e tela), a VS CLI e a curadoria opcional Vault-I.

| Parte | O que faz |
| --- | --- |
| **Hub** | Guarda os vaults, mostra as notas com origem e emite os tokens. |
| **VS CLI** | `vs login`, `vs init` e `vs sync` ligam uma pasta de projeto a um vault. No modo documentado, as notas que o agente do projeto escreveu entram já curadas. |
| **Vault-I** | Curadoria interna com chave de API (Claude ou OpenAI), só quando você pede. |

Para rodar na sua máquina, veja [local/README.md](local/README.md). Próximos passos: o comando `vs lock` e a CLI como binário sem Python.
