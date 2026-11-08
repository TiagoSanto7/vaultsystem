import { useEffect, useState } from "react";
import { api } from "./api";
import { useDados } from "./dados";
import { relativo } from "./formato";
import { Icone } from "./icones";

// Uma origem do cadastro (DV-292): repositório, ramo e as leituras (perfil,
// incluir, excluir). Usado em Novo vault e em Fontes > Adicionar repositório.
// DV-573: o repositório vem da lista do GitHub App (https://github.com/...);
// o endereço SSH com chave de deploy continua para as origens antigas.

export interface LeituraForm { perfil: string; incluir: string; excluir: string }
export type Acesso = "app" | "chave";
export interface OrigemForm { nome: string; acesso: Acesso; repo: string; ramo: string; leituras: LeituraForm[] }

interface RepoApp { nome: string; repo: string; ramo_padrao: string; privado: boolean; ramos: string[] }
interface ListaApp { repos: RepoApp[]; atualizado_em: string | null; erro: string | null; pedido_em: string | null }

export const origemVazia = (nome = "principal"): OrigemForm => ({
  nome, acesso: "app", repo: "", ramo: "main", leituras: [{ perfil: "documentos", incluir: "", excluir: "" }],
});

const doApp = (repo: string) => repo.startsWith("https://github.com/");

const linhas = (t: string) => t.split("\n").map((l) => l.trim()).filter(Boolean);

export const origemDaApi = (o: { nome: string; repo: string; ramo: string; leituras: { perfil: string; incluir: string[]; excluir: string[] }[] }): OrigemForm => ({
  nome: o.nome, acesso: doApp(o.repo) ? "app" : "chave", repo: o.repo, ramo: o.ramo,
  leituras: o.leituras.map((l) => ({ perfil: l.perfil, incluir: l.incluir.join("\n"), excluir: l.excluir.join("\n") })),
});

export function origemParaApi(o: OrigemForm) {
  return {
    nome: o.nome.trim(),
    repo: o.repo.trim(),
    ramo: o.ramo.trim() || "main",
    leituras: o.leituras.map((l) => ({ perfil: l.perfil, incluir: linhas(l.incluir), excluir: linhas(l.excluir) })),
  };
}

// semLeituras (Novo vault, DV-589): as leituras de uma origem do App saem da árvore, na etapa seguinte.
export function CamposOrigem({ id, valor, mudar, nomeFixo, repoFixo, semLeituras }: { id: string; valor: OrigemForm; mudar: (o: OrigemForm) => void; nomeFixo?: boolean; repoFixo?: boolean; semLeituras?: boolean }) {
  const leitura = (i: number, l: Partial<LeituraForm>) =>
    mudar({ ...valor, leituras: valor.leituras.map((x, n) => (n === i ? { ...x, ...l } : x)) });
  return (
    <>
      {!repoFixo && <TipoFonte id={id} />}
      <div className="form-grid">
        <div>
          <label htmlFor={`${id}-nome`}>Nome da origem <small className="muted">(minúsculas e hífen)</small></label>
          <input id={`${id}-nome`} value={valor.nome} disabled={nomeFixo} onChange={(e) => mudar({ ...valor, nome: e.target.value })} required />
        </div>
        {valor.acesso === "chave" && (
          <div>
            <label htmlFor={`${id}-ramo`}>Ramo</label>
            <input id={`${id}-ramo`} value={valor.ramo} onChange={(e) => mudar({ ...valor, ramo: e.target.value })} />
          </div>
        )}
      </div>
      {valor.acesso === "app" ? (
        <RepoDoApp id={id} valor={valor} mudar={mudar} repoFixo={repoFixo} />
      ) : (
        <>
          <label htmlFor={`${id}-repo`}>Repositório GitHub <small className="muted">(endereço SSH, com chave de deploy)</small></label>
          <input id={`${id}-repo`} className="mono" placeholder="git@github.com:minha-org/meu-repo.git" value={valor.repo}
            disabled={repoFixo} onChange={(e) => mudar({ ...valor, repo: e.target.value })} required />
        </>
      )}
      {!repoFixo && (
        <button type="button" className="textbtn" style={{ marginTop: 8 }}
          onClick={() => mudar({ ...valor, acesso: valor.acesso === "app" ? "chave" : "app", repo: "", ramo: "main" })}>
          {valor.acesso === "app" ? "Usar endereço SSH com chave de deploy (origens antigas)" : "Escolher da lista do GitHub App"}
        </button>
      )}

      {!semLeituras && valor.leituras.map((l, i) => (
        <fieldset key={i} className="panel" style={{ padding: "4px 16px 16px", marginTop: 16 }}>
          <legend className="visually-hidden">Leitura {i + 1}</legend>
          <div className="form-grid">
            <div>
              <label htmlFor={`${id}-perfil-${i}`}>{valor.leituras.length > 1 ? `Leitura ${i + 1}: perfil` : "Perfil da leitura"}</label>
              <select id={`${id}-perfil-${i}`} value={l.perfil} onChange={(e) => leitura(i, { perfil: e.target.value })} style={{ width: "100%" }}>
                <option value="documentos">documentos (documentos e assuntos)</option>
                <option value="codigo-literal">código + cópia literal (módulos, regras, ... e o código-fonte como está)</option>
                <option value="codigo">código, sem cópia (módulos, regras, integrações, APIs, dados)</option>
                <option value="referencia-explicada">referência + explicação (arquivos como estão e guias do curador)</option>
                <option value="referencia">referência, só literal (arquivos como estão, sem guias)</option>
              </select>
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "flex-end" }}>
              {valor.leituras.length > 1 && (
                <button type="button" className="btn danger" onClick={() => mudar({ ...valor, leituras: valor.leituras.filter((_, n) => n !== i) })}>
                  Tirar leitura
                </button>
              )}
            </div>
          </div>
          <div className="form-grid">
            <div>
              <label htmlFor={`${id}-incluir-${i}`}>Incluir <small className="muted">(um padrão por linha; vazio = tudo)</small></label>
              <textarea id={`${id}-incluir-${i}`} rows={3} className="mono" placeholder="docs/**" value={l.incluir} onChange={(e) => leitura(i, { incluir: e.target.value })} />
            </div>
            <div>
              <label htmlFor={`${id}-excluir-${i}`}>Excluir <small className="muted">(um padrão por linha)</small></label>
              <textarea id={`${id}-excluir-${i}`} rows={3} className="mono" placeholder="**/teste/**" value={l.excluir} onChange={(e) => leitura(i, { excluir: e.target.value })} />
            </div>
          </div>
        </fieldset>
      ))}
      {!semLeituras && valor.leituras.length < 10 && (
        <button type="button" className="textbtn" style={{ marginTop: 12 }}
          onClick={() => mudar({ ...valor, leituras: [...valor.leituras, { perfil: "codigo", incluir: "", excluir: "" }] })}>
          <Icone nome="plus" />Outra leitura no mesmo repositório
        </button>
      )}
    </>
  );
}

