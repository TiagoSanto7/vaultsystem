# PetroVault Documento de execução

Versão 1.0 • 26 de outubro de 2026 • Petrovina

## 1 Objetivo e limites da entrega

Construir a primeira versão operacional do PetroVault a partir da experiência aprovada. O produto reúne repositórios de um sistema, transforma código e documentação em notas Markdown com proveniência, apresenta suas relações em um mapa e disponibiliza o conhecimento por agente, API e MCP.

Este documento orienta produto, engenharia, infraestrutura e testes. A aprovação comunicada pelo responsável pelo produto refere-se ao protótipo e ao fluxo de uso. As escolhas técnicas e políticas identificadas como propostas abaixo precisam de ratificação; não representam infraestrutura já contratada ou implantada.

**Fluxo aprovado:** entrar com a Microsoft → cadastrar sistema → adicionar fontes com PAT do GitHub → processar e revisar conhecimento → consultar notas e mapa → conversar com o agente ou criar um token do PetroVault para integração externa.

**Referência de interface:** `petrovault/index.html`, entregue junto ao conjunto de artefatos do projeto. O protótipo é uma referência de experiência, não uma aplicação pronta para produção. Seu login, PAT, tokens, curadoria, respostas e permissões são simulados; dados de exemplo e estado temporário do navegador devem ser substituídos por serviços reais.

### Convenções de decisão

- **Aprovado:** decisão de produto consolidada durante a revisão do protótipo.
- **Proposto:** detalhamento técnico ou operacional recomendado neste documento para tornar a execução objetiva.
- **A confirmar:** depende da organização, do ambiente ou de uma escolha ainda não tomada. A seção 14 identifica responsáveis por função e o ponto em que cada definição é necessária.

### Escopo da primeira versão

Login corporativo; onboarding curto; catálogo de sistemas; múltiplas fontes GitHub por sistema; PAT por fonte; diagnóstico automático de conteúdo; processamento assíncrono; notas versionadas; revisão e proveniência; mapa navegável; agente contextual; consulta externa somente leitura; criação e revogação de tokens por sistema; auditoria e operação básica.

### Fora do escopo inicial

Escrita nos repositórios, execução do código ingerido, agentes que alteram sistemas, novos conectores além de GitHub, catálogo global de conexões, gestão complexa de grupos dentro de cada sistema, comunicação entre agentes, fine-tuning e automações externas de escrita. Não reintroduzir uma aba Acessos nem uma etapa obrigatória de cadastrar conexões antes de adicionar uma fonte.

<!-- page -->
## 2 Experiência aprovada e navegação

A interface deve manter conteúdo central amplo, sidebar principal recolhível, temas claro e escuro, avatar no topo direito e verde Petrovina como destaque. Usar o símbolo fornecido e a fonte Ubuntu quando disponível como ativo do produto. O fundo permanece branco ou grafite; o material de referência não autoriza substituir o layout aprovado por outro template.

### Entrada e primeira utilização

**UX01** O botão “Entrar com a Microsoft” direciona para autenticação corporativa. O PetroVault não coleta a senha Microsoft em formulário próprio. Após sucesso, mantém uma sessão segura e apresenta apenas os sistemas autorizados. Falha de login, conta sem acesso e sessão expirada devem ter mensagens curtas e ação de recuperação.

**UX02** Na primeira entrada, mostrar três etapas: cadastrar sistema e fontes; produzir notas e mapa; consultar pelo agente e integrar. Permitir avançar, voltar, pular e rever pelo perfil. Persistir conclusão por usuário no servidor, inclusive entre dispositivos. A persistência apenas local do mockup não é a regra de produção.

**UX03** Transições devem usar fade e deslocamento leve, sem deslocar cabeçalho e controles. Respeitar movimento reduzido e navegação por teclado. A iluminação verde fica no canto inferior direito do fundo externo da tela de onboarding, nunca no container central.

### Áreas do sistema

| Área | Função principal | Ação visível |
| --- | --- | --- |
| Visão geral | Resumir fontes, conhecimento e atualização | Continuar o trabalho |
| Fontes | Cadastrar e manter repositórios e PAT | Adicionar repositório |
| Processamento | Acompanhar execuções reais | Processar fontes |
| Conhecimento | Consultar, revisar e verificar notas | Abrir nota |
| Mapa | Explorar relações com origem | Selecionar elemento |
| Agente | Fazer perguntas ao conhecimento disponível | Enviar pergunta |
| Integrações | Autorizar consultas externas ao sistema | Criar token |

