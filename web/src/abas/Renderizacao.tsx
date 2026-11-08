import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { NotaResumo, Sistema } from "../api";
import { Badge, Carregando, Falha, Vazio } from "../componentes";
import { useDados } from "../dados";
import { curto, plural } from "../formato";
import { Icone } from "../icones";

// Aba Renderização (DV-600): uma página HTML do vault de Referência, com CSS e
// JS a mais se quiser, montada pela API com tudo embutido. Roda num iframe com
// sandbox="allow-scripts" e sem allow-same-origin: o HTML vem de um repositório
// de origem e não pode ver o cookie da sessão nem chamar a API.

interface Renderizada {
  html: string;
  pagina: { chave: string; origem: string; caminho: string; commit: string | null };
  usados: string[];
  avisos: string[];
  bytes: number;
}

const LARGURAS = [
  { slug: "", rotulo: "Inteira", px: null },
  { slug: "tablet", rotulo: "Tablet", px: 768 },
  { slug: "celular", rotulo: "Celular", px: 390 },
] as const;

const ext = (chave: string) => chave.slice(chave.lastIndexOf(".") + 1).toLowerCase();
const PAGINA = ["html", "htm"];
const EXTRA = ["css", "js", "mjs"];

/** O caminho do arquivo na origem (a chave sem `sistemas/<tag>/referencia/`). */
const caminho = (chave: string) => chave.split("/").slice(3).join("/");

export function temReferencia(s: Sistema) {
  return s.origens.some((o) => o.leituras.some((l) => l.perfil === "referencia" || l.perfil === "referencia-explicada"));
}

export default function Renderizacao({ s }: { s: Sistema }) {
  const arvore = useDados<{ pastas: { pasta: string; notas: NotaResumo[] }[] }>(`/sistemas/${s.tag}/notas`);
  const [params, setParams] = useSearchParams();
  const [busca, setBusca] = useState("");
  const pagina = params.get("pagina");
  const extras = params.getAll("extra");
  const largura = LARGURAS.find((l) => l.slug === (params.get("largura") ?? "")) ?? LARGURAS[0];

  const arquivos = useMemo(() => {
    const ref = arvore.dados?.pastas.find((p) => p.pasta === "referencia")?.notas ?? [];
    const b = busca.trim().toLowerCase();
    const filtra = (n: NotaResumo) => !b || n.chave.toLowerCase().includes(b);
    return {
      paginas: ref.filter((n) => PAGINA.includes(ext(n.chave)) && filtra(n)),
      extras: ref.filter((n) => EXTRA.includes(ext(n.chave)) && filtra(n)),
      total: ref.length,
    };
  }, [arvore.dados, busca]);

  function mudar(f: (p: URLSearchParams) => void) {
    const p = new URLSearchParams(params);
    f(p);
    setParams(p, { replace: true });
  }
  const escolher = (chave: string) => mudar((p) => p.set("pagina", chave));
  const alternarExtra = (chave: string) =>
    mudar((p) => {
      const atuais = p.getAll("extra");
      p.delete("extra");
      (atuais.includes(chave) ? atuais.filter((x) => x !== chave) : [...atuais, chave]).forEach((x) => p.append("extra", x));
    });

  if (arvore.erro) return <Falha erro={arvore.erro} tentar={arvore.recarregar} />;
  if (!arvore.dados) return <Carregando />;
  if (!arquivos.total) {
    return (
      <section className="panel">
        <Vazio titulo="Nada para renderizar">
          A renderização usa as notas literais de <span className="mono">referencia/</span>. Classifique uma origem como Referência
          (aba Fontes) e peça um pull.
        </Vazio>
      </section>
    );
  }

  return (
    <div className="split">
      <section className="panel">
        <div className="panel-head" style={{ paddingBottom: 8 }}>
          <div>
            <h2>Arquivos</h2>
            <small>Uma página HTML e, se quiser, CSS ou JS a mais.</small>
          </div>
        </div>
        <div className="search" style={{ margin: "0 16px", maxWidth: "none" }}>
          <Icone nome="search" />
          <input type="search" aria-label="Buscar arquivo" placeholder="Buscar arquivo" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <nav className="tree" aria-label="Arquivos para renderizar">
          <h3>Página ({arquivos.paginas.length})</h3>
          {arquivos.paginas.length === 0 && <p className="muted" style={{ padding: "4px 10px", fontSize: 12 }}>Nenhum .html no vault.</p>}
          {arquivos.paginas.map((n) => (
            <button key={n.chave} className={pagina === n.chave ? "active" : ""} aria-pressed={pagina === n.chave} onClick={() => escolher(n.chave)}>
              <Icone nome="file" />
              <span className="mono" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", fontSize: 12 }}>{caminho(n.chave)}</span>
            </button>
          ))}
          <h3>Carregar junto ({arquivos.extras.length})</h3>
          {arquivos.extras.map((n) => (
            <label key={n.chave} className={`marca ${extras.includes(n.chave) ? "active" : ""}`}>
              <input type="checkbox" checked={extras.includes(n.chave)} onChange={() => alternarExtra(n.chave)} />
              <span className="mono" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", fontSize: 12 }}>{caminho(n.chave)}</span>
            </label>
          ))}
        </nav>
      </section>
      <section className="panel">
        {!pagina ? (
          <Vazio titulo="Escolha uma página">
            Os arquivos que ela referencia por caminho relativo (CSS, JS, imagens, fontes) entram sozinhos, do mesmo commit.
          </Vazio>
        ) : (
          <Visualizar tag={s.tag} pagina={pagina} extras={extras} largura={largura} mudarLargura={(slug) => mudar((p) => (slug ? p.set("largura", slug) : p.delete("largura")))} />
        )}
      </section>
    </div>
  );
}

