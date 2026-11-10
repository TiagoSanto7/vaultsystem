"""Índices e verificador por tag, sem LLM. Rodam depois da curadoria.

Índices (refeitos inteiros): sistemas/<tag>/indices/documentos.md e
assuntos.md (perfil documentos) e codigo.md (perfil codigo), cada um só se a
tag tem notas daquele perfil.

Verificador: lista o que está errado, não corrige nada. Grava em
sistemas/<tag>/_meta/verificacao.md e sai com código 1 se houver problema
(o ciclo registra e segue).
- cabeçalho: sistema igual à tag, tipo_nota da pasta, origens, commit_origem,
  criado_em e atualizado_em;
- links: [[...]] e evidências que não apontam para nota existente, ou que
  apontam para outra tag (fora do MVP);
- órfãs: documento que nenhum assunto cita; assunto sem evidência;
- origens: arquivo em `origens` que não existe no commit da origem (o último
  ingerido), conferido no clone de cada origem;
- segredos: texto com cara de token, senha ou chave numa nota (os
  mesmos padrões da máscara da ingestão). A ingestão já mascara a origem;
  isto pega o que o curador possa ter escrito de outro jeito.
"""
import hashlib
import json
import os
import re
import sys

from . import estado, filtros, infra, ingestao, literal, notas
from .curadoria import PASTAS, PERFIS

OBRIGATORIOS = ("sistema", "tipo_nota", "origens", "commit_origem", "criado_em", "atualizado_em")


DATA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")


def _gravar_se_mudou(caminho, texto):
    """Grava só se mudou algo além da data de geração: sem isso, cada rodada
    viraria um commit no vault mesmo sem nada novo."""
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            if DATA.sub("", f.read()) == DATA.sub("", texto):
                return
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


def _escrever(tag, nome, titulo, linhas):
    _gravar_se_mudou(os.path.join(notas.pasta_tag(tag), "indices", nome),
                     f"# {titulo}\n\nGerado pelo código em {estado.agora()}. Não editar à mão.\n\n"
                     + "\n".join(linhas) + "\n")


def indices(tag):
    docs = notas.todas(tag, ("documentos",))
    assuntos = notas.todas(tag, ("assuntos",))
    if docs or assuntos:
        citado = {k: [] for k in docs}
        linhas_a = ["| Assunto | Documentos |", "| --- | --- |"]
        for chave, c in sorted(assuntos.items()):
            cab, corpo = notas.ler(c)
            evid = sorted(a for a in notas.links_de(cab, corpo) if a in docs)
            for a in evid:
                citado[a].append(chave)
            linhas_a.append(f"| [[{chave}]] {notas.titulo(corpo)} | {len(evid)} |")
        linhas_d = ["| Documento | Tipo | Origem | Assuntos |", "| --- | --- | --- | --- |"]
        for chave, c in sorted(docs.items()):
            cab, corpo = notas.ler(c)
            origem = ", ".join(f"`{o}`" for o in cab.get("origens") or [])
            linhas_d.append(f"| [[{chave}]] {notas.titulo(corpo)} | {cab.get('origem_tipo') or ''} | {origem} | "
                            f"{len(citado[chave])} |")
        _escrever(tag, "documentos.md", f"Documentos de {tag}", linhas_d)
        _escrever(tag, "assuntos.md", f"Assuntos de {tag}", linhas_a)
    codigo = notas.todas(tag, PERFIS["codigo"])
    # Só é índice de código se o vault tem notas de código de verdade (regras sozinhas podem ser de qualquer assunto).
    if not any(k.split("/")[2] in ("modulos", "integracoes", "apis", "dados", infra.PASTA) for k in codigo):
        codigo = {}
        velho = os.path.join(notas.pasta_tag(tag), "indices", "codigo.md")
        if os.path.exists(velho):
            os.remove(velho)
    if codigo:
        linhas = []
        for pasta in PERFIS["codigo"]:
            grupo = {k: c for k, c in codigo.items() if k.split("/")[2] == pasta}
            if not grupo:
                continue
            linhas += [f"## {pasta}", "", "| Nota | Arquivos de origem |", "| --- | --- |"]
            for chave, c in sorted(grupo.items()):
                cab, corpo = notas.ler(c)
                linhas.append(f"| [[{chave}]] {notas.titulo(corpo)} | {len(cab.get('origens') or [])} |")
            linhas.append("")
        _escrever(tag, "codigo.md", f"Código de {tag}", linhas)
    print(f"[indices] {tag}: documentos {len(docs)}; assuntos {len(assuntos)}; notas de código {len(codigo)}")


