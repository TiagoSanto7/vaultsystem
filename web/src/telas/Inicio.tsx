import { Link } from "react-router-dom";
import { ListaSistemas } from "../api";
import { Carregando, Falha, Selo, Vazio } from "../componentes";
import { useDados } from "../dados";
import { plural, proxima } from "../formato";
import { Icone } from "../icones";
import { useSessao } from "../sessao";

export default function Inicio() {
  const { eu } = useSessao();
  const { dados, erro, carregando, recarregar } = useDados<ListaSistemas>("/sistemas", 30000);
  const primeiro = eu?.nome.split(/\s+/)[0] ?? "";

  const sistemas = dados?.sistemas ?? [];
  const notas = sistemas.reduce((t, s) => t + s.sinais.notas, 0);
  const origens = sistemas.reduce((t, s) => t + s.origens.length, 0);
  const problemas = sistemas.reduce((t, s) => t + (s.sinais.verificacao.total ?? 0), 0);
  const atencao = (dados?.por_estado.erro_acesso ?? 0) + (dados?.por_estado.com_problema ?? 0);

  return (
    <div className="page">
      <div className="heading">
        <div>
          <div className="eyebrow">Seu conhecimento, conectado</div>
          <h1>Olá, {primeiro}<span className="green">.</span></h1>
          <p>Uma visão clara do que seus vaults sabem.</p>
        </div>
      </div>

      <section className="hero">
        <div className="hero-copy">
          <h2>Conhecimento distribuído.</h2>
          <p>Reúna arquivos e decisões, conecte cada nota à sua origem e distribua o contexto para pessoas, agentes e ferramentas.</p>
          <Link className="btn primary" to="/sistemas"><Icone nome="arrow" />Explorar vaults</Link>
        </div>
        <div className="hero-art" aria-hidden>
          <span className="orbit" />
          <span className="orbit two" />
          <div className="vault"><img src="/simbolo.svg" alt="" /></div>
        </div>
      </section>

      {erro && <Falha erro={erro} tentar={recarregar} />}
      {carregando && !dados ? <Carregando /> : dados && (
        <>
          <div className="metrics">
            <Link className="metric" to="/sistemas">
              <div className="metric-top">Vaults<Icone nome="grid" /></div>
              <strong>{sistemas.length}</strong>
              <small>{dados.por_estado.em_dia ?? 0} em dia</small>
            </Link>
            <div className="metric">
              <div className="metric-top">Notas de conhecimento<Icone nome="book" /></div>
              <strong>{notas.toLocaleString("pt-BR")}</strong>
              <small>Curadas em Markdown, com origem</small>
            </div>
            <div className="metric">
              <div className="metric-top">Origens<Icone nome="git" /></div>
              <strong>{origens}</strong>
              <small>Fontes cadastradas</small>
            </div>
            <div className="metric">
              <div className="metric-top">Pedem atenção<Icone nome="alert" /></div>
              <strong className={atencao ? "amber" : ""}>{atencao}</strong>
              <small>{problemas ? `${plural(problemas, "problema", "problemas")} na verificação` : "Nenhum problema na verificação"}</small>
            </div>
          </div>

          <div className="columns">
            <section className="panel">
              <div className="panel-head">
                <h2>Vaults</h2>
                <Link className="textbtn" to="/sistemas">Ver todos<Icone nome="arrow" /></Link>
              </div>
              {sistemas.length === 0 ? (
                <Vazio titulo="Nenhum vault ainda" acao={<Link className="btn primary" to="/sistemas/novo"><Icone nome="plus" />Novo vault</Link>}>
                  Crie o primeiro vault e as suas fontes.
                </Vazio>
              ) : sistemas.slice(0, 6).map((s) => (
                <Link key={s.tag} className="system-row" to={`/sistemas/${s.tag}`}>
                  <span className="sysicon"><Icone nome="activity" /></span>
                  <span>
                    <b style={{ fontWeight: 500 }}>{s.tag}</b>
                    <small>{plural(s.origens.length, "origem", "origens")} · {plural(s.sinais.notas, "nota", "notas")}</small>
                  </span>
                  <Selo estado={s.selo.estado} titulo={s.selo.texto} />
                  <Icone nome="chevron" />
                </Link>
              ))}
            </section>
            <section className="panel">
              <div className="panel-head"><h2>Curador</h2></div>
              <div className="panel-body">
                <ul className="kv">
                  <li>
                    <span>Agora</span>
                    <span>{dados.rodada_em_curso ? <><i className="dot pulse" /> Rodada #{dados.rodada_em_curso.id} em curso</> : "Aguardando a próxima rodada"}</span>
                  </li>
                  <li><span>Próxima rodada</span><span>{proxima(dados.proxima_rodada)}</span></li>
                  <li><span>Em dia</span><span>{dados.por_estado.em_dia ?? 0}</span></li>
                  <li><span>Processando</span><span>{dados.por_estado.processando ?? 0}</span></li>
                  <li><span>Com problema</span><span>{dados.por_estado.com_problema ?? 0}</span></li>
                  <li><span>Erro de acesso</span><span>{dados.por_estado.erro_acesso ?? 0}</span></li>
                </ul>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
