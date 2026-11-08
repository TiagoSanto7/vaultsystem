import { FormEvent, useState } from "react";
import { api, ListaSistemas } from "./api";
import { Carregando, Modal, useAviso } from "./componentes";
import { useDados } from "./dados";
import { Icone } from "./icones";
import { useSessao } from "./sessao";

// Tokens de integração (DV-599): credencial `pv_` só leitura, com os vaults que
// ela pode ler. A chave aparece uma vez só; o banco guarda apenas o hash. Usados
// pela aba Tokens e pela aba Integrações de cada vault.

export function useUrlPublica() {
  return useSessao().eu?.url_publica ?? window.location.origin;
}

/** Lista de vaults para marcar (os cadastrados e não removidos). */
function EscolherVaults({ marcados, mudar }: { marcados: string[]; mudar: (v: string[]) => void }) {
  const { dados } = useDados<ListaSistemas>("/sistemas");
  if (!dados) return <Carregando />;
  const tags = dados.sistemas.filter((s) => !s.removido_em).map((s) => s.tag);
  const alternar = (t: string) => mudar(marcados.includes(t) ? marcados.filter((x) => x !== t) : [...marcados, t].sort());
  return (
    <fieldset className="vaults-token">
      <legend>Vaults que o token pode ler</legend>
      {tags.length === 0 ? <p className="muted">Nenhum vault cadastrado.</p> : (
        <div>
          {tags.map((t) => (
            <label key={t} className="check"><input type="checkbox" checked={marcados.includes(t)} onChange={() => alternar(t)} />{t}</label>
          ))}
        </div>
      )}
      <small className="muted">Marque todos os que a aplicação ou o agente vai consultar. Dá para mudar depois sem trocar o token.</small>
    </fieldset>
  );
}

