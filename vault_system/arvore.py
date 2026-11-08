"""Árvore de pastas para classificar uma origem.

No "Novo vault", a tela mostra as pastas de cada repositório e a pessoa
classifica cada uma como documentos, código ou ignorar. A subpasta segue a
pasta de cima, a menos que tenha a própria classificação (a mais próxima vale).

- A tela pede a árvore (tabela `arvores`); o atendente do curador busca pelo
  GitHub App (uma chamada, sem clone) e grava os arquivos, os que os filtros
  fixos já tiram e uma sugestão de classificação.
- `leituras` transforma a classificação nas leituras que o curador já usa
  (perfil, incluir, excluir): documentos primeiro, código depois, e o que
  nenhuma aceita fica fora. O resultado é exato para os arquivos de hoje;
  arquivo novo numa pasta classificada segue a pasta (padrão `pasta/**`), e
  pasta nova na raiz segue a raiz.
- Regra dos .md (chave `MD` na classificação): todo .md vai para documentos,
  menos nas pastas ignoradas ou de referência e os classificados um a um.
- Referência: a pasta é copiada como está, sem LLM (literal.py). Vira uma leitura de
  documentos a mais (`*.md`), entre a de documentos e a de código. Assim um
  README ou spec novo numa pasta de código não é curado como código.
"""
import json

from . import estado, filtros, github_app

CLASSES = ("documentos", "referencia-explicada", "referencia", "codigo-literal", "codigo", "ignorar")
PERFIS = ("documentos", "referencia-explicada", "referencia", "codigo-literal", "codigo")  # nessa ordem: a primeira leitura que aceita leva
FORA_DA_REGRA_MD = ("ignorar", "referencia", "referencia-explicada")  # a regra dos .md não tira .md dessas
PASTAS_DOCUMENTOS = {"docs", "doc", "documentacao", "documentation"}
PASTAS_IGNORAR = {"assets", "fonts", "android", "ios", ".claude", ".vscode", ".idea"}  # pastas de ferramenta: 
MAX_PADROES = 100  # o mesmo limite de incluir/excluir do cadastro
MD = "*.md"  # chave da regra dos .md na classificação: {"*.md": "documentos"} = ligada


def fixo(caminho, tamanho=None):
    """Motivo pelo qual o arquivo fica fora em qualquer classificação, ou None."""
    motivo = filtros.por_caminho(caminho)
    if motivo:
        return motivo
    if tamanho is not None and tamanho > filtros.LIMITE_BYTES:
        return "tamanho"
    return None


def _pais(caminho):
    """Pastas de cima do caminho, da mais próxima à raiz ("")."""
    partes = caminho.split("/")
    return ["/".join(partes[:i]) for i in range(len(partes) - 1, 0, -1)] + [""]


def classe_de(caminho, classificacao):
    """A classificação do próprio arquivo ou da pasta mais próxima."""
    for c in [caminho] + _pais(caminho):
        if c in classificacao:
            return classificacao[c]
    return "ignorar"


def destino_de(caminho, classificacao):
    """Para onde vai o arquivo: a classificação dele, ou a da pasta mais
    próxima; com a regra dos .md, .md sem classificação própria fora de pasta
    ignorada vai para documentos."""
    proprio = caminho in classificacao
    classe = classe_de(caminho, classificacao)
    if (not proprio and classificacao.get(MD) == "documentos" and caminho.endswith(".md")
            and classe not in FORA_DA_REGRA_MD):
        return "documentos"
    return classe


def sugestao(arquivos):
    """Classificação inicial: raiz = código + cópia literal (04/11, o
    padrão é ter o código-fonte no vault); pastas de documentação =
    documentos; assets, fontes e apps nativos = ignorar; regra dos .md ligada."""
    s = {"": "codigo-literal"}
    for a in arquivos:
        partes = a["caminho"].split("/")
        for i, nome in enumerate(partes[:-1]):
            pasta = "/".join(partes[:i + 1])
            if nome.lower() in PASTAS_DOCUMENTOS:
                s.setdefault(pasta, "documentos")
            elif nome.lower() in PASTAS_IGNORAR:
                s.setdefault(pasta, "ignorar")
    # Só o que difere da pasta de cima (a árvore fica limpa na tela).
    return {**{c: v for c, v in s.items() if c == "" or classe_de(_pais(c)[0], s) != v}, MD: "documentos"}


PASTAS_DE_ARQUIVOS = {"assets", "fonts"}  # na Referência, as fontes e imagens viram arquivos para baixar


