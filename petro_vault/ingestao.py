"""Ingestão (DV-290): origem git → diff entre commits → filtros → fila. Sem LLM.

Roda no curador, o único container com as chaves de deploy das origens
(/opt/curador/origens/<tag>, copiadas pelo vault-init) e com a chave do GitHub
App (DV-573: origem `https://github.com/...`, lida pelo App, sem chave de deploy). A API só registra o
cadastro e os pedidos de pull; quem busca na origem é este código.

Para cada origem de cada sistema (DV-292: uma tag pode ter várias origens, e
cada origem várias leituras, cada uma com o seu perfil):
1. clone sem árvore de trabalho (bare) em estado/origens/<tag>/ (outras
   origens: estado/origens/<tag>--<origem>/) e `git fetch`
   do ramo. Sem árvore de trabalho, nenhum arquivo da origem (nem um `.env`)
   é escrito no disco como arquivo;
2. diff de <base>..<novo>, com `--find-renames`. base = commit pendente (o
   último diff já enfileirado), senão o processado, senão a árvore vazia (a
   primeira ingestão segue o mesmo caminho do pull);
3. renomeado vira removido + adicionado;
4. leitura: o arquivo vai para a primeira leitura da origem que o aceita
   (padrões de inclusão e exclusão mais os filtros fixos), e o item leva o
   perfil dela; nenhuma aceita: fica fora;
5. filtros de conteúdo (filtros.py); o que passa é mascarado e gravado em
   estado/lotes/<tag>/<origem>/<commit>/<caminho>. Só isso vai ao curador;
6. um item por arquivo na fila; o item na fila do mesmo arquivo que mudou de
   novo é substituído pelo novo;
7. commit_pendente da origem = <novo>. O processado só avança quando o
   curador registrar os itens da origem (DV-291).

Leituras editadas pela tela (DV-554): antes do diff, `reconciliar` compara a
árvore do último commit enfileirado com as leituras de antes e as de agora.
Origem removida: não há fetch; tudo o que veio dela sai do vault, e o curador
apaga o cadastro da origem quando a fila dela esvazia.

Uso: python -m petro_vault.ingestao pedidos   (só os pulls pedidos pela API)
     python -m petro_vault.ingestao todos     (todos os sistemas; a rodada)
"""
import fcntl
import json
import os
import shutil
import subprocess
import sys

from . import estado, filtros, github_app

ARVORE_VAZIA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
CHAVES_DIR = os.environ.get("VAULT_ORIGENS_CHAVES_DIR", "/opt/curador/origens")
KNOWN_HOSTS = os.environ.get("VAULT_KNOWN_HOSTS", "/opt/curador/known_hosts")


class ErroIngestao(Exception):
    pass


def _git(args, cwd=None, env=None, binario=False):
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True)
    if r.returncode != 0:
        raise ErroIngestao(f"git {args[0]}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binario else r.stdout.decode()


def _ambiente(nome, repo=None):
    app = github_app.do_app(repo)
    if app:
        try:
            return {**os.environ, **github_app.ambiente_git(*app)}
        except github_app.ErroGitHub as e:
            raise ErroIngestao(str(e)) from None
    chave = os.path.join(CHAVES_DIR, nome)
    if not os.path.isfile(chave):
        raise ErroIngestao(f"chave de deploy da origem não encontrada: {chave}")
    env = dict(os.environ)
    env["GIT_SSH_COMMAND"] = (f"ssh -i {chave} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
                              f"-o UserKnownHostsFile={KNOWN_HOSTS}")
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def dir_clone(tag, origem):
    return os.path.join(estado.dir_estado(), "origens", estado.nome_clone(tag, origem))


def buscar_origem(tag, origem, repo, ramo):
    """Clone (bare) ou fetch do ramo. Devolve (dir do clone, commit novo)."""
    from . import envios
    destino = dir_clone(tag, origem)
    if repo.startswith(envios.REPO + ":"):
        repo, env = envios.repositorio(repo), None
    else:
        env = _ambiente(estado.nome_clone(tag, origem), repo)
    if not os.path.isdir(os.path.join(destino, "objects")):
        shutil.rmtree(destino, ignore_errors=True)
        os.makedirs(destino)
        _git(["init", "-q", "--bare", destino])
        _git(["remote", "add", "origin", repo], cwd=destino)
    else:
        _git(["remote", "set-url", "origin", repo], cwd=destino)
    try:
        _git(["fetch", "-q", "--prune", "origin", f"+refs/heads/{ramo}:refs/remotes/origin/{ramo}"], cwd=destino, env=env)
    except ErroIngestao as e:
        if "couldn't find remote ref" in str(e):
            raise ErroIngestao(f"o ramo {ramo} não existe no repositório") from None
        raise
    novo = _git(["rev-parse", f"refs/remotes/origin/{ramo}^{{commit}}"], cwd=destino).strip()
    return destino, novo


def _existe(clone, commit):
    return subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=clone,
                          capture_output=True).returncode == 0