export function CriarToken({ inicial = [], fechar, feito }: { inicial?: string[]; fechar: () => void; feito: () => void }) {
  const [nome, setNome] = useState("");
  const [vaults, setVaults] = useState<string[]>(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const [chave, setChave] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setErro(null);
    try {
      const r = await api<{ chave: string }>("/credenciais", { metodo: "POST", corpo: { nome: nome.trim(), ler: vaults, escrever: [] } });
      setChave(r.chave);
      feito();
    } catch (x) {
      setErro((x as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  // Ao fechar, recarrega a lista: o token pode ter sido usado enquanto a janela estava aberta.
  if (chave) return <TokenCriado chave={chave} vaults={vaults} fechar={() => { feito(); fechar(); }} />;
  return (
    <Modal titulo="Criar token" aoFechar={fechar} largura={560}>
      <p>Um token por aplicação ou agente: assim dá para revogar um sem afetar os outros. Só leitura: não escreve, não executa código e não acessa o GitHub.</p>
      <form onSubmit={enviar}>
        <label htmlFor="nome-token">Nome</label>
        <input id="nome-token" value={nome} onChange={(e) => setNome(e.target.value)} maxLength={64} required placeholder="ex.: portal-rh ou agente-suporte" />
        <EscolherVaults marcados={vaults} mudar={setVaults} />
        {erro && <div className="erro-campo" role="alert">{erro}</div>}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={fechar}>Cancelar</button>
          <button className="btn primary" type="submit" disabled={enviando || !nome.trim() || vaults.length === 0}>
            <Icone nome="key" />{enviando ? "Criando…" : "Criar token"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function Copiavel({ id, texto, rotulo, linhas }: { id: string; texto: string; rotulo: string; linhas?: boolean }) {
  const [copiado, setCopiado] = useState(false);
  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
    } catch {
      (document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement | null)?.select();
    }
  }
  return (
    <div className="segredo">
      {linhas
        ? <textarea id={id} readOnly value={texto} aria-label={rotulo} rows={texto.split("\n").length} wrap="off" onFocus={(e) => e.target.select()} />
        : <input id={id} readOnly value={texto} aria-label={rotulo} onFocus={(e) => e.target.select()} />}
      <button className="btn" onClick={copiar}><Icone nome={copiado ? "check" : "copy"} />{copiado ? "Copiado" : "Copiar"}</button>
    </div>
  );
}

export function comandos(url: string, chave: string, vault: string) {
  return {
    mcp: `claude mcp add --scope user --transport http petro-vault ${url}/mcp \\\n  --header "Authorization: Bearer ${chave}"`,
    curl: `curl -X POST ${url}/v1/knowledge/search \\\n  -H "Authorization: Bearer ${chave}" -H "Content-Type: application/json" \\\n  -d '{"system_id": "${vault}", "query": "sua pergunta"}'`,
  };
}

function TokenCriado({ chave, vaults, fechar }: { chave: string; vaults: string[]; fechar: () => void }) {
  const url = useUrlPublica();
  const c = comandos(url, chave, vaults[0]);
  return (
    <Modal titulo="Token criado" aoFechar={fechar} largura={640}>
      <div className="banner warn" style={{ marginTop: 14 }}>
        <Icone nome="lock" />
        <span>Esta é a única vez em que o token aparece. Guarde-o agora (no <code>.env</code> da aplicação, por exemplo); o PetroVault só guarda o hash.</span>
      </div>
      <Copiavel id="chave-nova" texto={chave} rotulo="Token" />
      <p style={{ margin: "18px 0 0" }}>Lê {vaults.length === 1 ? "o vault" : `${vaults.length} vaults`}: <b>{vaults.join(", ")}</b>. Em cada consulta, o <code>system_id</code> diz qual deles.</p>
      <h3 className="token-passo">Agente (Claude Code, MCP)</h3>
      <Copiavel id="cmd-mcp" texto={c.mcp} rotulo="Comando MCP" linhas />
      <h3 className="token-passo">Aplicação (API HTTP)</h3>
      <Copiavel id="cmd-curl" texto={c.curl} rotulo="Exemplo de busca" linhas />
      <div className="modal-actions"><button className="btn primary" onClick={fechar}>Já guardei</button></div>
    </Modal>
  );
}

export function EditarVaults({ nome, atuais, fechar, feito }: { nome: string; atuais: string[]; fechar: () => void; feito: () => void }) {
  const avisar = useAviso();
  const [vaults, setVaults] = useState(atuais);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  async function salvar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    try {
      await api(`/credenciais/${encodeURIComponent(nome)}`, { metodo: "PATCH", corpo: { ler: vaults } });
      avisar(`Vaults do token ${nome} atualizados. Vale a partir da próxima chamada.`);
      feito();
      fechar();
    } catch (x) {
      setErro((x as Error).message);
      setEnviando(false);
    }
  }
  return (
    <Modal titulo={`Vaults do token ${nome}`} aoFechar={fechar} largura={560}>
      <p>O token continua o mesmo: quem usa não precisa mudar nada.</p>
      <form onSubmit={salvar}>
        <EscolherVaults marcados={vaults} mudar={setVaults} />
        {erro && <div className="erro-campo" role="alert">{erro}</div>}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={fechar}>Cancelar</button>
          <button className="btn primary" type="submit" disabled={enviando || vaults.length === 0}>Salvar</button>
        </div>
      </form>
    </Modal>
  );
}

export function Revogar({ nome, fechar, feito }: { nome: string; fechar: () => void; feito: () => void }) {
  const avisar = useAviso();
  const [enviando, setEnviando] = useState(false);
  async function revogar() {
    setEnviando(true);
    try {
      await api(`/credenciais/${encodeURIComponent(nome)}`, { metodo: "DELETE" });
      avisar(`Token ${nome} revogado. Ele para de funcionar na próxima chamada.`);
      feito();
      fechar();
    } catch (x) {
      avisar((x as Error).message);
      setEnviando(false);
    }
  }
  return (
    <Modal titulo={`Revogar ${nome}?`} aoFechar={fechar}>
      <p>Quem usa este token perde o acesso na próxima chamada. Não dá para desfazer: para voltar, crie outro token.</p>
      <div className="modal-actions">
        <button className="btn" onClick={fechar}>Cancelar</button>
        <button className="btn danger" onClick={revogar} disabled={enviando}>Revogar</button>
      </div>
    </Modal>
  );
}
