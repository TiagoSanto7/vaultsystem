import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { Carregando, Falha, useAviso } from "../componentes";
import { useDados } from "../dados";
import { dataHora } from "../formato";
import { Icone } from "../icones";

// Configurações do hub. Vault-I (Vault Intelligence): a chave de API da curadoria interna.
// A curadoria nunca é automática: só roda quando alguém pede no vault ou com vs sync --curate.

interface VaultI {
  configurada: boolean;
  provedor?: string;
  modelo?: string;
  chave_final?: string;
  atualizado_em?: string;
  atualizado_por?: string | null;
  provedores: { id: string; nome: string; modelo: string }[];
}

function VaultIPainel() {
  const { dados, erro, recarregar } = useDados<VaultI>("/vault-i");
  const avisar = useAviso();
  const [provedor, setProvedor] = useState("anthropic");
  const [modelo, setModelo] = useState("");
  const [chave, setChave] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);

  useEffect(() => {
    if (dados?.configurada && dados.provedor) {
      setProvedor(dados.provedor);
      setModelo(dados.modelo ?? "");
    }
  }, [dados?.configurada, dados?.provedor, dados?.modelo]);

  if (erro) return <Falha erro={erro} tentar={recarregar} />;
  if (!dados) return <Carregando />;
  const padrao = dados.provedores.find((p) => p.id === provedor)?.modelo ?? "";
  const trocaProvedor = dados.configurada && dados.provedor !== provedor;

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setFalha(null);
    try {
      await api("/vault-i", { metodo: "PUT", corpo: { provedor, modelo: modelo.trim(), chave: chave.trim() } });
      setChave("");
      avisar("Vault-I configurado. A curadoria continua só sob demanda.");
      recarregar();
    } catch (x) {
      setFalha((x as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  async function remover() {
    setEnviando(true);
    try {
      await api("/vault-i", { metodo: "DELETE" });
      avisar("Chave do Vault-I removida. O hub não cura mais nada até uma nova chave.");
      setModelo("");
      recarregar();
    } catch (x) {
      avisar((x as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2><Icone nome="spark" /> Vault-I · Vault Intelligence</h2>
        <span className={`badge ${dados.configurada ? "" : "muted"}`}>{dados.configurada ? "Chave ativa" : "Sem chave"}</span>
      </div>
      <div className="panel-body">
        <p style={{ marginTop: 0 }}>
          O Vault-I é a curadoria interna do hub: lê os arquivos de um vault e escreve notas com origem, no mesmo
          formato das notas do agente local. Use a chave de API do Claude (Anthropic) ou da OpenAI (Codex).
        </p>
        <div className="banner" role="note">
          <Icone nome="lock" />
          <span>A curadoria <b>nunca é automática</b>. Ela só roda quando você pede: no botão <b>Curar com Vault-I</b> de um
            vault ou com <code>vs sync --curate</code>. Sem chave, nada muda: o vault fica com os arquivos e as notas do agente.</span>
        </div>
        {dados.configurada && (
          <ul className="kv">
            <li><span>Provedor</span><span>{dados.provedores.find((p) => p.id === dados.provedor)?.nome}</span></li>
            <li><span>Modelo</span><span className="mono">{dados.modelo}</span></li>
            <li><span>Chave</span><span className="mono">{dados.chave_final}</span></li>
            <li><span>Atualizada</span><span>{dados.atualizado_em ? dataHora(dados.atualizado_em) : "—"}{dados.atualizado_por ? ` por ${dados.atualizado_por}` : ""}</span></li>
          </ul>
        )}
        <form onSubmit={salvar} style={{ marginTop: 16 }}>
          <label htmlFor="vi-provedor">Provedor</label>
          <select id="vi-provedor" value={provedor} onChange={(e) => { setProvedor(e.target.value); setModelo(""); }}>
            {dados.provedores.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          </select>
          <label htmlFor="vi-modelo">Modelo</label>
          <input id="vi-modelo" className="mono" value={modelo} onChange={(e) => setModelo(e.target.value)} placeholder={padrao} maxLength={80} />
          <small className="muted">Vazio usa o padrão: <code>{padrao}</code>.</small>
          <label htmlFor="vi-chave">Chave de API</label>
          <input id="vi-chave" className="mono" type="password" autoComplete="off" value={chave} onChange={(e) => setChave(e.target.value)}
            placeholder={dados.configurada && !trocaProvedor ? "deixe vazio para manter a chave atual" : provedor === "anthropic" ? "sk-ant-…" : "sk-…"} />
          <small className="muted">A chave fica só no servidor do hub. A tela mostra apenas os últimos caracteres.</small>
          {falha && <div className="erro-campo" role="alert">{falha}</div>}
          <div className="modal-actions" style={{ justifyContent: "flex-start" }}>
            <button className="btn primary" type="submit" disabled={enviando || ((!dados.configurada || trocaProvedor) && !chave.trim())}>
              <Icone nome="check" />{enviando ? "Salvando…" : "Salvar"}
            </button>
            {dados.configurada && <button type="button" className="btn danger" onClick={remover} disabled={enviando}>Remover chave</button>}
          </div>
        </form>
      </div>
    </section>
  );
}

export default function Configuracoes() {
  return (
    <div className="page">
      <div className="heading">
        <div>
          <div className="eyebrow">Workspace</div>
          <h1>Configurações</h1>
          <p>Preferências do hub. A curadoria com IA é opcional e só roda quando você pede.</p>
        </div>
      </div>
      <VaultIPainel />
    </div>
  );
}
