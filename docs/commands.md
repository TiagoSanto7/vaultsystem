# Referência de comandos da VS CLI

Esta é a fonte única da linha de comando `vs`. O README, a aba VS CLI do hub, o
`vs help` e a seção do `AGENTS.md` escrita pelo `vs init` seguem este documento.
Qualquer mudança em um comando começa aqui.

## Convenções

| Regra | Exemplo |
| --- | --- |
| Um padrão só: `vs <verbo> [objeto] [chave=valor ...] [--flag ...]` | `vs add template design:default dir=ui --dry-run` |
| Tudo o que se digita é em inglês: verbos, objetos, chaves, valores e flags. As explicações são em português. | `mode=documented`, nunca `modo=documentado` |
| O verbo vem primeiro; o objeto, quando existe, é uma palavra só | `vs list templates`, `vs connect repo` |
| Escolhas são sempre `chave=valor`, nunca posicionais | `vs init vault=meu-projeto`, não `vs init vault meu-projeto` |
| Flags ligam ou desligam algo e nunca recebem valor | `--dry-run`, `--curate`, `--force`, `--json` |
| Nomes usam letras minúsculas, números e hífen | `meu-projeto`, `design`, `motion-vs` |
| Um template é chamado de `<tipo>:<nome>` | `design:motion-vs` é a pasta `motion-vs` do vault `template-design` |
| Todo comando aceita `--json`, para scripts e agentes | `vs whoami --json` |
| `dir=<pasta>` roda o comando em outra pasta | `vs sync dir=../site` |

## Comandos

### Conexão

| Comando | O que faz |
| --- | --- |
| `vs login [url=<hub>]` | Conecta a um hub com o **token de conexão** da aba Tokens do painel. O token é pedido sem aparecer na tela e fica guardado só para o seu usuário (`~/.config/vaultsystem/config.json`). |
| `vs logout [agent=<agente>]` | Apaga o token do hub (ou, com `agent=`, a credencial do agente). |
| `vs login agent=claude` | Configura o agente do `vs sync --curate`: pede o token do `claude setup-token` (Enter vazio usa o login que o Claude Code já tem na máquina). |
| `vs whoami` | Mostra o hub, o token e o dono do workspace. |

### Pasta do projeto

| Comando | O que faz |
| --- | --- |
| `vs init` | Prepara a pasta: grava o `AGENTS.md` (seção gerenciada), o `.vs` e o `VS.lock`. **Não** liga a pasta a um vault. |
| `vs init vault=<nome>` | Faz o mesmo e liga a pasta ao vault `<nome>`. Padrão `mode=documented`. |
| `vs init template=<tipo>` | Faz o mesmo e liga a pasta ao vault `template-<tipo>`. Cada subpasta é um template (`<tipo>:<pasta>`). Padrão `mode=literal`. |
| `vs sync` | Envia a pasta para o vault ligado no `.vs`. O primeiro envio cria o vault. |
| `vs sync vault=<nome>` | Soma a pasta atual ao vault `<nome>`. Se o vault não existe, ele é criado. Não precisa de `vs init`. |
| `vs sync template=<tipo>` | Soma a pasta atual a `template-<tipo>` como um template, com o nome da pasta (`name=<template>` dá outro nome). |

Parâmetros e flags do `init` e do `sync`:

