import { useState } from "react";
import { Link } from "react-router-dom";
import { Falha } from "../componentes";
import { useDados } from "../dados";

interface Template {
  id: string;
  tipo: string;
  nome: string;
  vault: string;
  descricao: string;
  arquivos: number;
  commit: string;
  bloqueado?: string;
}

function Arquivos({ template }: { template: Template }) {
  const { dados, erro, recarregar } = useDados<{ files: { path: string; size: number }[] }>(
    `/cli/templates/${encodeURIComponent(template.tipo)}/${encodeURIComponent(template.nome)}`,
  );
  if (erro) return <Falha erro={erro} tentar={recarregar} />;
  if (!dados) return <p>Carregando arquivos…</p>;
  return <ul>{dados.files.map(file => <li key={file.path}><code>{file.path}</code> · {file.size} bytes</li>)}</ul>;
}

export default function Cli() {
  const { dados, erro, recarregar } = useDados<{ templates: Template[] }>("/cli");
  const [busca, setBusca] = useState("");
  const [aberto, setAberto] = useState("");
  const itens = dados?.templates.filter(t => t.id !== "init:padrao" &&
    `${t.id} ${t.descricao}`.toLowerCase().includes(busca.trim().toLowerCase()));
  return <div className="page">
    <div className="heading"><div><div className="eyebrow">Do terminal ao projeto</div>
      <h1>VS CLI</h1><p>Comandos, pacotes iniciais e templates disponíveis no hub.</p></div></div>
    <section className="panel">
      <div className="panel-head"><h2>Comandos e inicialização</h2></div>
      <div className="panel-body"><ul>
        <li><code>vaultsystem</code> abre o painel no terminal.</li>
        <li><code>vs init</code> aplica <code>init:padrao</code> e prepara <code>AGENTS.md</code>, <code>.vs</code>, <code>VS.lock</code> e <code>.gitignore</code>.</li>
        <li><code>vs init &lt;nome&gt;</code> aplica um pacote de inicialização do hub.</li>
        <li><code>vs sync &lt;vault&gt; &lt;arquivo.zip&gt;</code> envia uma revisão completa para um vault de envio.</li>
        <li><code>vs add template &lt;tipo:nome&gt;</code> aplica os arquivos na pasta atual. Use <code>--dry-run</code> para simular.</li>
      </ul></div>
    </section>
    <section className="panel">
      <div className="panel-head"><h2>Catálogo de templates</h2><Link className="textbtn" to="/sistemas">Ver vaults</Link></div>
      <div className="panel-body">
        <label htmlFor="buscar-template-cli">Buscar template</label>
        <input id="buscar-template-cli" value={busca} onChange={e => setBusca(e.target.value)} placeholder="Ex.: docker" />
        {erro && <Falha erro={erro} tentar={recarregar} />}
        {!dados && !erro && <p>Carregando catálogo…</p>}
        {itens?.length === 0 && <p>Nenhum template encontrado.</p>}
        {itens?.map(t => <article key={t.id} style={{ marginBlock: 18 }}>
          <button className="btn" type="button" aria-expanded={aberto === t.id} onClick={() => setAberto(aberto === t.id ? "" : t.id)}>{t.id}</button>
          <p>{t.descricao || "Pacote publicado no hub."} · {t.arquivos} arquivo(s) · <code>{t.commit.slice(0, 12)}</code></p>
          {aberto === t.id && <>
            <Link to={`/sistemas/${encodeURIComponent(t.vault)}`}>Vault de origem</Link>
            {t.bloqueado ? <p>{t.bloqueado}</p> : <p><code>{t.tipo === "init" ? `vs init ${t.nome}` : `vs add template ${t.id}`}</code></p>}
            <Arquivos template={t} />
          </>}
        </article>)}
      </div>
    </section>
  </div>;
}