def sugestao_referencia(arquivos):
    """Vault de Referência: tudo literal com a explicação do curador
    (guias), menos apps nativos e pastas de ferramenta; sem a regra dos .md.
    assets/ e fonts/ entram: os binários de lá viram arquivos para
    baixar (vault_system/arquivos.py), e o texto, nota literal."""
    s = {"": "referencia-explicada"}
    for a in arquivos:
        partes = a["caminho"].split("/")
        for i, nome in enumerate(partes[:-1]):
            if nome.lower() in PASTAS_IGNORAR - PASTAS_DE_ARQUIVOS:
                s.setdefault("/".join(partes[:i + 1]), "ignorar")
    return {c: v for c, v in s.items() if c == "" or classe_de(_pais(c)[0], s) != v}


def _literal(texto):
    """Curingas do nome como texto: * ? [ viram classe ([*])."""
    return "".join(f"[{c}]" if c in "*?[" else c for c in texto)


def _exato(caminho):
    """Padrão que casa só com esse arquivo. `filtros.casa` compara padrão sem
    barra com o nome do arquivo em qualquer pasta (README.md pegaria todos os
    README); na raiz, a primeira letra vira a classe [/R], que tem barra e só
    casa com a própria letra."""
    if "/" in caminho:
        return _literal(caminho)
    c = caminho[0]
    return ("[]/]" if c == "]" else f"[/{c}]") + _literal(caminho[1:])


def _pasta(pasta):
    return "**" if pasta == "" else f"{_literal(pasta)}/**"


def _cobrir(arquivos, alvo, proibido, raiz=""):
    """Padrões mínimos (pasta/** ou o arquivo), dentro da pasta `raiz`, que
    pegam todos os arquivos de `alvo` sem pegar nenhum de `proibido` (os
    outros arquivos tanto faz). [] = nenhum alvo; ["**"] = a raiz inteira."""
    filhos = {}  # pasta -> conjunto de caminhos de arquivos embaixo
    for a in arquivos:
        for p in _pais(a):
            filhos.setdefault(p, set()).add(a)

    def cobre(pasta):
        dentro = filhos.get(pasta, set())
        if not dentro & alvo:
            return []
        if not dentro & proibido:
            return [_pasta(pasta)]
        prefixo = f"{pasta}/" if pasta else ""
        padroes, subpastas = [], set()
        for a in sorted(dentro):
            resto = a[len(prefixo):]
            if "/" in resto:
                subpastas.add(prefixo + resto.split("/")[0])
            elif a in alvo:
                padroes.append(_exato(a))
        for sp in sorted(subpastas):
            padroes += cobre(sp)
        return padroes

    return cobre(raiz)


def leituras(arquivos, classificacao):
    """Leituras (perfil, incluir, excluir) equivalentes à classificação, para
    `arquivos` (lista de caminhos; os fixos tanto faz). Levanta ValueError se
    passar do limite de padrões do cadastro.

    Para cada perfil: incluir = as pastas (ou arquivos) do perfil cuja pasta
    de cima é de outro destino; excluir = as pastas de outro destino logo
    abaixo de uma do perfil (os "buracos"). Assim arquivo novo segue a pasta.
    Buraco com uma pasta do perfil lá dentro (documentos > ignorar >
    documentos) não pode sair inteiro: sai arquivo por arquivo o que não é do
    perfil. Na leitura de código, o que é documentos tanto faz (a leitura de
    documentos vem antes e já levou). A regra dos .md vira a leitura do meio
    (ver `_leitura_md`)."""
    regra = classificacao.get(MD) == "documentos"
    classificacao = {k: v for k, v in classificacao.items() if k != MD}
    existentes = set(arquivos)
    padrao = lambda k: _exato(k) if k in existentes else _pasta(k)  # noqa: E731
    dentro = lambda k, h: k.startswith(h + "/") if h else k != ""  # noqa: E731
    saida = []
    for i, perfil in enumerate(PERFIS):
        visao = {k: v for k, v in classificacao.items() if v not in PERFIS[:i]}
        nos = [k for k, v in visao.items() if v == perfil]
        if not nos:
            continue
        de_cima = lambda k: None if k == "" else classe_de(_pais(k)[0], visao)  # noqa: E731
        # A raiz do perfil já pega tudo; o resto da árvore só entra pelas pastas do perfil.
        incluir = [] if visao.get("") == perfil else sorted(padrao(k) for k in nos if de_cima(k) != perfil)
        excluir = []
        for h in sorted(k for k, v in visao.items() if v != perfil and k != "" and de_cima(k) == perfil):
            if not any(dentro(k, h) for k in nos):
                excluir.append(padrao(h))
                continue
            sob = [a for a in arquivos if dentro(a, h) and not fixo(a)]
            excluir += _cobrir(sob, {a for a in sob if classe_de(a, visao) != perfil},
                               {a for a in sob if classe_de(a, visao) == perfil}, h)
        l = {"perfil": perfil, "incluir": incluir, "excluir": excluir}
        if len(l["incluir"]) > MAX_PADROES or len(l["excluir"]) > MAX_PADROES:
            raise ValueError(f"a classificação de {perfil} dá mais de {MAX_PADROES} padrões; "
                             "classifique pastas inteiras em vez de arquivos soltos")
        saida.append(l)
    if regra:
        md = _leitura_md(arquivos, classificacao)
        if md:
            saida.insert(1 if saida and saida[0]["perfil"] == "documentos" else 0, md)
    return saida


