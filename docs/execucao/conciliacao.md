# Conciliação do documento de execução com o que existe

Etapa E0 do [documento de execução](PetroVault_Documento_de_Execucao_v1.md). O
documento descreve a evolução pretendida; este arquivo registra, item a item, o
que foi decidido diante do que já está implementado e validado (DV-287 a
DV-547). Decisões de 26/10/2026, aprovadas pelo Tiago.

Onde este arquivo e o documento divergem, vale este arquivo.

## Decisões principais

| # | Documento propõe | Existe hoje | Decisão | Ticket |
| --- | --- | --- | --- | --- |
| 1 | Entrar com a Microsoft (Entra ID, OIDC + PKCE) | Login pelo AD via LDAPS (DV-547) | Botão da Microsoft **pronto e desabilitado** ("em breve") e o **formulário do AD logo abaixo**, até a infra definir como receber o Azure AD. | DV-574 |
| 2 | PAT do GitHub colado por fonte | Chave de deploy só leitura por origem; GitHub App `petro-vault` criado (ID 5392441) | **GitHub App**, sem PAT. "Adicionar repositório" lista os repositórios onde o App está instalado. Configurar com o Tiago **depois da rodada de visual**. | DV-573 |
| 3 | Consulta padrão `verification=verified` | Sem estado editorial; verificação técnica pelo verificador | Adotar os estados editoriais (em revisão, verificada, arquivada), mas **padrão `all`**, com o estado visível em cada nota. | DV-575, DV-293 |
| 4 | React + PostgreSQL + fila + armazenamento de objetos | FastAPI + SQLite + vault em git + curador Hermes | **Frontend React + TypeScript**; **backend atual mantido**, com banco próprio (SQLite) **até migrar para o PostgreSQL corporativo**, que a infra está criando. | DV-548, DV-572 |

## Conciliações menores

- **Processamento.** O documento pede "Processar fontes" manual; o curador já
  roda a cada 15 minutos. Ficam os dois: o automático e o botão (pedido de pull).
- **Token de integração.** É a credencial `pv_` com permissão `ler`, só leitura.
  A escrita de achados por agentes (DV-293) é permissão separada (`escrever`),
  fora do token mostrado na aba Integrações. Ganha validade, última utilização e
  prefixo visível (RF10).
- **Snapshot.** Cada rodada já é um commit no vault (funciona como snapshot).
  Falta a regra de não publicar quando uma das origens falhou (registrar na
  DV-554 ou em tarefa própria quando chegar a hora).
- **Datas.** Gravadas com o deslocamento de Cuiabá (`-04:00`), sem ambiguidade;
  a tela mostra em Cuiabá.
- **Diagnóstico automático (RF05).** Hoje as leituras (perfil, incluir, excluir)
  são declaradas no cadastro. O diagnóstico pode **propor** leituras para a pessoa
  confirmar; o caminho fixo continua sendo do código, não do modelo.
- **Sistema.** A tag é o identificador estável (`system_id`). Nome, descrição e
  equipe entram como campos de exibição quando a tela de cadastro pedir.
- **Papéis.** Leitor, mantenedor e administrador (documento) correspondem a
  leitor, editor/dono e administrador (`docs/tela.md`); fase 1 só tem
  administrador (`VAULT_ADMINS`).

## Abas: documento × plano da tela

| Documento | `tela-plano.md` | Nesta fase |
| --- | --- | --- |
| Visão geral | Visão geral | DV-548 |
| Fontes | Ingestão | DV-548 |
| Processamento | Curadoria | DV-548 |
| Conhecimento | Verificação + Notas | DV-548 |
| Integrações | Credenciais | DV-548 |
| Mapa | — | DV-576 |
| Agente | — | DV-577 (depende da DV-293) |

Abas sem implementação real não aparecem (UX05: nada simulado).

## Visual

- Layout, navegação e textos: protótipo em [`prototipo/`](prototipo/)
  (`index.html` e capturas). O HTML é referência de experiência, não código a
  reaproveitar.
- Identidade: [`prototipo/DESIGN_PACKAGE.md`](prototipo/DESIGN_PACKAGE.md) —
  verde `#007800`, fonte Ubuntu, temas claro e escuro, sidebar recolhível.
- Contraste WCAG AA (texto ≥ 4,5:1) nos dois temas.