function Visualizar({ tag, pagina, extras, largura, mudarLargura }: {
  tag: string; pagina: string; extras: string[]; largura: (typeof LARGURAS)[number]; mudarLargura: (slug: string) => void;
}) {
  const q = new URLSearchParams({ pagina });
  extras.forEach((e) => q.append("extra", e));
  const { dados: r, erro, carregando, recarregar } = useDados<Renderizada>(`/sistemas/${tag}/renderizar?${q}`, undefined, true);
  const [versao, setVersao] = useState(0);
  const moldura = useRef<HTMLDivElement>(null);

  return (
    <article>
      <div className="panel-head" style={{ flexWrap: "wrap" }}>
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Renderização</div>
          <h2 className="mono" style={{ fontSize: 15 }}>{caminho(pagina)}</h2>
          {r && (
            <small>
              commit <span className="mono">{curto(r.pagina.commit)}</span> · {plural(r.usados.length, "arquivo embutido", "arquivos embutidos")} ·{" "}
              {(r.bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB
            </small>
          )}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div className="segmentos" role="group" aria-label="Largura">
            {LARGURAS.map((l) => (
              <button key={l.slug} className={largura.slug === l.slug ? "ativo" : ""} aria-pressed={largura.slug === l.slug} onClick={() => mudarLargura(l.slug)}>
                {l.rotulo}
              </button>
            ))}
          </div>
          <button className="btn" title="Recarregar a página (volta ao estado inicial)" onClick={() => { setVersao((v) => v + 1); recarregar(); }}>
            <Icone nome="refresh" />Recarregar
          </button>
          <button className="btn" title="Tela cheia" onClick={() => moldura.current?.requestFullscreen?.()}>
            <Icone nome="panel" />Tela cheia
          </button>
        </div>
      </div>
      {erro && <div className="panel-body"><Falha erro={erro} tentar={recarregar} /></div>}
      {r && r.avisos.length > 0 && (
        <div className="banner warn" style={{ margin: "0 23px 14px" }}>
          <Icone nome="alert" />
          <div>
            <div>{plural(r.avisos.length, "referência ficou de fora", "referências ficaram de fora")}:</div>
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
              {r.avisos.map((a) => <li key={a} className="mono" style={{ fontSize: 12 }}>{a}</li>)}
            </ul>
          </div>
        </div>
      )}
      <div className="render-moldura" ref={moldura}>
        {!r ? <Carregando texto={carregando ? "Montando a página…" : ""} /> : (
          <iframe
            key={`${r.pagina.chave}:${versao}`}
            title={`Renderização de ${caminho(pagina)}`}
            sandbox="allow-scripts"
            referrerPolicy="no-referrer"
            srcDoc={r.html}
            style={{ width: largura.px ? `${largura.px}px` : "100%" }}
          />
        )}
      </div>
      {r && (
        <div className="panel-body" style={{ paddingTop: 12 }}>
          <small>
            Isolada: a página roda sem acesso à sessão nem à API do hub.{" "}
          </small>
          {r.usados.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
              {r.usados.map((u) => <Badge key={u} tipo="neutral"><span className="mono">{u}</span></Badge>)}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
