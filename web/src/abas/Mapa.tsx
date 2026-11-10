import { KeyboardEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Sistema } from "../api";
import { Badge, Carregando, Falha, Vazio } from "../componentes";
import { useDados } from "../dados";
import { plural } from "../formato";
import { Icone } from "../icones";
import GrafoForcas from "./GrafoForcas";
import InfraMapa, { GrafoInfra } from "./InfraMapa";

// Mapa de relações: a vizinhança de um nó por vez (o foco), só com
// relações do índice das notas (vault_system/mapa.py). Clicar seleciona e
// destaca; "Explorar a partir daqui" (ou Enter de novo, ou duplo clique) muda o
// foco e carrega a vizinhança dele. "Mais notas" aumenta o limite.

type TipoNo = "sistema" | "origem" | "pasta" | "nota";
type Relacao = "compõe" | "fundamenta" | "documenta" | "menciona";
type Sentido = "sai" | "entra" | "ambos";
interface NoMapa {
  id: string; tipo: TipoNo; rotulo: string; sub?: string; chave?: string; pasta?: string; notas?: number; ligacoes?: number;
  lado?: "esquerda" | "direita"; sentido?: Sentido;
}
interface Aresta { de: string; para: string; relacao: Relacao; n?: number }
interface RelacaoNota { chave: string; titulo: string; pasta: string; relacao: Relacao; sentido: Sentido }
interface Vizinhanca {
  foco: NoMapa; nos: NoMapa[]; arestas: Aresta[]; notas_vizinhas: number; notas_mostradas: number; limite: number;
  relacoes?: RelacaoNota[]; arquivos?: { origem: string; repo: string | null; caminhos: string[] }[];
  totais: { notas: number; pastas: Record<string, number>; relacoes: Record<"fundamenta" | "documenta" | "menciona", number> };
}

const W = 210, H = 50, COL = 290, GAP = 14, PASSO = 24;
const MUITOS = 6; // acima disso, cada lado vira duas colunas intercaladas (as linhas passam nos vãos)
const ENTRE = W + 50; // distância entre as duas colunas de um lado
const TIPO: Record<TipoNo, string> = { sistema: "Vault", origem: "Fonte", pasta: "Pasta", nota: "Nota" };
const FILTROS = { todos: "Todos", fontes: "Fontes", notas: "Notas" } as const;
type Filtro = keyof typeof FILTROS;
const VISIVEL: Record<Filtro, TipoNo[]> = { todos: ["sistema", "origem", "pasta", "nota"], fontes: ["sistema", "origem"], notas: ["pasta", "nota"] };
const MAIS = "__mais";
const PASTA: Record<string, string> = { documentos: "Documentos", assuntos: "Assuntos", modulos: "Módulos", regras: "Regras", integracoes: "Integrações", apis: "APIs", dados: "Dados", referencia: "Referência", guias: "Guias", infra: "Infraestrutura" };
const num = (n: number) => n.toLocaleString("pt-BR");
const curto = (t: string, n = 27) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

interface Posicionado extends NoMapa { x: number; y: number }

/** Foco no centro; de onde vem à esquerda, o que tem ou cita à direita. Com
 *  muitos vizinhos, duas colunas intercaladas: um nó em cada linha, alternando
 *  a coluna, e a linha até a coluna de fora passa no vão da de dentro. */
function posicionar(foco: NoMapa, nos: NoMapa[]): Posicionado[] {
  const saida: Posicionado[] = [{ ...foco, x: 0, y: 0 }];
  for (const lado of ["esquerda", "direita"] as const) {
    const lista = nos.filter((n) => n.lado === lado);
    const duas = lista.length > MUITOS;
    const passo = duas ? H / 2 + 12 : H + GAP;
    lista.forEach((n, i) => {
      const x = COL + (duas && i % 2 ? ENTRE : 0);
      saida.push({ ...n, x: (lado === "esquerda" ? -1 : 1) * x, y: (i - (lista.length - 1) / 2) * passo });
    });
  }
  return saida;
}

/** Toda aresta liga o foco (no centro) a um vizinho: sai do lado do foco, chega
 *  à altura do vizinho antes da primeira coluna e segue reto até ele. */
