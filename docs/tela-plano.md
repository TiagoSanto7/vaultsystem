# Plano da tela do petro-vault (fase 1)

- **Ticket:** DV-546 (épico DV-286). **Status:** proposta, para validação do Tiago.
- **Base:** `docs/tela.md` (seções 2, 5 e 8) e `docs/arquitetura.md`.
- **O que é:** a especificação das telas da fase 1 (o que cada uma mostra, o que
  se pode fazer, estados e navegação). Não há código nem visual final aqui: o
  visual é construído no repositório, a partir deste plano.
- **Fora deste plano:** fases 2 e 3 (só indicamos onde encaixam, seção 7) e
  tudo o que `tela.md` seção 6 deixa de fora (criar repositório pela tela,
  edição direta de nota, avisos por e-mail ou Teams).

## 1. Como ler

**Quem usa na fase 1:** só o **administrador** (Tiago), com login do AD. Os
agentes não usam a tela; usam a API com a credencial `pv_`.

**Termos:**

| Termo | Significa |
| --- | --- |
| Tag | O nome do sistema no vault; vira a pasta `sistemas/<tag>/`. |
| Origem | Um repositório e ramo de onde o sistema lê (a primeira se chama `principal`). |
| Leitura | O que se lê de uma origem: perfil (`documentos`, `codigo` ou próprio) e filtros `incluir` e `excluir`. |
| Commit processado / pendente | O último commit da origem que o curador já registrou / o que está na origem e ainda não foi processado. |
| Pull | Pedido (manual ou da rodada automática) para trazer os commits novos e enchê-los na fila. |
| Rodada | Um ciclo do curador (a cada 15 min por padrão, e também a cada pull manual). Tem lotes; cada lote é de uma tag e um perfil. |

**Convenções de todas as telas:**

- A tela é uma **tela de confiança** (`tela.md` seção 2): tudo que aparece leva
  à **origem** (arquivo no GitHub, no commit certo); tudo que ficou de fora
  tem o **motivo**; toda rodada do curador tem **resultado**.
- O estado vem escrito em texto, nunca só por cor ou ícone.
- Conteúdo de arquivo ignorado por segredo **nunca** aparece: só o caminho e o
  motivo. Chave de credencial só aparece uma vez, na criação.
- Os dados se atualizam sozinhos (o curador atende pedidos em até 30 s) e há
  sempre um botão **Atualizar**. Uma falha ao atualizar não apaga o que já
  estava na tela: mostra uma faixa "Não foi possível atualizar" com **Tentar de
  novo**.

## 2. Sinais de confiança e estados (a base de tudo)

### 2.1 Os sinais

Aparecem **na lista de sistemas e no topo de cada sistema**, sempre na mesma
ordem de importância.

| # | Sinal | Pergunta | Valores | Clicar leva a |
| --- | --- | --- | --- | --- |
| 1 | **Em dia / atrasado** | O vault reflete o último commit da origem? | Em dia; Atrasado (n commits pendentes); Nunca processado; Sem acesso ao repositório; Não se aplica (sistema por achados de API) | Sistema › Visão geral |
| 2 | **Fila** | Tem coisa esperando o curador? | Número de itens (0 = vazia) | Sistema › Ingestão (fila) |
| 3 | **Verificação** | Tem problema nas notas? | Limpa; n problemas (por tipo: link quebrado, origem que sumiu, possível segredo) | Sistema › Verificação |
| 4 | **Ignorados** | O que da origem ficou de fora, e por quê? | Número no último pull, com os motivos mais comuns | Sistema › Ingestão (ignorados) |
| 5 | **Pedidos abertos** | Tem correção pedida e ainda não feita? | Fase 3. Não aparece na fase 1; o lugar fica reservado. | — |

Em sistemas com mais de uma origem, o sinal 1 mostra o **pior caso** (basta uma
origem atrasada ou sem acesso) e a Visão geral detalha por origem.

### 2.2 Os cinco estados

Todo sistema, e cada tela, usa os mesmos cinco estados. A lista de sistemas e
o topo de cada sistema mostram **um selo geral**, escolhido por esta
precedência (o primeiro que valer):