def _leitura_md(arquivos, classificacao):
    """Leitura da regra dos .md: incluir `*.md`; excluir as pastas ignoradas
    (inteiras, para .md novo lá dentro ficar fora) e os .md classificados um a
    um fora de documentos. Pasta ignorada com pasta de outro destino dentro sai
    pelos padrões mínimos que não pegam nada de fora dela. None = nada passa."""
    alvo, proibido = set(), set()
    sem_fixo = [a for a in arquivos if not fixo(a)]
    for a in sem_fixo:
        if a in classificacao:
            if a.endswith(".md") and classificacao[a] != "documentos":
                alvo.add(a)
        elif classe_de(a, classificacao) in FORA_DA_REGRA_MD:
            alvo.add(a)
        else:
            proibido.add(a)
    excluir = _cobrir(sem_fixo, alvo, proibido)
    if excluir == ["**"]:
        return None
    if len(excluir) > MAX_PADROES:
        raise ValueError(f"a regra dos .md dá mais de {MAX_PADROES} padrões de exclusão; "
                         "classifique pastas inteiras em vez de arquivos soltos")
    return {"perfil": "documentos", "incluir": [MD], "excluir": excluir}


def destinos(arquivos, leituras):
    """Para onde as leituras mandam cada arquivo hoje: {caminho: classe}.
    Fixo (`arquivos` com o campo fixo) fica de fora do dicionário."""
    from vault_system import ingestao  # a ingestão importa o GitHub App; aqui só a regra de leitura
    saida = {}
    for a in arquivos:
        if not a.get("fixo"):
            perfil, _ = ingestao.leitura_de(a["caminho"], leituras, cru=True)
            saida[a["caminho"]] = perfil if perfil in PERFIS else "ignorar"
    return saida


# perfis cujo arquivo que entra vai ao curador (LLM); `referencia` é cópia pelo código.
COM_LLM = ("documentos", "referencia-explicada", "codigo", "codigo-literal")
COPIADOS = ("referencia", "codigo-literal")  # ganham cópia literal pelo código, sem LLM


def _na_fila(classe):
    """O perfil da fila (código + cópia literal é código para o curador)."""
    return "codigo" if classe == "codigo-literal" else classe


def impacto(mudancas):
    """O custo de uma reclassificação, para a tela avisar antes de salvar:
    {ao_curador, lotes, copia, saem, por_destino}. `lotes` é estimativa: segue o
    tamanho de lote do curador (documentos e referência explicada em grupos de
    VAULT_LOTE; código por pasta, em grupos de VAULT_LOTE_CODIGO), sem contar
    o limite de bytes nem as notas que o curador revisa quando um arquivo sai."""
    import math
    import os
    import posixpath
    lote = int(os.environ.get("VAULT_LOTE", "5"))
    lote_codigo = int(os.environ.get("VAULT_LOTE_CODIGO", "12"))
    por_destino, pastas = {}, {}
    for m in mudancas:
        if _na_fila(m["de"]) == _na_fila(m["para"]):
            continue  # código ↔ código + cópia literal: só a cópia muda, sem fila
        if m["para"] in COM_LLM:
            por_destino[m["para"]] = por_destino.get(m["para"], 0) + 1
            if _na_fila(m["para"]) == "codigo":
                pasta = posixpath.dirname(m["caminho"])
                pastas[pasta] = pastas.get(pasta, 0) + 1
    lotes = sum(math.ceil(n / lote_codigo) for n in pastas.values())
    lotes += sum(math.ceil(por_destino.get(p, 0) / lote) for p in ("documentos", "referencia-explicada"))
    return {"ao_curador": sum(por_destino.values()), "lotes": lotes,
            "copia": sum(1 for m in mudancas if m["para"] in COPIADOS),
            "saem": sum(1 for m in mudancas if m["de"] != "ignorar" and m["para"] == "ignorar"),
            "por_destino": por_destino}


