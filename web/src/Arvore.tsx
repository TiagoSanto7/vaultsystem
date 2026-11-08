import { useEffect, useMemo, useState } from "react";
import { api, Leitura } from "./api";
import { Carregando } from "./componentes";
import { plural } from "./formato";
import { Icone } from "./icones";

// Árvore de pastas de uma origem do GitHub App: a pessoa classifica
// cada pasta como documentos, código ou ignorar; a subpasta segue a de cima, a
// menos que tenha a própria classificação. A API transforma isso em leituras.
// A regra dos .md (chave MD) manda todo .md para documentos, menos nas pastas
// ignoradas e os classificados um a um (vault_system/arvore.py, destino_de).
// Referência: a pasta é copiada como está, sem LLM; com explicação, o curador
// também escreve guias (o código deles vem só por trecho). A regra dos .md não mexe nelas.

export type Classe = "documentos" | "referencia-explicada" | "referencia" | "codigo-literal" | "codigo" | "ignorar";
export type Classificacao = Record<string, Classe>;
export interface ArquivoArvore { caminho: string; tamanho: number | null; fixo: string | null }
export interface ResultadoArvore {
  id: number; estado: "pedido" | "pronto" | "erro"; repo: string; ramo: string;
  commit?: string; truncado?: boolean; arquivos?: ArquivoArvore[]; sugestao?: Classificacao; sugestao_referencia?: Classificacao; erro?: string;
}

export const MD = "*.md";

export const ROTULO: Record<Classe, string> = {
  documentos: "documentos", "referencia-explicada": "referência + explicação", referencia: "referência (só literal)",
  "codigo-literal": "código + cópia literal", codigo: "código (sem cópia)", ignorar: "ignorar",
};
const FORA_DA_REGRA_MD: Classe[] = ["ignorar", "referencia", "referencia-explicada"];

interface No { nome: string; caminho: string; pastas: No[]; arquivos: ArquivoArvore[]; total: number; fixos: number }

function montar(arquivos: ArquivoArvore[]): No {
  const raiz: No = { nome: "", caminho: "", pastas: [], arquivos: [], total: 0, fixos: 0 };
  const indice = new Map<string, No>([["", raiz]]);
  for (const a of arquivos) {
    const partes = a.caminho.split("/");
    let no = raiz;
    const subir = [raiz];
    for (let i = 0; i < partes.length - 1; i++) {
      const caminho = partes.slice(0, i + 1).join("/");
      let filho = indice.get(caminho);
      if (!filho) {
        filho = { nome: partes[i], caminho, pastas: [], arquivos: [], total: 0, fixos: 0 };
        indice.set(caminho, filho);
        no.pastas.push(filho);
      }
      no = filho;
      subir.push(no);
    }
    no.arquivos.push(a);
    for (const n of subir) a.fixo ? n.fixos++ : n.total++;
  }
  const ordenar = (n: No) => {
    n.pastas.sort((x, y) => x.nome.localeCompare(y.nome));
    n.arquivos.sort((x, y) => x.caminho.localeCompare(y.caminho));
    n.pastas.forEach(ordenar);
  };
  ordenar(raiz);
  return raiz;
}

const pai = (c: string) => (c.includes("/") ? c.slice(0, c.lastIndexOf("/")) : "");

export function classeDe(caminho: string, c: Classificacao): Classe {
  let atual = caminho;
  for (;;) {
    if (atual in c) return c[atual];
    if (atual === "") return "ignorar";
    atual = pai(atual);
  }
}

/** Destino do arquivo sem classificação própria: o da pasta, ou documentos pela regra dos .md. */
function herdado(caminho: string, c: Classificacao): Classe {
  const daPasta = classeDe(pai(caminho), c);
  return c[MD] === "documentos" && caminho.endsWith(".md") && !FORA_DA_REGRA_MD.includes(daPasta) ? "documentos" : daPasta;
}

export function destinoDe(caminho: string, c: Classificacao): Classe {
  return caminho in c ? c[caminho] : herdado(caminho, c);
}

export function totais(arquivos: ArquivoArvore[], c: Classificacao) {
  const t = { documentos: 0, "referencia-explicada": 0, referencia: 0, "codigo-literal": 0, codigo: 0, ignorar: 0, fixo: 0 };
  for (const a of arquivos) a.fixo ? t.fixo++ : t[destinoDe(a.caminho, c)]++;
  return t;
}

/** Pede a árvore e acompanha até o curador responder (poucos segundos). */
const DEMORA = 20000; // ms: o atendente responde em poucos segundos; mais que isso, ele deve estar parado

