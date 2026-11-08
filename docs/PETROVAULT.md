# petro-vault

Serviço de conhecimento da Petrovina: um vault Markdown com curador, que
organiza o conhecimento de vários sistemas (repositórios de código e de
documentos, achados de agentes), separado por tag.

- Épico: [DV-286](https://petrovina.atlassian.net/browse/DV-286)
- Arquitetura: [docs/arquitetura.md](docs/arquitetura.md)

## Forma de trabalho

Toda mudança vai numa branch com a chave do Jira (ex.: `DV-287-arquitetura`)
e chega à `main` só por PR.

## Rodar em homologação

1. `cp .env.example .env` e preencher (cada variável está explicada lá).
2. Subir: `sudo docker compose up -d --build` (o compose usa o
   `COMPOSE_PROJECT_NAME` do `.env`; nunca rode sem ele, para não colidir com
   outro conjunto da máquina).
3. Criar uma credencial (a chave aparece uma vez só):
   `sudo docker compose exec api python -m app.cli criar <nome> --ler tag1,tag2 --escrever tag1`
4. Testar: `curl -H "Authorization: Bearer <chave>" http://127.0.0.1:8670/v1/sistemas/tag1/acesso`

## Consultar o conhecimento: API e MCP (DV-293)

Pela tela: aba **Tokens** → Criar token → marque os vaults que a aplicação ou o
agente vai ler (DV-599). O token criado já mostra os comandos abaixo prontos.

Endereço padrão: `http://10.2.2.31:8670` (o servidor do petro-vault). Com uma
credencial só de leitura (`--ler <tag>`, sem `--escrever`), capturada direto na
variável para não precisar copiar a chave:

```sh
K=$(sudo docker compose exec -T api python -m app.cli criar <nome> --ler <tag> | tail -1)
```

```sh
curl -X POST http://10.2.2.31:8670/v1/knowledge/search \
  -H "Authorization: Bearer $K" -H "Content-Type: application/json" \
  -d '{"system_id": "<tag>", "query": "preço do catálogo"}'
curl -H "Authorization: Bearer $K" http://10.2.2.31:8670/v1/notas/sistemas/<tag>/regras/<nome>
```

Fontes, imagens e PDF de um vault de Referência não viram nota: ficam para baixar
(DV-601). Na tela, use a aba **Arquivos**. Pela API:

```sh
curl -H "Authorization: Bearer $K" http://10.2.2.31:8670/v1/sistemas/<tag>/arquivos
curl -H "Authorization: Bearer $K" -o logo.png http://10.2.2.31:8670/v1/arquivos/<tag>/assets/logo.png
curl -H "Authorization: Bearer $K" -o assets.zip "http://10.2.2.31:8670/v1/sistemas/<tag>/arquivos.zip?pasta=assets"
```

MCP no Claude Code (ferramentas `list_systems`, `search_knowledge`, `read_note`,
`list_files` e `get_file`; esta devolve um link de 15 minutos e o `curl` pronto
para o agente salvar o arquivo no projeto).
`--scope user` deixa o servidor disponível em qualquer pasta:

```sh
claude mcp add --scope user --transport http petro-vault http://10.2.2.31:8670/mcp \
  --header "Authorization: Bearer $K"
```

## Cadastrar um sistema (DV-290)

1. **Chave só leitura da origem**, no servidor (uma por sistema, com o nome
   da tag), e registrar a pública como *deploy key* **sem escrita** no
   repositório de origem:
   ```sh
   ssh-keygen -t ed25519 -N '' -C "petro-vault <tag> (só leitura)" -f "$VAULT_ORIGENS_CHAVES_DIR/<tag>"
   gh repo deploy-key add "$VAULT_ORIGENS_CHAVES_DIR/<tag>.pub" -R <Org>/<repo> -t "petro-vault (só leitura)"
   ```
   Depois, entregar a chave ao curador (o vault-init copia):
   `sudo docker compose up -d --force-recreate vault-init`.
2. **Cadastro**, com uma credencial que escreve na tag:
   ```sh
   curl -X POST -H "Authorization: Bearer <chave>" -H 'Content-Type: application/json' \
     http://127.0.0.1:8670/v1/sistemas \
     -d '{"tag": "<tag>", "perfil": "documentos", "repo": "git@github.com:<Org>/<repo>.git",
          "ramo": "main", "incluir": [], "excluir": ["rascunhos/*"]}'
   ```
   Perfis: `documentos`, `codigo` ou um perfil próprio. `incluir` vazio é tudo.
   Padrão sem barra casa com o nome do arquivo; com barra, com o caminho.

   **Várias origens e leituras (DV-292).** A tag é o sistema; cada origem é
   um repositório, e cada origem tem uma ou mais leituras. Cada arquivo vai
   para a primeira leitura que o aceita. Código e `docs/` no mesmo repositório:
   ```json
   {"tag": "<tag>", "origens": [{"repo": "git@github.com:<Org>/<repo>.git", "leituras": [
     {"perfil": "documentos", "incluir": ["docs/*"]},
     {"perfil": "codigo", "excluir": ["tests/*", "*/static/*"]}]}]}
   ```
   Outra origem num sistema que já existe (ex.: um repositório só de
   documentação): `POST /v1/sistemas/<tag>/origens` com
   `{"nome": "<nome>", "repo": "...", "leituras": [{"perfil": "documentos"}]}`.
   A chave dessa origem fica em `$VAULT_ORIGENS_CHAVES_DIR/<tag>--<nome>`
   (a origem `principal` usa só `<tag>`).
   Editar ramo e leituras (DV-554): `PUT /v1/sistemas/<tag>/origens/<nome>`
   com `{"ramo": "main", "leituras": [...]}`; remover uma origem (não a
   única): `DELETE /v1/sistemas/<tag>/origens/<nome>`. Os dois já pedem um
   pull, e a ingestão reconcilia: o que saiu das leituras sai do vault, o que
   entrou é lido, e o que mudou de leitura sai de uma e entra na outra.
3. **Pull:** `POST /v1/sistemas/<tag>/pull` devolve um id; o curador atende em
   até 30 s. Resultado em `GET /v1/sistemas/<tag>/pulls/<id>` (commits, itens,
   ignorados e o motivo de cada um). Fila: `GET /v1/sistemas/<tag>/fila`.
   Sem pull, a rodada do curador ingere todos os sistemas a cada `VAULT_INTERVALO`.
4. **Tirar um sistema:** `DELETE /v1/sistemas/<tag>` (credencial que escreve
   na tag). Em até 30 s o curador apaga a pasta da tag no vault (com commit),
   o clone, os lotes e o cadastro. A origem não é tocada; a chave de deploy
   (no host e no GitHub) é apagada à mão.

## Tela (DV-547: API da fase 1)

Planejamento em [docs/tela.md](docs/tela.md) e plano das telas em
[docs/tela-plano.md](docs/tela-plano.md). A API da tela fica em `/v1/painel`:

- **Entrar:** `POST /v1/painel/entrar` com `{"login", "senha"}` do AD; só os
  logins de `VAULT_ADMINS` entram (fase 1). Sessão por cookie, 12 h.
- **Sistemas:** `GET /v1/painel/sistemas` (sinais de confiança e selo) e, por
  tag, `.../fila`, `.../pulls`, `.../pulls/<id>`, `.../rodadas`,
  `.../rodadas/<id>`, `.../avisos`, `.../verificacao`, `.../notas`,
  `.../notas/<chave>`, `.../registro`, `.../conflitos`.
- **Ações:** cadastrar (`POST /v1/painel/sistemas`), pedir pull, remover;
  credenciais (`GET`, `POST`, `DELETE /v1/painel/credenciais`).
- O curador grava no `estado.db` o histórico das rodadas e o índice das notas;
  a API continua sem montar o vault.
- **Mais uma origem:** `POST /v1/painel/sistemas/<tag>/origens`; editar e
  remover: `PUT` e `DELETE /v1/painel/sistemas/<tag>/origens/<nome>` (DV-554);
  **apresentação vista:** `PUT /v1/painel/eu/apresentacao` (DV-548).

### A tela (DV-548)

React + TypeScript em `web/`, no visual do protótipo aprovado
([docs/execucao/prototipo](docs/execucao/prototipo)). A imagem da API compila a
tela e a serve na mesma origem: `http://<servidor>:8670/` (rebuild da API com
`sudo docker compose up -d --build api`). Desenvolvimento local:

```
cd web && npm ci && npm run dev    # proxy de /v1 para VAULT_API (padrão 127.0.0.1:8670)
```

Login com a Microsoft fica visível e desabilitado até a DV-574; até lá entra-se
pelo formulário do AD. Mapa (DV-576) e Agente (DV-577) entram como abas quando
existirem.

## Curador com LLM (DV-291)

1. Token próprio do curador: `claude setup-token` e depois
   `sh scripts/token-curador.sh` (cola o token sem mostrar na tela e grava só
   `VAULT_CLAUDE_CODE_OAUTH_TOKEN` no `.env`). Subir de novo:
   `sudo docker compose up -d`.
2. Teste do plugin com chamadas reais:
   `sudo docker compose exec curador /opt/hermes/.venv/bin/python -m petro_vault.curadoria testar-plugin <tag>`.
3. Resultado de cada tag no vault de conteúdo: `sistemas/<tag>/_meta/registro.md`
   (o que o curador fez) e `_meta/verificacao.md` (o verificador).

Repositórios de documentos novos nascem do
[petro-docs-modelo](https://github.com/PetrovinaS/petro-docs-modelo).

Testes: `PYTHONPATH=.:api pytest tests`.
