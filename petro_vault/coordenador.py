"""Coordenador do curador (DV-606): vários vaults ao mesmo tempo.

Antes, um processo só curava um vault por vez: um repositório grande segurava
todos os outros (até 10 lotes de 20 min por rodada). Agora o coordenador:

- mantém até VAULT_TRABALHADORES processos (padrão 3), cada um rodando
  `python -m petro_vault.rodada tag <tag>` para **um** vault, com pasta de lote
  e HERMES_HOME próprios (VAULT_TRABALHO_DIR/t<N>/). O mesmo vault nunca roda
  em dois trabalhadores (e a curadoria ainda tem trava por vault);
- escolhe quem roda nesta ordem: pull pedido (tela, API, CLI), vault que ficou
  com fila da vez anterior, e a agenda (cada vault a cada VAULT_INTERVALO s);
- dá a cada trabalhador uma fatia de VAULT_LOTES_POR_VEZ lotes (padrão 3): o
  vault com fila grande volta para a fila e cede a vez aos outros;
- publica em série, quando um trabalhador termina, **só as pastas dos vaults
  que terminaram** (e a base): nada de commit com nota pela metade de outro
  vault que ainda está sendo curado;
- faz a manutenção que é de todos (remoção de cadastro e lista do GitHub App)
  fora dos trabalhadores, sem tocar em vault que está rodando.

`python -m petro_vault.coordenador` (o ciclo.sh chama); `uma-volta` para testes.
"""
import fcntl
import os
import subprocess
import sys
import time

from . import curadoria, estado, github_app, historico, rodada

TRABALHADORES = int(os.environ.get("VAULT_TRABALHADORES", "3"))
LOTES_POR_VEZ = os.environ.get("VAULT_LOTES_POR_VEZ", "3")
TRABALHO_DIR = os.environ.get("VAULT_TRABALHO_DIR", "/opt/curador")
CURADOR_DIR = os.environ.get("VAULT_CURADOR_DIR", "/opt/petro-vault/curador")
ESPERA = float(os.environ.get("VAULT_ESPERA_COORDENADOR", "5"))
VOLTA_DA_FILA = 60  # vault que ficou com fila passa na frente da agenda depois disto; antes, vai por último


def _agora():
    return time.time()