export function useArvore(id: number | null) {
  const [r, setR] = useState<ResultadoArvore | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [demorando, setDemorando] = useState(false);
  useEffect(() => {
    if (id === null) return;
    let vivo = true;
    let espera: number | undefined;
    setDemorando(false);
    const alarme = window.setTimeout(() => vivo && setDemorando(true), DEMORA);
    const buscar = async () => {
      try {
        const d = await api<ResultadoArvore>(`/arvores/${id}`);
        if (!vivo) return;
        setR(d);
        if (d.estado === "pedido") espera = window.setTimeout(buscar, 1500);
      } catch (e) {
        if (vivo) setErro((e as Error).message);
      }
    };
    buscar();
    return () => {
      vivo = false;
      window.clearTimeout(espera);
      window.clearTimeout(alarme);
    };
  }, [id]);
  return { r, erro, demorando: demorando && (!r || r.estado === "pedido") };
}

export function ClassificarArvore({ r, valor, mudar }: { r: ResultadoArvore; valor: Classificacao; mudar: (c: Classificacao) => void }) {
  const arquivos = r.arquivos ?? [];
  const raiz = useMemo(() => montar(arquivos), [arquivos]);
  const [abertas, setAbertas] = useState<Set<string>>(() => new Set([""]));
  const t = totais(arquivos, valor);

  // Arquivo herda da pasta ou da regra dos .md; pasta, da pasta de cima.
  const padrao = (caminho: string, arquivo: boolean) => (arquivo ? herdado(caminho, valor) : classeDe(pai(caminho), valor));

  function escolher(caminho: string, v: string, arquivo: boolean) {
    const novo = { ...valor };
    if (v === "" || (caminho !== "" && v === padrao(caminho, arquivo))) delete novo[caminho];
    else novo[caminho] = v as Classe;
    mudar(novo);
  }
  const alternar = (c: string) => {
    const n = new Set(abertas);
    n.has(c) ? n.delete(c) : n.add(c);
    setAbertas(n);
  };

  function Seletor({ caminho, rotulo, arquivo = false }: { caminho: string; rotulo: string; arquivo?: boolean }) {
    const proprio = valor[caminho];
    const pelaRegra = arquivo && herdado(caminho, valor) !== classeDe(pai(caminho), valor);
    return (
      <select aria-label={`Destino de ${rotulo}`} value={proprio ?? ""} className={`destino ${arquivo ? destinoDe(caminho, valor) : classeDe(caminho, valor)}`}
        onChange={(e) => escolher(caminho, e.target.value, arquivo)}>
        {caminho !== "" && <option value="">{pelaRegra ? "regra dos .md" : "segue a pasta"} ({ROTULO[padrao(caminho, arquivo)]})</option>}
        {(Object.keys(ROTULO) as Classe[]).map((k) => <option key={k} value={k}>{ROTULO[k]}</option>)}
      </select>
    );
  }

  function Linhas({ no, nivel }: { no: No; nivel: number }) {
    const aberta = abertas.has(no.caminho);
    const soFixos = no.total === 0;
    return (
      <>
        <li className="arvore-linha" style={{ paddingLeft: 12 + nivel * 20 }}>
          <button type="button" className="arvore-nome" onClick={() => alternar(no.caminho)} aria-expanded={aberta}>
            <span className="seta" aria-hidden>{aberta ? "▾" : "▸"}</span>
            <b>{no.caminho === "" ? `${r.repo.replace("https://github.com/", "")} · ${r.ramo}` : `${no.nome}/`}</b>
          </button>
          <small className="muted">{plural(no.total, "arquivo", "arquivos")}{no.fixos ? ` · ${no.fixos} fora sempre` : ""}</small>
          {soFixos ? <small className="muted fixo"><Icone nome="lock" />fica fora</small> : <Seletor caminho={no.caminho} rotulo={no.caminho || "raiz"} />}
        </li>
        {aberta && no.pastas.map((p) => <Linhas key={p.caminho} no={p} nivel={nivel + 1} />)}
        {aberta && no.arquivos.map((a) => (
          <li key={a.caminho} className="arvore-linha arquivo" style={{ paddingLeft: 12 + (nivel + 1) * 20 + 16 }}>
            <span className="mono">{a.caminho.split("/").pop()}</span>
            <span />
            {a.fixo ? <small className="muted fixo"><Icone nome="lock" />fica fora: {a.fixo}</small> : <Seletor caminho={a.caminho} rotulo={a.caminho} arquivo />}
          </li>
        ))}
      </>
    );
  }

  return (
    <div>
      {r.truncado && (
        <div className="banner warn" role="status"><Icone nome="alert" /><div>O repositório é grande demais e o GitHub mandou só parte da árvore. Classifique as pastas que aparecem; o resto segue a raiz.</div></div>
      )}
      <label className="arvore-regra">
        <input type="checkbox" checked={valor[MD] === "documentos"}
          onChange={(e) => {
            const { [MD]: _, ...resto } = valor;
            mudar(e.target.checked ? { ...resto, [MD]: "documentos" } : resto);
          }} />
        <span>
          <b>Todo arquivo .md vai para documentos</b>, menos nas pastas ignoradas e nas de referência. Vale também para .md novo numa pasta de
          código (README, spec). Um .md com destino próprio na árvore segue o destino dele.
        </span>
      </label>
      <ul className="arvore" aria-label={`Pastas de ${r.repo}`}>
        <Linhas no={raiz} nivel={0} />
      </ul>
      <p className="arvore-resumo" aria-live="polite">
        {t["referencia-explicada"] ? <><b>{t["referencia-explicada"]}</b> copiados como estão e explicados em guias · </> : null}
        {t.referencia ? <><b>{t.referencia}</b> só copiados como estão · </> : null}
        {t["codigo-literal"] ? <><b>{t["codigo-literal"]}</b> para código, com cópia literal · </> : null}
        <b>{t.documentos}</b> para documentos · {t.codigo ? <><b>{t.codigo}</b> para código, sem cópia · </> : null}<b>{t.ignorar}</b> ignorados
        {t.fixo ? <> · <b>{t.fixo}</b> fora sempre (dependências, lockfiles, segredos, grandes demais)</> : null}
      </p>
    </div>
  );
}