def gravar_problemas(db, tag, erros, commits):
    """Problemas no banco, para a tela; `desde` fica com a primeira
    vez que o problema apareceu, e o que sumiu sai."""
    agora = estado.agora()
    chaves = {}
    for tipo, nota, texto in erros:
        chaves[hashlib.sha1(f"{tipo}|{texto}".encode()).hexdigest()] = (tipo, nota, texto)
    with db:
        antigos = {l["chave"] for l in db.execute("SELECT chave FROM problemas WHERE tag = ?", (tag,))}
        for chave in antigos - set(chaves):
            db.execute("DELETE FROM problemas WHERE tag = ? AND chave = ?", (tag, chave))
        for chave, (tipo, nota, texto) in chaves.items():
            if chave not in antigos:
                db.execute("INSERT INTO problemas (tag, chave, tipo, nota, detalhe, desde) VALUES (?, ?, ?, ?, ?, ?)",
                           (tag, chave, tipo, nota, texto, agora))
        db.execute("INSERT INTO verificacoes (tag, rodou_em, commits, total) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(tag) DO UPDATE SET rodou_em = excluded.rodou_em, commits = excluded.commits, "
                   "total = excluded.total", (tag, agora, json.dumps(commits), len(chaves)))


def indexar(db, tag):
    """Índice das notas da tag, mais o registro e os conflitos, no banco: a
    API lê daqui e não monta o vault. Refeito inteiro a cada rodada."""
    todas = notas.todas(tag, PASTAS)
    todas.update(notas.todas(tag, ("indices",)))
    with db:
        db.execute("DELETE FROM notas_indice WHERE tag = ?", (tag,))
        for chave, c in todas.items():
            with open(c, encoding="utf-8") as f:
                texto = f.read()
            cab, corpo = notas.separar(texto)
            db.execute("INSERT INTO notas_indice (tag, chave, pasta, titulo, tipo_nota, origens, commit_origem, "
                       "criado_em, atualizado_em, conteudo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (tag, chave, chave.split("/")[2], notas.titulo(corpo, chave.rsplit("/", 1)[-1]),
                        cab.get("tipo_nota"), json.dumps(cab.get("origens") or [], ensure_ascii=False),
                        cab.get("commit_origem"), cab.get("criado_em"), cab.get("atualizado_em"), texto))
        for nome in ("registro", "conflitos"):
            c = os.path.join(notas.pasta_tag(tag), "_meta", f"{nome}.md")
            if os.path.exists(c):
                with open(c, encoding="utf-8") as f:
                    db.execute("INSERT INTO meta_tag (tag, nome, conteudo) VALUES (?, ?, ?) ON CONFLICT(tag, nome) "
                               "DO UPDATE SET conteudo = excluded.conteudo", (tag, nome, f.read()))
    print(f"[indices] {tag}: {len(todas)} nota(s) no índice do banco")


