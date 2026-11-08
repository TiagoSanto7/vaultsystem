import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Sistema } from "../api";
import { Badge, LinkExterno, Modal, useAviso } from "../componentes";
import { curto, dataHora, plural, relativo, repoCurto } from "../formato";
import { Icone } from "../icones";
import { Sinais } from "../sinais";

export default function VisaoGeral({ s, recarregar }: { s: Sistema; recarregar: () => void }) {
  const base = `/sistemas/${s.tag}`;
  const r = s.ultima_rodada;
  const p = s.ultimo_pull;
  const [remover, setRemover] = useState(false);

  return (
    <>
      <div className="columns">
        <section className="panel">
          <div className="panel-head" style={{ display: "block" }}>
            <h2 style={{ marginBottom: 8 }}>Do commit à nota</h2>
            <Sinais s={s} />
          </div>
          <div className="pipeline">
            <Link className="stage" to={`${base}/fontes`}><span><Icone nome="git" /></span><strong>{s.origens.length}</strong>Origens</Link>
            <i />
            <Link className="stage" to={`${base}/fontes#fila`}><span><Icone nome="clock" /></span><strong>{s.sinais.fila.itens}</strong>Na fila</Link>
            <i />
            <Link className="stage" to={`${base}/processamento`}><span><Icone nome="spark" /></span><strong>{r ? `#${r.rodada_id}` : "—"}</strong>Última rodada</Link>
            <i />
            <Link className="stage" to={`${base}/conhecimento`}><span><Icone nome="book" /></span><strong>{s.sinais.notas}</strong>Notas</Link>
            <i />
            <Link className="stage" to={`${base}/conhecimento#verificacao`}><span><Icone nome="shield" /></span><strong>{s.sinais.verificacao.total ?? "—"}</strong>Problemas</Link>
          </div>
          {s.origens.map((o) => (
            <div key={o.nome} className="row">
              <span className="sysicon"><Icone nome="git" /></span>
              <div className="info">
                <LinkExterno href={o.url}>{repoCurto(o.repo)}</LinkExterno>
                <small>
                  {o.nome} · ramo {o.ramo} · {o.leituras.map((l) => l.perfil).join(" + ")} · processado até{" "}
                  <LinkExterno href={o.commit_processado.url}>{curto(o.commit_processado.hash)}</LinkExterno>
                  {o.commit_processado.data && ` (${dataHora(o.commit_processado.data)})`}
                </small>
              </div>
              <Badge tipo={o.situacao === "em_dia" ? "" : o.situacao === "sem_acesso" ? "erro" : o.situacao === "atrasado" ? "warn" : "neutral"}>
                {{ em_dia: "Em dia", atrasado: `Atrasada${o.commits_atras ? ` ${o.commits_atras}` : ""}`, nunca_processado: "Nunca processada", sem_acesso: "Sem acesso", removendo: "Removendo" }[o.situacao]}
              </Badge>
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="panel-head"><h2>Atividade</h2></div>
          <div className="panel-body">
            <ul className="kv">
              <li>
                <span>Último pull</span>
                <span>{p ? <>#{p.id} {p.estado === "pedido" ? "pedido" : relativo(p.atendido_em)}{p.erro && <span className="red"> · com erro</span>}</> : "nenhum"}</span>
              </li>
              {p && p.estado === "concluido" && (
                <li>
                  <span>Trouxe</span>
                  <span>{Object.entries(p.itens).map(([k, v]) => `${v} ${k}`).join(", ") || "nada novo"}{p.ignorados ? ` · ${p.ignorados} ignorado(s)` : ""}</span>
                </li>
              )}
              <li><span>Última rodada</span><span>{r ? <Link className="textbtn" to={`${base}/processamento`}>#{r.rodada_id} · {relativo(r.fim ?? r.inicio)}</Link> : "nenhuma"}</span></li>
              {r?.ultimo_lote && (
                <li>
                  <span>Último lote</span>
                  <span>{r.ultimo_lote.perfil}: {r.ultimo_lote.registrados ?? 0} de {r.ultimo_lote.itens} registrados{r.ultimo_lote.erro && <span className="red"> · erro</span>}</span>
                </li>
              )}
              <li><span>Curador agora</span><span>{s.lote_atual ? <><i className="dot pulse" /> lendo {plural(s.lote_atual.itens, "item", "itens")} ({s.lote_atual.perfil})</> : "parado"}</span></li>
              <li><span>Cadastrado</span><span>{dataHora(s.cadastro.em)} por {s.cadastro.por}</span></li>
            </ul>
          </div>
        </section>
      </div>

      <section className="panel section-gap">
        <div className="panel-head">
          <div>
            <h2>Remover vault</h2>
            <small>Tira o vault do hub: apaga a pasta do vault, o clone e o cadastro. As origens (pasta enviada ou repositório Git) não são tocadas.</small>
          </div>
          <button className="btn danger" onClick={() => setRemover(true)} disabled={!!s.removido_em}>
            {s.removido_em ? "Remoção pedida" : "Remover…"}
          </button>
        </div>
      </section>
      {remover && <ConfirmarRemocao tag={s.tag} fechar={() => setRemover(false)} feito={recarregar} />}
    </>
  );
}

function ConfirmarRemocao({ tag, fechar, feito }: { tag: string; fechar: () => void; feito: () => void }) {
  const [digitado, setDigitado] = useState("");
  const [enviando, setEnviando] = useState(false);
  const avisar = useAviso();
  const ir = useNavigate();
  async function remover() {
    setEnviando(true);
    try {
      await api(`/sistemas/${tag}`, { metodo: "DELETE" });
      avisar(`Remoção de ${tag} pedida. O curador conclui em até 30 s.`);
      feito();
      ir("/sistemas");
    } catch (x) {
      avisar((x as Error).message);
      setEnviando(false);
    }
  }
  return (
    <Modal titulo={`Remover ${tag}?`} aoFechar={fechar}>
      <p>As notas de <b>{tag}</b> saem do vault (com commit, fica no histórico do git), e as credenciais deixam de achar o vault. Para confirmar, digite a tag.</p>
      <label htmlFor="confirma-tag">Tag</label>
      <input id="confirma-tag" className="mono" value={digitado} onChange={(e) => setDigitado(e.target.value)} />
      <div className="modal-actions">
        <button className="btn" onClick={fechar}>Cancelar</button>
        <button className="btn danger" disabled={digitado !== tag || enviando} onClick={remover}>Remover vault</button>
      </div>
    </Modal>
  );
}