| Precedência | Estado | Quando | Texto do selo |
| --- | --- | --- | --- |
| 1 | **Erro de acesso ao repositório** | O curador não consegue ler uma origem (chave de deploy ausente, errada ou revogada; repositório não encontrado) | "Sem acesso ao repositório" + nome da origem |
| 2 | **Com problema** | Verificação com problemas; ou último pull com erro; ou lote do curador com erro; ou vault atrasado sem fila andando | "Com problema" + o motivo em palavras |
| 3 | **Processando** | Pull pedido ou fila andando ou rodada em curso | "Processando" + o que falta |
| 4 | **Em dia** | Commit processado = último da origem; fila vazia; verificação limpa; último pull sem erro | "Em dia" + quando foi a última rodada |
| 5 | **Vazio** | Sistema cadastrado que ainda não teve pull | "Aguardando o primeiro pull" |

Além desses, dois estados que não são do sistema, mas de cada tela:

- **Carregando:** a tela está buscando dados da API (mostra a estrutura da
  tela com o conteúdo "em branco", sem números inventados).
- **Remoção pedida:** o sistema foi mandado remover; a tela fica só de leitura
  com a faixa "Removendo: o curador apaga a pasta da tag, o clone, os lotes e
  o cadastro em até 30 s" até o sistema sumir da lista.

## 3. Mapa de navegação

```
Entrar ──▶ Sistemas ──▶ Cadastrar sistema ──▶ Sistema (Visão geral)
              │  ▲                                  ▲
              │  └──── topo "Sistemas" ─────────────┤
              └───────────────▶ Sistema ────────────┘
                              ├─ Visão geral
                              ├─ Ingestão   (fila · pulls · ignorados)
                              ├─ Curadoria  (rodadas · lotes · avisos)
                              ├─ Verificação
                              ├─ Notas      (árvore · leitura da nota)
                              └─ Credenciais
```

**Barra superior (em todas as telas, menos Entrar):** nome do serviço e
ambiente (ex.: "homologação"); link **Sistemas**; usuário e **Sair**.

**Cada aba do sistema tem endereço próprio** (abrir direto na Curadoria, por
exemplo, e a tecla Voltar do navegador funcionar). Um pull aberto na Ingestão e
uma nota aberta em Notas também têm endereço, para poderem ser enviados a
alguém.

**Topo comum de um sistema (acima das abas):**

1. Tag e selo geral (seção 2.2).
2. Os sinais 1 a 4 (seção 2.1), clicáveis.
3. Origens em uma linha (ex.: "2 origens: documentos, código").
4. Última rodada: quando e resultado.
5. Ação principal: **Pedir pull**.
6. As abas, cada uma com um ponto de atenção quando há o que ver (fila > 0 na
   Ingestão, problemas na Verificação, erro na última rodada na Curadoria).

## 4. As telas

### 4.1 Entrar

**1. Objetivo e quem usa**
Dar entrada ao administrador com o login da empresa (AD), no mesmo esquema do
painel do Petro Observer. Na fase 1, só o administrador usa a tela.

**2. O que mostra**
- Nome do serviço e ambiente.
- Campos de usuário e senha do AD.
- Mensagem de erro, quando houver.
- Aviso curto: "Agentes não entram aqui: usam a API com credencial `pv_`."

**3. Ações**
- **Entrar:** valida no AD. Certo: vai para a página que a pessoa tentou abrir
  ou, se não houve, para **Sistemas**. Errado: mostra "Usuário ou senha
  inválidos", sem dizer qual dos dois.
- **Sair** (nas outras telas): encerra a sessão e volta para Entrar.
- Sessão que expira: volta para Entrar com "Sua sessão expirou" e, depois de
  entrar, retorna à página em que a pessoa estava.

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Formulário limpo. |
| Processando | Botão desabilitado ("Entrando…"). |
| Em dia | Não se aplica: quem entra sai da tela. |
| Com problema | Usuário ou senha inválidos. Usuário do AD sem permissão de administrador: "Sem acesso a esta ferramenta", sem listar nada (proposta para a fase 1; a fase 2 muda isso). |
| Erro de acesso | O AD não respondeu: "Não foi possível falar com o AD agora", separado de "senha errada". (Erro de acesso a repositório não se aplica aqui.) |

**5. Navegação**
De: qualquer endereço sem sessão válida; **Sair**; sessão expirada.
Para: **Sistemas** (ou a página que a pessoa tentou abrir).

### 4.2 Sistemas

**1. Objetivo e quem usa**
Ver de relance quais sistemas estão no vault, **se dá para confiar neles** e o
que precisa de atenção, e ter a porta para cadastrar um novo. Usa o
administrador.

**2. O que mostra** (em ordem de importância)