export function CarregandoArvore({ id, aoCarregar, children }: { id: number; aoCarregar?: (r: ResultadoArvore) => void; children: (r: ResultadoArvore) => JSX.Element }) {
  const { r, erro, demorando } = useArvore(id);
  useEffect(() => {
    if (r?.estado === "pronto") aoCarregar?.(r);
  }, [r]); // eslint-disable-line react-hooks/exhaustive-deps
  if (erro) return <div className="banner erro" role="alert"><Icone nome="alert" /><div>{erro}</div></div>;
  if (demorando) {
    return (
      <div className="banner warn" role="status">
        <Icone nome="alert" />
        <div>
          O curador não respondeu em {DEMORA / 1000} s. Normalmente leva poucos segundos: o atendente do curador deve estar
          parado. Peça ao administrador para reiniciar o curador (<code>docker compose restart curador</code>). A tela continua
          esperando e mostra as pastas assim que ele responder.
        </div>
      </div>
    );
  }
  if (!r || r.estado === "pedido") return <Carregando texto="Carregando as pastas pelo GitHub App…" />;
  if (r.estado === "erro") return <div className="banner erro" role="alert"><Icone nome="alert" /><div>Não deu para carregar as pastas: {r.erro}</div></div>;
  return children(r);
}

// --- editar uma origem pela árvore: o que muda de destino antes de salvar ---

export interface Mudanca { caminho: string; de: Classe; para: Classe }
/** o custo da reclassificação (vault_system/arvore.py, impacto). */
export interface Impacto { ao_curador: number; lotes: number; copia: number; saem: number; por_destino: Partial<Record<Classe, number>> }
export interface ResultadoLeituras {
  leituras: Leitura[]; totais: Record<Classe | "fixo", number>; mudancas?: Mudanca[]; total_mudancas?: number; impacto?: Impacto;
}

/** A partir daqui, salvar pede o nome do vault digitado. */
export const IMPACTO_GRANDE = 100;

/** Leituras (e, com a origem, as mudanças) da classificação, pedidas de novo a cada mudança, com 300 ms de folga. */
export function useLeituras(id: number | null, classificacao: Classificacao | undefined, origem?: { tag: string; origem: string }) {
  const [r, setR] = useState<ResultadoLeituras | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const chave = JSON.stringify([id, classificacao, origem]);
  useEffect(() => {
    setR(null);
    setErro(null);
    if (id === null || !classificacao) return;
    let vivo = true;
    const t = window.setTimeout(async () => {
      try {
        const d = await api<ResultadoLeituras>(`/arvores/${id}/leituras`, { metodo: "POST", corpo: { classificacao, ...origem } });
        if (vivo) setR(d);
      } catch (e) {
        if (vivo) setErro((e as Error).message);
      }
    }, 300);
    return () => {
      vivo = false;
      window.clearTimeout(t);
    };
  }, [chave]); // eslint-disable-line react-hooks/exhaustive-deps
  return { r, erro };
}

function frase(de: Classe, para: Classe, n: number) {
  const arq = plural(n, "arquivo", "arquivos");
  if (para === "ignorar") return <><b>{arq}</b> {n === 1 ? "sai" : "saem"} do vault <small className="muted">(hoje em {ROTULO[de]})</small></>;
  if (de === "ignorar") return <><b>{arq}</b> {n === 1 ? "entra" : "entram"} em {ROTULO[para]}</>;
  return <><b>{arq}</b> {n === 1 ? "passa" : "passam"} de {ROTULO[de]} para {ROTULO[para]}</>;
}

