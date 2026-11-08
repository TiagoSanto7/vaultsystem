// Cliente da API da tela (/v1/painel, DV-547). Mesma origem: o cookie da sessão
// vai sozinho. 401 em qualquer chamada leva de volta à tela de entrar.

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

let aoPerderSessao: () => void = () => {};
export function quandoPerderSessao(f: () => void) {
  aoPerderSessao = f;
}

function mensagem(corpo: unknown, status: number): string {
  const d = (corpo as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (typeof x === "string" ? x : x?.msg ?? JSON.stringify(x))).join("; ");
  if (status === 503) return "Serviço indisponível no momento. Tente de novo em instantes.";
  return `Erro ${status}`;
}

export async function api<T>(caminho: string, opcoes: { metodo?: string; corpo?: unknown; semRedirecionar?: boolean } = {}): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`/v1/painel${caminho}`, {
      method: opcoes.metodo ?? "GET",
      credentials: "same-origin",
      headers: opcoes.corpo === undefined ? {} : { "Content-Type": opcoes.corpo instanceof Blob ? "application/zip" : "application/json" },
      body: opcoes.corpo === undefined ? undefined : opcoes.corpo instanceof Blob ? opcoes.corpo : JSON.stringify(opcoes.corpo),
    });
  } catch {
    throw new ErroApi(0, "Sem conexão com o hub do Vault System. Verifique a rede e tente de novo.");
  }
  const corpo = await r.json().catch(() => null);
  if (!r.ok) {
    if (r.status === 401 && !opcoes.semRedirecionar) aoPerderSessao();
    throw new ErroApi(r.status, mensagem(corpo, r.status));
  }
  return corpo as T;
}

// --- formatos que a API devolve ------------------------------------------

export type EstadoSelo = "erro_acesso" | "com_problema" | "processando" | "em_dia" | "vazio" | "removendo";

export interface Eu {
  login: string;
  nome: string;
  papel: string;
  ambiente: string;
  url_publica: string;
  apresentacao_vista_em: string | null;
  // Vault System: curadoria interna (LLM no hub) só com chave de API ativa; sem ela, nada de botão.
  curadoria?: Curadoria;
}

export interface Curadoria { disponivel: boolean; provedor: string | null }

export interface Commit { hash: string | null; data: string | null; url: string | null }

export interface Leitura { perfil: string; incluir: string[]; excluir: string[] }

export interface Origem {
  nome: string;
  repo: string;
  ramo: string;
  url: string | null;
  leituras: Leitura[];
  situacao: "sem_acesso" | "nunca_processado" | "atrasado" | "em_dia" | "removendo";
  leituras_antes: Leitura[] | null;
  classificacao: Record<string, "documentos" | "referencia-explicada" | "referencia" | "codigo-literal" | "codigo" | "ignorar"> | null; // DV-589: da árvore
  removida_em: string | null;
  commits_atras: number | null;
  acesso: { ok: boolean | null; em: string | null; erro: string | null };
  commit_processado: Commit;
  commit_pendente: Commit;
}

export interface Sinais {
  em_dia: { estado: Origem["situacao"]; commits_atras: number };
  fila: { itens: number; parados: number };
  verificacao: { total: number | null; por_tipo: Record<string, number> };
  ignorados: { total: number; motivos: string[] };
  notas: number;
}

export interface UltimaRodada {
  rodada_id: number;
  inicio: string;
  fim: string | null;
  resultado: string | null;
  ultimo_lote: { id: number; perfil: string; itens: number; registrados: number | null; erro: string | null; fim: string | null } | null;
}

export interface LoteAtual { tag: string; perfil: string; itens: number; inicio: string }

export interface ResumoSistema {
  tag: string;
  removido_em: string | null;
  selo: { estado: EstadoSelo; texto: string };
  sinais: Sinais;
  origens: Origem[];
  ultima_rodada: UltimaRodada | null;
  lote_atual: LoteAtual | null;
  pull_pendente: number | null;
}

