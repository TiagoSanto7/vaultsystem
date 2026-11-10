import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, Simulation, SimulationLinkDatum, SimulationNodeDatum } from "d3-force";
import { FormEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Carregando, Falha } from "../componentes";
import { useDados } from "../dados";
import { plural } from "../formato";
import { Icone } from "../icones";

// Visão de grafo do Mapa, no estilo do Graph view do Obsidian: todas
// as notas como pontos, as relações como molas, simulação de forças (d3-force)
// desenhada em canvas. Cor pelo perfil (documentos × código): 7 cores, uma por
// pasta, não se distinguem nem com visão normal; a pasta se destaca pela
// legenda. O acesso pelo teclado nó a nó fica na visão em colunas.

type Relacao = "documenta" | "menciona";
interface GrafoApi {
  nos: { chave: string; titulo: string; pasta: string; ligacoes: number }[];
  arestas: [number, number, Relacao][];
  totais: { notas: number };
}
interface No extends SimulationNodeDatum { i: number; chave: string; titulo: string; pasta: string; ligacoes: number; r: number }
interface Ar extends SimulationLinkDatum<No> { rel: Relacao }

const PASTA: Record<string, string> = { documentos: "Documentos", assuntos: "Assuntos", modulos: "Módulos", regras: "Regras", integracoes: "Integrações", apis: "APIs", dados: "Dados", referencia: "Referência", guias: "Guias", infra: "Infraestrutura" };
const DOCUMENTOS = new Set(["documentos", "assuntos", "referencia", "guias"]); // referência e guias com os documentos
const raio = (ligacoes: number) => 3 + Math.sqrt(ligacoes) * 1.1;
// Nota-ponte: liga quase tudo (no refeitorio, app--tests e app--services, com 230
// ligações cada) e puxa o código inteiro para um bolo só. Escondida por padrão.
const PONTE = 100;
const FORCAS = { repulsao: 90, distancia: 50, centro: 0.03 };

export default function GrafoForcas({ tag, emColunas }: { tag: string; emColunas: (chave: string) => void }) {
  const { dados, erro, carregando, recarregar } = useDados<GrafoApi>(`/sistemas/${tag}/mapa/grafo`);
  if (!dados && carregando) return <Carregando texto="Montando o grafo…" />;
  if (!dados) return <Falha erro={erro ?? "Não deu para montar o grafo."} tentar={recarregar} />;
  return <Desenho g={dados} tag={tag} emColunas={emColunas} />;
}

