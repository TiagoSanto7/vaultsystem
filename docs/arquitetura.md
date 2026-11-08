# Arquitetura do petro-vault

Serviço de conhecimento da Petrovina: um vault Markdown com curador, que
organiza o conhecimento de vários sistemas (repositórios de código e de
documentos, achados de agentes), separado por tag.

- **Épico:** DV-286. **Este documento:** DV-287 (validação das diretrizes e quebra do MVP).
- **Origem:** o vault + curador do Petro Observer (DV-63). Este serviço copia
  o que servir de lá, mas não importa código nem depende do Petro Observer.
- **Status:** validado pelo Tiago em 14/10/2026, inclusive os pontos que estavam
  marcados "a validar". Decisões tomadas na validação: seção 3.7 e seção 6.

## 1. Princípios

Lições do Petro Observer (DV-63, DV-257) que valem para todo o serviço:

1. **Caminho fixo é código.** Clone, diff entre commits, filtro por tag,
   filtro de segredos, fila, índices, verificação, commit e push são scripts.
   O LLM só organiza e interpreta o conteúdo que o código entrega.
2. **A tag é garantida no código,** antes de qualquer LLM ver o conteúdo: na
   API (credencial → tags), no curador (o plugin só deixa ler e escrever na
   pasta da tag do lote) e no cabeçalho das notas (o código reescreve o campo
   `sistema` depois do LLM).
3. **O curador não apaga arquivo.** Para tirar uma nota, ele a grava vazia, e
   o código apaga. Toda remoção é código.
4. **O modelo nunca faz conta com datas.** Datas de commit, `criado_em` e
   `atualizado_em` são gravadas pelo código.
5. **Conteúdo é dado, nunca instrução.** Repositórios, documentos e achados
   podem trazer texto que parece ordem; o curador ignora, e o plugin limita o
   estrago possível ao que a tag do lote permite.
6. **Teste na fonte real:** o resultado é conferido no repositório do vault,
   no disco e no banco, e não no que o modelo diz que fez.

## 2. Visão geral

```
 origens                       petro-vault (compose petro-vault-<ambiente>)                   clientes
 ───────                       ─────────────────────────────────────────────                  ────────
 repo git (código) ──┐        ┌──────────────┐   fila por tag   ┌─────────────────────┐
 repo git (docs)  ───┼─clone──▶ ingestão      ├──────────────────▶ curador             │
                     │ +diff  │ (sem LLM)     │                  │ 1 lote = 1 tag      │
 agentes (achados) ──┼─POST───▶ API           │                  │ Hermes + plugin     │
                     │        │ credencial →  │                  │ (só sistemas/<tag>) │
                     │        │ tags          │                  └──────────┬──────────┘
                     │        └──────┬───────┘                              │ pós-lote (sem LLM):
                     │               │ busca (FTS5, filtro por tag)          │ cabeçalho, remoção,
                     │               ▼                                       │ índices, verificador,
 agentes, apps ◀─────┴─── MCP só leitura / HTTP ◀── índice derivado ◀──── vault (git) ── push ──▶ petro-vault-conteudo(-teste)
```

### Componentes (containers)

| Serviço | O que faz | LLM |
| --- | --- | --- |
| `api` | Cadastro de sistemas, pull manual, escrita de achados, busca HTTP e MCP só leitura. Credencial → tags. | Não |
| `curador` | Ciclo: ingestão (clone/diff/fila), lotes do LLM por tag, pós-lote, índices, verificador, índice de busca, commit e push. | Só no passo "organizar" |
| `vault-init` | Clona ou atualiza o vault de conteúdo antes dos outros subirem; copia a chave de deploy com dono e permissão certos. | Não |

- **Stack (a validar):** Python 3, FastAPI para a API e o MCP (transporte HTTP
  streamable, na mesma porta em `/mcp`), SQLite para o estado e para o índice
  FTS5. Imagem do Hermes fixada (`nousresearch/hermes-agent:v2026.9.11`, a
  mesma do observer) para o curador, que usa perfil, plugin e `--oneshot`.
- **Estado (volume `estado`):** `estado.db` (sistemas, credenciais, fila,
  commits processados), `origens/<tag>/` (clones), `lotes/` (conteúdo que o
  curador recebe), `busca.db` (índice derivado, recriável).
- **Chave de deploy (volume `curador`):** só o curador monta; a API nunca
  vê a chave nem o vault. O mesmo vale para as chaves só leitura das origens
  (`/opt/curador/origens/<tag>`, DV-290).
- **Fuso:** datas gravadas pelo serviço em America/Cuiaba (UTC−4), alinhado
  ao Petro Observer (DV-299, decidido em 15/10/2026).
- **Ingestão no curador (DV-290):** a API só grava o cadastro e o pedido de
  pull no `estado.db`; quem clona, faz o diff e enche a fila é o curador, o
  único com as chaves das origens. Por isso o pull é assíncrono: devolve um
  id, e o curador atende em até 30 s. O clone é *bare* (sem árvore de
  trabalho): nenhum arquivo da origem, nem um `.env`, é gravado como arquivo
  no disco; só o conteúdo filtrado vai para `lotes/`.
- **Código compartilhado:** `petro_vault/` (estado, filtros, ingestão), só
  biblioteca padrão, usado pela API e pelo curador (que roda na imagem do
  Hermes e não instala pacotes).
- **Ambiente de homologação:** servidor 10.2.2.31, `COMPOSE_PROJECT_NAME=petro-vault-tiago`,
  API em `127.0.0.1:8670` (o observer usa 8642, 8650 e 8660, que é o painel dele;
  a 8660 proposta antes estava ocupada, corrigido na DV-289). Nada é
  compartilhado com o compose `petro-observer-tiago`.

## 3. Validação das 6 diretrizes do DV-286

### 3.1 Tag garantida em código — **concordo, com dois acréscimos**

- **Na API:** cada credencial tem uma lista de tags de leitura e outra de
  escrita (`estado.db`, chave guardada só como hash). Pedido para tag fora da
  lista: 403, antes de tocar no conteúdo. Busca sem tag usa todas as tags de
  leitura da credencial, nunca mais que isso.
- **Acréscimo 1, no curador:** cada lote do LLM é de uma tag só. O plugin
  (`pre_tool_call`) só deixa ler e escrever em `sistemas/<tag>/`, no lote
  atual e nas regras e modelos do perfil. É o mesmo mecanismo do plugin
  `petro-curador`, que já bloqueia tudo fora de `/opt/vault`.
- **Acréscimo 2, no cabeçalho:** depois do lote, o código reescreve
  `sistema: <tag>` (e os campos de origem e data, ver 3.3) em toda nota
  mudada. O LLM pode errar o campo; o código corrige sem perguntar.

### 3.2 Uma pasta por tag — **concordo**

```
README.md
_regras/               por PR: comum.md, documentos.md, codigo.md, <perfil próprio>.md
_templates/<perfil>/   por PR: um modelo por tipo de nota
sistemas/<tag>/
  _meta/               origem.json e verificacao.md (código); registro.md e conflitos.md (curador)
  indices/             gerado pelo código
  ...                  pastas do perfil (3.4)
```

