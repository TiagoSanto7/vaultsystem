import { useRef } from "react";
import { Icone } from "./icones";

// Envio pelo painel: arquivos soltos, uma pasta inteira ou um ZIP pronto. Arquivos e pasta viram um ZIP
// no navegador (deflate do próprio navegador), no mesmo formato que o vs sync envia.

export const LIMITE_ENVIO = 10 * 1024 * 1024;
const FORA = new Set([".git", "node_modules", ".venv", "venv", "__pycache__", ".vs", ".vaultsystem", ".ds_store", "thumbs.db"]);

export interface Selecao {
  arquivos: { caminho: string; arquivo: File }[];
  zip?: File; // um ZIP pronto, enviado como está
  pasta?: string; // nome da pasta escolhida (para sugerir o nome da origem)
  fora: number; // quantos ficaram de fora (.git, node_modules, .env…)
}

function ficaFora(caminho: string) {
  const partes = caminho.toLowerCase().split("/");
  const nome = partes[partes.length - 1];
  return partes.some((p) => FORA.has(p)) || nome === ".env" || (nome.startsWith(".env.") && nome !== ".env.example");
}

/** Arquivos escolhidos -> seleção. manterPasta: num vault de template, a pasta escolhida é o template. */
function selecionar(lista: FileList, comoPasta: boolean, manterPasta: boolean): Selecao {
  const todos = Array.from(lista);
  if (!comoPasta && todos.length === 1 && /\.zip$/i.test(todos[0].name)) return { arquivos: [], zip: todos[0], fora: 0 };
  let pasta: string | undefined;
  let fora = 0;
  const arquivos: Selecao["arquivos"] = [];
  for (const f of todos) {
    let caminho = (comoPasta && f.webkitRelativePath) || f.name;
    if (comoPasta) {
      const [topo, ...resto] = caminho.split("/");
      pasta = pasta ?? topo;
      if (!manterPasta) caminho = resto.join("/");
    }
    if (!caminho || ficaFora(caminho)) {
      fora++;
      continue;
    }
    arquivos.push({ caminho, arquivo: f });
  }
  return { arquivos, pasta, fora };
}

// --- ZIP ---------------------------------------------------------------------------------------------

const TABELA = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(dados: Uint8Array) {
  let c = 0xffffffff;
  for (let i = 0; i < dados.length; i++) c = TABELA[(c ^ dados[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

async function comprimir(dados: Uint8Array): Promise<Uint8Array | null> {
  if (typeof CompressionStream === "undefined") return null;
  const fluxo = new Blob([dados]).stream().pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(fluxo).arrayBuffer());
}

/** ZIP com os arquivos (deflate quando o navegador comprime e compensa; senão, guardado). */
export async function montarZip(arquivos: Selecao["arquivos"]): Promise<Blob> {
  const partes: BlobPart[] = [];
  const central: Uint8Array[] = [];
  let posicao = 0;
  const texto = new TextEncoder();
  for (const { caminho, arquivo } of arquivos) {
    const dados = new Uint8Array(await arquivo.arrayBuffer());
    const comprimido = await comprimir(dados);
    const usa = comprimido && comprimido.length < dados.length;
    const corpo = usa ? comprimido! : dados;
    const nome = texto.encode(caminho);
    const crc = crc32(dados);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true); // nomes em UTF-8
    local.setUint16(8, usa ? 8 : 0, true);
    local.setUint16(10, 0, true);
    local.setUint16(12, 0x21, true); // 1980-01-01
    local.setUint32(14, crc, true);
    local.setUint32(18, corpo.length, true);
    local.setUint32(22, dados.length, true);
    local.setUint16(26, nome.length, true);
    local.setUint16(28, 0, true);
    partes.push(local.buffer, nome, corpo);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true);
    c.setUint16(4, 20, true);
    c.setUint16(6, 20, true);
    c.setUint16(8, 0x0800, true);
    c.setUint16(10, usa ? 8 : 0, true);
    c.setUint16(12, 0, true);
    c.setUint16(14, 0x21, true);
    c.setUint32(16, crc, true);
    c.setUint32(20, corpo.length, true);
    c.setUint32(24, dados.length, true);
    c.setUint16(28, nome.length, true);
    c.setUint32(42, posicao, true);
    const entrada = new Uint8Array(46 + nome.length);
    entrada.set(new Uint8Array(c.buffer), 0);
    entrada.set(nome, 46);
    central.push(entrada);
    posicao += 30 + nome.length + corpo.length;
  }
  const tamanhoCentral = central.reduce((s, e) => s + e.length, 0);
  const fim = new DataView(new ArrayBuffer(22));
  fim.setUint32(0, 0x06054b50, true);
  fim.setUint16(8, central.length, true);
  fim.setUint16(10, central.length, true);
  fim.setUint32(12, tamanhoCentral, true);
  fim.setUint32(16, posicao, true);
  return new Blob([...partes, ...central, fim.buffer], { type: "application/zip" });
}

/** O pacote para enviar: o ZIP escolhido ou um ZIP montado com os arquivos. Erro se passa do limite. */
export async function pacoteDa(s: Selecao): Promise<Blob> {
  const pacote = s.zip ?? (await montarZip(s.arquivos));
  if (pacote.size > LIMITE_ENVIO) throw new Error("O envio passa de 10 MB, mesmo compactado. Escolha menos arquivos ou use o vs sync.");
  return pacote;
}

function tamanho(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Escolher arquivos, uma pasta ou um ZIP. */
export function EscolherArquivos({ id, valor, mudar, manterPasta = false }: {
  id: string; valor: Selecao | null; mudar: (s: Selecao | null) => void; manterPasta?: boolean;
}) {
  const arquivos = useRef<HTMLInputElement>(null);
  const pasta = useRef<HTMLInputElement>(null);
  const total = valor ? (valor.zip ? valor.zip.size : valor.arquivos.reduce((s, a) => s + a.arquivo.size, 0)) : 0;
  return (
    <div className="escolher-arquivos">
      <input ref={arquivos} id={`${id}-arquivos`} type="file" multiple hidden
        onChange={(e) => { if (e.target.files?.length) mudar(selecionar(e.target.files, false, manterPasta)); e.target.value = ""; }} />
      <input ref={pasta} id={`${id}-pasta`} type="file" hidden
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        onChange={(e) => { if (e.target.files?.length) mudar(selecionar(e.target.files, true, manterPasta)); e.target.value = ""; }} />
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button type="button" className="btn" onClick={() => arquivos.current?.click()}><Icone nome="plus" />Escolher arquivos</button>
        <button type="button" className="btn" onClick={() => pasta.current?.click()}><Icone nome="plus" />Escolher pasta</button>
      </div>
      <small className="muted">Arquivos soltos, uma pasta inteira ou um ZIP pronto, até 10 MB depois de compactado. <code>.git</code>, <code>node_modules</code> e <code>.env</code> ficam de fora.</small>
      {valor && (
        <div className="escolha">
          <b>{valor.zip ? valor.zip.name : valor.pasta ? `Pasta ${valor.pasta}` : `${valor.arquivos.length} arquivo(s)`}</b>
          <span className="muted">
            {valor.zip ? "ZIP enviado como está" : `${valor.arquivos.length} arquivo(s)`} · {tamanho(total)}
            {valor.fora ? ` · ${valor.fora} de fora` : ""}
          </span>
          <button type="button" className="textbtn" onClick={() => mudar(null)}>Trocar</button>
        </div>
      )}
    </div>
  );
}

/** Nome de origem a partir do nome da pasta: minúsculas, números e hífen. */
export function nomeDeOrigem(texto: string) {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
}