function Desenho({ g, tag, emColunas }: { g: GrafoApi; tag: string; emColunas: (chave: string) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const caixa = useRef<HTMLDivElement>(null);
  const [tam, setTam] = useState({ w: 900, h: 560 });
  const vista = useRef({ x: 0, y: 0, k: 1 });
  const [sel, setSel] = useState<number | null>(null);
  const [sobre, setSobre] = useState<number | null>(null);
  const [local, setLocal] = useState(false);
  const [prof, setProf] = useState(1);
  const [ocultas, setOcultas] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const [aviso, setAviso] = useState("");
  const [semPontes, setSemPontes] = useState(true);
  const [forcas, setForcas] = useState(FORCAS);
  const [verForcas, setVerForcas] = useState(false);

  // Nós ficam no ref: a simulação mexe em x/y e os mantém quando o recorte muda.
  const nos = useMemo<No[]>(() => g.nos.map((n, i) => ({ ...n, i, r: raio(n.ligacoes) })), [g]);
  const vizinhos = useMemo(() => {
    const v = nos.map(() => new Set<number>());
    for (const [a, b] of g.arestas) {
      v[a].add(b);
      v[b].add(a);
    }
    return v;
  }, [g, nos]);
  const pastas = useMemo(() => [...new Set(g.nos.map((n) => n.pasta))].sort((a, b) => Object.keys(PASTA).indexOf(a) - Object.keys(PASTA).indexOf(b)), [g]);

  // Recorte: grafo local (a nota selecionada e até `prof` saltos) e pastas ocultas.
  // Fora do grafo local, selecionar não muda o recorte (nem reinicia a simulação).
  const centro = local ? sel : null;
  const visiveis = useMemo(() => {
    let base = new Set(nos.filter((n) => !ocultas.has(n.pasta) && (!semPontes || n.ligacoes <= PONTE || n.i === centro)).map((n) => n.i));
    if (centro !== null) {
      const perto = new Set([centro]);
      let borda = [centro];
      for (let d = 0; d < prof; d++) {
        const prox: number[] = [];
        for (const i of borda) for (const j of vizinhos[i]) if (!perto.has(j) && base.has(j)) { perto.add(j); prox.push(j); }
        borda = prox;
      }
      base = perto;
    }
    return base;
  }, [nos, vizinhos, ocultas, centro, prof, semPontes]);
  const pontes = useMemo(() => nos.filter((n) => n.ligacoes > PONTE), [nos]);
  const arestas = useMemo<Ar[]>(() => g.arestas.filter(([a, b]) => visiveis.has(a) && visiveis.has(b))
    .map(([a, b, rel]) => ({ source: nos[a], target: nos[b], rel })), [g, nos, visiveis]);

  const sim = useRef<Simulation<No, Ar> | null>(null);
  // Enquanto a pessoa não mexe na vista, ela acompanha o grafo se espalhando.
  const mexeu = useRef(false);
  const desenhar = useRef<() => void>(() => {});

  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setTam({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  function enquadrar() {
    const vs = nos.filter((n) => visiveis.has(n.i));
    if (!vs.length) return;
    const xs = vs.map((n) => n.x ?? 0), ys = vs.map((n) => n.y ?? 0);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const k = Math.min(2.5, (tam.w - 60) / Math.max(x1 - x0, 1), (tam.h - 60) / Math.max(y1 - y0, 1));
    vista.current = { k, x: tam.w / 2 - ((x0 + x1) / 2) * k, y: tam.h / 2 - ((y0 + y1) / 2) * k };
    desenhar.current();
  }

  // Simulação: refeita quando o recorte muda; as posições de antes continuam.
  useEffect(() => {
    const vs = nos.filter((n) => visiveis.has(n.i));
    const s = forceSimulation<No, Ar>(vs)
      .force("carga", forceManyBody<No>().strength(-forcas.repulsao).distanceMax(800))
      // Força padrão da mola (1 / ligações do nó menos ligado): nota muito ligada não esmaga as vizinhas.
      .force("molas", forceLink<No, Ar>(arestas).distance(forcas.distancia))
      .force("x", forceX<No>(0).strength(forcas.centro))
      .force("y", forceY<No>(0).strength(forcas.centro))
      .force("colisao", forceCollide<No>((n) => n.r + 4))
      .stop();
    // Primeiro arranjo sem animação (rápido), depois assenta animando.
    if (vs.some((n) => n.x === undefined || Number.isNaN(n.x))) s.tick(120);
    s.alpha(0.3).restart();
    mexeu.current = false;
    s.on("tick", () => (mexeu.current ? desenhar.current() : enquadrar()));
    sim.current = s;
    enquadrar();
    return () => {
      s.stop();
    };
  }, [visiveis, arestas, forcas]); // eslint-disable-line react-hooks/exhaustive-deps

  // Desenho em canvas, com as cores dos tokens do tema (claro/escuro).
  desenhar.current = () => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    const css = getComputedStyle(c);
    const cor = (v: string) => css.getPropertyValue(v).trim();
    const { x, y, k } = vista.current;
    const foco = sobre ?? sel;
    const perto = foco !== null ? vizinhos[foco] : null;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, tam.w, tam.h);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * x, dpr * y);

    ctx.lineWidth = 1 / k;
    for (const a of arestas) {
      const s = a.source as No, t = a.target as No;
      const ativa = foco !== null && (s.i === foco || t.i === foco);
      // Mesmas cores da visão em colunas: documenta em verde, menciona em cinza.
      ctx.strokeStyle = a.rel === "documenta" ? cor("--green") : ativa ? cor("--text") : cor("--muted");
      ctx.globalAlpha = ativa ? 0.8 : foco !== null ? 0.06 : a.rel === "documenta" ? 0.45 : 0.18;
      ctx.beginPath();
      ctx.moveTo(s.x!, s.y!);
      ctx.lineTo(t.x!, t.y!);
      ctx.stroke();
    }
    for (const n of nos) {
      if (!visiveis.has(n.i)) continue;
      const apagado = foco !== null && n.i !== foco && !perto!.has(n.i);
      ctx.globalAlpha = apagado ? 0.18 : 1;
      ctx.fillStyle = cor(DOCUMENTOS.has(n.pasta) ? "--serie-documentos" : "--serie-codigo");
      ctx.beginPath();
      ctx.arc(n.x!, n.y!, n.r, 0, Math.PI * 2);
      ctx.fill();
      if (n.i === sel) {
        ctx.lineWidth = 2.5 / k;
        ctx.strokeStyle = cor("--text");
        ctx.stroke();
      }
    }
    // Nomes: com zoom, de todas; sem zoom, só do foco e dos vizinhos (como no Obsidian).
    ctx.fillStyle = cor("--text");
    ctx.font = `${12 / k}px Ubuntu, sans-serif`;
    ctx.textAlign = "center";
    const geral = Math.min(1, Math.max(0, (k - 1.1) / 0.6));
    for (const n of nos) {
      if (!visiveis.has(n.i)) continue;
      const destaque = foco !== null && (n.i === foco || perto!.has(n.i));
      const alpha = destaque ? 1 : foco !== null ? geral * 0.08 : geral;
      if (alpha <= 0.02) continue;
      ctx.globalAlpha = alpha;
      const t = n.titulo.length > 34 ? n.titulo.slice(0, 33) + "…" : n.titulo;
      ctx.fillText(t, n.x!, n.y! + n.r + 13 / k);
    }
    ctx.globalAlpha = 1;
  };
  useEffect(() => desenhar.current(), [sel, sobre, tam, ocultas]); // eslint-disable-line react-hooks/exhaustive-deps

  // Tema trocado: redesenha com as cores novas.
  useEffect(() => {
    const mo = new MutationObserver(() => desenhar.current());
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-tema"] });
    return () => mo.disconnect();
  }, []);

  // Roda do mouse amplia em volta do ponteiro (passive: false para não rolar a página).
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const roda = (e: WheelEvent) => {
      e.preventDefault();
      const r = c.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    };
    c.addEventListener("wheel", roda, { passive: false });
    return () => c.removeEventListener("wheel", roda);
  });

  function zoom(f: number, px = tam.w / 2, py = tam.h / 2) {
    mexeu.current = true;
    const v = vista.current;
    const k = Math.min(8, Math.max(0.1, v.k * f));
    vista.current = { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
    desenhar.current();
  }

  function noEm(px: number, py: number) {
    const { x, y, k } = vista.current;
    const gx = (px - x) / k, gy = (py - y) / k;
    let melhor: No | null = null, dist = Infinity;
    for (const n of nos) {
      if (!visiveis.has(n.i)) continue;
      const d = Math.hypot(n.x! - gx, n.y! - gy);
      if (d < Math.max(n.r + 3, 8 / k) && d < dist) { melhor = n; dist = d; }
    }
    return melhor;
  }

  const gesto = useRef<{ tipo: "pan" | "no"; no?: No; x: number; y: number; vx: number; vy: number; moveu: boolean } | null>(null);
  function apertar(e: PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const n = noEm(e.clientX - r.left, e.clientY - r.top);
    gesto.current = { tipo: n ? "no" : "pan", no: n ?? undefined, x: e.clientX, y: e.clientY, vx: vista.current.x, vy: vista.current.y, moveu: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function mover(e: PointerEvent<HTMLCanvasElement>) {
    const gs = gesto.current;
    const r = e.currentTarget.getBoundingClientRect();
    if (!gs) {
      const n = noEm(e.clientX - r.left, e.clientY - r.top);
      setSobre(n ? n.i : null);
      return;
    }
    if (Math.hypot(e.clientX - gs.x, e.clientY - gs.y) > 3) gs.moveu = true;
    mexeu.current = true;
    if (gs.tipo === "pan") {
      vista.current = { ...vista.current, x: gs.vx + e.clientX - gs.x, y: gs.vy + e.clientY - gs.y };
      desenhar.current();
    } else if (gs.moveu && gs.no) {
      const { x, y, k } = vista.current;
      gs.no.fx = (e.clientX - r.left - x) / k;
      gs.no.fy = (e.clientY - r.top - y) / k;
      sim.current?.alphaTarget(0.3).restart();
    }
  }
  function soltar() {
    const gs = gesto.current;
    gesto.current = null;
    if (!gs) return;
    if (gs.no) {
      gs.no.fx = gs.no.fy = null;
      sim.current?.alphaTarget(0);
    }
    if (!gs.moveu) setSel(gs.no ? gs.no.i : null);
  }

  function buscar(e: FormEvent) {
    e.preventDefault();
    const b = busca.trim().toLowerCase();
    if (!b) return;
    const achou = nos.find((n) => visiveis.has(n.i) && n.titulo.toLowerCase().includes(b))
      ?? nos.find((n) => n.titulo.toLowerCase().includes(b));
    if (!achou) return setAviso(`Nenhuma nota com "${busca.trim()}".`);
    setAviso("");
    if (!visiveis.has(achou.i)) {
      setOcultas((o) => { const x = new Set(o); x.delete(achou.pasta); return x; });
      if (achou.ligacoes > PONTE) setSemPontes(false);
    }
    setSel(achou.i);
    mexeu.current = true;
    const k = Math.max(vista.current.k, 1.6);
    vista.current = { k, x: tam.w / 2 - (achou.x ?? 0) * k, y: tam.h / 2 - (achou.y ?? 0) * k };
    desenhar.current();
  }

  const n = sel !== null ? nos[sel] : null;
  const contaPasta = (p: string) => g.nos.filter((x) => x.pasta === p).length;
  const total = visiveis.size;
  const ligacoesVisiveis = arestas.length;

  return (
    <>
      <div className="panel mapa-quadro">
        <div className="mapa-barra">
          <form className="grafo-busca" onSubmit={buscar} role="search">
            <Icone nome="search" />
            <input aria-label="Buscar nota no grafo" placeholder="Buscar nota e Enter" value={busca} onChange={(e) => setBusca(e.target.value)} />
          </form>
          <label className="grafo-local">
            <input type="checkbox" checked={local} onChange={(e) => setLocal(e.target.checked)} />
            Grafo local
          </label>
          {local && sel === null && <small className="muted" role="status">Clique numa nota para ver só ela e as vizinhas.</small>}
          {local && sel !== null && (
            <label className="grafo-local">
              Profundidade
              <select value={prof} onChange={(e) => setProf(Number(e.target.value))}>
                {[1, 2, 3].map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          )}
          {pontes.length > 0 && (
            <label className="grafo-local" title={pontes.map((p) => `${p.titulo} (${p.ligacoes} ligações)`).join("\n")}>
              <input type="checkbox" checked={semPontes} onChange={(e) => setSemPontes(e.target.checked)} />
              Esconder {plural(pontes.length, "nota-ponte", "notas-ponte")}
            </label>
          )}
          <button type="button" className={`btn${verForcas ? " ativo" : ""}`} aria-expanded={verForcas} onClick={() => setVerForcas(!verForcas)}>Forças</button>
          {aviso && <small className="muted" role="status">{aviso}</small>}
          <div className="mapa-zoom">
            <button type="button" className="btn" aria-label="Reduzir" onClick={() => zoom(1 / 1.2)}>−</button>
            <button type="button" className="btn" aria-label="Ampliar" onClick={() => zoom(1.2)}>+</button>
            <button type="button" className="btn" onClick={enquadrar}>Centralizar</button>
          </div>
        </div>
        {verForcas && (
          <div className="grafo-forcas">
            <label>Repulsão<input type="range" min={20} max={300} value={forcas.repulsao} onChange={(e) => setForcas({ ...forcas, repulsao: Number(e.target.value) })} /></label>
            <label>Distância das ligações<input type="range" min={10} max={200} value={forcas.distancia} onChange={(e) => setForcas({ ...forcas, distancia: Number(e.target.value) })} /></label>
            <label>Gravidade do centro<input type="range" min={0} max={0.2} step={0.01} value={forcas.centro} onChange={(e) => setForcas({ ...forcas, centro: Number(e.target.value) })} /></label>
            <button type="button" className="textbtn" onClick={() => setForcas(FORCAS)}>Voltar ao padrão</button>
          </div>
        )}
        <div className="mapa-tela grafo-tela" ref={caixa}>
          <canvas ref={canvas} width={tam.w * (window.devicePixelRatio || 1)} height={tam.h * (window.devicePixelRatio || 1)}
            style={{ width: tam.w, height: tam.h }} role="img"
            aria-label={`Grafo com ${plural(total, "nota", "notas")} e ${plural(ligacoesVisiveis, "relação", "relações")}. Para navegar pelo teclado, use a busca ou a visão em colunas.`}
            onPointerDown={apertar} onPointerMove={mover} onPointerUp={soltar} onPointerLeave={() => !gesto.current && setSobre(null)} />
          {sobre !== null && sobre !== sel && <div className="grafo-dica" aria-hidden>{nos[sobre].titulo} · {PASTA[nos[sobre].pasta] ?? nos[sobre].pasta}</div>}
        </div>
        <p className="mapa-dica">Arraste o fundo para mover e uma nota para puxar · roda do mouse amplia · clique seleciona · a busca leva até a nota</p>
        <div className="grafo-legenda">
          <span className="perfil"><i style={{ background: "var(--serie-documentos)" }} />Documentos, assuntos e referência</span>
          <span className="perfil"><i style={{ background: "var(--serie-codigo)" }} />Código</span>
          <span className="muted">Pastas (clique para esconder):</span>
          {pastas.map((p) => (
            <button key={p} type="button" className={`chip${ocultas.has(p) ? " oculta" : ""}`} aria-pressed={!ocultas.has(p)}
              onClick={() => setOcultas((o) => { const x = new Set(o); x.has(p) ? x.delete(p) : x.add(p); return x; })}>
              {PASTA[p] ?? p} · {contaPasta(p)}
            </button>
          ))}
          <span className="grafo-rel"><i className="documenta" />documenta</span>
          <span className="grafo-rel"><i />menciona</span>
        </div>
      </div>
      <div className="panel mapa-detalhes" aria-live="polite">
        {n ? (
          <div className="mapa-detalhes-topo">
            <div>
              <div className="eyebrow">Nota selecionada</div>
              <h3>{n.titulo}</h3>
              <small className="muted">{PASTA[n.pasta] ?? n.pasta} · {plural(vizinhos[n.i].size, "nota ligada", "notas ligadas")}</small>
            </div>
            <div className="mapa-acoes">
              <Link className="btn primary" to={`/sistemas/${tag}/conhecimento?nota=${encodeURIComponent(n.chave)}`}><Icone nome="file" />Abrir nota</Link>
              <button type="button" className="btn" onClick={() => emColunas(n.chave)}><Icone nome="arrow" />Ver relações em colunas</button>
              <Link className="btn" to={`/conversas?vault=${encodeURIComponent(tag)}&nota=${encodeURIComponent(n.chave)}`} title="Abre uma conversa com o Vault-I sobre esta nota"><Icone nome="spark" />Perguntar sobre isso</Link>
            </div>
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>Clique numa nota para destacar as ligações dela. "Grafo local" mostra só a nota e as vizinhas, até 3 saltos. As notas-ponte ligam quase tudo e embolam o código; escondê-las separa os grupos.</p>
        )}
      </div>
      <p className="mapa-rodape">
        Mostrando <b>{total.toLocaleString("pt-BR")}</b> de <b>{g.totais.notas.toLocaleString("pt-BR")}</b> notas e {ligacoesVisiveis.toLocaleString("pt-BR")} relações entre notas.
        Só relações que existem nas notas; nada é inferido.
      </p>
    </>
  );
}