*Em cada linha (um sistema):*
1. Tag.
2. Selo geral (seção 2.2), com o motivo em palavras quando não é "Em dia".
3. Sinal **Em dia / atrasado**, com o número de commits pendentes.
4. Sinal **Fila** (itens).
5. Sinal **Verificação** (limpa ou n problemas).
6. Sinal **Ignorados** (n no último pull).
7. Origens: repositórios e ramo, e as leituras de cada um em forma curta
   (ex.: `PetrovinaS/petro-observer-vault · main · documentos`). Sistema por
   achados de API mostra "achados pela API", e o sinal Em dia mostra "não se
   aplica".
8. Última rodada: quando e resultado.

*Acima da lista:* contagem de sistemas por estado (com problema, processando,
em dia, vazio), que funciona como filtro; busca por tag; ordem padrão com os
sistemas que pedem atenção primeiro (erro de acesso, com problema, processando,
vazio, em dia). *Se a API informar:* quando é a próxima rodada do curador.

**3. Ações**
- **Cadastrar sistema:** leva à tela de cadastro.
- **Abrir um sistema:** clicar na linha leva à Visão geral dele.
- **Clicar num sinal:** leva direto à aba do sistema que explica aquele sinal
  (tabela da seção 2.1).
- **Filtrar** por estado e **buscar** por tag.
- **Atualizar** (e atualização automática).
- Não há "Pedir pull" na lista, de propósito: o pull se pede dentro do
  sistema, para não disparar um pedido no sistema errado.

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Nenhum sistema cadastrado: mensagem "Nenhum sistema no vault ainda" com **Cadastrar sistema** em destaque e uma linha dizendo o que é preciso ter à mão (repositório e chave de acesso). |
| Carregando | A lista aparece com linhas "em branco", sem números. |
| Processando | Linha com selo "Processando" e quantos itens faltam; some quando a fila zera. |
| Em dia | Linha "Tudo em dia" no topo quando todos estão em dia; cada linha com seu selo. |
| Com problema | Linhas no topo da lista, com o motivo escrito ("Verificação: 3 problemas", "Último pull com erro", "Atrasado: 4 commits"). |
| Erro de acesso | Linha com "Sem acesso ao repositório" e a origem; clicar leva à Visão geral do sistema, onde está o que fazer. A falha da própria lista (API fora) é outra coisa: faixa com **Tentar de novo**, mantendo o que já estava na tela. |
| Remoção pedida | Linha com "Removendo" e sem ações, até sumir. |

**5. Navegação**
De: Entrar; **Sistemas** na barra superior de qualquer tela; após cadastrar
com cancelamento; após remover um sistema.
Para: **Sistema** (Visão geral, ou a aba do sinal clicado); **Cadastrar
sistema**.

### 4.3 Sistema

O sistema tem o **topo comum** (seção 3) e seis abas. Os cinco estados da
seção 2.2 valem para o topo; cada aba os detalha abaixo.

#### 4.3.1 Aba Visão geral

**1. Objetivo e quem usa**
Responder "este sistema está bem e de onde ele vem?". Usa o administrador.

**2. O que mostra** (em ordem de importância)
1. **Explicação dos sinais:** cada sinal do topo com uma frase do que significa
   agora (ex.: "Atrasado: o vault está 4 commits atrás da origem").
2. **Origens**, uma por bloco:
   - nome da origem, repositório (com link para o GitHub) e ramo;
   - leituras: perfil, `incluir` e `excluir`;
   - **commit processado** e **commit pendente** (hash curto com link para o
     commit no GitHub, data e quantos commits de diferença);
   - **acesso ao repositório:** "Lendo normalmente" ou "Sem acesso", com o
     momento da última tentativa.
3. **Último pull:** número, quando, quem pediu (ou "rodada automática"),
   resultado, com link para o detalhe na Ingestão.
4. **Última rodada do curador:** quando, resultado, com link para a Curadoria.
5. **Cadastro:** cadastrado por quem e quando.
6. **Remover sistema** (zona separada, no fim da página).

**3. Ações**
- **Pedir pull:** pede um pull do sistema (da tag, cobrindo todas as origens).
  A tela mostra "Pull #n pedido; o curador atende em até 30 s" e acompanha até
  o resultado. Enquanto um pull está em andamento, o botão fica desabilitado
  e diz qual é.
