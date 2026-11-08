"""Histórico do curador (DV-547): rodadas, lotes, avisos e o que está rodando
agora, gravados no estado.db para a tela. Antes, isso só existia no log do
container, que some quando ele é recriado.

A rodada (`petro_vault.rodada`) abre e fecha a rodada; a curadoria abre e
fecha cada lote e registra os avisos do código. Falha aqui nunca derruba a
rodada: o histórico é para ver, não para decidir.
"""
import json
import os

from . import estado

RODADA = None  # id da rodada em curso neste processo (definido por rodada.py)
# Trabalhador do curador (DV-606): cada um grava a sua rodada e o seu lote em chaves próprias
# (`rodada:t1`, `lote:t1`); sem trabalhador (rodada avulsa, testes), as chaves de antes.
TRABALHADOR = os.environ.get("VAULT_TRABALHADOR") or None


def _chave(nome):
    return f"{nome}:{TRABALHADOR}" if TRABALHADOR else nome


def em_curso(estado_, nome):
    """Os valores de `nome` (rodada ou lote) de todos os trabalhadores e da rodada avulsa."""
    return [v for k, v in estado_.items() if v and (k == nome or k.startswith(nome + ":"))]


def _seguro(funcao):
    def envolta(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - histórico não derruba a rodada
            print(f"[historico] {funcao.__name__} falhou: {e}")
            return None
    return envolta


def _definir(db, chave, valor):
    with db:
        db.execute("INSERT INTO curador_estado (chave, valor) VALUES (?, ?) "
                   "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                   (chave, None if valor is None else json.dumps(valor, ensure_ascii=False)))


def ler_estado(db):
    return {l["chave"]: json.loads(l["valor"]) if l["valor"] else None
            for l in db.execute("SELECT chave, valor FROM curador_estado")}


INTERROMPIDA = "interrompida"


def interromper(db, trabalhador="*"):
    """Rodada e lote ainda abertos são de um curador que parou no meio: fecham como interrompidos.
    `trabalhador="*"`: todos (o coordenador ao subir); senão, só os desse trabalhador (None = avulsa)."""
    filtro = "" if trabalhador == "*" else ("AND trabalhador IS NULL" if trabalhador is None else "AND trabalhador = ?")
    args = () if trabalhador in ("*", None) else (trabalhador,)
    with db:
        ids = [l["id"] for l in db.execute(f"SELECT id FROM rodadas WHERE fim IS NULL {filtro}", args)]
        db.execute(f"UPDATE rodadas SET fim = ?, resultado = ? WHERE fim IS NULL {filtro}",
                   (estado.agora(), INTERROMPIDA, *args))
        if trabalhador == "*":
            db.execute("UPDATE lotes SET fim = ?, erro = ? WHERE fim IS NULL",
                       (estado.agora(), "interrompido: o curador parou no meio do lote"))
            db.execute("DELETE FROM curador_estado WHERE chave LIKE 'rodada%' OR chave LIKE 'lote%' "
                       "OR chave = 'trabalhadores'")
        elif ids:
            db.execute(f"UPDATE lotes SET fim = ?, erro = ? WHERE fim IS NULL AND rodada_id IN "
                       f"({','.join('?' * len(ids))})",
                       (estado.agora(), "interrompido: o curador parou no meio do lote", *ids))


@_seguro
def abrir_rodada(db, modo, tags):
    """Abre a rodada. Rodada ou lote ainda aberto deste mesmo trabalhador é de um curador parado no meio, e
    fecha como interrompido (os dos outros trabalhadores seguem: rodam ao mesmo tempo, DV-606)."""
    global RODADA
    interromper(db, TRABALHADOR)
    with db:
        RODADA = db.execute("INSERT INTO rodadas (modo, tags, inicio, trabalhador) VALUES (?, ?, ?, ?)",
                            (modo, json.dumps(tags), estado.agora(), TRABALHADOR)).lastrowid
    _definir(db, _chave("rodada"), {"id": RODADA, "modo": modo, "tags": tags, "inicio": estado.agora(),
                                    "trabalhador": TRABALHADOR})
    return RODADA


@_seguro
def fechar_rodada(db, resultado, intervalo=None):
    with db:
        db.execute("UPDATE rodadas SET fim = ?, resultado = ? WHERE id = ?", (estado.agora(), resultado, RODADA))
    _definir(db, _chave("rodada"), None)
    _definir(db, _chave("lote"), None)
    if intervalo:
        import datetime
        proxima = datetime.datetime.now(estado.FUSO) + datetime.timedelta(seconds=intervalo)
        _definir(db, "proxima_rodada", proxima.isoformat(timespec="seconds"))


@_seguro
def abrir_lote(db, tag, perfil, itens):
    with db:
        lote = db.execute("INSERT INTO lotes (rodada_id, tag, perfil, itens, inicio) VALUES (?, ?, ?, ?, ?)",
                          (RODADA, tag, perfil, itens, estado.agora())).lastrowid
    _definir(db, _chave("lote"), {"id": lote, "tag": tag, "perfil": perfil, "itens": itens, "inicio": estado.agora(),
                                  "trabalhador": TRABALHADOR})
    return lote


@_seguro
def fechar_lote(db, lote, registrados, codigo=None, erro=None, saida=""):
    if lote is None:
        return
    with db:
        db.execute("UPDATE lotes SET fim = ?, registrados = ?, codigo = ?, erro = ?, saida = ? WHERE id = ?",
                   (estado.agora(), registrados, codigo, erro, (saida or "")[-2000:], lote))
    _definir(db, _chave("lote"), None)


@_seguro
def aviso(db, tag, tipo, detalhe, nota=None, lote=None):
    """Tipos: fonte_inventada, sem_fontes, nota_nao_ligada, item_parado, nota_interrompida."""
    with db:
        db.execute("INSERT INTO avisos (rodada_id, lote_id, tag, tipo, nota, detalhe, em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (RODADA, lote, tag, tipo, nota, detalhe, estado.agora()))


def intervalo():
    return int(os.environ.get("VAULT_INTERVALO", "900"))
