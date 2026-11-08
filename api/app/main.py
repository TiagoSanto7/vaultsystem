"""API do vault-system.

Toda rota com tag passa por `exigir_tag`: a credencial precisa ter a tag no
modo pedido, senão 403, antes de qualquer conteúdo ser lido. A checagem vem
antes de qualquer consulta ao banco: quem não tem a tag recebe 403 mesmo para
um sistema que não existe.

- rota de teste de acesso.
- cadastro de sistema e pull manual (tag na escrita); consulta do
  sistema, da fila e dos pulls (tag na leitura).
- consulta ao conhecimento (busca por texto completo e leitura de
  nota) por HTTP e por MCP em /mcp (conhecimento.py), com a mesma checagem.
  A escrita de achados vem numa segunda etapa.
- rotas da tela em /v1/painel (painel.py), para pessoas logadas pelo
  AD (sessao.py); a API dos agentes continua com a credencial `vs_`.
- a própria tela (React, compilada em web/dist), servida no fim deste
  arquivo, na mesma origem da API.
- templates para baixar (`/v1/templates`) e a CLI `vs` (`/v1/cli/vs`).
"""
import os
import re
from typing import Literal

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.sessions import SessionMiddleware

from vault_system import arquivos, arvore, busca, estado, templates

from . import baixar, conhecimento, credenciais, envio, painel, sessao, sistemas

app = FastAPI(title="vault-system", docs_url=None, redoc_url=None, openapi_url=None)
# Tela: pessoas entram pelo AD, com sessão em cookie assinado. Sem
# VAULT_SESSAO_SEGREDO a tela fica desligada (503) e a API dos agentes segue.
if sessao.segredo_da_sessao():
    app.add_middleware(SessionMiddleware, secret_key=sessao.segredo_da_sessao(), session_cookie="vault_system",
                       max_age=12 * 3600, same_site="lax",
                       https_only=os.environ.get("VAULT_COOKIE_SEGURO", "0") == "1")
app.state.ldap = sessao.ldap_do_ambiente()
try:
    sessao.garantir_admin_do_ambiente()  # VAULT_ADMIN_LOGIN e VAULT_ADMIN_SENHA na primeira subida
except Exception as e:  # noqa: BLE001 - a API sobe mesmo sem o estado gravável (testes, leitura)
    print(f"[api] conta inicial não criada: {e}")
app.include_router(painel.router)


def credencial(authorization: str = Header(default="")):
    chave = authorization.removeprefix("Bearer ").strip()
    cred = credenciais.buscar(chave)
    if not cred:
        raise HTTPException(401, "credencial ausente ou inválida")
    return cred


def exigir_tag(cred, tag, modo):
    if not credenciais.TAG.match(tag):
        raise HTTPException(400, "tag inválida")
    if tag not in cred[modo]:
        raise HTTPException(403, f"a credencial não pode {modo} a tag {tag}")


@app.put("/v1/sistemas/{tag}/envio")
async def sincronizar_envio(tag: str, request: Request, modo: str | None = None, curar: bool = False,
                            cred=Depends(credencial)):
    exigir_tag(cred, tag, "escrever")
    # Token de conexão: quem envia é o dono do workspace (vs sync); outro token, pelo nome dele.
    por = cred["dono"] if cred.get("workspace") and cred.get("dono") else cred["nome"]
    r = await envio.receber(request, tag, por, modo)
    if curar:  # vs sync --curate: pede a curadoria do Vault-I (nunca automática)
        from vault_system import vault_i
        with credenciais.conectar() as db:
            try:
                pid, _ = vault_i.pedir(db, tag, por, "cli")
                r["curadoria"] = {"estado": "pedida", "pedido": pid}
            except vault_i.SemConfiguracao as e:
                r["curadoria"] = {"estado": "indisponivel", "motivo": str(e)}
    return r


@app.get("/v1/eu")
def quem_sou(cred=Depends(credencial)):
    """A conexão da CLI (`vs login`, `vs init`): o token, o dono do workspace e o hub."""
    return {"credencial": cred["nome"], "workspace": cred.get("workspace", False), "dono": cred.get("dono"),
            "hub": baixar.url_publica(), "vaults": sorted(cred["escrever"] if cred.get("workspace") else cred["ler"] | cred["escrever"])}