- **Abrir no GitHub:** repositório e commits (abre em outra aba).
- **Clicar num sinal ou no último pull/rodada:** leva à aba correspondente.
- **Remover sistema:** pede confirmação (digitar a tag). Explica o efeito: em
  até 30 s o curador apaga a pasta da tag no vault (com commit), o clone, os
  lotes e o cadastro; a origem não é tocada; a chave de deploy, no servidor e
  no GitHub, **é apagada à mão** (a tela lembra disso). Depois volta para
  **Sistemas**.

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Sistema sem pull: "Ainda não foi processado". **Pedir primeiro pull** em destaque; commit processado aparece como "—". Se o acesso ao repositório nunca foi testado, lembra de conferir a chave de deploy. |
| Carregando | Blocos de origem "em branco". |
| Processando | "Pull #n pedido" (atende em até 30 s), depois a contagem da fila diminuindo; atualiza sozinha. |
| Em dia | Commit processado igual ao pendente; selo "Em dia" com a data da última rodada. |
| Com problema | Bloco de aviso no topo da página com o motivo (atrasado, verificação, pull ou lote com erro) e o link para a aba que detalha. |
| Erro de acesso | No bloco da origem afetada: "O curador não conseguiu ler `<repositório>`", o horário e a instrução (conferir a chave de deploy só leitura registrada no repositório e entregue ao curador), com link para a instrução da chave. O último commit processado continua visível; **Pedir pull** continua habilitado, para tentar de novo. |
| Remoção pedida | Página só de leitura com a faixa de remoção (seção 2.2). |

**5. Navegação**
De: **Sistemas** (linha ou sinal); **Cadastrar sistema** (ao concluir); as
outras abas (por links de sinais).
Para: as outras abas; GitHub (outra aba); **Sistemas**.

#### 4.3.2 Aba Ingestão

**1. Objetivo e quem usa**
Entender **o que entrou, o que está esperando e o que ficou de fora e por
quê**. Usa o administrador.

**2. O que mostra** (em ordem de importância)
1. **Fila atual:** número de itens e, por item: caminho (com link para o
   arquivo no GitHub), tipo (adicionado, modificado, removido), origem,
   leitura/perfil, commit e há quanto tempo está esperando. Itens esperando
   há várias rodadas ganham o selo "parado".
2. **Histórico de pulls** (mais recente primeiro): número, quando, quem pediu
   (ou "rodada automática"), origem, intervalo de commits, resultado
   (pedido, concluído, com erro), commits, itens e ignorados.
3. **Detalhe de um pull** (ao abrir): commits; itens que foram para a fila;
   **ignorados agrupados por motivo**, cada um com caminho e contagem.
   Motivos:
   - segredo (arquivo com chave privada fica fora; linha com cara de token é
     mascarada, e a tela diz quantas linhas foram mascaradas);
   - binário;
   - acima do limite de tamanho;
   - filtro do cadastro (`incluir` ou `excluir`);
   - `vendor/`, `node_modules/` e lockfiles;
   - "deixou de passar no filtro" (virou item *removido* para o curador tirar
     o que veio dele).

**3. Ações**
- **Pedir pull** (mesmo comportamento da Visão geral).
- **Abrir um pull** para ver o detalhe; voltar ao histórico.
- **Filtrar** a fila por tipo e por origem; **filtrar** os ignorados por
  motivo.
- **Abrir o arquivo no GitHub** (no commit certo) e **copiar o caminho**.
- Não há ação para "forçar" a entrada de um ignorado: o ajuste é no filtro do
  cadastro (ver pergunta 1 da seção 6).

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Nunca houve pull: "Nenhum pull ainda" com **Pedir pull**. Fila vazia com pulls feitos: "Nada esperando o curador" (é um bom sinal e se diz isso). |
| Carregando | Fila e histórico "em branco". |
| Processando | Pull "pedido" no topo do histórico; a fila enche e depois diminui conforme o curador registra os itens; atualiza sozinha. |
| Em dia | Fila vazia e último pull concluído sem erro. |
| Com problema | Pull com erro: a mensagem do erro e o intervalo de commits afetado. Itens que o curador não registrou voltam à fila na rodada seguinte e ficam sinalizados. Item "parado". |
| Erro de acesso | Pull que falhou por não conseguir ler o repositório: "Sem acesso a `<repositório>`", sem itens, com o link para a instrução da chave de deploy. |

**5. Navegação**
De: abas do sistema; sinais **Fila** e **Ignorados** (Sistemas e topo); Visão
geral (último pull).
Para: Curadoria (item que já foi registrado); Notas (nota gerada por um item
concluído); GitHub (arquivo e commit); Visão geral.

