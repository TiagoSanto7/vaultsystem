import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useSearchParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { Nota, NotaResumo, Sistema, Verificacao } from "../api";
import { Badge, Carregando, Falha, LinkExterno, usePagina, Vazio } from "../componentes";
import { useAncora, useDados } from "../dados";
import { curto, dataHora, plural, relativo } from "../formato";
import { Icone } from "../icones";

const PASTAS: Record<string, string> = {
  documentos: "Documentos", assuntos: "Assuntos", modulos: "Módulos", regras: "Regras de negócio",
  integracoes: "Integrações", apis: "APIs", dados: "Dados", indices: "Índices",
};

const TIPOS: Record<string, string> = {
  possivel_segredo: "Possível segredo", origem_sumiu: "Origem que não existe mais", origem_nao_cadastrada: "Origem não cadastrada",
  link_quebrado: "Link quebrado", link_outra_tag: "Link para outra tag", cabecalho: "Cabeçalho incompleto",
  sistema_errado: "Sistema errado no cabeçalho", tipo_nota_errado: "Tipo de nota errado", assunto_sem_documento: "Assunto sem documento",
  documento_orfao: "Documento órfão", infra_sem_servico: "Infra de serviço que não existe",
};

/** Tira o cabeçalho YAML e troca [[alvo|texto]] por links internos (?nota=alvo). */
function preparar(conteudo: string) {
  const corpo = conteudo.replace(/^---\n[\s\S]*?\n---\n?/, "");
  return corpo.replace(/\[\[([^\]|#]+)(?:[#|]([^\]]*))?\]\]/g, (_, alvo: string, texto?: string) => {
    const a = alvo.trim();
    return `[${(texto || a.split("/").pop() || a).replace(/[[\]]/g, "")}](?nota=${encodeURIComponent(a)})`;
  });
}

export default function Conhecimento({ s }: { s: Sistema }) {
  const verif = useDados<Verificacao>(`/sistemas/${s.tag}/verificacao`, 30000);
  const arvore = useDados<{ pastas: { pasta: string; quantas: number; notas: NotaResumo[] }[] }>(`/sistemas/${s.tag}/notas`, 30000);
  const [params, setParams] = useSearchParams();
  const [busca, setBusca] = useState("");
  const aberta = params.get("nota");
  useAncora(!!verif.dados);

  const pastas = useMemo(() => {
    const b = busca.trim().toLowerCase();
    return (arvore.dados?.pastas ?? [])
      .map((p) => ({ ...p, notas: p.notas.filter((n) => !b || (n.titulo ?? "").toLowerCase().includes(b) || n.chave.toLowerCase().includes(b)) }))
      .filter((p) => p.notas.length);
  }, [arvore.dados, busca]);

  const abrir = (chave: string) => setParams({ nota: chave });
  const problemas = usePagina(verif.dados?.problemas);

  return (
    <>
      <section className="panel" id="verificacao">
        <div className="panel-head">
          <div>
            <h2>Verificação</h2>
            <small>
              Conferência feita pelo código, sem IA, ao fim de cada rodada: cabeçalhos, links, origens no commit e possíveis segredos.
              Não é a aprovação editorial de uma pessoa.
            </small>
          </div>
          {verif.dados && (
            <Badge tipo={verif.dados.estado === "limpa" ? "" : verif.dados.estado === "com_problema" ? "warn" : "neutral"}>
              {verif.dados.estado === "limpa" ? "Limpa" : verif.dados.estado === "com_problema" ? plural(verif.dados.total ?? 0, "problema", "problemas") : "Nunca verificado"}
            </Badge>
          )}
        </div>
        {verif.erro && <div className="panel-body"><Falha erro={verif.erro} tentar={verif.recarregar} /></div>}
        {!verif.dados ? <Carregando /> : (
          <div className="panel-body">
            <small>
              {verif.dados.rodou_em ? `Última verificação ${relativo(verif.dados.rodou_em)} (${dataHora(verif.dados.rodou_em)})` : "Ainda não verificado."}
              {Object.keys(verif.dados.commits).length > 0 && ` · commits: ${Object.entries(verif.dados.commits).map(([o, c]) => `${o} ${curto(c)}`).join(", ")}`}
            </small>
            {verif.dados.problemas.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 14 }}>
                <table>
                  <thead><tr><th>Problema</th><th>Nota</th><th>Detalhe</th><th>Desde</th></tr></thead>
                  <tbody>
                    {problemas.visiveis.map((p, i) => (
                      <tr key={i}>
                        <td className={p.tipo === "possivel_segredo" ? "red" : ""}>{TIPOS[p.tipo] ?? p.tipo}</td>
                        <td>{p.nota ? <button className="textbtn" onClick={() => abrir(p.nota!)}>{p.nota.split("/").slice(2).join("/")}</button> : "—"}</td>
                        <td style={{ whiteSpace: "normal" }}>{p.detalhe}</td>
                        <td>{relativo(p.desde)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {problemas.rodape}
              </div>
            )}
          </div>
        )}
      </section>

      <div className="split section-gap">
        <section className="panel">
          <div className="panel-head" style={{ paddingBottom: 8 }}>
            <h2>Notas</h2>
            <small>{s.sinais.notas}</small>
          </div>
          <div className="search" style={{ margin: "0 16px", maxWidth: "none" }}>
            <Icone nome="search" />
            <input type="search" aria-label="Buscar nota" placeholder="Buscar nota" value={busca} onChange={(e) => setBusca(e.target.value)} />
          </div>
          {arvore.erro && <div className="panel-body"><Falha erro={arvore.erro} tentar={arvore.recarregar} /></div>}
          {!arvore.dados ? <Carregando /> : arvore.dados.pastas.length === 0 ? (
            <Vazio titulo="Nenhuma nota ainda">O curador escreve as notas depois do primeiro pull.</Vazio>
          ) : (
            <nav className="tree" aria-label="Notas por pasta">
              {pastas.map((p) => <Pasta key={p.pasta} pasta={p.pasta} notas={p.notas} aberta={aberta} abrir={abrir} />)}
              <h3>Do curador</h3>
              <button className={aberta === "_meta/registro" ? "active" : ""} onClick={() => abrir("_meta/registro")}><Icone nome="clock" />Registro</button>
              <button className={aberta === "_meta/conflitos" ? "active" : ""} onClick={() => abrir("_meta/conflitos")}><Icone nome="alert" />Conflitos</button>
            </nav>
          )}
        </section>
        <section className="panel" aria-live="polite">
          {!aberta ? (
            <Vazio titulo="Escolha uma nota">Cada nota mostra de que arquivos e de que commit veio, e abre a origem no GitHub.</Vazio>
          ) : aberta.startsWith("_meta/") ? (
            <Meta tag={s.tag} nome={aberta.slice(6)} />
          ) : (
            <LerNota tag={s.tag} chave={aberta} />
          )}
        </section>
      </div>
    </>
  );
}

function Markdown({ texto }: { texto: string }) {
  return (
    <div className="nota">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith("?nota=") ? <Link to={href}>{children}</Link> : <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
        }}
      >
        {preparar(texto)}
      </ReactMarkdown>
    </div>
  );
}

function LerNota({ tag, chave }: { tag: string; chave: string }) {
  const { dados: n, erro } = useDados<Nota>(`/sistemas/${tag}/notas/${chave.split("/").map(encodeURIComponent).join("/")}`);
  if (erro) return <div className="panel-body" style={{ paddingTop: 22 }}><Falha erro={erro} /></div>;
  if (!n) return <Carregando />;
  return (
    <article>
      <div className="panel-head">
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{PASTAS[n.pasta] ?? n.pasta}{n.tipo_nota && n.tipo_nota !== n.pasta ? ` · ${n.tipo_nota}` : ""}</div>
          <h2>{n.titulo ?? n.chave.split("/").pop()}</h2>
          <small className="mono">{n.chave}.md</small>
        </div>
        <Badge tipo="neutral">Gerada pelo curador</Badge>
      </div>
      <div className="cabecalho">
        <ul className="kv" style={{ fontSize: 12 }}>
          <li><span>Atualizada</span><span>{dataHora(n.atualizado_em)}{n.criado_em && ` · criada ${dataHora(n.criado_em)}`}</span></li>
          <li><span>Commit de origem</span><span className="mono">{curto(n.commit_origem)}</span></li>
          <li>
            <span>Origem</span>
            <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
              {n.origens.length === 0 ? "—" : n.origens.map((o) => (
                <LinkExterno key={o.ref} href={o.url}><span className="mono">{o.ref}</span></LinkExterno>
              ))}
            </span>
          </li>
        </ul>
      </div>
      {n.problemas.length > 0 && (
        <div className="banner warn" style={{ margin: "12px 26px 0" }}>
          <Icone nome="alert" />
          <div>{n.problemas.map((p, i) => <div key={i}>{TIPOS[p.tipo] ?? p.tipo}: {p.detalhe}</div>)}</div>
        </div>
      )}
      {n.itens_na_fila.length > 0 && (
        <div className="banner" style={{ margin: "12px 26px 0" }}>
          <Icone nome="clock" />
          <span>{plural(n.itens_na_fila.length, "arquivo de origem desta nota mudou", "arquivos de origem desta nota mudaram")} e {n.itens_na_fila.length === 1 ? "está" : "estão"} na fila: a nota pode mudar na próxima rodada.</span>
        </div>
      )}
      <Markdown texto={n.conteudo} />
    </article>
  );
}

function Meta({ tag, nome }: { tag: string; nome: string }) {
  const { dados, erro } = useDados<{ nome: string; conteudo: string | null }>(`/sistemas/${tag}/${nome}`);
  if (erro) return <div className="panel-body" style={{ paddingTop: 22 }}><Falha erro={erro} /></div>;
  if (!dados) return <Carregando />;
  return (
    <article>
      <div className="panel-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Do curador</div>
          <h2>{nome === "registro" ? "Registro" : "Conflitos"}</h2>
          <small>{nome === "registro" ? "O que o curador fez com cada arquivo da fila." : "Onde código e documentação discordam, com as origens."}</small>
        </div>
      </div>
      {dados.conteudo ? <Markdown texto={dados.conteudo} /> : <Vazio titulo={nome === "registro" ? "Registro vazio" : "Nenhum conflito registrado"} />}
    </article>
  );
}

const POR_PASTA = 15;

/** Uma pasta da árvore: as primeiras 15 notas e "Mostrar mais" (um repositório de
 *  código pode gerar centenas de regras). A nota aberta aparece mesmo fora da página. */
function Pasta({ pasta, notas, aberta, abrir }: { pasta: string; notas: NotaResumo[]; aberta: string | null; abrir: (c: string) => void }) {
  const [n, setN] = useState(POR_PASTA);
  const visiveis = notas.slice(0, n);
  const fora = notas.find((x) => x.chave === aberta && !visiveis.includes(x));
  return (
    <div>
      <h3>{PASTAS[pasta] ?? pasta} ({notas.length})</h3>
      {(fora ? [...visiveis, fora] : visiveis).map((x) => (
        <button key={x.chave} className={aberta === x.chave ? "active" : ""} aria-current={aberta === x.chave ? "true" : undefined} onClick={() => abrir(x.chave)}>
          <Icone nome="file" />
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{x.titulo || x.chave.split("/").pop()}</span>
          {x.problemas > 0 && <Badge tipo="warn">{x.problemas}</Badge>}
        </button>
      ))}
      {notas.length > n && (
        <MaisLinhasArvore mostrando={n} total={notas.length} mais={() => setN(n + POR_PASTA * 2)} />
      )}
    </div>
  );
}

function MaisLinhasArvore({ mostrando, total, mais }: { mostrando: number; total: number; mais: () => void }) {
  return (
    <button className="textbtn mais-arvore" onClick={mais}>
      Mostrar mais ({total - mostrando} {total - mostrando === 1 ? "restante" : "restantes"})
    </button>
  );
}
