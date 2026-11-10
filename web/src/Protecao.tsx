import { Component, ReactNode } from "react";

/** Um erro de desenho numa tela não pode deixar o hub em branco: mostra o erro e um jeito de seguir.
 * Ao trocar de tela (chave = caminho), a proteção recomeça sem remontar a página. */
export class Protecao extends Component<{ chave: string; children: ReactNode }, { erro: Error | null }> {
  state = { erro: null as Error | null };

  static getDerivedStateFromError(erro: Error) {
    return { erro };
  }

  componentDidCatch(erro: Error) {
    console.error("[vault-system] erro na tela:", erro);
  }

  componentDidUpdate(antes: { chave: string }) {
    if (this.state.erro && antes.chave !== this.props.chave) this.setState({ erro: null });
  }

  render() {
    if (!this.state.erro) return this.props.children;
    return (
      <div className="page">
        <section className="panel" style={{ padding: 24 }}>
          <h2 style={{ marginTop: 0 }}>Esta tela falhou ao abrir</h2>
          <p className="muted">O resto do hub continua funcionando. Mande esta mensagem para quem cuida do hub:</p>
          <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 12, background: "var(--soft)", padding: 12, borderRadius: 8 }}>
            {this.state.erro.message}
          </pre>
          <button type="button" className="btn" onClick={() => window.location.reload()}>Recarregar a página</button>
        </section>
      </div>
    );
  }
}