@app.get("/saude")
def saude():
    credenciais.conectar().close()
    return {"ok": True}


@app.get("/v1/sistemas/{tag}/acesso")
def acesso(tag: str, modo: Literal["ler", "escrever"] = "ler", cred=Depends(credencial)):
    """Teste de acesso por tag: 200 se a credencial pode, 403 se não."""
    exigir_tag(cred, tag, modo)
    return {"tag": tag, "modo": modo, "credencial": cred["nome"]}


class Leitura(BaseModel):
    perfil: str
    incluir: list[str] = Field(default_factory=list, max_length=100)
    excluir: list[str] = Field(default_factory=list, max_length=100)


# Destinos da árvore: a mesma lista no cadastro e na edição de origem.
ClasseArvore = Literal[arvore.CLASSES]


class Origem(BaseModel):
    nome: str = "principal"
    repo: str
    ramo: str = "main"
    leituras: list[Leitura] = Field(min_length=1, max_length=10)
    # a classificação por pasta da árvore, de onde vieram as leituras.
    classificacao: dict[str, ClasseArvore] | None = Field(default=None, max_length=2000)


class Cadastro(BaseModel):
    """Formato com `origens` ou o antigo, com uma origem no topo."""
    tag: str
    origens: list[Origem] | None = Field(default=None, min_length=1, max_length=10)
    perfil: str | None = None
    repo: str | None = None
    ramo: str = "main"
    incluir: list[str] = Field(default_factory=list, max_length=100)
    excluir: list[str] = Field(default_factory=list, max_length=100)


@app.post("/v1/sistemas", status_code=201)
def cadastrar(dados: Cadastro, cred=Depends(credencial)):
    """Cadastro de sistema. A chave de deploy só leitura de cada origem é
    colocada à mão no servidor (ver README); sem ela, o pull registra o erro."""
    exigir_tag(cred, dados.tag, "escrever")
    d = sistemas.normalizar(dados.model_dump())
    erros = sistemas.validar(d)
    if erros:
        raise HTTPException(400, erros)
    if not sistemas.criar(d, cred["nome"]):
        raise HTTPException(409, f"a tag {dados.tag} já está cadastrada")
    return sistemas.ler(dados.tag)


@app.post("/v1/sistemas/{tag}/origens", status_code=201)
def nova_origem(tag: str, origem: Origem, cred=Depends(credencial)):
    """Mais uma origem num sistema que já existe (ex.: o repositório de
    documentação de um sistema cujo código já está cadastrado)."""
    exigir_tag(cred, tag, "escrever")
    s = sistemas.ler(tag)
    if not s or s["removido_em"]:
        raise HTTPException(404, "sistema não cadastrado")
    o = origem.model_dump()
    erros = sistemas.validar_origem(o)
    if erros:
        raise HTTPException(400, erros)
    if not sistemas.acrescentar_origem(tag, o):
        raise HTTPException(409, f"a origem {o['nome']} já existe em {tag}")
    return sistemas.ler(tag)


class EdicaoOrigem(BaseModel):
    repo: str | None = None  # só o mesmo repositório em outro endereço
    ramo: str = "main"
    leituras: list[Leitura] = Field(min_length=1, max_length=10)
    classificacao: dict[str, ClasseArvore] | None = Field(default=None, max_length=2000)


def _origem_ativa(tag, nome):
    s = sistemas.ler(tag)
    if not s or s["removido_em"]:
        raise HTTPException(404, "sistema não cadastrado")
    o = next((o for o in s["origens"] if o["nome"] == nome and not o["removida_em"]), None)
    if not o:
        raise HTTPException(404, f"a origem {nome} não existe em {tag}")
    return o


