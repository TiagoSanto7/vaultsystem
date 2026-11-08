"""Consulta ao conhecimento pelos agentes e aplicações: HTTP e MCP.

O MCP é um adaptador do mesmo serviço da API (contrato nas seções 9 e 10 de
docs/execucao/Vault System_Documento_de_Execucao_v1.md): transporte Streamable
HTTP em `/mcp`, só com respostas JSON (sem stream SSE), na mesma porta e com a
mesma credencial `vs_` (Authorization: Bearer). A credencial é conferida antes
de qualquer mensagem; o acesso a cada vault é conferido em cada chamada.

Ferramentas, todas só leitura: `list_systems`, `search_knowledge`, `read_note` e,
para os arquivos binários dos vaults de Referência, `list_files` e
`get_file`. O arquivo não vai pelo MCP: `get_file` devolve um link assinado de
15 minutos para baixar com `curl -o` (imagem pequena vem também como imagem).
"""
import base64
import json
import posixpath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from vault_system import arquivos, busca, estado

from . import baixar

VERSOES = ["2025-11-25", "2025-06-18", "2025-03-26"]  # a primeira é a preferida
SERVIDOR = {"name": "vault-system", "title": "Vault System", "version": "0.1.0"}
INSTRUCOES = ("Base de conhecimento curada do Vault System, um vault por sistema (system_id). Use list_systems para "
              "ver os vaults que esta credencial pode ler, search_knowledge para achar notas e read_note para ler "
              "uma nota inteira (os links [[...]] do texto são note_id de outras notas). As respostas são trechos "
              "das notas com a origem de cada uma, não respostas prontas. Fontes, imagens e PDF de um vault de "
              "Referência (design system) não são notas: list_files lista e get_file dá um link para baixar no "
              "projeto com curl.")


class Consulta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    verification: Literal["verified", "all"] = "all"
    limit: int = Field(default=busca.LIMITE, ge=1, le=busca.LIMITE_MAX)


