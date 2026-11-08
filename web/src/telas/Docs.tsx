import { Children, isValidElement, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, Navigate, useParams } from "react-router-dom";
import cli from "../docs/cli.md?raw";
import { Icone } from "../icones";

// Documentação (DV-607): a v1 traz a CLI. As próximas páginas (Sobre, Quickstart,
// Tutorial) entram aqui como novos arquivos em src/docs e uma linha em PAGINAS.
type Pagina = { slug: string; titulo: string; texto?: string };
const PAGINAS: Pagina[] = [
  { slug: "cli", titulo: "CLI (pv)", texto: cli },
  { slug: "sobre", titulo: "Sobre" },
  { slug: "quickstart", titulo: "Quickstart" },
  { slug: "tutorial", titulo: "Tutorial" },
];

function texto(n: ReactNode): string {
  return Children.toArray(n)
    .map((c) => (typeof c === "string" || typeof c === "number" ? String(c) : isValidElement(c) ? texto((c.props as { children?: ReactNode }).children) : ""))
    .join("");
}

const ancora = (s: string) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export default function Docs() {
  const { pagina = "cli" } = useParams();
  const atual = PAGINAS.find((p) => p.slug === pagina && p.texto);
  if (!atual) return <Navigate to="/docs/cli" replace />;
  // O endereço dos exemplos é o desta tela (a mesma origem da API).
  const corpo = atual.texto!.split("{{URL}}").join(window.location.origin);
  const secoes = [...corpo.matchAll(/^## (.+)$/gm)].map((m) => m[1].replace(/`/g, ""));

  return (
    <div className="page">
      <div className="heading">
        <div>
          <div className="eyebrow">Documentação</div>
          <h1>{atual.titulo}</h1>
        </div>
      </div>
      <div className="docs">
        <nav className="panel docs-indice" aria-label="Páginas da documentação">
          {PAGINAS.map((p) =>
            p.texto ? (
              <div key={p.slug}>
                <Link to={`/docs/${p.slug}`} className={`nav${p.slug === atual.slug ? " active" : ""}`}
                  aria-current={p.slug === atual.slug ? "page" : undefined}>
                  <Icone nome="book" /><span>{p.titulo}</span>
                </Link>
                {p.slug === atual.slug && (
                  <ul>
                    {secoes.map((s) => <li key={s}><a href={`#${ancora(s)}`}>{s}</a></li>)}
                  </ul>
                )}
              </div>
            ) : (
              <div key={p.slug} className="nav desabilitado" aria-disabled>
                <Icone nome="book" /><span>{p.titulo}</span><span className="count">em breve</span>
              </div>
            ),
          )}
        </nav>
        <article className="panel nota docs-corpo">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: () => null, // o título já está no cabeçalho da página
              h2: ({ children }) => <h2 id={ancora(texto(children))}>{children}</h2>,
              a: ({ href, children }) =>
                href?.startsWith("#") || href?.startsWith("/") ? <a href={href}>{children}</a>
                  : <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
            }}
          >
            {corpo}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  );
}
