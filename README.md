<p align="center">
  <img src="assets/vault-system-banner.svg" alt="Vault System — Conhecimento distribuído" width="960">
</p>

<h1 align="center">Vault System</h1>
<p align="center"><strong>Conhecimento distribuído para pessoas, agentes e ferramentas.</strong></p>
<p align="center"><a href="#como-funciona">Como funciona</a> · <a href="#from-project-to-hub">From project to hub</a> · <a href="#commands">Commands</a> · <a href="#access">Access</a> · <a href="#estado-do-projeto">Estado do projeto</a></p>

Vault System reúne conhecimento que vive espalhado entre código, documentação e decisões de projeto. Ele relaciona essas informações com suas fontes e ajuda a levar o contexto certo para pessoas, agentes e ferramentas.

## Como funciona

| Etapa | O que acontece |
| --- | --- |
| **01 · Reunir** | Código, documentos e decisões entram na órbita do projeto. |
| **02 · Conectar** | As relações entre as fontes dão contexto a cada informação. |
| **03 · Distribuir** | Pessoas, agentes e ferramentas reaproveitam esse contexto onde trabalham. |

## From project to hub

The **hub** is your workspace server: it stores the vaults, shows the notes and issues access tokens. The **VS CLI** links each project folder to a vault on the hub. Git is optional: what gets uploaded is the folder itself.

```text
 Project (your machine)                        Hub (workspace)
 ──────────────────────                        ───────────────
 vs login   ── connection token ─────────────▶ checks the token and its owner
 vs init    ── writes .vs and AGENTS.md
 agent      ── writes the notes (vs: regra, elemento, …)
 vs sync    ── folder package ───────────────▶ creates or updates the vault
                                               files as they are + curated notes
                                               source and secret checks
                                                        │
                       ┌────────────────────────────────┼─────────────────────────────┐
                       ▼                                ▼                             ▼
                 Panel (people)                MCP and API (agents, apps)    vs add template (other projects)
```

1. **Install the CLI.** In the panel, VS CLI tab, one command installs `vs` and `vaultsystem` for your user, already pointing to the hub:
   - Windows: `irm <hub>/v1/cli/install.ps1 | iex`
   - Linux, macOS and WSL: `curl -fsSL <hub>/v1/cli/install.sh | sh`
2. **Connect.** In the Tokens tab, create a **connection token** and run `vs login`. The token is saved only for your user (`~/.config/vaultsystem/config.json`). `vs whoami` shows the hub and the workspace owner.
3. **Link the folder.** `vs init vault=my-project` writes the link in `.vs` and adds the documentation protocol to `AGENTS.md`. The default mode is **literal + documented** (`mode=documented`); `mode=literal` only stores the files. For templates, `vs init template=design` links the folder to the `template-design` vault: each subfolder is one template (`design:default`, `design:motion-vs`, …), and the default mode is `literal`.
4. **Document.** The project's agent (Claude Code, Codex or another) reads `AGENTS.md` and writes one note per subject, with its type and source files in the header.
5. **Send.** `vs sync` packages the folder, respecting `.gitignore` (`.env`, `node_modules` and the like never go), and sends it. The first sync creates the vault. Files are stored as they are, and the agent's notes arrive **already curated**, linked to their sources. A file that looks like a secret blocks the sync. `vs sync --dry-run` lists what would be sent.
6. **Distribute.** The vault's knowledge becomes available to:
   - **people**, in the panel;
   - **agents and applications**, through MCP and the API, with a read token;
   - **other projects**, as a template: `vs add template design:default` applies a folder from a `template-*` vault.

**Curation on the hub (optional).** Vault-I writes notes from the files using an API key (Claude or OpenAI), set in Settings. It never runs on its own: only from a vault's **Curar com Vault-I** button or with `vs sync --curate`. Without a key, nothing changes.

### Commands

| Command | What it does |
| --- | --- |
| `vs login [url=<address>]` | Connects to the hub with your connection token. |
| `vs logout` | Removes the saved token. |
| `vs whoami` | Shows the hub, the token and the workspace owner. |
| `vs init vault=<name> [mode=literal\|documented]` | Links this folder to a vault: writes `.vs`, `AGENTS.md` and `VS.lock`. |
| `vs init template=<type> [mode=literal\|documented]` | Links this folder to the `template-<type>` vault; each subfolder is a template. |
| `vs sync [--dry-run] [--curate]` | Packages this folder and sends it to the vault in `.vs`. |
| `vs init` | Prepares this folder (`AGENTS.md`, `.vs`) without linking it to any vault. |
| `vs sync vault=<name>` | Adds this folder to that vault; content sent by other folders stays. |
| `vs sync template=<type> [name=<template>]` | Adds this folder to `template-<type>` as one template (default name: the folder's name). |
| `vs sync <vault> <file.zip> [mode=literal\|documented]` | Sends a ready-made ZIP to a vault. |
| `vs templates [type]` | Lists the templates on the hub. |
| `vs add template <type:name> [dir=<folder>] [--dry-run] [--force]` | Applies a template to the current folder. |
| `vs repo connect <ssh-url>` | Initializes Git and adds the `vault` remote. |
| `vs version` / `vs update` | Shows the version / downloads the latest CLI from the hub. |
| `vs help` | Lists all commands. |
| `vaultsystem` | Opens the welcome panel. |

Every command accepts `--json` (output for scripts and agents).

## Access

| Who | How they sign in | What they can do |
| --- | --- | --- |
| **Person in the panel** | Username and password of a hub account. The first account is created at install time; others on the server. 12-hour session. | See vaults and notes, create and revoke tokens, configure Vault-I and request curation. |
| **Project terminal and agent** | **Connection token**, created in the panel and used by `vs login`. | Send to and read all vaults in the workspace, and create vaults on the first `vs sync`. |
| **Agents and applications** | **Read token**, created in the panel with the selected vaults. | Query only those vaults, through MCP (`search_knowledge`, `read_note`, …) or the API. |

Every token starts with `vs_`, is shown **only once** when created and is stored on the hub only as a hash. Revoking a token in the panel cuts access on the next call.

## Estado do projeto

Primeira versão executável: o hub (API e tela), a VS CLI e a curadoria opcional Vault-I.

| Parte | O que faz |
| --- | --- |
| **Hub** | Guarda os vaults, mostra as notas com origem e emite os tokens. |
| **VS CLI** | `vs login`, `vs init` e `vs sync` ligam uma pasta de projeto a um vault. No modo documentado, as notas que o agente do projeto escreveu entram já curadas. |
| **Vault-I** | Curadoria interna com chave de API (Claude ou OpenAI), só quando você pede. |

Para rodar na sua máquina, veja [local/README.md](local/README.md). Próximos passos: o comando `vs lock` e a CLI como binário sem Python.