#### 4.3.3 Aba Curadoria

**1. Objetivo e quem usa**
Ver **o que o curador fez e o que deixou de fazer**: quando rodou, quanto
tempo levou, o que registrou e o que travou. Usa o administrador.

**2. O que mostra** (em ordem de importância)
1. **Último problema**, se houver: lote com erro, itens não registrados, rodada
   que travou, com a causa como o curador registrou.
2. **Última rodada:** início, duração, resultado, lotes, itens registrados e
   não registrados.
3. **Avisos do código:** fonte inventada descartada; nota não ligada ao item
   que mudou mesmo assim. Cada aviso cita a nota ou o arquivo e leva a ele.
4. **Histórico de rodadas** (mais recente primeiro). Ao abrir uma, os lotes: perfil,
   itens, registrados, tempo, erro.
5. **Registro do curador** do sistema (o que fez em cada item).
6. **Conflitos entre documentos**, como o curador os anotou (o assunto ainda
   está em aberto na arquitetura).

Quando o perfil de uma leitura ainda não tem curador pronto, a aba diz "A fila
aguarda: este perfil ainda não tem curador" (hoje isso vale só para perfis
próprios que ainda não existem).

**3. Ações**
- **Abrir uma rodada ou um lote** para ver o detalhe.
- **Abrir a nota** citada num aviso ou no registro (vai para Notas).
- **Abrir o item** (vai para a Ingestão).
- **Filtrar** por "só com erro" e "só com aviso".
- **Pedir pull** (no topo): a rodada acontece a cada 15 min e a cada pull; não
  há "rodar o curador agora" separado.
- Não há "refazer a nota" na fase 1 (isso é fase 3).

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | "O curador ainda não passou por este sistema", com **Pedir pull** se ainda não houve nenhum. |
| Carregando | Lista de rodadas "em branco". |
| Processando | Rodada em curso no topo: lote atual e quantos itens já foram registrados; atualiza sozinha. |
| Em dia | Última rodada concluída, sem erro nem aviso, fila vazia. |
| Com problema | Lote com erro, itens não registrados ou avisos do código, com o resumo no topo e os detalhes abaixo. |
| Erro de acesso | Quando a ingestão da rodada falhou por falta de acesso ao repositório, a rodada mostra "Ingestão sem acesso a `<repositório>`" com link para a Visão geral. |

**5. Navegação**
De: abas do sistema; topo (última rodada); Ingestão (item já registrado).
Para: Notas (nota afetada); Ingestão (item); Visão geral.

#### 4.3.4 Aba Verificação

**1. Objetivo e quem usa**
Saber se **há problema nas notas do sistema** e chegar à nota e à origem de cada
um. Usa o administrador.

**2. O que mostra** (em ordem de importância)
1. **Resumo:** "Limpa" ou "n problemas", com a divisão por tipo, o commit a que
   o resultado se refere e quando a verificação rodou (no fim da última
   rodada).
2. **Lista de problemas, agrupada por tipo**, com possível segredo primeiro:
   - **possível segredo:** nota e o padrão encontrado, com o trecho
     **mascarado** (nunca o valor);
   - **origem que sumiu:** nota cuja origem aponta para um arquivo que não
     existe no commit processado;
   - **link quebrado:** nota e o link;
   - outros tipos que o verificador passar a registrar.
3. Em cada problema: a nota (com link), o detalhe e desde quando existe.

**3. Ações**
- **Abrir a nota** (vai para Notas).
- **Abrir a origem no GitHub** (nos problemas de origem que sumiu).
- **Filtrar** por tipo.
- **Pedir pull** (no topo). A verificação roda no fim de cada rodada; a tela
  não tem "verificar agora".
- Na fase 1 não há "dispensar problema".

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Nunca foi verificado (sistema sem rodada): "Ainda não foi verificado", com **Pedir pull**. |
| Carregando | Resumo e lista "em branco". |
| Processando | Mostra o resultado anterior com a faixa "Rodada em curso: o resultado será atualizado". |
| Em dia | "Limpa: nenhum problema no commit `<hash>`", com a data. |
| Com problema | Lista por tipo, com o total no topo e no sinal. |
| Erro de acesso | O resultado mostrado é o do último commit processado, com a faixa "O vault está atrasado: sem acesso a `<repositório>`" e link para a Visão geral. Se o próprio resultado não puder ser lido: "Não foi possível ler o resultado da verificação" com **Tentar de novo**. |

