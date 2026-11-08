import { useState } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { api, Sistema as TSistema } from "../api";
import Conhecimento from "../abas/Conhecimento";
import Fontes from "../abas/Fontes";
import Integracoes from "../abas/Integracoes";
import Mapa from "../abas/Mapa";
import Processamento from "../abas/Processamento";
import Arquivos from "../abas/Arquivos";
import Renderizacao, { temReferencia } from "../abas/Renderizacao";
import VisaoGeral from "../abas/VisaoGeral";
import { Carregando, Falha, Selo, useAviso } from "../componentes";
import { useDados } from "../dados";
import { plural } from "../formato";
import { Icone } from "../icones";

// Agente (DV-577) entra aqui quando existir de verdade.
const ABAS = [
  { slug: "", rotulo: "Visão geral" },
  { slug: "fontes", rotulo: "Fontes" },
  { slug: "processamento", rotulo: "Processamento" },
  { slug: "conhecimento", rotulo: "Conhecimento" },
  { slug: "mapa", rotulo: "Mapa" },
  { slug: "renderizacao", rotulo: "Renderização" }, // DV-600: só em vault com origem de Referência
  { slug: "arquivos", rotulo: "Arquivos" }, // DV-601: idem
  { slug: "integracoes", rotulo: "Integrações" },
] as const;

function pontoDaAba(s: TSistema, slug: string): "" | "warn" | "erro" {
  if (slug === "fontes") {
    if (s.origens.some((o) => o.situacao === "sem_acesso")) return "erro";
    return s.sinais.fila.itens > 0 || s.sinais.em_dia.estado === "atrasado" ? "warn" : "";
  }
  if (slug === "processamento") return s.ultima_rodada?.ultimo_lote?.erro || s.ultimo_pull?.erro ? "warn" : "";
  if (slug === "conhecimento") return s.sinais.verificacao.total ? "warn" : "";
  return "";
}

export default function Sistema() {
  const { tag = "", aba = "" } = useParams();
  const { dados: s, erro, carregando, recarregar } = useDados<TSistema>(`/sistemas/${encodeURIComponent(tag)}`, 15000);
  const [pedindo, setPedindo] = useState(false);
  const avisar = useAviso();

  async function pedirPull() {
    setPedindo(true);
    try {
      const r = await api<{ pedido: number; ja_havia: boolean }>(`/sistemas/${tag}/pull`, { metodo: "POST" });
      avisar(r.ja_havia ? `O pull #${r.pedido} já estava pedido. O curador atende em até 30 s.` : `Pull #${r.pedido} pedido. O curador atende em até 30 s.`);
      recarregar();
    } catch (x) {
      avisar((x as Error).message);
    } finally {
      setPedindo(false);
    }
  }

  if (carregando && !s) return <Carregando />;
  if (!s) {
    return (
      <div className="page">
        <Link className="back" to="/sistemas"><Icone nome="back" />Todos os vaults</Link>
        <Falha erro={erro ?? "Vault não encontrado."} tentar={recarregar} />
      </div>
    );
  }

  const removendo = !!s.removido_em;
  const conteudo = {
    "": <VisaoGeral s={s} recarregar={recarregar} />,
    fontes: <Fontes s={s} recarregar={recarregar} />,
    processamento: <Processamento s={s} pedirPull={pedirPull} pedindo={pedindo} />,
    conhecimento: <Conhecimento s={s} />,
    mapa: <Mapa s={s} />,
    renderizacao: temReferencia(s) ? <Renderizacao s={s} /> : undefined,
    arquivos: temReferencia(s) ? <Arquivos s={s} /> : undefined,
    integracoes: <Integracoes s={s} />,
  }[aba];

  return (
    <div className="page">
      <Link className="back" to="/sistemas"><Icone nome="back" />Todos os vaults</Link>
      <div className="heading">
        <div className="system-title">
          <span className="sysicon"><Icone nome="activity" /></span>
          <div>
            <h1>{s.tag}</h1>
            <p style={{ marginTop: 4 }}>
              {plural(s.origens.length, "origem", "origens")} · {plural(s.sinais.notas, "nota", "notas")} · cadastrado por {s.cadastro.por}
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <Selo estado={s.selo.estado} titulo={s.selo.texto} />
          <button className="btn primary" onClick={pedirPull} disabled={pedindo || removendo || s.pull_pendente !== null}>
            <Icone nome="refresh" />
            {s.pull_pendente !== null ? `Pull #${s.pull_pendente} pedido` : pedindo ? "Pedindo…" : "Pedir pull"}
          </button>
        </div>
      </div>
      {erro && <Falha erro={`Não consegui atualizar agora: ${erro}`} tentar={recarregar} />}
      {s.selo.estado !== "em_dia" && s.selo.estado !== "vazio" && (
        <div className={`banner ${s.selo.estado === "erro_acesso" ? "erro" : s.selo.estado === "com_problema" ? "warn" : ""}`} role="status">
          <Icone nome={s.selo.estado === "processando" || removendo ? "clock" : "alert"} />
          <span>{s.selo.texto}</span>
        </div>
      )}
      <nav className="tabs" aria-label="Seções do vault">
        {ABAS.filter((a) => (a.slug !== "renderizacao" && a.slug !== "arquivos") || temReferencia(s)).map((a) => {
          const p = pontoDaAba(s, a.slug);
          return (
            <NavLink key={a.slug} end to={`/sistemas/${s.tag}${a.slug ? `/${a.slug}` : ""}`} className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
              {a.rotulo}
              {p && <i className={`ponto ${p === "erro" ? "erro" : ""}`} aria-label="pede atenção" />}
            </NavLink>
          );
        })}
      </nav>
      {conteudo ?? <Falha erro="Esta seção não existe." />}
    </div>
  );
}
