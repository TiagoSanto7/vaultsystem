import { useState } from "react";
import { Link } from "react-router-dom";
import { Aviso, DetalheRodada, Rodada, Sistema } from "../api";
import { Badge, Carregando, Falha, MaisLinhas, Modal, usePagina, Vazio } from "../componentes";
import { useDados } from "../dados";
import { dataHora, hora, plural, proxima } from "../formato";
import { Icone } from "../icones";

interface Rodadas { rodadas: Rodada[]; total: number; lote_atual: Sistema["lote_atual"]; proxima_rodada: string | null }

const RESULTADO: Record<string, { texto: string; tipo: "" | "warn" | "erro" | "neutral" }> = {
  ok: { texto: "Ok", tipo: "" },
  com_erro: { texto: "Com erro", tipo: "erro" },
  com_avisos: { texto: "Com avisos", tipo: "warn" },
  nada: { texto: "Nada a processar", tipo: "neutral" },
  interrompida: { texto: "Interrompida", tipo: "warn" },
};

const PAGINA = 10;

// O que cada aviso quer dizer, para quem opera: o que houve, o que o código
// fez e se há algo a fazer. Um tipo novo em historico.aviso entra aqui também.
const EXPLICACAO: Record<string, { titulo: string; houve: string; fez: string; fazer: string }> = {
  fonte_inventada: {
    titulo: "Fonte inventada",
    houve: "O curador (a IA) citou como fonte um arquivo que não existe na origem com esse caminho. Quase sempre é o caminho escrito errado, por exemplo sem a pasta do começo.",
    fez: "Descartou essa fonte. A nota ficou só com as fontes que existem, então nunca aponta para um arquivo que não está no repositório.",
    fazer: "Nada. Se a nota ficou sem nenhuma fonte, aparece também o aviso \"Sem fontes\".",
  },
  sem_fontes: {
    titulo: "Sem fontes",
    houve: "Nenhuma das fontes que o curador citou existe na origem.",
    fez: "Ligou a nota aos arquivos do lote, que é de onde ela com certeza veio. A ligação é mais larga que o ideal, mas garante que, se esse arquivo mudar ou sair do repositório, a nota seja revista ou apagada.",
    fazer: "Nada.",
  },
  nota_nao_ligada: {
    titulo: "Nota não ligada",
    houve: "Num lote de arquivo modificado, o curador mudou uma nota que não estava ligada a esse arquivo. Pode estar certo (o que mudou afeta outra nota) ou ter ido além do pedido.",
    fez: "Manteve a mudança.",
    fazer: "Vale abrir a nota no Conhecimento e conferir se a mudança faz sentido.",
  },
  item_parado: {
    titulo: "Item parado",
    houve: "Um item da fila foi a vários lotes e o curador nunca o registrou, ou o arquivo dele sumiu e não deu para refazer.",
    fez: "Parou o item, para ele não travar o resto da fila. Enquanto ele estiver parado, a origem não fica em dia.",
    fazer: "Ver o erro do item na aba Fontes e usar \"Tentar de novo\".",
  },
  nota_interrompida: {
    titulo: "Nota interrompida",
    houve: "O curador foi desligado no meio de um lote e uma nota que ele já tinha escrito ficou sem o cabeçalho que o código completa no fim do lote.",
    fez: "Se as fontes da nota ainda são lidas como código, completou o cabeçalho. Se não são, apagou a nota e trocou os links para ela por texto. O conteúdo volta quando o arquivo for lido de novo pela leitura certa.",
    fazer: "Nada.",
  },
};

function AjudaAvisos({ tipos }: { tipos: string[] }) {
  const presentes = [...new Set(tipos)].filter((t) => EXPLICACAO[t]);
  if (presentes.length === 0) return null;
  return (
    <details className="ajuda">
      <summary>Ficou com dúvida? O que cada aviso quer dizer</summary>
      <p>Nenhum aviso para a fila nem apaga trabalho do curador: é o código dizendo o que corrigiu no que a IA escreveu.</p>
      {presentes.map((t) => (
        <div key={t}>
          <p><b style={{ fontWeight: 500 }}>{EXPLICACAO[t].titulo}</b> <code>{t}</code></p>
          <ul style={{ paddingLeft: 18 }}>
            <li>O que houve: {EXPLICACAO[t].houve}</li>
            <li>O que o código fez: {EXPLICACAO[t].fez}</li>
            <li>O que fazer: {EXPLICACAO[t].fazer}</li>
          </ul>
        </div>
      ))}
    </details>
  );
}

