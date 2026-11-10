"""API da tela, fase 1. Plano: docs/tela-plano.md.

Rotas em /v1/painel, para a sessão de um administrador (login do AD em
sessao.py). A API dos agentes (/v1/sistemas, credencial `vs_`) continua igual.

A API não monta o vault: notas, registro, conflitos e verificação vêm do
estado.db, gravados pelo curador ao fim de cada rodada (verificacao.indexar e
gravar_problemas). Rodadas, lotes e avisos vêm do histórico do curador
(vault_system/historico.py).

Selo geral de um sistema (tela-plano.md, seção 2.2), o primeiro que valer:
erro de acesso > com problema > processando > em dia > vazio.
"""
import collections
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from vault_system import arquivos, arvore, conversa, estado, github_app, historico, infra, mapa, templates, vault_i
from vault_system.estado import conectar, url_arquivo, url_commit, url_repo  # noqa: F401 - url_* também usados nos testes

from . import baixar, credenciais, envio, renderizacao, sessao, sistemas

router = APIRouter(prefix="/v1/painel")


@router.get("/cli")
def catalogo_cli(adm=Depends(sessao.administrador)):
    with conectar() as db:
        return {"templates": templates.listar(db)}


@router.get("/cli/templates/{tipo}/{nome}")
def detalhes_cli(tipo: str, nome: str, adm=Depends(sessao.administrador)):
    try:
        tipo, nome = templates.separar(f"{tipo}:{nome}")
        with conectar() as db:
            return templates.detalhes(db, tipo, nome)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except templates.NaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/envios/{tag}", status_code=201)
async def cadastrar_por_envio(tag: str, request: Request, modo: str | None = None, origem: str | None = None,
                             adm=Depends(sessao.administrador)):
    """Envio pelo painel: cria o vault (com modo), soma uma origem nova a ele (com origem) ou atualiza a
    origem de envio que já existe. Os arquivos chegam num ZIP, montado no navegador quando são soltos."""
    return await envio.receber(request, tag, adm["login"], modo, origem)
ORDEM_TIPOS = ["possivel_segredo", "origem_sumiu", "origem_nao_cadastrada", "link_quebrado", "link_outra_tag",
               "cabecalho", "sistema_errado", "tipo_nota_errado", "assunto_sem_documento", "documento_orfao",
               "infra_sem_servico"]
ORDEM_SELO = ["erro_acesso", "com_problema", "processando", "vazio", "em_dia"]  # para ordenar a lista


# --- leitura do estado -----------------------------------------------------------

def _json(texto, padrao=None):
    try:
        return json.loads(texto) if texto else padrao
    except ValueError:
        return padrao


def _origens(db, tag):
    saida = []
    for o in db.execute("SELECT * FROM origens WHERE tag = ? ORDER BY id", (tag,)):
        if o["removida_em"]:
            situacao = "removendo"
        elif o["acesso_ok"] == 0:
            situacao = "sem_acesso"
        elif not o["commit_pendente"]:
            situacao = "nunca_processado"
        elif o["commit_processado"] != o["commit_pendente"] or (o["commits_atras"] or 0) > 0:
            situacao = "atrasado"
        else:
            situacao = "em_dia"
        saida.append({
            "nome": o["nome"], "repo": o["repo"], "ramo": o["ramo"], "url": url_repo(o["repo"]),
            "leituras": _json(o["leituras"], []), "leituras_antes": _json(o["leituras_antes"], None),
            "classificacao": _json(o["classificacao"], None),
            "removida_em": o["removida_em"],
            "situacao": situacao, "commits_atras": o["commits_atras"],
            "acesso": {"ok": None if o["acesso_ok"] is None else bool(o["acesso_ok"]),
                       "em": o["acesso_em"], "erro": o["acesso_erro"]},
            "commit_processado": {"hash": o["commit_processado"], "data": o["data_processado"],
                                  "url": url_commit(o["repo"], o["commit_processado"])},
            "commit_pendente": {"hash": o["commit_pendente"], "data": o["data_pendente"],
                                "url": url_commit(o["repo"], o["commit_pendente"])},
        })
    return saida


def _ultimo_pull(db, tag, atendido=False):
    filtro = "AND atendido_em IS NOT NULL" if atendido else ""
    p = db.execute(f"SELECT * FROM pulls WHERE tag = ? {filtro} ORDER BY id DESC LIMIT 1", (tag,)).fetchone()
    return _resumo_pull(p) if p else None


def _erro_do_pull(r):
    if not r:
        return None
    if r.get("erro"):
        return r["erro"]
    erros = [f"{o}: {v['erro']}" for o, v in (r.get("origens") or {}).items() if v.get("erro")]
    return "; ".join(erros) or None


def _resumo_pull(p):
    r = _json(p["resultado"])
    return {"id": p["id"], "pedido_em": p["pedido_em"], "pedido_por": p["pedido_por"],
            "atendido_em": p["atendido_em"], "estado": "concluido" if p["atendido_em"] else "pedido",
            "erro": _erro_do_pull(r), "itens": (r or {}).get("itens", {}),
            "ignorados": len(_separar(r)[0]), "guardados": len(_separar(r)[1]),
            "mascarados": (r or {}).get("mascarados", 0),
            "origens": {o: {k: v.get(k) for k in ("de", "para", "nada_novo", "aviso", "erro")}
                        for o, v in ((r or {}).get("origens") or {}).items()}}


def _categoria(motivo):
    m = (motivo or "").lower()
    for chave, rotulo in (("segredo", "segredo"), ("binário", "binário"), ("acima de", "acima do limite de tamanho"),
                          ("padrão", "filtro do cadastro"), ("leitura", "filtro do cadastro"),
                          ("dependências", "vendor, node_modules e lockfiles"),
                          ("lockfile", "vendor, node_modules e lockfiles"), ("vazio", "arquivo vazio"),
                          ("estrutura do git", "arquivo de estrutura do git"), ("link simbólico", "link ou submódulo"),
                          ("deixou de passar", "deixou de passar no filtro")):
        if chave in m:
            return rotulo
    return "outro"


