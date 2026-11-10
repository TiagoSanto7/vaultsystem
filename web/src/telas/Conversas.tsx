import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Badge, Carregando, Falha, useAviso, Vazio } from "../componentes";
import { useDados } from "../dados";
import { relativo } from "../formato";
import { Icone } from "../icones";

// Conversa com o Vault-I: geral, sobre um vault (com ou sem uma nota em foco) ou sobre o hub inteiro.
// A API grava a pergunta e o curador responde em segundos; a tela consulta até a resposta chegar.

type Escopo = "geral" | "vault" | "hub";

interface Conversa {
  id: number;
  escopo: Escopo;
  tag: string | null;
  nota: string | null;
  titulo: string;
  criado_em: string;
  atualizado_em: string | null;
  pendentes?: number;
}

interface Mensagem {
  id: number;
  papel: "usuario" | "vault-i";
  texto: string;
  estado: "pendente" | "respondendo" | "ok" | "erro";
  erro: string | null;
  modelo: string | null;
  fontes: { tag: string; chave: string; titulo: string }[];
  criado_em: string;
}

const ROTULO: Record<Escopo, string> = { geral: "Geral", vault: "Vault", hub: "Hub inteiro" };

function escopoDe(c: Conversa) {
  return c.escopo === "vault" ? `Vault ${c.tag}` : ROTULO[c.escopo];
}

function nomeDaNota(chave: string) {
  return chave.split("/").pop()?.replace(/\.md$/, "") ?? chave;
}

