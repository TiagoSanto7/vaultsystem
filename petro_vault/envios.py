"""Snapshots enviados pelo painel ou pela CLI, consumidos como origens locais."""
import io
import json
import os
import re
import stat
import subprocess
import uuid
import zipfile

from . import estado, filtros, templates

MAXIMO = 10 * 1024 * 1024
ORIGEM = "envio-local"
REPO = "vault-system:upload"


def repositorio(origem):
    chave = origem.removeprefix(REPO + ":")
    if not re.fullmatch(r"[0-9a-f]{32}", chave):
        raise ValueError("Origem de envio inválida.")
    return os.path.abspath(os.path.join(estado.dir_estado(), "envios", chave + ".git"))


def _arquivos(pacote):
    itens = {}
    nomes = set()
    tamanho = 0
    with zipfile.ZipFile(io.BytesIO(pacote)) as z:
        for info in z.infolist():
            nome = info.filename.rstrip("/")
            partes = nome.split("/")
            if (any(not p or p in (".", "..") or p.endswith((".", " "))
                    or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", p.split(".")[0])
                    or re.search(r'[\\:*?"<>|\x00-\x1f]', p) for p in partes)
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError(f"Caminho inválido no pacote: {nome}")
            if info.is_dir() or filtros.por_caminho(nome, [], []) or any(
                p.casefold() in {".git", ".vs", "vs.lock", ".vaultsystem", ".petrovault"} for p in partes
            ):
                continue
            if info.flag_bits & 1:
                raise ValueError("O ZIP não pode estar protegido por senha.")
            if nome.casefold() in nomes:
                raise ValueError(f"Caminho duplicado no pacote: {nome}")
            nomes.add(nome.casefold())
            tamanho += info.file_size
            if len(itens) >= 2000 or tamanho > MAXIMO:
                raise ValueError("O pacote expandido excede 10 MB ou 2.000 arquivos.")
            dados = z.read(info)
            motivo = templates._conferir(nome, dados)
            if motivo and motivo != "pular":
                raise ValueError(f"Arquivo bloqueado: {nome} ({motivo}).")
            itens[nome] = (dados, "100755" if (info.external_attr >> 16) & stat.S_IXUSR else "100644")
    if not itens:
        raise ValueError("O pacote não contém arquivos aceitos.")
    for nome in nomes:
        partes = nome.split("/")
        if any("/".join(partes[:i]) in nomes for i in range(1, len(partes))):
            raise ValueError("O pacote usa o mesmo caminho para arquivo e pasta.")
    return itens


def _git(repo, *args, dados=None, conferir=True):
    r = subprocess.run(["git", "--git-dir", repo, *args], input=dados, capture_output=True, timeout=30,
                       env={**os.environ, "GIT_AUTHOR_NAME": "Vault System", "GIT_AUTHOR_EMAIL": "vault@localhost",
                            "GIT_COMMITTER_NAME": "Vault System", "GIT_COMMITTER_EMAIL": "vault@localhost"})
    if conferir and r.returncode:
        raise RuntimeError("Não foi possível gravar a revisão do pacote.")
    return r.stdout.strip().decode("ascii") if not r.returncode else None


def gravar(tag, pacote, por, modo=None):
    """Cria o vault quando modo é informado, ou atualiza sua origem de envio."""
    if not estado.TAG.fullmatch(tag):
        raise ValueError("Nome de vault inválido.")
    if len(pacote) > MAXIMO or modo not in (None, "literal", "documentado"):
        raise ValueError("Pacote maior que 10 MB ou modo inválido.")
    itens = _arquivos(pacote)
    if tag.startswith(templates.PREFIXO) and not any("/" in nome for nome in itens):
        raise ValueError("Coloque os arquivos dentro de uma pasta por template no ZIP.")
    perfil = "referencia" if modo == "literal" else "codigo-literal"
    leituras = json.dumps([{"perfil": perfil, "incluir": [], "excluir": []}])
    with estado.conectar() as db:
        db.execute("BEGIN IMMEDIATE")
        existente = db.execute("SELECT removido_em FROM sistemas WHERE tag = ?", (tag,)).fetchone()
        if modo is not None and existente:
            raise FileExistsError("Já existe um vault com esse nome.")
        if modo is None:
            origem = db.execute("SELECT repo FROM origens WHERE tag = ? AND nome = ? AND repo LIKE ? AND removida_em IS NULL",
                                (tag, ORIGEM, REPO + ":%")).fetchone()
            if not existente or existente["removido_em"] or not origem:
                raise LookupError("Crie no painel um vault com origem por envio antes de sincronizar.")
        identificador = REPO + ":" + uuid.uuid4().hex if modo is not None else origem["repo"]
        repo = repositorio(identificador)
        os.makedirs(os.path.dirname(repo), exist_ok=True)
        if not os.path.isfile(os.path.join(repo, "HEAD")):
            _git(repo, "init", "--bare", "--quiet")
        entradas = []
        for nome, (dados, permissao) in sorted(itens.items()):
            blob = _git(repo, "hash-object", "-w", "--stdin", dados=dados)
            entradas.append(f"{permissao} {blob}\t{nome}\0".encode())
        _git(repo, "read-tree", "--empty")
        _git(repo, "update-index", "-z", "--index-info", dados=b"".join(entradas))
        arvore = _git(repo, "write-tree")
        anterior = _git(repo, "rev-parse", "--verify", "refs/heads/main", conferir=False)
        if anterior and _git(repo, "rev-parse", anterior + "^{tree}") == arvore:
            commit = anterior
        else:
            pais = ["-p", anterior] if anterior else []
            commit = _git(repo, "commit-tree", arvore, *pais, "-m", "Sincroniza pacote Vault System")
            _git(repo, "update-ref", "refs/heads/main", commit)
        if modo is not None:
            agora = estado.agora()
            db.execute("INSERT INTO sistemas (tag, perfil, repo, ramo, incluir, excluir, criado_em, criado_por) "
                       "VALUES (?, ?, ?, 'main', '[]', '[]', ?, ?)", (tag, perfil, identificador, agora, por))
            db.execute("INSERT INTO origens (tag, nome, repo, ramo, leituras, criado_em) "
                       "VALUES (?, ?, ?, 'main', ?, ?)", (tag, ORIGEM, identificador, leituras, agora))
        db.execute("INSERT INTO pulls (tag, pedido_em, pedido_por) VALUES (?, ?, ?)",
                   (tag, estado.agora(), por))
    return {"tag": tag, "commit": commit, "arquivos": len(itens)}
