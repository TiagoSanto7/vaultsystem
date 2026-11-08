import { useMemo } from "react";
import { Sistema } from "../api";
import { Carregando, Falha, Vazio } from "../componentes";
import { useDados } from "../dados";
import { curto, plural } from "../formato";
import { Icone } from "../icones";

// Aba Arquivos (DV-601): fontes, imagens e PDF dos vaults de Referência, que não
// viram nota. Saem do repositório da origem no commit processado; a mesma lista
// vai para a API (/v1/sistemas/{tag}/arquivos) e para o MCP (list_files, get_file).

interface Arquivo { origem: string; caminho: string; tipo: string; tamanho: number; commit: string }
interface Lista { arquivos: Arquivo[]; limite: number; limite_pacote: number; extensoes: string[] }

export function tamanho(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

const pastaDe = (c: string) => (c.includes("/") ? c.slice(0, c.lastIndexOf("/")) : "");

export default function Arquivos({ s }: { s: Sistema }) {
  const { dados, erro, recarregar } = useDados<Lista>(`/sistemas/${s.tag}/arquivos`);
  const pastas = useMemo(() => {
    const m = new Map<string, Arquivo[]>();
    for (const a of dados?.arquivos ?? []) {
      const p = (a.origem === "principal" ? "" : `${a.origem}:`) + pastaDe(a.caminho);
      m.set(p, [...(m.get(p) ?? []), a]);
    }
    return [...m.entries()];
  }, [dados]);

  if (erro) return <Falha erro={erro} tentar={recarregar} />;
  if (!dados) return <Carregando />;
  const base = `/v1/painel/sistemas/${s.tag}`;
  const total = dados.arquivos.reduce((t, a) => t + a.tamanho, 0);

  if (!dados.arquivos.length) {
    return (
      <section className="panel">
        <Vazio titulo="Nenhum arquivo para baixar">
          Fontes, imagens e PDF ({dados.extensoes.join(", ")}, até {tamanho(dados.limite)}) de uma pasta classificada como
          Referência aparecem aqui. Se estão numa pasta em "ignorar", mude a classificação na aba Fontes e peça um pull.
        </Vazio>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-head" style={{ flexWrap: "wrap" }}>
        <div>
          <h2>Arquivos para baixar</h2>
          <small>
            {plural(dados.arquivos.length, "arquivo", "arquivos")} · {tamanho(total)} · do repositório, no commit processado.
            Pelo MCP: <span className="mono">list_files</span> e <span className="mono">get_file</span> (link de 15 minutos para o agente baixar com curl).
          </small>
        </div>
        {total <= dados.limite_pacote && (
          <a className="btn primary" href={`${base}/arquivos.zip`} download>
            <Icone nome="download" />Baixar tudo (.zip)
          </a>
        )}
      </div>
      {pastas.map(([pasta, lista]) => (
        <div key={pasta} className="table-wrap" style={{ margin: "0 16px 16px" }}>
          <table>
            <thead>
              <tr>
                <th className="mono">{pasta || "/"}</th>
                <th>Tipo</th>
                <th>Tamanho</th>
                <th>Commit</th>
                <th style={{ textAlign: "right" }}>
                  {!pasta.includes(":") && lista.length > 1 && (
                    <a className="textbtn" href={`${base}/arquivos.zip?pasta=${encodeURIComponent(pasta)}`} download>Baixar pasta</a>
                  )}
                </th>
              </tr>
            </thead>
            <tbody>
              {lista.map((a) => (
                <tr key={`${a.origem}:${a.caminho}`}>
                  <td className="mono" style={{ fontSize: 12 }}>{a.caminho.slice(a.caminho.lastIndexOf("/") + 1)}</td>
                  <td>{a.tipo}</td>
                  <td>{tamanho(a.tamanho)}</td>
                  <td className="mono">{curto(a.commit)}</td>
                  <td style={{ textAlign: "right" }}>
                    <a className="textbtn" href={`${base}/arquivos/baixar?${new URLSearchParams({ origem: a.origem, caminho: a.caminho })}`} download
                       aria-label={`Baixar ${a.caminho}`}>
                      <Icone nome="download" />Baixar
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