def verificar(db, tag):
    todas = notas.todas(tag, PASTAS)
    indices_ = notas.todas(tag, ("indices", "_meta"))  # índices, registro e conflitos também são alvo válido
    commits = {o["nome"]: o["commit_pendente"] or o["commit_processado"]
               for o in db.execute("SELECT * FROM origens WHERE tag = ?", (tag,))}
    na_origem = {o: ingestao.arquivos_no_commit(tag, o, c) if c else None for o, c in commits.items()}

    erros, citados = [], set()
    servicos_infra = None  # lido só se houver nota de infra
    for chave, c in todas.items():
        cab, corpo = notas.ler(c)
        pasta = chave.split("/")[2]
        faltando = [k for k in OBRIGATORIOS if not cab.get(k)]
        if faltando:
            erros.append(("cabecalho", chave, f"cabeçalho sem {', '.join(faltando)}: `{chave}`"))
        if cab.get("sistema") and cab.get("sistema") != tag:
            erros.append(("sistema_errado", chave, f"cabeçalho com sistema `{cab.get('sistema')}` (devia ser `{tag}`): `{chave}`"))
        if cab.get("tipo_nota") and cab.get("tipo_nota") != PASTAS[pasta]:
            erros.append(("tipo_nota_errado", chave, f"tipo_nota `{cab.get('tipo_nota')}` em {pasta}/: `{chave}`"))
        if pasta == literal.PASTA:
            # Nota literal: o texto é o da origem, como está; links e
            # assuntos não são do vault. Só confere se ninguém editou a nota.
            problema = literal.conferir(chave, cab, corpo)
            if problema:
                erros.append(problema)
            alvos = set()
        else:
            alvos = notas.links_de(cab, corpo)
            if pasta in literal.PASTAS_COM_TRECHO:
                erros += literal.conferir_guia(tag, chave, corpo)
            if pasta == infra.PASTA and chave.rsplit("/", 1)[1] != infra.VISAO_GERAL:
                if servicos_infra is None:
                    servicos_infra = set(infra.ler_tag(db, tag)["servicos"])
                if chave.rsplit("/", 1)[1] not in servicos_infra:
                    erros.append(("infra_sem_servico", chave, f"nota de infra de um serviço que não existe nos "
                                                               f"arquivos de container: `{chave}`"))
        for alvo in alvos:
            if alvo in todas or alvo in indices_:
                if pasta == "assuntos":
                    citados.add(alvo)
            elif alvo.startswith("sistemas/") and not alvo.startswith(f"sistemas/{tag}/"):
                erros.append(("link_outra_tag", chave, f"link para outra tag (fora do MVP): `{chave}` → `{alvo}`"))
            else:
                erros.append(("link_quebrado", chave, f"link quebrado: `{chave}` → `{alvo}`"))
        if pasta == "assuntos" and not any(a.startswith(f"sistemas/{tag}/documentos/") for a in alvos):
            erros.append(("assunto_sem_documento", chave, f"assunto sem documento como evidência: `{chave}`"))
        for o in cab.get("origens") or []:
            nome, caminho = estado.separar_ref(o)
            if nome not in na_origem:
                erros.append(("origem_nao_cadastrada", chave, f"origem `{nome}` não cadastrada: `{chave}` → `{o}`"))
            elif na_origem[nome] is not None and caminho not in na_origem[nome]:
                erros.append(("origem_sumiu", chave, f"origem que não existe mais no commit {commits[nome][:12]}: `{chave}` → `{o}`"))
        with open(c, encoding="utf-8") as f:
            # O marcador de trecho é um caminho com linhas (`tokens/tokens.json:L1-L9`), não atribuição.
            texto = re.sub(r"^<!-- trecho: \S+ -->[ \t]*$", "", f.read(), flags=re.M)
        if filtros.mascarar(texto)[1] or filtros.CHAVE_PRIVADA.search(texto):
            erros.append(("possivel_segredo", chave, f"possível segredo no texto (padrão de token, senha ou chave): `{chave}`"))
    for chave in todas:
        if chave.split("/")[2] == "documentos" and chave not in citados:
            erros.append(("documento_orfao", chave, f"documento órfão (nenhum assunto cita): `{chave}`"))

    erros = sorted(set(erros), key=lambda e: e[2])
    gravar_problemas(db, tag, erros, commits)
    linhas = ["# Verificação", "",
              f"Tag `{tag}`. Última verificação: {estado.agora()}. Notas conferidas: {len(todas)}. "
              "Commits das origens: " + (", ".join(f"{o} `{(c or 'nenhum')[:12]}`" for o, c in commits.items())
                                         or "nenhuma origem")
              + ("" if all(v is not None for v in na_origem.values()) else
                 " (alguma origem sem clone ou sem commit: arquivos dela não conferidos)") + ".", ""]
    linhas += [f"- {e[2]}" for e in erros] if erros else ["Nenhum problema encontrado."]
    _gravar_se_mudou(os.path.join(notas.pasta_tag(tag), "_meta", "verificacao.md"), "\n".join(linhas) + "\n")
    print(f"[verificar] {tag}: notas {len(todas)}; problemas {len(erros)}")
    for e in erros[:10]:
        print(f"[verificar]   {e[2]}")
    return [e[2] for e in erros]


def main(argv=None):
    """python -m vault_system.verificacao [<tag> ...]   (sem tag: todas com curador)"""
    tags = argv if argv is not None else sys.argv[1:]
    db = estado.conectar()
    problemas = 0
    for s in db.execute("SELECT tag FROM sistemas WHERE removido_em IS NULL ORDER BY tag").fetchall():
        if tags and s["tag"] not in tags:
            continue
        if not os.path.isdir(notas.pasta_tag(s["tag"])):
            continue
        indices(s["tag"])
        problemas += len(verificar(db, s["tag"]))
        indexar(db, s["tag"])
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
