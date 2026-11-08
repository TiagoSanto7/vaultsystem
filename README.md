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

Every command follows one pattern: `vs <verb> [object] [key=value ...] [--flag ...]`, all in English. The full reference, with every parameter and the renamed commands, is in [docs/commands.md](docs/commands.md).

| Command | What it does |
| --- | --- |
| `vs login [url=<hub>]` | Connects to a hub with a connection token. |
| `vs logout` / `vs whoami` | Removes the saved token / shows the hub, the token and the owner. |
| `vs init` | Prepares this folder (`AGENTS.md`, `.vs`, `VS.lock`) without linking it to a vault. |
| `vs init vault=<name>` | Same, and links the folder to a vault (default `mode=documented`). |
| `vs init template=<type>` | Same, and links it to `template-<type>`; each subfolder is a template (default `mode=literal`). |
| `vs sync` | Sends this folder to the vault linked in `.vs`. |
| `vs sync vault=<name>` | Adds this folder to a vault; what other folders sent stays. |
| `vs sync template=<type> [name=<template>]` | Adds this folder to `template-<type>` as one template. |
| `vs list templates [type=<type>]` | Lists the templates on the hub. |
| `vs add template <type:name>` | Applies a template to this folder. |
| `vs connect repo <ssh-url>` | Initializes Git and adds the `vault` remote (optional). |
| `vs version` / `vs update` / `vs help` | Version / latest CLI from the hub / all commands. |
| `vaultsystem` | Opens the welcome panel. |

Flags: `--dry-run` (only show), `--curate` (ask Vault-I, on `sync`), `--force` (overwrite, on `init` and `add template`), `--json` (on every command).

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
