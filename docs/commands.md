# VS CLI command reference

This is the single source of truth for the `vs` command line. The README, the hub's
VS CLI tab, `vs help` and the `AGENTS.md` section written by `vs init` all follow it.
A change to a command starts here.

## Conventions

| Rule | Example |
| --- | --- |
| One pattern: `vs <verb> [object] [key=value ...] [--flag ...]` | `vs add template design:default dir=ui --dry-run` |
| Everything typed is English: verbs, objects, keys, values and flags | `mode=documented`, never `modo=documentado` |
| Verbs come first; the object, when there is one, is a single word | `vs list templates`, `vs connect repo` |
| Choices are `key=value`, never positional | `vs init vault=my-project`, not `vs init vault my-project` |
| Flags are on/off switches and never take a value | `--dry-run`, `--curate`, `--force`, `--json` |
| Names are lowercase letters, digits and hyphens | `my-project`, `design`, `motion-vs` |
| A template is addressed as `<type>:<name>` | `design:motion-vs` is the `motion-vs` folder of the `template-design` vault |
| Every command accepts `--json` for scripts and agents | `vs whoami --json` |
| `dir=<folder>` runs a command on another folder | `vs sync dir=../site` |

## Commands

### Connection

| Command | What it does |
| --- | --- |
| `vs login [url=<hub>]` | Connects to a hub with a **connection token** from the panel's Tokens tab. The token is asked without echo and saved for your user only (`~/.config/vaultsystem/config.json`). |
| `vs logout` | Removes the saved token. |
| `vs whoami` | Shows the hub, the token and the workspace owner. |

### Project folder

| Command | What it does |
| --- | --- |
| `vs init` | Prepares this folder: writes `AGENTS.md` (managed section), `.vs` and `VS.lock`. It does **not** link the folder to a vault. |
| `vs init vault=<name>` | Same, and links the folder to the vault `<name>`. Default `mode=documented`. |
| `vs init template=<type>` | Same, and links the folder to the vault `template-<type>`. Each subfolder is one template (`<type>:<folder>`). Default `mode=literal`. |
| `vs sync` | Sends this folder to the vault linked in `.vs`. The first sync creates the vault. |
| `vs sync vault=<name>` | Adds this folder to the vault `<name>`. |
| `vs sync template=<type>` | Adds this folder to `template-<type>` as one template, named after the folder (`name=<template>` sets another name). |

Parameters and flags of `init` and `sync`:

| Parameter or flag | Used with | Meaning |
| --- | --- | --- |
| `mode=literal` | `init`, `sync` | Store the files as they are. |
| `mode=documented` | `init`, `sync` | Store the files and import the agent's notes as curated. |
| `package=<name>` | `init` | Apply the init package `init:<name>` from the hub instead of the local one. |
| `name=<template>` | `sync template=` | The template's name inside the template vault. |
| `file=<zip>` | `sync vault=` / `sync template=` | Send a ready-made ZIP instead of this folder. |
| `--dry-run` | `init`, `sync`, `add template` | Only show what would happen. Notes are marked with `*`. |
| `--curate` | `sync` | Ask Vault-I to curate after the sync. Needs an API key or a `claude setup-token` token on the hub. |
| `--force` | `init`, `add template` | Overwrite files that already exist. |

How folders and vaults relate:

- Each folder that syncs is its own **origin** of the vault. A sync only replaces what that folder sent before; what other folders sent stays.
- A vault keeps the mode it was created with. A folder that adds to it follows that mode.
- `vs init` never runs twice on the same folder unless you want to change its link.

### Templates

| Command | What it does |
| --- | --- |
| `vs list templates [type=<type>]` | Lists the templates on the hub, of one type or all. |
| `vs add template <type:name>` | Applies a template to this folder (`dir=<folder>` for another one). Never overwrites without `--force`. Records the revision in `.vaultsystem/templates.json`. |

### Git (optional)

| Command | What it does |
| --- | --- |
| `vs connect repo <ssh-url>` | Initializes Git in this folder and adds the `vault` remote. |

### CLI

| Command | What it does |
| --- | --- |
| `vs version` | Shows this version and the hub's. |
| `vs update` | Downloads the latest CLI from the hub. |
| `vs help` | Lists every command. |
| `vaultsystem` | Opens the welcome panel. |

## Notes written by the agent

`vs init` writes a managed section in `AGENTS.md` (between `<!-- vs:inicio -->` and
`<!-- vs:fim -->`) that tells the project's agent how to write notes and which
commands it may run. Note types, set in the `vs:` header field: `elemento`,
`regra`, `orientacao`, `decisao`, `modulo`, `integracao`, `api`, `dado` and `nota`.

## Renamed commands

The old forms stop with a message that names the new one.

| Old | New |
| --- | --- |
| `vs templates [type]` | `vs list templates [type=<type>]` |
| `vs repo connect <url>` | `vs connect repo <url>` |
| `vs init <package>` | `vs init package=<package>` |
| `vs init vault <name>` | `vs init vault=<name>` |
| `vs sync <vault> <file.zip>` | `vs sync vault=<vault> file=<file.zip>` |
| `modo=literal\|documentado` | `mode=literal\|documented` |
| `vs versao`, `vs ajuda` | `vs version`, `vs help` |
