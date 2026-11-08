import { createServer } from "vite";
import { fileURLToPath } from "node:url";

const stamp = "2026-11-07T15:00:00Z";
const revision = { hash: null, data: null, url: null };
const demo = [
  { tag: "portal-demo", notas: 18, perfil: "codigo" },
  { tag: "design-system", notas: 7, perfil: "documentos" },
  { tag: "template-docker", notas: 0, perfil: "referencia" },
].map(({ tag, notas, perfil }) => ({
  tag, removido_em: null, selo: { estado: "em_dia", texto: "Em dia" },
  sinais: {
    notas, em_dia: { estado: "em_dia", commits_atras: 0 },
    fila: { itens: 0, parados: 0 }, verificacao: { total: 0, por_tipo: {} },
    ignorados: { total: 0, motivos: [] },
  },
  origens: [{
    nome: "principal", repo: `git@vault.example:${tag}.git`, ramo: "main", url: null,
    leituras: [{ perfil, incluir: [], excluir: [] }], situacao: "em_dia",
    classificacao: null, removida_em: null, commits_atras: 0,
    acesso: { ok: true, em: stamp, erro: null }, commit_processado: revision, commit_pendente: revision,
  }],
  ultima_rodada: null, lote_atual: null, pull_pendente: null,
  cadastro: { por: "demo", em: stamp }, ultimo_pull: null,
}));

const logo = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="18" cy="20" r="14" fill="none" stroke="#6ba5ff"/><path d="M11 8l7 12-7 12m7-12 17-7m-17 7 17 7" stroke="#0758ed" fill="none"/><g fill="#0758ed"><circle cx="11" cy="8" r="2.4"/><circle cx="11" cy="32" r="2.4"/><circle cx="35" cy="13" r="2.4"/><circle cx="35" cy="27" r="2.4"/><circle cx="18" cy="20" r="4"/></g></svg>';

const server = await createServer({
  root: fileURLToPath(new URL(".", import.meta.url)),
  configFile: false,
  plugins: [
    (await import("@vitejs/plugin-react")).default(),
    {
      name: "vault-system-local-preview",
      enforce: "pre",
      transformIndexHtml(html) {
        return html.replaceAll("PetroVault", "Vault System").replace("/simbolo.png", "/simbolo.svg");
      },
      transform(source, id) {
        const filename = id.replaceAll("\\", "/").split("?")[0];
        if (filename.endsWith("/src/estilo.css")) {
          return source.replaceAll("#007800", "#0758ed").replaceAll("#7ed087", "#82baff")
            .replaceAll("#e8f3ea", "#eaf2ff").replaceAll("#2f4434", "#223b63");
        }
        if (filename.endsWith("/src/Layout.tsx") || filename.endsWith("/src/telas/Inicio.tsx")) {
          return source.replaceAll("PetroVault", "Vault System").replaceAll("Petrovina", "Workspace demo")
            .replaceAll("Conhecimento corporativo", "Dados de demonstração")
            .replaceAll("Conhecimento com origem", "Conhecimento distribuído")
            .replaceAll("/simbolo.png", "/simbolo.svg").replaceAll("Repositórios GitHub", "Repositórios Git");
        }
      },
      configureServer(vite) {
        vite.middlewares.use((req, res, next) => {
          const path = new URL(req.url, "http://localhost").pathname;
          if (path === "/simbolo.svg") {
            res.setHeader("Content-Type", "image/svg+xml");
            return res.end(logo);
          }
          if (!path.startsWith("/v1/")) return next();
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          const send = (body, status = 200) => {
            res.statusCode = status;
            res.end(JSON.stringify(body));
          };
          if (req.method !== "GET") return send({ detail: "Prévia local em modo leitura." }, 405);
          const route = path.replace(/^\/v1\/painel/, "");
          if (route === "/eu") return send({
            login: "demo", nome: "Tiago", papel: "administrador", ambiente: "Prévia local",
            url_publica: "http://127.0.0.1:5173", apresentacao_vista_em: stamp,
          });
          if (route === "/sistemas") return send({
            sistemas: demo, por_estado: { em_dia: demo.length }, proxima_rodada: null, rodada_em_curso: null,
          });
          const template = {
            id: "docker:python", tipo: "docker", nome: "python", vault: "template-docker",
            descricao: "Exemplo de stack Python com Docker Compose", arquivos: 2, commit: "demo",
          };
          if (route === "/cli") return send({ templates: [template] });
          if (route === "/cli/templates/docker/python") return send({ ...template, files: [
            { path: "Dockerfile", size: 128 }, { path: "docker-compose.yml", size: 245 },
          ] });
          if (route === "/github/repos") return send({ repos: [], atualizado_em: null, erro: null, pedido_em: null });
          const vault = demo.find(item => route === `/sistemas/${item.tag}`);
          if (vault) return send(vault);
          return send({ detail: "Esta seção depende da API do hub e não está disponível na prévia." }, 503);
        });
      },
    },
  ],
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
});
await server.listen();
server.printUrls();