class Leitura(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def tag_da_nota(note_id):
    """A tag de um note_id (`sistemas/<tag>/<pasta>/<nome>`), ou None."""
    partes = note_id.removesuffix(".md").split("/")
    return partes[1] if len(partes) >= 4 and partes[0] == "sistemas" and estado.TAG.match(partes[1]) else None


def sistemas_legiveis(cred):
    with estado.conectar() as db:
        linhas = db.execute("SELECT tag, COUNT(*) AS notas FROM notas_indice WHERE pasta != 'indices' GROUP BY tag")
        notas = {l["tag"]: l["notas"] for l in linhas}
    return {"systems": [{"system_id": t, "notes": notas.get(t, 0)} for t in sorted(cred["ler"])]}


# --- MCP ---------------------------------------------------------------------------

_PROVENIENCIA = {"type": "array", "items": {"type": "object", "properties": {
    "repository": {"type": "string"}, "path": {"type": "string"}, "branch": {"type": ["string", "null"]},
    "commit": {"type": ["string", "null"]}, "url": {"type": ["string", "null"]}}}}
_NOTA = {"note_id": {"type": "string"}, "title": {"type": "string"},
         "verification": {"type": "string"}, "updated_at": {"type": ["string", "null"]}, "provenance": _PROVENIENCIA}
FERRAMENTAS = [
    {"name": "list_systems", "title": "Listar vaults",
     "description": "Lista os vaults (system_id) que esta credencial pode consultar, com o número de notas de cada um.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {"systems": {"type": "array", "items": {
         "type": "object", "properties": {"system_id": {"type": "string"}, "notes": {"type": "integer"}}}}},
         "required": ["systems"]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "search_knowledge", "title": "Consultar conhecimento de um sistema",
     "description": "Busca por texto completo nas notas de um vault. Retorna trechos das notas, com estado de "
                    "verificação e proveniência (repositório, arquivo, commit). Não consulta o GitHub ao vivo, não "
                    "gera resposta de IA e não modifica dados. Nomes exatos (função, tela, regra) funcionam bem.",
     "inputSchema": {"type": "object", "properties": {
         "system_id": {"type": "string", "description": "O vault (veja list_systems)."},
         "query": {"type": "string", "minLength": 1, "maxLength": 500},
         "verification": {"type": "string", "enum": ["verified", "all"], "default": "all"},
         "limit": {"type": "integer", "minimum": 1, "maximum": busca.LIMITE_MAX, "default": busca.LIMITE}},
         "required": ["system_id", "query"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {
         "system_id": {"type": "string"}, "has_more": {"type": "boolean"},
         "results": {"type": "array", "items": {"type": "object", "properties": {**_NOTA, "excerpt": {"type": "string"}}}}},
         "required": ["system_id", "results", "has_more"]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "read_note", "title": "Ler uma nota inteira",
     "description": "Lê uma nota inteira em markdown pelo note_id (vindo de search_knowledge ou de um link [[...]] "
                    "de outra nota), com estado de verificação e proveniência.",
     "inputSchema": {"type": "object", "properties": {"note_id": {"type": "string"}},
                     "required": ["note_id"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {**_NOTA, "system_id": {"type": "string"},
                                                       "folder": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["note_id", "content"]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
]


class ListaArquivos(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    folder: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class PedidoArquivo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    path: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    origin: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] = "principal"


_ARQUIVO = {"path": {"type": "string"}, "origin": {"type": "string"}, "type": {"type": "string"},
            "size": {"type": "integer"}, "commit": {"type": "string"}}
FERRAMENTAS += [
    {"name": "list_files", "title": "Listar arquivos para baixar",
     "description": "Lista os arquivos binários de um vault de Referência (fontes, imagens, logos, PDF), que não "
                    "viram nota: caminho na origem, tipo, tamanho e commit. Use get_file para baixar um deles.",
     "inputSchema": {"type": "object", "properties": {
         "system_id": {"type": "string", "description": "O vault (veja list_systems)."},
         "folder": {"type": "string", "description": "Só os arquivos desta pasta da origem (ex.: assets/fonts)."}},
         "required": ["system_id"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {
         "system_id": {"type": "string"},
         "files": {"type": "array", "items": {"type": "object", "properties": {**_ARQUIVO, "download_url": {
             "type": "string"}}}}}, "required": ["system_id", "files"]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "get_file", "title": "Link para baixar um arquivo",
     "description": "Dá um link de download de um arquivo de list_files, válido por 15 minutos e sem credencial, "
                    "e o comando curl pronto para salvar no projeto. O conteúdo do arquivo não vem na resposta "
                    "(imagem pequena vem também como imagem, para ver).",
     "inputSchema": {"type": "object", "properties": {
         "system_id": {"type": "string"},
         "path": {"type": "string", "description": "Caminho na origem, como em list_files."},
         "origin": {"type": "string", "default": "principal"}},
         "required": ["system_id", "path"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {
         **_ARQUIVO, "url": {"type": "string"}, "expires_at": {"type": "integer"}, "curl": {"type": "string"}},
         "required": ["path", "url", "expires_at", "curl"]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}},
]
IMAGEM_NA_RESPOSTA = {"image/png", "image/jpeg", "image/gif", "image/webp"}
LIMITE_IMAGEM = 100 * 1024


class ErroFerramenta(Exception):
    pass


def _sem_acesso(tag):
    # Mesma mensagem para vault que não existe e vault sem permissão: não revela o que existe.
    return ErroFerramenta(f"Esta credencial não pode ler o vault {tag!r}. Veja list_systems.")


def _chamar(nome, args, cred):
    try:
        if nome == "list_systems":
            return sistemas_legiveis(cred)
        if nome == "search_knowledge":
            c = Consulta(**args)
            if c.system_id not in cred["ler"]:
                raise _sem_acesso(c.system_id)
            return busca.buscar(c.system_id, c.query, c.limit, c.verification)
        if nome == "read_note":
            note_id = Leitura(**args).note_id.removesuffix(".md")
            tag = tag_da_nota(note_id)
            if not tag:
                raise ErroFerramenta("note_id inválido: use o formato sistemas/<tag>/<pasta>/<nome>.")
            if tag not in cred["ler"]:
                raise _sem_acesso(tag)
            nota = busca.ler(tag, note_id)
            if not nota:
                raise ErroFerramenta(f"A nota {note_id!r} não existe.")
            return nota
        if nome == "list_files":
            p = ListaArquivos(**args)
            if p.system_id not in cred["ler"]:
                raise _sem_acesso(p.system_id)
            with estado.conectar() as db:
                itens = arquivos.listar(db, p.system_id, p.folder or None)
            return {"system_id": p.system_id, "files": [baixar.publico(p.system_id, a) for a in itens]}
        if nome == "get_file":
            p = PedidoArquivo(**args)
            if p.system_id not in cred["ler"]:
                raise _sem_acesso(p.system_id)
            with estado.conectar() as db:
                try:
                    a = arquivos.achar(db, p.system_id, p.origin, p.path)
                except arquivos.NaoEncontrado as e:
                    raise ErroFerramenta(f"{e}. Veja list_files.") from None
            expira, url = baixar.link_assinado(p.system_id, a)
            dados = {"path": a["caminho"], "origin": a["origem"], "type": a["tipo"], "size": a["tamanho"],
                     "commit": a["commit"], "url": url, "expires_at": expira,
                     "curl": f'curl -fsSL -o "{posixpath.basename(a["caminho"])}" "{url}"'}
            extra = []
            if a["tipo"] in IMAGEM_NA_RESPOSTA and a["tamanho"] <= LIMITE_IMAGEM:
                bruto, _ = arquivos.ler_blob(p.system_id, a["origem"], a["commit"], a["caminho"])
                if bruto:
                    extra.append({"type": "image", "mimeType": a["tipo"], "data": base64.b64encode(bruto).decode()})
            return dados, extra
    except ValidationError as e:
        raise ErroFerramenta("Argumentos inválidos: " + "; ".join(
            f"{'.'.join(map(str, x['loc'])) or 'arguments'}: {x['msg']}" for x in e.errors())) from None
    return None


def resposta(id_, result=None, erro=None):
    return {"jsonrpc": "2.0", "id": id_, **({"error": erro} if erro else {"result": result})}


def atender(msg, cred):
    """Uma mensagem JSON-RPC; devolve a resposta, ou None para notificações."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return resposta(msg.get("id") if isinstance(msg, dict) else None,
                         erro={"code": -32600, "message": "Invalid Request"})
    id_, metodo, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:  # notificação (ex.: notifications/initialized): nada a responder
        return None
    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        return resposta(id_, {"protocolVersion": pedida if pedida in VERSOES else VERSOES[0],
                               "capabilities": {"tools": {"listChanged": False}},
                               "serverInfo": SERVIDOR, "instructions": INSTRUCOES})
    if metodo == "ping":
        return resposta(id_, {})
    if metodo == "tools/list":
        return resposta(id_, {"tools": FERRAMENTAS})
    if metodo == "tools/call":
        nome = params.get("name")
        if nome not in {f["name"] for f in FERRAMENTAS}:
            return resposta(id_, erro={"code": -32602, "message": f"Unknown tool: {nome}"})
        try:
            dados = _chamar(nome, params.get("arguments") or {}, cred)
        except ErroFerramenta as e:
            return resposta(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        dados, extra = dados if isinstance(dados, tuple) else (dados, [])
        return resposta(id_, {"content": [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}, *extra],
                               "structuredContent": dados, "isError": False})
    return resposta(id_, erro={"code": -32601, "message": f"Method not found: {metodo}"})