**UX04** Ajuda longa fica em expansores fechados. Dicas “?” funcionam por hover, foco de teclado e toque/clique, sem depender exclusivamente do mouse. Contratos, payloads e simuladores ficam dentro de “Documentação técnica”. Recomenda-se renomear “Ver contrato” para “Especificação da consulta”.

**UX05** Mostrar estados vazios e próximos passos. Não exibir “atualizado”, percentuais de qualidade ou notas verificadas sem cálculo real. Resultados vazios, carregamento, erro e sucesso devem ser distinguíveis. Números do mockup não são metas de produção.

<!-- page -->
## 3 Sistemas e fontes GitHub

**RF01 Cadastro de sistema.** Nome, descrição, equipe responsável e tags de organização. Gerar identificador estável no servidor. Validar nome obrigatório e duplicidade dentro do workspace, sem depender do rótulo visual para autorização. Recomenda-se atribuir o criador como mantenedor inicial, sujeito à política corporativa de criação de sistemas.

**RF02 Cadastro de fonte.** Receber URL do repositório, branch e PAT do GitHub. Permitir vários repositórios por sistema. O PAT é uma credencial de ingestão; não é o login do usuário, uma tag nem um token de integração do PetroVault. A pessoa cria o PAT no GitHub e informa-o ao cadastrar a fonte.

**RF03 Testar acesso.** Validar formato da URL, acesso ao repositório e existência da branch no backend. Separar respostas: leitura autorizada, credencial inválida/expirada, falta de autorização, branch não encontrada, limite do provedor e indisponibilidade temporária. Não concluir que um repositório privado inexiste apenas a partir de um retorno sem acesso.

**RF04 Manutenção.** Mostrar URL, branch, estado, última verificação e quantidade de notas. Oferecer atualizar PAT, testar acesso e processar. Não devolver o segredo salvo ao navegador; apresentar somente máscara e metadados. A atualização não modifica o PAT na conta GitHub, apenas substitui a credencial armazenada no PetroVault.

### Regras técnicas propostas

- Preferir PAT de acesso refinado, limitado aos repositórios e às permissões de leitura necessárias aos endpoints usados. A política da organização pode exigir aprovação; validar esse pré-requisito antes do piloto [R1, R2].
- Armazenar o PAT criptografado ou em cofre de segredos. O worker recebe acesso apenas durante a operação; logs, prompts, embeddings e respostas nunca recebem o PAT.
- Aceitar GitHub.com inicialmente. GitHub Enterprise exige host explicitamente configurado. Rejeitar URLs com credenciais, parâmetros inesperados ou destinos arbitrários; validar redirecionamentos e impedir acesso a endereços internos não autorizados.
- Normalizar o repositório pelo identificador do provedor. Proposta: uma fonte ativa por repositório e branch dentro do mesmo sistema. A mesma origem em sistemas diferentes mantém autorização e ciclo de publicação separados.
- Permitir salvar a fonte com diagnóstico de erro, mas impedir processamento enquanto o acesso estiver inválido. Uma falha transitória não apaga conhecimento já publicado.
- Desativar a fonte deve suspender novos jobs e retirar suas evidências do corpus consultável. Manter histórico para auditoria conforme a retenção definida. A política para notas com múltiplas fontes está na seção 5.

**Aceite mínimo:** cadastrar dois repositórios no mesmo sistema, testar leitura, rejeitar duplicidade e recuperar uma fonte após substituição de PAT sem criar outro sistema.

<!-- page -->
## 4 Diagnóstico e processamento das fontes

**RF05 Identificação automática.** Inspecionar arquivos e pastas de uma revisão fixa do repositório. Classificar conteúdo em código, documentação, testes, configuração, gerado/dependências e não suportado. Inferir “código”, “documentação” ou “misto” para o repositório a partir desses resultados. A inferência não deve depender apenas do nome da fonte ou da extensão do arquivo.

Em um repositório misto, conservar uma única fonte e aplicar tratamentos específicos a cada arquivo. Código e documentação continuam conectados na proveniência. Arquivos ambíguos ficam sinalizados; arquivos excluídos aparecem no diagnóstico, com motivo. Não contabilizar conteúdo ignorado como conhecimento processado.

**RF06 Revisão do diagnóstico.** Exibir um resumo curto de tipos encontrados. Em “Detalhes”, permitir incluir/excluir caminhos e corrigir classificações. Proposta: apresentar o diagnóstico antes da primeira curadoria; em execuções seguintes, reaplicar regras salvas e avisar sobre mudanças relevantes. Não impor uma nova tela de autenticação.

### Execução assíncrona proposta

