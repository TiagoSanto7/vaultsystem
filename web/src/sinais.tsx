import { Link } from "react-router-dom";
import { ResumoSistema } from "./api";
import { plural } from "./formato";

// Os sinais de confiança (tela-plano.md, seção 2.1). Cada um leva à aba que o explica.

const EM_DIA: Record<string, { texto: string; cor: string }> = {
  em_dia: { texto: "Origens em dia", cor: "green" },
  atrasado: { texto: "Origem atrasada", cor: "amber" },
  nunca_processado: { texto: "Nunca processado", cor: "muted" },
  sem_acesso: { texto: "Sem acesso", cor: "red" },
};

export function Sinais({ s }: { s: ResumoSistema }) {
  const base = `/sistemas/${s.tag}`;
  const e = EM_DIA[s.sinais.em_dia.estado] ?? EM_DIA.nunca_processado;
  const v = s.sinais.verificacao.total;
  const fila = s.sinais.fila;
  return (
    <div className="sinais">
      <Link className={`sinal ${e.cor}`} to={`${base}/fontes`}>
        {e.texto}
        {s.sinais.em_dia.estado === "atrasado" && s.sinais.em_dia.commits_atras > 0 && ` (${plural(s.sinais.em_dia.commits_atras, "commit", "commits")})`}
      </Link>
      <Link className={`sinal ${fila.parados ? "amber" : ""}`} to={`${base}/fontes#fila`}>
        {fila.itens ? `${plural(fila.itens, "item", "itens")} na fila` : "Fila vazia"}
        {fila.parados > 0 && ` · ${fila.parados} parado${fila.parados > 1 ? "s" : ""}`}
      </Link>
      <Link className={`sinal ${v ? "amber" : v === 0 ? "green" : ""}`} to={`${base}/conhecimento#verificacao`}>
        {v === null ? "Nunca verificado" : v === 0 ? "Verificação limpa" : `${plural(v, "problema", "problemas")} na verificação`}
      </Link>
      {s.sinais.ignorados.total > 0 && (
        <Link className="sinal" to={`${base}/fontes#ignorados`} title={s.sinais.ignorados.motivos.join(", ")}>
          {plural(s.sinais.ignorados.total, "ignorado", "ignorados")} no último pull
        </Link>
      )}
    </div>
  );
}
