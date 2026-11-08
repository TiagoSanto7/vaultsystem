import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EstadoSelo, ListaSistemas } from "../api";
import { Carregando, Falha, Selo, Vazio } from "../componentes";
import { useDados } from "../dados";
import { plural, proxima, repoCurto } from "../formato";
import { Icone } from "../icones";
import { Sinais } from "../sinais";

const FILTROS: { valor: "todos" | EstadoSelo; rotulo: string }[] = [
  { valor: "todos", rotulo: "Todos" },
  { valor: "erro_acesso", rotulo: "Erro de acesso" },
  { valor: "com_problema", rotulo: "Com problema" },
  { valor: "processando", rotulo: "Processando" },
  { valor: "em_dia", rotulo: "Em dia" },
  { valor: "vazio", rotulo: "Aguardando o primeiro pull" },
];

export default function Sistemas() {
  const { dados, erro, carregando, recarregar } = useDados<ListaSistemas>("/sistemas", 20000);
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<(typeof FILTROS)[number]["valor"]>("todos");

  const visiveis = useMemo(() => {
    const b = busca.trim().toLowerCase();
    return (dados?.sistemas ?? []).filter(
      (s) => (filtro === "todos" || s.selo.estado === filtro) &&
        (!b || s.tag.includes(b) || s.origens.some((o) => o.repo.toLowerCase().includes(b))),
    );
  }, [dados, busca, filtro]);

  return (
    <div className="page">
      <div className="heading">
        <div>
          <div className="eyebrow">Catálogo do workspace</div>
          <h1>Vaults</h1>
          <p>O contexto de cada vault, em um só lugar. Os que pedem atenção aparecem primeiro.</p>
        </div>
        <Link className="btn primary" to="/sistemas/novo"><Icone nome="plus" />Novo vault</Link>
      </div>

      {erro && <Falha erro={erro} tentar={recarregar} />}
      {carregando && !dados ? <Carregando /> : dados && (
        <>
          <div className="toolbar">
            <div className="search">
              <Icone nome="search" />
              <input type="search" aria-label="Buscar vault" placeholder="Buscar por tag ou repositório" value={busca} onChange={(e) => setBusca(e.target.value)} />
            </div>
            <select aria-label="Filtrar pelo selo" value={filtro} onChange={(e) => setFiltro(e.target.value as typeof filtro)}>
              {FILTROS.map((f) => (
                <option key={f.valor} value={f.valor}>
                  {f.rotulo}{f.valor !== "todos" && dados.por_estado[f.valor] ? ` (${dados.por_estado[f.valor]})` : ""}
                </option>
              ))}
            </select>
            <small style={{ marginLeft: "auto" }}>
              {(dados.rodadas_em_curso?.length ?? 0) > 1
                ? `Curador em ${dados.rodadas_em_curso!.length} vaults agora: ${dados.rodadas_em_curso!.flatMap((r) => r.tags).join(", ")}`
                : dados.rodada_em_curso ? `Rodada #${dados.rodada_em_curso.id} em curso` : `Próxima rodada do curador ${proxima(dados.proxima_rodada)}`}
            </small>
          </div>

          {dados.sistemas.length === 0 ? (
            <section className="panel">
              <Vazio titulo="Nenhum vault ainda" acao={<Link className="btn primary" to="/sistemas/novo"><Icone nome="plus" />Novo vault</Link>}>
                Um vault reúne um ou mais repositórios do GitHub sob uma tag.
              </Vazio>
            </section>
          ) : visiveis.length === 0 ? (
            <section className="panel"><Vazio titulo="Nenhum vault encontrado">Mude a busca ou o filtro.</Vazio></section>
          ) : (
            <div className="cards">
              {visiveis.map((s) => (
                <article key={s.tag} className="system-card">
                  <div className="card-top">
                    <span className="sysicon"><Icone nome="activity" /></span>
                    <Selo estado={s.selo.estado} titulo={s.selo.texto} />
                  </div>
                  <h2><Link to={`/sistemas/${s.tag}`} style={{ textDecoration: "none" }}>{s.tag}</Link></h2>
                  <p>{s.origens.map((o) => repoCurto(o.repo)).join(" · ") || "Sem origem"}</p>
                  {s.selo.estado !== "em_dia" && s.selo.estado !== "vazio" && <small style={{ display: "block", marginTop: 8 }}>{s.selo.texto}</small>}
                  <div className="card-bottom">
                    <Sinais s={s} />
                  </div>
                  <div className="card-bottom" style={{ marginTop: 12, paddingTop: 12 }}>
                    <span>{plural(s.sinais.notas, "nota", "notas")}</span>
                    <span>{plural(s.origens.length, "origem", "origens")}</span>
                    <Link className="textbtn" style={{ marginLeft: "auto" }} to={`/sistemas/${s.tag}`}>Abrir<Icone nome="arrow" /></Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
