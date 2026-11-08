# CLI do PetroVault (`pv`): plano (DV-607)

Status: **aprovado** (05/11/2026), em implementação no ramo `DV-607-cli`.

## 1. O que a primeira versão resolve

Montar um projeto novo no padrão da empresa sem copiar arquivos à mão:

```
pv add template docker:python
```

Esse comando baixa para a pasta atual o pacote padrão de montagem da stack
Python (`Dockerfile`, `docker-compose.yml`, `.dockerignore` e um `LEIA-ME.md`).
A infra mantém os pacotes num repositório, e o PetroVault serve sempre a versão
publicada. Quem roda o comando recebe o padrão do dia, não uma cópia velha de
outro projeto.

O resto da CLI (busca, leitura, `note:add`, achados) segue o que está no
DV-607. Fica para depois deste primeiro comando, mas sobre a mesma base:
login, configuração e formato dos comandos.

## 2. Template é um vault

Para não inventar outra estrutura, o template é um **vault do PetroVault**,
com a mesma ingestão, o mesmo histórico, a mesma tela e as mesmas credenciais.

| | Vault de sistema | Vault de referência | **Vault de template** (novo) |
| --- | --- | --- | --- |
| Para quê | conhecer um sistema | consultar um padrão (design system) | **baixar** um pacote pronto |
| Origem | repositório do sistema | repositório do padrão | repositório de templates da infra |
| Curador (LLM) | sim | guias (opcional) | **não**: cópia literal, custo zero |
| Consumo | MCP, API, tela | MCP, API, tela, arquivos | **`pv add template`**, API, tela |

### 2.1 Repositório e nomes

Um repositório por **tipo** de template, mantido pela infra:

```
petro-templates-docker/          → vault  template-docker
  python/
    Dockerfile
    docker-compose.yml
    .dockerignore
    LEIA-ME.md
    template.json                ← opcional: descrição (e, depois, variáveis)
  laravel/
    ...
  php/
    ...
```

`docker:python` é lido como **tipo** `docker` e **nome** `python`. O tipo aponta
para o vault `template-docker` e o nome aponta para a pasta `python/` dele.
Amanhã, `k8s:python` ou `ci:github-actions` são outros vaults, de outros donos,
sem mexer na CLI. Com isso, cada tipo tem o próprio dono, permissão e histórico.

Nome com versão fica para depois (`docker:python@3.12`, com a pasta
`python@3.12/`). A primeira versão não precisa disso.

### 2.2 Como o PetroVault guarda

- Na tela "Novo vault", o tipo **Template** entra ao lado de Sistema e
  Referência. Com o tipo Template, o campo de nome **trava o prefixo
  `template-`**: a pessoa digita só o tipo (`docker`), e o vault fica
  `template-docker`. Assim todo vault de template segue o padrão, e o
  `docker:` da CLI acha o vault sem tabela de apelidos (decidido pelo Tiago
  em 04/11). A árvore sugere tudo como **referência (só literal)**: cópia
  pelo código, sem LLM. O Dockerfile e o compose também aparecem no mapa de
  infra (DV-603), porque o leitor de infra é determinístico.
- O que sai no download vem do **clone no commit processado**, como os binários
  do DV-601, com os mesmos filtros de caminho. `.env` nunca sai.
  `.env.example` sai.
- Arquivo que o filtro de segredo acusar **bloqueia o template inteiro**, com
  erro claro. Template não pode carregar segredo.

### 2.3 API

| Rota | O que devolve |
| --- | --- |
| `GET /v1/templates` | os templates que a credencial lê: `[{id: "docker:python", descricao, arquivos, commit}]` |
| `GET /v1/templates/docker/python` | os detalhes: arquivos, tamanhos, commit e `template.json` |
| `GET /v1/templates/docker/python.zip` | o pacote para baixar |

Qualquer credencial `pv_` válida lê qualquer template (decisão 3 na seção 5):
template é para todos e não carrega segredo.

## 3. A CLI

### 3.1 Instalar

Um arquivo Python só com biblioteca padrão (`cli/pv.py`), servido pela própria API:

