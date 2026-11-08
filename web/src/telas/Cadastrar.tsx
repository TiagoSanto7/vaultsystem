import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAviso } from "../componentes";
import { CamposOrigem, ExplicacaoChave, origemParaApi, origemVazia } from "../FormOrigem";
import { Icone } from "../icones";

const TAG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
type Tipo = "vault" | "template";
type Modo = "literal" | "documentado";

export default function Cadastrar() {
  const [tipo, setTipo] = useState<Tipo>("vault");
  const [modo, setModo] = useState<Modo>("documentado");
  const [fonte, setFonte] = useState<"envio" | "git">("envio");
  const [nome, setNome] = useState("");
  const [pacote, setPacote] = useState<File>();
  const [origens, setOrigens] = useState([origemVazia()]);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const ir = useNavigate();
  const avisar = useAviso();
  const tag = tipo === "template" ? "template-" + nome : nome;

  async function criar(e: FormEvent) {
    e.preventDefault();
    if (!TAG.test(nome) || (tipo === "vault" && nome.startsWith("template-"))) {
      return setErro("Use minúsculas, números e hífen. O prefixo template- é reservado.");
    }
    if (fonte === "envio" && (!pacote || pacote.size > 10 * 1024 * 1024)) {
      return setErro("Escolha um ZIP de até 10 MB.");
    }
    if (fonte === "git" && origens.some(o => !o.repo.trim())) return setErro("Escolha cada repositório Git.");
    setErro("");
    setEnviando(true);
    try {
      if (fonte === "envio") {
        await api(`/envios/${tag}?modo=${modo}`, { metodo: "POST", corpo: pacote });
      } else {
        const perfil = modo === "literal" ? "referencia" : "codigo-literal";
        const dados = origens.map(o => ({
          ...origemParaApi(o), leituras: [{ perfil, incluir: [], excluir: [] }], classificacao: { "": perfil },
        }));
        await api("/sistemas", { metodo: "POST", corpo: { tag, origens: dados } });
        try {
          await api(`/sistemas/${tag}/pull`, { metodo: "POST" });
        } catch (x) {
          avisar(`Vault criado. Para solicitar o processamento, use Pedir pull. ${(x as Error).message}`);
          ir(`/sistemas/${tag}`);
          return;
        }
      }
      avisar("Cadastro concluído. O conteúdo entrou na fila de processamento.");
      ir(`/sistemas/${tag}`);
    } catch (x) {
      setErro((x as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return <div className="page">
    <Link className="back" to="/sistemas"><Icone nome="back" />Todos os vaults</Link>
    <div className="heading"><div><div className="eyebrow">Catálogo do workspace</div>
      <h1>Novo vault ou template</h1><p>Envie arquivos pelo painel ou pela CLI, ou conecte um repositório Git.</p></div></div>
    <form className="panel" style={{ padding: "8px 26px 26px", maxWidth: 860 }} onSubmit={criar}>
      <fieldset className="tipo-vault"><legend>O que você quer adicionar?</legend><div>
        {([{ id: "vault", titulo: "Vault", descricao: "Arquivos e conhecimento de um projeto." },
          { id: "template", titulo: "Template", descricao: "Pacotes de arquivos para reutilizar pela CLI." }] as const).map(t =>
          <label key={t.id} className={tipo === t.id ? "ativo" : ""}>
            <input type="radio" name="tipo" checked={tipo === t.id} onChange={() => {
              setTipo(t.id); setModo(t.id === "template" ? "literal" : "documentado");
            }} /><b>{t.titulo}</b><small>{t.descricao}</small>
          </label>)}
      </div></fieldset>
      <label htmlFor="nome-vault">{tipo === "template" ? "Categoria do template" : "Nome do vault"}</label>
      <input id="nome-vault" value={nome} onChange={e => setNome(e.target.value.toLowerCase())}
        placeholder={tipo === "template" ? "docker" : "meu-projeto"} required />
      {tipo === "template" && <small>O vault fica <code>{tag}</code>. Cada pasta de primeiro nível vira um template.</small>}
      <fieldset className="tipo-vault"><legend>Como processar?</legend><div>
        {([{ id: "literal", titulo: "Literal", descricao: "Guarda os arquivos selecionados." },
          { id: "documentado", titulo: "Literal + documentado", descricao: "Guarda os arquivos e encaminha a documentação ao curador do hub." }] as const).map(m =>
          <label key={m.id} className={modo === m.id ? "ativo" : ""}>
            <input type="radio" name="modo" checked={modo === m.id} onChange={() => setModo(m.id)} />
            <b>{m.titulo}</b><small>{m.descricao}</small>
          </label>)}
      </div></fieldset>
      <label htmlFor="fonte-vault">Origem</label>
      <select id="fonte-vault" value={fonte} onChange={e => setFonte(e.target.value === "git" ? "git" : "envio")}>
        <option value="envio">Enviar arquivos</option><option value="git">Conectar Git</option>
      </select>
      {fonte === "envio" ? <>
        <label htmlFor="pacote-vault">Pacote ZIP de até 10 MB</label>
        <input id="pacote-vault" type="file" accept=".zip,application/zip" required onChange={e => setPacote(e.target.files?.[0])} />
        <p>Também pode fazer o primeiro envio no terminal com <code>vs sync {tag || "meu-projeto"} pacote.zip modo={modo}</code>.</p>
      </> : <>
        {origens.map((o, i) => <section key={i} style={{ marginTop: 20 }}>
          <h2 style={{ fontSize: 16 }}>{i === 0 ? "Repositório principal" : `Repositório ${i + 1}`}</h2>
          <CamposOrigem id={`origem-${i}`} valor={o} nomeFixo={i === 0} semLeituras
            mudar={v => setOrigens(items => items.map((item, j) => j === i ? v : item))} />
          {i > 0 && <button type="button" className="textbtn" onClick={() => setOrigens(items => items.filter((_, j) => i !== j))}>Remover origem</button>}
        </section>)}
        {origens.length < 10 && <button type="button" className="btn" style={{ marginTop: 16 }}
          onClick={() => setOrigens(items => [...items, origemVazia(`origem-${items.length + 1}`)])}>Adicionar repositório</button>}
        {origens.some(o => o.acesso === "chave") && <ExplicacaoChave tag={tag || "<tag>"} origem="principal" />}
      </>}
      {erro && <p role="alert">{erro}</p>}
      <div className="modal-actions"><Link className="btn" to="/sistemas">Cancelar</Link>
        <button className="btn primary" type="submit" disabled={enviando}>{enviando ? "Enviando…" : "Criar"}</button></div>
    </form>
  </div>;
}
