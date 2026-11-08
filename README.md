<p align="center">
  <img src="assets/vault-system-banner.svg" alt="Vault System — Conhecimento distribuído" width="960">
</p>

<h1 align="center">Vault System</h1>
<p align="center"><strong>Conhecimento distribuído para pessoas, agentes e ferramentas.</strong></p>
<p align="center"><a href="#como-funciona">Como funciona</a> · <a href="#do-projeto-ao-hub">Do projeto ao hub</a> · <a href="#acessos">Acessos</a> · <a href="#estado-do-projeto">Estado do projeto</a></p>

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
3. **Ligar a pasta.** `vs init vault=meu-projeto` grava o vínculo em `.vs` e acrescenta ao `AGENTS.md` o protocolo de documentação. O modo padrão é **literal + documentado**; `modo=literal` só guarda os arquivos.
4. **Documentar.** O agente do projeto (Claude Code, Codex ou outro) lê o `AGENTS.md` e escreve uma nota por assunto, com o tipo e os arquivos de origem no cabeçalho.
5. **Enviar.** `vs sync` empacota a pasta, respeitando o `.gitignore` (`.env`, `node_modules` e afins nunca vão), e envia. O primeiro envio cria o vault. Os arquivos entram como estão e as notas do agente entram **já curadas**, ligadas à origem. Arquivo com cara de segredo bloqueia o envio.
6. **Distribuir.** O conhecimento do vault fica disponível para:
   - **pessoas**, no painel;
   - **agentes e aplicações**, pelo MCP e pela API, com um token de leitura;
   - **outros projetos**, como template: `vs add template design:default` aplica uma pasta de um vault `template-*`.

**Curadoria no hub (opcional).** O Vault-I escreve notas a partir dos arquivos com uma chave de API (Claude ou OpenAI), configurada em Configurações. Ele nunca roda sozinho: só pelo botão **Curar com Vault-I** de um vault ou com `vs sync --curate`. Sem chave, nada muda.

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
