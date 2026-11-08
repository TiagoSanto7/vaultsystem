import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Carregando } from "./componentes";
import Layout from "./Layout";
import { useSessao } from "./sessao";
import Apresentacao from "./telas/Apresentacao";
import Cadastrar from "./telas/Cadastrar";
import Cli from "./telas/Cli";
import Configuracoes from "./telas/Configuracoes";
import Docs from "./telas/Docs";
import Entrar from "./telas/Entrar";
import Inicio from "./telas/Inicio";
import Sistema from "./telas/Sistema";
import Sistemas from "./telas/Sistemas";
import Tokens from "./telas/Tokens";

export default function App() {
  const { eu, verificando } = useSessao();
  const local = useLocation();

  if (verificando) return <Carregando />;
  if (!eu) {
    return (
      <Routes>
        <Route path="/entrar" element={<Entrar />} />
        <Route path="*" element={<Navigate to="/entrar" replace state={{ voltar: local.pathname + local.search }} />} />
      </Routes>
    );
  }
  // Primeira entrada: a apresentação de três passos antes de tudo.
  if (!eu.apresentacao_vista_em && local.pathname !== "/apresentacao") {
    return <Navigate to="/apresentacao" replace state={{ voltar: local.pathname }} />;
  }
  return (
    <Routes>
      <Route path="/entrar" element={<Navigate to={(local.state as { voltar?: string })?.voltar ?? "/"} replace />} />
      <Route path="/apresentacao" element={<Apresentacao />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Inicio />} />
        <Route path="/sistemas" element={<Sistemas />} />
        <Route path="/sistemas/novo" element={<Cadastrar />} />
        <Route path="/cli" element={<Cli />} />
        <Route path="/sistemas/:tag" element={<Sistema />} />
        <Route path="/sistemas/:tag/:aba" element={<Sistema />} />
        <Route path="/tokens" element={<Tokens />} />
        <Route path="/configuracoes" element={<Configuracoes />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/docs/:pagina" element={<Docs />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
