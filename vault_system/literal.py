"""Vault de Referência, modo literal: o arquivo vira nota como está, sem LLM.

Para conteúdo que precisa chegar exato a quem consulta (design system, normas
já escritas): tokens, código de componente, texto de quem desenhou. O curador
não reescreve; o código copia.

  perfil referencia
    referencia/<caminho na origem>.md   uma nota por arquivo (1:1)

- `.md`: o corpo da nota é o arquivo inteiro, como está (com o cabeçalho
  dele, se tiver). Nada de normalizar links nem reescrever.
- Outros arquivos de texto (CSS, JSON, HTML, JS, ...): título com o nome do
  arquivo e o conteúdo inteiro num bloco de código com a linguagem.
- O cabeçalho é todo do código: sistema, tipo_nota, origens, commit_origem,
  datas, `literal: true` e `hash_literal` (o hash do corpo gravado). O
  verificador acusa nota cujo corpo não bate mais com o hash (alguém editou a
  nota no vault em vez de editar a origem).
- Arquivo removido na origem: a nota sai.
- O conteúdo vem do arquivo do lote, que já passou pelos filtros de segredo
  da ingestão (valores mascarados).

Os itens são registrados em `_meta/registro.md` como os do curador e saem da
fila na hora: não há lote nem tentativa, porque não há LLM.

Referência + explicação (perfil `referencia-explicada`, fase 2): o arquivo
também é copiado aqui, mas o item fica na fila para o curador escrever guias
em `guias/` (para que serve, quando usar). O curador nunca escreve código: ele
marca o trecho e o código cola, sempre a partir da nota literal (o mesmo texto,
com os mesmos filtros de segredo):

    <!-- trecho: design_system/index.html#buttons -->   elemento HTML com esse id
    <!-- trecho: tokens/tokens.css:L1-L40 -->             linhas (1 = a primeira)

Depois do marcador, o código grava o bloco de código e fecha com
`<!-- /trecho -->`. Os trechos são recolados a cada rodada (a origem mudou, o
guia acompanha); bloco de código fora de trecho é tirado do guia.
"""
import hashlib
import json
import os
import posixpath
import re
from html.parser import HTMLParser

from . import estado, historico, notas

PERFIL = "referencia"
EXPLICADA = "referencia-explicada"
PERFIS_COPIADOS = (PERFIL, EXPLICADA)
PASTA = "referencia"
TIPO_NOTA = "referencia"
PASTA_GUIAS = "guias"
TIPO_GUIA = "guia"
LINGUAGENS = {
    ".css": "css", ".scss": "scss", ".less": "less", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx", ".json": "json", ".html": "html", ".htm": "html",
    ".svg": "xml", ".xml": "xml", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".py": "python",
    ".dart": "dart", ".kt": "kotlin", ".swift": "swift", ".sh": "bash", ".sql": "sql", ".vue": "vue",
}


def lingua_de(caminho):
    """Linguagem do bloco de código de um arquivo: pela extensão, ou pelo nome (Dockerfile, nginx)."""
    nome = os.path.basename(caminho).lower()
    if nome == "dockerfile" or nome.startswith("dockerfile.") or nome.endswith(".dockerfile"):
        return "dockerfile"
    if nome.endswith(".conf") and "nginx" in caminho.lower():
        return "nginx"
    if nome == "caddyfile":
        return "caddyfile"
    return LINGUAGENS.get(os.path.splitext(caminho)[1].lower(), "")


def nota_literal(tag, origem, caminho):
    rel = caminho if caminho.endswith(".md") else caminho + ".md"
    prefixo = "" if origem == "principal" else origem + "/"
    return os.path.join(notas.pasta_tag(tag), PASTA, prefixo + rel)


def _cerca(texto):
    maior = max((len(s) for s in texto.split("\n") if s and set(s) == {"`"}), default=0)
    return "`" * max(3, maior + 1)


def corpo_de(caminho, texto):
    """O corpo da nota: o .md como está; o resto num bloco de código."""
    if caminho.endswith(".md"):
        return texto
    cerca = _cerca(texto)
    lingua = lingua_de(caminho)
    return f"# {os.path.basename(caminho)}\n\n{cerca}{lingua}\n{texto.rstrip(chr(10))}\n{cerca}\n"


def hash_corpo(corpo):
    return hashlib.sha256(corpo.lstrip("\n").encode()).hexdigest()[:16]


