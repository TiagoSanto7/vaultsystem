import { useCallback, useState } from "react";

export type Tema = "claro" | "escuro";

function lido(): Tema {
  return document.documentElement.dataset.tema === "escuro" ? "escuro" : "claro";
}

export function useTema(): [Tema, () => void] {
  const [tema, setTema] = useState<Tema>(lido);
  const alternar = useCallback(() => {
    const novo: Tema = lido() === "escuro" ? "claro" : "escuro";
    if (novo === "escuro") document.documentElement.dataset.tema = "escuro";
    else delete document.documentElement.dataset.tema;
    try {
      localStorage.setItem("pv-tema", novo);
    } catch {
      /* navegador sem armazenamento: o tema vale só nesta página */
    }
    setTema(novo);
  }, []);
  return [tema, alternar];
}
