import { FormEvent, ReactNode, useState } from "react";
import { Icone } from "../icones";
import { ErroApi, useSessao } from "../sessao";
import { useTema } from "../tema";

/** Casca das telas fora do sistema (entrar e apresentação), como no protótipo. */
export function Entrada({ children, luz = false }: { children: ReactNode; luz?: boolean }) {
  const [tema, alternar] = useTema();
  return (
    <div className={`entry-shell ${luz ? "com-luz" : ""}`}>
      <header className="entry-header">
        <div className="entry-brand">
          <img src="/simbolo.png" alt="" />
          <div>
            PetroVault
            <small>Uma plataforma Petrovina</small>
          </div>
        </div>
        <button className="icon-btn" onClick={alternar} aria-label={tema === "escuro" ? "Usar tema claro" : "Usar tema escuro"}>
          <Icone nome={tema === "escuro" ? "sun" : "moon"} />
        </button>
      </header>
      {children}
      <footer className="entry-footer">
        <span>Petrovina · Conhecimento corporativo</span>
      </footer>
    </div>
  );
}

export default function Entrar() {
  const { entrar } = useSessao();
  const [login, setLogin] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await entrar(login.trim(), senha);
    } catch (x) {
      const s = (x as ErroApi).status;
      setErro(
        s === 401 ? "Usuário ou senha incorretos." :
        s === 403 ? "Sua conta ainda não tem acesso a este hub. Peça acesso ao administrador." :
        s === 429 ? "Muitas tentativas. Aguarde alguns minutos e tente de novo." :
        (x as Error).message,
      );
      setSenha("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Entrada>
      <div className="entry-grid">
        <section className="entry-story">
          <div className="eyebrow">Conhecimento que permanece</div>
          <h1>
            Seus sistemas.
            <br />
            Seu conhecimento.
            <br />
            <span>Um só lugar.</span>
          </h1>
          <p>Transforme código e documentação em respostas com contexto e origem.</p>
          <div className="entry-flow" aria-hidden>
            <span><Icone nome="git" />Fontes</span>
            <i />
            <span><Icone nome="book" />Conhecimento</span>
            <i />
            <span><Icone nome="spark" />Respostas</span>
          </div>
        </section>
        <section className="entry-card" aria-labelledby="titulo-entrar">
          <h2 id="titulo-entrar">Bem-vindo ao PetroVault.</h2>
          <p>Entre com a sua conta do hub.</p>

          <form className="entry-ad" onSubmit={enviar} noValidate>
            <label htmlFor="login">Usuário</label>
            <input id="login" name="username" autoComplete="username" placeholder="seu.usuario" value={login}
              onChange={(e) => setLogin(e.target.value)} required autoFocus />
            <label htmlFor="senha">Senha</label>
            <input id="senha" name="password" type="password" autoComplete="current-password" value={senha}
              onChange={(e) => setSenha(e.target.value)} required />
            {erro && <div className="erro-campo" role="alert">{erro}</div>}
            <button className="btn primary" type="submit" disabled={enviando || !login.trim() || !senha}>
              <Icone nome="arrow" />
              {enviando ? "Entrando…" : "Entrar"}
            </button>
          </form>

          <details className="ajuda">
            <summary>Precisa de ajuda?</summary>
            <p>A conta é criada no servidor do hub (<code>python -m app.cli usuario &lt;login&gt;</code>) ou na primeira subida, com <code>VAULT_ADMIN_LOGIN</code> e <code>VAULT_ADMIN_SENHA</code>. A senha fica guardada só como hash.</p>
            <p>Sem acesso? Peça ao administrador do hub para criar a sua conta.</p>
          </details>
        </section>
      </div>
    </Entrada>
  );
}
