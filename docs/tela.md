# Tela do petro-vault: planejamento

- **Ticket:** DV-546 (épico DV-286). **Status:** aprovado pelo Tiago em 22/10/2026.
- **Para que serve este documento:** combinar o que a tela é antes de construir;
  base dos tickets de construção e briefing para o Claude Design.
- **Quem faz o quê:** o Claude Design entrega o **plano** (especificação das
  telas: o que cada uma mostra, estados, navegação). O **visual é construído
  aqui**, no repositório do petro-vault, a partir desse plano.

## 1. Objetivo

Quem cuida de um sistema consegue **colocar o sistema no vault, ver se ele foi
bem entendido e confiar no que está lá**, sem depender de alguém no terminal.

## 2. Significado: uma tela de confiança

O vault só vale se quem consulta acredita nele. Por isso a tela não mostra só
"o que tem": mostra **de onde veio cada coisa, o que ficou de fora e por quê, e
o que o curador fez ou deixou de fazer**. Toda nota leva ao arquivo de origem
no GitHub; todo arquivo ignorado tem o motivo; toda rodada do curador tem
resultado.

Sinais de confiança de um sistema (aparecem na lista e no topo do sistema):

| Sinal | Pergunta que responde |
| --- | --- |
| Em dia / atrasado | O vault reflete o último commit da origem? |
| Fila | Tem coisa esperando o curador? |
| Verificação | Tem problema (link quebrado, origem que sumiu, possível segredo)? |
| Ignorados | O que da origem ficou de fora, e por quê? |
| Pedidos abertos | Tem correção pedida e ainda não feita? (fase 3) |

## 3. Quem usa

| Quem | Como entra | O que faz |
| --- | --- | --- |
| **Administrador** (Tiago) | Login do AD | Tudo, em todos os sistemas |
| **Dono de um sistema** | Login do AD | Cadastra e gerencia o sistema, dá permissão a outras pessoas, cria credenciais de agentes (fase 2) |
| **Editor** | Login do AD | Pede pull, comenta e manda refazer (fase 2 e 3) |
| **Leitor** | Login do AD | Vê o sistema e as notas, comenta (fase 2 e 3) |
| **Agentes** (ex.: Petro Observer) | Credencial `pv_` | Não usam a tela; usam a API |

São **duas portas diferentes**: pessoas entram pela tela com o login da empresa
(AD); agentes entram pela API com a credencial `pv_`, presa às tags que podem
ler e escrever.

## 4. Início, meio e fim

**Início: colocar um sistema**
1. Escolher a tag (o nome do sistema no vault).
2. Dizer de onde vem: repositório(s) e, em cada um, o que é documentação e o
   que é código (as "leituras").
3. Liberar a leitura do repositório (hoje, chave de deploy pelo administrador;
   depois, o GitHub App).
4. Pedir o primeiro pull.

**Meio: acompanhar**
- A fila andando; o que entrou e o que ficou de fora, com o motivo.
- Cada rodada do curador: quando, quanto tempo, quantos itens, o que ficou
  registrado e o que travou.
- A verificação: problemas por nota.

**Fim: usar e confiar**
- Navegar o conhecimento do sistema; cada nota com a origem (link para o
  arquivo no commit certo).
- Entregar uma credencial a um agente, que passa a consultar o vault.
- (Fase 3) Corrigir: comentar numa nota e mandar o curador refazer; buscar.

## 5. Fases

Cada fase é usável sozinha.

### Fase 1: ver e operar o básico (administrador)

**Telas**
1. **Entrar:** login do AD (mesmo esquema do painel do Petro Observer).
2. **Sistemas:** lista com tag, origens, sinais de confiança (seção 2), última
   rodada. Botão "Cadastrar sistema".
3. **Sistema** (abas):
   - **Visão geral:** origens (repositório, ramo, leituras), commit processado
     e pendente, botão "Pedir pull".
   - **Ingestão:** fila atual; histórico de pulls; ignorados de cada pull com o
     motivo (segredo, binário, filtro do cadastro, etc.).
   - **Curadoria:** rodadas e lotes (quando, perfil, itens, registrados, tempo,
     erro) e avisos do código (fonte inventada descartada, nota não ligada que
     mudou).
   - **Verificação:** a lista do verificador.
   - **Notas:** árvore por pasta (documentos, assuntos, módulos, regras,
     integrações, APIs, dados), leitura da nota, origens com link para o
     GitHub.
   - **Credenciais:** credenciais de agentes que leem ou escrevem este
     sistema; criar (a chave aparece uma vez) e revogar.
