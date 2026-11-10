"""Notas preparadas pelo agente local (Vault System), importadas como curadas, sem LLM no hub.

O `vs init` deixa no AGENTS.md do projeto o protocolo: o agente que trabalha no
repositório escreve notas em Markdown com um cabeçalho `vs:` e o `vs sync` manda
o projeto inteiro para o hub. Num vault no modo documentado, a cada rodada o
código lê o snapshot processado e copia cada nota dessas para a pasta do tipo
dela, com o cabeçalho do vault (sistema, tipo_nota, origens, commit, datas) e
`curada_por: agente`. O arquivo continua também como cópia literal em
`referencia/`, como todo arquivo do snapshot.

Formato no projeto (qualquer caminho terminado em .md):

    ---
    vs: regra                    # o tipo: veja TIPOS
    titulo: Desconto máximo      # opcional; senão, o primeiro # do corpo
    origens:                     # arquivos do projeto que a nota explica
      - app/precos.py
    ---
    # Desconto máximo
    ...

`origens` são caminhos a partir da raiz do projeto. Num vault de template, a
pasta do template também vale como raiz (`tokens/cores.css` dentro de
`default/` acha `default/tokens/cores.css`). Origem que não existe no snapshot
sai da nota, com aviso. Sem nenhuma origem válida, a origem é a própria nota.
"""
import os
import posixpath
import re

from . import estado, filtros, historico, ingestao, literal, notas

# tipo no cabeçalho do agente -> (pasta no vault, tipo_nota)
TIPOS = {
    "conceito": ("conceitos", "conceito"), "definicao": ("conceitos", "conceito"),
    "nota": ("notas", "nota"), "documento": ("notas", "nota"),
    "decisao": ("decisoes", "decisao"),
    "elemento": ("elementos", "elemento"), "componente": ("elementos", "elemento"),
    "regra": ("regras", "regra"),
    "orientacao": ("orientacoes", "orientacao"), "guia": ("orientacoes", "orientacao"),
    "tutorial": ("orientacoes", "orientacao"),
    "modulo": ("modulos", "modulo"), "integracao": ("integracoes", "integracao"),
    "api": ("apis", "api"), "dado": ("dados", "dado"),
}
PASTAS = {p: t for p, t in TIPOS.values()}
CURADA_POR = "agente"
LINK = re.compile(r"\[\[([^\]|#]+)((?:#[^\]|]*)?)((?:\|[^\]]*)?)\]\]")
NAO_E_CONHECIMENTO = {"agents.md"}  # o protocolo do vs init: fica no projeto, não vira nota no vault
LIMITE = 256 * 1024


def cabecalho(texto):
    """(cabeçalho, corpo) do Markdown do agente: `chave: valor`, listas `[a, b]` e listas em bloco `- item`."""
    m = re.match(r"^﻿?---\r?\n(.*?)\r?\n---\r?\n?(.*)$", texto, re.S)
    if not m:
        return {}, texto
    cab, chave = {}, None
    for linha in m.group(1).splitlines():
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s*(.*)$", linha) or re.match(r"^-\s+(.*)$", linha)
        if item and chave:
            if not isinstance(cab.get(chave), list):
                cab[chave] = []
            cab[chave].append(_valor(item.group(1)))
            continue
        if ":" not in linha:
            continue
        chave, valor = (p.strip() for p in linha.split(":", 1))
        valor = re.sub(r"\s+#.*$", "", valor)
        if valor.startswith("[") and valor.endswith("]"):
            cab[chave] = [_valor(v) for v in valor[1:-1].split(",") if v.strip()]
        else:
            cab[chave] = _valor(valor) if valor else []
    return cab, m.group(2)


