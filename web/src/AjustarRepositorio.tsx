import { Copiavel } from "./tokens";

// "Quer ajustar antes de incluir?" (DV-600): um prompt pronto para um agente
// (Claude Code ou outro) organizar o repositório no padrão do PetroVault antes
// do cadastro. Opcional: dá para incluir como está e organizar depois.

export type TipoVault = "sistema" | "referencia" | "template";

// Infraestrutura (DV-602 a DV-604): o PetroVault lê os arquivos de container e o .env.example para as notas
// de infra e o mapa (stacks, banco e serviços externos). Vale para os dois tipos de vault.
const INFRA = `Infraestrutura (o PetroVault lê estes arquivos e desenha o mapa de infraestrutura):
- Se o sistema roda em container, deixe no repositório o Dockerfile, o docker-compose.yml e o .dockerignore (e o nginx.conf ou Caddyfile, se houver). Não mude o que já existe: portas, nome de projeto, volumes e serviços ficam como estão. Falta de healthcheck ou de restart vai para PENDENCIAS.md.
- Mantenha um .env.example com TODAS as variáveis que o sistema lê: endereço real de banco e serviços (host:porta), senha e token sempre falsos (ex.: troque-me). Variável que existe por ambiente leva o sufixo _PROD / _HOMO. Nunca copie o .env de verdade nem valor de segredo.
- Não escreva documentação de infra à mão: o PetroVault gera a partir desses arquivos.`;

const COMUM = `Regras:
- Trabalhe numa branch nova e abra um PR. Nada direto no ramo principal.
- Não mude comportamento, código de produção nem visual. Só organize e documente.
- Não invente: tudo o que escrever tem que estar no repositório (código, comentários, documentos). O que não der para confirmar, anote em PENDENCIAS.md para o time decidir.
- Nada de segredo (senha, token, chave) em nenhum arquivo.
- No PR, resuma o que foi criado e o que ficou em PENDENCIAS.md.`;

function promptSistema(repo: string, ramo: string) {
  return `Preciso organizar a documentação do repositório ${repo} (ramo ${ramo}) para ele ser lido pelo PetroVault, a base de conhecimento da Petrovina. O PetroVault lê o código e os documentos e escreve notas para pessoas e agentes consultarem.

Organize a documentação em docs/, no padrão do repositório modelo PetrovinaS/petro-docs-modelo:
docs/processos/    como as coisas acontecem (fluxos, rotinas, passo a passo)
docs/manuais/      como usar ou operar (telas, instalação, operação)
docs/decisoes/     decisões tomadas e o motivo de cada uma
docs/referencias/  glossário, integrações, contratos, tabelas de referência

Cada documento é um .md com este cabeçalho:
---
titulo: <título>
tipo: processo | manual | decisao | referencia
responsavel: <time ou pessoa>
revisado_em: <AAAA-MM-DD>
---

- Mova para docs/ a documentação que já existe (README de módulos, specs, wikis exportadas), sem perder conteúdo.
- Escreva o que falta só a partir do que está no código: regras de negócio, integrações, APIs e dados principais.
- O README.md da raiz continua: deixe nele o que é o sistema e um índice de docs/.

${INFRA}

${COMUM}`;
}

function promptReferencia(repo: string, ramo: string) {
  return `Preciso reorganizar o repositório ${repo} (ramo ${ramo}) para ele ser consumido por agentes de IA e sistemas pelo PetroVault, a base de conhecimento da Petrovina. Ele vai entrar como vault de Referência: cada arquivo é copiado como está, sem reescrita, e um curador escreve guias de quando usar cada coisa a partir dele. Por isso cada regra precisa existir em arquivo próprio, em texto, com o código pronto para copiar.

Estrutura:
README.md                o que é, princípios, como usar, índice dos arquivos
tokens/                  valores exatos (ex.: tokens.json no formato Design Tokens, $value e $type, e tokens.css com as variáveis)
fundamentos/*.md         as bases (ex.: cores, tipografia, espaçamento, ícones, marca, acessibilidade)
componentes/<nome>.md    um arquivo por componente ou item de referência
padroes/<nome>.md        combinações e telas inteiras
assets/                  imagens, fontes e PDF (não viram nota: ficam para baixar pela API e pelo MCP)
vitrine/                 páginas de demonstração que já existam, usando os tokens

Modelo de cada componentes/<nome>.md:
---
componente: <nome>
tokens: [tokens usados]
---
# <Nome>
Para que serve, em uma ou duas frases.
## Quando usar / quando não usar
## Variações
## Estados
## Faça / não faça
## Acessibilidade
## Código   (HTML/CSS ou do framework usado, completo, copiado do que já existe, em blocos de código)

- Extraia o que já existe (páginas, CSS, componentes) para essa estrutura com os valores e o código exatos. Não mude o visual.
- Antes do PR, confira: a vitrine abre igual a antes; todo valor do original está nos tokens com o mesmo valor; toda parte do original tem um .md correspondente; nenhum .md passa de umas 300 linhas.

${INFRA}

${COMUM}`;
}

export function AjustarRepositorio({ tipo, repo, ramo }: { tipo: TipoVault; repo: string; ramo: string }) {
  const nome = repo.replace("https://github.com/", "").replace(/^git@github\.com:/, "").replace(/\.git$/, "") || "<repositório>";
  const prompt = tipo === "referencia" ? promptReferencia(nome, ramo || "main") : promptSistema(nome, ramo || "main");
  return (
    <details className="ajustar section-gap">
      <summary>Quer ajustar o repositório antes de incluir?</summary>
      <p>
        Um repositório organizado vira um vault melhor. Copie o pedido abaixo e cole no Claude Code (ou outro agente) aberto
        na pasta do repositório: ele organiza {tipo === "referencia" ? "os arquivos de referência" : "a documentação"} no
        padrão do PetroVault e abre um PR.
      </p>
      <Copiavel id="prompt-ajuste" texto={prompt} rotulo="Pedido para o agente" linhas />
      <div className="banner warn" style={{ marginTop: 14 }}>
        <span>
          <b>A mudança só chega ao PetroVault depois do merge no ramo {ramo || "main"}.</b> Depois disso, use "Pedir pull"
          no vault (ou espere a próxima rodada). Não precisa esperar para criar o vault: dá para incluir agora e organizar depois.
        </span>
      </div>
    </details>
  );
}