def editar_origem(tag, nome, dados, por):
    """Valida, grava e pede um pull: a reconciliação roda na ingestão."""
    o = _origem_ativa(tag, nome)
    repo = (dados.get("repo") or o["repo"]).strip()
    if repo != o["repo"] and not sistemas.mesmo_repo(repo, o["repo"]):
        # Outro repositório é outra origem: o vault reflete o que veio deste.
        raise HTTPException(400, [f"origem {nome}: só dá para trocar o endereço do mesmo repositório "
                                  "(SSH ↔ GitHub App); outro repositório é outra origem"])
    nova = {**o, "repo": repo, "ramo": dados["ramo"], "leituras": dados["leituras"]}
    erros = sistemas.validar_origem(nova)
    if erros:
        raise HTTPException(400, erros)
    sistemas.editar_origem(tag, nome, nova["ramo"], nova["leituras"], nova["repo"], dados.get("classificacao"))
    sistemas.pedir_pull(tag, por)


def remover_origem(tag, nome, por):
    _origem_ativa(tag, nome)
    if sistemas.remover_origem(tag, nome) == "ultima":
        raise HTTPException(409, "é a única origem do sistema: remova o sistema")
    sistemas.pedir_pull(tag, por)


@app.put("/v1/sistemas/{tag}/origens/{nome}")
def editar(tag: str, nome: str, dados: EdicaoOrigem, cred=Depends(credencial)):
    """Muda o ramo e as leituras de uma origem e, do mesmo
    repositório, o endereço: SSH ↔ GitHub App. No pull que já fica
    pedido, o que saiu das leituras sai do vault e o que entrou é lido."""
    exigir_tag(cred, tag, "escrever")
    editar_origem(tag, nome, dados.model_dump(), cred["nome"])
    return sistemas.ler(tag)


@app.delete("/v1/sistemas/{tag}/origens/{nome}", status_code=202)
def remover_uma_origem(tag: str, nome: str, cred=Depends(credencial)):
    """Tira uma origem (não a única): o que veio dela sai do vault no pull que
    já fica pedido, e o cadastro dela sai quando a fila dela esvazia."""
    exigir_tag(cred, tag, "escrever")
    remover_origem(tag, nome, cred["nome"])
    return sistemas.ler(tag)


@app.get("/v1/sistemas/{tag}")
def ver_sistema(tag: str, cred=Depends(credencial)):
    exigir_tag(cred, tag, "ler")
    s = sistemas.ler(tag)
    if not s:
        raise HTTPException(404, "sistema não cadastrado")
    return s


@app.delete("/v1/sistemas/{tag}", status_code=202)
def remover(tag: str, cred=Depends(credencial)):
    """Tira o sistema do serviço: o curador apaga a pasta da tag no vault (com
    commit), o clone, os lotes e o cadastro em até 30 s. A origem não é tocada."""
    exigir_tag(cred, tag, "escrever")
    s = sistemas.ler(tag)
    if not s:
        raise HTTPException(404, "sistema não cadastrado")
    if s["removido_em"]:
        return {"tag": tag, "estado": "remocao_pedida", "pedido_em": s["removido_em"]}
    sistemas.marcar_remocao(tag, cred["nome"])
    return {"tag": tag, "estado": "remocao_pedida"}


@app.get("/v1/sistemas/{tag}/fila")
def ver_fila(tag: str, cred=Depends(credencial)):
    exigir_tag(cred, tag, "ler")
    if not sistemas.ler(tag):
        raise HTTPException(404, "sistema não cadastrado")
    return sistemas.fila(tag)


@app.post("/v1/sistemas/{tag}/pull", status_code=202)
def pull(tag: str, cred=Depends(credencial)):
    """Pede uma ingestão; o curador atende em até 30 s. Acompanhe pelo id."""
    exigir_tag(cred, tag, "escrever")
    s = sistemas.ler(tag)
    if not s:
        raise HTTPException(404, "sistema não cadastrado")
    if s["removido_em"]:
        raise HTTPException(409, "remoção do sistema já pedida")
    return {"pedido": sistemas.pedir_pull(tag, cred["nome"]), "estado": "pedido"}


@app.get("/v1/sistemas/{tag}/pulls/{pid}")
def ver_pull(tag: str, pid: int, cred=Depends(credencial)):
    exigir_tag(cred, tag, "ler")
    p = sistemas.ler_pull(tag, pid)
    if not p:
        raise HTTPException(404, "pedido não encontrado")
    return p


# --- conhecimento -----------------------------------------------------------
# Só leitura. O contrato é o das seções 9 e 10 do documento de execução.