1. Criar job com sistema, fontes e regras de ingestão; validar autorização do solicitante.
2. Resolver a branch de cada fonte para o SHA completo de um commit e manter essa revisão durante a execução.
3. Obter e classificar conteúdo; registrar arquivos ignorados e limites excedidos.
4. Extrair estrutura e texto sem executar código, scripts, instaladores ou instruções encontradas nos arquivos.
5. Curar notas Markdown e relações com evidências verificáveis. Validar o formato de saída antes de gravar candidatos.
6. Publicar um snapshot consistente de notas e relações; atualizar os índices e então marcar o job como concluído.

### Estados e recuperação

Job: aguardando → coletando → classificando → curando → validando → publicando → concluído. Estados alternativos: falhou, cancelado ou concluído com avisos. Percentual deve derivar de unidades de trabalho conhecidas; usar etapa e progresso indeterminado quando não houver base para estimar.

**RF07** Reprocessar somente itens alterados quando possível, usando hashes, commit, regras, versão do extrator e configuração de curadoria. Uma mudança de modelo ou prompt também pode invalidar resultados anteriores. Repetir um job não duplica notas nem relações.

**Proposta de consistência:** falha em uma fonte impede promover o novo snapshot do sistema; o snapshot anterior continua servindo. Arquivos explicitamente excluídos podem gerar conclusão com avisos. Cancelamento e falha não expõem resultados parciais como concluídos.

**Atualização inicial:** manual por “Processar fontes”. Agendamento e webhook são evoluções, não dependências do primeiro fluxo. Tratar limites do GitHub e do modelo com retry limitado, espera progressiva e diagnóstico persistido.

<!-- page -->
## 5 Notas Markdown e verificação

**RF08** Cada nota contém identidade estável, título, corpo Markdown, tipo, tags, versão, estado de revisão, evidências e datas de criação/atualização. A tela apresenta o texto e permite abrir sua proveniência. Notas são artefatos versionados do conhecimento, não cópias anônimas de trechos do código.

**Proveniência mínima:** fonte, repositório, branch, SHA completo, caminho, revisão da nota e job que a produziu. Registrar linhas quando disponíveis. Uma referência deve apontar para a revisão lida, não apenas para a versão atual da branch. Relações entre notas e código também precisam de evidência e estado de derivação.

### Política de revisão proposta para a primeira versão

- Conteúdo gerado por IA nasce **em revisão**, mesmo quando todas as referências são válidas.
- **Verificada** significa que um mantenedor/revisor autorizado aprovou a versão da nota e suas evidências. Registrar quem, quando e qual versão foi aprovada.
- **Arquivada** não participa de novas consultas. O histórico permanece conforme a política de retenção.
- Uma alteração material no corpo ou nas evidências cria nova versão em revisão. Não transferir automaticamente a aprovação da versão anterior.
- Se código e documentação divergirem, registrar a divergência e as origens. Não escolher silenciosamente uma “verdade” nem usar confiança numérica do modelo como verificação humana.

A validação automática de formato, citações e arquivos é uma etapa técnica. Ela não equivale ao estado editorial “verificada”. Confirmar a responsabilidade pela revisão antes do piloto; o modelo acima é a recomendação de implementação.

### Comportamento de consulta

`verification=verified`, padrão, retorna apenas versões correntes verificadas. `verification=all` inclui versões correntes em revisão e verificadas, sempre dentro do conteúdo autorizado. O filtro não executa revisão, não altera a nota e não amplia o acesso do token.

Após a primeira curadoria, Integrações pode ser habilitada quando existir um snapshot consultável. Se nenhuma nota tiver sido verificada, a consulta padrão retorna vazio com mensagem orientativa, e não promoção automática. O Agente deve mostrar quando uma resposta usa notas em revisão.

### Remoção ou perda de origem

Credencial expirada: manter a última publicação com data e aviso de atualização pendente. Fonte desativada ou retirada de publicação: bloquear a consulta às notas dependentes até revisão ou recomposição das evidências. Para notas com várias fontes, bloquear se qualquer evidência indispensável deixar de ser publicável; não expor trechos de fonte restrita por meio de uma síntese.

**Aceite mínimo:** aprovação de uma versão, reprocessamento com mudança, retorno ao estado em revisão e comprovação de que o filtro padrão deixa de retornar a versão anterior como corrente.

<!-- page -->
## 6 Identidade e os dois tipos de token

### Login das pessoas

**RF09 Aprovado:** entrada com a Microsoft e identidade corporativa. **Proposto:** OpenID Connect com Authorization Code e PKCE, sessão de servidor e cookie seguro, HttpOnly e com proteção de CSRF aplicável. Confirmar tenant, registro da aplicação, URLs de retorno e integração com o diretório. AD local isolado não basta para concluir automaticamente essa configuração [R3].