def _registrar(tag, linhas):
    with open(os.path.join(notas.pasta_tag(tag), "_meta", "registro.md"), "a", encoding="utf-8") as f:
        f.write("".join(f"- {l}\n" for l in linhas))


def _so_do_agente(db, tag, caminho, texto):
    """No modo documentado, as notas do agente entram curadas (agente.py) e o AGENTS.md é o protocolo do
    projeto: nenhum dos dois fica de novo no vault como arquivo bruto."""
    from . import agente
    s = db.execute("SELECT modo FROM sistemas WHERE tag = ?", (tag,)).fetchone()
    if not s or s["modo"] != "documentado":
        return False
    if posixpath.basename(caminho).lower() in agente.NAO_E_CONHECIMENTO:
        return True
    return caminho.lower().endswith(".md") and agente.do_agente(agente.cabecalho(texto)[0])


def copiar(db, tag):
    """Itens da fila dos perfis copiados: viram nota literal, ou a nota sai. Os
    de `referencia` saem da fila; os de `referencia-explicada` ficam para o
    curador escrever os guias. Devolve quantos itens registrou."""
    itens = db.execute("SELECT * FROM fila WHERE tag = ? AND estado = 'na_fila' AND parado_em IS NULL "
                       "AND perfil IN (?, ?) ORDER BY id", (tag, *PERFIS_COPIADOS)).fetchall()
    if not itens:
        return 0
    agora, linhas, feitos = estado.agora(), [], []
    for i in itens:
        ref = estado.ref(i["origem"], i["caminho"])
        c = nota_literal(tag, i["origem"], i["caminho"])
        explicada = i["perfil"] == EXPLICADA
        if i["acao"] == "removido":
            if explicada:
                continue  # a remoção da curadoria apaga a nota literal e manda revisar os guias que a usavam
            if os.path.exists(c):
                os.remove(c)
            linhas.append(f"item-{i['id']}: {ref} removido na origem; nota literal apagada (código)")
            feitos.append(i["id"])
            continue
        try:
            with open(os.path.join(estado.dir_estado(), "lotes", i["lote"]), encoding="utf-8") as f:
                texto = f.read()
        except (OSError, TypeError) as e:
            with db:
                db.execute("UPDATE fila SET erro = ?, parado_em = ? WHERE id = ?",
                           (f"arquivo do lote indisponível: {e}", agora, i["id"]))
            historico.aviso(db, tag, "item_parado", f"{ref}: arquivo do lote indisponível para a cópia literal")
            continue
        if _so_do_agente(db, tag, i["caminho"], texto):
            if os.path.exists(c):
                os.remove(c)
            linhas.append(f"item-{i['id']}: {ref} é nota do agente ou o AGENTS.md: não vira cópia literal")
            feitos.append(i["id"])
            continue
        corpo = corpo_de(i["caminho"], texto)
        velho = notas.ler(c)[0] if os.path.exists(c) else {}
        if explicada:
            if velho.get("hash_literal") != hash_corpo(corpo) or velho.get("commit_origem") != i["commit_origem"]:
                notas.escrever(c, {"sistema": tag, "tipo_nota": TIPO_NOTA, "origens": [ref],
                                   "commit_origem": i["commit_origem"], "criado_em": velho.get("criado_em") or agora,
                                   "atualizado_em": agora, "literal": "true", "hash_literal": hash_corpo(corpo)}, corpo)
            continue  # fica na fila para o curador
        notas.escrever(c, {"sistema": tag, "tipo_nota": TIPO_NOTA, "origens": [ref],
                           "commit_origem": i["commit_origem"], "criado_em": velho.get("criado_em") or agora,
                           "atualizado_em": agora, "literal": "true", "hash_literal": hash_corpo(corpo)}, corpo)
        linhas.append(f"item-{i['id']}: {ref} copiado como está para [[{notas.chave(c)}]] (código, sem LLM)")
        feitos.append(i["id"])
    if linhas:
        _registrar(tag, linhas)
    with db:
        for n in feitos:
            db.execute("UPDATE fila SET estado = 'registrado' WHERE id = ?", (n,))
    if feitos:
        print(f"[literal] {tag}: {len(feitos)} item(ns) copiado(s) ou removido(s) sem LLM")
    return len(feitos)