```
curl -fsSL http://10.2.2.31:8670/v1/cli/pv \
  -o ~/.local/bin/pv
chmod +x ~/.local/bin/pv
```

Não precisa de pip, pipx nem venv: funciona em qualquer máquina com Python 3.8
ou mais novo. `pv versao` compara com a versão servida e avisa quando há uma
mais nova.

### 3.2 Login e configuração

```
pv login            # pede o token pv_ (sem eco) e testa
```

O token fica em `~/.config/petrovault/config.json`, com permissão 0600.
`PV_TOKEN` e `PV_URL` no ambiente têm prioridade sobre o arquivo, para CI e
agente. O endereço padrão é `http://10.2.2.31:8670`.

### 3.3 Comandos da primeira versão

```
pv templates [docker]                     # lista o que há (de um tipo ou de todos)
pv add template docker:python             # baixa na pasta atual
pv add template docker:python dir=infra   # baixa noutra pasta
pv add template docker:python --dry-run   # só mostra o que faria
pv add template docker:python --force     # sobrescreve o que já existe
```

**Comportamento de `add template`:**
- **Nunca sobrescreve sem `--force`.** Se algum arquivo já existe, para antes
  de escrever qualquer coisa e lista os conflitos.
- **Mostra o que escreveu**, com o commit do template (`docker:python @ a1b2c3d`).
- **Grava `.petrovault/templates.json`** na pasta, com tipo, nome, commit e data.
  Um `pv update template` futuro usa isso para saber de qual versão o projeto
  partiu.

### 3.4 Formato dos comandos daqui para frente

- **Verbo e objeto**, como no seu exemplo: `pv add template`, `pv add note`
  (achado, DV-598), `pv search`, `pv read`.
- **Parâmetros:** `nome=valor`. **Flags:** `--force` e `--dry-run`.
- **Saída:** texto para pessoa por padrão; `--json` para script e agente.

## 4. Teste antes de você rodar

1. **Eu crio um repositório de teste**, `PetrovinaS/petro-templates-docker-teste`,
   com `python/` e um pacote de exemplo. **Não é o padrão oficial**: este a
   infra sobe depois.
2. **Você inclui o repositório no acesso do GitHub App.** Eu não tenho
   permissão para isso.
3. **Você cadastra o vault** `template-docker` pela tela, com o tipo Template.
4. **Eu testo do servidor:** a API, o zip e o `pv add template docker:python`
   numa pasta vazia, além do conflito sem `--force`.
5. **Você roda o comando** e confere os arquivos.

Testes automatizados cobrem a API (a credencial, o zip, o bloqueio por
segredo, o `.env` fora) e a CLI (o conflito, o `--force`, o `--dry-run` e o
`.petrovault/templates.json`).

## 5. Decisões (Tiago, 04 e 05/11)

1. **Um repositório por tipo**: `petro-templates-docker` → vault
   `template-docker`; outro tipo, outro repositório e outro vault.
2. **Placeholders depois**: a primeira versão só copia os arquivos. O
   preenchimento (`{{nome}}`, `{{porta}}`, com as variáveis no
   `template.json`) fica para a próxima, e é desejado.
3. **Qualquer credencial `pv_` válida** lista e baixa qualquer template. Não
   precisa ter a tag `template-*` na leitura.
4. **Nome do vault**: o prefixo `template-` fica travado no cadastro, e o vault
   do tipo `docker` é `template-docker` (seção 2.2).
5. **Página Docs na tela**: um item **Docs** no menu lateral, logo acima de
   "Recolher menu", abre a documentação. A v1 traz a documentação da CLI;
   depois entram Sobre, Quickstart, Tutorial e o resto do PetroVault.

## 6. Fora desta primeira entrega

- `pv update template`: mostra a diferença entre o template de hoje e o do
  projeto e aplica.
- Ferramenta do MCP (`get_template`) para o agente montar o projeto sozinho.
- Os comandos de leitura (`search`, `read`, `files`, `infra`), de operação
  (`pull`, `status`, `verify`) e de conhecimento oculto (`add note`, DV-598),
  como estão no DV-607.
- Login com a Microsoft (DV-574) no lugar do token.