def _guardado(i):
    """Binário de um tipo que o vault guarda como arquivo (fonte, imagem, PDF, áudio): não vira texto para o
    curador, mas fica no vault e sai no download, no vs add template e no MCP. Não é ignorado."""
    m = (i.get("motivo") or "").lower()
    return m.startswith(("binário", "acima de")) and bool(arquivos.tipo(i.get("caminho") or ""))


def _separar(r):
    """(ignorados de verdade, guardados como arquivo) de um resultado de pull."""
    todos = (r or {}).get("ignorados", [])
    return [i for i in todos if not _guardado(i)], [i for i in todos if _guardado(i)]


def _ignorados(p):
    r = _json(p["resultado"], {}) if p else {}
    ignorados, guardados = _separar(r)
    grupos = collections.OrderedDict()
    for i in ignorados:
        grupos.setdefault(_categoria(i.get("motivo")), []).append(i)
    return {"total": len(ignorados), "mascarados": r.get("mascarados", 0),
            "por_motivo": [{"motivo": k, "quantos": len(v), "arquivos": v} for k, v in grupos.items()],
            "guardados": [{"origem": i.get("origem"), "caminho": i.get("caminho")} for i in guardados]}


def _verificacao(db, tag):
    v = db.execute("SELECT * FROM verificacoes WHERE tag = ?", (tag,)).fetchone()
    por_tipo = {l["tipo"]: l["n"] for l in db.execute(
        "SELECT tipo, COUNT(*) n FROM problemas WHERE tag = ? GROUP BY tipo", (tag,))}
    return {"rodou_em": v["rodou_em"] if v else None, "commits": _json(v["commits"], {}) if v else {},
            "total": v["total"] if v else None, "por_tipo": por_tipo}


def _lote_atual(db, tag):
    """O lote em curso deste vault, de qualquer trabalhador do curador."""
    return next((l for l in historico.em_curso(historico.ler_estado(db), "lote") if l.get("tag") == tag), None)


def _ultima_rodada(db, tag):
    l = db.execute("SELECT l.*, r.modo, r.resultado AS r_resultado FROM lotes l LEFT JOIN rodadas r ON r.id = l.rodada_id "
                   "WHERE l.tag = ? ORDER BY l.id DESC LIMIT 1", (tag,)).fetchone()
    r = db.execute("SELECT * FROM rodadas WHERE tags LIKE ? ORDER BY id DESC LIMIT 1", (f'%"{tag}"%',)).fetchone()
    if not r and not l:
        return None
    return {"rodada_id": r["id"] if r else l["rodada_id"], "inicio": r["inicio"] if r else l["inicio"],
            "fim": r["fim"] if r else l["fim"], "resultado": r["resultado"] if r else None,
            "ultimo_lote": {"id": l["id"], "rodada_id": l["rodada_id"], "perfil": l["perfil"], "itens": l["itens"],
                            "registrados": l["registrados"], "erro": l["erro"], "fim": l["fim"]} if l else None}


def sinais(db, tag):
    """Os sinais de confiança e o selo geral de um sistema (tela-plano.md, seção 2)."""
    origens = _origens(db, tag)
    fila = db.execute("SELECT COUNT(*) FROM fila WHERE tag = ? AND estado = 'na_fila'", (tag,)).fetchone()[0]
    parados = db.execute("SELECT COUNT(*) FROM fila WHERE tag = ? AND estado = 'na_fila' AND parado_em IS NOT NULL",
                         (tag,)).fetchone()[0]
    pull_pendente = db.execute("SELECT id FROM pulls WHERE tag = ? AND atendido_em IS NULL ORDER BY id LIMIT 1",
                               (tag,)).fetchone()
    algum_pull = db.execute("SELECT 1 FROM pulls WHERE tag = ? LIMIT 1", (tag,)).fetchone()
    ultimo = db.execute("SELECT * FROM pulls WHERE tag = ? AND atendido_em IS NOT NULL ORDER BY id DESC LIMIT 1",
                        (tag,)).fetchone()
    verif = _verificacao(db, tag)
    notas = db.execute("SELECT COUNT(*) FROM notas_indice WHERE tag = ? AND pasta != 'indices'", (tag,)).fetchone()[0]
    ign = _ignorados(ultimo)
    rodada = _ultima_rodada(db, tag)
    lote_atual = _lote_atual(db, tag)

    piores = ["sem_acesso", "atrasado", "nunca_processado", "em_dia"]
    em_dia = min((o["situacao"] for o in origens if o["situacao"] != "removendo"), key=piores.index,
                 default="nunca_processado")
    atras = sum(o["commits_atras"] or 0 for o in origens)
    motivos_ign = [g["motivo"] for g in sorted(ign["por_motivo"], key=lambda g: -g["quantos"])[:3]]
    s = {"em_dia": {"estado": em_dia, "commits_atras": atras},
         "fila": {"itens": fila, "parados": parados},
         "verificacao": {"total": verif["total"], "por_tipo": verif["por_tipo"]},
         "ignorados": {"total": ign["total"], "motivos": motivos_ign},
         "pedidos_abertos": None,  # fase 3
         "notas": notas}

    sem_acesso = [o["nome"] for o in origens if o["situacao"] == "sem_acesso"]
    problemas = []
    if verif["total"]:
        problemas.append(f"Verificação: {verif['total']} problema(s)")
    erro_pull = _erro_do_pull(_json(ultimo["resultado"])) if ultimo else None
    if erro_pull:
        problemas.append("Último pull com erro")
    lote = rodada and rodada["ultimo_lote"]
    # Só o lote da última rodada do vault: vault que deixou de ter lote (cópia sem LLM) ou que
    # teve rodada depois do lote com erro não fica preso no erro antigo. O que o lote não registrou volta à fila,
    # e item que não anda aparece como parado.
    if lote and lote["erro"] and lote["fim"] and lote["rodada_id"] == rodada["rodada_id"]:
        problemas.append("Último lote do curador com erro")
    if parados:
        problemas.append(f"{parados} item(ns) parado(s) na fila")
    if em_dia == "atrasado" and not fila and not pull_pendente and not lote_atual:
        problemas.append(f"Atrasado: {atras} commit(s)")

    if sem_acesso:
        selo = ("erro_acesso", "Sem acesso ao repositório: " + ", ".join(sem_acesso))
    elif problemas:
        selo = ("com_problema", "Com problema: " + "; ".join(problemas))
    elif pull_pendente or fila or lote_atual:
        partes = ([f"pull #{pull_pendente['id']} pedido"] if pull_pendente else []) + \
            ([f"{fila} item(ns) na fila"] if fila else []) + (["curador trabalhando"] if lote_atual else [])
        selo = ("processando", "Processando: " + ", ".join(partes))
    elif not algum_pull and all(not o["commit_pendente"]["hash"] for o in origens):
        selo = ("vazio", "Aguardando o primeiro pull")
    elif em_dia == "em_dia":
        selo = ("em_dia", "Em dia" + (f" (última rodada {rodada['fim'] or rodada['inicio']})" if rodada else ""))
    else:
        selo = ("vazio", "Aguardando o primeiro pull")
    return {"selo": {"estado": selo[0], "texto": selo[1]}, "sinais": s, "origens": origens,
            "ultima_rodada": rodada, "lote_atual": lote_atual,
            "pull_pendente": pull_pendente["id"] if pull_pendente else None}


