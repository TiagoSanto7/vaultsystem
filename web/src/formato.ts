export function dataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function hora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Quando o curador roda de novo: "em 4 min", ou "a qualquer momento" se a hora já passou. */
export function proxima(iso: string | null | undefined, agora = Date.now()): string {
  if (!iso) return "—";
  return new Date(iso).getTime() <= agora ? "a qualquer momento" : relativo(iso, agora);
}

/** "há 5 min", "há 2 h", "há 3 dias"; para datas futuras, "em 4 min". */
export function relativo(iso: string | null | undefined, agora = Date.now()): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.round((agora - t) / 1000);
  const futuro = s < 0;
  const a = Math.abs(s);
  const txt = a < 60 ? "menos de 1 min" : a < 3600 ? `${Math.floor(a / 60)} min` : a < 86400 ? `${Math.floor(a / 3600)} h` : `${Math.floor(a / 86400)} dia${Math.floor(a / 86400) > 1 ? "s" : ""}`;
  return futuro ? `em ${txt}` : `há ${txt}`;
}

export function curto(hash: string | null | undefined): string {
  return hash ? hash.slice(0, 7) : "—";
}

export function plural(n: number, um: string, varios: string): string {
  return `${n.toLocaleString("pt-BR")} ${n === 1 ? um : varios}`;
}

export function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter((p) => p.length > 2 || /^[A-Z]/.test(p));
  return ((partes[0]?.[0] ?? "") + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase() || "?";
}

export function repoCurto(repo: string): string {
  const m = repo.match(/[:/]([^/:]+\/[^/]+?)(\.git)?$/);
  return m ? m[1] : repo;
}