def diff(clone, base, novo):
    """Itens do diff base..novo: lista de (acao, caminho, blob, modo).
    Renomeado vira removido + adicionado; cópia, adicionado."""
    saida = _git(["diff", "--raw", "-z", "--no-abbrev", "--find-renames", base, novo], cwd=clone, binario=True)
    campos = saida.decode("utf-8", errors="surrogateescape").split("\0")
    itens, i = [], 0
    while i < len(campos) and campos[i]:
        _modo_a, modo_b, _blob_a, blob_b, status = campos[i].lstrip(":").split(" ")
        letra = status[0]
        if letra in "RC":
            antigo, novo_caminho = campos[i + 1], campos[i + 2]
            i += 3
            if letra == "R":
                itens.append(("removido", antigo, None, None))
            itens.append(("adicionado", novo_caminho, blob_b, modo_b))
            continue
        caminho = campos[i + 1]
        i += 2
        acao = {"A": "adicionado", "D": "removido"}.get(letra, "modificado")  # M, T
        itens.append((acao, caminho, None if acao == "removido" else blob_b, None if acao == "removido" else modo_b))
    return itens


def arquivos_no_commit(tag, origem, commit):
    """Caminhos que existem na origem naquele commit (None se não há clone)."""
    r = subprocess.run(["git", "ls-tree", "-r", "--name-only", "-z", commit], cwd=dir_clone(tag, origem),
                       capture_output=True)
    if r.returncode != 0:
        return None
    return set(r.stdout.decode("utf-8", errors="surrogateescape").split("\0")) - {""}


def _registrar_acesso(db, tag, origem, ok, erro=None):
    """Estado de acesso de cada origem, para a tela (DV-547)."""
    with db:
        db.execute("UPDATE origens SET acesso_ok = ?, acesso_em = ?, acesso_erro = ? WHERE tag = ? AND nome = ?",
                   (1 if ok else 0, estado.agora(), erro, tag, origem))


def atualizar_commits(db, tag, origem):
    """Datas dos commits processado e pendente e quantos commits o vault está
    atrás da origem (o que já foi buscado), para a tela. Sem clone: não mexe."""
    o = db.execute("SELECT * FROM origens WHERE tag = ? AND nome = ?", (tag, origem)).fetchone()
    clone = dir_clone(tag, origem)
    if not o or not o["commit_pendente"] or not os.path.isdir(os.path.join(clone, "objects")):
        return

    def data(commit):
        r = subprocess.run(["git", "show", "-s", "--format=%cI", commit], cwd=clone, capture_output=True, text=True)
        return r.stdout.strip() or None if r.returncode == 0 else None

    intervalo = f"{o['commit_processado']}..{o['commit_pendente']}" if o["commit_processado"] else o["commit_pendente"]
    r = subprocess.run(["git", "rev-list", "--count", intervalo], cwd=clone, capture_output=True, text=True)
    atras = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None
    with db:
        db.execute("UPDATE origens SET commits_atras = ?, data_pendente = ?, data_processado = ? "
                   "WHERE tag = ? AND nome = ?",
                   (atras, data(o["commit_pendente"]), data(o["commit_processado"]) if o["commit_processado"] else None,
                    tag, origem))


# DV-608: "código + cópia literal" é, para a fila e o curador, o perfil código; a cópia em referencia/
# é do código, a cada rodada (literal.copiar_codigo). Trocar código ↔ código + cópia não enfileira nada.
CODIGO_LITERAL = "codigo-literal"