# --- código + cópia literal ---------------------------------------------
#
# O arquivo de uma leitura codigo-literal vai à fila como código (o curador
# escreve módulos, regras, ...) e, além disso, ganha a nota literal em
# referencia/, feita aqui a cada rodada, sem fila e sem LLM: a partir do clone,
# no commit processado da origem, com os mesmos filtros de conteúdo da
# ingestão. A nota leva `copia_codigo: true` (só essas este passo apaga) e
# `blob_origem` (o arquivo só é lido de novo quando o blob muda). Assim, trocar
# a classe entre código e código + cópia literal só cria ou apaga cópias.

def _copias_de_codigo(tag):
    """{ref: caminho da nota} das notas literais feitas por copiar_codigo."""
    saida = {}
    for c in notas.todas(tag, [PASTA]).values():
        cab = notas.ler(c)[0]
        if str(cab.get("copia_codigo")) == "true" and cab.get("origens"):
            saida[cab["origens"][0]] = c
    return saida


def copiar_codigo(db, tag):
    """Sincroniza as cópias literais das leituras codigo-literal. Devolve (gravadas, apagadas)."""
    from . import filtros, ingestao
    feitas = _copias_de_codigo(tag)
    esperadas, agora, gravadas = set(), estado.agora(), 0
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome", (tag,)).fetchall():
        leituras = json.loads(o["leituras"] or "[]")
        commit, clone = o["commit_processado"], ingestao.dir_clone(tag, o["nome"])
        if not any(l.get("perfil") == ingestao.CODIGO_LITERAL for l in leituras) or not commit \
                or not os.path.isdir(os.path.join(clone, "objects")):
            if any(l.get("perfil") == ingestao.CODIGO_LITERAL for l in leituras):
                # Sem commit processado ou sem clone ainda: as cópias que já existem ficam até dar para conferir.
                esperadas.update(r for r in feitas if estado.separar_ref(r)[0] == o["nome"])
            continue
        for caminho, blob, modo in ingestao.arvore(clone, commit):
            if modo in ("120000", "160000") or ingestao.leitura_de(caminho, leituras, cru=True)[0] != ingestao.CODIGO_LITERAL:
                continue
            ref = estado.ref(o["nome"], caminho)
            c = nota_literal(tag, o["nome"], caminho)
            velho = notas.ler(c)[0] if os.path.exists(c) else {}
            if ref in feitas and velho.get("blob_origem") == blob \
                    and velho.get("hash_literal") == hash_corpo(notas.ler(c)[1]):
                esperadas.add(ref)
                continue  # mesmo arquivo e cópia intacta; editada no vault ou gravada errado, é refeita
            if int(ingestao._git(["cat-file", "-s", blob], cwd=clone)) > filtros.LIMITE_BYTES:
                continue
            texto, motivo = filtros.por_conteudo(ingestao._git(["cat-file", "blob", blob], cwd=clone, binario=True))
            if motivo:
                continue  # binário, segredo que não dá para mascarar, ...: sem cópia (a nota velha, se havia, sai)
            # Quebra de linha como a nota é lida (open em modo texto): com o \r do Windows, o hash
            # gravado não batia com o relido.
            texto, _ = filtros.mascarar(texto.replace("\r\n", "\n").replace("\r", "\n"))
            corpo = corpo_de(caminho, texto)
            notas.escrever(c, {"sistema": tag, "tipo_nota": TIPO_NOTA, "origens": [ref], "commit_origem": commit,
                               "criado_em": velho.get("criado_em") or agora, "atualizado_em": agora,
                               "literal": "true", "hash_literal": hash_corpo(corpo), "copia_codigo": "true",
                               "blob_origem": blob}, corpo)
            esperadas.add(ref)
            gravadas += 1
    apagadas = 0
    for ref, c in feitas.items():
        if ref not in esperadas and os.path.exists(c):
            os.remove(c)
            apagadas += 1
    if gravadas or apagadas:
        print(f"[literal] {tag}: código + cópia literal: {gravadas} cópia(s) gravada(s), {apagadas} apagada(s), sem LLM")
    return gravadas, apagadas


ARQUIVOS = re.compile(r"\n*<!-- arquivos -->\n.*?<!-- /arquivos -->\n?", re.S)


