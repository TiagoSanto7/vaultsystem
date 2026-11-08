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
      <div className="panel-head"><h2>Fluxo principal</h2><Link className="textbtn" to="/tokens">Criar token de conexão</Link></div>
      <div className="panel-body"><ol>
        <li><code>vs login url=&lt;hub&gt;</code> conecta o terminal ao seu workspace com o token de conexão (aba Tokens).</li>
        <li><code>vs init vault=&lt;nome&gt;</code> liga a pasta a um vault: grava o vínculo em <code>.vs</code> e o protocolo de documentação no <code>AGENTS.md</code>. Padrão: literal + documentado; <code>modo=literal</code> só copia os arquivos.</li>
        <li>O agente do projeto escreve as notas seguindo o <code>AGENTS.md</code> (cabeçalho <code>vs:</code>, com as origens).</li>
        <li><code>vs sync</code> empacota a pasta (respeita o <code>.gitignore</code>) e envia. O primeiro envio cria o vault; as notas do agente entram já curadas. <code>--dry-run</code> mostra o que iria.</li>
      </ol></div>
    </section>
    <section className="panel">
      <div className="panel-head"><h2>Outros comandos</h2></div>
      <div className="panel-body"><ul>
        <li><code>vaultsystem</code> abre o painel no terminal.</li>
        <li><code>vs whoami</code> mostra o hub, o token e o dono do workspace.</li>
        <li><code>vs init &lt;nome&gt;</code> aplica um pacote de inicialização do hub.</li>
        <li><code>vs sync &lt;vault&gt; &lt;arquivo.zip&gt;</code> envia um ZIP pronto para um vault.</li>
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