def leitura_de(caminho, leituras, cru=False):
    """(perfil, None) da primeira leitura que aceita o caminho, ou (None, motivo).
    Sem `cru`, codigo-literal sai como codigo (o perfil da fila e do curador)."""
    motivo = "nenhuma leitura"
    for l in leituras:
        motivo = filtros.por_caminho(caminho, l.get("incluir") or [], l.get("excluir") or [])
        if not motivo:
            return ("codigo" if l["perfil"] == CODIGO_LITERAL and not cru else l["perfil"]), None
    return None, motivo


def _gravar_lote(tag, origem, novo, caminho, texto):
    raiz = os.path.join(estado.dir_estado(), "lotes")
    rel = os.path.join(tag, origem, novo[:12], caminho)
    alvo = os.path.normpath(os.path.join(raiz, rel))
    if not alvo.startswith(os.path.join(raiz, tag) + os.sep):
        raise ErroIngestao(f"caminho fora do lote: {caminho}")
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    with open(alvo, "w", encoding="utf-8") as f:
        f.write(texto)
    return rel


def _apagar_lote(rel):
    if rel:
        try:
            os.remove(os.path.join(estado.dir_estado(), "lotes", rel))
        except FileNotFoundError:
            pass


def _item(clone, tag, nome, commit, acao, caminho, blob, modo, perfil, resumo):
    """Filtros de conteúdo de um arquivo que entra (adicionado ou modificado):
    o item da fila (acao, caminho, perfil, lote, motivo), ou None se fica fora."""
    if modo in ("120000", "160000"):
        texto, motivo = None, "link simbólico ou submódulo"
    else:
        tamanho = int(_git(["cat-file", "-s", blob], cwd=clone))
        if tamanho > filtros.LIMITE_BYTES:
            texto, motivo = None, f"acima de {filtros.LIMITE_BYTES} bytes"
        else:
            texto, motivo = filtros.por_conteudo(_git(["cat-file", "blob", blob], cwd=clone, binario=True))
    if motivo:
        resumo["ignorados"].append({"origem": nome, "caminho": caminho, "motivo": motivo})
        if acao == "modificado":
            # Já esteve no vault: o curador precisa tirar o que veio dele.
            return ("removido", caminho, perfil, None, f"deixou de passar no filtro: {motivo}")
        return None
    texto, n = filtros.mascarar(texto)
    resumo["mascarados"] += n
    lote = _gravar_lote(tag, nome, commit, caminho, texto)
    return (acao, caminho, perfil, lote, f"{n} valor(es) mascarado(s)" if n else None)