def ligar_arquivos(tag, pastas):
    """Em cada nota de código (as `pastas` do perfil), o bloco "Arquivos" com o
    link para a cópia (copiar_codigo) de cada origem que tem uma. O bloco é do
    código: refeito a cada rodada, some quando não há cópia. Só as cópias de
    código entram: a Referência explicada já liga pelos guias e trechos.
    Devolve quantas notas mudaram."""
    literais = _copias_de_codigo(tag)
    mudadas = 0
    for c in notas.todas(tag, pastas).values():
        cab, corpo = notas.ler(c)
        alvos = sorted({literais[r] for r in (cab.get("origens") or []) if r in literais})
        tem = ARQUIVOS.search(corpo)
        if not alvos and not tem:
            continue  # nota sem cópia e sem bloco: não toca (nem no fim do arquivo)
        novo = ARQUIVOS.sub("\n", corpo).rstrip("\n") + "\n" if tem else corpo
        if alvos:
            novo = novo.rstrip("\n") + "\n" + ("\n<!-- arquivos -->\n## Arquivos\n\nO código-fonte, como está na origem (cópia literal):\n\n"
                     + "".join(f"- {notas.link(a)}\n" for a in alvos) + "<!-- /arquivos -->\n")
        if novo != corpo:
            notas.escrever(c, cab, novo)
            mudadas += 1
    if mudadas:
        print(f"[literal] {tag}: bloco Arquivos refeito em {mudadas} nota(s) de código")
    return mudadas


def conferir(chave, cab, corpo):
    """Problema de uma nota literal, ou None."""
    if cab.get("hash_literal") and cab["hash_literal"] != hash_corpo(corpo):
        return ("literal_editado", chave, f"nota literal editada no vault (edite a origem, não a nota): `{chave}`")
    return None


# --- trechos dos guias (fase 2) -------------------------------------------------

