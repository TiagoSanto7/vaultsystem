import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Icone } from "../icones";
import { useSessao } from "../sessao";
import { Entrada } from "./Entrar";

// Três passos na primeira entrada (UX02). Concluir ou pular grava no servidor.
const PASSOS = [
  {
    olho: "01 / Conecte o contexto",
    titulo: "Comece pelo seu vault.",
    texto: "Crie o vault e escolha as fontes: os repositórios do GitHub com o código e a documentação.",
    etapas: ["Vault", "Repositórios", "Pastas"],
    icone: "git",
  },
  {
    olho: "02 / Produza conhecimento",
    titulo: "Notas com origem.",
    texto: "A cada commit, o curador lê o que mudou e escreve notas em Markdown. Cada nota aponta para o arquivo e o commit de onde veio, e o verificador confere tudo.",
    etapas: ["Fila", "Curadoria", "Verificação"],
    icone: "book",
  },
  {
    olho: "03 / Consulte e integre",
    titulo: "Conhecimento que trabalha.",
    texto: "Leia as notas aqui e crie uma credencial para que agentes e sistemas consultem o conhecimento de um vault pela API, só leitura.",
    etapas: ["Notas", "Integrações", "Agentes"],
    icone: "spark",
  },
];

export default function Apresentacao() {
  const [passo, setPasso] = useState(0);
  const { marcarApresentacao } = useSessao();
  const ir = useNavigate();
  const voltar = (useLocation().state as { voltar?: string })?.voltar ?? "/";
  const p = PASSOS[passo];
  const ultimo = passo === PASSOS.length - 1;

  async function concluir() {
    await marcarApresentacao(true).catch(() => undefined);
    ir(voltar === "/apresentacao" ? "/" : voltar, { replace: true });
  }

  return (
    <Entrada luz>
      <section className="welcome-card" aria-roledescription="apresentação" aria-label={`Passo ${passo + 1} de ${PASSOS.length}`}>
        <div className="welcome-top">
          <span>Uma introdução rápida</span>
          <button className="textbtn" onClick={concluir}>Pular apresentação</button>
        </div>
        <div className="welcome-content" key={passo}>
          <div className="welcome-symbol" aria-hidden><Icone nome={p.icone} /></div>
          <div className="eyebrow">{p.olho}</div>
          <h1>{p.titulo}</h1>
          <p className="descr">{p.texto}</p>
          <div className="welcome-steps" aria-hidden>
            {p.etapas.map((e, i) => (
              <span key={e} style={{ display: "contents" }}>
                {i > 0 && <span>→</span>}
                <b>{e}</b>
              </span>
            ))}
          </div>
        </div>
        <div className="welcome-bottom">
          <div className="welcome-dots">
            {PASSOS.map((_, i) => (
              <button key={i} className={i === passo ? "active" : ""} aria-label={`Ir para o passo ${i + 1}`}
                aria-current={i === passo ? "step" : undefined} onClick={() => setPasso(i)} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            {passo > 0 && <button className="btn" onClick={() => setPasso(passo - 1)}><Icone nome="back" />Voltar</button>}
            <button className="btn primary" onClick={() => (ultimo ? concluir() : setPasso(passo + 1))}>
              <Icone nome={ultimo ? "check" : "arrow"} />
              {ultimo ? "Começar" : "Continuar"}
            </button>
          </div>
        </div>
      </section>
    </Entrada>
  );
}