def _sistema_ou_404(db, tag):
    if not estado.TAG.match(tag):
        raise HTTPException(400, "tag inválida")
    s = db.execute("SELECT * FROM sistemas WHERE tag = ?", (tag,)).fetchone()
    if not s:
        raise HTTPException(404, "sistema não cadastrado")
    return s


# --- entrar e sair -----------------------------------------------------------------

class Login(BaseModel):
    login: str = ""
    senha: str = ""


@router.post("/entrar")
def entrar(dados: Login, request: Request):
    if "session" not in request.scope:
        raise HTTPException(503, "Tela desligada: VAULT_SESSAO_SEGREDO não configurado.")
    u = sessao.entrar(request, request.app.state.ldap, dados.login, dados.senha)
    return {"login": u.login, "nome": u.nome, "papel": "administrador"}


@router.post("/sair")
def sair(request: Request):
    if "session" in request.scope:
        request.session.clear()
    return {"ok": True}


@router.get("/eu")
def eu(adm=Depends(sessao.administrador)):
    with conectar() as db:
        p = db.execute("SELECT apresentacao_vista_em FROM preferencias WHERE login = ?", (adm["login"],)).fetchone()
        curadoria = curadoria_interna(db)
    return {**adm, "papel": "administrador", "ambiente": _ambiente(), "url_publica": url_publica(),
            "apresentacao_vista_em": p["apresentacao_vista_em"] if p else None, "curadoria": curadoria}


# Endereço que os consumidores usam para a API e o MCP (decisão de 30/10: o IP do servidor).
url_publica = baixar.url_publica


class Apresentacao(BaseModel):
    vista: bool


@router.put("/eu/apresentacao")
def marcar_apresentacao(dados: Apresentacao, adm=Depends(sessao.administrador)):
    """A apresentação de três passos aparece na primeira entrada; concluir ou
    pular grava aqui. `vista: false` faz aparecer de novo (rever pelo perfil)."""
    em = estado.agora() if dados.vista else None
    with conectar() as db:
        db.execute("INSERT INTO preferencias (login, apresentacao_vista_em) VALUES (?, ?) ON CONFLICT(login) "
                   "DO UPDATE SET apresentacao_vista_em = excluded.apresentacao_vista_em", (adm["login"], em))
    return {"apresentacao_vista_em": em}


def _ambiente():
    import os
    return os.environ.get("VAULT_AMBIENTE", "homologação")


# --- sistemas ------------------------------------------------------------------------

@router.get("/sistemas")
def listar_sistemas(adm=Depends(sessao.administrador)):
    with conectar() as db:
        linhas = []
        for s in db.execute("SELECT * FROM sistemas ORDER BY tag").fetchall():
            d = sinais(db, s["tag"])
            linhas.append({"tag": s["tag"], "removido_em": s["removido_em"], **d})
        curador = historico.ler_estado(db)
    for l in linhas:
        if l["removido_em"]:
            l["selo"] = {"estado": "removendo", "texto": "Removendo"}
    contagem = collections.Counter(l["selo"]["estado"] for l in linhas)
    linhas.sort(key=lambda l: (ORDEM_SELO.index(l["selo"]["estado"]) if l["selo"]["estado"] in ORDEM_SELO
                               else len(ORDEM_SELO), l["tag"]))
    em_curso = historico.em_curso(curador, "rodada")
    return {"sistemas": linhas, "por_estado": dict(contagem), "proxima_rodada": curador.get("proxima_rodada"),
            "rodada_em_curso": em_curso[0] if em_curso else None, "rodadas_em_curso": em_curso,
            "trabalhadores": curador.get("trabalhadores") or []}


@router.get("/sistemas/{tag}")
def ver_sistema(tag: str, adm=Depends(sessao.administrador)):
    with conectar() as db:
        s = _sistema_ou_404(db, tag)
        d = sinais(db, tag)
        ultimo = _ultimo_pull(db, tag)
        agente = db.execute("SELECT COUNT(*) FROM notas_indice WHERE tag = ? AND conteudo LIKE ?",
                            (tag, "%\ncurada_por: agente\n%")).fetchone()[0]
        curadoria = curadoria_interna(db)
        ultima = vault_i.listar(db, tag, 1)
        curadoria["ultima"] = {k: ultima[0][k] for k in ("id", "estado", "pedido_em", "fim", "notas", "erro", "via")} if ultima else None
    if s["removido_em"]:
        d["selo"] = {"estado": "removendo", "texto": "Removendo: o curador apaga a pasta da tag, o clone, os lotes "
                                                      "e o cadastro em até 30 s"}
    return {"tag": tag, "cadastro": {"por": s["criado_por"], "em": s["criado_em"]}, "removido_em": s["removido_em"],
            "ultimo_pull": ultimo, "modo": s["modo"], "notas_do_agente": agente, "curadoria": curadoria, **d}