A remoção da aba Acessos não elimina autorização no backend. Proposta mínima: leitor consulta sistemas atribuídos; mantenedor cadastra fontes, processa, revisa notas e gerencia tokens do seu sistema; administrador define associação de pessoas a sistemas pela configuração administrativa corporativa. Não adicionar uma nova tela complexa ao fluxo principal sem validação de produto.

### Token do GitHub

PAT usado exclusivamente pelo serviço de ingestão para ler a fonte. É vinculado às permissões da identidade que o criou. Expiração, revogação, mudança de acesso ou aprovação organizacional pendente podem interromper leituras. Não reutilizar esse segredo para autorizar consultas externas ao PetroVault.

### Token do PetroVault

**RF10 Aprovado:** criar e revogar um token na aba Integrações do sistema. Ele autoriza somente consulta ao conhecimento daquele sistema. Não concede escrita, execução de código nem acesso direto ao GitHub.

**Proposta:** token opaco de alta entropia, gerado no servidor; mostrar o segredo completo apenas na criação. Persistir identificador, prefixo de identificação, hash seguro, sistema, criador, criação, expiração, última utilização e revogação. Comparar em tempo constante. Nunca armazenar o segredo em texto puro ou localStorage. Política inicial sugerida: validade de 90 dias, ajustável após decisão corporativa; criar substituto e revogar o anterior para rotação.

Cada requisição valida token, validade, revogação, escopo de leitura e vínculo ao sistema. A busca recebe esse contexto antes de recuperar notas, trechos, relações e proveniência. Alterar `system_id`, tags ou `verification` nunca amplia o acesso. Revogação deve valer já na próxima requisição; evitar caches positivos de autorização que atrasem a retirada.

### Limite de publicação a confirmar

A posse de um PAT autoriza tecnicamente a leitura no GitHub, mas não define quem pode receber o conhecimento derivado. Proposta de MVP: cada sistema é um limite de publicação; o mantenedor só inclui fontes permitidas para sua audiência. Sistemas com audiências diferentes devem ficar separados. Se forem exigidas restrições por fonte dentro do mesmo sistema, implementar ACL por evidência antes de publicar; não pressupor sincronização automática das permissões individuais do GitHub.

<!-- page -->
## 7 Arquitetura e componentes

Arquitetura proposta, sujeita ao ambiente corporativo. Manter os componentes desacoplados sem exigir microserviços independentes na primeira entrega. Uma aplicação modular com worker separado é suficiente como ponto de partida.

| Componente | Responsabilidade | Limite de acesso |
| --- | --- | --- |
| Aplicação web | Fluxos aprovados e sessão de usuário | Sem segredos de infraestrutura |
| Backend | Sistemas, fontes, revisão, jobs e tokens | Autoriza cada operação |
| Worker de ingestão | Ler revisões GitHub, extrair e curar | PAT somente durante a tarefa |
| Serviço de consulta | Busca autorizada e proveniência | Corpus do sistema solicitado |
| Agente | Recuperar evidências e responder | Sem ferramentas de escrita |
| Adaptadores HTTP e MCP | Expor o mesmo serviço de consulta | Mesmo controle de token |
| Persistência | Metadados, versões e relações | Particionamento por sistema |
| Cofre e armazenamento | PATs e artefatos de conhecimento | Identidades de serviço restritas |

### Base tecnológica recomendada

Frontend React com TypeScript; backend Python com FastAPI; PostgreSQL para metadados, relações e busca textual; pgvector se a avaliação justificar busca semântica. Fila durável com worker Python e armazenamento de objetos para snapshots e artefatos. Cofre de segredos do ambiente escolhido. Não é necessário um banco de grafos dedicado no MVP: relações persistidas e consultas delimitadas atendem ao mapa inicial.

Essas escolhas não foram aprovadas como stack obrigatória. Antes de iniciar o repositório, verificar padrões e componentes já existentes na Petrovina. Registrar substituições em uma decisão arquitetural curta, preservando contratos e critérios de aceite.

### Contratos internos

O worker recebe IDs, regras e revisão, não segredos na mensagem de fila. Resolve a credencial por referência autorizada. O serviço de consulta recebe identidade, sistema, filtros e versão de publicação. O agente chama esse serviço; não implementa uma segunda política de autorização.

Armazenar nota estruturada e corpo Markdown canônico, com exportação possível para arquivo. O índice de busca e os embeddings são derivados e reconstruíveis. A publicação troca a referência ao snapshot ativo em transação após todas as validações; consultas em andamento mantêm uma visão consistente.

### Modelo de IA

