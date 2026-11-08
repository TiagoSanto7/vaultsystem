import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { EstadoSelo } from "./api";
import { Icone } from "./icones";

// --- selo geral de um sistema (tela-plano.md, seção 2.2) ---------------------

const SELOS: Record<EstadoSelo, { rotulo: string; classe: string }> = {
  erro_acesso: { rotulo: "Erro de acesso", classe: "erro" },
  com_problema: { rotulo: "Com problema", classe: "warn" },
  processando: { rotulo: "Processando", classe: "neutral" },
  em_dia: { rotulo: "Em dia", classe: "" },
  vazio: { rotulo: "Aguardando o primeiro pull", classe: "neutral" },
  removendo: { rotulo: "Removendo", classe: "neutral" },
};

export function Selo({ estado, titulo }: { estado: EstadoSelo; titulo?: string }) {
  const s = SELOS[estado] ?? SELOS.vazio;
  return (
    <span className={`badge ${s.classe}`} title={titulo}>
      <i className={`dot ${estado === "processando" ? "pulse" : ""}`} />
      {s.rotulo}
    </span>
  );
}

export function Badge({ tipo = "", children }: { tipo?: "" | "warn" | "erro" | "neutral"; children: ReactNode }) {
  return (
    <span className={`badge ${tipo}`}>
      <i className="dot" />
      {children}
    </span>
  );
}

// --- avisos rápidos ----------------------------------------------------------

const ContextoAviso = createContext<(texto: string) => void>(() => {});
export const useAviso = () => useContext(ContextoAviso);

export function ProvedorAviso({ children }: { children: ReactNode }) {
  const [texto, setTexto] = useState<string | null>(null);
  const timer = useRef<number>();
  const avisar = useCallback((t: string) => {
    setTexto(t);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setTexto(null), 4200);
  }, []);
  return (
    <ContextoAviso.Provider value={avisar}>
      {children}
      <div aria-live="polite">{texto && <div className="toast" role="status">{texto}</div>}</div>
    </ContextoAviso.Provider>
  );
}

// --- janela modal ------------------------------------------------------------

export function Modal({ titulo, aoFechar, children, largura }: { titulo: string; aoFechar: () => void; children: ReactNode; largura?: number }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const antes = document.activeElement as HTMLElement | null;
    const primeiro = ref.current?.querySelector<HTMLElement>("input, select, textarea, button:not([data-fechar])");
    (primeiro ?? ref.current)?.focus();
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") aoFechar();
      if (e.key === "Tab" && ref.current) {
        const focaveis = ref.current.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input, select, textarea, [tabindex='0']");
        if (!focaveis.length) return;
        const [a, z] = [focaveis[0], focaveis[focaveis.length - 1]];
        if (e.shiftKey && document.activeElement === a) { z.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === z) { a.focus(); e.preventDefault(); }
      }
    };
    document.addEventListener("keydown", tecla);
    return () => { document.removeEventListener("keydown", tecla); antes?.focus(); };
  }, [aoFechar]);
  // No body: dentro da página, um ancestral com transform (a animação de
  // entrada) prende o position: fixed a ele, e o modal abria no meio da página.
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={titulo} ref={ref} tabIndex={-1} style={largura ? { width: largura } : undefined}>
        <div className="modal-header">
          <h2>{titulo}</h2>
          <button className="icon-btn" onClick={aoFechar} aria-label="Fechar" data-fechar>
            <Icone nome="close" />
          </button>
        </div>
        {children}
      </section>
    </div>,
    document.body,
  );
}

// --- estados de carregamento -------------------------------------------------

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return <div className="carregando" role="status">{texto}</div>;
}

export function Falha({ erro, tentar }: { erro: string; tentar?: () => void }) {
  return (
    <div className="banner erro" role="alert">
      <Icone nome="alert" />
      <span>{erro}</span>
      {tentar && <button className="textbtn" onClick={tentar}>Tentar de novo</button>}
    </div>
  );
}

export function Vazio({ titulo, children, acao }: { titulo: string; children?: ReactNode; acao?: ReactNode }) {
  return (
    <div className="empty">
      <h2>{titulo}</h2>
      {children && <p>{children}</p>}
      {acao}
    </div>
  );
}

/** Rodapé de tabela paginada: quantas linhas aparecem e o botão para trazer mais. */
export function MaisLinhas({ mostrando, total, mais, passo }: { mostrando: number; total: number; mais: () => void; passo: number }) {
  return (
    <div className="table-foot">
      <small>Mostrando {mostrando} de {total}</small>
      {total > mostrando && <button className="textbtn" onClick={mais}>Mostrar mais {Math.min(passo, total - mostrando)}</button>}
    </div>
  );
}

/** Paginação no navegador para listas que já vieram inteiras: devolve as primeiras
 *  `passo` linhas e o rodapé com "Mostrar mais" (nenhuma tabela cresce sem limite). */
export function usePagina<T>(lista: T[] | null | undefined, passo = 10) {
  const [n, setN] = useState(passo);
  const todos = lista ?? [];
  return {
    visiveis: todos.slice(0, n),
    rodape: todos.length > passo ? <MaisLinhas mostrando={Math.min(n, todos.length)} total={todos.length} passo={passo} mais={() => setN(n + passo)} /> : null,
  };
}

export function LinkExterno({ href, children, className = "textbtn" }: { href: string | null | undefined; children: ReactNode; className?: string }) {
  if (!href) return <span>{children}</span>;
  return (
    <a className={className} href={href} target="_blank" rel="noreferrer noopener">
      {children}
      <Icone nome="external" />
      <span className="visually-hidden">(abre em outra aba)</span>
    </a>
  );
}