function duracao(inicio: string, fim: string | null) {
  if (!fim) return "em curso";
  const s = Math.max(0, Math.round((new Date(fim).getTime() - new Date(inicio).getTime()) / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

export default function Processamento({ s, pedirPull, pedindo }: { s: Sistema; pedirPull: () => void; pedindo: boolean }) {
  const [limite, setLimite] = useState(PAGINA);
  const [todas, setTodas] = useState(false);
  const { dados, erro, recarregar } = useDados<Rodadas>(`/sistemas/${s.tag}/rodadas?limite=${limite}&todas=${todas}`, 15000, true);
  const avisos = useDados<Aviso[]>(`/sistemas/${s.tag}/avisos?limite=200`, 30000);
  const paginaAvisos = usePagina(avisos.dados);
  const [aberta, setAberta] = useState<number | null>(null);

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Processamento</h2>
            <small>
              O curador roda sozinho a cada 15 minutos e atende os pulls pedidos em até 30 s.
              {dados?.proxima_rodada && ` Próxima rodada ${proxima(dados.proxima_rodada)} (${hora(dados.proxima_rodada)}).`}
            </small>
          </div>
          <button className="btn primary" onClick={pedirPull} disabled={pedindo || s.pull_pendente !== null || !!s.removido_em}>
            <Icone nome="play" />{s.pull_pendente !== null ? `Pull #${s.pull_pendente} pedido` : "Processar fontes"}
          </button>
        </div>
        <div className="panel-body">
          {s.lote_atual ? (
            <div className="banner" role="status">
              <i className="dot pulse" style={{ marginTop: 7 }} />
              <span>O curador está lendo {plural(s.lote_atual.itens, "item", "itens")} do perfil {s.lote_atual.perfil}, desde {hora(s.lote_atual.inicio)}.</span>
            </div>
          ) : s.pull_pendente !== null ? (
            <div className="banner" role="status"><Icone nome="clock" /><span>Pull #{s.pull_pendente} pedido; o curador atende em até 30 s.</span></div>
          ) : s.selo.estado === "erro_acesso" ? (
            <div className="banner erro" role="status">
              <Icone nome="alert" />
              <span>
                Nada para processar: o último pull não conseguiu ler o repositório ({s.selo.texto.replace(/^Sem acesso ao repositório: /, "origem ")}).{" "}
                <Link to={`/sistemas/${s.tag}/fontes`}>Ver em Fontes</Link>
              </span>
            </div>
          ) : (
            <small>Nada em andamento agora.</small>
          )}
        </div>
      </section>

      <section className="panel section-gap">
        <div className="panel-head">
          <div>
            <h2>Rodadas</h2>
            <small>{todas ? "Todas as rodadas que incluíram este vault." : "Só as rodadas em que o curador leu algo deste vault."} Clique numa rodada para ver os lotes e os avisos.</small>
          </div>
          <label className="check">
            <input type="checkbox" checked={todas} onChange={(e) => { setTodas(e.target.checked); setLimite(PAGINA); }} />
            Incluir rodadas sem nada a processar
          </label>
        </div>
        {erro && <div className="panel-body"><Falha erro={erro} tentar={recarregar} /></div>}
        {!dados ? <Carregando /> : dados.rodadas.length === 0 ? (
          <Vazio titulo={todas ? "Nenhuma rodada com este vault ainda" : "O curador ainda não leu nada deste vault"}>
            Depois de um pull com arquivos novos, o curador lê a fila na próxima rodada.
          </Vazio>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Rodada</th><th>Início</th><th>Duração</th><th>Lotes</th><th>Registrados</th><th>Avisos</th><th>Resultado</th></tr></thead>
              <tbody>
                {dados.rodadas.map((r) => {
                  const res = r.fim ? (r.resultado === "interrompida" ? RESULTADO.interrompida : r.com_erro ? RESULTADO.com_erro : r.avisos ? RESULTADO.com_avisos : r.lotes ? RESULTADO.ok : RESULTADO.nada) : { texto: "Em curso", tipo: "neutral" as const };
                  return (
                    <tr key={r.id} className="clicavel" tabIndex={0} onClick={() => setAberta(r.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setAberta(r.id)}>
                      <td>#{r.id}<small>{r.modo === "pedidos" ? "pull pedido" : "automática"}</small></td>
                      <td>{dataHora(r.inicio)}</td>
                      <td>{duracao(r.inicio, r.fim)}</td>
                      <td>{r.lotes}</td>
                      <td>{r.registrados} de {r.itens}</td>
                      <td>{r.avisos || "—"}</td>
                      <td><Badge tipo={res.tipo}>{res.texto}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <MaisLinhas mostrando={dados.rodadas.length} total={Math.min(dados.total, 300)} passo={PAGINA} mais={() => setLimite(limite + PAGINA)} />
          </div>
        )}
      </section>

      <section className="panel section-gap" id="avisos">
        <div className="panel-head"><h2>Avisos do código</h2><small>O que o código corrigiu ou recusou no que o curador escreveu.</small></div>
        {!avisos.dados ? <Carregando /> : avisos.dados.length === 0 ? <Vazio titulo="Nenhum aviso" /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Quando</th><th>Tipo</th><th>Nota</th><th>Detalhe</th></tr></thead>
              <tbody>
                {paginaAvisos.visiveis.map((a) => (
                  <tr key={a.id}><td>{dataHora(a.em)}</td><td>{a.tipo}</td><td className="mono">{a.nota ?? "—"}</td><td style={{ whiteSpace: "normal" }}>{a.detalhe}</td></tr>
                ))}
              </tbody>
            </table>
            {paginaAvisos.rodape}
          </div>
        )}
        {avisos.dados && <div style={{ padding: "0 23px 20px" }}><AjudaAvisos tipos={avisos.dados.map((a) => a.tipo)} /></div>}
      </section>

      {aberta !== null && <DetalhesRodada tag={s.tag} id={aberta} fechar={() => setAberta(null)} />}
    </>
  );
}

function DetalhesRodada({ tag, id, fechar }: { tag: string; id: number; fechar: () => void }) {
  const { dados, erro } = useDados<DetalheRodada>(`/sistemas/${tag}/rodadas/${id}`);
  const lotes = usePagina(dados?.lotes);
  const avisos = usePagina(dados?.avisos);
  return (
    <Modal titulo={`Rodada #${id}`} aoFechar={fechar} largura={820}>
      {erro && <Falha erro={erro} />}
      {!dados ? <Carregando /> : (
        <>
          <p>{dataHora(dados.inicio)} · {duracao(dados.inicio, dados.fim)} · {dados.modo === "pedidos" ? "pull pedido" : "rodada automática"}</p>
          <h3 style={{ margin: "20px 0 8px" }}>Lotes de {tag}</h3>
          {dados.lotes.length === 0 ? <small>Nenhum lote deste vault nesta rodada.</small> : (
            <div className="table-wrap panel">
              <table>
                <thead><tr><th>Lote</th><th>Perfil</th><th>Itens</th><th>Registrados</th><th>Tempo</th><th>Saída</th></tr></thead>
                <tbody>
                  {lotes.visiveis.map((l) => (
                    <tr key={l.id}>
                      <td>#{l.id}</td><td>{l.perfil}</td><td>{l.itens}</td><td>{l.registrados ?? "—"}</td>
                      <td>{duracao(l.inicio, l.fim)}</td>
                      <td>{l.erro ? <span className="red">{l.erro}</span> : l.codigo === 0 ? "ok" : l.codigo ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {lotes.rodape}
            </div>
          )}
          <h3 style={{ margin: "20px 0 8px" }}>Avisos</h3>
          {dados.avisos.length === 0 ? <small>Nenhum aviso.</small> : (
            <ul style={{ paddingLeft: 18, fontSize: 13 }}>
              {avisos.visiveis.map((a) => <li key={a.id}><b style={{ fontWeight: 500 }}>{a.tipo}</b>{a.nota && <> · <code>{a.nota}</code></>} — {a.detalhe}</li>)}
            </ul>
          )}
          {avisos.rodape}
          <AjudaAvisos tipos={dados.avisos.map((a) => a.tipo)} />
        </>
      )}
    </Modal>
  );
}