export interface ListaSistemas {
  sistemas: ResumoSistema[];
  por_estado: Partial<Record<EstadoSelo, number>>;
  proxima_rodada: string | null;
  rodada_em_curso: { id: number; inicio: string; modo: string } | null;
  // Curador em paralelo (DV-606): o que cada trabalhador está fazendo agora.
  rodadas_em_curso?: { id: number; inicio: string; modo: string; tags: string[]; trabalhador: string | null }[];
  trabalhadores?: { id: string; tag: string | null; desde: string | null; motivo: string | null }[];
}

export interface Pull {
  id: number;
  pedido_em: string;
  pedido_por: string;
  atendido_em: string | null;
  estado: "pedido" | "concluido";
  erro: string | null;
  itens: Record<string, number>;
  ignorados: number;
  mascarados: number;
  origens: Record<string, { de: string | null; para: string | null; nada_novo?: boolean; aviso?: string | null; erro?: string | null }>;
}

export interface Ignorados {
  total: number;
  mascarados: number;
  por_motivo: { motivo: string; quantos: number; arquivos: { caminho: string; motivo: string; origem?: string }[] }[];
}

export interface Sistema extends ResumoSistema {
  cadastro: { por: string; em: string };
  ultimo_pull: Pull | null;
  modo?: "literal" | "documentado" | null; // Vault System: vault criado por envio (vs sync)
  notas_do_agente?: number; // notas que o agente local preparou e entraram curadas
  curadoria?: Curadoria;
}

export interface ItemFila {
  id: number;
  acao: "adicionado" | "modificado" | "removido";
  caminho: string;
  origem: string;
  perfil: string;
  commit: string;
  desde: string;
  tentativas: number;
  parado: boolean;
  parado_em: string | null;
  erro: string | null;
  motivo: string | null;
  url: string | null;
}

export interface Rodada {
  id: number;
  modo: string;
  inicio: string;
  fim: string | null;
  resultado: string | null;
  lotes: number;
  itens: number;
  registrados: number;
  com_erro: number;
  avisos: number;
}

export interface Lote {
  id: number;
  perfil: string;
  itens: number;
  registrados: number | null;
  inicio: string;
  fim: string | null;
  codigo: number | null;
  erro: string | null;
}

export interface Aviso { id: number; tipo: string; nota: string | null; detalhe: string; em: string }

export interface DetalheRodada { id: number; modo: string; inicio: string; fim: string | null; resultado: string | null; lotes: Lote[]; avisos: Aviso[] }

export interface Problema { tipo: string; nota: string | null; detalhe: string; desde: string }

export interface Verificacao {
  rodou_em: string | null;
  commits: Record<string, string | null>;
  total: number | null;
  por_tipo: Record<string, number>;
  estado: "nunca_verificado" | "limpa" | "com_problema";
  problemas: Problema[];
}

export interface NotaResumo { chave: string; pasta: string; titulo: string | null; tipo_nota: string | null; atualizado_em: string | null; problemas: number }

export interface Nota {
  chave: string;
  pasta: string;
  titulo: string | null;
  tipo_nota: string | null;
  commit_origem: string | null;
  criado_em: string | null;
  atualizado_em: string | null;
  conteudo: string;
  origens: { ref: string; origem: string; caminho: string; url: string | null }[];
  problemas: { tipo: string; detalhe: string; desde: string }[];
  itens_na_fila: { id: number; acao: string; caminho: string; origem: string }[];
}

export interface Credencial {
  nome: string;
  ler: string[];
  escrever: string[];
  criado_em: string;
  criado_por: string | null;
  revogada_em: string | null;
  usado_em: string | null;
  estado: "ativa" | "revogada";
  workspace?: boolean; // token de conexão da CLI (vs login): todos os vaults, cria vault no vs sync
}
