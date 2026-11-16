import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ListaSistemas } from "./api";
import { useDados } from "./dados";
import { iniciais } from "./formato";
import { Protecao } from "./Protecao";
import { Icone } from "./icones";
import { useSessao } from "./sessao";
import { useTema } from "./tema";

function Migalhas() {
  const partes = useLocation().pathname.split("/").filter(Boolean);
  const itens: { rotulo: string; para?: string }[] = [{ rotulo: "Vault System", para: "/" }];
  if (partes[0] === "sistemas") {
    itens.push({ rotulo: "Vaults", para: "/sistemas" });
    if (partes[1] === "novo") itens.push({ rotulo: "Novo vault" });
    else if (partes[1]) itens.push({ rotulo: decodeURIComponent(partes[1]) });
  } else if (partes[0] === "tokens") {
    itens.push({ rotulo: "Tokens" });
  } else if (partes[0] === "docs") {
    itens.push({ rotulo: "Docs" });
  } else if (partes[0] === "cli") {
    itens.push({ rotulo: "VS CLI" });
  } else if (partes[0] === "configuracoes") {
    itens.push({ rotulo: "Configurações" });
  } else {
    itens.push({ rotulo: "Início" });
  }
  const ultimo = itens.length - 1;
  return (
    <nav className="crumb" aria-label="Você está em">
      {itens.map((i, n) =>
        n === ultimo || !i.para ? (
          <b key={n} aria-current="page">{i.rotulo}</b>
        ) : (
          <span key={n} className="anterior">
            <Link to={i.para}>{i.rotulo}</Link>
            <span aria-hidden> / </span>
          </span>
        ),
      )}
    </nav>
  );
}

function Perfil() {
  const { eu, sair, marcarApresentacao } = useSessao();
  const [aberto, setAberto] = useState(false);
  const ir = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setAberto(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);
  if (!eu) return null;
  return (
    <div className="profilewrap" ref={ref}>
      <button className="avatar" aria-haspopup="menu" aria-expanded={aberto} aria-label={`Perfil de ${eu.nome}`} onClick={() => setAberto(!aberto)}>
        {iniciais(eu.nome)}
      </button>
      {aberto && (
        <div className="profilemenu" role="menu">
          <div>
            <b style={{ fontWeight: 500 }}>{eu.nome}</b>
            <small style={{ display: "block" }}>{eu.login} · {eu.papel}</small>
          </div>
          <button role="menuitem" onClick={() => { setAberto(false); ir("/configuracoes"); }}>
            <Icone nome="gear" /> Configurações
          </button>
          <button role="menuitem" onClick={async () => { await marcarApresentacao(false); ir("/apresentacao"); }}>
            <Icone nome="help" /> Rever apresentação
          </button>
          <button role="menuitem" onClick={sair}>
            <Icone nome="out" /> Sair
          </button>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { eu } = useSessao();
  const [tema, alternarTema] = useTema();
  const [recolhido, setRecolhido] = useState(() => {
    try { return localStorage.getItem("vs-menu") === "recolhido"; } catch { return false; }
  });
  const { dados } = useDados<ListaSistemas>("/sistemas", 60000);
  const local = useLocation();

  useEffect(() => {
    document.body.classList.toggle("collapsed", recolhido);
    try { localStorage.setItem("vs-menu", recolhido ? "recolhido" : "aberto"); } catch { /* sem armazenamento */ }
  }, [recolhido]);
  // Com chaves: um efeito não pode devolver valor (o React o chamaria como limpeza ao
  // trocar de página, e houve navegador em que scrollTo não devolve undefined).
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [local.pathname]);

  return (
    <>
      <a href="#conteudo" className="visually-hidden">Ir para o conteúdo</a>
      <aside className="sidebar" aria-label="Menu principal">
        <Link to="/" className="brand">
          <img src="/simbolo.svg" alt="" />
          <span>Vault System<b className="ponto" aria-hidden>.</b></span>
        </Link>
        <div className="navlabel">Workspace</div>
        <NavLink to="/" end className="nav" title="Início">
          <Icone nome="home" />
          <span>Início</span>
        </NavLink>
        <NavLink to="/sistemas" className="nav" title="Sistemas">
          <Icone nome="grid" />
          <span>Vaults</span>
          {dados && <span className="count">{dados.sistemas.length}</span>}
        </NavLink>
        <NavLink to="/conversas" className="nav" title="Conversas">
          <Icone nome="spark" />
          <span>Conversas</span>
        </NavLink>
        <NavLink to="/tokens" className="nav" title="Tokens">
          <Icone nome="key" />
          <span>Tokens</span>
        </NavLink>
        <NavLink to="/cli" className="nav" title="CLI">
          <Icone nome="download" />
          <span>CLI</span>
        </NavLink>
        <div className="sidebar-bottom">
          <div className="workspace">
            <img src="/simbolo.svg" alt="" />
            <div>
              <b>{eu?.nome ? `Workspace de ${eu.nome}` : "Workspace"}</b>
              <small>Conhecimento distribuído.</small>
            </div>
          </div>
          <NavLink to="/docs" className="nav" title="Docs">
            <Icone nome="book" />
            <span>Docs</span>
          </NavLink>
          <button className="nav" onClick={() => setRecolhido(!recolhido)} aria-expanded={!recolhido} title={recolhido ? "Abrir menu" : "Recolher menu"}>
            <Icone nome="panel" />
            <span>{recolhido ? "Abrir menu" : "Recolher menu"}</span>
          </button>
        </div>
      </aside>
      <div className="shell">
        <header className="topbar">
          <Migalhas />
          <div className="top-actions">
            {eu && <span className="ambiente">{eu.ambiente}</span>}
            <button className="icon-btn" onClick={alternarTema} aria-label={tema === "escuro" ? "Usar tema claro" : "Usar tema escuro"} title={tema === "escuro" ? "Tema claro" : "Tema escuro"}>
              <Icone nome={tema === "escuro" ? "sun" : "moon"} />
            </button>
            <Perfil />
          </div>
        </header>
        <main id="conteudo">
          <Protecao chave={local.pathname}><Outlet /></Protecao>
          <footer className="foot">
            <span>Vault System · Conhecimento distribuído.</span>
          </footer>
        </main>
      </div>
    </>
  );
}
