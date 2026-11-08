import "@fontsource/ubuntu/300.css";
import "@fontsource/ubuntu/400.css";
import "@fontsource/ubuntu/500.css";
import "./estilo.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ProvedorAviso } from "./componentes";
import { ProvedorSessao } from "./sessao";

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <BrowserRouter>
      <ProvedorSessao>
        <ProvedorAviso>
          <App />
        </ProvedorAviso>
      </ProvedorSessao>
    </BrowserRouter>
  </StrictMode>,
);