function caminho(de: Posicionado, para: Posicionado, foco: string) {
  const outro = de.id === foco ? para : de;
  const dir = outro.x >= 0 ? 1 : -1;
  const x0 = (dir * W) / 2, xj = dir * (COL - W / 2 - 16), xe = outro.x - (dir * W) / 2;
  const c = (xj - x0) / 2;
  const ida = `M${x0},0 C${x0 + c},0 ${xj - c},${outro.y} ${xj},${outro.y} L${xe},${outro.y}`;
  const volta = `M${xe},${outro.y} L${xj},${outro.y} C${xj - c},${outro.y} ${x0 + c},0 ${x0},0`;
  return { d: de.id === foco ? ida : volta, mx: (x0 + xj) / 2, my: outro.y / 2 };
}

const FRASE: Record<string, (n: number) => string> = {
  "documenta:entra": (n) => `Documentada por ${plural(n, "documento", "documentos")}`,
  "documenta:sai": (n) => `Documenta ${plural(n, "assunto", "assuntos")}`,
  "menciona:sai": (n) => `Menciona ${plural(n, "nota", "notas")}`,
  "menciona:entra": (n) => `Mencionada por ${plural(n, "nota", "notas")}`,
  "menciona:ambos": (n) => `Menção nos dois sentidos com ${plural(n, "nota", "notas")}`,
};

export default function Mapa({ s }: { s: Sistema }) {
  const [params, setParams] = useSearchParams();
  const foco = params.get("foco") || "sistema";
  const grafo = params.get("vista") === "grafo";
  const verInfra = params.get("vista") === "infra";
  const infra = useDados<GrafoInfra>(`/sistemas/${s.tag}/infra`); // containers lidos dos arquivos
  const temInfra = (infra.dados?.servicos.length ?? 0) > 0;
  const [limite, setLimite] = useState(PASSO);
  const [trilha, setTrilha] = useState<{ id: string; rotulo: string }[]>([]);
  const [sel, setSel] = useState<string>(foco);
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const { dados: v, erro, carregando, recarregar } = useDados<Vizinhanca>(
    `/sistemas/${s.tag}/mapa?foco=${encodeURIComponent(foco)}&limite=${limite}`, undefined, true);

  useEffect(() => setSel(foco), [foco]);

  function explorar(no: { id: string; rotulo: string }) {
    if (no.id === foco) return;
    const i = trilha.findIndex((t) => t.id === no.id);
    setTrilha(i >= 0 ? trilha.slice(0, i) : [...trilha, { id: foco, rotulo: v?.foco.rotulo ?? foco }]);
    setLimite(PASSO);
    setParams({ foco: no.id }, { replace: false });
  }

  if (!v && carregando) return <Carregando texto="Montando o mapa…" />;
  if (!v) return <Falha erro={erro ?? "Não deu para montar o mapa."} tentar={recarregar} />;
  if (v.totais.notas === 0) {
    return (
      <section className="panel">
        <Vazio titulo="Mapa sem relações ainda"
          acao={<Link className="btn" to={`/sistemas/${s.tag}/processamento`}>Ver o processamento</Link>}>
          O mapa é montado das notas do vault. Ele aparece depois do primeiro pull que gerar notas.
        </Vazio>
      </section>
    );
  }
  return (
    <section className="mapa-aba">
      <div className="eyebrow">Conhecimento em relação</div>
      <div className="mapa-topo">
        <div>
          <h2>Explore o contexto, siga a origem.</h2>
          <p className="muted">Selecione um elemento para destacar as relações e ver de onde ele vem. Explore a partir dele para abrir a vizinhança.</p>
        </div>
      </div>
      <div className="segmentos mapa-vistas" role="group" aria-label="Visão do mapa">
        <button type="button" className={grafo || verInfra ? "" : "ativo"} aria-pressed={!grafo && !verInfra} onClick={() => setParams({ foco })}>Colunas</button>
        <button type="button" className={grafo ? "ativo" : ""} aria-pressed={grafo} onClick={() => setParams({ foco, vista: "grafo" })}>Grafo</button>
        {temInfra && (
          <button type="button" className={verInfra ? "ativo" : ""} aria-pressed={verInfra} onClick={() => setParams({ foco, vista: "infra" })}>Infraestrutura</button>
        )}
      </div>
      {verInfra ? (
        infra.dados ? <InfraMapa tag={s.tag} g={infra.dados} />
          : infra.erro ? <Falha erro={infra.erro} tentar={infra.recarregar} /> : <Carregando texto="Lendo os arquivos de container…" />
      ) : grafo ? (
        <GrafoForcas tag={s.tag} emColunas={(chave) => {
          setTrilha([]);
          setLimite(PASSO);
          setParams({ foco: `nota:${chave}` });
        }} />
      ) : (<>
      <nav className="mapa-trilha" aria-label="Caminho no mapa">
        {trilha.map((t) => (
          <span key={t.id}><button type="button" className="textbtn" onClick={() => explorar(t)}>{t.rotulo}</button><Icone nome="chevron" /></span>
        ))}
        <b aria-current="location">{v.foco.rotulo}</b>
      </nav>
      <Grafo v={v} sel={sel} selecionar={setSel} explorar={explorar} filtro={filtro} setFiltro={setFiltro}
        mais={() => setLimite(limite + PASSO)} carregando={carregando} />
      <Detalhes tag={s.tag} v={v} sel={sel} selecionar={setSel} explorar={explorar} />
      <Rodape v={v} filtro={filtro} />
      </>)}
    </section>
  );
}