@app.post("/v1/knowledge/search")
def buscar_conhecimento(corpo: dict = Body(...), cred=Depends(credencial)):
    try:
        c = conhecimento.Consulta(**corpo)
    except ValidationError as e:
        raise HTTPException(400, [{"campo": ".".join(map(str, x["loc"])), "erro": x["msg"]} for x in e.errors()])
    exigir_tag(cred, c.system_id, "ler")
    return busca.buscar(c.system_id, c.query, c.limit, c.verification)


@app.get("/v1/notas/{note_id:path}")
def ler_nota(note_id: str, cred=Depends(credencial)):
    note_id = note_id.removesuffix(".md")
    tag = conhecimento.tag_da_nota(note_id)
    if not tag:
        raise HTTPException(400, "note_id inválido: use sistemas/<tag>/<pasta>/<nome>")
    exigir_tag(cred, tag, "ler")
    nota = busca.ler(tag, note_id)
    if not nota:
        raise HTTPException(404, "nota não encontrada")
    return nota


# --- arquivos para baixar ---------------------------------------------------
# Fontes, imagens e PDF dos vaults de Referência. Com a credencial `vs_` (tag em `ler`)
# ou com o link assinado que o MCP entrega (get_file), que vale 15 minutos.

@app.get("/v1/sistemas/{tag}/arquivos")
def listar_arquivos(tag: str, pasta: str | None = None, cred=Depends(credencial)):
    exigir_tag(cred, tag, "ler")
    with estado.conectar() as db:
        return {"system_id": tag, "files": [baixar.publico(tag, a) for a in arquivos.listar(db, tag, pasta)]}


@app.get("/v1/sistemas/{tag}/arquivos.zip")
def baixar_pacote(tag: str, pasta: str | None = None, cred=Depends(credencial)):
    exigir_tag(cred, tag, "ler")
    with estado.conectar() as db:
        return baixar.pacote(db, tag, pasta)


@app.get("/v1/arquivos/{tag}/{caminho:path}")
def baixar_arquivo(tag: str, caminho: str, origem: str = "principal", exp: str | None = None,
                   sig: str | None = None, authorization: str = Header(default="")):
    if sig is not None:  # link assinado do MCP: sem credencial
        if not credenciais.TAG.match(tag):
            raise HTTPException(400, "tag inválida")
        motivo = arquivos.conferir(tag, origem, caminho, exp, sig)
        if motivo:
            raise HTTPException(403, motivo)
    else:
        exigir_tag(credencial(authorization), tag, "ler")
    with estado.conectar() as db:
        return baixar.arquivo(db, tag, origem, caminho)


# --- templates e CLI --------------------------------------------------------
# `vs add template docker:python`: a pasta python/ do vault template-docker
# (vault_system/templates.py). Qualquer credencial `vs_` válida lê qualquer template:
# template é para todos e não carrega segredo (o pacote com segredo é bloqueado).

def _template(tipo, nome):
    try:
        return templates.separar(f"{tipo}:{nome}")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/v1/templates")
def listar_templates(tipo: str | None = None, cred=Depends(credencial)):
    if tipo is not None and not templates.TIPO.match(tipo):
        raise HTTPException(400, "tipo inválido")
    with estado.conectar() as db:
        return {"templates": templates.listar(db, tipo)}


@app.get("/v1/templates/{tipo}/{nome}.zip")
def baixar_template(tipo: str, nome: str, cred=Depends(credencial)):
    tipo, nome = _template(tipo, nome)
    with estado.conectar() as db:
        try:
            r, dados = templates.pacote(db, tipo, nome)
        except templates.NaoEncontrado as e:
            raise HTTPException(404, str(e)) from None
        except templates.Bloqueado as e:
            raise HTTPException(409, str(e)) from None
    return Response(dados, media_type="application/zip", headers={
        **baixar.CABECALHOS, "Content-Disposition": f'attachment; filename="{tipo}-{nome}.zip"',
        "X-Commit": r["commit"], "X-Template": r["id"]})


@app.get("/v1/templates/{tipo}/{nome}")
def ver_template(tipo: str, nome: str, cred=Depends(credencial)):
    tipo, nome = _template(tipo, nome)
    with estado.conectar() as db:
        try:
            return templates.detalhes(db, tipo, nome)
        except templates.NaoEncontrado as e:
            raise HTTPException(404, str(e)) from None