- **Fila fora do vault:** os itens ficam em `estado.db` e `lotes/`, e não em
  `_inbox/` dentro do repositório (o observer precisou de `.gitignore` para
  isso). O vault só tem conhecimento.
- **Ligação entre sistemas (a validar):** no MVP, o curador não lê nem escreve
  fora da própria tag, então não cria ligação entre sistemas. Ligação
  explícita entra depois, num campo próprio (`relacionados: ["<tag>/<nota>"]`)
  que o verificador confere e a busca respeita (só mostra o link se a
  credencial lê a outra tag).

### 3.3 O repositório de origem é a fonte da verdade — **concordo, com o fluxo abaixo**

1. **Primeira ingestão** é o diff da árvore vazia até o `HEAD`: o mesmo
   caminho do pull, sem caso especial.
2. **Pull:** `git fetch` e `git diff --name-status --find-renames <processado>..<novo>`.
   Renomeado vira removido + adicionado.
3. **Filtros em código, antes da fila:** padrões de inclusão e exclusão do
   cadastro, binários, arquivos acima do limite de tamanho, `vendor/`,
   `node_modules/`, lockfiles e **segredos** (`.env`, chaves, certificados, e
   linhas com cara de token, que são mascaradas). O LLM só recebe o que passou.
   Detalhes (DV-290, `petro_vault/filtros.py`): `.env.example` e afins entram,
   mascarados; arquivo com chave privada no conteúdo fica fora; valor que é
   código (`token = os.environ.get(...)`) não é mascarado. Arquivo modificado
   que deixa de passar no filtro (ficou grande, virou binário) vira item
   `removido`, para o curador tirar o que veio dele. Item na fila de um
   caminho que mudou de novo antes de o curador vê-lo é substituído.
4. **Origem em cada nota:** `origens: ["caminho/no/repo", ...]` e
   `commit_origem`, gravados pelo código no pós-lote.
5. **Arquivo apagado na origem:** o código acha as notas com aquele caminho
   em `origens`. Nota que só tinha ele: o código apaga. Nota com outras
   origens: o código tira o caminho e manda um item `remocao` ao curador,
   que revisa o texto e os links (e grava vazio o que tiver de sair).
6. **Commit processado** só avança depois que todos os itens daquele diff
   aparecem no `registro.md` da tag (a regra do `organizar.py`: o que não foi
   registrado volta na próxima rodada).
7. **Verificador:** nenhuma nota com `origens` apontando para arquivo que não
   existe no commit processado.

### 3.4 Dois perfis de curador — **concordo, com um terceiro caso: perfil próprio**

Perfil = SOUL do curador + `_regras/<perfil>.md` + `_templates/<perfil>/` +
pastas. O tipo do sistema é escolhido no cadastro.

| Perfil | Origem | Pastas em `sistemas/<tag>/` (a validar) |
| --- | --- | --- |
| `documentos` | repositório de documentos | `documentos/` (uma nota por arquivo da origem, 1:1, o que deixa a remoção trivial), `assuntos/` (síntese com evidências) |
| `codigo` | repositório de código | `modulos/` (um por pasta relevante), `regras/` (regras de negócio), `integracoes/` (sistemas externos chamados), `apis/` (o que o sistema expõe), `dados/` (entidades e tabelas). Não copia código. |
| próprio | achados por API, como o observer | Pastas e modelos do sistema, versionados neste repositório (ex.: `perfis/petro-observer/` com equipamentos, tipos, ocorrências, aprendizados, consultas, documentos) |

- **Por que o terceiro caso:** a tag `petro-observer` não vem de um
  repositório; vem de achados escritos pela API e tem uma estrutura própria.
  Sem perfil próprio, a migração reescreveria o vault, e a diretriz era migrar
  sem reescrever.

**Perfil `documentos`, como ficou (DV-291):**

- **Caminho da nota é código:** `docs/a.md` → `sistemas/<tag>/documentos/docs/a.md`
  (outro formato ganha `.md` no fim). O lote diz ao curador onde escrever.
- **Cabeçalho do código** (depois do curador, sem perguntar): `sistema`,
  `tipo_nota` (pela pasta), `origens`, `commit_origem`, `criado_em`,
  `atualizado_em`. Nos assuntos, `origens` é a união das origens dos
  documentos citados. Arquivo na estrutura padrão (3.7) traz `tipo`,
  `responsavel` e `revisado_em`, copiados como `origem_*` sem LLM.
- **Remoção:** o código tira o caminho das `origens`; nota que fica sem
  origem é apagada pelo código (inclusive assunto que só citava aquele
  documento); as que ainda citam o que saiu vão ao curador revisar. Remoção
  sem nada a revisar nem chega ao LLM.
- **Plugin** (`curador/perfil/plugins/petro-vault-curador`): no lote da tag
  X, lê só o lote, `_regras/`, `_templates/documentos/` e `sistemas/X/`;
  escreve só em `documentos/`, `assuntos/`, `_meta/registro.md` e
  `_meta/conflitos.md` de X. Toda chamada vai para `/opt/curador/plugin.log`
  (`python -m petro_vault.curadoria testar-plugin <tag>` faz o teste com
  chamadas reais).
- **Várias origens por tag** (feito na DV-292): ver abaixo.

**Várias origens e leituras (DV-292):** a tag é o sistema; cada **origem**
(tabela `origens`) é um repositório e ramo, com chave só leitura, clone e
commits próprios; cada origem tem **leituras** (`{perfil, incluir,
excluir}`), e cada arquivo vai para a primeira que o aceita. Cada item da
fila guarda origem e perfil; cada lote é de uma tag e um perfil. Em
`origens` das notas, a origem `principal` aparece só com o caminho; as
outras, como `<origem>:<caminho>` (notas de documento delas ficam em
`documentos/<origem>/...`). O cadastro antigo (repo e perfil no topo) vira a
origem `principal`, e os sistemas da DV-290/291 foram migrados assim.

**Perfil `codigo`, como ficou (DV-292):**

- **Lote por pasta** da origem (até `VAULT_LOTE_CODIGO` arquivos), para o
  curador ver o módulo inteiro; a nota do módulo (`modulos/<pasta>.md`) tem
  caminho calculado pelo código.
- **Origens declaradas e conferidas:** a nota de código não é 1:1 com um
  arquivo, então o curador declara `fontes`; o código confere cada uma no
  commit da origem e só as que existem viram `origens` (inventada é
  descartada e logada).
- **Arquivo modificado:** o lote lista as notas ligadas a ele (que o têm em
  `origens`); só essas devem mudar, e o código avisa no log se outra mudar.
- **Remoção:** igual à de documentos; além disso, link para nota que o
  código apagou vira texto na hora, nas notas que vão para revisão.
- **Segredos:** a ingestão já mascara; o verificador procura os mesmos
  padrões em toda nota e acusa.

### 3.5 Acesso pelo serviço — **concordo, com o MVP só com texto completo**

- **Leitura:** MCP só leitura (`buscar(consulta, tags?)`, `ler_nota(caminho)`)
  e os mesmos endpoints em HTTP. O filtro por tag é aplicado na consulta
  SQL, a partir da credencial.
