"""Notas do vault: ler e escrever cabeçalho, caminhos e links.

Cabeçalho entre `---`,
uma chave por linha, listas em JSON. Só biblioteca padrão.
"""
import json
import os
import re

LINK = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
TITULO = re.compile(r"^#\s+(.+)$", re.M)


def dir_vault():
    return os.environ.get("VAULT_DIR", "/opt/vault")


def pasta_tag(tag):
    return os.path.join(dir_vault(), "sistemas", tag)


def ler(caminho):
    """(cabecalho: dict, corpo: str)."""
    with open(caminho, encoding="utf-8") as arq:
        return separar(arq.read())


def separar(texto):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", texto, re.S)
    if not m:
        return {}, texto
    cab = {}
    for linha in m.group(1).splitlines():
        if ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        valor = valor.strip()
        if valor.startswith("["):
            try:
                valor = json.loads(valor)
            except ValueError:
                valor = [v.strip().strip("\"'") for v in valor.strip("[]").split(",") if v.strip()]
        elif len(valor) >= 2 and valor[0] == valor[-1] == '"':
            # escrever() grava com json.dumps: ler desfaz o escape (04/11: sem isso, cada
            # regravação dobrava as barras de um resumo com aspas).
            try:
                valor = _sem_escape_repetido(json.loads(valor))
            except ValueError:
                valor = valor[1:-1]
        elif len(valor) >= 2 and valor[0] == valor[-1] == "'":
            valor = valor[1:-1]
        elif valor in ("null", "~"):
            valor = None
        cab[chave.strip()] = valor
    return cab, m.group(2)


ESCAPE_REPETIDO = re.compile(r'\\+"')


def _sem_escape_repetido(valor):
    """Antes do  (04/11), cada regravação escapava de novo o valor entre
    aspas: `"n/a"` virava `\\"n/a\\"`, `\\\\\\"n/a\\\\\\"`, ... Uma aspa precedida de barras
    é sobra disso: volta a ser só a aspa."""
    return ESCAPE_REPETIDO.sub('"', valor)


def escrever(caminho, cab, corpo):
    linhas = ["---"]
    for chave, valor in cab.items():
        if isinstance(valor, list):
            valor = json.dumps(valor, ensure_ascii=False)
        elif valor is None:
            valor = "null"
        elif isinstance(valor, str) and (valor == "" or ":" in valor or valor.startswith(("[", "{", "#", "'", '"'))):
            valor = json.dumps(valor, ensure_ascii=False)
        linhas.append(f"{chave}: {valor}")
    linhas.append("---")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as arq:
        arq.write("\n".join(linhas) + "\n" + corpo.lstrip("\n"))


def chave(caminho):
    """Chave da nota (o que vai no link): caminho a partir da raiz do vault, sem .md."""
    return re.sub(r"\.md$", "", os.path.relpath(caminho, dir_vault()))


def link(caminho):
    return f"[[{chave(caminho)}]]"


def titulo(corpo, padrao=""):
    m = TITULO.search(corpo)
    return m.group(1).strip() if m else padrao


def todas(tag, pastas):
    """Notas .md da tag nas pastas do perfil: {chave: caminho absoluto}."""
    saida = {}
    for pasta in pastas:
        raiz = os.path.join(pasta_tag(tag), pasta)
        for base, _dirs, nomes in os.walk(raiz):
            for nome in sorted(nomes):
                if nome.endswith(".md"):
                    c = os.path.join(base, nome)
                    saida[chave(c)] = c
    return saida


def links_de(cab, corpo):
    """Alvos de link de uma nota: [[...]] no corpo e no cabeçalho, e as evidências."""
    texto = corpo + " " + " ".join(str(v) for v in cab.values())
    alvos = {a.strip() for a in LINK.findall(texto)}
    for e in cab.get("evidencias") or []:
        e = str(e).strip()
        m = LINK.fullmatch(e)
        alvos.add((m.group(1) if m else e).strip())
    return {a for a in alvos if a}


def consertar_cabecalhos(tag):
    """Regrava as notas da tag cujo cabeçalho tem a sobra do escape repetido
    (a leitura já desfaz; regravar deixa o arquivo limpo). Devolve as chaves."""
    feitas = []
    for base, _dirs, nomes in os.walk(pasta_tag(tag)):
        for nome in sorted(nomes):
            c = os.path.join(base, nome)
            if not nome.endswith(".md"):
                continue
            with open(c, encoding="utf-8") as f:
                texto = f.read()
            cab_txt = texto.split("\n---", 1)[0] if texto.startswith("---\n") else ""
            if not re.search(r'\\\\+"', cab_txt):
                continue
            cab, corpo = separar(texto)
            escrever(c, cab, corpo)
            feitas.append(chave(c))
    return feitas


def main(argv=None):
    """python -m vault_system.notas consertar-cabecalhos <tag>  (no curador; publica na próxima rodada)"""
    import sys
    from . import curadoria
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2 or args[0] != "consertar-cabecalhos":
        print(main.__doc__)
        return 2
    with curadoria.trava_da_tag(args[1]):  # não mexe enquanto um lote do vault roda
        feitas = consertar_cabecalhos(args[1])
    for k in feitas:
        print(f"[notas] cabeçalho consertado: {k}")
    print(f"[notas] {len(feitas)} nota(s); sobem na próxima rodada de {args[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