class Coordenador:
    def __init__(self, n=TRABALHADORES, publicar=None):
        self.n = max(1, n)
        self.rodando = {}  # vaga (t1..tN) -> {"tag", "proc", "motivo", "desde"}
        self.ultima = {}   # tag -> quando a última volta dela terminou
        self.publicar = publicar or publicar_tags
        self.publicados = []  # para os testes: [[tags], ...]

    # --- fila --------------------------------------------------------------------
    def fila(self, db):
        """[(tag, motivo)] na ordem: pull pedido, fila que sobrou, agenda."""
        ocupadas = {r["tag"] for r in self.rodando.values()}
        agora = _agora()
        ativos = [l["tag"] for l in db.execute(estado.ATIVOS)]
        saida, vistos = [], set(ocupadas)

        def por(tag, motivo):
            if tag not in vistos:
                vistos.add(tag)
                saida.append((tag, motivo))

        for l in db.execute("SELECT p.tag, MIN(p.pedido_em) AS em FROM pulls p JOIN sistemas s ON s.tag = p.tag "
                            "WHERE p.atendido_em IS NULL AND s.removido_em IS NULL GROUP BY p.tag ORDER BY em"):
            por(l["tag"], "pull")
        # Sem curadoria interna, a fila do LLM não anda: voltar ao vault só por ela seria um laço (a cada ESPERA s).
        com_fila = [l["tag"] for l in db.execute("SELECT DISTINCT f.tag FROM fila f JOIN sistemas s ON s.tag = f.tag "
                                                 "WHERE f.estado = 'na_fila' AND s.removido_em IS NULL ORDER BY f.tag")
                    ] if curadoria.disponivel() else []
        for tag in com_fila:
            if agora - self.ultima.get(tag, 0) >= VOLTA_DA_FILA:
                por(tag, "fila")
        intervalo = historico.intervalo()
        for tag in sorted(ativos, key=lambda t: self.ultima.get(t, 0)):
            if agora - self.ultima.get(tag, 0) >= intervalo:
                por(tag, "agenda")
        # O vault que acabou de fazer a fatia dele vai por último: se ninguém mais espera, volta na hora (sem os 60 s).
        for tag in sorted(com_fila, key=lambda t: self.ultima.get(t, 0)):
            por(tag, "fila")
        return saida

    # --- trabalhadores -----------------------------------------------------------
    def _iniciar(self, vaga, tag, motivo):
        base = os.path.join(TRABALHO_DIR, vaga)
        os.makedirs(base, exist_ok=True)
        env = {**os.environ, "VAULT_TRABALHADOR": vaga, "VAULT_LOTE_DIR": os.path.join(base, "lote"),
               "HERMES_HOME": os.path.join(base, "hermes"), "VAULT_LOTES_MAX": LOTES_POR_VEZ,
               "PYTHONUNBUFFERED": "1"}
        print(f"[coordenador] {vaga}: {tag} ({motivo})", flush=True)
        proc = subprocess.Popen([sys.executable, "-m", "petro_vault.rodada", "tag", tag, motivo], env=env)
        self.rodando[vaga] = {"tag": tag, "proc": proc, "motivo": motivo, "desde": estado.agora()}

    def _terminados(self):
        feitos = []
        for vaga, r in list(self.rodando.items()):
            codigo = r["proc"].poll()
            if codigo is not None:
                print(f"[coordenador] {vaga}: {r['tag']} terminou (código {codigo})", flush=True)
                self.ultima[r["tag"]] = _agora()
                feitos.append(r["tag"])
                del self.rodando[vaga]
        return feitos

    def _gravar_estado(self, db):
        vagas = [f"t{i}" for i in range(1, self.n + 1)]
        historico._definir(db, "trabalhadores", [
            {"id": v, "tag": self.rodando[v]["tag"] if v in self.rodando else None,
             "motivo": self.rodando[v]["motivo"] if v in self.rodando else None,
             "desde": self.rodando[v]["desde"] if v in self.rodando else None} for v in vagas])
        ativos = [l["tag"] for l in db.execute(estado.ATIVOS)]
        if ativos:
            import datetime
            proxima = min(self.ultima.get(t, 0) for t in ativos) + historico.intervalo()
            historico._definir(db, "proxima_rodada", datetime.datetime.fromtimestamp(
                max(proxima, _agora()), estado.FUSO).isoformat(timespec="seconds"))

    # --- uma volta -----------------------------------------------------------------
    def passo(self, db):
        """Recolhe quem terminou (e publica), faz a manutenção e põe vaults nas vagas livres."""
        feitos = self._terminados()
        ocupadas = {r["tag"] for r in self.rodando.values()}
        removidos = []
        try:
            with open(os.path.join(estado.dir_estado(), "ingestao.lock"), "w") as trava:
                fcntl.flock(trava, fcntl.LOCK_EX)
                removidos = rodada.remover_cadastros(db, pular=ocupadas)
                github_app.atualizar_lista(db)
        except Exception as e:  # noqa: BLE001 - manutenção não para o coordenador
            print(f"[coordenador] manutenção falhou: {e}", flush=True)
        if feitos or removidos:
            self.publicados.append(sorted(feitos + removidos))
            self.publicar(feitos + removidos)
        livres = [f"t{i}" for i in range(1, self.n + 1) if f"t{i}" not in self.rodando]
        for vaga, (tag, motivo) in zip(livres, self.fila(db)):
            self._iniciar(vaga, tag, motivo)
        self._gravar_estado(db)
        return feitos

    def esperar_todos(self, db, limite=600):
        fim = _agora() + limite
        while self.rodando and _agora() < fim:
            time.sleep(0.2)
            self.passo(db)


def publicar_tags(tags):
    """Base e publicação, em série, só das pastas destes vaults (curador/publicar.sh <caminhos>)."""
    py = sys.executable
    subprocess.run([py, os.path.join(CURADOR_DIR, "base.py")], check=False)
    caminhos = [f"sistemas/{t}" for t in sorted(set(tags))]
    subprocess.run(["sh", os.path.join(CURADOR_DIR, "publicar.sh"), *caminhos], check=False)


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    db = estado.conectar()
    historico.interromper(db, "*")  # o que estava aberto é de antes de o container subir
    # A tela lê daqui se há curadoria interna (o botão "Curar" só aparece com chave de API ativa).
    historico._definir(db, "curadoria", {"disponivel": curadoria.disponivel(),
                                         "provedor": os.environ.get("VAULT_CURADORIA_PROVEDOR") or
                                         ("hermes" if curadoria.disponivel() else None)})
    c = Coordenador()
    print(f"[coordenador] {c.n} trabalhador(es); fatia de {LOTES_POR_VEZ} lote(s); "
          f"agenda a cada {historico.intervalo()} s", flush=True)
    if args[:1] == ["uma-volta"]:
        c.passo(db)
        c.esperar_todos(db)
        return 0
    while True:
        try:
            c.passo(db)
        except Exception as e:  # noqa: BLE001 - o coordenador não pode cair por um erro de uma volta
            print(f"[coordenador] erro na volta: {e}", flush=True)
        time.sleep(ESPERA)


if __name__ == "__main__":
    sys.exit(main())