**5. Navegação**
De: abas do sistema; sinal **Verificação** (Sistemas e topo).
Para: Notas (a nota com problema); GitHub; Visão geral.

#### 4.3.5 Aba Notas

**1. Objetivo e quem usa**
Navegar o conhecimento do sistema e **conferir a origem de cada nota**. Usa o
administrador.

**2. O que mostra** (em ordem de importância)
1. **Árvore por pasta**, com a contagem por pasta, conforme o perfil:
   - documentos: `documentos`, `assuntos`;
   - código: `módulos`, `regras`, `integrações`, `APIs`, `dados`;
   - perfil próprio: as pastas do perfil;
   - mais as `índices` (geradas pelo código). A pasta `_meta` não aparece: o
     registro e a verificação têm abas próprias.
2. **A nota aberta:**
   - título e tipo de nota;
   - texto, com os links entre notas navegáveis e o link quebrado em destaque;
   - cabeçalho: sistema, tipo de nota, criada em, atualizada em, commit de
     origem;
   - **origens:** cada caminho com link para o arquivo no GitHub, no commit de
     origem da nota (origem que não é a `principal` aparece como
     `<origem>:<caminho>`, deixando claro de qual repositório é);
   - problemas da verificação **desta nota**, se houver.
3. Aviso quando há itens esperando o curador que podem mudar a nota.

**3. Ações**
- **Abrir pasta ou nota**, **seguir um link** entre notas, voltar.
- **Abrir a origem no GitHub** e **copiar o caminho** da nota no vault.
- **Filtrar a árvore** por nome (a busca de texto completo é fase 3).
- Não há editar nem apagar nota (a próxima rodada reescreveria; correção de
  fato é no repositório de origem).

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Ainda não há notas: "O curador cria as notas depois do primeiro pull", com a fila ("n itens esperando") quando já há. |
| Carregando | Árvore e nota "em branco". |
| Processando | Faixa "Rodada em curso: as notas podem mudar"; as notas continuam legíveis. |
| Em dia | Árvore completa, notas sem selo de problema. |
| Com problema | Notas com problema ganham selo na árvore e o detalhe na própria nota (link para a Verificação). Nota não encontrada (apagada na última rodada): "Esta nota não existe mais", com volta à pasta. |
| Erro de acesso | As notas continuam legíveis (estão no vault), com a faixa "O vault pode estar desatualizado: sem acesso a `<repositório>`". Links para o GitHub avisam que só abrem para quem tem acesso ao repositório. |

**5. Navegação**
De: abas do sistema; Verificação (nota com problema); Curadoria (nota afetada);
Ingestão (item concluído).
Para: outra nota (links); GitHub (origem); Verificação (problemas da nota);
Curadoria (registro do item).

#### 4.3.6 Aba Credenciais

**1. Objetivo e quem usa**
Dar e tirar **acesso de agentes** (credencial `pv_`) a este sistema. Na fase 1
usa o administrador; na fase 2, o dono.

**2. O que mostra** (em ordem de importância)
1. **Lista das credenciais que leem ou escrevem esta tag:** nome, tags que
   lê, tags que escreve (todas, não só esta, porque uma credencial pode
   alcançar outros sistemas), quem criou e quando, e o estado (ativa ou
   revogada). A chave **nunca** é mostrada: só se guarda o hash.
2. **Criar credencial:** nome, tags de leitura, tags de escrita (esta tag
   já marcada).
3. **Como usar** (aparece na criação): endereço da API e o cabeçalho de
   autorização.

**3. Ações**
- **Criar credencial:** abre o formulário; ao confirmar, mostra a **chave uma
  única vez**, com **Copiar** e a confirmação "Copiei a chave", sem a qual o
  aviso não fecha. Depois disso só se vê o nome.
- **Revogar:** pede confirmação mostrando quantas tags a credencial alcança e
  avisando que o agente que a usa passa a receber 401. O efeito é imediato.
- Não há "editar tags" na fase 1: revoga e cria outra (ver pergunta 3 da
  seção 6).

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | "Nenhum agente com acesso a este sistema", com **Criar credencial**. |
| Carregando | Lista "em branco". |
| Processando | Criando ou revogando: botão desabilitado. |
| Em dia | Lista de credenciais ativas. |
| Com problema | Falha ao criar (nome já usado, tag que não existe) com a mensagem no campo; falha ao revogar com **Tentar de novo**. |
| Erro de acesso | Não se aplica: as credenciais não dependem do acesso ao repositório. Esta aba não muda com o estado de acesso. |

