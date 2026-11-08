import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, ErroApi, Eu, quandoPerderSessao } from "./api";

interface Sessao {
  eu: Eu | null;
  verificando: boolean;
  entrar: (login: string, senha: string) => Promise<void>;
  sair: () => Promise<void>;
  marcarApresentacao: (vista: boolean) => Promise<void>;
}

const Contexto = createContext<Sessao>(null as unknown as Sessao);
export const useSessao = () => useContext(Contexto);

export function ProvedorSessao({ children }: { children: ReactNode }) {
  const [eu, setEu] = useState<Eu | null>(null);
  const [verificando, setVerificando] = useState(true);

  useEffect(() => {
    quandoPerderSessao(() => setEu(null));
    api<Eu>("/eu", { semRedirecionar: true })
      .then(setEu)
      .catch(() => setEu(null))
      .finally(() => setVerificando(false));
  }, []);

  const entrar = useCallback(async (login: string, senha: string) => {
    await api("/entrar", { metodo: "POST", corpo: { login, senha }, semRedirecionar: true });
    setEu(await api<Eu>("/eu", { semRedirecionar: true }));
  }, []);

  const sair = useCallback(async () => {
    await api("/sair", { metodo: "POST" }).catch(() => undefined);
    setEu(null);
  }, []);

  const marcarApresentacao = useCallback(async (vista: boolean) => {
    const r = await api<{ apresentacao_vista_em: string | null }>("/eu/apresentacao", { metodo: "PUT", corpo: { vista } });
    setEu((e) => (e ? { ...e, apresentacao_vista_em: r.apresentacao_vista_em } : e));
  }, []);

  return <Contexto.Provider value={{ eu, verificando, entrar, sair, marcarApresentacao }}>{children}</Contexto.Provider>;
}

export { ErroApi };