/** O que a classificação muda em relação a hoje, agrupado por destino de antes e de depois. */
export function PreviaMudancas({ r }: { r: ResultadoLeituras }) {
  const grupos = new Map<string, Mudanca[]>();
  for (const m of r.mudancas ?? []) {
    const k = `${m.de}>${m.para}`;
    grupos.set(k, [...(grupos.get(k) ?? []), m]);
  }
  const total = r.total_mudancas ?? 0;
  if (total === 0) {
    return <div className="banner section-gap" role="status"><Icone nome="check" /><div>Nenhum arquivo muda de destino em relação ao vault de hoje.</div></div>;
  }
  return (
    <div className="banner warn section-gap previa" role="status" aria-live="polite">
      <Icone nome="alert" />
      <div>
        <b>Ao salvar, {plural(total, "arquivo muda", "arquivos mudam")} de destino:</b>
        <ul>
          {[...grupos.entries()].map(([k, ms]) => (
            <li key={k}>
              <details>
                <summary>{frase(ms[0].de, ms[0].para, ms.length)}</summary>
                <ul className="mono">{ms.map((m) => <li key={m.caminho}>{m.caminho}</li>)}</ul>
              </details>
            </li>
          ))}
        </ul>
        {total > (r.mudancas?.length ?? 0) && <small>A lista mostra os primeiros {r.mudancas?.length}.</small>}
        {r.impacto && <ResumoImpacto i={r.impacto} />}
        <small style={{ display: "block", marginTop: 6 }}>
          O que sai é tirado do vault pelo código; o que entra em documentos, código ou referência + explicação é lido de novo pelo
          curador (LLM) no pull que já fica pedido. A cópia literal (referência e código + cópia) é feita pelo código, sem LLM;
          trocar entre código e código + cópia literal não volta ao curador.
        </small>
      </div>
    </div>
  );
}

function ResumoImpacto({ i }: { i: Impacto }) {
  const partes = (Object.entries(i.por_destino) as [Classe, number][]).map(([k, n]) => `${n.toLocaleString("pt-BR")} em ${ROTULO[k]}`);
  return (
    <p className="impacto" style={{ margin: "8px 0 0" }}>
      {i.ao_curador > 0
        ? <><b>Vai ao curador (LLM): {plural(i.ao_curador, "arquivo", "arquivos")}, cerca de {plural(i.lotes, "lote", "lotes")}</b> ({partes.join(", ")}).</>
        : <b>Nada vai ao curador (LLM).</b>}
      {i.copia > 0 && <> Cópia literal pelo código: {plural(i.copia, "arquivo", "arquivos")}.</>}
    </p>
  );
}

/** antes de salvar uma reclassificação que manda arquivos ao curador, o custo e um segundo clique; a partir
 * de IMPACTO_GRANDE arquivos, o nome do vault digitado. */
export function ConfirmarImpacto({ tag, i, voltar, enviando }: { tag: string; i: Impacto; voltar: () => void; enviando: boolean }) {
  const [digitado, setDigitado] = useState("");
  const grande = i.ao_curador >= IMPACTO_GRANDE;
  return (
    <div className={`banner ${grande ? "erro" : "warn"} section-gap`} role="alertdialog" aria-labelledby="confirmar-impacto">
      <Icone nome="alert" />
      <div style={{ flex: 1 }}>
        <b id="confirmar-impacto">Confirme o custo antes de salvar</b>
        <ResumoImpacto i={i} />
        <p style={{ margin: "8px 0 0" }}>
          Cada lote é uma chamada ao curador (LLM). As notas do vault mudam a cada rodada publicada, até a fila terminar:
          no meio do caminho, a API e o MCP servem parte do conteúdo novo e parte do antigo.
        </p>
        {grande && (
          <>
            <label htmlFor="confirma-impacto" style={{ display: "block", marginTop: 8 }}>
              São {plural(i.ao_curador, "arquivo", "arquivos")} para o curador. Para confirmar, digite o nome do vault ({tag}).
            </label>
            <input id="confirma-impacto" className="mono" value={digitado} onChange={(e) => setDigitado(e.target.value)} autoComplete="off" />
          </>
        )}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={voltar} disabled={enviando}>Voltar e revisar</button>
          <button className={`btn ${grande ? "danger" : "primary"}`} type="submit" disabled={enviando || (grande && digitado.trim() !== tag)}>
            <Icone nome="check" />{enviando ? "Salvando…" : `Confirmar: ${plural(i.lotes, "lote", "lotes")}`}
          </button>
        </div>
      </div>
    </div>
  );
}
