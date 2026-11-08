# CLI do PetroVault (`pv`)

Versão 1. A `pv` leva o PetroVault para o terminal. O primeiro comando monta um
projeto novo no padrão da empresa sem copiar arquivo à mão:

```
pv add template docker:python
```

Esse comando baixa para a pasta atual o pacote padrão da stack Python
(`Dockerfile`, `docker-compose.yml`, `.dockerignore` e o que mais a infra
publicou), sempre na versão em vigor.

## Instalar

A `pv` é um arquivo Python único, sem dependências. Precisa de Python 3.8 ou
mais novo.

**Linux, macOS e WSL:**

```
mkdir -p ~/.local/bin
curl -fsSL {{URL}}/v1/cli/pv \
  -o ~/.local/bin/pv
chmod +x ~/.local/bin/pv
pv versao
```

Se aparecer `pv: command not found`, coloque `~/.local/bin` no `PATH`
(`export PATH="$HOME/.local/bin:$PATH"` no `~/.bashrc`).

**Windows (PowerShell):**

```
curl.exe -fsSL {{URL}}/v1/cli/pv -o pv.py
python pv.py versao
```

No Windows, troque `pv` por `python pv.py` nos exemplos abaixo.

## Entrar

```
pv login
```

O comando pede um token `pv_`, sem mostrar o que você digita, e testa o token
no servidor. Para criar um token, abra **Tokens** no menu desta tela.
Qualquer token válido baixa templates.

O token fica em `~/.config/petrovault/config.json`, que só o seu usuário lê.
`pv logout` apaga o token.

Para outro servidor, use `pv login url=http://outro:8670`.

## Templates

### Ver o que existe

```
pv templates          # todos
pv templates docker   # só os de Docker
```

Cada linha mostra o nome do template (`docker:python`), quantos arquivos ele
tem, o commit publicado e a descrição.

### Baixar

```
pv add template docker:python             # na pasta atual
pv add template docker:python dir=infra   # noutra pasta (é criada)
pv add template docker:python --dry-run   # só mostra o que faria
pv add template docker:python --force     # sobrescreve o que já existe
```

- **Nada é sobrescrito sem `--force`.** Se algum arquivo já existe com outro conteúdo, o comando
  para antes de escrever qualquer coisa e lista os conflitos.
- A saída mostra cada arquivo (`+` novo, `~` sobrescrito, `=` já estava igual) e o commit do template
  (`docker:python @ a1b2c3d`).
- O comando grava `.petrovault/templates.json` na pasta. O arquivo registra
  qual template entrou, de qual commit e quando. Pode ir para o git.

### Como o nome funciona

`docker:python` quer dizer **tipo** `docker` e **template** `python`. O tipo
aponta para o vault `template-docker`, e o template é a pasta `python/` dele.
Um tipo novo (`k8s`, `ci`) é outro vault. Um template novo (`laravel`, `php`) é
outra pasta no mesmo vault.

## Para agentes e scripts

- `--json` em qualquer comando devolve JSON em vez de texto.
- As variáveis `PV_TOKEN` e `PV_URL` valem mais que o arquivo de configuração,
  o que serve para CI e para agentes.
- **Código de saída:** `0` para ok, `1` para erro (inclusive conflito sem
  `--force`) e `2` para comando desconhecido.

```
PV_TOKEN=pv_... pv add template docker:python --json
```

## Publicar um template (infra)

1. **Um repositório por tipo:** `petro-templates-docker`, com uma pasta por
   template:

   ```
   petro-templates-docker/
     python/
       Dockerfile
       docker-compose.yml
       .dockerignore
       .env.example
       template.json
     laravel/
       ...
   ```

2. **`template.json` é opcional** e não vai para o projeto. Por enquanto, só a
   descrição:

   ```
   { "descricao": "Python 3.12 com compose" }
   ```

3. **Cadastre o vault** em Vaults › Novo vault, com o tipo **Template**. O nome
   já começa com `template-`: digite só o tipo (`docker`). Inclua o repositório
   no acesso do GitHub App antes.
4. **Para publicar uma mudança**, faça o merge no repositório. O PetroVault lê
   o commit novo no próximo pull e a `pv` passa a entregar a versão nova.

**Regras do pacote:**

- `.env`, chaves e certificados nunca saem. `.env.example` sai.
- Um arquivo com cara de segredo (token, senha escrita no arquivo, chave
  privada) **bloqueia o template inteiro**, e o erro diz qual é o arquivo. Use
  variáveis: `DB_PASSWORD: ${DB_PASSWORD}`.
- Arquivos soltos na raiz do repositório (como o `README.md`) não são
  templates.
- O executável continua executável (`chmod +x` no git).

## Atualizar a `pv`

`pv versao` compara a sua versão com a do servidor e mostra o comando para
atualizar quando há versão nova.

## Problemas comuns

| Mensagem | O que fazer |
| --- | --- |
| `sem token: rode pv login` | Rode `pv login` ou defina `PV_TOKEN`. |
| `token inválido ou revogado` | Crie outro token em Tokens e rode `pv login`. |
| `template docker:x não existe` | Veja os nomes com `pv templates docker`. |
| `já existe(m) na pasta` | Use `--force` para sobrescrever, ou `dir=` para outra pasta. |
| `template ... bloqueado` | O template tem um segredo: avise a infra (o erro diz o arquivo). |
| `não consegui falar com ...` | Confira a rede e o endereço (`PV_URL` ou `pv login url=`). |

## O que vem depois

- **Variáveis no template:** `pv add template docker:python nome=refeitorio
  porta=8010` preenche `{{nome}}` e `{{porta}}` nos arquivos.
- **`pv update template`:** mostra a diferença para o template de hoje e
  aplica.
- **Consulta ao conhecimento:** `pv search`, `pv read` e `pv add note`.