Criar uma interface substituível para o provedor. Registrar modelo, versão do prompt, custo estimado/real disponível, duração e versão do pipeline. Confirmar fornecedor, região, retenção e tratamento de código privado antes de enviar dados reais. A especificação não fixa modelo nem presume autorização para transmitir repositórios a qualquer serviço.

<!-- page -->
## 8 Modelo de dados e persistência

Esquema lógico proposto. Identificadores devem ser estáveis e independentes de nomes de exibição. Todos os registros que descrevem conhecimento ou autorização incluem sistema/workspace quando aplicável. Chaves e consultas devem impedir referências cruzadas acidentais.

| Entidade | Campos essenciais | Regra principal |
| --- | --- | --- |
| Sistema | id, workspace, nome, descrição, equipe, tags, estado | Nome não é chave de autorização |
| Associação | usuário ou grupo, sistema, papel | Política avaliada no servidor |
| Fonte | id, sistema, repo_id, URL, branch, segredo_ref, estado | Não contém PAT legível |
| Revisão de fonte | fonte, SHA, manifesto, hashes | Conteúdo imutável por revisão |
| Job | id, sistema, etapas, fontes, tentativas, erros, datas | Idempotente e auditável |
| Snapshot | id, sistema, job, versões de origem, estado | Uma publicação ativa por sistema |
| Nota | id, sistema, tipo, versão corrente | Identidade preservada entre versões |
| Versão de nota | Markdown, estado, autor IA, revisor, datas | Aprovação vinculada à versão |
| Evidência | versão de nota, fonte, commit, arquivo, linhas | Não aponta só para branch mutável |
| Relação | origem, destino, tipo, evidência, snapshot | Não é uma aresta sem origem |
| Token externo | id, sistema, hash, prefixo, validade, revogação | Segredo mostrado uma única vez |
| Conversa | usuário, sistema, mensagens, referências | Sem cruzar histórico entre sistemas |
| Auditoria | ator, ação, alvo, resultado, correlação, data | Sem PAT, token ou corpo sensível |

### Índices e consistência

Índices para sistema/estado, fonte/revisão, nota/versão e token/prefixo. A restrição de sistema e a política de publicação precedem a seleção vetorial ou textual. Não buscar em todo o corpus e filtrar apenas depois de construir o contexto do modelo.

Guardar datas em UTC e exibir no fuso da pessoa. Manter migrações versionadas, chave de idempotência nos comandos sensíveis a repetição e transações para publicação, revisão e revogação.

### Retenção e exclusão

Proposta inicial a ratificar: retenção de auditoria por 90 dias e de conversas por 30 dias; versões de conhecimento mantidas enquanto o sistema estiver ativo. Não aplicar exclusão definitiva sem política aprovada. A retirada de consulta é imediata, mesmo quando o histórico permanece para auditoria.

Excluir/desativar um sistema deve revogar tokens, cancelar jobs pendentes e impedir consulta de notas, relações e conversas. A remoção física e a retenção de backups seguem a política corporativa. Testar restauração incluindo as referências de segredo e as publicações ativas; backup apenas do banco não basta se os artefatos estiverem em armazenamento separado.

<!-- page -->
## 9 Contrato de consulta HTTP

**RF11** Expor uma API versionada somente leitura para conhecimento. Proposta de endpoint: `POST /v1/knowledge/search`. Receber o token PetroVault em `Authorization: Bearer <token>`, sobre HTTPS. O endpoint e os exemplos deste documento não são um serviço publicado.

### Exemplo de requisição

```json
{
  "system_id": "petro-observer",
  "query": "Como funciona a ingestão de eventos?",
  "verification": "verified",
  "limit": 5
}
```

`system_id` é obrigatório e deve corresponder ao sistema vinculado ao token. Em produção, usar o identificador estável retornado pelo cadastro. `query` aceita de 1 a 500 caracteres após trim; `verification` aceita `verified` ou `all` e assume `verified`; `limit` é inteiro de 1 a 20 e assume 5. Rejeitar campos desconhecidos na primeira versão. Tags como filtro de consulta são uma evolução contratual, não um mecanismo de autorização.

### Exemplo de resposta reduzida

```json
{
  "system_id": "petro-observer",
  "snapshot_id": "snapshot-exemplo",
  "results": [{
    "note_id": "nota-exemplo",
    "note_version": 2,
    "title": "Ingestão de eventos",
    "excerpt": "Eventos são validados antes do processamento.",
    "verification": "verified",
    "updated_at": "2026-10-26T12:00:00Z",
    "provenance": [{
      "repository": "petrovina/observer-workers",
      "path": "docs/ingestion.md",
      "branch": "main",
      "commit": "0123456789abcdef0123456789abcdef01234567"
    }]
  }],
  "has_more": false
}
```