- **Busca no MVP:** SQLite FTS5, refeito pelo código ao fim de cada rodada a
  partir das notas (derivado, pode ser apagado e recriado). A parte semântica
  do DV-276 fica para depois da escolha do modelo de embeddings.
- **Implementado na DV-293, etapa 1 (30/10/2026):**
  - `POST /v1/knowledge/search` no contrato da seção 9 do documento de execução: `system_id` (a tag do vault), `query`
    (1 a 500), `verification` (`all` padrão, ou `verified`), `limit` (1 a 20, padrão 5). Campo desconhecido dá 400.
    Cada resultado traz `note_id`, título, trecho, estado e `provenance` (repositório, arquivo, ramo, commit e link),
    mais `has_more`.
  - `GET /v1/notas/<note_id>`: a nota inteira em markdown, com a mesma proveniência.
  - MCP em `/mcp` (Streamable HTTP, só respostas JSON, sem stream SSE), com a credencial `pv_` em
    `Authorization: Bearer`. Ferramentas só leitura: `list_systems`, `search_knowledge` e `read_note`. Tag fora da
    credencial: 403 no HTTP e erro da ferramenta (`isError`) no MCP, com a mesma mensagem para vault inexistente.
  - O índice FTS5 fica em `estado/busca.db` e é derivado do `notas_indice`. Antes de cada busca, a marca da tag
    (quantas notas e o maior rowid, que mudam a cada rodada) é conferida e, se mudou, o índice da tag é refeito. O
    curador não precisa saber da busca. Tokens com acento normalizado (`credito` acha `crédito`); cada palavra da
    consulta vira termo entre aspas, unido por OR e ordenado por bm25, com peso maior no título e no nome do arquivo.
  - Até a DV-575, toda nota sai como `unverified`; `verification: verified` volta vazio.
  - Não é só para sistemas de código: o design system da empresa vai ser um vault consumido por este mesmo canal
    (decisão de 30/10/2026).
- **Tokens pela tela (DV-599):** a aba Tokens lista todos os tokens. Criar um token é dar um nome (a aplicação ou
  o agente) e marcar os vaults que ele lê; só leitura. Uma aplicação que precisa de 3 vaults usa um token só, com os 3
  marcados: `list_systems` mostra quais são, cada consulta diz o `system_id` e um vault fora do token dá 403. Os vaults
  de um token mudam sem trocar a chave (`PATCH /v1/painel/credenciais/<nome>`). O último uso é gravado a cada chamada
  (no máximo uma vez por minuto). O token criado já vem com os comandos de MCP e de busca, com o endereço público
  (`VAULT_URL_PUBLICA`, padrão `http://10.2.2.31:8670`).
- **Escrita:** `POST /v1/sistemas/<tag>/achados` → fila → curador. A
  resposta é um id; `GET .../achados/<id>` diz `na_fila`, `incorporado` ou
  `recusado`. Ninguém escreve direto no vault, só o curador.
- **Documentos enviados** (contratos 2 e 3 do observer): no serviço, viram um
  endpoint de upload com o mesmo ciclo (original nunca apagado, remoção
  bloqueia a leitura na hora). **Entra só com a migração do observer**, que é
  quem precisa disso.

### 3.6 Credencial da organização por GitHub App — **feito na DV-573**

- **GitHub App `petro-vault`** (App ID 5392441) instalado na PetrovinaS, só
  leitura de conteúdo e metadados, nos repositórios escolhidos na instalação.
  Um admin da organização instala uma vez; depois, qualquer pessoa adiciona
  uma origem pela tela escolhendo o repositório numa lista, sem chave no
  servidor. Repositório fora da lista: o admin o inclui na instalação.
- **Origem `https://github.com/<dono>/<repo>`** é lida pelo App
  (`petro_vault/github_app.py`): o curador assina um JWT com a chave privada,
  troca pelo token da instalação (1 h) e faz o `git fetch` por HTTPS com o
  token num cabeçalho passado por variável de ambiente. O token não fica na
  URL, no config do clone, no log, no banco nem no prompt. Erros separados:
  App não instalado no repositório, ramo inexistente, limite do GitHub,
  GitHub indisponível, credencial do App recusada.
- **Lista para a tela:** a API não vê a chave do App. O curador grava os
  repositórios e ramos em `github_repos` quando a tela pede (até 30 s) ou a
  cada 10 min.
- **Origem `git@...`** continua com a chave de deploy só leitura por
  repositório, até migrar. O vault de conteúdo continua com a chave de deploy
  com escrita. Nada de token pessoal.

### 3.7 Estrutura padrão dos repositórios de documentos (decidido na validação)