// Tipo da fonte (DV-591): só GitHub por enquanto; PDF e .md entram depois
// sem mudar o formulário.
function TipoFonte({ id }: { id: string }) {
  const tipos = [
    { valor: "github", texto: "Repositório GitHub", ativo: true },
    { valor: "pdf", texto: "Documento PDF", ativo: false },
    { valor: "md", texto: "Arquivo .md", ativo: false },
  ];
  return (
    <fieldset className="tipo-fonte">
      <legend>Tipo de fonte</legend>
      <div>
        {tipos.map((t) => (
          <label key={t.valor} className={t.ativo ? "" : "muted"}>
            <input type="radio" name={`${id}-tipo`} value={t.valor} defaultChecked={t.ativo} disabled={!t.ativo} />
            {t.texto}{!t.ativo && <small> (em breve)</small>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function RepoDoApp({ id, valor, mudar, repoFixo }: { id: string; valor: OrigemForm; mudar: (o: OrigemForm) => void; repoFixo?: boolean }) {
  const [pedido, setPedido] = useState(false);
  // Enquanto o curador não atende o pedido de atualização, a lista é lida a cada 5 s.
  const lista = useDados<ListaApp>("/github/repos", pedido ? 5000 : undefined, true);
  const l = lista.dados;
  useEffect(() => {
    if (pedido && l && !l.pedido_em) setPedido(false);
  }, [pedido, l]);
  const escolhido = l?.repos.find((r) => r.repo === valor.repo);
  // O ramo da origem aparece mesmo que a lista do App não o traga (ex.: ramo apagado no GitHub).
  const ramos = [...new Set([...(valor.ramo ? [valor.ramo] : []), ...(escolhido?.ramos ?? [])])];

  async function atualizar() {
    await api("/github/atualizar", { metodo: "POST" });
    setPedido(true);
    lista.recarregar();
  }

  return (
    <>
      <div className="form-grid">
        <div>
          <label htmlFor={`${id}-repo`}>Repositório <small className="muted">(onde o GitHub App está instalado)</small></label>
          {repoFixo ? (
            <input id={`${id}-repo`} className="mono" value={valor.repo.replace("https://github.com/", "")} disabled />
          ) : (
            <select id={`${id}-repo`} value={valor.repo} style={{ width: "100%" }} required
              onChange={(e) => {
                const r = l?.repos.find((x) => x.repo === e.target.value);
                mudar({ ...valor, repo: e.target.value, ramo: r?.ramo_padrao ?? "main" });
              }}>
              <option value="">{lista.carregando && !l ? "Carregando…" : "Escolha o repositório"}</option>
              {l?.repos.map((r) => <option key={r.nome} value={r.repo}>{r.nome}{r.privado ? "" : " (público)"}</option>)}
            </select>
          )}
        </div>
        <div>
          <label htmlFor={`${id}-ramo`}>Ramo</label>
          <select id={`${id}-ramo`} value={valor.ramo} style={{ width: "100%" }} disabled={!valor.repo}
            onChange={(e) => mudar({ ...valor, ramo: e.target.value })}>
            {ramos.map((r) => <option key={r} value={r}>{r}{r === escolhido?.ramo_padrao ? " (padrão)" : ""}</option>)}
          </select>
        </div>
      </div>
      {!repoFixo && (
        <small className="muted" style={{ display: "block", marginTop: 6 }}>
          {l?.erro ? <span className="red">Lista não atualizada: {l.erro}. </span> : null}
          {l?.atualizado_em ? `Lista de ${relativo(l.atualizado_em)}. ` : l ? "A lista ainda não foi montada pelo curador. " : ""}
          {pedido ? "Atualizando (até 30 s)…" : <button type="button" className="textbtn" onClick={atualizar}>Atualizar lista</button>}
        </small>
      )}
      {!repoFixo && l && l.repos.length === 0 && !pedido && (
        <details className="ajuda" open>
          <summary>O repositório não aparece?</summary>
          <p>
            A lista mostra só os repositórios onde o <b>GitHub App petro-vault</b> está instalado. Um admin da organização
            inclui o repositório em GitHub → sua organização → Settings → GitHub Apps → o app do Vault System → <b>Configure</b> →
            Repository access. Depois, clique em <b>Atualizar lista</b>.
          </p>
        </details>
      )}
    </>
  );
}

export function ExplicacaoChave({ tag, origem }: { tag: string; origem: string }) {
  const nome = origem === "principal" ? tag : `${tag}--${origem}`;
  return (
    <details className="ajuda" open>
      <summary>Endereço SSH: precisa da chave de deploy no servidor</summary>
      <p>
        Pelo endereço SSH, o repositório usa uma <b>chave de deploy só leitura</b>, colocada no servidor pelo administrador com o nome{" "}
        <code>{nome}</code>. Sem ela, o pull registra “sem acesso” e nada é lido. Pela lista do GitHub App, nada disso é preciso.
      </p>
    </details>
  );
}

// Editar origem (DV-573): uma origem antiga, por SSH com chave de deploy, passa a
// ser lida pelo GitHub App. Só o endereço muda: o clone é o mesmo e o próximo pull
// não lê nada de novo se o commit não mudou.
const SSH_GITHUB = /^(?:git@github\.com:|ssh:\/\/git@github\.com(?::\d+)?\/)([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?)(?:\.git)?$/;

export function TrocarAcesso({ original, valor, mudar }: { original: string; valor: OrigemForm; mudar: (o: OrigemForm) => void }) {
  const [pedido, setPedido] = useState(false);
  const lista = useDados<ListaApp>("/github/repos", pedido ? 5000 : undefined, true);
  useEffect(() => {
    if (pedido && lista.dados && !lista.dados.pedido_em) setPedido(false);
  }, [pedido, lista.dados]);
  const donoRepo = SSH_GITHUB.exec(original)?.[1];
  if (!donoRepo) return null;
  const noApp = lista.dados?.repos.find((r) => r.nome.toLowerCase() === donoRepo.toLowerCase());
  if (valor.acesso === "app") {
    return (
      <div className="banner section-gap" role="status">
        <Icone nome="check" />
        <div>
          Ao salvar, {donoRepo} passa a ser lido pelo GitHub App, sem a chave de deploy. O clone é o mesmo: se o commit não
          mudou, o pull não lê nada de novo.{" "}
          <button type="button" className="textbtn" onClick={() => mudar({ ...valor, acesso: "chave", repo: original })}>Continuar com a chave de deploy</button>
        </div>
      </div>
    );
  }
  return (
    <div className="banner section-gap" role="status">
      <Icone nome="alert" />
      <div>
        {noApp ? (
          <>
            {donoRepo} está na instalação do GitHub App: a origem pode deixar a chave de deploy.{" "}
            <button type="button" className="textbtn" onClick={() => mudar({ ...valor, acesso: "app", repo: noApp.repo })}>Passar a ler pelo GitHub App</button>
          </>
        ) : (
          <>
            Esta origem é lida pela chave de deploy. Para ler pelo GitHub App, o admin da organização inclui {donoRepo} na
            instalação do App (GitHub → Settings → GitHub Apps → petro-vault → Configure) e a lista do App é atualizada.{" "}
            <button type="button" className="textbtn" disabled={pedido}
              onClick={async () => { await api("/github/atualizar", { metodo: "POST" }); setPedido(true); lista.recarregar(); }}>
              {pedido ? "Atualizando a lista…" : "Atualizar a lista do App"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