def classificacao_de(arquivos, leituras):
    """A classificação mais enxuta que leva cada arquivo aonde as leituras de
    hoje levam (editar uma origem cadastrada pelo formulário antigo):
    o menor número de pastas e arquivos com classificação própria, escolhido
    pasta a pasta (em empate, a classificação fica na pasta mais alta: arquivo
    novo lá dentro segue o mesmo destino). Ex.: um app com
    android/ e ios/ ignorados fica "código, menos android e ios", e não
    "ignorar, menos lib e test"."""
    hoje = destinos(arquivos, leituras)
    if not hoje:
        return {"": "codigo", MD: "documentos"}
    # Com e sem a regra dos .md: vale a mais enxuta. Empate fica sem a regra: a
    # pasta classificada (ex.: docs/ só com .md) também leva o arquivo novo que não é .md.
    com, sem = _classificacao_de(hoje, True), _classificacao_de(hoje, False)
    return {**com, MD: "documentos"} if len(com) + 1 < len(sem) else sem


def _classificacao_de(hoje, regra):
    def esperado(a, classe):
        return "documentos" if regra and a.endswith(".md") and classe not in FORA_DA_REGRA_MD else classe

    pastas, soltos = {""}, {}
    for caminho in hoje:
        pastas.update(_pais(caminho))
        soltos.setdefault(_pais(caminho)[0], []).append(caminho)
    filhos = {}
    for p in pastas - {""}:
        filhos.setdefault(_pais(p)[0], []).append(p)
    custo = {}  # (pasta, classe da pasta) -> nós próprios embaixo dela

    def abaixo(pasta, classe):
        if (pasta, classe) not in custo:
            custo[pasta, classe] = (sum(hoje[a] != esperado(a, classe) for a in soltos.get(pasta, []))
                                    + sum(min(abaixo(f, k) + (k != classe) for k in CLASSES)
                                          for f in filhos.get(pasta, [])))
        return custo[pasta, classe]

    c = {}

    def escolher(pasta, herdada):
        classe = min(CLASSES, key=lambda k: (abaixo(pasta, k) + (k != herdada), k == herdada))
        if pasta == "" or classe != herdada:
            c[pasta] = classe
        for f in sorted(filhos.get(pasta, [])):
            escolher(f, classe)
        for a in soltos.get(pasta, []):
            if hoje[a] != esperado(a, classe):
                c[a] = hoje[a]

    escolher("", "codigo")
    return c


def mudancas(arquivos, leituras, classificacao):
    """Arquivos que mudam de destino entre as leituras de hoje e a classificação:
    [{caminho, de, para}]."""
    hoje = destinos(arquivos, leituras)
    return [{"caminho": k, "de": v, "para": destino_de(k, classificacao)}
            for k, v in sorted(hoje.items()) if destino_de(k, classificacao) != v]


# --- pedidos da tela (a API grava, o atendente do curador responde) ------------

def pedir(db, repo, ramo, por):
    with db:
        return db.execute("INSERT INTO arvores (repo, ramo, pedido_em, pedido_por) VALUES (?, ?, ?, ?)",
                          (repo, ramo, estado.agora(), por)).lastrowid


def buscar(repo, ramo):
    """Arquivos do ramo pelo GitHub App: {commit, arquivos: [{caminho, tamanho, fixo}],
    sugestao}. Levanta github_app.ErroGitHub."""
    dono, nome = github_app.do_app(repo) or (None, None)
    if not dono:
        raise github_app.ErroGitHub("a árvore só é carregada para repositório do GitHub App")
    commit, itens, truncado = github_app.arvore(dono, nome, ramo)
    arquivos = [{"caminho": i["path"], "tamanho": i.get("size"), "fixo": fixo(i["path"], i.get("size"))}
                for i in itens if i["type"] == "blob"]
    return {"commit": commit, "truncado": truncado, "arquivos": arquivos, "sugestao": sugestao(arquivos)}


def atender(db):
    """Responde os pedidos de árvore abertos. Devolve quantos respondeu."""
    pedidos = db.execute("SELECT id, repo, ramo FROM arvores WHERE atendido_em IS NULL ORDER BY id").fetchall()
    for p in pedidos:
        try:
            r = buscar(p["repo"], p["ramo"])
            print(f"[arvore] {p['repo']} {p['ramo']}: {len(r['arquivos'])} arquivo(s)")
        except github_app.ErroGitHub as e:
            r = {"erro": str(e)}
            print(f"[arvore] {p['repo']} {p['ramo']}: {e}")
        with db:
            db.execute("UPDATE arvores SET atendido_em = ?, resultado = ? WHERE id = ?",
                       (estado.agora(), json.dumps(r, ensure_ascii=False), p["id"]))
    return len(pedidos)