def _cli_vs():
    """O arquivo da CLI: na imagem fica em /opt/api/cli; no repositório, na raiz."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    for c in (os.environ.get("VAULT_CLI"), os.path.join(aqui, "..", "cli", "vs.py"),
              os.path.join(aqui, "..", "..", "cli", "vs.py")):
        if c and os.path.isfile(c):
            return c
    raise HTTPException(404, "CLI não instalada nesta imagem")


@app.get("/v1/cli")
def versao_cli():
    with open(_cli_vs(), encoding="utf-8") as f:
        m = re.search(r'^VERSAO = "([^"]+)"', f.read(), re.M)
    return {"versao": m.group(1) if m else None, "url": baixar.url_publica() + "/v1/cli/vs"}


@app.get("/v1/cli/vs")
def baixar_cli_vs():
    """A mesma CLI com o nome do Vault System: salva como `vs` (ou vs.py), ela se apresenta como vs."""
    return FileResponse(_cli_vs(), media_type="text/x-python", filename="vs",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


INSTALADORES = {"install.ps1": "text/plain; charset=utf-8", "install.sh": "text/x-shellscript; charset=utf-8"}


@app.get("/v1/cli/{nome}")
def instalador_cli(nome: str):
    """Instaladores da VS CLI, já com o endereço deste hub (sem credencial):
    `irm <hub>/v1/cli/install.ps1 | iex` no Windows e `curl -fsSL <hub>/v1/cli/install.sh | sh` no resto."""
    if nome not in INSTALADORES:
        raise HTTPException(404, "não encontrado")
    caminho = os.path.join(os.path.dirname(_cli_vs()), nome)
    if not os.path.isfile(caminho):
        raise HTTPException(404, "instalador não incluído nesta imagem")
    with open(caminho, encoding="utf-8") as f:
        texto = f.read().replace("{{HUB}}", baixar.url_publica())
    if nome.endswith(".ps1"):
        texto = texto.replace("\r\n", "\n").replace("\n", "\r\n")  # o PowerShell 5.1 prefere CRLF
    return Response(texto, media_type=INSTALADORES[nome],
                    headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


@app.post("/mcp")
def mcp(corpo=Body(None), cred=Depends(credencial)):
    """MCP (Streamable HTTP, só respostas JSON). Uma mensagem JSON-RPC por POST."""
    if isinstance(corpo, list):
        return JSONResponse(conhecimento.resposta(None, erro={"code": -32600, "message": "Batch not supported"}),
                            status_code=400)
    resposta = conhecimento.atender(corpo, cred)
    return Response(status_code=202) if resposta is None else JSONResponse(resposta)


@app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
def mcp_sem_stream():
    # Sem stream SSE do servidor e sem sessão para encerrar (a especificação aceita 405).
    return Response(status_code=405, headers={"Allow": "POST"})


# --- tela ------------------------------------------------------------------
# Os arquivos compilados do React (web/dist, copiados na imagem). Qualquer caminho
# fora da API devolve o index.html, e o roteador do React mostra a tela certa.
# Registrado por último, para não encobrir nenhuma rota da API.
WEB = os.environ.get("VAULT_WEB_DIR", os.path.join(os.path.dirname(__file__), "..", "web"))


@app.get("/{caminho:path}", include_in_schema=False)
def tela(caminho: str):
    if caminho.startswith("v1/") or caminho == "v1":
        raise HTTPException(404, "rota não encontrada")
    raiz = os.path.realpath(WEB)
    arquivo = os.path.realpath(os.path.join(raiz, caminho))
    if caminho and arquivo.startswith(raiz + os.sep) and os.path.isfile(arquivo):
        # Os arquivos de assets/ têm hash no nome: podem ficar em cache para sempre.
        cache = "public, max-age=31536000, immutable" if caminho.startswith("assets/") else "no-cache"
        return FileResponse(arquivo, headers={"Cache-Control": cache})
    indice = os.path.join(raiz, "index.html")
    if not os.path.isfile(indice):
        raise HTTPException(404, "tela não instalada nesta imagem")
    return FileResponse(indice, headers={"Cache-Control": "no-cache"})
