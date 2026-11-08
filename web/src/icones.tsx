// Ícones do protótipo aprovado (traço de 1,6 px, 24×24).
const caminhos: Record<string, string> = {
  home: '<path d="m3 10 9-7 9 7v10H4V10"/><path d="M9 20v-7h6v7"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  book: '<path d="M12 5C8 2 4 3 2 4v15c4-2 7-1 10 1 3-2 6-3 10-1V4c-4-2-7-1-10 1v15"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  back: '<path d="M19 12H5m5-5-5 5 5 5"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M4.9 4.9 7 7m10 10 2.1 2.1M2 12h3m14 0h3M4.9 19.1 7 17m10-10 2.1-2.1"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
  git: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="6" r="2"/><path d="M6 7v10m12-9c0 5-12 2-12 9"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
  moon: '<path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m6-11-3 3 3 3"/>',
  spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>',
  file: '<path d="M5 3h9l5 5v13H5zM14 3v6h5M9 13h6m-6 4h6"/>',
  download: '<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>',
  play: '<path d="m8 4 12 8-12 8Z"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  activity: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5m0 3h.01"/>',
  refresh: '<path d="M20 8a9 9 0 0 0-15-3L2 8m0-5v5h5m-3 8a9 9 0 0 0 15 3l3-3m0 5v-5h-5"/>',
  alert: '<path d="M12 3 2 20h20Z"/><path d="M12 10v4m0 3h.01"/>',
  out: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4m-4-4h11"/>',
  external: '<path d="M14 4h6v6m0-6-9 9M18 14v6H4V6h6"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9m-3 3 3 3m-6 0 2 2"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>',
};

export function Icone({ nome, titulo }: { nome: string; titulo?: string }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" aria-hidden={titulo ? undefined : true} role={titulo ? "img" : undefined}
      aria-label={titulo} dangerouslySetInnerHTML={{ __html: caminhos[nome] ?? caminhos.grid }} />
  );
}