MARCA = re.compile(r"^<!-- trecho: (\S+?) -->[ \t]*\n(?:.*?\n<!-- /trecho -->[ \t]*\n?)?", re.M | re.S)
CERCA = re.compile(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$\n?", re.M | re.S)
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def fonte_da_nota(c):
    """O texto do arquivo de origem guardado numa nota literal: o corpo inteiro
    (arquivo .md) ou o conteúdo do bloco de código (os outros, ver corpo_de)."""
    corpo = notas.ler(c)[1]
    nome = re.escape(os.path.basename(c)[:-3])
    m = re.fullmatch(rf"# {nome}\n\n(`{{3,}})[^\n]*\n(.*)\n\1\n", corpo, re.S)
    return m.group(2) + "\n" if m else corpo


class _Elemento(HTMLParser):
    def __init__(self, alvo):
        super().__init__(convert_charrefs=False)
        self.alvo, self.inicio, self.fim, self.nome, self.nivel = alvo, None, None, None, 0

    def handle_starttag(self, tag, attrs):
        if self.fim is not None:
            return
        if self.inicio is None:
            if dict(attrs).get("id") == self.alvo:
                self.inicio, self.nome = self.getpos(), tag
                if tag in VAZIOS:
                    self.fim = ("vazio", self.get_starttag_text())
                else:
                    self.nivel = 1
        elif tag == self.nome:
            self.nivel += 1

    def handle_endtag(self, tag):
        if self.inicio is not None and self.fim is None and tag == self.nome:
            self.nivel -= 1
            if self.nivel == 0:
                self.fim = self.getpos()


def _deslocamento(texto, pos):
    linha, coluna = pos
    inicio = 0
    for _ in range(linha - 1):
        inicio = texto.index("\n", inicio) + 1
    return inicio + coluna


def extrair(texto, seletor):
    """O trecho do texto pelo seletor (`#id` de um elemento HTML ou `:L<a>-L<b>`), ou None."""
    m = re.fullmatch(r":L(\d+)(?:-L?(\d+))?", seletor)
    if m:
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        linhas = texto.split("\n")
        if a < 1 or b < a or b > len(linhas):
            return None
        return "\n".join(linhas[a - 1:b])
    if seletor.startswith("#") and len(seletor) > 1:
        p = _Elemento(seletor[1:])
        p.feed(texto)
        if p.inicio is None or p.fim is None:
            return None
        ini = _deslocamento(texto, p.inicio)
        if p.fim[0] == "vazio":
            return texto[ini:ini + len(p.fim[1])]
        fim = texto.index(">", _deslocamento(texto, p.fim)) + 1
        return texto[ini:fim]
    return None


def _alvo(tag, marca):
    """(caminho da nota literal, seletor, linguagem) de um marcador `arquivo#id` ou `arquivo:L1-L2`."""
    m = re.fullmatch(r"(.+?)(#[^#\s]+|:L\d+(?:-L?\d+)?)", marca)
    if not m:
        return None, None, ""
    ref, seletor = m.group(1), m.group(2)
    origem, caminho = estado.separar_ref(ref)
    lingua = "markdown" if caminho.endswith(".md") else lingua_de(caminho)
    return nota_literal(tag, origem, caminho), seletor, lingua


def blocos(texto):
    """Blocos de código de um .md: [(linha da abertura, linha do fechamento, linguagem)], linhas a partir de 1."""
    saida, aberto = [], None
    for n, linha in enumerate(texto.split("\n"), 1):
        if aberto is None:
            m = re.match(r"(`{3,}|~{3,})\s*([^\s`]*)", linha)
            if m:
                aberto = (n, m.group(1), m.group(2))
        elif re.fullmatch(rf"{re.escape(aberto[1][0])}{{{len(aberto[1])},}}[ \t]*", linha):
            saida.append((aberto[0], n, aberto[2]))
            aberto = None
    return saida


def _lingua_md(texto, a, b):
    """Como colar as linhas a..b de um .md: dentro de um bloco de código, com a linguagem dele;
    blocos inteiros (com ou sem texto em volta), como estão (None); o resto, como markdown."""
    for ini, fim, lingua in blocos(texto):
        if ini < a and b < fim:
            return lingua
    cortados = [1 for ini, fim, _ in blocos(texto) if (ini < a <= fim) or (ini <= b < fim)]
    return "markdown" if cortados else None


def trecho(tag, marca):
    """(texto, linguagem) do marcador, ou (None, motivo). Linguagem None: colar sem cerca."""
    c, seletor, lingua = _alvo(tag, marca)
    if not c:
        return None, "marcador fora do formato arquivo#id ou arquivo:L1-L2"
    if not os.path.exists(c):
        return None, "o arquivo não é uma referência copiada neste vault"
    fonte = fonte_da_nota(c)
    texto = extrair(fonte, seletor)
    if texto is None:
        if seletor.startswith("#"):
            existentes = ids(fonte)
            dica = ("; ids que existem: " + ", ".join(existentes[:20])) if existentes else "; o arquivo não tem id"
            return None, f"{seletor} não existe no arquivo{dica}"
        return None, f"{seletor} não existe no arquivo"
    if lingua == "markdown":  # arquivo .md: a linguagem é a do bloco de código de onde o trecho saiu
        if seletor.startswith(":"):
            m = re.fullmatch(r":L(\d+)(?:-L?(\d+))?", seletor)
            a = int(m.group(1))
            b = int(m.group(2) or a)
            for ini, fim, lg in blocos(fonte):
                # Marcador só na linha de crases (`arquivo.md:L67`, a abertura ou o fechamento): o curador quis o
                # bloco; o trecho é o bloco inteiro, sem as crases (03/11).
                if a == b and a in (ini, fim) and fim - ini > 1:
                    a, b = ini + 1, fim - 1
                    texto = extrair(fonte, f":L{a}-L{b}")
                    break
                # O curador às vezes pega junto a linha de crases do bloco (a de abertura ou a de fechamento):
                # o trecho é o conteúdo do bloco, sem ela.
                na, nb = max(a, ini + 1), min(b, fim - 1)
                if ini <= a <= b <= fim and (a, b) != (ini, fim) and (a == ini or b == fim) and na <= nb:
                    a, b = na, nb
                    texto = extrair(fonte, f":L{a}-L{b}")
            lingua = _lingua_md(fonte, a, b)
        else:
            antes = fonte[:fonte.index(texto)].count("\n") + 1
            lingua = next((lg or "html" for ini, fim, lg in blocos(fonte) if ini < antes < fim), "html")
    return texto, lingua


def ids(texto):
    """Os ids de elementos HTML do texto, na ordem."""
    class _Ids(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.ids = []

        def handle_starttag(self, tag, attrs):
            i = dict(attrs).get("id")
            if i and i not in self.ids:
                self.ids.append(i)
    p = _Ids()
    p.feed(texto)
    return p.ids


def numerado(texto):
    """O texto com o número de cada linha à esquerda, como o curador vê no lote."""
    return "\n".join(f"{n:>5}| {linha}" for n, linha in enumerate(texto.split("\n"), 1))


def escrever_fontes(tag, destino):
    """Cópia numerada de cada arquivo de referência da tag em destino/<arquivo>: os números
    de linha dos marcadores são os do arquivo, não os da nota em referencia/ (que tem cabeçalho)."""
    for c in notas.todas(tag, (PASTA,)).values():
        cab = notas.ler(c)[0]
        if not cab.get("literal") or not cab.get("origens"):
            continue
        origem, caminho = estado.separar_ref(cab["origens"][0])
        alvo = os.path.join(destino, ("" if origem == "principal" else origem + "/") + caminho)
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        with open(alvo, "w", encoding="utf-8") as f:
            f.write(numerado(fonte_da_nota(c)))


def _bloco(marca, texto, lingua):
    if lingua is None:
        return f"<!-- trecho: {marca} -->\n{texto.rstrip(chr(10))}\n<!-- /trecho -->\n"
    cerca = _cerca(texto)
    return f"<!-- trecho: {marca} -->\n{cerca}{lingua}\n{texto.rstrip(chr(10))}\n{cerca}\n<!-- /trecho -->\n"


def colar(tag, corpo):
    """O corpo do guia com os trechos colados de novo e sem código do curador.
    Devolve (corpo, avisos)."""
    avisos, pedacos, ultimo = [], [], 0
    for m in MARCA.finditer(corpo):
        antes = corpo[ultimo:m.start()]
        sem_codigo = CERCA.sub("", antes)
        if sem_codigo != antes:
            avisos.append("bloco de código escrito pelo curador tirado do guia (código só por trecho)")
        pedacos.append(sem_codigo)
        texto, lingua = trecho(tag, m.group(1))
        if texto is None:
            avisos.append(f"trecho {m.group(1)}: {lingua}")
            pedacos.append(f"<!-- trecho: {m.group(1)} -->\n> Trecho indisponível: {lingua}.\n<!-- /trecho -->\n")
        else:
            pedacos.append(_bloco(m.group(1), texto, lingua))
        ultimo = m.end()
    resto = corpo[ultimo:]
    sem_codigo = CERCA.sub("", resto)
    if sem_codigo != resto:
        avisos.append("bloco de código escrito pelo curador tirado do guia (código só por trecho)")
    pedacos.append(sem_codigo)
    return "".join(pedacos), avisos


def refs_dos_trechos(tag, corpo):
    """Arquivos de origem citados pelos marcadores do guia (`origem:caminho` fora da principal)."""
    saida = []
    for m in MARCA.finditer(corpo):
        mm = re.fullmatch(r"(.+?)(#[^#\s]+|:L\d+(?:-L?\d+)?)", m.group(1))
        if mm and mm.group(1) not in saida:
            saida.append(mm.group(1))
    return saida


PASTAS_COM_TRECHO = (PASTA_GUIAS, "infra")  # a nota de infra também mostra o arquivo por trecho


def colar_guias(db, tag):
    """Recola os trechos de todos os guias e notas de infra (a nota literal pode ter mudado)."""
    raiz = os.path.join(notas.pasta_tag(tag), PASTA_GUIAS)
    for chave, c in notas.todas(tag, PASTAS_COM_TRECHO).items():
        cab, corpo = notas.ler(c)
        novo, avisos = colar(tag, corpo)
        if novo != corpo:
            notas.escrever(c, cab, novo)
        for a in avisos:
            historico.aviso(db, tag, "trecho", a, nota=chave)
    return raiz


def conferir_guia(tag, chave, corpo):
    """Problemas de um guia: código fora de trecho e trecho que não bate com a origem."""
    erros = []
    fora = MARCA.sub("", corpo)
    if CERCA.search(fora):
        erros.append(("codigo_fora_de_trecho", chave, f"guia com código escrito à mão (só por trecho): `{chave}`"))
    for m in MARCA.finditer(corpo):
        texto, lingua = trecho(tag, m.group(1))
        if texto is None or _bloco(m.group(1), texto, lingua) != m.group(0).rstrip("\n") + "\n":
            erros.append(("trecho_divergente", chave, f"trecho `{m.group(1)}` não bate com a origem: `{chave}`"))
        elif lingua == "markdown" and ":L" in m.group(1):  # linhas que cortam um bloco: quase sempre linha errada
            erros.append(("trecho_corta_bloco", chave, f"trecho `{m.group(1)}` começa ou termina no meio de um "
                                                       f"bloco de código (linhas erradas?): `{chave}`"))
    return erros
