import { PointerEvent, WheelEvent, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "../componentes";
import { Icone } from "../icones";

// Mapa de infraestrutura (DV-603): os containers do vault como num canvas de
// serviços. Os dados vêm só do leitor de Dockerfile, compose e proxy
// (petro_vault/infra.py, DV-602): nenhuma ligação é inventada. Camadas da
// esquerda para a direita: entrada (porta do host) → proxy → apps → dados.

export type TipoServico = "proxy" | "site" | "app" | "banco" | "cache" | "fila";
export interface ServicoInfra {
  id: string; nome: string; stack: string | null; tipo: TipoServico; container: string | null; imagem: string | null; build: string | null;
  portas: { host: string | null; container: string; texto: string }[]; expose: string[];
  volumes: { origem: string | null; destino: string; somente_leitura: boolean; nomeado: boolean }[];
  redes: string[]; healthcheck: string | null; restart: string | null; proxy: string[]; env: string[];
  arquivos: { ref: string; tipo: string | null; nota: string | null }[]; nota: string | null;
}
/** Banco, AD/LDAP, SAP ou serviço HTTP que o container usa sem fazer parte do stack (DV-604). */
export interface ExternoInfra {
  id: string; tipo: string; rotulo: string; ambientes: { ambiente: string | null; variaveis: string[] }[];
  variaveis: string[]; destinos: number; servicos: string[]; origens: string[]; notas: string[]; notas_dados: number;
}
export interface GrafoInfra {
  servicos: ServicoInfra[]; ligacoes: { de: string; para: string; tipo: "depende" | "proxy" | "externo" }[];
  externos: ExternoInfra[];
  stacks: { id: string; nome: string; arquivo: string | null; servicos: string[] }[];
  redes: { stack: string; nome: string }[]; avisos: string[]; soltos: string[]; visao_geral: string | null;
}

const LARG = 248, CAB = 92, VOL = 30, COLW = 340, VGAP = 46, ENTRADA_X = -280;
const STACK_PAD = 34, STACK_TOPO = 46, STACK_GAP = 70; // quadro de cada stack (DV-603): um por compose
const EXT_LARG = 240, EXT_GAP = 18, EXT_DX = 190; // dependências externas (DV-604), à direita, sem endereço
const extAltura = (e: ExternoInfra) => (e.ambientes.some((a) => a.ambiente) ? 96 : 70);
const ICONE_EXT: Record<string, string> = { mysql: "book", postgres: "book", sqlserver: "book", oracle: "book", mongodb: "book",
  redis: "clock", rabbitmq: "activity", ldap: "key", smtp: "activity", sap: "grid", http: "external" };
const ROTULO: Record<TipoServico, string> = { proxy: "Proxy", site: "Site estático", app: "Aplicação", banco: "Banco", cache: "Cache", fila: "Fila" };
const ICONE: Record<TipoServico, string> = { proxy: "arrow", site: "grid", app: "panel", banco: "book", cache: "clock", fila: "activity" };

interface Caixa { x: number; y: number; h: number }

/** Coluna de cada serviço: o caminho mais longo desde quem não é usado por ninguém (a entrada). */
function colunas(g: GrafoInfra) {
  const entram = new Map<string, string[]>();
  g.ligacoes.filter((l) => l.tipo !== "externo").forEach((l) => entram.set(l.para, [...(entram.get(l.para) ?? []), l.de]));
  const memo = new Map<string, number>();
  const col = (id: string, visto: Set<string>): number => {
    if (memo.has(id)) return memo.get(id)!;
    if (visto.has(id)) return 0; // ciclo: não deveria haver, mas não trava
    visto.add(id);
    const de = entram.get(id) ?? [];
    const c = de.length ? 1 + Math.max(...de.map((d) => col(d, visto))) : 0;
    memo.set(id, c);
    return c;
  };
  g.servicos.forEach((s) => col(s.id, new Set()));
  return memo;
}

function altura(s: ServicoInfra) {
  return CAB + (s.volumes.length ? 10 + s.volumes.length * VOL : 0);
}

/** Um stack embaixo do outro; dentro de cada um, colunas pela dependência e serviços empilhados na coluna. */
function posicoes(g: GrafoInfra): Map<string, Caixa> {
  const col = colunas(g);
  const porId = new Map(g.servicos.map((s) => [s.id, s]));
  const saida = new Map<string, Caixa>();
  let topo = 0;
  for (const st of g.stacks) {
    const lista = st.servicos.map((id) => porId.get(id)).filter((s): s is ServicoInfra => !!s);
    const minCol = Math.min(...lista.map((s) => col.get(s.id) ?? 0));
    const porCol = new Map<number, ServicoInfra[]>();
    lista.forEach((s) => {
      const c = (col.get(s.id) ?? 0) - minCol;
      porCol.set(c, [...(porCol.get(c) ?? []), s]);
    });
    const alturaCol = (l: ServicoInfra[]) => l.reduce((t, s) => t + altura(s), 0) + VGAP * (l.length - 1);
    const maior = Math.max(...[...porCol.values()].map(alturaCol));
    porCol.forEach((l, c) => {
      let y = topo + STACK_TOPO + (maior - alturaCol(l)) / 2;
      l.forEach((s) => {
        saida.set(s.id, { x: c * COLW, y, h: altura(s) });
        y += altura(s) + VGAP;
      });
    });
    topo += STACK_TOPO + maior + STACK_PAD * 2 + STACK_GAP;
  }
  // Externos numa coluna à direita de tudo, fora dos quadros dos stacks.
  const caixas = [...saida.values()];
  if (g.externos.length && caixas.length) {
    const x = Math.max(...caixas.map((c) => c.x + LARG)) + STACK_PAD + EXT_DX;
    const y0 = Math.min(...caixas.map((c) => c.y)), y1 = Math.max(...caixas.map((c) => c.y + c.h));
    const total = g.externos.reduce((t, e) => t + extAltura(e), 0) + (g.externos.length - 1) * EXT_GAP;
    let y = (y0 + y1) / 2 - total / 2;
    g.externos.forEach((e) => {
      saida.set(e.id, { x, y, h: extAltura(e) });
      y += extAltura(e) + EXT_GAP;
    });
  }
  return saida;
}

function curva(x1: number, y1: number, x2: number, y2: number) {
  const c = Math.max(40, Math.abs(x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}`;
}

export default function InfraMapa({ tag, g }: { tag: string; g: GrafoInfra }) {
  const base = useMemo(() => posicoes(g), [g]);
  const [movidos, setMovidos] = useState<Record<string, { x: number; y: number }>>({});
  const [vista, setVista] = useState({ x: 360, y: 300, z: 1 });
  const [sel, setSel] = useState<string | null>(g.servicos[0]?.id ?? null);
  const arrasto = useRef<{ id: string | null; x: number; y: number; ox: number; oy: number } | null>(null);
  const tela = useRef<HTMLDivElement>(null);

  /** Enquadra tudo (cards, entrada e redes) no canvas, sem passar de 100%. */
  function enquadrar(pos: Map<string, Caixa>) {
    const el = tela.current;
    if (!el || pos.size === 0) return;
    const cs = [...pos.values()];
    const temEntrada = g.servicos.some((sv) => sv.portas.some((p) => p.host));
    const x0 = Math.min(...cs.map((c) => c.x), temEntrada ? ENTRADA_X : Infinity) - 40;
    const x1 = Math.max(...[...pos.entries()].map(([id, c]) => c.x + (id.startsWith("ext-") ? EXT_LARG : LARG))) + 40;
    const y0 = Math.min(...cs.map((c) => c.y)) - STACK_PAD - 40, y1 = Math.max(...cs.map((c) => c.y + c.h)) + STACK_PAD + 20;
    const z = Math.max(0.4, Math.min(1, el.clientWidth / (x1 - x0), el.clientHeight / (y1 - y0)));
    setVista({ z, x: (el.clientWidth - (x1 - x0) * z) / 2 - x0 * z, y: (el.clientHeight - (y1 - y0) * z) / 2 - y0 * z });
  }
  useLayoutEffect(() => enquadrar(base), [base]); // enquadra de novo quando o grafo muda

  const caixa = (id: string): Caixa => {
    const b = base.get(id)!;
    const m = movidos[id];
    return m ? { ...b, x: m.x, y: m.y } : b;
  };
  const publicados = g.servicos.filter((s) => s.portas.some((p) => p.host));
  const entradaY = (() => {
    const ys = publicados.map((s) => caixa(s.id).y + 34);
    return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length - 34 : 0;
  })();

  function inicio(e: PointerEvent, id: string | null) {
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const c = id ? caixa(id) : { x: vista.x, y: vista.y };
    arrasto.current = { id, x: e.clientX, y: e.clientY, ox: c.x, oy: c.y };
    if (id) e.stopPropagation();
  }
  function mover(e: PointerEvent) {
    const a = arrasto.current;
    if (!a) return;
    const dx = e.clientX - a.x, dy = e.clientY - a.y;
    if (a.id) {
      const id = a.id;
      setMovidos((m) => ({ ...m, [id]: { x: a.ox + dx / vista.z, y: a.oy + dy / vista.z } }));
    } else {
      setVista((v) => ({ ...v, x: a.ox + dx, y: a.oy + dy }));
    }
  }
  function fim() {
    arrasto.current = null;
  }
  function roda(e: WheelEvent) {
    const z = Math.min(1.8, Math.max(0.4, vista.z * (e.deltaY < 0 ? 1.1 : 0.9)));
    setVista((v) => ({ ...v, z }));
  }
  const zoom = (f: number) => setVista((v) => ({ ...v, z: Math.min(1.8, Math.max(0.4, v.z * f)) }));

  const envolver = (ids: string[], pad: number, topo: number) => {
    const cs = ids.map((id) => caixa(id));
    const x = Math.min(...cs.map((c) => c.x)) - pad, y = Math.min(...cs.map((c) => c.y)) - pad - topo;
    const x2 = Math.max(...cs.map((c) => c.x + LARG)) + pad, y2 = Math.max(...cs.map((c) => c.y + c.h)) + pad;
    return { x, y, w: x2 - x, h: y2 - y };
  };
  // Stack (um por compose) e, dentro dele, as redes do compose: regiões em volta dos serviços.
  const quadros = g.stacks.filter((st) => st.servicos.length).map((st) => ({ st, ...envolver(st.servicos, STACK_PAD, 18) }));
  const regioes = g.redes.map((r, i) => {
    const ids = g.servicos.filter((s) => (s.stack ?? "") === r.stack && s.redes.includes(r.nome)).map((s) => s.id);
    return { r: `${r.stack}/${r.nome}`, nome: r.nome, ...envolver(ids, 14 + (i % 3) * 6, 16) };
  }).filter((rg) => Number.isFinite(rg.x));
  // Linha para o externo: do quadro do stack, se todos os serviços dele usam; senão, de cada serviço.
  const linhasExternas = g.externos.flatMap((e) => {
    const b = caixa(e.id);
    return quadros.flatMap((q) => {
      const usam = q.st.servicos.filter((id) => e.servicos.includes(id));
      if (!usam.length) return [];
      const ativa = sel === e.id || usam.includes(sel ?? "");
      if (usam.length === q.st.servicos.length && usam.length > 1) {
        return [{ k: `${q.st.id}-${e.id}`, x1: q.x + q.w, y1: q.y + q.h / 2, x2: b.x, y2: b.y + b.h / 2, ativa }];
      }
      return usam.map((id) => {
        const a = caixa(id);
        return { k: `${id}-${e.id}`, x1: a.x + LARG, y1: a.y + a.h - 18, x2: b.x, y2: b.y + b.h / 2, ativa };
      });
    });
  });
  const s = g.servicos.find((x) => x.id === sel) ?? null;
  const ext = g.externos.find((x) => x.id === sel) ?? null;
  const nomeDe = (id: string) => g.servicos.find((x) => x.id === id)?.nome ?? id;

  return (
    <div className="infra-split">
      <div className="panel infra-quadro">
        <div className="mapa-barra">
          <small>
            {g.servicos.length} {g.servicos.length === 1 ? "serviço" : "serviços"}
            {g.stacks.length > 1 ? ` em ${g.stacks.length} stacks` : ""} · lido dos arquivos de container, sem LLM.
            Arraste os cards e o fundo.
          </small>
          <div className="mapa-zoom">
            <button type="button" className="btn" aria-label="Diminuir" onClick={() => zoom(0.85)}>−</button>
            <button type="button" className="btn" aria-label="Aumentar" onClick={() => zoom(1.15)}>+</button>
            <button type="button" className="btn" onClick={() => { setMovidos({}); enquadrar(base); }}>Arrumar</button>
          </div>
        </div>
        <div className="infra-canvas" ref={tela} onPointerDown={(e) => inicio(e, null)} onPointerMove={mover} onPointerUp={fim}
          onPointerCancel={fim} onWheel={roda} role="application" aria-label="Mapa de infraestrutura">
          <div className="infra-camada" style={{ transform: `translate(${vista.x}px, ${vista.y}px) scale(${vista.z})` }}>
            {quadros.map((q) => (
              <div key={q.st.id || "_sem"} className={`infra-stack ${q.st.id ? "" : "sem"}`} style={{ left: q.x, top: q.y, width: q.w, height: q.h }}>
                <div className="infra-stack-topo">
                  <Icone nome="grid" />
                  <b>{q.st.nome}</b>
                  <small className="mono">{q.st.arquivo ? `${q.st.arquivo} · ` : ""}{q.st.servicos.length} {q.st.servicos.length === 1 ? "serviço" : "serviços"}</small>
                </div>
              </div>
            ))}
            {regioes.map((rg) => (
              <div key={rg.r} className="infra-rede" style={{ left: rg.x, top: rg.y, width: rg.w, height: rg.h }}>
                <span>rede {rg.nome}</span>
              </div>
            ))}
            <svg className="infra-linhas" width="1" height="1" aria-hidden="true">
              <defs>
                <marker id="infra-seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="infra-seta" />
                </marker>
              </defs>
              {publicados.map((sv) => {
                const c = caixa(sv.id);
                return <path key={`e-${sv.id}`} className="infra-linha entrada" d={curva(ENTRADA_X + 170, entradaY + 34, c.x, c.y + 34)} />;
              })}
              {linhasExternas.map((l) => (
                <path key={l.k} className={`infra-linha externo ${l.ativa ? "ativa" : ""}`} d={curva(l.x1, l.y1, l.x2, l.y2)} />
              ))}
              {g.ligacoes.filter((l) => l.tipo !== "externo").map((l) => {
                const a = caixa(l.de), b = caixa(l.para);
                const ativa = sel === l.de || sel === l.para;
                const dy = l.tipo === "proxy" ? 18 : 0; // a linha do proxy corre abaixo da de dependência
                return (
                  <path key={`${l.de}-${l.para}-${l.tipo}`} className={`infra-linha ${l.tipo} ${ativa ? "ativa" : ""}`}
                    d={curva(a.x + LARG, a.y + 34 + dy, b.x, b.y + 34 + dy)} markerEnd="url(#infra-seta)" />
                );
              })}
            </svg>
            {publicados.length > 0 && (
              <div className="infra-entrada" style={{ left: ENTRADA_X, top: entradaY }}>
                <Icone nome="external" />
                <div>
                  <b>Host</b>
                  <small>{publicados.flatMap((sv) => sv.portas.filter((p) => p.host).map((p) => `:${p.host}`)).join(" ")}</small>
                </div>
              </div>
            )}
            {g.externos.map((e) => {
              const c = caixa(e.id);
              return (
                <div key={e.id} className={`infra-externo ${sel === e.id ? "sel" : ""}`} style={{ left: c.x, top: c.y, width: EXT_LARG, height: c.h }}
                  onPointerDown={(ev) => { setSel(e.id); inicio(ev, e.id); }} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") setSel(e.id); }}
                  tabIndex={0} role="button" aria-pressed={sel === e.id} aria-label={`${e.rotulo}, fora do stack`}>
                  <div className="infra-card-topo">
                    <span className="infra-icone externo"><Icone nome={ICONE_EXT[e.tipo] ?? "external"} /></span>
                    <div style={{ minWidth: 0 }}>
                      <b>{e.rotulo}</b>
                      <small>{e.variaveis.length} {e.variaveis.length === 1 ? "variável" : "variáveis"} · fora do stack</small>
                    </div>
                  </div>
                  {e.ambientes.some((a) => a.ambiente) && (
                    <div className="infra-selos">
                      {e.ambientes.filter((a) => a.ambiente).map((a) => <span key={a.ambiente} className="infra-selo">{a.ambiente}</span>)}
                    </div>
                  )}
                </div>
              );
            })}
            {g.servicos.map((sv) => {
              const c = caixa(sv.id);
              return (
                <div key={sv.id} className={`infra-card ${sel === sv.id ? "sel" : ""}`} style={{ left: c.x, top: c.y, width: LARG }}
                  onPointerDown={(e) => { setSel(sv.id); inicio(e, sv.id); }} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setSel(sv.id); }}
                  tabIndex={0} role="button" aria-pressed={sel === sv.id} aria-label={`${sv.nome}, ${ROTULO[sv.tipo]}`}>
                  <div className="infra-card-topo">
                    <span className={`infra-icone ${sv.tipo}`}><Icone nome={ICONE[sv.tipo]} /></span>
                    <div style={{ minWidth: 0 }}>
                      <b title={sv.nome}>{sv.nome}</b>
                      <small className="mono" title={sv.imagem ?? sv.build ?? ""}>{sv.imagem ?? (sv.build ? `build ${sv.build}` : ROTULO[sv.tipo])}</small>
                    </div>
                    <span className={`infra-saude ${sv.healthcheck ? "com" : ""}`} title={sv.healthcheck ? `healthcheck: ${sv.healthcheck}` : "sem healthcheck"} />
                  </div>
                  <div className="infra-selos">
                    {sv.portas.map((p) => <span key={p.texto} className="infra-selo porta">{p.host ? `${p.host} → ${p.container}` : p.container}</span>)}
                    {sv.portas.length === 0 && sv.expose.map((p) => <span key={p} className="infra-selo">interna {p}</span>)}
                    {sv.restart && <span className="infra-selo">{sv.restart}</span>}
                  </div>
                  {sv.volumes.length > 0 && (
                    <div className="infra-volumes">
                      {sv.volumes.map((v) => (
                        <div key={`${v.origem}:${v.destino}`} className="infra-volume" title={`${v.origem ?? "anônimo"} → ${v.destino}`}>
                          <Icone nome="lock" />
                          <span className="mono">{v.nomeado ? v.origem : v.destino}</span>
                          {v.somente_leitura && <small>ro</small>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <div className="infra-legenda">
          <span><i className="l depende" />depende de</span>
          <span><i className="l proxy" />proxy para</span>
          <span><i className="l entrada" />porta publicada no host</span>
          <span><i className="s" />stack (um por compose)</span>
          {g.externos.length > 0 && <span><i className="x" />fora do stack (do .env.example)</span>}
          {g.redes.length > 0 && <span><i className="r" />rede do compose</span>}
        </div>
      </div>
      <aside className="panel infra-detalhe" aria-live="polite">
        {ext ? (
          <div className="panel-body">
            <div className="eyebrow">Fora do stack</div>
            <h3 style={{ margin: "4px 0 2px" }}>{ext.rotulo}</h3>
            <ul className="infra-ext-lista">
              {ext.ambientes.map((a) => (
                <li key={a.ambiente ?? "-"}><b>{a.ambiente ?? "sem ambiente no nome"}</b><small className="mono">{a.variaveis.join(", ")}</small></li>
              ))}
            </ul>
            <dl className="infra-fatos">
              <dt>Usado por</dt><dd>{ext.servicos.map(nomeDe).join(", ")}</dd>
              <dt>De onde</dt><dd className="mono">{ext.origens.join(", ")}</dd>
            </dl>
            <p style={{ fontSize: 12 }} className="muted">Só o tipo e o ambiente (pelo nome da variável). Endereço, usuário e senha não aparecem.</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
              {ext.notas.map((n) => (
                <Link key={n} className="btn" to={`/sistemas/${tag}/conhecimento?nota=${encodeURIComponent(n)}`}><Icone nome="file" />{n.split("/").pop()}</Link>
              ))}
              {ext.notas_dados > 0 && <Link className="btn" to={`/sistemas/${tag}/conhecimento`}>{ext.notas_dados} notas de dados</Link>}
            </div>
          </div>
        ) : !s ? <div className="panel-body"><small>Selecione um serviço.</small></div> : (
          <div className="panel-body">
            <div className="eyebrow">{ROTULO[s.tipo]}{s.stack ? ` · stack ${s.stack}` : ""}</div>
            <h3 style={{ margin: "4px 0 2px" }}>{s.nome}</h3>
            {s.container && <small className="mono">container {s.container}</small>}
            <dl className="infra-fatos">
              {s.imagem && <><dt>Imagem</dt><dd className="mono">{s.imagem}</dd></>}
              {s.build && <><dt>Build</dt><dd className="mono">{s.build}</dd></>}
              {s.portas.length > 0 && <><dt>Portas</dt><dd className="mono">{s.portas.map((p) => p.texto).join(", ")}</dd></>}
              {s.volumes.length > 0 && <><dt>Volumes</dt><dd className="mono">{s.volumes.map((v) => `${v.origem ?? "—"} → ${v.destino}${v.somente_leitura ? " (ro)" : ""}`).join("; ")}</dd></>}
              {s.redes.length > 0 && <><dt>Redes</dt><dd>{s.redes.join(", ")}</dd></>}
              {s.healthcheck && <><dt>Healthcheck</dt><dd className="mono">{s.healthcheck}</dd></>}
              {s.restart && <><dt>Restart</dt><dd>{s.restart}</dd></>}
              {s.proxy.length > 0 && <><dt>Rotas</dt><dd className="mono">{s.proxy.map((p) => <div key={p}>{p}</div>)}</dd></>}
              {s.env.length > 0 && <><dt>Variáveis</dt><dd className="mono">{s.env.join(", ")}</dd></>}
            </dl>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
              {s.nota
                ? <Link className="btn primary" to={`/sistemas/${tag}/conhecimento?nota=${encodeURIComponent(s.nota)}`}><Icone nome="file" />Abrir nota</Link>
                : <Badge tipo="warn">ainda sem nota em infra/</Badge>}
              {g.visao_geral && <Link className="btn" to={`/sistemas/${tag}/conhecimento?nota=${encodeURIComponent(g.visao_geral)}`}>Visão geral</Link>}
            </div>
            <small>Arquivos</small>
            <ul className="infra-arquivos">
              {s.arquivos.map((a) => (
                <li key={a.ref}>
                  {a.nota ? <Link className="textbtn mono" to={`/sistemas/${tag}/conhecimento?nota=${encodeURIComponent(a.nota)}`}>{a.ref}</Link>
                    : <span className="mono">{a.ref}</span>}
                  {a.tipo && <small> · {a.tipo}</small>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {g.avisos.length > 0 && (
          <div className="banner warn" style={{ margin: "0 16px 16px" }}>
            <Icone nome="alert" /><div>{g.avisos.join("; ")}</div>
          </div>
        )}
      </aside>
    </div>
  );
}