def _valor(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def do_agente(cab):
    return str(cab.get("vs") or "").strip().lower() in TIPOS if isinstance(cab.get("vs"), str) else False


def _slug(texto):
    return re.sub(r"[^a-z0-9._-]+", "-", texto.lower()).strip("-.") or "nota"


def _destino(tag, pasta, caminho, usados):
    """Nota no vault: <pasta>/[<template>/]<nome>.md; nome repetido ganha as pastas de cima."""
    partes = caminho[:-3].split("/") if caminho.endswith(".md") else caminho.split("/")
    prefixo = []
    if tag.startswith("template-") and len(partes) > 1:
        prefixo, partes = [partes[0]], partes[1:]
    nome = _slug(partes[-1])
    i = len(partes) - 1
    while (pasta, *prefixo, nome) in usados and i > 0:
        i -= 1
        nome = _slug(partes[i]) + "--" + nome
    usados.add((pasta, *prefixo, nome))
    return os.path.join(notas.pasta_tag(tag), pasta, *prefixo, nome + ".md")


def _origens(tag, nota, pedidas, existentes):
    """Os caminhos de `origens` que existem no snapshot, e os que não existem."""
    raizes = [""]
    if tag.startswith("template-") and "/" in nota:
        raizes.append(nota.split("/", 1)[0] + "/")
    base = os.path.dirname(nota)
    if base:
        raizes.append(base + "/")
    achadas, faltam = [], []
    for p in pedidas if isinstance(pedidas, list) else [pedidas]:
        p = str(p).strip().lstrip("./").replace("\\", "/")
        if not p:
            continue
        alvo = next((r + p for r in raizes if r + p in existentes), None)
        (achadas if alvo else faltam).append(alvo or p)
    return list(dict.fromkeys(achadas)), faltam


def _resolver(m, mapa):
    """[[vetor-representacao]] ou [[docs/vs/vetor-representacao.md]] -> [[sistemas/<tag>/<pasta>/<nome>]]."""
    alvo = m.group(1).strip().replace("\\", "/").lstrip("./")
    if alvo.lower().endswith(".md"):
        alvo = alvo[:-3]
    for chave in (alvo.lower(), posixpath.basename(alvo).lower()):
        if chave in mapa:
            return f"[[{mapa[chave]}{m.group(2)}{m.group(3)}]]"
    return m.group(0)


def importadas(tag):
    """{caminho da nota no vault: ref da nota no projeto} das notas que vieram do agente."""
    saida = {}
    for pasta in PASTAS:
        for c in notas.todas(tag, (pasta,)).values():
            cab, _ = notas.ler(c)
            if cab.get("curada_por") == CURADA_POR:
                saida[c] = cab.get("nota_origem")
    return saida


def importar(db, tag):
    """Importa as notas do agente do snapshot processado (modo documentado). Devolve (gravadas, apagadas)."""
    s = db.execute("SELECT modo FROM sistemas WHERE tag = ? AND removido_em IS NULL", (tag,)).fetchone()
    if not s or s["modo"] != "documentado":
        return 0, 0
    antes, agora = importadas(tag), estado.agora()
    feitas, gravadas, usados = set(), 0, set()
    lidas, mapa = [], {}  # mapa: como o agente chama a nota ([[nome]]) -> chave da nota no vault
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome", (tag,)).fetchall():
        commit, clone = o["commit_processado"], ingestao.dir_clone(tag, o["nome"])
        if not commit or not os.path.isdir(os.path.join(clone, "objects")):
            feitas.update(c for c, ref in antes.items() if ref and estado.separar_ref(ref)[0] == o["nome"])
            continue
        arvore = {caminho: blob for caminho, blob, modo in ingestao.arvore(clone, commit) if modo not in ("120000", "160000")}
        for caminho, blob in sorted(arvore.items()):
            if not caminho.lower().endswith(".md") or int(ingestao._git(["cat-file", "-s", blob], cwd=clone)) > LIMITE:
                continue
            bruto = ingestao._git(["cat-file", "blob", blob], cwd=clone, binario=True)
            try:
                texto = bruto.decode("utf-8")
            except UnicodeDecodeError:
                continue
            cab, corpo = cabecalho(texto.replace("\r\n", "\n"))
            if not do_agente(cab):
                continue
            pasta, tipo = TIPOS[cab["vs"].strip().lower()]
            achadas, faltam = _origens(tag, caminho, cab.get("origens") or [], arvore)
            avisos = [("nota_agente_origem", f"{caminho}: origem que não existe no snapshot, ignorada: "
                                              f"{', '.join(faltam)}")] if faltam else []
            refs = [estado.ref(o["nome"], a) for a in (achadas or [caminho])]
            corpo, mascarados = filtros.mascarar(corpo)
            if mascarados:
                avisos.append(("nota_agente_segredo", f"{caminho}: valor com cara de segredo mascarado"))
            titulo = str(cab.get("titulo") or cab.get("title") or "").strip()
            if titulo and not notas.TITULO.search(corpo):
                corpo = f"# {titulo}\n\n" + corpo.lstrip("\n")
            ligacoes = [f"- [[{notas.chave(literal.nota_literal(tag, o['nome'], a))}]]" for a in (achadas or [])
                        if os.path.exists(literal.nota_literal(tag, o["nome"], a))]
            if ligacoes:
                corpo = corpo.rstrip("\n") + "\n\n<!-- arquivos -->\n## Arquivos de origem\n\n" + "\n".join(ligacoes) + "\n"
            destino = _destino(tag, pasta, caminho, usados)
            chave_vault = notas.chave(destino)
            sem_ext = caminho[:-3]
            for apelido in (sem_ext, posixpath.basename(sem_ext), titulo):
                if apelido:
                    mapa.setdefault(apelido.strip().lower(), chave_vault)
            for copia in (literal.nota_literal(tag, o["nome"], caminho),):
                if os.path.exists(copia):
                    os.remove(copia)  # a nota do agente não fica de novo como arquivo bruto
            lidas.append((o, caminho, commit, refs, corpo, destino, tipo, avisos))
        for nome_md in NAO_E_CONHECIMENTO:
            for caminho in arvore:
                if posixpath.basename(caminho).lower() == nome_md:
                    copia = literal.nota_literal(tag, o["nome"], caminho)
                    if os.path.exists(copia):
                        os.remove(copia)
    for o, caminho, commit, refs, corpo, destino, tipo, avisos in lidas:
        corpo = LINK.sub(lambda m: _resolver(m, mapa), corpo)
        velho = notas.ler(destino)[0] if os.path.exists(destino) else {}
        cab_vault = {"sistema": tag, "tipo_nota": tipo, "origens": refs, "commit_origem": commit,
                     "criado_em": velho.get("criado_em") or agora, "atualizado_em": agora,
                     "curada_por": CURADA_POR, "nota_origem": estado.ref(o["nome"], caminho)}
        if velho and os.path.exists(destino) and notas.ler(destino)[1] == corpo.lstrip("\n") \
                and {k: v for k, v in velho.items() if k != "atualizado_em"} == \
                {k: v for k, v in cab_vault.items() if k != "atualizado_em"}:
            feitas.add(destino)
            continue  # nada mudou: não regrava (sem commit novo no vault)
        notas.escrever(destino, cab_vault, corpo)
        for tipo_aviso, detalhe in avisos:  # só quando a nota muda: sem repetir a cada rodada
            historico.aviso(db, tag, tipo_aviso, detalhe, nota=notas.chave(destino))
        feitas.add(destino)
        gravadas += 1
    apagadas = 0
    for c in antes:
        if c not in feitas and os.path.exists(c):
            os.remove(c)
            apagadas += 1
    if gravadas or apagadas:
        print(f"[agente] {tag}: {gravadas} nota(s) curada(s) pelo agente gravada(s), {apagadas} apagada(s)")
    return gravadas, apagadas
