import { FormEvent, useEffect, useState } from "react";
import { api, Ignorados, ItemFila, Origem, Pull, Sistema } from "../api";
import { Badge, Carregando, Falha, LinkExterno, MaisLinhas, Modal, useAviso, Vazio } from "../componentes";
import { CarregandoArvore, ClassificarArvore, Classificacao, ConfirmarImpacto, MD, PreviaMudancas, ROTULO, useLeituras } from "../Arvore";
import { useAncora, useDados } from "../dados";
import { CamposOrigem, ExplicacaoChave, origemDaApi, origemParaApi, origemVazia, TrocarAcesso } from "../FormOrigem";
import { curto, dataHora, plural, relativo, repoCurto } from "../formato";
import { Icone } from "../icones";

const SITUACAO = {
  em_dia: { texto: "Em dia", tipo: "" },
  atrasado: { texto: "Atrasada", tipo: "warn" },
  nunca_processado: { texto: "Nunca processada", tipo: "neutral" },
  sem_acesso: { texto: "Sem acesso", tipo: "erro" },
  removendo: { texto: "Removendo", tipo: "neutral" },
} as const;

const PAGINA = 20;

export default function Fontes({ s, recarregar }: { s: Sistema; recarregar: () => void }) {
  const [adicionar, setAdicionar] = useState(false);
  const [editar, setEditar] = useState<Origem | null>(null);
  const [remover, setRemover] = useState<Origem | null>(null);
  const ativas = s.origens.filter((o) => !o.removida_em).length;
  const [limiteFila, setLimiteFila] = useState(PAGINA);
  const [limitePulls, setLimitePulls] = useState(10);
  const fila = useDados<{ total: number; parados: number; itens: ItemFila[] }>(`/sistemas/${s.tag}/fila?limite=${limiteFila}`, 15000, true);
  // A API de pulls não devolve o total: se veio a página cheia, pode haver mais.
  const pulls = useDados<Pull[]>(`/sistemas/${s.tag}/pulls?limite=${limitePulls + 1}`, 15000, true);
  const ultimoConcluido = pulls.dados?.find((p) => p.estado === "concluido");
  const ign = useDados<Pull & { ignorados: Ignorados }>(ultimoConcluido ? `/sistemas/${s.tag}/pulls/${ultimoConcluido.id}` : null);
  useAncora(!!fila.dados && !!pulls.dados);
  const avisar = useAviso();

  async function retomar(i: ItemFila) {
    try {
      await api(`/sistemas/${s.tag}/fila/${i.id}/retomar`, { metodo: "POST" });
      avisar(`${i.caminho} volta à fila na próxima rodada.`);
      fila.recarregar();
      recarregar();
    } catch (x) {
      avisar((x as Error).message);
    }
  }

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Repositórios</h2>
            <small>Vários repositórios, um contexto compartilhado. O curador verifica cada um a cada rodada.</small>
          </div>
          <button className="btn" onClick={() => setAdicionar(true)} disabled={!!s.removido_em}><Icone nome="plus" />Adicionar repositório</button>
        </div>
        {s.origens.map((o) => {
          const sit = SITUACAO[o.situacao];
          return (
            <div key={o.nome} className="row" style={{ alignItems: "flex-start" }}>
              <span className="sysicon"><Icone nome="git" /></span>
              <div className="info">
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <LinkExterno href={o.url}>{repoCurto(o.repo)}</LinkExterno>
                  <Badge tipo={sit.tipo}>{sit.texto}{o.situacao === "atrasado" && o.commits_atras ? ` · ${plural(o.commits_atras, "commit", "commits")}` : ""}</Badge>
                </div>
                <small>Origem <b style={{ fontWeight: 500 }}>{o.nome}</b> · ramo {o.ramo}</small>
                {o.leituras_antes && !o.removida_em && (
                  <small><Badge tipo="warn">Leituras alteradas</Badge> O vault é ajustado no próximo pull (já pedido).</small>
                )}
                {o.removida_em && <small>Remoção pedida {relativo(o.removida_em)}: o que veio dela sai do vault, e a origem some quando a fila dela esvaziar.</small>}
                <ul className="kv" style={{ marginTop: 10, fontSize: 12 }}>
                  <li>
                    <span>Acesso</span>
                    <span className={o.acesso.ok === false ? "red" : ""}>
                      {o.acesso.ok === null ? "ainda não testado" : o.acesso.ok ? `ok ${relativo(o.acesso.em)}` : `falhou ${relativo(o.acesso.em)}: ${o.acesso.erro ?? ""}`}
                    </span>
                  </li>
                  <li>
                    <span>Processado até</span>
                    <span><LinkExterno href={o.commit_processado.url}>{curto(o.commit_processado.hash)}</LinkExterno> {o.commit_processado.data && `· ${dataHora(o.commit_processado.data)}`}</span>
                  </li>
                  {o.commit_pendente.hash && o.commit_pendente.hash !== o.commit_processado.hash && (
                    <li>
                      <span>Na fila até</span>
                      <span><LinkExterno href={o.commit_pendente.url}>{curto(o.commit_pendente.hash)}</LinkExterno> {o.commit_pendente.data && `· ${dataHora(o.commit_pendente.data)}`}</span>
                    </li>
                  )}
                  {o.classificacao ? (<>
                    {/* DV-589: origem classificada pela árvore; os padrões gerados ficam por trás. */}
                    {(Object.keys(ROTULO) as (keyof typeof ROTULO)[]).map((k) => {
                      const nos = Object.entries(o.classificacao!).filter(([c, v]) => v === k && c !== MD).map(([c]) => c);
                      if (!nos.length) return null;
                      const raiz = nos.includes("");
                      // Arquivo: o nome tem extensão (".superpowers" é pasta).
                      const pastas = nos.filter((c) => c && !/^[^.].*\.[^.]+$/.test(c.split("/").pop()!));
                      const arquivos = nos.length - pastas.length - (raiz ? 1 : 0);
                      return (
                        <li key={k}>
                          <span>{ROTULO[k][0].toUpperCase() + ROTULO[k].slice(1)}</span>
                          <span>
                            {raiz && "a raiz"}{raiz && (pastas.length || arquivos) ? " e " : ""}
                            {pastas.length > 0 && <code>{pastas.map((c) => `${c}/`).join(", ")}</code>}
                            {arquivos > 0 && <>{pastas.length ? " e " : ""}{plural(arquivos, "arquivo solto", "arquivos soltos")}</>}
                          </span>
                        </li>
                      );
                    })}
                    {o.classificacao[MD] === "documentos" && (
                      <li><span>Arquivos .md</span><span>documentos, em qualquer pasta que não seja ignorada</span></li>
                    )}
                  </>) : o.leituras.map((l, i) => (
                    <li key={i}>
                      <span>Leitura {o.leituras.length > 1 ? i + 1 : ""}</span>
                      <span>
                        <b style={{ fontWeight: 500 }}>{l.perfil}</b>
                        {l.incluir.length > 0 && <> · incluir <code>{l.incluir.join(", ")}</code></>}
                        {l.excluir.length > 0 && <> · excluir <code>{l.excluir.join(", ")}</code></>}
                        {!l.incluir.length && !l.excluir.length && " · tudo"}
                      </span>
                    </li>
                  ))}
                </ul>
                {!o.removida_em && !s.removido_em && (
                  <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
                    <button type="button" className="textbtn" onClick={() => setEditar(o)}>{doApp(o.repo) ? "Editar ramo e pastas" : "Editar ramo e leituras"}</button>
                    {ativas > 1 && <button type="button" className="textbtn" onClick={() => setRemover(o)}>Remover origem</button>}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </section>

      <section className="panel section-gap" id="fila">
        <div className="panel-head">
          <div>
            <h2>Fila</h2>
            <small>Arquivos que mudaram e esperam o curador. Um item que falha volta para o fim da fila, num lote menor. Depois de várias tentativas, fica “parado” e o curador segue sem ele.</small>
          </div>
          {fila.dados && <Badge tipo={fila.dados.parados ? "warn" : "neutral"}>{plural(fila.dados.total, "item", "itens")}{fila.dados.parados ? ` · ${fila.dados.parados} parado(s)` : ""}</Badge>}
        </div>
        {fila.erro && <div className="panel-body"><Falha erro={fila.erro} tentar={fila.recarregar} /></div>}
        {!fila.dados ? <Carregando /> : fila.dados.total === 0 ? (
          <Vazio titulo="Fila vazia">Tudo o que chegou já foi registrado pelo curador.</Vazio>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Arquivo</th><th>Ação</th><th>Origem · perfil</th><th>Commit</th><th>Desde</th><th>Tentativas</th></tr></thead>
              <tbody>
                {fila.dados.itens.map((i) => (
                  <tr key={i.id}>
                    <td><LinkExterno href={i.url}><span className="mono">{i.caminho}</span></LinkExterno>{i.motivo && <small>{i.motivo}</small>}</td>
                    <td>{i.acao}</td>
                    <td>{i.origem} · {i.perfil}</td>
                    <td className="mono">{curto(i.commit)}</td>
                    <td>{relativo(i.desde)}</td>
                    <td>
                      {i.parado ? <Badge tipo="warn">{i.tentativas} · parado</Badge> : i.tentativas}
                      {i.erro && <small title={i.erro}>{i.erro}</small>}
                      {i.parado && <button type="button" className="textbtn" onClick={() => retomar(i)}>Tentar de novo</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <MaisLinhas mostrando={fila.dados.itens.length} total={Math.min(fila.dados.total, 1000)} passo={PAGINA} mais={() => setLimiteFila(limiteFila + PAGINA)} />
          </div>
        )}
      </section>

      <section className="panel section-gap" id="ignorados">
        <div className="panel-head">
          <div>
            <h2>Ignorados no último pull</h2>
            <small>Arquivos que não entram no conhecimento, e por quê. Segredos são mascarados antes de qualquer leitura.</small>
          </div>
          {ign.dados && <Badge tipo="neutral">{plural(ign.dados.ignorados.total, "arquivo", "arquivos")}{ign.dados.ignorados.mascarados ? ` · ${plural(ign.dados.ignorados.mascarados, "segredo mascarado", "segredos mascarados")}` : ""}</Badge>}
        </div>
        {!ultimoConcluido ? (
          <Vazio titulo="Nenhum pull concluído ainda" />
        ) : !ign.dados ? <Carregando /> : ign.dados.ignorados.total === 0 ? (
          <Vazio titulo="Nada ignorado">O pull #{ultimoConcluido.id} aproveitou todos os arquivos que mudaram.</Vazio>
        ) : (
          <div className="panel-body">
            {ign.dados.ignorados.por_motivo.map((g) => (
              <details key={g.motivo} style={{ borderTop: "1px solid var(--line)", padding: "12px 0" }}>
                <summary style={{ cursor: "pointer" }}>{g.motivo} <span className="muted">({g.quantos})</span></summary>
                <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 12 }}>
                  {g.arquivos.slice(0, 200).map((a, n) => <li key={n}><span className="mono">{a.origem && a.origem !== "principal" ? `${a.origem}:` : ""}{a.caminho}</span> <span className="muted">— {a.motivo}</span></li>)}
                </ul>
              </details>
            ))}
          </div>
        )}
      </section>

      <section className="panel section-gap" id="pulls">
        <div className="panel-head"><h2>Pulls</h2></div>
        {!pulls.dados ? <Carregando /> : pulls.dados.length === 0 ? (
          <Vazio titulo="Nenhum pull ainda">Peça o primeiro pull no topo da página. O curador também verifica sozinho a cada rodada.</Vazio>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Pull</th><th>Pedido</th><th>Atendido</th><th>Trouxe</th><th>Commits</th></tr></thead>
              <tbody>
                {pulls.dados.slice(0, limitePulls).map((p) => (
                  <tr key={p.id}>
                    <td>#{p.id}{p.erro && <small className="red">{p.erro}</small>}</td>
                    <td>{dataHora(p.pedido_em)}<small>por {p.pedido_por}</small></td>
                    <td>{p.atendido_em ? dataHora(p.atendido_em) : <Badge tipo="neutral">aguardando</Badge>}</td>
                    <td>{Object.entries(p.itens).map(([k, v]) => `${v} ${k}`).join(", ") || (p.atendido_em ? "nada novo" : "—")}{p.ignorados ? <small>{p.ignorados} ignorado(s)</small> : null}</td>
                    <td className="mono">
                      {Object.entries(p.origens).map(([o, v]) => (
                        <div key={o}>{o}: {v.nada_novo ? "nada novo" : `${curto(v.de)} → ${curto(v.para)}`}{v.erro && <span className="red"> {v.erro}</span>}</div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {pulls.dados.length > limitePulls && limitePulls < 500 && (
              <div className="table-foot">
                <small>Mostrando os {limitePulls} mais recentes</small>
                <button className="textbtn" onClick={() => setLimitePulls(limitePulls + 10)}>Mostrar mais 10</button>
              </div>
            )}
          </div>
        )}
      </section>

      {editar && doApp(editar.repo) && <EditarPelaArvore tag={s.tag} origem={editar} fechar={() => setEditar(null)} feito={recarregar} />}
      {editar && !doApp(editar.repo) && <EditarOrigem tag={s.tag} origem={editar} fechar={() => setEditar(null)} feito={recarregar} />}
      {remover && <RemoverOrigem tag={s.tag} origem={remover} fechar={() => setRemover(null)} feito={recarregar} />}
      {adicionar && <AdicionarOrigem tag={s.tag} existentes={s.origens.map((o) => o.nome)} fechar={() => setAdicionar(false)} feito={recarregar} />}
    </>
  );
}

const doApp = (repo: string) => repo.startsWith("https://github.com/");

/** Pede a árvore de repo/ramo (de novo quando mudam). null enquanto não há repositório. */
function usePedidoArvore(repo: string, ramo: string) {
  const [id, setId] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    setId(null);
    setErro(null);
    if (!doApp(repo) || !ramo) return;
    let vivo = true;
    api<{ id: number }>("/arvores", { metodo: "POST", corpo: { repo, ramo } })
      .then((r) => vivo && setId(r.id))
      .catch((e) => vivo && setErro((e as Error).message));
    return () => { vivo = false; };
  }, [repo, ramo]);
  return { id, erro };
}

function AdicionarOrigem({ tag, existentes, fechar, feito }: { tag: string; existentes: string[]; fechar: () => void; feito: () => void }) {
  const [o, setO] = useState(origemVazia(existentes.includes("principal") ? "documentacao" : "principal"));
  // DV-589: repositório do App passa pela árvore antes de adicionar, como no Novo vault.
  const [pastas, setPastas] = useState(false);
  const [classes, setClasses] = useState<Classificacao | undefined>();
  const arvore = usePedidoArvore(pastas ? o.repo : "", o.ramo);
  const previa = useLeituras(arvore.id, classes);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const avisar = useAviso();
  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (o.acesso === "app" && !pastas) {
      setClasses(undefined);
      return setPastas(true);
    }
    setEnviando(true);
    setErro(null);
    try {
      const base = origemParaApi(o);
      const corpo = o.acesso === "app" ? { ...base, leituras: previa.r!.leituras, classificacao: classes } : base;
      if (o.acesso === "app" && previa.r!.leituras.length === 0) throw new Error("Nada deste repositório vai para documentos ou código.");
      await api(`/sistemas/${tag}/origens`, { metodo: "POST", corpo });
      avisar(`Origem ${o.nome} adicionada a ${tag}.`);
      feito();
      fechar();
    } catch (x) {
      setErro((x as Error).message);
      setEnviando(false);
    }
  }
  const prontas = !pastas || !!previa.r;
  return (
    <Modal titulo={pastas ? `O que ler de ${o.repo.replace("https://github.com/", "")}` : "Adicionar repositório"} aoFechar={fechar} largura={pastas ? 900 : 760}>
      <p>
        {pastas
          ? "Cada pasta vai para documentos, código ou fica de fora. A subpasta segue a pasta de cima, a menos que você mude."
          : `Mais um repositório para ${tag}: por exemplo, o repositório de documentação de um vault cujo código já está aqui.`}
      </p>
      <form onSubmit={enviar} noValidate>
        {pastas ? (
          arvore.erro ? <div className="banner erro" role="alert"><Icone nome="alert" /><div>{arvore.erro}</div></div>
            : arvore.id === null ? <Carregando texto="Pedindo as pastas…" />
            : (
              <CarregandoArvore id={arvore.id} aoCarregar={(r) => setClasses((c) => c ?? r.sugestao ?? { "": "codigo-literal" })}>
                {(r) => <ClassificarArvore r={r} valor={classes ?? r.sugestao ?? { "": "codigo-literal" }} mudar={setClasses} />}
              </CarregandoArvore>
            )
        ) : (
          <>
            <CamposOrigem id="nova" valor={o} mudar={setO} semLeituras={o.acesso === "app"} />
            {o.acesso === "chave" && <ExplicacaoChave tag={tag} origem={o.nome || "<origem>"} />}
          </>
        )}
        {(erro || previa.erro) && <div className="erro-campo" role="alert">{erro || previa.erro}</div>}
        <div className="modal-actions">
          {pastas
            ? <button type="button" className="btn" onClick={() => setPastas(false)}><Icone nome="back" />Voltar</button>
            : <button type="button" className="btn" onClick={fechar}>Cancelar</button>}
          <button className="btn primary" type="submit" disabled={enviando || !o.repo.trim() || !o.nome.trim() || !prontas}>
            {o.acesso === "app" && !pastas
              ? <>Continuar<Icone nome="arrow" /></>
              : <><Icone nome="check" />{enviando ? "Adicionando…" : prontas ? "Adicionar" : "Carregando as pastas…"}</>}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Editar uma origem do App (DV-589): a árvore com a classificação de hoje e,
 * antes de salvar, os arquivos que mudam de destino. */
function EditarPelaArvore({ tag, origem, fechar, feito }: { tag: string; origem: Origem; fechar: () => void; feito: () => void }) {
  const [o, setO] = useState(origemDaApi(origem));
  const arvore = usePedidoArvore(origem.repo, o.ramo);
  const [atual, setAtual] = useState<{ classificacao: Classificacao; gravada: boolean } | null>(null);
  const [classes, setClasses] = useState<Classificacao | undefined>();
  const previa = useLeituras(arvore.id, classes, { tag, origem: origem.nome });
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const avisar = useAviso();

  useEffect(() => {
    setAtual(null);
    setClasses(undefined);
  }, [arvore.id]);
  useEffect(() => setConfirmando(false), [previa.r]); // mudou a classificação: o custo confirmado não vale mais

  async function carregou() {
    try {
      const a = await api<{ classificacao: Classificacao; gravada: boolean }>(`/arvores/${arvore.id}/atual`, { metodo: "POST", corpo: { tag, origem: origem.nome } });
      setAtual(a);
      setClasses(a.classificacao);
    } catch (x) {
      setErro((x as Error).message);
    }
  }

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!previa.r) return;
    if (!confirmando && (previa.r.impacto?.ao_curador ?? 0) > 0) {  // DV-608: o custo antes do pull
      setConfirmando(true);
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      if (previa.r.leituras.length === 0) throw new Error("Nada deste repositório vai para documentos ou código.");
      await api(`/sistemas/${tag}/origens/${origem.nome}`, {
        metodo: "PUT", corpo: { repo: origem.repo, ramo: o.ramo, leituras: previa.r.leituras, classificacao: classes },
      });
      avisar(`Origem ${origem.nome} alterada. Pull pedido: o vault é ajustado na próxima rodada.`);
      feito();
      fechar();
    } catch (x) {
      setErro((x as Error).message);
      setEnviando(false);
    }
  }

  const mudou = o.ramo !== origem.ramo || (previa.r?.total_mudancas ?? 0) > 0;
  return (
    <Modal titulo={`Editar a origem ${origem.nome}`} aoFechar={fechar} largura={900}>
      <p>
        A árvore abre como o vault está hoje. Mude o destino das pastas ou arquivos: antes de salvar, aparece cada arquivo
        que muda de destino. Cancelar não muda nada.
      </p>
      <form onSubmit={enviar} noValidate>
        <CamposOrigem id="editar" valor={o} mudar={setO} nomeFixo repoFixo semLeituras />
        {atual && !atual.gravada && (
          <small className="muted" style={{ display: "block", marginTop: 12 }}>
            Esta origem foi cadastrada com padrões de incluir/excluir: a árvore abaixo foi montada a partir deles e leva cada
            arquivo exatamente aonde eles levam hoje.
          </small>
        )}
        <div style={{ marginTop: 12 }}>
          {arvore.erro ? <div className="banner erro" role="alert"><Icone nome="alert" /><div>{arvore.erro}</div></div>
            : arvore.id === null ? <Carregando texto="Pedindo as pastas…" />
            : (
              <CarregandoArvore id={arvore.id} aoCarregar={carregou}>
                {(r) => (classes ? <ClassificarArvore r={r} valor={classes} mudar={setClasses} /> : <Carregando texto="Montando a classificação de hoje…" />)}
              </CarregandoArvore>
            )}
        </div>
        {previa.r && <PreviaMudancas r={previa.r} />}
        {(erro || previa.erro) && <div className="erro-campo" role="alert">{erro || previa.erro}</div>}
        {confirmando && previa.r?.impacto ? (
          <ConfirmarImpacto tag={tag} i={previa.r.impacto} voltar={() => setConfirmando(false)} enviando={enviando} />
        ) : (
          <div className="modal-actions">
            <button type="button" className="btn" onClick={fechar}>Cancelar</button>
            <button className="btn primary" type="submit" disabled={enviando || !previa.r || !mudou}
              title={!previa.r ? "Espere as pastas carregarem" : !mudou ? "Nada mudou" : undefined}>
              <Icone nome="check" />{enviando ? "Salvando…" : !previa.r ? "Carregando as pastas…" : mudou ? "Salvar e pedir pull" : "Nada mudou"}
            </button>
          </div>
        )}
      </form>
    </Modal>
  );
}

function EditarOrigem({ tag, origem, fechar, feito }: { tag: string; origem: Origem; fechar: () => void; feito: () => void }) {
  const [o, setO] = useState(origemDaApi(origem));
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const avisar = useAviso();
  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setErro(null);
    const { repo, ramo, leituras } = origemParaApi(o);
    try {
      await api(`/sistemas/${tag}/origens/${origem.nome}`, { metodo: "PUT", corpo: { repo, ramo, leituras } });
      avisar(`Origem ${origem.nome} alterada. Pull pedido: o vault é ajustado na próxima rodada.`);
      feito();
      fechar();
    } catch (x) {
      setErro((x as Error).message);
      setEnviando(false);
    }
  }
  return (
    <Modal titulo={`Editar a origem ${origem.nome}`} aoFechar={fechar} largura={760}>
      <p>
        Cada arquivo vai para a <b>primeira</b> leitura que o aceita. Ao salvar, o hub pede um pull e ajusta o vault:
        o que saiu das leituras sai do vault, o que entrou é lido, e o que mudou de leitura (por exemplo, de código para
        documentos) sai de uma e é lido de novo na outra.
      </p>
      <form onSubmit={enviar} noValidate>
        <CamposOrigem id="editar" valor={o} mudar={setO} nomeFixo repoFixo />
        <TrocarAcesso original={origem.repo} valor={o} mudar={setO} />
        {erro && <div className="erro-campo" role="alert">{erro}</div>}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={fechar}>Cancelar</button>
          <button className="btn primary" type="submit" disabled={enviando}>
            <Icone nome="check" />{enviando ? "Salvando…" : "Salvar e pedir pull"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function RemoverOrigem({ tag, origem, fechar, feito }: { tag: string; origem: Origem; fechar: () => void; feito: () => void }) {
  const [digitado, setDigitado] = useState("");
  const [enviando, setEnviando] = useState(false);
  const avisar = useAviso();
  async function remover() {
    setEnviando(true);
    try {
      await api(`/sistemas/${tag}/origens/${origem.nome}`, { metodo: "DELETE" });
      avisar(`Remoção da origem ${origem.nome} pedida.`);
      feito();
      fechar();
    } catch (x) {
      avisar((x as Error).message);
      setEnviando(false);
    }
  }
  return (
    <Modal titulo={`Remover a origem ${origem.nome}?`} aoFechar={fechar}>
      <p>As notas que vieram de <b>{repoCurto(origem.repo)}</b> saem do vault no próximo pull (com commit, fica no histórico do git). As outras origens de {tag} continuam. Para confirmar, digite o nome da origem.</p>
      <label htmlFor="confirma-origem">Origem</label>
      <input id="confirma-origem" className="mono" value={digitado} onChange={(e) => setDigitado(e.target.value)} />
      <div className="modal-actions">
        <button className="btn" onClick={fechar}>Cancelar</button>
        <button className="btn danger" disabled={digitado !== origem.nome || enviando} onClick={remover}>Remover origem</button>
      </div>
    </Modal>
  );
}
