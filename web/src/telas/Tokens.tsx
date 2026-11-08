import { ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { Credencial } from "../api";
import { Carregando, Falha, usePagina, Vazio } from "../componentes";
import { useDados } from "../dados";
import { dataHora } from "../formato";
import { Icone } from "../icones";
import { comandos, CriarToken, EditarVaults, Revogar, useUrlPublica } from "../tokens";

// Aba Tokens: todos os tokens de integração, cada um com os vaults que lê.

export function TabelaTokens({ tokens, recarregar, vazio }: { tokens: Credencial[]; recarregar: () => void; vazio: ReactNode }) {
  const [editar, setEditar] = useState<Credencial | null>(null);
  const [revogar, setRevogar] = useState<string | null>(null);
  const ativos = tokens.filter((c) => c.estado === "ativa");
  const revogados = tokens.filter((c) => c.estado === "revogada");
  const pagina = usePagina(ativos);
  const paginaRevogados = usePagina(revogados);
  return (
    <>
      {ativos.length === 0 ? vazio : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Nome</th><th>Vaults que lê</th><th>Último uso</th><th>Criado</th><th /></tr></thead>
            <tbody>
              {pagina.visiveis.map((c) => (
                <tr key={c.nome}>
                  <td><b style={{ fontWeight: 500 }}>{c.nome}</b>
                    {c.workspace ? <small>conexão da CLI (vs login)</small> : c.escrever.length > 0 && <small>escreve em {c.escrever.join(", ")}</small>}</td>
                  <td>
                    {c.workspace ? <span className="muted">todos os vaults do workspace</span> : (
                      <div className="tags">{c.ler.map((t) => <Link key={t} className="tag" to={`/sistemas/${encodeURIComponent(t)}`}>{t}</Link>)}</div>
                    )}
                  </td>
                  <td>{c.usado_em ? dataHora(c.usado_em) : <span className="muted">nunca usado</span>}</td>
                  <td>{dataHora(c.criado_em)}<small>{c.criado_por ? `por ${c.criado_por}` : "pelo terminal"}</small></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {!c.workspace && <><button className="btn" onClick={() => setEditar(c)}>Vaults</button>{" "}</>}
                    <button className="btn danger" onClick={() => setRevogar(c.nome)}>Revogar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {pagina.rodape}
        </div>
      )}
      {revogados.length > 0 && (
        <details className="panel-body" style={{ borderTop: "1px solid var(--line)" }}>
          <summary style={{ cursor: "pointer" }}>Revogados ({revogados.length})</summary>
          <ul className="kv" style={{ marginTop: 10 }}>
            {paginaRevogados.visiveis.map((c) => <li key={c.nome}><span>{c.nome}</span><span>revogado {dataHora(c.revogada_em)}</span></li>)}
          </ul>
          {paginaRevogados.rodape}
        </details>
      )}
      {editar && <EditarVaults nome={editar.nome} atuais={editar.ler} fechar={() => setEditar(null)} feito={recarregar} />}
      {revogar && <Revogar nome={revogar} fechar={() => setRevogar(null)} feito={recarregar} />}
    </>
  );
}

export function ComoUsar({ vault }: { vault: string }) {
  const url = useUrlPublica();
  const c = comandos(url, "<token>", vault);
  return (
    <details className="panel section-gap" style={{ padding: "16px 23px" }}>
      <summary style={{ cursor: "pointer", fontWeight: 500 }}>Como consultar com o token</summary>
      <p className="muted" style={{ margin: "12px 0", fontSize: 13 }}>
        <b>Agentes</b> (Claude Code e outros clientes MCP): ferramentas <code>list_systems</code>, <code>search_knowledge</code> e <code>read_note</code>.
      </p>
      <pre className="cabecalho mono" style={{ margin: 0, overflow: "auto" }}>{c.mcp}</pre>
      <p className="muted" style={{ margin: "12px 0", fontSize: 13 }}>
        <b>Aplicações</b> (API HTTP): busca por texto, e <code>GET /v1/notas/&lt;note_id&gt;</code> para ler a nota inteira.
      </p>
      <pre className="cabecalho mono" style={{ margin: 0, overflow: "auto" }}>{c.curl}</pre>
      <p className="muted" style={{ margin: "12px 0 0", fontSize: 13 }}>
        Um token pode ler vários vaults: cada consulta diz qual no <code>system_id</code>, e um vault fora do token responde 403.
      </p>
    </details>
  );
}

export default function Tokens() {
  const { dados, erro, recarregar } = useDados<Credencial[]>("/credenciais");
  const [criar, setCriar] = useState(false);
  return (
    <div className="page">
      <div className="heading">
        <div>
          <div className="eyebrow">Integrações</div>
          <h1>Tokens</h1>
          <p>O token de conexão liga o terminal ao hub (<code>vs login</code>). Aplicações e agentes consultam com um token de leitura, que lê só os vaults marcados nele.</p>
        </div>
        <button className="btn primary" onClick={() => setCriar(true)}><Icone nome="key" />Criar token</button>
      </div>
      {erro && <Falha erro={erro} tentar={recarregar} />}
      <section className="panel">
        {!dados ? <Carregando /> : (
          <TabelaTokens tokens={dados} recarregar={recarregar}
            vazio={<Vazio titulo="Nenhum token ativo">Crie um token para cada aplicação ou agente e marque os vaults que ele vai consultar.</Vazio>} />
        )}
      </section>
      <ComoUsar vault="<vault>" />
      {criar && <CriarToken conexaoInicial fechar={() => setCriar(false)} feito={recarregar} />}
    </div>
  );
}
