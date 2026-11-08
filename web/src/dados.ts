import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Busca `caminho` na API da tela e, se `intervalo` for dado (ms), atualiza
 *  sozinho enquanto a aba do navegador estiver visível: assim um pull pode ser
 *  acompanhado sem recarregar a página. Com `manter`, os dados antigos continuam na
 *  tela enquanto o novo caminho carrega (ex.: "Mostrar mais" numa tabela). */
export function useDados<T>(caminho: string | null, intervalo?: number, manter = false) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const atual = useRef(caminho);
  atual.current = caminho;

  const buscar = useCallback(async () => {
    if (!caminho) return;
    try {
      const d = await api<T>(caminho);
      if (atual.current === caminho) {
        setDados(d);
        setErro(null);
      }
    } catch (e) {
      if (atual.current === caminho) setErro((e as Error).message);
    } finally {
      if (atual.current === caminho) setCarregando(false);
    }
  }, [caminho]);

  useEffect(() => {
    setCarregando(true);
    if (!manter) setDados(null);
    buscar();
    if (!intervalo) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") buscar();
    }, intervalo);
    return () => window.clearInterval(id);
  }, [buscar, intervalo, manter]);

  return { dados, erro, carregando, recarregar: buscar };
}

/** Rola até o `#ancora` da URL quando `pronto` (os sinais levam a uma seção da aba). */
export function useAncora(pronto: boolean) {
  useEffect(() => {
    if (!pronto || !window.location.hash) return;
    const alvo = document.getElementById(window.location.hash.slice(1));
    alvo?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [pronto]);
}
