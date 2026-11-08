import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Icone } from "../icones";
import { useSessao } from "../sessao";
import { Entrada } from "./Entrar";

// Três passos na primeira entrada (UX02). Concluir ou pular grava no servidor.
const PASSOS = [
  {
    olho: "01 / Reunir",
    titulo: "Comece pelo seu vault.",
    texto: "Conecte o terminal com um token de conexão e rode vs init vault=<nome> na pasta do projeto. O primeiro vs sync cria o vault. Git é opcional.",
    etapas: ["vs login", "vs init", "vs sync"],
    icone: "git",
  },
  {
    olho: "02 / Conectar",
    titulo: "Notas com origem.",
    texto: "Os arquivos entram como estão. No modo documentado, as notas que o agente do projeto escreveu entram já curadas, cada uma ligada aos arquivos de onde veio, e o verificador confere tudo.",
    etapas: ["Literal", "Notas do agente", "Verificação"],
    icone: "book",
  },
  {
    olho: "03 / Distribuir",
    titulo: "Conhecimento distribuído.",
    texto: "Leia as notas aqui, aplique templates com vs add template e crie tokens de leitura para agentes e sistemas consultarem pela API e pelo MCP.",
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
