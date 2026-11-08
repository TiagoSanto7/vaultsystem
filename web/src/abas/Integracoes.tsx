import { useState } from "react";
import { Link } from "react-router-dom";
import { Credencial, Sistema } from "../api";
import { Carregando, Falha, Vazio } from "../componentes";
import { useDados } from "../dados";
import { Icone } from "../icones";
import { ComoUsar, TabelaTokens } from "../telas/Tokens";
import { CriarToken } from "../tokens";

// Tokens que leem este vault. A gestão completa (um token com vários vaults)
// fica na aba Tokens; aqui o token novo já vem com este vault marcado.

export default function Integracoes({ s }: { s: Sistema }) {
  const { dados, erro, recarregar } = useDados<Credencial[]>(`/credenciais?tag=${encodeURIComponent(s.tag)}`);
  const [criar, setCriar] = useState(false);
  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Integrações</h2>
            <small>
              Tokens que podem consultar o conhecimento de {s.tag}, por API ou MCP. Um token pode ler vários vaults; a lista completa está em <Link to="/tokens">Tokens</Link>.
            </small>
          </div>
          <button className="btn primary" onClick={() => setCriar(true)}><Icone nome="key" />Criar token</button>
        </div>
        {erro && <div className="panel-body"><Falha erro={erro} tentar={recarregar} /></div>}
        {!dados ? <Carregando /> : (
          <TabelaTokens tokens={dados} recarregar={recarregar}
            vazio={<Vazio titulo="Nenhum token lê este vault">Crie um token para cada aplicação ou agente que vai consultar {s.tag}.</Vazio>} />
        )}
      </section>
      <ComoUsar vault={s.tag} />
      {criar && <CriarToken inicial={[s.tag]} fechar={() => setCriar(false)} feito={recarregar} />}
    </>
  );
}