**5. Navegação**
De: abas do sistema. Para: outras abas; Sistemas.

### 4.4 Cadastrar sistema

**1. Objetivo e quem usa**
Colocar um sistema no vault **sem terminal**: escolher a tag, dizer de onde ele
vem (origens e leituras) e orientar a chave de acesso ao repositório. Na fase 1
só o administrador cadastra (proposta da pergunta 2 de `tela.md`); o cadastro
pelo dono entra com a fase 2.

**2. O que mostra** (em ordem de preenchimento)
1. **Tag:** com a regra ao lado (minúsculas, números e hífen; vira a pasta
   `sistemas/<tag>/`).
2. **Origens** (pelo menos uma; a primeira se chama `principal`). Em cada uma:
   - repositório (ex.: `git@github.com:Org/repo.git`) e ramo (padrão `main`);
   - **leituras** da origem (pelo menos uma): perfil (`documentos`, `codigo` ou
     próprio), `incluir` e `excluir` (um padrão por linha; vazio em `incluir`
     é tudo; padrão sem barra casa com o nome do arquivo e com barra, com o
     caminho). Uma dica para repositório de documentos na estrutura padrão:
     `incluir: docs/*`, `excluir: docs/README.md`.
3. **Chave de acesso**, por origem: o passo a passo com os comandos já
   preenchidos com a tag e o repositório (gerar a chave só leitura com o nome
   da tag, registrá-la como *deploy key* **sem escrita** no repositório e
   entregá-la ao curador), e a caixa "Já fiz isso". Na fase 1 isso é feito pelo
   administrador no servidor; a tela não cria a chave.
4. **Resumo** do que será cadastrado, antes de confirmar.

**3. Ações**
- **Adicionar origem** e **remover origem** do formulário; **adicionar leitura**
  a uma origem.