def curadoria_interna(db):
    """Vault-I: há chave de API configurada? A curadoria nunca é automática; o botão só aparece com ela."""
    c = vault_i.configuracao(db)
    return {"disponivel": bool(c), "provedor": c["provedor"] if c else None, "modelo": c["modelo"] if c else None}


@router.post("/sistemas/{tag}/curadoria", status_code=202)
def pedir_curadoria(tag: str, adm=Depends(sessao.administrador)):
    """Pede ao Vault-I que cure o vault agora (sob demanda; nunca automático). 409 sem chave de API."""
    with conectar() as db:
        s = _sistema_ou_404(db, tag)
        if s["removido_em"]:
            raise HTTPException(409, "remoção do sistema já pedida")
        try:
            pid, ja = vault_i.pedir(db, tag, adm["login"], "painel")
        except vault_i.SemConfiguracao as e:
            raise HTTPException(409, str(e))
    return {"tag": tag, "pedido": pid, "ja_havia": ja, "estado": "pedida"}


@router.get("/sistemas/{tag}/curadorias")
def ver_curadorias(tag: str, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        lista = vault_i.listar(db, tag)
    for c in lista:
        c["detalhe"] = _json(c["detalhe"], None)
    return {"curadorias": lista}


# --- conversa com o Vault-I -----------------------------------------------------------------

class NovaConversa(BaseModel):
    escopo: str = "hub"
    tag: str | None = None
    nota: str | None = Field(default=None, max_length=500)
    pergunta: str = Field(max_length=conversa.LIMITE_PERGUNTA)


class Pergunta(BaseModel):
    pergunta: str = Field(max_length=conversa.LIMITE_PERGUNTA)


def _erro_conversa(e):
    if isinstance(e, conversa.SemConfiguracao):
        return HTTPException(409, str(e))
    if isinstance(e, LookupError):
        return HTTPException(404, str(e))
    if isinstance(e, FileExistsError):
        return HTTPException(409, str(e))
    return HTTPException(400, str(e))


@router.get("/conversas")
def listar_conversas(adm=Depends(sessao.administrador)):
    with conectar() as db:
        return {"disponivel": bool(vault_i.configuracao(db)), "conversas": conversa.listar(db, adm["login"])}


@router.post("/conversas", status_code=201)
def nova_conversa(dados: NovaConversa, adm=Depends(sessao.administrador)):
    with conectar() as db:
        try:
            cid = conversa.criar(db, adm["login"], dados.escopo, dados.pergunta, dados.tag, dados.nota)
        except (conversa.SemConfiguracao, LookupError, ValueError) as e:
            raise _erro_conversa(e) from None
        return conversa.ler(db, cid, adm["login"])


@router.get("/conversas/{cid}")
def ver_conversa(cid: int, adm=Depends(sessao.administrador)):
    with conectar() as db:
        try:
            return conversa.ler(db, cid, adm["login"])
        except LookupError as e:
            raise _erro_conversa(e) from None


@router.post("/conversas/{cid}/mensagens", status_code=201)
def perguntar_na_conversa(cid: int, dados: Pergunta, adm=Depends(sessao.administrador)):
    with conectar() as db:
        try:
            conversa.perguntar(db, cid, adm["login"], dados.pergunta)
        except (conversa.SemConfiguracao, LookupError, ValueError, FileExistsError) as e:
            raise _erro_conversa(e) from None
        return conversa.ler(db, cid, adm["login"])


@router.delete("/conversas/{cid}", status_code=204)
def apagar_conversa(cid: int, adm=Depends(sessao.administrador)):
    with conectar() as db:
        try:
            conversa.apagar(db, cid, adm["login"])
        except LookupError as e:
            raise _erro_conversa(e) from None


# --- configurações: Vault-I ---------------------------------------------------------------

class ConfigVaultI(BaseModel):
    provedor: str
    modelo: str = ""
    chave: str = Field(default="", max_length=400)


@router.get("/vault-i")
def ver_vault_i(adm=Depends(sessao.administrador)):
    with conectar() as db:
        return vault_i.publica(db)


@router.put("/vault-i")
def salvar_vault_i(dados: ConfigVaultI, adm=Depends(sessao.administrador)):
    with conectar() as db:
        try:
            vault_i.salvar(db, dados.provedor, dados.modelo, dados.chave, adm["login"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return vault_i.publica(db)


@router.delete("/vault-i")
def remover_vault_i(adm=Depends(sessao.administrador)):
    with conectar() as db:
        vault_i.remover(db)
        return vault_i.publica(db)


@router.get("/sistemas/{tag}/fila")
def ver_fila(tag: str, limite: int = 20, adm=Depends(sessao.administrador)):
    """Os primeiros `limite` itens na fila (os parados antes, depois os que já
    falharam), com o total: a fila de um repositório grande passa de milhares
    de itens no primeiro pull. Parado: o curador desistiu do item
    depois de VAULT_TENTATIVAS_MAX tentativas; volta com `retomar`."""
    with conectar() as db:
        _sistema_ou_404(db, tag)
        repos = {o["nome"]: o["repo"] for o in db.execute("SELECT nome, repo FROM origens WHERE tag = ?", (tag,))}
        total, parados = db.execute("SELECT COUNT(*), COUNT(parado_em) FROM fila "
                                    "WHERE tag = ? AND estado = 'na_fila'", (tag,)).fetchone()
        itens = db.execute("SELECT * FROM fila WHERE tag = ? AND estado = 'na_fila' "
                           "ORDER BY parado_em IS NULL, tentativas DESC, id LIMIT ?",
                           (tag, max(1, min(limite, 1000)))).fetchall()
    return {"total": total, "parados": parados, "itens": [
        {"id": i["id"], "acao": i["acao"], "caminho": i["caminho"], "origem": i["origem"], "perfil": i["perfil"],
         "commit": i["commit_origem"], "desde": i["criado_em"], "tentativas": i["tentativas"],
         "parado": i["parado_em"] is not None, "parado_em": i["parado_em"], "erro": i["erro"], "motivo": i["motivo"],
         "url": None if i["acao"] == "removido" else url_arquivo(repos.get(i["origem"]), i["commit_origem"], i["caminho"])}
        for i in itens]}


@router.post("/sistemas/{tag}/fila/{item}/retomar")
def retomar(tag: str, item: int, adm=Depends(sessao.administrador)):
    """Item parado volta à fila do começo (zero tentativas): na próxima rodada
    o curador tenta de novo, num lote só dele se ele falhar de novo."""
    with conectar() as db:
        _sistema_ou_404(db, tag)
        with db:
            n = db.execute("UPDATE fila SET parado_em = NULL, tentativas = 0, erro = NULL WHERE id = ? AND tag = ? "
                           "AND estado = 'na_fila' AND parado_em IS NOT NULL", (item, tag)).rowcount
    if not n:
        raise HTTPException(404, "item parado não encontrado na fila")
    return {"id": item, "estado": "na_fila"}


@router.get("/sistemas/{tag}/pulls")
def ver_pulls(tag: str, limite: int = 50, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        return [_resumo_pull(p) for p in db.execute(
            "SELECT * FROM pulls WHERE tag = ? ORDER BY id DESC LIMIT ?", (tag, min(limite, 500)))]


@router.get("/sistemas/{tag}/pulls/{pid}")
def ver_pull(tag: str, pid: int, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        p = db.execute("SELECT * FROM pulls WHERE tag = ? AND id = ?", (tag, pid)).fetchone()
    if not p:
        raise HTTPException(404, "pull não encontrado")
    return {**_resumo_pull(p), "ignorados": _ignorados(p)}


@router.get("/sistemas/{tag}/rodadas")
def ver_rodadas(tag: str, limite: int = 10, todas: bool = False, adm=Depends(sessao.administrador)):
    """Por padrão só as rodadas em que o curador fez algo com a tag (ou a em curso): as
    rodadas automáticas sem nada novo seriam a maioria da lista. `todas=true` mostra todas."""
    filtro = "tags LIKE ?" + ("" if todas else
                              " AND (fim IS NULL OR EXISTS (SELECT 1 FROM lotes l WHERE l.rodada_id = rodadas.id"
                              " AND l.tag = ?))")
    args = (f'%"{tag}"%',) + (() if todas else (tag,))
    with conectar() as db:
        _sistema_ou_404(db, tag)
        total = db.execute(f"SELECT COUNT(*) FROM rodadas WHERE {filtro}", args).fetchone()[0]
        rodadas = db.execute(f"SELECT * FROM rodadas WHERE {filtro} ORDER BY id DESC LIMIT ?",
                             args + (max(1, min(limite, 300)),)).fetchall()
        saida = []
        for r in rodadas:
            lotes = db.execute("SELECT * FROM lotes WHERE rodada_id = ? AND tag = ? ORDER BY id", (r["id"], tag)).fetchall()
            saida.append({"id": r["id"], "modo": r["modo"], "inicio": r["inicio"], "fim": r["fim"],
                          "resultado": r["resultado"], "lotes": len(lotes),
                          "itens": sum(l["itens"] for l in lotes),
                          "registrados": sum(l["registrados"] or 0 for l in lotes),
                          "com_erro": sum(1 for l in lotes if l["erro"]),
                          "avisos": db.execute("SELECT COUNT(*) FROM avisos WHERE rodada_id = ? AND tag = ?",
                                               (r["id"], tag)).fetchone()[0]})
        return {"rodadas": saida, "total": total, "lote_atual": _lote_atual(db, tag),
                "proxima_rodada": historico.ler_estado(db).get("proxima_rodada")}


@router.get("/sistemas/{tag}/rodadas/{rid}")
def ver_rodada(tag: str, rid: int, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        r = db.execute("SELECT * FROM rodadas WHERE id = ?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "rodada não encontrada")
        lotes = [dict(l) for l in db.execute("SELECT * FROM lotes WHERE rodada_id = ? AND tag = ? ORDER BY id",
                                             (rid, tag))]
        avisos = [dict(a) for a in db.execute("SELECT * FROM avisos WHERE rodada_id = ? AND tag = ? ORDER BY id",
                                              (rid, tag))]
    return {**dict(r), "tags": _json(r["tags"], []), "lotes": lotes, "avisos": avisos}


@router.get("/sistemas/{tag}/avisos")
def ver_avisos(tag: str, limite: int = 100, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        return [dict(a) for a in db.execute("SELECT * FROM avisos WHERE tag = ? ORDER BY id DESC LIMIT ?",
                                            (tag, min(limite, 1000)))]


@router.get("/sistemas/{tag}/verificacao")
def ver_verificacao(tag: str, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        v = _verificacao(db, tag)
        probs = [dict(p) for p in db.execute("SELECT tipo, nota, detalhe, desde FROM problemas WHERE tag = ?", (tag,))]
    probs.sort(key=lambda p: (ORDEM_TIPOS.index(p["tipo"]) if p["tipo"] in ORDEM_TIPOS else 99, p["detalhe"]))
    return {**v, "estado": "nunca_verificado" if v["rodou_em"] is None else ("limpa" if not v["total"] else
                                                                               "com_problema"),
            "problemas": probs}


@router.get("/sistemas/{tag}/notas")
def ver_arvore(tag: str, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        probs = collections.Counter(p["nota"] for p in db.execute("SELECT nota FROM problemas WHERE tag = ?", (tag,)))
        pastas = collections.OrderedDict()
        for n in db.execute("SELECT chave, pasta, titulo, tipo_nota, atualizado_em FROM notas_indice WHERE tag = ? "
                            "ORDER BY pasta, chave", (tag,)):
            pastas.setdefault(n["pasta"], []).append({**dict(n), "problemas": probs.get(n["chave"], 0)})
    return {"pastas": [{"pasta": p, "quantas": len(v), "notas": v} for p, v in pastas.items()]}


@router.get("/sistemas/{tag}/notas/{chave:path}")
def ver_nota(tag: str, chave: str, adm=Depends(sessao.administrador)):
    if not chave.startswith(f"sistemas/{tag}/"):
        chave = f"sistemas/{tag}/{chave}"
    chave = re.sub(r"\.md$", "", chave)
    with conectar() as db:
        _sistema_ou_404(db, tag)
        n = db.execute("SELECT * FROM notas_indice WHERE tag = ? AND chave = ?", (tag, chave)).fetchone()
        if not n:
            raise HTTPException(404, "Esta nota não existe mais.")
        origens = {o["nome"]: o for o in db.execute("SELECT * FROM origens WHERE tag = ?", (tag,))}
        refs = _json(n["origens"], [])
        links = [{k: p[k] for k in ("ref", "origem", "caminho", "url")}
                 for p in estado.proveniencia(origens, refs, n["commit_origem"])]
        probs = [dict(p) for p in db.execute("SELECT tipo, detalhe, desde FROM problemas WHERE tag = ? AND nota = ?",
                                             (tag, chave))]
        pendentes = [dict(i) for i in db.execute(
            "SELECT id, acao, caminho, origem FROM fila WHERE tag = ? AND estado = 'na_fila'", (tag,))
            if estado.ref(i["origem"], i["caminho"]) in refs]
    return {**{k: n[k] for k in ("chave", "pasta", "titulo", "tipo_nota", "commit_origem", "criado_em",
                                 "atualizado_em", "conteudo")},
            "origens": links, "problemas": probs, "itens_na_fila": pendentes}


# --- arquivos para baixar ---------------------------------------------------

@router.get("/sistemas/{tag}/arquivos")
def listar_arquivos(tag: str, adm=Depends(sessao.administrador)):
    """Fontes, imagens e PDF das leituras de Referência, para baixar (vault_system/arquivos.py)."""
    with conectar() as db:
        _sistema_ou_404(db, tag)
        itens = arquivos.listar(db, tag)
    return {"arquivos": itens, "limite": arquivos.LIMITE, "limite_pacote": arquivos.LIMITE_PACOTE,
            "extensoes": sorted(arquivos.PERMITIDOS)}


@router.get("/sistemas/{tag}/arquivos/baixar")
def baixar_arquivo(tag: str, caminho: str, origem: str = "principal", adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        return baixar.arquivo(db, tag, origem, caminho)


@router.get("/sistemas/{tag}/arquivos.zip")
def baixar_pacote(tag: str, pasta: str | None = None, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        return baixar.pacote(db, tag, pasta)


@router.get("/sistemas/{tag}/renderizar")
def renderizar(tag: str, pagina: str, extra: list[str] = Query(default=[]), adm=Depends(sessao.administrador)):
    """Uma página do vault de Referência com tudo embutido, para o
    iframe isolado da aba Renderização. `pagina` e `extra`: chaves de notas."""
    chaves = [c if c.startswith(f"sistemas/{tag}/") else f"sistemas/{tag}/{c}" for c in [pagina, *extra]]
    with conectar() as db:
        _sistema_ou_404(db, tag)
        try:
            return renderizacao.montar(db, tag, chaves[0], chaves[1:])
        except renderizacao.NaoRenderizavel as e:
            raise HTTPException(422, str(e)) from None


@router.get("/sistemas/{tag}/infra")
def ver_infra(tag: str, adm=Depends(sessao.administrador)):
    """Infraestrutura de containers para o mapa: serviços, ligações e redes lidos dos arquivos
    (vault_system/infra.py), sem LLM."""
    with conectar() as db:
        _sistema_ou_404(db, tag)
        return infra.grafo(db, tag)


@router.get("/sistemas/{tag}/mapa")
def ver_mapa(tag: str, foco: str = "sistema", limite: int = mapa.LIMITE, adm=Depends(sessao.administrador)):
    """Vizinhança de um nó do mapa, só com relações do índice das
    notas, e os totais do índice para a tela conferir o que mostra."""
    with conectar() as db:
        _sistema_ou_404(db, tag)
        g = mapa.carregar(db, tag)
    v = g.vizinhanca(foco, limite)
    if v is None:
        raise HTTPException(404, "Este item não está mais no mapa.")
    return {**v, "totais": g.totais()}


@router.get("/sistemas/{tag}/mapa/grafo")
def ver_grafo(tag: str, adm=Depends(sessao.administrador)):
    """Todas as notas e relações entre notas, para a visão de grafo."""
    with conectar() as db:
        _sistema_ou_404(db, tag)
        g = mapa.carregar(db, tag)
    return {**mapa.inteiro(g), "totais": g.totais()}


@router.get("/sistemas/{tag}/registro")
def ver_registro(tag: str, adm=Depends(sessao.administrador)):
    return _meta(tag, "registro")


@router.get("/sistemas/{tag}/conflitos")
def ver_conflitos(tag: str, adm=Depends(sessao.administrador)):
    return _meta(tag, "conflitos")


def _meta(tag, nome):
    with conectar() as db:
        _sistema_ou_404(db, tag)
        m = db.execute("SELECT conteudo FROM meta_tag WHERE tag = ? AND nome = ?", (tag, nome)).fetchone()
    return {"nome": nome, "conteudo": m["conteudo"] if m else None}


@router.get("/curador")
def ver_curador(adm=Depends(sessao.administrador)):
    with conectar() as db:
        return historico.ler_estado(db)


# --- GitHub App -----------------------------------------------------------

@router.get("/github/repos")
def github_repos(adm=Depends(sessao.administrador)):
    """Repositórios onde o App está instalado, com os ramos (gravados pelo
    curador), quando a lista foi atualizada e o erro da última tentativa."""
    with conectar() as db:
        g = historico.ler_estado(db).get("github") or {}
        repos = [{"nome": r["nome"], "repo": f"https://github.com/{r['nome']}", "ramo_padrao": r["ramo_padrao"],
                  "privado": bool(r["privado"]), "ramos": json.loads(r["ramos"])}
                 for r in db.execute("SELECT * FROM github_repos ORDER BY nome COLLATE NOCASE")]
    return {"repos": repos, "atualizado_em": g.get("em"), "erro": g.get("erro"), "pedido_em": g.get("pedido_em")}


@router.post("/github/atualizar", status_code=202)
def github_atualizar(adm=Depends(sessao.administrador)):
    """Pede ao curador a lista de novo (atende em até 30 s): para quando o
    admin acabou de incluir um repositório na instalação do App."""
    with conectar() as db:
        g = historico.ler_estado(db).get("github") or {}
        g["pedido_em"] = estado.agora()
        historico._definir(db, "github", g)
    return {"pedido_em": g["pedido_em"]}


# --- árvore de pastas -------------------------------------------------------

class PedidoArvore(BaseModel):
    repo: str
    ramo: str = "main"


@router.post("/arvores", status_code=202)
def pedir_arvore(p: PedidoArvore, adm=Depends(sessao.administrador)):
    """Pede ao curador a árvore de um repositório do App; o atendente responde
    em poucos segundos (GET /arvores/{id})."""
    if not github_app.do_app(p.repo):
        raise HTTPException(400, "a árvore só é carregada para repositório do GitHub App (https://github.com/...)")
    if not sistemas.RAMO.match(p.ramo):
        raise HTTPException(400, "ramo inválido")
    with conectar() as db:
        return {"id": arvore.pedir(db, p.repo, p.ramo, adm["login"])}


def _arvore(db, aid):
    a = db.execute("SELECT * FROM arvores WHERE id = ?", (aid,)).fetchone()
    if not a:
        raise HTTPException(404, "pedido de árvore não encontrado")
    return a


@router.get("/arvores/{aid}")
def ver_arvore(aid: int, adm=Depends(sessao.administrador)):
    with conectar() as db:
        a = _arvore(db, aid)
    if not a["atendido_em"]:
        return {"id": aid, "estado": "pedido", "repo": a["repo"], "ramo": a["ramo"]}
    r = json.loads(a["resultado"])
    if "arquivos" in r:  # o ponto de partida do vault de Referência (pedidos antigos não têm)
        r["sugestao_referencia"] = arvore.sugestao_referencia(r["arquivos"])
    return {"id": aid, "estado": "erro" if "erro" in r else "pronto", "repo": a["repo"], "ramo": a["ramo"], **r}


class Classificacao(BaseModel):
    classificacao: dict[str, str] = Field(max_length=2000)
    # Editar: com a origem, a resposta traz o que muda de destino.
    tag: str | None = None
    origem: str | None = None


class DaOrigem(BaseModel):
    tag: str
    origem: str


def _arquivos_da_arvore(aid):
    with conectar() as db:
        a = _arvore(db, aid)
    r = json.loads(a["resultado"] or "{}")
    if "arquivos" not in r:
        raise HTTPException(409, "a árvore ainda não foi carregada")
    return r["arquivos"]


def _origem(tag, nome):
    from .main import _origem_ativa
    return _origem_ativa(tag, nome)


MAX_MUDANCAS = 1000  # a tela lista no máximo isso; o total vem à parte


@router.post("/arvores/{aid}/atual")
def classificacao_atual(aid: int, d: DaOrigem, adm=Depends(sessao.administrador)):
    """A classificação que leva cada arquivo da árvore aonde as leituras da
    origem levam hoje: a gravada, se ainda bate com as leituras, ou uma
    tirada das leituras (origem cadastrada pelo formulário antigo)."""
    arquivos = _arquivos_da_arvore(aid)
    o = _origem(d.tag, d.origem)
    gravada = o.get("classificacao")
    if gravada and not arvore.mudancas(arquivos, o["leituras"], gravada):
        return {"classificacao": gravada, "gravada": True}
    return {"classificacao": arvore.classificacao_de(arquivos, o["leituras"]), "gravada": False}


@router.post("/arvores/{aid}/leituras")
def leituras_da_arvore(aid: int, c: Classificacao, adm=Depends(sessao.administrador)):
    """Leituras (perfil, incluir, excluir) equivalentes à classificação, e os
    totais por destino, para a tela mostrar e mandar no cadastro. Com tag e
    origem, também os arquivos que mudam de destino em relação a hoje."""
    r = {"arquivos": _arquivos_da_arvore(aid)}
    if any(v not in arvore.CLASSES for v in c.classificacao.values()) or "" not in c.classificacao:
        raise HTTPException(400, "classificação: documentos, referencia-explicada, referencia, codigo ou ignorar, com a raiz (\"\")")
    caminhos = [x["caminho"] for x in r["arquivos"]]
    try:
        leituras = arvore.leituras(caminhos, c.classificacao)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # As leituras geradas têm que levar cada arquivo aonde a árvore mostra.
    if arvore.mudancas(r["arquivos"], leituras, c.classificacao):
        raise HTTPException(500, "as leituras geradas não reproduzem a classificação; avise o administrador")
    totais = collections.Counter("fixo" if x["fixo"] else arvore.destino_de(x["caminho"], c.classificacao)
                                 for x in r["arquivos"])
    saida = {"leituras": leituras, "totais": {k: totais.get(k, 0) for k in (*arvore.CLASSES, "fixo")}}
    if c.tag and c.origem:
        m = arvore.mudancas(r["arquivos"], _origem(c.tag, c.origem)["leituras"], c.classificacao)
        saida["mudancas"] = m[:MAX_MUDANCAS]
        saida["total_mudancas"] = len(m)
        saida["impacto"] = arvore.impacto(m)  # a tela confirma antes de mandar muito ao curador
    return saida


# --- ações: cadastro, pull, remoção ------------------------------------------------

@router.post("/sistemas", status_code=201)
def cadastrar(dados: dict, adm=Depends(sessao.administrador)):
    """Mesmo formato e mesmas regras de POST /v1/sistemas (com `origens` e
    leituras, ou o formato antigo), pela sessão do administrador."""
    from .main import Cadastro
    try:
        c = Cadastro(**dados)
    except Exception as e:  # noqa: BLE001 - erro de validação vira 422 legível
        raise HTTPException(422, str(e))
    d = sistemas.normalizar(c.model_dump())
    erros = sistemas.validar(d)
    if erros:
        raise HTTPException(400, erros)
    if not sistemas.criar(d, adm["login"]):
        raise HTTPException(409, f"A tag {c.tag} já está cadastrada.")
    return ver_sistema(c.tag, adm)


@router.post("/sistemas/{tag}/origens", status_code=201)
def nova_origem(tag: str, dados: dict, adm=Depends(sessao.administrador)):
    """Mais uma origem num sistema (mesmas regras de POST /v1/sistemas/{tag}/origens)."""
    from .main import Origem
    try:
        o = Origem(**dados).model_dump()
    except Exception as e:  # noqa: BLE001 - erro de validação vira 422 legível
        raise HTTPException(422, str(e))
    with conectar() as db:
        s = _sistema_ou_404(db, tag)
    if s["removido_em"]:
        raise HTTPException(409, "remoção do sistema já pedida")
    erros = sistemas.validar_origem(o)
    if erros:
        raise HTTPException(400, erros)
    if not sistemas.acrescentar_origem(tag, o):
        raise HTTPException(409, f"A origem {o['nome']} já existe em {tag}.")
    return ver_sistema(tag, adm)


@router.put("/sistemas/{tag}/origens/{nome}")
def editar_origem(tag: str, nome: str, dados: dict, adm=Depends(sessao.administrador)):
    """Ramo, leituras e endereço de uma origem (mesmas regras de PUT /v1/sistemas/{tag}/origens/{nome})."""
    from .main import EdicaoOrigem, editar_origem as editar
    try:
        d = EdicaoOrigem(**dados).model_dump()
    except Exception as e:  # noqa: BLE001 - erro de validação vira 422 legível
        raise HTTPException(422, str(e))
    editar(tag, nome, d, adm["login"])
    return ver_sistema(tag, adm)


@router.delete("/sistemas/{tag}/origens/{nome}", status_code=202)
def remover_origem(tag: str, nome: str, adm=Depends(sessao.administrador)):
    from .main import remover_origem as remover
    remover(tag, nome, adm["login"])
    return ver_sistema(tag, adm)


@router.post("/sistemas/{tag}/pull", status_code=202)
def pedir_pull(tag: str, adm=Depends(sessao.administrador)):
    with conectar() as db:
        s = _sistema_ou_404(db, tag)
        pendente = db.execute("SELECT id FROM pulls WHERE tag = ? AND atendido_em IS NULL LIMIT 1", (tag,)).fetchone()
    if s["removido_em"]:
        raise HTTPException(409, "remoção do sistema já pedida")
    if pendente:
        return {"pedido": pendente["id"], "estado": "pedido", "ja_havia": True}
    return {"pedido": sistemas.pedir_pull(tag, adm["login"]), "estado": "pedido", "ja_havia": False}


@router.delete("/sistemas/{tag}", status_code=202)
def remover(tag: str, adm=Depends(sessao.administrador)):
    with conectar() as db:
        _sistema_ou_404(db, tag)
    sistemas.marcar_remocao(tag, adm["login"])
    return {"tag": tag, "estado": "remocao_pedida"}


# --- credenciais -----------------------------------------------------------------------

class NovaCredencial(BaseModel):
    nome: str = Field(min_length=1, max_length=64)
    ler: list[str] = Field(default_factory=list, max_length=100)
    escrever: list[str] = Field(default_factory=list, max_length=100)
    workspace: bool = False  # token de conexão da CLI (vs login): todos os vaults, cria vault no vs sync


class VaultsDoToken(BaseModel):
    ler: list[str] = Field(min_length=1, max_length=100)


def _credencial_publica(l):
    return {"nome": l["nome"], "ler": _json(l["ler"], []), "escrever": _json(l["escrever"], []),
            "criado_em": l["criado_em"], "criado_por": l["criado_por"], "revogada_em": l["revogada_em"],
            "usado_em": l["usado_em"], "estado": "revogada" if l["revogada_em"] else "ativa",
            "workspace": l.get("escopo") == credenciais.WORKSPACE}


def _vaults_existem(tags):
    """pela tela, o token só pode ler vaults cadastrados (e não removidos)."""
    with conectar() as db:
        ativos = {l["tag"] for l in db.execute(estado.ATIVOS)}
    faltam = [t for t in tags if t not in ativos]
    if faltam:
        raise HTTPException(400, f"Vault não cadastrado: {', '.join(faltam)}.")


@router.get("/credenciais")
def listar_credenciais(tag: str | None = None, adm=Depends(sessao.administrador)):
    """A chave nunca aparece (só o hash está guardado). Com `tag`: só as que leem ou escrevem a tag."""
    saida = [_credencial_publica(l) for l in credenciais.listar()]
    if tag:
        saida = [c for c in saida if tag in c["ler"] or tag in c["escrever"] or c["workspace"]]
    return saida


@router.post("/credenciais", status_code=201)
def criar_credencial(dados: NovaCredencial, adm=Depends(sessao.administrador)):
    if not dados.workspace:
        _vaults_existem(dados.ler + dados.escrever)
    try:
        chave = credenciais.criar(dados.nome, dados.ler, dados.escrever, por=adm["login"], workspace=dados.workspace)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001 - nome repetido (UNIQUE)
        if "UNIQUE" in str(e):
            raise HTTPException(409, f"Já existe uma credencial com o nome {dados.nome}.")
        raise
    return {"nome": dados.nome, "chave": chave,
            "workspace": dados.workspace,
            "aviso": "Esta é a única vez em que a chave aparece. Guarde-a no .env do agente."
                     if not dados.workspace else "Esta é a única vez em que a chave aparece. Use em vs login.",
            "como_usar": "Authorization: Bearer <chave>"}


@router.patch("/credenciais/{nome}")
def alterar_credencial(nome: str, dados: VaultsDoToken, adm=Depends(sessao.administrador)):
    """Troca os vaults que o token lê. A chave continua a mesma: quem usa não precisa mudar nada."""
    _vaults_existem(dados.ler)
    try:
        mudou = credenciais.alterar_leitura(nome, dados.ler)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not mudou:
        raise HTTPException(404, f"Nenhuma credencial ativa com o nome {nome}.")
    return next(_credencial_publica(l) for l in credenciais.listar() if l["nome"] == nome)


@router.delete("/credenciais/{nome}")
def revogar_credencial(nome: str, adm=Depends(sessao.administrador)):
    if not credenciais.revogar(nome):
        raise HTTPException(404, f"Nenhuma credencial ativa com o nome {nome}.")
    return {"nome": nome, "estado": "revogada"}
