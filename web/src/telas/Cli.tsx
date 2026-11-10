import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Falha, Modal, Vazio } from "../componentes";
import { useDados } from "../dados";
import { Copiavel } from "../tokens";

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

function tamanho(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1).replace(".0", "")} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".0", "")} MB`;
}

function comando(t: Template) {
  return t.tipo === "init" ? `vs init package=${t.nome}` : `vs add template ${t.id}`;
}

function Arquivos({ template }: { template: Template }) {
  const { dados, erro, recarregar } = useDados<{ files: { path: string; size: number }[] }>(
    `/cli/templates/${encodeURIComponent(template.tipo)}/${encodeURIComponent(template.nome)}`,
  );
  if (erro) return <Falha erro={erro} tentar={recarregar} />;
  if (!dados) return <p className="muted">Carregando arquivos…</p>;
  return (
    <div className="table-wrap" style={{ maxHeight: 360, overflow: "auto", border: "1px solid var(--line)", borderRadius: 8 }}>
      <table>
        <thead><tr><th>Arquivo</th><th style={{ textAlign: "right" }}>Tamanho</th></tr></thead>
        <tbody>
          {dados.files.map((f) => (
            <tr key={f.path}><td className="mono">{f.path}</td><td className="muted" style={{ textAlign: "right", whiteSpace: "nowrap" }}>{tamanho(f.size)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Detalhe({ t, aoFechar }: { t: Template; aoFechar: () => void }) {
  return (
    <Modal titulo={t.id} aoFechar={aoFechar} largura={720}>
      <p style={{ marginTop: 0 }}>{t.descricao || "Pacote publicado no hub."}</p>
      <p className="muted" style={{ fontSize: 12 }}>
        {t.arquivos} arquivo(s) · revisão <code>{t.commit.slice(0, 12)}</code> · <Link to={`/sistemas/${encodeURIComponent(t.vault)}`}>vault {t.vault}</Link>
      </p>
      {t.bloqueado ? <div className="erro-campo" role="alert">{t.bloqueado}</div> : (
        <>
          <h3 className="token-passo">Aplicar na pasta atual</h3>
          <Copiavel id={`cmd-${t.id}`} texto={comando(t)} rotulo={`Comando de ${t.id}`} />
        </>
      )}
      <h3 className="token-passo">Arquivos</h3>
      <Arquivos template={t} />
    </Modal>
  );
}

export default function Cli() {
  const { dados, erro, recarregar } = useDados<{ templates: Template[] }>("/cli");
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState("");
  const [aberto, setAberto] = useState<Template | null>(null);
  const todos = dados?.templates.filter((t) => t.id !== "init:padrao") ?? [];
  const tipos = [...new Set(todos.map((t) => t.tipo))].sort();
  const termo = busca.trim().toLowerCase();
  const itens = todos.filter((t) => (!tipo || t.tipo === tipo) && `${t.id} ${t.descricao}`.toLowerCase().includes(termo));
  return (
    <div className="page">
      <div className="heading"><div><div className="eyebrow">Do terminal ao projeto</div>
        <h1>VS CLI</h1><p>Instalar, o fluxo do dia a dia e os templates disponíveis no hub.</p></div></div>

      <div className="columns iguais">
        <section className="panel">
          <div className="panel-head"><h2>Instalar</h2></div>
          <div className="panel-body">
            <p className="muted" style={{ marginTop: 0 }}>Instala <code>vs</code> e <code>vaultsystem</code> no seu usuário (sem administrador), já apontando para este hub. Precisa do Python 3.8 ou mais novo.</p>
            <h3 className="token-passo">Windows (PowerShell)</h3>
            <Copiavel id="instalar-ps" texto={`irm ${window.location.origin}/v1/cli/install.ps1 | iex`} rotulo="Instalar no Windows" />
            <h3 className="token-passo">Linux, macOS e WSL</h3>
            <Copiavel id="instalar-sh" texto={`curl -fsSL ${window.location.origin}/v1/cli/install.sh | sh`} rotulo="Instalar no Linux e macOS" />
            <p className="muted" style={{ marginBottom: 0 }}>Depois, num terminal novo: <code>vs login</code> e cole o token de conexão. Para atualizar: <code>vs update</code>.</p>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head"><h2>Fluxo principal</h2><Link className="textbtn" to="/tokens">Criar token de conexão</Link></div>
          <div className="panel-body">
            <ol className="passos">
              <li><code>vs login</code><span>Conecta o terminal ao workspace com o token de conexão.</span></li>
              <li><code>vs init vault=&lt;nome&gt;</code><span>Liga a pasta a um vault e grava o protocolo no <code>AGENTS.md</code>.</span></li>
              <li><b>O agente documenta</b><span>Notas com cabeçalho <code>vs:</code> e as origens, seguindo o <code>AGENTS.md</code>.</span></li>
              <li><code>vs sync</code><span>Empacota a pasta e envia. Com <code>--curate</code>, o agente da máquina cura antes.</span></li>
            </ol>
            <p className="muted" style={{ marginBottom: 0, fontSize: 12 }}>Todos os comandos e parâmetros: <Link to="/docs/cli">documentação da CLI</Link>.</p>
          </div>
        </section>
      </div>

      <section className="panel section-gap">
        <div className="panel-head">
          <div><h2>Catálogo de templates</h2><small>{todos.length ? `${todos.length} template(s) em ${tipos.length} tipo(s)` : "Templates publicados nos vaults template-<tipo>."}</small></div>
          <Link className="textbtn" to="/sistemas">Ver vaults</Link>
        </div>
        <div className="panel-body">
          <div className="catalogo-filtros">
            <input aria-label="Buscar template" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nome ou descrição" />
            <div className="chips" role="group" aria-label="Filtrar por tipo">
              <button type="button" className={`chip ${!tipo ? "ativo" : ""}`} onClick={() => setTipo("")}>Todos</button>
              {tipos.map((t) => <button key={t} type="button" className={`chip ${tipo === t ? "ativo" : ""}`} onClick={() => setTipo(tipo === t ? "" : t)}>{t}</button>)}
            </div>
          </div>
          {erro && <Falha erro={erro} tentar={recarregar} />}
          {!dados && !erro && <p className="muted">Carregando catálogo…</p>}
          {dados && itens.length === 0 && <Vazio titulo="Nenhum template encontrado">Tente outro termo ou tipo.</Vazio>}
          <div className="grade-cartoes">
            {itens.map((t) => (
              <article key={t.id} className="cartao">
                <div className="cartao-topo">
                  <b className="mono">{t.id}</b>
                  {t.bloqueado ? <Badge tipo="erro">Bloqueado</Badge> : <Badge tipo="neutral">{t.tipo}</Badge>}
                </div>
                <p className="cartao-texto">{t.descricao || "Pacote publicado no hub."}</p>
                <code className="cartao-cmd">{comando(t)}</code>
                <div className="cartao-rodape">
                  <span>{t.arquivos} arquivo(s) · <span className="mono">{t.commit.slice(0, 7)}</span></span>
                  <button type="button" className="textbtn" onClick={() => setAberto(t)}>Ver arquivos</button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>
      {aberto && <Detalhe t={aberto} aoFechar={() => setAberto(null)} />}
    </div>
  );
}