Dados fictícios. O retorno usa lista de evidências porque uma nota pode reunir várias fontes. Incluir versão da nota e snapshot evita ambiguidades. O campo `demo` do mockup não integra o contrato de produção. `has_more` indica resultados além do limite; paginação por cursor deve ser definida antes de prometer leitura exaustiva. Busca retorna trechos, não uma resposta redigida por IA.

<!-- page -->
## 10 MCP e comportamento de integração

**RF12** Implementar `search_knowledge` como adaptador do mesmo serviço da API. A ferramenta deve declarar `inputSchema`, `outputSchema`, descrição e comportamento somente leitura. A anotação de leitura não substitui autorização do servidor [R4].

### Exemplo de chamada MCP

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_knowledge",
    "arguments": {
      "system_id": "petro-observer",
      "query": "ingestão de eventos",
      "verification": "verified",
      "limit": 5
    }
  }
}
```

O exemplo representa uma chamada após inicialização e negociação do protocolo, e não uma sessão completa. Referência de sintaxe: MCP 2025-11-25. Fixar a versão suportada e o SDK no projeto após testar o cliente de destino; não presumir que essa versão será a única ou a mais recente no início da implementação.

No sucesso, envolver a resposta da seção 9 em `result.structuredContent`, com `content` textual compatível e `isError=false`. A declaração de saída deve refletir o formato real, inclusive proveniência múltipla. Produzir OpenAPI e schemas JSON versionados como artefatos de engenharia e testá-los contra respostas reais.

### Compatibilidade de autenticação

O fluxo aprovado cria um token próprio do PetroVault. Ele pode ser usado por clientes que aceitam Bearer configurado. Isso não garante compatibilidade com clientes MCP que exigem descoberta e autorização OAuth. Executar uma prova com os clientes escolhidos antes de prometer “conectar qualquer agente”. Caso OAuth seja obrigatório, apresentar a necessidade como extensão técnica, preservando a tela simples e sem recolocar conceitos de autenticação no fluxo comum [R5].

| Resultado | HTTP proposto | Comportamento |
| --- | --- | --- |
| Sucesso sem correspondência | 200 | results vazio, sem resposta inventada |
| Corpo inválido | 400 na API | Erro de validação legível |
| Token ausente, inválido ou revogado | 401 | Sem conteúdo de conhecimento |
| Token sem acesso ao sistema | 403 | Sem revelar fontes ou notas |
| Limite de consumo excedido | 429 | Informar possibilidade de repetição |
| Serviço temporariamente indisponível | 503 | Erro recuperável e correlação |

No MCP, distinguir erros do transporte/autorização, erros JSON-RPC e falhas da ferramenta. Não empacotar um erro de autenticação como resultado textual de sucesso.

<!-- page -->
## 11 Agente e mapa de conhecimento

### Agente contextual

**RF13** Conversa vinculada ao sistema e à identidade da sessão. Usar as notas do snapshot publicado; não pedir novo PAT para conversar e não ler diretamente o GitHub a cada pergunta. As referências devem abrir a nota e sua proveniência.

A resposta diferencia conteúdo verificado de conteúdo em revisão. Proposta: usar apenas verificado como padrão e oferecer “Incluir notas em revisão” em opção discreta. Sem evidência suficiente, explicar a limitação e sugerir onde procurar. Não inventar arquivos, commits ou regras de negócio. Conflitos entre evidências devem aparecer como conflito.

O agente não executa código, não altera fontes, não cria tokens e não revela credenciais. Conteúdo do repositório é dado não confiável; instruções dentro dele não mudam as regras do sistema. Implementar isolamento de prompt, orçamento de contexto e testes de injeção com documentos maliciosos.

Manter histórico separado por usuário e sistema. Mudanças de sistema não reutilizam contexto oculto anterior. Antes de reutilizar uma referência antiga, revalidar que continua publicável e autorizada. Proposta: não disponibilizar conversas pessoais via token de integração.

**Teste equivalente ao consumidor externo:** quando houver modo de prévia de integração, chamar o mesmo serviço e filtros daquele token. Não afirmar que a conversa administrativa demonstra as permissões de um token mais restrito. Esse modo é uma evolução opcional, não exige uma nova aba.

### Mapa navegável

**RF14** Mostrar sistema, fontes, notas e, quando extraídos com evidência, componentes de código. As relações precisam ter tipos compreensíveis, como “compõe”, “fundamenta” e “documenta”, com direção coerente.

Permitir selecionar nós, destacar vizinhança, filtrar tipos, ampliar/reduzir e mover o fundo. Abrir detalhes e proveniência; “Perguntar sobre isso” leva contexto explícito ao Agente. A seleção deve funcionar com teclado, e o painel de detalhes deve oferecer alternativa textual à leitura do grafo.

Renderizar um subconjunto delimitado com expansão progressiva, evitando carregar todo o universo de relações. O total de nós exibidos e filtros ativos precisam ser claros. Não inventar relações apenas para preencher o visual, nem apresentar uma relação inferida como dependência confirmada.

### Estados importantes

Primeiro sistema sem fonte; fonte com PAT inválido; processamento interrompido; nenhuma nota verificada; nenhum resultado; agente indisponível; mapa sem relações; token revogado. Cada estado deve preservar contexto e oferecer a próxima ação pertinente, com texto curto e detalhes sob demanda.

<!-- page -->
## 12 Segurança operação e qualidade

### Requisitos não funcionais propostos

**RNF01 Isolamento.** Aplicar autorização no backend em todas as rotas, objetos, pesquisas, relações e citações. Testar acesso por identificador de outro sistema, busca semântica, download e histórico. O filtro da interface não é proteção.

**RNF02 Segredos.** HTTPS em trânsito; PAT criptografado/cofre; token externo armazenado como hash. Não registrar credenciais, cabeçalhos de autenticação ou código completo em logs comuns. Redigir dados sensíveis em exceções, traces e eventos de observabilidade.

**RNF03 Ingestão segura.** Não executar conteúdo. Excluir arquivos de segredo conhecidos, dependências, binários e artefatos gerados por padrão; detectar e quarentenar possíveis segredos antes de transmitir ao modelo. Limitar tamanho, número de arquivos, contexto, tempo e custo por job. Valores precisam ser configuráveis e aparecer no diagnóstico quando afetarem cobertura.

**RNF04 Auditoria.** Registrar criação/alteração de fonte, teste de acesso, job, publicação, revisão, criação/revogação de token e consulta externa. Usar identificador de correlação e ator; manter conteúdo sensível fora do evento. Registrar recusas de autorização sem expor objetos restritos.

**RNF05 Acessibilidade.** Alvo proposto WCAG 2.2 AA para fluxos principais: foco visível, teclado, rótulos, contraste, leitura de estados e movimento reduzido. Dicas de ajuda não podem ser a única forma de conhecer um campo obrigatório.

### Metas de desempenho para homologação

Proposta inicial de carga: 10 sistemas, 30 fontes, 5 mil notas e 10 consultas concorrentes. Meta de busca: p95 até 2 segundos, excluindo geração do modelo; meta de feedback de job: confirmação de enfileiramento em até 2 segundos. Medir e ajustar com repositórios representativos. Tempo e custo de curadoria dependem de volume e provedor; não assumir SLA antes do ensaio.

### Operação e liberação

Ambientes separados de desenvolvimento, homologação e produção, com segredos distintos. Pipeline de entrega com análise estática, testes, migrações e varredura de dependências. Documentar restauração e rollback de aplicação/publicação, incluindo compatibilidade de banco.

Monitorar idade da fila, falhas de fonte, duração/custo de curadoria, notas pendentes de revisão, latência, recusas e limites de consulta. Alertar o responsável pelo sistema sobre fonte que deixou de atualizar; não enviar código ou segredos nas notificações.

Proposta inicial de recuperação: RPO de 24 horas e RTO de 4 horas, sujeitos à capacidade de infraestrutura. Executar teste de restauração antes do piloto. Definir retenção, responsáveis de plantão e tratamento de incidentes antes da produção.

<!-- page -->
## 13 Sequência de implementação e aceite

Executar em incrementos demonstráveis. As funções abaixo identificam responsabilidades, não pessoas já designadas. Estimar esforço e calendário após confirmar ambiente e equipe; não existe prazo de implantação aprovado neste documento.

| Etapa | Entrega e dependência | Critério para encerrar |
| --- | --- | --- |
| E0 Produto e arquitetura | Resolver decisões necessárias e registrar contratos | Escopo e escolhas anotados |
| E1 Fundação | Repositório, persistência, sessão Microsoft, layout e onboarding | Login real em homologação e isolamento de sessão |
| E2 Sistemas e fontes | Cadastro, PAT protegido, teste e diagnóstico | Dois repos mistos lidos sem expor segredo |
| E3 Pipeline | Fila, revisão fixa, candidatos e publicação | Job idempotente, falha recuperável e snapshot consistente |
| E4 Conhecimento | Revisão, proveniência, busca e mapa | Nota aprovada e invalidada após alteração material |
| E5 Consumo | Agente, API, token por sistema e revogação | Citações reais e testes positivos/negativos de autorização |
| E6 MCP e piloto | Adaptador, cliente escolhido, operação e restauração | Prova ponta a ponta e aceite do responsável pelo produto |

Frontend e backend podem avançar em paralelo após os contratos de E0. E4 depende de evidências reais de E3; E5 não deve ser homologada apenas com dados fixos. Compatibilidade MCP precisa de uma prova antecipada em E0, embora sua entrega completa esteja em E6.

### Cenários obrigatórios de aceite

- **AT01** Primeiro login apresenta onboarding; pular/concluir persiste por usuário; perfil permite rever; usuário não autorizado não vê dados.
- **AT02** Um sistema recebe dois repositórios, um misto. Diagnóstico separa código/documentação sem criar sistemas duplicados; exclusões são respeitadas.
- **AT03** PAT inválido impede leitura; atualização recupera a fonte. PAT e token externo não aparecem em logs, respostas, prompts ou armazenamento do navegador.
- **AT04** Repetição de job não duplica notas. Falha/cancelamento preserva a publicação anterior; mudança de commit produz proveniência correta.
- **AT05** Nota em revisão não aparece em verified; aparece sinalizada em all. Aprovação registra revisor; alteração material invalida a aprovação corrente.
- **AT06** Token do sistema A não consulta B por alteração de ID, filtros, mapa ou citações. Revogação bloqueia a próxima requisição. Agente respeita o mesmo limite.
- **AT07** Agente responde com referências existentes e admite ausência de evidência. Instruções maliciosas em um README não mudam comportamento nem extraem segredo.
- **AT08** API e MCP retornam conhecimento equivalente para os mesmos argumentos autorizados. Cliente MCP escolhido conecta de verdade; incompatibilidade de autenticação é resolvida, não escondida.
- **AT09** Login, formulário, revisão e mapa utilizáveis com teclado; dados vazios e erros compreensíveis. Testes de carga e restauração registrados.

**Definição de pronto:** código revisado, testes relevantes aprovados, migrações e rollback documentados, telemetria sem segredos, documentação técnica atualizada e demonstração do incremento aceita pelo responsável pelo produto.

<!-- page -->
## 14 Decisões pendentes e referências

| Decisão | Responsável por função | Momento necessário |
| --- | --- | --- |
| Stack e ambiente de hospedagem | Engenharia e infraestrutura | Antes de E1 |
| Tenant Microsoft e registro da aplicação | Identidade corporativa | Antes de validar login em E1 |
| Quem cria sistemas e quem revisa notas | Produto e responsável técnico | Antes de E2 e E4 |
| Publicação por sistema ou ACL por fonte | Produto e segurança da informação | Antes de ingerir conteúdo privado no piloto |
| Hosts GitHub e política de PAT | Administração GitHub | Antes de E2 com dados reais |
| Provedor de IA e uso de código privado | Engenharia e governança | Antes da curadoria real em E3 |
| Clientes MCP e forma de autenticação | Engenharia e consumidores | Prova em E0 e aceite em E6 |
| Validade de tokens e retenção | Operação e segurança da informação | Antes do piloto |
| Capacidade e metas de recuperação | Infraestrutura e operação | Antes da produção |

Essas definições não impedem implementar telas, modelos e testes locais. Impedem assumir configuração corporativa, exposição de dados ou compatibilidade que ainda não foi comprovada. Registrar a decisão, o responsável, a data e o impacto sobre os requisitos deste documento.

### Referências do produto

**P1** Protótipo aprovado: `outputs/petrovault/index.html`. Referência de layout e fluxo; o HTML do mockup não define a arquitetura de produção.

**P2** Identidade Petrovina: `system-design/bundle/DESIGN_PACKAGE.md` e ativos fornecidos. Preservar os ajustes aprovados: simplicidade, temas, ajuda discreta e iluminação externa. Mascote opcional.

### Referências técnicas consultadas

[R1] GitHub — Managing your personal access tokens. Permissões refinadas e ciclo de vida. https://docs.github.com/en/enterprise-cloud@latest/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

[R2] GitHub — Setting a personal access token policy for your organization. Aprovação e políticas corporativas. https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/setting-a-personal-access-token-policy-for-your-organization

[R3] Microsoft — OAuth 2.0 authorization code flow. Base para login corporativo proposto. https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow

[R4] MCP — Tools, referência 2025-11-25. Descoberta, chamada e schemas de ferramentas. https://modelcontextprotocol.io/specification/2025-11-25/server/tools

[R5] MCP — Authorization, referência 2025-11-25. Autorização no transporte HTTP. https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