function Grafo({ v, sel, selecionar, explorar, filtro, setFiltro, mais, carregando }: {
  v: Vizinhanca; sel: string; selecionar: (id: string) => void; explorar: (n: NoMapa) => void; filtro: Filtro;
  setFiltro: (f: Filtro) => void; mais: () => void; carregando: boolean;
}) {
  const caixa = useRef<HTMLDivElement>(null);
  const [tam, setTam] = useState({ w: 900, h: 520 });
  const [vista, setVista] = useState({ x: 0, y: 0, k: 1 });
  const arrasto = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  const visiveis = VISIVEL[filtro];
  const nos = useMemo(() => {
    const lista = v.nos.filter((n) => visiveis.includes(n.tipo));
    const faltam = v.notas_vizinhas - v.notas_mostradas;
    if (faltam > 0 && visiveis.includes("nota")) {
      lista.push({ id: MAIS, tipo: "nota", rotulo: `Mais ${plural(Math.min(faltam, PASSO), "nota", "notas")}`, sub: `faltam ${num(faltam)}`, lado: "direita" });
    }
    return posicionar(v.foco, lista);
  }, [v, filtro]); // eslint-disable-line react-hooks/exhaustive-deps
  const pos = useMemo(() => new Map(nos.map((n) => [n.id, n])), [nos]);
  const arestas = v.arestas.filter((a) => pos.has(a.de) && pos.has(a.para));
  const vizinhosSel = new Set(arestas.flatMap((a) => (a.de === sel || a.para === sel ? [a.de, a.para] : [])));

  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setTam({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  function centralizar() {
    const xs = nos.map((n) => n.x), ys = nos.map((n) => n.y);
    const bw = Math.max(...xs) - Math.min(...xs) + W + 60, bh = Math.max(...ys) - Math.min(...ys) + H + 60;
    const k = Math.min(1.2, tam.w / bw, tam.h / bh);
    setVista({ x: -((Math.max(...xs) + Math.min(...xs)) / 2) * k, y: -((Math.max(...ys) + Math.min(...ys)) / 2) * k, k });
  }
  useEffect(centralizar, [nos, tam.w, tam.h]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoom = (f: number) => setVista((z) => ({ x: z.x * f, y: z.y * f, k: Math.min(3, Math.max(0.2, z.k * f)) }));

  function tecla(e: KeyboardEvent) {
    if ((e.target as Element).closest("g.mapa-no")) return;
    const passo = 60;
    const acoes: Record<string, () => void> = {
      "+": () => zoom(1.2), "=": () => zoom(1.2), "-": () => zoom(1 / 1.2), "0": centralizar,
      ArrowLeft: () => setVista((z) => ({ ...z, x: z.x + passo })), ArrowRight: () => setVista((z) => ({ ...z, x: z.x - passo })),
      ArrowUp: () => setVista((z) => ({ ...z, y: z.y + passo })), ArrowDown: () => setVista((z) => ({ ...z, y: z.y - passo })),
    };
    if (acoes[e.key]) {
      e.preventDefault();
      acoes[e.key]();
    }
  }
  function apertar(e: PointerEvent<SVGSVGElement>) {
    if ((e.target as Element).closest("g.mapa-no")) return;
    arrasto.current = { x: e.clientX, y: e.clientY, vx: vista.x, vy: vista.y };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  }
  function mover(e: PointerEvent<SVGSVGElement>) {
    const a = arrasto.current;
    if (a) setVista((z) => ({ ...z, x: a.vx + e.clientX - a.x, y: a.vy + e.clientY - a.y }));
  }

  function ativar(n: Posicionado, explorarJa: boolean) {
    if (n.id === MAIS) return mais();
    if (explorarJa || sel === n.id) explorar(n);
    else selecionar(n.id);
  }

  return (
    <div className="panel mapa-quadro">
      <div className="mapa-barra">
        <div className="segmentos" role="group" aria-label="Filtrar o mapa">
          {(Object.keys(FILTROS) as Filtro[]).map((f) => (
            <button key={f} type="button" className={filtro === f ? "ativo" : ""} aria-pressed={filtro === f} onClick={() => setFiltro(f)}>{FILTROS[f]}</button>
          ))}
        </div>
        {carregando && <small className="muted">Atualizando…</small>}
        <div className="mapa-zoom">
          <button type="button" className="btn" aria-label="Reduzir" onClick={() => zoom(1 / 1.2)}>−</button>
          <button type="button" className="btn" aria-label="Ampliar" onClick={() => zoom(1.2)}>+</button>
          <button type="button" className="btn" onClick={centralizar}>Centralizar</button>
        </div>
      </div>
      <div className="mapa-tela" ref={caixa} tabIndex={0} onKeyDown={tecla}
        aria-label="Mapa de relações. Setas movem, + e − ampliam, 0 centraliza. Tab percorre os elementos.">
        <svg width={tam.w} height={tam.h} onPointerDown={apertar} onPointerMove={mover} onPointerUp={() => (arrasto.current = null)}
          role="group" aria-label={`Vizinhança de ${v.foco.rotulo}: ${plural(nos.length - 1, "elemento", "elementos")}`}>
          <defs>
            {(["compõe", "fundamenta", "documenta", "menciona"] as Relacao[]).map((r) => (
              <marker key={r} id={`seta-${r}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" className={`seta ${r}`} />
              </marker>
            ))}
          </defs>
          <g transform={`translate(${tam.w / 2 + vista.x},${tam.h / 2 + vista.y}) scale(${vista.k})`}>
            {arestas.map((a, i) => {
              const de = pos.get(a.de)!, para = pos.get(a.para)!;
              const { d, mx, my } = caminho(de, para, v.foco.id);
              const ativa = a.de === sel || a.para === sel;
              // Rótulo só para o elemento selecionado (com o foco selecionado, todos se sobreporiam no centro).
              const rotulo = ativa && sel !== v.foco.id;
              return (
                <g key={i} className={`mapa-aresta ${a.relacao}${ativa ? " ativa" : ""}`}>
                  <path d={d} markerEnd={`url(#seta-${a.relacao})`}><title>{`${de.rotulo} ${a.relacao} ${para.rotulo}${a.n ? ` (${num(a.n)})` : ""}`}</title></path>
                  {rotulo && <text x={mx} y={my - 5} textAnchor="middle">{a.relacao}{a.n ? ` · ${num(a.n)}` : ""}</text>}
                </g>
              );
            })}
            {nos.map((n) => {
              const apagado = sel !== v.foco.id && n.id !== sel && !vizinhosSel.has(n.id) && n.id !== MAIS;
              return (
                <g key={n.id} className={`mapa-no ${n.tipo}${n.id === sel ? " sel" : ""}${n.id === v.foco.id ? " foco" : ""}${apagado ? " apagado" : ""}${n.id === MAIS ? " mais" : ""}`}
                  transform={`translate(${n.x - W / 2},${n.y - H / 2})`} tabIndex={0} role="button"
                  aria-pressed={n.id === MAIS ? undefined : n.id === sel}
                  aria-label={n.id === MAIS ? `${n.rotulo}, ${n.sub}` : `${TIPO[n.tipo]}: ${n.rotulo}${n.sub ? `, ${n.sub}` : ""}${n.id === sel ? ". Selecionado; Enter explora a partir dele" : ""}`}
                  onClick={() => ativar(n, false)} onDoubleClick={() => ativar(n, true)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      ativar(n, false);
                    }
                  }}>
                  <title>{n.rotulo}</title>
                  <rect width={W} height={H} rx={8} />
                  <circle cx={14} cy={15} r={2.5} />
                  <text x={22} y={18} className="tipo">{n.id === MAIS ? "expandir" : TIPO[n.tipo]}{n.sub ? ` · ${n.sub}` : ""}</text>
                  <text x={10} y={37} className="rotulo">{curto(n.rotulo)}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <p className="mapa-dica">Arraste o fundo para mover · +/− ampliam · Tab e Enter selecionam; Enter de novo (ou duplo clique) explora a partir do elemento</p>
      <ul className="mapa-legenda" aria-label="Legenda das relações">
        <li className="compõe">compõe</li>
        <li className="fundamenta">fundamenta (arquivo de origem → nota)</li>
        <li className="documenta">documenta (documento → assunto)</li>
        <li className="menciona">menciona (link entre notas; citação, não dependência)</li>
      </ul>
    </div>
  );
}

function resumoDe(conteudo: string) {
  const corpo = conteudo.replace(/^---\n[\s\S]*?\n---\n?/, "");
  const par = corpo.split(/\n\s*\n/).map((p) => p.trim()).find((p) => p && !p.startsWith("#") && !p.startsWith("|") && !p.startsWith("-"));
  const texto = (par ?? "").replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2").replace(/\[\[([^\]]+)\]\]/g, (_, a: string) => a.split("/").pop()!).replace(/[*_`]/g, "");
  return texto.length > 320 ? texto.slice(0, 319) + "…" : texto;
}

function Detalhes({ tag, v, sel, selecionar, explorar }: {
  tag: string; v: Vizinhanca; sel: string; selecionar: (id: string) => void; explorar: (n: NoMapa) => void;
}) {
  const no = sel === v.foco.id ? v.foco : v.nos.find((n) => n.id === sel) ?? v.foco;
  const nota = useDados<{ conteudo: string; problemas: unknown[] }>(no.tipo === "nota" && no.chave ? `/sistemas/${tag}/notas/${no.chave}` : null);
  const comFoco = v.arestas.filter((a) => (a.de === no.id && a.para === v.foco.id) || (a.para === no.id && a.de === v.foco.id));
  const ehFoco = no.id === v.foco.id;

  return (
    <div className="panel mapa-detalhes" aria-live="polite">
      <div className="mapa-detalhes-topo">
        <div>
          <div className="eyebrow">{TIPO[no.tipo]} {ehFoco ? "em foco" : "selecionada"}</div>
          <h3>{no.rotulo}</h3>
          {no.sub && <small className="muted">{no.sub}</small>}
          {no.tipo === "nota" && nota.dados && (
            <>
              <div className="mapa-verif">
                {nota.dados.problemas.length
                  ? <Badge tipo="warn">{plural(nota.dados.problemas.length, "problema", "problemas")} na verificação</Badge>
                  : <Badge>Sem problemas na verificação</Badge>}
              </div>
              <p>{resumoDe(nota.dados.conteudo)}</p>
            </>
          )}
          {!ehFoco && comFoco.length > 0 && (
            <div className="mapa-chips">
              {comFoco.map((a, i) => (
                <span key={i} className="chip">{a.de === no.id ? `${a.relacao} → ${v.foco.rotulo}` : `${v.foco.rotulo} ${a.relacao} →`}{a.n ? ` · ${num(a.n)}` : ""}</span>
              ))}
            </div>
          )}
        </div>
        <div className="mapa-acoes">
          {no.tipo === "nota" && no.chave && (
            <Link className="btn primary" to={`/sistemas/${tag}/conhecimento?nota=${encodeURIComponent(no.chave)}`}><Icone nome="file" />Abrir nota</Link>
          )}
          {!ehFoco && <button type="button" className="btn" onClick={() => explorar(no)}><Icone nome="arrow" />Explorar a partir daqui</button>}
          <Link className="btn" to={`/conversas?vault=${encodeURIComponent(tag)}${no.tipo === "nota" && no.chave ? `&nota=${encodeURIComponent(no.chave)}` : ""}`}
            title="Abre uma conversa com o Vault-I sobre isso">
            <Icone nome="spark" />Perguntar sobre isso
          </Link>
        </div>
      </div>
      {ehFoco && <ListaRelacoes v={v} selecionar={selecionar} explorar={explorar} />}
    </div>
  );
}

/** Alternativa em texto ao desenho: tudo o que se liga ao foco, inclusive o que não coube no mapa. */
function ListaRelacoes({ v, selecionar, explorar }: { v: Vizinhanca; selecionar: (id: string) => void; explorar: (n: NoMapa) => void }) {
  const botao = (n: NoMapa) => (
    <button type="button" className="textbtn" onClick={() => (v.nos.some((x) => x.id === n.id) ? selecionar(n.id) : explorar(n))}>{n.rotulo}</button>
  );
  const grupos: { titulo: string; itens: NoMapa[] }[] = [];
  const fora = v.nos.filter((n) => n.tipo !== "nota");
  if (fora.length) grupos.push({ titulo: v.foco.tipo === "nota" ? "Pasta e fontes" : "Ligado a", itens: fora });
  if (v.relacoes) {
    const por = new Map<string, RelacaoNota[]>();
    for (const r of v.relacoes) por.set(`${r.relacao}:${r.sentido}`, [...(por.get(`${r.relacao}:${r.sentido}`) ?? []), r]);
    for (const [k, rs] of por) {
      grupos.push({ titulo: FRASE[k]?.(rs.length) ?? k, itens: rs.map((r) => ({ id: `nota:${r.chave}`, tipo: "nota", rotulo: r.titulo, sub: PASTA[r.pasta] ?? r.pasta })) });
    }
  } else {
    const notas = v.nos.filter((n) => n.tipo === "nota");
    if (notas.length) grupos.push({ titulo: `Notas (${num(v.notas_mostradas)} de ${num(v.notas_vizinhas)}, as mais ligadas primeiro)`, itens: notas });
  }
  return (
    <div className="mapa-lista">
      <h4>Relações de {v.foco.rotulo}</h4>
      {grupos.map((g) => (
        <details key={g.titulo} open={g.itens.length <= 8}>
          <summary>{g.titulo}</summary>
          <ul>{g.itens.map((n) => <li key={n.id}>{botao(n)}{n.sub && <small className="muted"> · {n.sub}</small>}</li>)}</ul>
        </details>
      ))}
      {v.arquivos && v.arquivos.length > 0 && (
        <details>
          <summary>Fundamentada por {plural(v.arquivos.reduce((t, a) => t + a.caminhos.length, 0), "arquivo de origem", "arquivos de origem")}</summary>
          <ul className="mono">{v.arquivos.flatMap((a) => a.caminhos.map((c) => <li key={a.origem + c}>{a.repo ?? a.origem}: {c}</li>))}</ul>
        </details>
      )}
    </div>
  );
}

function Rodape({ v, filtro }: { v: Vizinhanca; filtro: Filtro }) {
  const notas = VISIVEL[filtro].includes("nota") ? v.nos.filter((n) => n.tipo === "nota").length + (v.foco.tipo === "nota" ? 1 : 0) : 0;
  const r = v.totais.relacoes;
  return (
    <p className="mapa-rodape">
      Mostrando <b>{num(notas)}</b> de <b>{num(v.totais.notas)}</b> notas · filtro: {FILTROS[filtro]}. No índice: {num(r.fundamenta)} fundamenta ·{" "}
      {num(r.documenta)} documenta · {num(r.menciona)} menciona. Só relações que existem nas notas; nada é inferido.
    </p>
  );
}