- **Copiar os comandos** da chave.
- **Cadastrar:** valida os campos; tag já usada é recusada ("A tag já está
  cadastrada"). Sem a caixa "Já fiz isso", cadastra mesmo assim, mas avisa que
  o primeiro pull vai registrar erro de acesso. Ao concluir, abre o **Sistema
  › Visão geral**, no estado Vazio.
- **Cadastrar e pedir o primeiro pull:** o mesmo, e já pede o pull.
- **Cancelar:** volta para **Sistemas**, sem guardar nada.

**4. Estados**

| Estado | O que a tela faz |
| --- | --- |
| Vazio | Formulário em branco, com uma origem (`principal`, ramo `main`) e uma leitura prontas para preencher. |
| Carregando | Não há (o formulário é local); só o envio. |
| Processando | Enviando: campos e botões desabilitados. |
| Em dia | "Sistema cadastrado": leva à Visão geral do sistema. |
| Com problema | Erros por campo: tag inválida ou já usada; repositório fora do formato; padrão inválido; leitura sem perfil. Falta de permissão para escrever na tag: mensagem no topo. Falha da API: faixa com **Tentar de novo**, sem perder o que foi digitado. |
| Erro de acesso | Não aparece aqui: é descoberto no primeiro pull e aparece na Visão geral e na Ingestão do sistema, com o link de volta para esta instrução da chave. |

**5. Navegação**
De: **Cadastrar sistema** em Sistemas (e o botão do estado Vazio dessa tela).
Para: **Sistema › Visão geral** (ao cadastrar); **Sistemas** (cancelar).

## 5. Matriz de estados (consulta rápida)

| Tela / aba | Vazio | Processando | Em dia | Com problema | Erro de acesso |
| --- | --- | --- | --- | --- | --- |
| Entrar | formulário limpo | "Entrando…" | — | usuário ou senha inválidos; sem permissão | AD não respondeu |
| Sistemas | nenhum sistema | selo "Processando" na linha | "Tudo em dia" | linhas no topo com o motivo | linha "Sem acesso ao repositório" |
| Visão geral | sem pull ainda | pull pedido, fila andando | commits iguais | aviso no topo com o motivo | bloco da origem com a instrução |
| Ingestão | nenhum pull | fila e pull em andamento | fila vazia, pull concluído | pull com erro; item parado | pull sem acesso ao repositório |
| Curadoria | curador não passou | rodada em curso | rodada ok, sem aviso | lote com erro, avisos | ingestão sem acesso |
| Verificação | nunca verificada | resultado anterior + faixa | "Limpa" | lista por tipo | resultado do commit atrasado |
| Notas | sem notas ainda | "as notas podem mudar" | árvore sem selos | notas com selo de problema | notas legíveis + faixa de atraso |
| Credenciais | nenhuma credencial | criando ou revogando | lista ativa | falha ao criar ou revogar | não se aplica |
| Cadastrar | formulário em branco | enviando | cadastrado | erros por campo | descoberto no primeiro pull |

## 6. Pontos para decidir

Coisas que o plano deixou como proposta porque `tela.md` e a API ainda não
respondem:

1. **Editar o cadastro.** A API só cria e remove (não há edição). Mudar `incluir`
   e `excluir` ou o ramo hoje exige remover e cadastrar de novo, o que apaga as
   notas. Proposta: pedir à API uma edição de origens e leituras antes da
   tela; sem isso, a tela só mostra o cadastro. **Feito na DV-554** (27/10/2026):
   Fontes > Editar ramo e leituras / Remover origem, com reconciliação na ingestão.
2. **Pull por tag ou por origem.** Hoje o pull é da tag. Para sistemas com várias
   origens, a tela só mostra o resultado por origem; pedir pull de uma só
   origem ficaria para depois.
3. **Editar tags de uma credencial.** Proposta: não na fase 1 (revogar e criar
   outra).
4. **Usuário do AD sem permissão** (entrar, mas não ser administrador).
   Proposta: bloquear com mensagem até a fase 2.
5. **Cadastro com várias origens** (DV-292): o README ainda mostra o cadastro com
   um repositório e um perfil; a tela precisa que a API de cadastro aceite
   origens e leituras. Conferir antes de construir.
6. **Pergunta 1 de `tela.md` (visual):** tema do painel do Petro Observer (HMI,
   DV-311) ou um visual próprio. O plano não depende da resposta; vale para
   qualquer visual que o estado e a origem sejam o que se vê primeiro.
7. **Perguntas 2 e 3 de `tela.md`** continuam como estão (só o administrador
   cadastra; endereço próprio em homologação).

**O que cada tela espera da API** (resumo da lista de `tela.md` seção 5):

| Tela | Depende de |
| --- | --- |
| Todas | Tela aberta na rede interna; login do AD e sessão |
| Sistemas | Listar sistemas, com os sinais de confiança |
| Visão geral, Ingestão | Estado do sistema, commits processado e pendente, pulls (já existem em parte) |
| Curadoria | Histórico das rodadas e dos lotes do curador (hoje só no log do contêiner) |
| Verificação, Notas | Ler as notas de um sistema e o resultado da verificação |
| Credenciais | Criar, listar e revogar credenciais pela API |
| Cadastrar | Cadastro com várias origens e leituras (ponto 5 acima) |

## 7. Onde as fases 2 e 3 encaixam (fora deste plano)

| Fase | O que entra | Onde encaixa |
| --- | --- | --- |
| 2 | Qualquer pessoa do AD entra e vê só os sistemas em que tem papel | **Sistemas** passa a filtrar pelo papel; **Entrar** deixa de bloquear quem não é administrador |
| 2 | Dono, editor e leitor; o dono convida pessoas | Nova seção em **Credenciais** (ou aba "Pessoas") para papéis; o topo do sistema mostra o papel de quem está vendo |
| 2 | Cadastro pelo dono, com o GitHub App | **Cadastrar sistema**: o passo "Chave de acesso" vira "Conferência do GitHub App" (a tela confere se o app enxerga o repositório); **erro de acesso** ganha a causa "o app não enxerga este repositório" |
| 3 | Comentar numa nota e mandar o curador refazer | **Notas**: painel de comentário na nota e antes/depois da nota; o pedido aparece na fila |
| 3 | Sinal **Pedidos abertos** | Ocupa o lugar reservado na lista, no topo do sistema e na seção 2.1; os pedidos (na fila, feito, recusado com motivo) aparecem na **Curadoria** |
| 3 | Busca de texto completo, só nos sistemas que a pessoa lê | Campo de busca na barra superior de **Sistemas** e dentro de **Notas** (hoje só filtra a árvore) |
| depois | Relações entre notas, documentos e sistemas (links e `relacionados`) | **Notas**: "quem aponta para esta nota" e visão em grafo. Fora das fases de `tela.md`; é uma sugestão para a conversa |