4. **Cadastrar sistema:** tag, origens e leituras; instrução da chave de
   acesso ao repositório.

**O que falta na API para a fase 1**
- Login do AD e sessão para pessoas (hoje a API só conhece credenciais `pv_`).
- Listar sistemas (hoje só se consulta um por tag).
- Guardar o histórico das rodadas e dos lotes do curador (hoje só no log do
  container).
- Ler as notas de um sistema e o resultado da verificação.
- Criar, listar e revogar credenciais pela API (hoje só pela linha de comando).
- Abrir a tela na rede interna (hoje a API só escuta no próprio servidor).

### Fase 2: dono e permissões

- Qualquer pessoa do AD entra; vê só os sistemas em que tem papel.
- Quem cadastra um sistema vira **dono**; o dono convida pessoas (pelo login
  do AD) como **editor** ou **leitor**, e cria credenciais de agentes.
- Cadastro pelo próprio dono. **Depende do GitHub App** (DV-286, tarefa a
  criar): com ele, a tela confere se o app enxerga o repositório e avisa se não
  enxerga, sem chave manual.

### Fase 3: corrigir o conhecimento e buscar

- **Comentar e mandar refazer (decisão: opção B).** Numa nota, a pessoa
  comenta o que está errado e manda refazer. O comentário vira um pedido na
  fila do curador, só para aquela nota, com quem pediu. A tela mostra o pedido
  (na fila, feito, recusado com motivo) e o antes e depois da nota.
  - Não há edição direta da nota: a próxima rodada do curador a reescreveria.
  - Se o erro é no fato (o documento de origem está errado), a correção é no
    repositório de origem, que é a fonte da verdade.
- **Busca** (DV-293): texto completo, só nos sistemas que a pessoa pode ler.

## 6. Fora por enquanto

- **Criar repositório pela tela** (decidido em 22/10/2026): é um fluxo
  complexo e exigiria permissão de administração para o GitHub App. Quem
  precisa usa "Use this template" no `petro-docs-modelo` e cadastra depois.
- Edição direta de nota (ver fase 3).
- Avisos por e-mail ou Teams.

## 7. Como a tela é feita (proposta)

- Servida pela própria API do petro-vault (FastAPI), com páginas no servidor e
  JavaScript simples, como o painel do Petro Observer. Sem build de front-end.
- Login do AD copiado do painel do observer (sem importar código de lá).
- A tela só fala com a API; o curador e o vault continuam como estão.

## 8. Para o design (briefing)

O que se pede ao Claude Design é a especificação (plano), não o código: telas,
o que cada uma mostra, estados e navegação. A construção é feita aqui.

- **Telas da fase 1:** entrar, sistemas, sistema (6 abas), cadastrar sistema.
- **Estados de cada tela:** vazio (sistema sem pull), processando (fila
  andando), em dia, com problema (verificação ou erro de pull), erro de acesso
  ao repositório.
- **Dados:** os campos de cada aba estão na seção 5; os sinais de confiança na
  seção 2.
- **Tom:** ferramenta de trabalho para gente técnica; o que importa é ver
  rápido o estado e chegar à origem de cada coisa.

## 9. Perguntas em aberto

1. **Visual:** o mesmo tema do painel do Petro Observer (visual HMI, DV-311)
   ou um visual próprio do petro-vault? Fica para o plano do Claude Design.
2. **Na fase 1, só o administrador cadastra?** Proposta: sim; o cadastro pelo
   dono entra com a fase 2 e o GitHub App.
3. **Endereço da tela:** porta própria em homologação (ex.: `10.2.2.31:8670`)
   e, depois, um nome interno.

## 10. Tickets da fase 1

- **API da fase 1** (não depende do visual; pode começar já): login do AD e
  sessão, listar sistemas, histórico de rodadas e lotes, ler notas e
  verificação, credenciais pela API, tela aberta na rede interna.
- **Tela da fase 1** (começa quando o plano do Claude Design chegar): as telas
  da seção 5, construídas aqui sobre a API.