| Parâmetro ou flag | Vale para | O que faz |
| --- | --- | --- |
| `mode=literal` | `init`, `sync` | Guarda os arquivos como estão. |
| `mode=documented` | `init`, `sync` | Guarda os arquivos e importa as notas do agente como curadas. |
| `package=<nome>` | `init` | Aplica o pacote de inicialização `init:<nome>` do hub no lugar do local. |
| `name=<template>` | `sync template=` | O nome do template dentro do vault de template: a parte depois dos dois-pontos em `vs add template <tipo>:<nome>`. |
| `file=<zip>` | `sync vault=` / `sync template=` | Envia um ZIP pronto no lugar da pasta. Substitui o envio principal do vault; num `template=`, o ZIP já vem com uma pasta por template. |
| `--dry-run` | `init`, `sync`, `add template` | Só mostra o que aconteceria. As notas aparecem marcadas com `*`. |
| `--curate` | `sync` | Antes de enviar, abre o agente da máquina, que cura a pasta seguindo o `AGENTS.md` (escreve e atualiza as notas em `docs/vs/`). Depois o `vs` confere as notas e envia. Com `--dry-run`, só avisa. |
| `agent=<agente>` | `sync --curate` | Qual agente usar. Padrão: o do `vs login agent=`. Hoje: `claude`. Em seguida: `codex`, `gemini`, `cursor` e `opencode`. |
| `--force` | `init`, `add template` | Sobrescreve arquivos que já existem. |

Como pastas e vaults se relacionam:

- Cada pasta que envia é uma **origem** do vault. Um envio só troca o que aquela pasta mandou antes; o que outras pastas mandaram continua.
- Um vault mantém o modo com que foi criado. Uma pasta que soma conteúdo a ele segue esse modo.
- Só rode `vs init` de novo numa pasta se quiser mudar o vínculo dela.

### Templates

| Comando | O que faz |
| --- | --- |
| `vs list templates [type=<tipo>]` | Lista os templates do hub, de um tipo ou todos. |
| `vs add template <tipo:nome>` | Aplica um template na pasta (`dir=<pasta>` para outra). Nunca sobrescreve sem `--force`. Registra a revisão em `.vaultsystem/templates.json`. |

### Git (opcional)

| Comando | O que faz |
| --- | --- |
| `vs connect repo <url-ssh>` | Inicia o Git na pasta e adiciona o remoto `vault`. |

### CLI

| Comando | O que faz |
| --- | --- |
| `vs version` | Mostra esta versão e a do hub. |
| `vs update` | Baixa a CLI mais nova do hub. |
| `vs help` | Lista todos os comandos. |
| `vaultsystem` | Abre o painel de boas-vindas. |

## Curadoria

| Onde | Como | Quem escreve as notas |
| --- | --- | --- |
| Na sua máquina | `vs sync --curate` | O agente local (hoje, o Claude Code), com a sua conta, seguindo o `AGENTS.md`. Só lê e edita arquivos da pasta; não roda comandos. |
| No hub | Botão **Curar com Vault-I** no vault | O Vault-I, com a chave de API ou o token configurado em Configurações. |
| À mão ou pelo seu agente | Escrevendo em `docs/vs/` | Você ou o agente da sua sessão, seguindo o `AGENTS.md`. |

## Notas escritas pelo agente

O `vs init` grava no `AGENTS.md` uma seção gerenciada (entre `<!-- vs:inicio -->` e
`<!-- vs:fim -->`) que diz ao agente do projeto como escrever as notas e quais
comandos ele pode rodar. Tipos de nota, no campo `vs:` do cabeçalho, para qualquer assunto:
`conceito`, `regra`, `orientacao`, `elemento`, `decisao` e `nota`; só para código: `modulo`,
`integracao`, `api` e `dado`. Para ligar notas, `[[nome-do-arquivo]]` (sem `.md`); o hub troca pelo
endereço da nota no vault.

## Comandos renomeados

As formas antigas param com uma mensagem que mostra a nova.

| Antes | Agora |
| --- | --- |
| `vs templates [tipo]` | `vs list templates [type=<tipo>]` |
| `vs repo connect <url>` | `vs connect repo <url>` |
| `vs init <pacote>` | `vs init package=<pacote>` |
| `vs init vault <nome>` | `vs init vault=<nome>` |
| `vs sync <vault> <arquivo.zip>` | `vs sync vault=<vault> file=<arquivo.zip>` |
| `modo=literal\|documentado` | `mode=literal\|documented` |
| `vs versao`, `vs ajuda` | `vs version`, `vs help` |