def _enfileirar(db, tag, nome, commit, novos, resumo):
    """Itens na fila. O item na fila do mesmo arquivo e do mesmo perfil sai
    (substituido). Um arquivo que mudou de leitura (DV-554) tem um item em
    cada perfil: o removido da leitura antiga não é substituído pelo da nova."""
    criado, vistos, sobras = estado.agora(), set(), set()
    with db:
        for acao, caminho, perfil, lote, motivo in novos:
            chave = (tag, nome, caminho, perfil)
            if chave not in vistos:
                vistos.add(chave)
                for a in db.execute("SELECT id, lote, acao FROM fila WHERE tag = ? AND origem = ? AND caminho = ? "
                                    "AND perfil = ? AND estado = 'na_fila'", chave).fetchall():
                    if a["lote"] and a["lote"] != lote:
                        sobras.add(a["lote"])
                    if a["acao"] == "adicionado" and acao == "modificado":
                        acao = "adicionado"  # ainda não chegou ao vault: continua novo
                db.execute("UPDATE fila SET estado = 'substituido' WHERE tag = ? AND origem = ? AND caminho = ? "
                           "AND perfil = ? AND estado = 'na_fila'", chave)
            db.execute("INSERT INTO fila (tag, origem, perfil, acao, caminho, commit_origem, lote, motivo, criado_em) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (tag, nome, perfil, acao, caminho, commit, lote, motivo, criado))
            resumo["itens"][acao] = resumo["itens"].get(acao, 0) + 1
    # O arquivo do lote não tem o perfil no caminho: o item que sai pode
    # dividir o arquivo com o de outro perfil (DV-554, 27/10: o removido de
    # código apagava o arquivo do adicionado de documentos e a rodada caía).
    for rel in sobras:
        if not db.execute("SELECT 1 FROM fila WHERE lote = ? AND estado = 'na_fila'", (rel,)).fetchone():
            _apagar_lote(rel)


def restaurar_lote(tag, item):
    """Refaz o arquivo do lote de um item que perdeu o seu, a partir do clone.
    Devolve None se refez, ou o motivo de não conseguir."""
    clone = dir_clone(tag, item["origem"])
    try:
        dados = _git(["cat-file", "blob", f"{item['commit_origem']}:{item['caminho']}"], cwd=clone, binario=True)
    except ErroIngestao as e:
        return f"arquivo do lote sumiu e não está no clone: {e}"
    texto, motivo = filtros.por_conteudo(dados)
    if motivo:
        return f"arquivo do lote sumiu e não passa mais no filtro: {motivo}"
    if _gravar_lote(tag, item["origem"], item["commit_origem"], item["caminho"], filtros.mascarar(texto)[0]) != item["lote"]:
        return "arquivo do lote sumiu e o caminho refeito não bate"
    return None


def arvore(clone, commit):
    """(caminho, blob, modo) de cada arquivo do commit."""
    saida = _git(["ls-tree", "-r", "-z", "--full-tree", commit], cwd=clone, binario=True)
    for linha in saida.decode("utf-8", errors="surrogateescape").split("\0"):
        if linha:
            meta, caminho = linha.split("\t", 1)
            modo, _tipo, blob = meta.split(" ")
            yield caminho, blob, modo


def reconciliar(db, tag, origem, clone, resumo):
    """Leituras mudaram (DV-554): na árvore do último commit enfileirado, cada
    arquivo cujo perfil mudou entre as leituras de antes e as de agora sai da
    leitura antiga (removido, o curador tira o que veio dele) e entra na nova
    (adicionado). Arquivo que nunca chegou ao vault vira um removido que o
    código resolve sem LLM. Origem removida: as leituras de agora são []."""
    nome = origem["nome"]
    antes, agora = json.loads(origem["leituras_antes"]), json.loads(origem["leituras"])
    base = origem["commit_pendente"] or origem["commit_processado"]
    novos = []
    if base and os.path.isdir(os.path.join(clone, "objects")) and _existe(clone, base):
        for caminho, blob, modo in arvore(clone, base):
            de, _ = leitura_de(caminho, antes)
            para, motivo = leitura_de(caminho, agora)
            if de == para:
                continue
            if de:
                novos.append(("removido", caminho, de, None, f"saiu da leitura {de}" + (f" para {para}" if para else "")))
            if para:
                item = _item(clone, tag, nome, base, "adicionado", caminho, blob, modo, para, resumo)
                if item:
                    novos.append(item)
            else:
                resumo["ignorados"].append({"origem": nome, "caminho": caminho, "motivo": motivo})
    _enfileirar(db, tag, nome, base, novos, resumo)
    with db:
        db.execute("UPDATE origens SET leituras_antes = NULL WHERE tag = ? AND nome = ?", (tag, nome))
    resumo["origens"].setdefault(nome, {})["reconciliados"] = len(novos)
    print(f"[ingestao] {tag}: leituras de {nome} mudaram: {len(novos)} item(ns) de reconciliação")


def ingerir_origem(db, tag, origem, resumo):
    """Uma ingestão de uma origem; acumula em `resumo` (vai para pulls.resultado)."""
    nome, leituras = origem["nome"], json.loads(origem["leituras"])
    if origem["removida_em"]:  # sem fetch: só tira do vault o que veio dela
        resumo["origens"][nome] = {"removida": True}
        if origem["leituras_antes"] is not None:
            reconciliar(db, tag, origem, dir_clone(tag, nome), resumo)
        return
    try:
        clone, novo = buscar_origem(tag, nome, origem["repo"], origem["ramo"])
    except ErroIngestao as e:
        _registrar_acesso(db, tag, nome, False, str(e))
        raise
    _registrar_acesso(db, tag, nome, True)
    r = resumo["origens"][nome] = {"para": novo}
    if origem["leituras_antes"] is not None:
        reconciliar(db, tag, origem, clone, resumo)

    base = None
    for candidato in (origem["commit_pendente"], origem["commit_processado"]):
        if candidato and _existe(clone, candidato):
            base = candidato
            break
        if candidato:
            r["aviso"] = f"commit {candidato[:12]} não existe mais na origem (force push?); diff a partir do anterior"
    base = base or ARVORE_VAZIA
    r["de"] = base
    if base == novo:
        r["nada_novo"] = True
        return

    novos = []  # (acao, caminho, perfil, lote, motivo)
    for acao, caminho, blob, modo in diff(clone, base, novo):
        perfil, motivo = leitura_de(caminho, leituras)
        if motivo:
            if acao != "removido":
                resumo["ignorados"].append({"origem": nome, "caminho": caminho, "motivo": motivo})
            continue
        if acao == "removido":
            novos.append((acao, caminho, perfil, None, None))
            continue
        item = _item(clone, tag, nome, novo, acao, caminho, blob, modo, perfil, resumo)
        if item:
            novos.append(item)

    _enfileirar(db, tag, nome, novo, novos, resumo)
    with db:
        db.execute("UPDATE origens SET commit_pendente = ? WHERE tag = ? AND nome = ?", (novo, tag, nome))
    atualizar_commits(db, tag, nome)


def ingerir(db, sistema):
    """Uma ingestão de todas as origens de um sistema. Com uma origem só, `de`,
    `para`, `nada_novo` e `aviso` também ficam no topo do resumo."""
    tag = sistema["tag"]
    resumo = {"tag": tag, "itens": {}, "ignorados": [], "mascarados": 0, "origens": {}}
    origens = db.execute("SELECT * FROM origens WHERE tag = ? ORDER BY id", (tag,)).fetchall()
    for origem in origens:
        try:
            ingerir_origem(db, tag, origem, resumo)
        except ErroIngestao as e:
            resumo["origens"][origem["nome"]] = {"erro": str(e)}
    if len(origens) == 1:
        unica = resumo["origens"][origens[0]["nome"]]
        if "erro" in unica:
            raise ErroIngestao(unica["erro"])
        resumo.update({k: v for k, v in unica.items() if k in ("de", "para", "nada_novo", "aviso")})
    return resumo


def _atender(db, tags):
    """Ingere cada tag uma vez e fecha os pedidos de pull pendentes dela."""
    estado.migrar_origens(db)  # sistema gravado sem origens (API antiga) ganha a principal
    for tag in tags:
        sistema = db.execute("SELECT * FROM sistemas WHERE tag = ?", (tag,)).fetchone()
        try:
            if not sistema:
                raise ErroIngestao("sistema não cadastrado")
            resumo = ingerir(db, sistema)
        except ErroIngestao as e:
            resumo = {"tag": tag, "erro": str(e)}
        with db:
            db.execute("UPDATE pulls SET atendido_em = ?, resultado = ? WHERE tag = ? AND atendido_em IS NULL",
                       (estado.agora(), json.dumps(resumo, ensure_ascii=False), tag))
        if "erro" in resumo:
            print(f"[ingestao] {tag}: erro: {resumo['erro']}")
            continue
        itens = ", ".join(f"{n} {a}" for a, n in resumo["itens"].items()) or "nenhum item"
        commits = "; ".join(f"{o}: {r['erro']}" if "erro" in r else f"{o}: removida" if r.get("removida") else
                            f"{o} {r['de'][:12]}..{r['para'][:12]}" + (f" ({r['aviso']})" if "aviso" in r else "")
                            for o, r in resumo["origens"].items())
        print(f"[ingestao] {tag}: {commits}: {itens}, {len(resumo['ignorados'])} ignorado(s), "
              f"{resumo['mascarados']} mascarado(s)")


def main(argv=None):
    modo = (argv or sys.argv[1:] or ["pedidos"])[0]
    if modo not in ("pedidos", "todos"):
        sys.exit(__doc__)
    db = estado.conectar()
    # Uma ingestão por vez (a rodada e os pedidos rodam no mesmo container).
    with open(os.path.join(estado.dir_estado(), "ingestao.lock"), "w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        if modo == "todos":
            tags = [l["tag"] for l in db.execute(estado.ATIVOS)]
        else:
            tags = [l["tag"] for l in db.execute("SELECT DISTINCT tag FROM pulls WHERE atendido_em IS NULL ORDER BY tag")]
        _atender(db, tags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