function Nova({ aoCriar }: { aoCriar: (id: number) => void }) {
  const [params] = useSearchParams();
  const vaults = useDados<{ sistemas: { tag: string }[] }>("/sistemas");
  const vaultInicial = params.get("vault") ?? "";
  const nota = params.get("nota");
  const [escopo, setEscopo] = useState<Escopo>(vaultInicial ? "vault" : "hub");
  const [tag, setTag] = useState(vaultInicial);
  const [pergunta, setPergunta] = useState(nota ? `Me explica a nota ${nomeDaNota(nota)}.` : "");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const tags = (vaults.dados?.sistemas ?? []).map((s) => s.tag);

  async function enviar(e?: FormEvent) {
    e?.preventDefault();
    if (!pergunta.trim() || (escopo === "vault" && !tag)) return;
    setEnviando(true);
    setErro(null);
    try {
      const r = await api<{ conversa: Conversa }>("/conversas", {
        metodo: "POST",
        corpo: { escopo, tag: escopo === "vault" ? tag : null, nota: escopo === "vault" && tag === vaultInicial ? nota : null, pergunta },
      });
      aoCriar(r.conversa.id);
    } catch (x) {
      setErro((x as Error).message);
      setEnviando(false);
    }
  }

  return (
    <form className="conversa-nova" onSubmit={enviar}>
      <h2>Nova conversa</h2>
      <p className="muted">Pergunte ao Vault-I. Ele responde a partir das notas do escopo escolhido e cita as que usou.</p>
      <fieldset className="chips" role="radiogroup" aria-label="Escopo da conversa">
        {(["hub", "vault", "geral"] as Escopo[]).map((e) => (
          <button key={e} type="button" role="radio" aria-checked={escopo === e} className={`chip ${escopo === e ? "ativo" : ""}`} onClick={() => setEscopo(e)}>
            {e === "hub" ? "Hub inteiro" : e === "vault" ? "Um vault" : "Geral"}
          </button>
        ))}
      </fieldset>
      <small className="muted">
        {escopo === "hub" ? "Busca nas notas de todos os vaults." : escopo === "vault" ? "Busca só nas notas do vault escolhido." : "Conversa livre, sem consultar notas."}
      </small>
      {escopo === "vault" && (
        <>
          <label htmlFor="conversa-vault">Vault</label>
          <select id="conversa-vault" value={tag} onChange={(e) => setTag(e.target.value)}>
            <option value="">Escolha um vault</option>
            {tags.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {nota && tag === vaultInicial && <small className="muted">Com foco na nota <code>{nomeDaNota(nota)}</code>.</small>}
        </>
      )}
      <label htmlFor="conversa-pergunta">Pergunta</label>
      <Caixa id="conversa-pergunta" valor={pergunta} mudar={setPergunta} enviar={() => enviar()} />
      {erro && <div className="erro-campo" role="alert">{erro}</div>}
      <div className="modal-actions" style={{ justifyContent: "flex-start" }}>
        <button className="btn primary" type="submit" disabled={enviando || !pergunta.trim() || (escopo === "vault" && !tag)}>
          <Icone nome="spark" />{enviando ? "Enviando…" : "Perguntar"}
        </button>
      </div>
    </form>
  );
}

function Caixa({ id, valor, mudar, enviar, desligada }: { id: string; valor: string; mudar: (v: string) => void; enviar: () => void; desligada?: boolean }) {
  function tecla(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  }
  return (
    <textarea id={id} rows={3} value={valor} disabled={desligada} maxLength={4000} onChange={(e) => mudar(e.target.value)} onKeyDown={tecla}
      placeholder="Escreva e aperte Enter (Shift+Enter quebra a linha)" />
  );
}

function Fio({ id, aoApagar }: { id: number; aoApagar: () => void }) {
  const [esperando, setEsperando] = useState(false);
  const { dados, erro, recarregar } = useDados<{ conversa: Conversa; mensagens: Mensagem[] }>(`/conversas/${id}`, esperando ? 2000 : undefined, true);
  const [pergunta, setPergunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const fim = useRef<HTMLDivElement>(null);
  const avisar = useAviso();
  const pendente = !!dados?.mensagens.some((m) => m.estado === "pendente" || m.estado === "respondendo");

  useEffect(() => setEsperando(pendente), [pendente]);
  useEffect(() => fim.current?.scrollIntoView({ block: "end" }), [dados?.mensagens.length, pendente]);

  async function enviar(e?: FormEvent) {
    e?.preventDefault();
    if (!pergunta.trim() || pendente) return;
    setEnviando(true);
    setFalha(null);
    try {
      await api(`/conversas/${id}/mensagens`, { metodo: "POST", corpo: { pergunta } });
      setPergunta("");
      recarregar();
    } catch (x) {
      setFalha((x as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  async function apagar() {
    await api(`/conversas/${id}`, { metodo: "DELETE" });
    avisar("Conversa apagada.");
    aoApagar();
  }

  if (erro) return <Falha erro={erro} tentar={recarregar} />;
  if (!dados) return <Carregando />;
  const c = dados.conversa;
  return (
    <div className="conversa-fio">
      <div className="conversa-topo">
        <div style={{ minWidth: 0 }}>
          <h2>{c.titulo}</h2>
          <small className="muted">
            {escopoDe(c)}{c.nota ? <> · nota <code>{nomeDaNota(c.nota)}</code></> : null}
            {c.tag && <> · <Link to={`/sistemas/${c.tag}/conhecimento`}>abrir o vault</Link></>}
          </small>
        </div>
        <button type="button" className="textbtn" onClick={apagar}>Apagar conversa</button>
      </div>
      <div className="conversa-mensagens" aria-live="polite">
        {dados.mensagens.map((m) => (
          <div key={m.id} className={`msg ${m.papel === "usuario" ? "minha" : "dele"}`}>
            {m.papel === "vault-i" && <div className="msg-autor"><Icone nome="spark" /> Vault-I</div>}
            <div className="msg-texto">
              {m.papel === "usuario" ? <p>{m.texto}</p> : <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.texto}</ReactMarkdown>}
            </div>
            {m.fontes.length > 0 && (
              <div className="msg-fontes">
                <span className="muted">Notas usadas:</span>
                {m.fontes.map((f) => (
                  <Link key={`${f.tag}/${f.chave}`} className="chip" to={`/sistemas/${f.tag}/conhecimento?nota=${encodeURIComponent(f.chave)}`}>
                    {f.titulo}{c.escopo === "hub" ? ` · ${f.tag}` : ""}
                  </Link>
                ))}
              </div>
            )}
            {m.estado === "erro" && <div className="erro-campo" role="alert">O Vault-I não respondeu: {m.erro}</div>}
          </div>
        ))}
        {pendente && <div className="msg dele"><div className="msg-autor"><Icone nome="spark" /> Vault-I</div><p className="muted pensando">Lendo as notas e escrevendo…</p></div>}
        <div ref={fim} />
      </div>
      <form className="conversa-caixa" onSubmit={enviar}>
        <Caixa id="conversa-resposta" valor={pergunta} mudar={setPergunta} enviar={() => enviar()} desligada={enviando} />
        <button className="btn primary" type="submit" disabled={enviando || pendente || !pergunta.trim()}><Icone nome="arrow" />Enviar</button>
      </form>
      {falha && <div className="erro-campo" role="alert">{falha}</div>}
    </div>
  );
}

export default function Conversas() {
  const { id } = useParams();
  const ir = useNavigate();
  const lista = useDados<{ disponivel: boolean; conversas: Conversa[] }>("/conversas", 5000, true);
  const aberta = id ? Number(id) : null;

  return (
    <div className="page">
      <div className="heading">
        <div>
          <div className="eyebrow">Vault-I</div>
          <h1>Conversas</h1>
          <p>Pergunte sobre um vault, sobre o hub inteiro ou converse livremente. Conversar não muda nenhuma nota.</p>
        </div>
        {aberta && <button type="button" className="btn" onClick={() => ir("/conversas")}><Icone nome="plus" />Nova conversa</button>}
      </div>
      {lista.erro ? <Falha erro={lista.erro} tentar={lista.recarregar} /> : !lista.dados ? <Carregando /> : !lista.dados.disponivel ? (
        <section className="panel">
          <Vazio titulo="Configure o Vault-I para conversar" acao={<Link className="btn primary" to="/configuracoes"><Icone nome="gear" />Abrir Configurações</Link>}>
            A conversa usa a mesma chave de API ou o token do <code>claude setup-token</code> da curadoria.
          </Vazio>
        </section>
      ) : (
        <div className="conversa-layout">
          <aside className="panel conversa-lista" aria-label="Suas conversas">
            <div className="panel-head"><h2>Suas conversas</h2><Badge tipo="neutral">{lista.dados.conversas.length}</Badge></div>
            {lista.dados.conversas.length === 0 && <p className="muted" style={{ padding: "0 23px" }}>Nenhuma ainda.</p>}
            {lista.dados.conversas.map((c) => (
              <Link key={c.id} to={`/conversas/${c.id}`} className={`conversa-item ${aberta === c.id ? "ativa" : ""}`}>
                <b>{c.titulo}</b>
                <small>{escopoDe(c)} · {relativo(c.atualizado_em ?? c.criado_em)}{c.pendentes ? " · respondendo…" : ""}</small>
              </Link>
            ))}
          </aside>
          <section className="panel conversa-principal">
            {aberta
              ? <Fio key={aberta} id={aberta} aoApagar={() => { lista.recarregar(); ir("/conversas"); }} />
              : <Nova aoCriar={(nova) => { lista.recarregar(); ir(`/conversas/${nova}`); }} />}
          </section>
        </div>
      )}
    </div>
  );
}