Hoje o único repositório com documentação pronta é o
[petro-observer-vault](https://github.com/PetrovinaS/petro-observer-vault).
Os repositórios de documentos dos outros sistemas ainda vão nascer, e nascem
numa **estrutura padrão definida por este serviço**.

- **Na tarefa 4,** a estrutura padrão sai junto com o perfil `documentos` e
  vira um repositório modelo (*template* do GitHub) na PetrovinaS: pastas,
  cabeçalho mínimo de cada documento e um README de como escrever.
- **Feito (DV-291):** [PetrovinaS/petro-docs-modelo](https://github.com/PetrovinaS/petro-docs-modelo),
  com tudo em `docs/` (`processos/`, `manuais/`, `decisoes/`, `referencias/`),
  cabeçalho `titulo`, `tipo`, `responsavel`, `revisado_em`, e `modelos/`.
  Documentação sem código: "Use this template" cria `petro-docs-<assunto>`,
  um repositório novo e independente. Projeto com código: copiar `docs/`
  para dentro do repositório do projeto. Cadastro: perfil `documentos`,
  `incluir: ["docs/*"]`, `excluir: ["docs/README.md"]`.
- **Ganho:** com a estrutura conhecida, o código entende mais coisas sem LLM
  (tipo de documento, sistema, autor), e o curador recebe menos para
  interpretar.
- **Fora do padrão:** um repositório fora do padrão ainda é aceito (o
  petro-observer-vault, por exemplo). Nesse caso, o curador organiza a partir
  do conteúdo.

### 3.8 Classificação por árvore no Novo vault (DV-589)

"Novo vault" tem duas etapas. Na primeira, o nome e os repositórios (da lista
do GitHub App). Na segunda, a árvore de pastas de cada repositório, com um
seletor por pasta ou arquivo: documentos, código ou ignorar. A subpasta segue
a pasta de cima, a menos que tenha a própria classificação (a mais próxima
vale). O que os filtros fixos já tiram (dependências, lockfiles, segredos,
grandes demais) aparece travado.

- **A árvore** vem do GitHub pelo App (`git/trees` recursivo, sem clone). A
  API grava o pedido em `arvores`; o **atendente** do curador
  (`petro_vault/atendente.py`, em segundo plano no `ciclo.sh`) olha os pedidos
  a cada 2 s e grava os arquivos e uma sugestão (raiz = código; `docs/` =
  documentos; `assets/`, `fonts/`, `android/`, `ios/` = ignorar; regra dos
  .md ligada).
- **A classificação vira leituras** (`petro_vault/arvore.py`), as mesmas que
  o curador já usa: documentos primeiro, código depois. Incluir = as pastas do
  perfil cuja pasta de cima é de outro destino (ou nada, se a raiz é do
  perfil); excluir = as pastas de outro destino logo abaixo de uma do perfil.
  Assim arquivo novo segue a pasta. O resultado é exato para os arquivos do
  commit da árvore (testado com 300 classificações sorteadas). A
  classificação fica em `origens.classificacao`, para editar pela árvore
  depois.
- Origem por SSH continua com as leituras escritas à mão.
- **Deploy:** `curador/ciclo.sh` e `petro_vault/` entram no curador por bind
  mount, e o `docker compose up -d --build` não recria o curador quando só
  eles mudam. O código Python novo vale na rodada seguinte (cada passo é um
  processo novo), mas o `ciclo.sh` e o atendente só mudam com
  `docker compose restart curador`. Em 29/10, sem esse restart, o atendente
  não subiu e a tela ficou esperando a árvore; por isso a tela avisa depois
  de 20 s sem resposta.
- **Editar pela árvore** (Fontes › Editar ramo e pastas, origem do App): a
  árvore abre com a classificação de hoje. A classificação gravada vale se
  ainda leva cada arquivo aonde as leituras levam. Se não houver (origem
  cadastrada pelo formulário antigo), `arvore.classificacao_de` tira uma
  das leituras: a menor quantidade de pastas e arquivos com destino próprio
  que reproduz o destino de cada arquivo, por programação dinâmica na
  árvore (testado com 300 classificações sorteadas). Antes de salvar,
  `POST /arvores/{id}/leituras` com tag e origem devolve os arquivos que
  mudam de destino (`arvore.mudancas`), e a tela agrupa em "saem do vault",
  "entram em" e "passam de X para Y". Salvar grava as leituras e a
  classificação; editar pelo formulário de padrões apaga a classificação.
  DV-608 (04/11): a resposta traz também `impacto` (`arvore.impacto`):
  quantos arquivos vão ao curador (LLM), por destino, e a estimativa de
  lotes (documentos e referência explicada em grupos de VAULT_LOTE; código
  por pasta, em grupos de VAULT_LOTE_CODIGO; sem o limite de bytes nem as
  revisões de notas quando um arquivo sai). Se algo vai ao curador, salvar
  pede um segundo clique com esse custo; a partir de 100 arquivos, pede o
  nome do vault digitado. Veio do refeitório, que foi a 1154 itens com um
  clique em 03/11.
  "Adicionar repositório" do App também passa pela árvore.
- **Regra dos .md** (decidida em 30/10, comentários 11949 e 11950 do DV-589):
  uma caixa na árvore, ligada por padrão, que manda todo `.md` para
  documentos, menos nas pastas ignoradas e os `.md` com destino próprio. Os
  repositórios ganham README e specs sem ninguém abrir o painel; sem a regra,
  um `.md` novo numa pasta de código seria curado como código. Fica na
  classificação como a chave `"*.md": "documentos"` e vira uma leitura de
  documentos a mais (incluir `*.md`, excluir as pastas ignoradas inteiras e os
  `.md` classificados um a um), entre a de documentos e a de código. Ao
  derivar a classificação das leituras antigas, a regra entra quando deixa a
  árvore menor (no refeitorio: 13 classificações em vez de 25).
- **Padrão de arquivo exato:** `filtros.casa` compara padrão sem barra com o
  nome do arquivo em qualquer pasta, então `README.md` da raiz pegaria todos
  os README. O arquivo da raiz sai como `[/R]EADME.md` (a classe tem barra e
  só casa com a letra), e curingas no nome viram classe (`[*]`). A API recusa
  leituras geradas que não reproduzam a classificação arquivo por arquivo.

### 3.9 Mapa de relações (DV-576)

A aba **Mapa** mostra o vault, as fontes e as notas, só com relações que
existem no índice das notas (`notas_indice`). Nada é inferido para preencher o
desenho. `petro_vault/mapa.py` monta o grafo por pedido (cerca de 20 ms para
as 719 notas do refeitorio), e `GET /v1/painel/sistemas/{tag}/mapa?foco=&limite=`
devolve a vizinhança de um nó e os totais do índice.

- **Relações:**
  - **compõe:** origem → vault, pasta → vault e nota → pasta;
  - **fundamenta:** origem → nota, pelo campo `origens`; os arquivos aparecem no painel de detalhes;
  - **documenta:** documento → assunto, pelas `evidencias` do assunto;
  - **menciona:** os outros `[[links]]`, como citação e não como dependência.

  Os índices gerados (`indices/`) ficam de fora, e por isso o total bate com
  o contador de notas do vault.
- **Expansão progressiva:** o mapa mostra um foco por vez, com no máximo 24
  notas. "Mais notas" aumenta o limite e "Explorar a partir daqui" muda o
  foco. A trilha leva de volta, e o foco fica na URL (`?foco=`). Numa pasta,
  as notas mais ligadas vêm primeiro. Numa nota, vêm primeiro as que a
  documentam e depois as menções nos dois sentidos.
- **Desenho:** o foco fica no centro. À esquerda fica de onde vem (pasta,
  fontes, notas que citam o foco) e à direita o que ele tem ou cita. Com mais
  de 6 vizinhos de um lado, as colunas ficam intercaladas e as linhas passam
  nos vãos.
- **Acessibilidade:** cada nó é um botão no Tab. Enter seleciona e, de novo,
  explora. As setas movem o mapa, +/− ampliam e 0 centraliza. O painel de
  detalhes lista em texto todas as relações do foco, inclusive as que não
  couberam no desenho.
- "Perguntar sobre isso" fica desabilitado até o Agente (DV-577).
- **Visão de grafo** (30/10, pedida pelo Tiago), no estilo do Graph view do
  Obsidian. Um seletor alterna entre Colunas e Grafo, e o Grafo fica em
  `?vista=grafo`.
  - **Dados:** `GET /v1/painel/sistemas/{tag}/mapa/grafo` devolve todas as
    notas e as relações entre elas.
  - **Desenho:** a simulação de forças vem do `d3-force` 3.0.0, primeira
    dependência nova da tela, e o desenho é em canvas.
  - **Cor pelo perfil:** documentos e assuntos em azul, código em laranja.
    Uma cor por pasta (7) foi testada com o validador de paleta e falhou: nem
    com visão normal os pares se distinguem. A pasta se esconde ou aparece
    pela legenda.
  - **Interação:**
    - o tamanho do ponto acompanha o número de ligações;
    - clicar destaca as vizinhas;
    - o "Grafo local" mostra a nota e até 3 saltos;
    - a busca leva até a nota;
    - "Ver relações em colunas" abre a nota na outra visão.
  - **Teclado:** o canvas não tem acesso nó a nó. O caminho pelo teclado é a
    busca e a visão em colunas.
  - **Notas-ponte:** notas com mais de 100 ligações ficam escondidas por
    padrão, com uma caixa para mostrar. No refeitorio são `app--tests` e
    `app--services`, com 231 e 230 ligações. Elas ligam quase todas as regras
    e juntavam o código num bolo só. O rodapé mostra quantas notas estão
    visíveis, por exemplo "717 de 719".
  - **Forças**, como no Obsidian: repulsão, distância das ligações e
    gravidade do centro. A mola usa a força padrão do d3 (1 ÷ ligações do nó
    menos ligado), para que uma nota muito ligada não esmague as vizinhas.

### 3.10 Vault de Referência, modo literal (DV-600)

Para conteúdo que precisa chegar exato a quem consome: design system, normas, manuais já escritos. Decisão de 30/10/2026
(DV-591, comentários 11970 e 11971).

- **Tipo no Novo vault:** *Sistema* (o curador escreve notas, como sempre) ou *Referência*. O tipo só escolhe o ponto
  de partida da árvore: na Referência, tudo vem como `referencia`, menos assets, fontes e pastas de ferramenta
  (`.claude`, `.vscode`, `.idea`). Num vault de Sistema, uma pasta também pode ser marcada como referência.
- **Perfil `referencia`, sem LLM** (`petro_vault/literal.py`): cada arquivo vira `referencia/<caminho>.md`. Um `.md`
  entra inteiro, como está; outros arquivos de texto entram num bloco de código com a linguagem. Arquivo removido na
  origem: a nota sai. Roda antes dos lotes do curador e não conta no teto de lotes.
- **Cabeçalho só do código:** `literal: true` e `hash_literal`. O verificador acusa `literal_editado` quando o corpo não
  bate com o hash (alguém editou a nota no vault em vez de editar a origem). Links e assuntos das notas literais não
  são conferidos nem normalizados: o texto é o da origem.
- **Regra dos .md:** não tira os `.md` de uma pasta de referência.
- **Segredos:** o conteúdo passa pelos mesmos filtros da ingestão. Para não estragar código, a máscara de atribuição
  deixou de pegar pseudo-classe de CSS (`.password-toggle:focus-visible{`) e nome que termina em ponto (fim de frase
  num texto de JavaScript).
- **"Quer ajustar o repositório antes de incluir?":** seção opcional do Novo vault com um pedido pronto, por tipo, para
  um agente organizar o repositório (Sistema: `docs/` no padrão do petro-docs-modelo; Referência: `tokens/`,
  `fundamentos/`, `componentes/`, `padroes/`). A mudança só chega ao PetroVault depois do merge no ramo cadastrado.
- **Referência + explicação (fase 2, perfil `referencia-explicada`):** o ponto de partida do tipo Referência. O código
  faz a mesma cópia literal, e o curador (SOUL `SOUL-referencia-explicada.md`, regras
  `_regras/referencia-explicada.md`) escreve **guias** em `guias/<assunto>.md`: para que serve, quando usar, variações,
  cuidados. **O curador nunca escreve código:** marca o trecho numa linha (`<!-- trecho: arquivo#id -->` para um
  elemento HTML, `<!-- trecho: arquivo:L1-L40 -->` para linhas) e o código cola o trecho exato, tirado da nota
  literal, até `<!-- /trecho -->`. Bloco de código escrito pelo curador é tirado. Os trechos são colados de novo a
  cada rodada (a origem mudou, o guia acompanha); o verificador acusa `trecho_divergente`, `codigo_fora_de_trecho`
  e `trecho_corta_bloco`.
  Os números de linha são os do arquivo de origem: o lote traz uma cópia numerada de cada arquivo de referência em
  `fontes/`, e o plugin não deixa o curador ler as notas de `referencia/` (o cabeçalho delas desloca as linhas). O item
  lista os ids HTML do arquivo. Trecho de um `.md` sai com a linguagem do bloco de código de onde veio (CSS como `css`,
  não `markdown`); linhas que pegam blocos inteiros saem como estão, sem cerca em volta; a linha de crases pega
  junto na borda do bloco é descartada (o curador erra por uma) (ajustes de 03/11/2026).
  **Aba Renderização** (03/11/2026): no painel, um vault com origem de Referência mostra uma página `.html` de
  `referencia/` rodando. `GET /v1/painel/sistemas/{tag}/renderizar?pagina=…&extra=…` (só administradores,
  `api/app/renderizacao.py`) devolve o HTML com tudo embutido:
  - CSS e JS saem das notas literais;
  - imagens e fontes saem do clone bare da origem no commit da página (só essas extensões, até 5 MB cada e 40 MB no
    total);
  - o que não resolve vira aviso.

  A tela mostra a página num iframe `srcdoc` com `sandbox="allow-scripts"`, sem `allow-same-origin`, então ela não
  vê o cookie da sessão nem a API. A imagem da API passou a ter `git`.
  `origens` do guia = arquivos dos trechos e das notas literais citadas. Arquivo removido: a nota literal sai e os
  guias que a usavam vão para revisão do curador. A opção "referência (só literal)" continua para quem não quer guias.

### 3.11 Arquivos binários para baixar (DV-601)

Decisão de 03/11/2026, no teste do vault designsystem. Fontes e logos não viram nota, e quem consome o design
system precisava buscá-los no repositório.

- **O que entra:** o arquivo de uma leitura de Referência (`referencia` ou `referencia-explicada`) que passa nos
  filtros de caminho da ingestão e tem uma destas extensões:
  - fontes: woff, woff2, ttf e otf;
  - imagens: png, jpg, gif, webp, svg e ico;
  - pdf.

  Cada arquivo tem até 5 MB, e o pacote zip até 40 MB. Binário não passa pelo filtro de segredo: a lista fechada de
  extensões é a proteção.
- **De onde vem:** a lista sai do clone bare de cada origem, no commit processado (`petro_vault/arquivos.py`), sem
  tabela nem fila. Os bytes são lidos do clone na hora, com a mesma leitura da aba Renderização.
- **API** (credencial `pv_`, tag em `ler`):
  - `GET /v1/sistemas/{tag}/arquivos[?pasta=]` lista os arquivos;
  - `GET /v1/arquivos/{tag}/{caminho}[?origem=]` baixa um arquivo;
  - `GET /v1/sistemas/{tag}/arquivos.zip[?pasta=]` baixa o pacote.

  O download sai como anexo, com `Content-Security-Policy: sandbox` e `nosniff`: um SVG ou PDF da origem nunca roda
  na origem da tela.
- **MCP:**
  - `list_files` lista os arquivos.
  - `get_file` devolve um link assinado (HMAC-SHA256 de tag, origem, caminho e validade) que vale 15 minutos e não
    pede credencial, junto com o `curl -o` pronto. Imagem raster de até 100 KB vem também como conteúdo de imagem.

  O arquivo não vai em base64 pela resposta, para não lotar o contexto do agente. A chave dos links é
  `VAULT_CHAVE_LINKS`; sem ela, o serviço usa `estado/links.chave`, criada na primeira vez.
- **Tela:** a aba Arquivos (só em vault com origem de Referência) baixa cada arquivo, cada pasta ou tudo.
- **Árvore:** a sugestão do vault de Referência não manda mais `assets/` e `fonts/` para "ignorar".
- **Mudança:** um vault já cadastrado com `assets/` em "ignorar" precisa reclassificar a pasta (Editar ramo e
  pastas) para os arquivos aparecerem.

### 3.12 Infraestrutura de containers (DV-602)

Decisão de 03/11/2026. Infraestrutura ganha um padrão de documentação, como módulos, regras, integrações, APIs e
dados.

- **Arquivos (1ª versão, containers):** Dockerfile (`Dockerfile`, `Dockerfile.*`, `*.dockerfile`), compose
  (`compose*.yml` e `docker-compose*.yml`), `.dockerignore`, nginx (`.conf` com nginx no nome ou na pasta) e
  `Caddyfile`. CI e Kubernetes ficam para depois.
- **Leitor determinístico** (`petro_vault/infra.py`): tira os fatos dos arquivos, no clone e no último commit
  ingerido.
  - **Do compose:** serviço, container, imagem ou build, portas (formas curta e longa), volumes, redes,
    `depends_on`, healthcheck, restart e logging.
  - **Do Dockerfile:** estágios e imagens base, EXPOSE, HEALTHCHECK, USER, CMD/ENTRYPOINT e os arquivos copiados.
  - **Do nginx e do Caddy:** `location → proxy_pass/return/arquivos` e `reverse_proxy`.
  - **Variáveis de ambiente, ARG e ENV:** só os nomes.
  - **YAML com erro:** vira aviso só com a linha, porque a mensagem do PyYAML traz trecho do arquivo.
  - **Sem PyYAML:** sem PyYAML no ambiente (a imagem do Hermes), um leitor próprio do básico do compose dá o mesmo
    resultado.
- **Serviço:** cada serviço do compose é um serviço. Juntam-se a ele:
  - o Dockerfile do build;
  - o `.dockerignore` e os `.conf` de proxy do contexto;
  - os arquivos de infra montados como volume.

  Um Dockerfile que nenhum compose usa vira um serviço com o nome da pasta, ou com a tag se estiver na raiz.
- **Notas:** `infra/<serviço>.md`, uma por serviço, mais `infra/visao-geral.md`, nos perfis código e
  referência + explicação. Na Referência, o arquivo continua literal em `referencia/`.
  - **Cabeçalho, gravado pelo código a cada rodada (`infra.carimbar`):**
    - fatos: `servico`, `container`, `imagem`, `build`, `portas`, `volumes`, `redes`, `depende_de`,
      `healthcheck`, `restart` e `proxy`;
    - mais `origens`.

    Se o arquivo muda, o cabeçalho acompanha sem LLM.
  - **Texto do curador:** segue o modelo `_templates/<perfil>/infra.md`.
- **Lote:** o item de um arquivo de infra traz as notas a escrever e os fatos lidos. No perfil código, o arquivo não
  vai para o módulo da pasta.
- **Adoção:** um arquivo de infra já processado antes desta mudança, ou cujos serviços não têm nota, entra na fila
  **uma vez** (motivo `infra: documentar em infra/ (DV-602)`). Assim o vault existente ganha as notas sem ser
  recriado.
- **Verificador:** acusa `infra_sem_servico`, a nota de um serviço que sumiu dos arquivos.
- **Trechos:** na Referência, a nota de infra mostra o arquivo por marcador de trecho, como os guias. O código cola
  o trecho a cada rodada, e o verificador confere. O Dockerfile sai como `dockerfile` e o nginx como `nginx`
  (ajuste de 03/11, depois da primeira rodada real).

### 3.13 Mapa de infraestrutura (DV-603)

Pedido de 03/11/2026: incluir a infraestrutura de containers no mapa de relações, com um visual de canvas de
serviços (inspirado no Railway, sem a marca dele).

- **Dados:** `GET /v1/painel/sistemas/{tag}/infra` devolve o `infra.grafo`, que sai só do leitor do DV-602, sem LLM.
  - **Serviços:** o tipo vem da imagem (proxy, site estático, aplicação, banco, cache ou fila). Cada um traz portas,
    volumes (nomeado ou bind, somente leitura), redes, healthcheck, restart, rotas do proxy, nomes das variáveis,
    arquivos (com a nota literal, se houver) e a nota `infra/<serviço>`.
  - **Ligações:** `depends_on` e o destino do `proxy_pass`.
  - **Redes do compose.**
- **Tela:** aba Mapa, terceira visão, "Infraestrutura". Ela só aparece se o vault tem serviço.
  - **Canvas:** fundo com grade de pontos, um card por serviço (ícone pelo tipo, imagem, portas e restart como selos
    e ponto de healthcheck), volumes presos ao card e o Host como entrada das portas publicadas.
  - **Linhas:** `depends_on` em linha cheia com seta, proxy tracejado e as redes como regiões.
  - **Layout determinístico:** colunas pelo caminho mais longo de dependência (entrada → proxy → apps → dados).
  - **Interação:** arrastar cards e fundo, zoom, e "Arrumar" volta ao enquadramento.
  - **Painel lateral:** os fatos, "Abrir nota" e os arquivos.
- **Stack** (ajuste de 03/11): cada compose é um stack, com o nome que o docker compose daria ao projeto: o `name:` do
  arquivo; sem ele, a pasta; na raiz, o nome do repositório. No mapa, cada stack é um quadro com nome, arquivo e
  quantidade de serviços, um embaixo do outro. O Dockerfile sem compose fica no quadro "sem compose".
  - **Notas:** o `stack` também vai para o cabeçalho da nota de infra.
  - **Nome repetido:** um serviço com o mesmo nome em outro stack ganha o stack na frente (`monitor-web`).
  - **Ambientes** (overrides como `docker-compose.prod.yml`) ficam para depois.
- **Contraste:** os pares novos ficam em 5:1 ou mais nos temas claro e escuro.

### 3.14 Dependências externas no mapa de infra (DV-604)

Decisão de 03/11/2026: mostrar no mapa o que os containers usam sem fazer parte do stack, como o MySQL do refeitório,
o AD/LDAP, o SAP e serviços HTTP.

- **Fonte:** o `.env.example` (e afins) ao lado do `env_file` que o serviço carrega, mais o `environment:` do
  compose. O `.env` real **nunca** é lido. O exemplo é lido mesmo fora das leituras do vault, porque dele só sai tipo
  e host.
- **O que sai do valor** (`infra.destino`): só o **tipo**; usuário, senha, caminho e query nunca saem. O host:porta é
  lido só para duas coisas: saber se aponta para um serviço do próprio vault e contar destinos diferentes. Logo na
  leitura ele vira um identificador opaco (`d1`, `d2`). **Endereço não aparece no mapa, na API, na nota nem no lote**
  (decisão do Tiago em 03/11, depois de ver os IPs no mapa). No lugar, cada card mostra o **ambiente** tirado do sufixo
  da variável: `_PROD` = produção, `_HOMO`/`_HML` = homologação, `_DEV` = desenvolvimento.
  - **Tipo:** pelo esquema da URL (mysql, postgres, sqlserver, oracle, mongodb, redis, amqp, ldap, smtp, http) ou pelo
    nome da variável (`SL_*`, `SAP_*`, `HANA_*` e `SERVICE_LAYER*` são SAP; `LDAP_*`; `SMTP_*`).
  - **Variável de host sem URL** (`HANA_IP_PROD=10.x`) também vira endereço.
  - **localhost e 0.0.0.0** não são endereço: o card fica sem endereço ("endereço só no .env").
  - **Host que é serviço do próprio vault** (`http://web:8000`) não é externo.
- **Grafo:** um card por tipo, com os ambientes e as variáveis de cada um. Ele traz os serviços que usam,
  os arquivos de onde veio e as notas ligadas (`integracoes/` pelo tipo; quantas notas de `dados/` no caso de banco).
  O cabeçalho da nota de infra ganha `externos` (por exemplo, `SAP (homologação, produção)`).
- **Tela:**
  - **Cards:** tracejados, numa coluna à direita, fora dos quadros dos stacks.
  - **Linhas:** sai uma linha do quadro do stack quando todos os serviços dele usam o externo; senão, uma de cada
    serviço.
  - **Painel lateral:** endereços, variáveis, quem usa e as notas.
- **Filtro de segredo:** `mascarar` passou a ser idempotente para senha de URL. Uma senha já mascarada não conta de
  novo, então o `.env.example` literal num vault de Referência deixou de virar "possível segredo".
- **Marcador de trecho numa linha só de crases** (`arquivo.md:L60`): o código entende como o bloco inteiro e cola o
  conteúdo dele (03/11).
- **Prompt "Ajustar repositório"** (Novo vault, tipos Sistema e Referência): ganhou um bloco de infraestrutura que
  pede para deixar no repositório os arquivos de container, sem mudar o que existe (o que faltar vai para
  `PENDENCIAS.md`), e um `.env.example` completo. Esse exemplo traz os endereços reais (host:porta), senhas
  falsas e o sufixo `_PROD`/`_HOMO` por ambiente. O bloco também diz para não escrever documentação de infra à mão.

### 3.15 Código + cópia literal (DV-608)

Decidido em 04/11 (comentário 12062 do DV-608): o vault de sistema guarda
também o código-fonte, como está, e esse é o padrão da árvore para vault
novo (`arvore.sugestao`: raiz = `codigo-literal`).

- **Perfil `codigo-literal`.** Para a fila e o curador, é o perfil `codigo`
  (`ingestao.leitura_de` devolve `codigo`; `cru=True` devolve o perfil da
  leitura). O curador escreve módulos, regras, integrações, APIs e dados
  como sempre.
- **Cópia, sem fila e sem LLM.** A cada rodada, `literal.copiar_codigo` lê o
  clone no commit processado de cada origem e grava em
  `referencia/<caminho>.md` cada arquivo da leitura, com os mesmos filtros de
  conteúdo da ingestão (tamanho, binário, segredos mascarados) e o mesmo
  formato da nota literal (DV-600). A nota leva `copia_codigo: true` e
  `blob_origem`; o arquivo só é lido de novo quando o blob muda, e só as
  notas com `copia_codigo` são apagadas por este passo (arquivo apagado na
  origem, fora da leitura ou origem removida).
- **Ligação.** `literal.ligar_arquivos` põe no fim de cada nota de código o
  bloco `<!-- arquivos -->` com o link para a cópia de cada arquivo de
  `origens`; o bloco é refeito a cada rodada e some quando não há cópia. O
  curador não escreve esse bloco (`_regras/codigo.md`).
- **Trocar de classe.** Código ↔ código + cópia literal não enfileira nada
  (o perfil da fila é o mesmo): só cria ou apaga as cópias e os blocos. O
  aviso da edição (`arvore.impacto`) mostra zero lotes.
- **Acesso.** A credencial de leitura do vault lê também o código-fonte
  copiado (com segredos mascarados). Limitar por token até onde cada
  credencial chega fica para depois (DV-609).

### 3.16 Templates e CLI `pv` (DV-607)

`pv add template docker:python` baixa a pasta `python/` do vault
`template-docker`. Detalhes e decisões em [cli.md](cli.md).

- **Vault de template**: o nome começa com `template-` (o prefixo fica
  travado no cadastro) e a árvore entra como `referencia` (cópia literal, sem
  LLM). Cada pasta de primeiro nível é um template; arquivo solto na raiz não é.
- **Pacote** (`petro_vault/templates.py`): sai do clone bare no commit
  processado. Entra o que alguma leitura aceita, com os filtros de caminho da
  ingestão: `.env`, chaves e certificados nunca saem; `.env.example` sai.
  Binário só sai com extensão do DV-601. `template.json` descreve o template e
  não vai para o projeto. O bit de executável é mantido.
- **Segredo bloqueia**: um texto em que a máscara da ingestão acharia algo
  (token, senha atribuída, chave privada, senha em URL) bloqueia o template
  inteiro (409, com o arquivo no erro). `${VAR}` não é segredo.
- **API**: `GET /v1/templates`, `/v1/templates/<tipo>/<nome>` e
  `/v1/templates/<tipo>/<nome>.zip`. Qualquer credencial `pv_` válida lê
  qualquer template. `GET /v1/cli/pv` serve a CLI, sem credencial;
  `GET /v1/cli` dá a versão.
- **CLI** (`cli/pv.py`): um arquivo, só biblioteca padrão. Não sobrescreve sem
  `--force` (arquivo igual ao do template não é conflito) e grava
  `.petrovault/templates.json` na pasta.
- **Docs na tela**: `/docs`, com o texto em `web/src/docs/*.md`. A v1 traz a
  CLI.

## 4. Ciclo do curador

**Em paralelo (DV-606, 03/11/2026).** Antes, um processo só curava um vault por vez, e um repositório grande segurava
todos os outros. Agora o `curador/ciclo.sh` roda o **coordenador** (`petro_vault/coordenador.py`):

- **Trabalhadores:** até `VAULT_TRABALHADORES` vaults ao mesmo tempo (padrão 3). Cada trabalhador é um processo
  `python -m petro_vault.rodada tag <tag>`, com pasta de lote e `HERMES_HOME` próprios (`/opt/curador/t<N>/`).
  - O mesmo vault nunca roda em dois trabalhadores, e a curadoria tem trava por vault (`estado/travas/<tag>.lock`).
  - A ingestão (fetch e fila) continua em série entre eles, sob `ingestao.lock`, porque é curta.
- **Ordem:** pull pedido (tela, API) primeiro; depois o vault que ficou com fila da vez anterior, se faz mais de 60 s
  que ele rodou; depois a agenda, com cada vault a cada `VAULT_INTERVALO` s. Por último, o vault que acabou de fazer a
  fatia dele: sem ninguém esperando, ele volta na hora.
- **Um vault, um trabalhador:** os lotes de um mesmo vault rodam em sequência. Eles mexem nas mesmas notas e no mesmo
  registro, e o pós-lote compara a pasta antes e depois de cada lote.
- **Fatia:** cada trabalhador faz até `VAULT_LOTES_POR_VEZ` lotes (padrão 3) e cede a vez. Um vault com fila grande
  não monopoliza.
- **Publicação em série,** quando um trabalhador termina: `base.py`, depois `publicar.sh sistemas/<tag>`. O commit
  leva **só as pastas dos vaults que terminaram** e a base, nunca uma nota pela metade de outro vault. Sem rebase:
  se o push for recusado, entra um merge.
- **Manutenção** (remoção de cadastro e lista do GitHub App): fica com o coordenador e não toca em vault que está
  rodando.
- **Histórico e tela:**
  - cada trabalhador grava a sua rodada e o seu lote (`rodada:t1`, `lote:t1`, coluna `rodadas.trabalhador`);
  - a tela mostra os vaults em curso ao mesmo tempo, e o `curador_estado.trabalhadores` diz quem está em qual vault;
  - ao subir, o coordenador fecha como interrompido o que ficou aberto; um trabalhador só fecha o que é dele.
- **SQLite em WAL**, para leitura não bloquear escrita. O DV-572 (PostgreSQL) resolve de vez.
- **`ciclo.sh uma-vez`** ainda roda a rodada antiga, sequencial, de todos os vaults.

Cada volta de um vault (e a rodada antiga) faz:

1. **Ingestão** (sem LLM): para cada sistema de repositório, fetch, diff,
   filtros e itens na fila.
2. **Achados** (sem LLM): os da API já estão na fila.
3. **Organizar** (LLM): por tag, lotes de até `VAULT_LOTE` itens (até
   `VAULT_LOTES_MAX` lotes por tag e rodada). O código monta um arquivo por
   item em `/opt/curador/lote/` (conteúdo filtrado e a nota a escrever); o
   curador cria ou funde notas e registra cada item (`item-<id>`) em
   `sistemas/<tag>/_meta/registro.md`. Perfil sem curador pronto: a fila
   aguarda. Falha (DV-584): o item não registrado volta para o fim da fila,
   e o lote dele cai pela metade a cada tentativa, até um item só; com
   `VAULT_TENTATIVAS_MAX` tentativas o item fica parado (continua na fila, o
   commit não avança, e a tela pede de novo). `VAULT_FALHAS_MAX` lotes com
   falha encerram a tag na rodada (teto de gasto).
4. **Pós-lote** (sem LLM): reescreve `sistema`, `origens`, `commit_origem` e
   datas; apaga notas vazias e as de origem removida; retira da fila só o que
   foi registrado. Lote interrompido (curador desligado no meio, DV-554): no
   começo da tag seguinte, a nota de código sem os campos do código tem as
   `fontes` que ainda são código promovidas a `origens`; sem nenhuma, sai, e
   os links para ela viram texto (aviso `nota_interrompida`). Item cujo
   arquivo de lote sumiu é refeito do clone; sem como refazer, fica parado.
   Erro numa tag não para as outras nem a verificação.
5. **Índices e verificador** por tag (sem LLM): `indices/` e
   `_meta/verificacao.md`.
6. **Índice de busca** (sem LLM).
7. **Publicar:** commit (autor `petro-vault-curador`, mensagem por tag) e push.

**Isolamento do LLM:** perfil por rodada (config, SOUL e plugin copiados do
repositório), só ferramentas de arquivo, sem fallback, memória do Hermes
desligada, token próprio (`VAULT_CLAUDE_CODE_OAUTH_TOKEN`, de `claude setup-token`),
um curador por vez (trava de arquivo).

## 5. MVP em tarefas

Uma tarefa por vez, cada uma com branch `DV-<n>-...` e PR neste repositório.

| # | Tarefa | Pronto quando (conferido na fonte) |
| --- | --- | --- |
| 1 (DV-287) | **Arquitetura e validação** (este documento) | Diretrizes validadas pelo Tiago; tarefas 2 a 7 criadas no DV-286 |
| 2 (DV-289) | **Esqueleto:** compose (`petro-vault-tiago`, porta 8670), `vault-init`, vault de conteúdo `petro-vault-conteudo-teste` com `_regras/`, `_templates/` e `sistemas/`, chave de deploy, API com credencial → tags e saúde | Credencial sem a tag recebe 403 (curl); `git log` do vault de teste mostra o commit inicial feito pelo serviço |
| 3 (DV-290) | **Cadastro e ingestão** (sem LLM): `POST /v1/sistemas` (tag, perfil, repo, ramo, filtros), clone, diff entre commits, filtros e segredos, fila, pull manual | Fila igual ao `git diff` real entre dois commits; arquivo com segredo não aparece em `lotes/` |
| 4 (DV-291) | **Curador, perfil documentos:** perfil Hermes, plugin por tag, SOUL, modelos, pós-lote, remoção, índices, verificador, publicar; repositório modelo com a estrutura padrão (3.7) | O petro-observer-vault (só leitura, numa tag de teste) vira notas; um arquivo removido numa cópia de teste some do vault e o verificador fica limpo; conferido no `git log` do vault de conteúdo |
| 5 (DV-292) | **Curador, perfil código** | Um repositório de código real (proposta: o petro-observer, só leitura, que conhecemos bem para conferir) gera regras, integrações e APIs com `origens`; nenhum trecho de segredo no vault |
| 6 (DV-293) | **Busca e escrita:** FTS5 por tag, HTTP e MCP só leitura, `POST achados` e status | Credencial da tag A não acha nada da tag B, mesmo pedindo; achado enviado aparece como nota e como `incorporado` |
| 7 (DV-294) | **Migração do Petro Observer** (lado do serviço): perfil `petro-observer`, importação do vault atual, upload de documentos | Notas atuais importadas sem reescrita, com `sistema: petro-observer`; verificador limpo. A troca no observer é ticket do DV-51 |

**Fora do MVP** (entrega final): GitHub App, entrada por MCP, atualização por
CI/CD, painel de gestão, busca semântica (DV-276), ligação entre sistemas.

## 6. A decidir

| Assunto | Proposta | Quem decide |
| --- | --- | --- |
| Painel de gestão | Fora do MVP; cadastro por API (curl) | Tiago |
| Várias origens por tag (código e documentação do mesmo sistema) | Aceita pelo Tiago em 15/10/2026; detalhes no comentário da DV-292 | Tiago, no início da tarefa 5 |
| Repositório de código para a tarefa 5 | petro-observer, só leitura (o de documentos já está decidido: petro-observer-vault) | Tiago, no início da tarefa 5 |
| Fichas de equipamento do observer (vêm do Zabbix, sem LLM) | Na migração, o observer envia nota pronta por um endpoint de "nota determinística", que não passa pelo LLM | Tiago, na tarefa 7 |
| Remoção pendente de documento (hoje o plugin do observer lê `_inbox/documentos/`) | API `GET .../documentos/remocoes-pendentes` para o plugin do observer | Tiago, na tarefa 7 |
| Modelo de embeddings | Em aberto no DV-276 | Tiago |
| Conflitos entre documentos | Em aberto desde o DV-63; segue como `_meta/conflitos.md` por tag | Tiago |
| Servidor de produção | Em aberto | Tiago |

## 7. Combinados de execução (14/10/2026)

- **Comandos com sudo** (acesso ao Docker, por exemplo): o Claude manda os
  comandos prontos, e o Tiago roda.
- **Token do curador:** quando a tarefa 4 precisar, o Claude avisa e diz onde
  colocar: `VAULT_CLAUDE_CODE_OAUTH_TOKEN` no `.env` do petro-vault no
  servidor de homologação (gerado com `claude setup-token`).
- **Petro Observer:** só leitura. Usar o petro-observer-vault ou o
  petro-observer como origem é só clone, com chave de deploy **só leitura**.
  Essa chave é registrada no DV-63 (vault) ou no DV-51 (código).
