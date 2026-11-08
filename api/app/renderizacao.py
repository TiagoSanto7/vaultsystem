"""Renderização: uma página HTML do vault de Referência, montada com
tudo embutido, para a tela mostrar num iframe isolado.

A tela escolhe a página (uma nota literal .html em `referencia/`) e, se quiser,
CSS e JS a mais (outras notas literais). O que a página referencia por caminho
relativo é resolvido a partir do lugar dela na origem:

- texto (CSS, JS, SVG): da nota literal, o mesmo texto que o MCP entrega (já
  passou pelos filtros de segredo da ingestão);
- binário (imagens e fontes, que não viram nota): do clone bare da origem, no
  commit da página. Só as extensões de BINARIOS, até LIMITE_ARQUIVO cada.

Tudo vira `<style>`, `<script>` ou `data:`, para o iframe não precisar pedir
nada à API: ele roda em `sandbox="allow-scripts"`, sem `allow-same-origin`,
numa origem opaca que não vê o cookie da sessão nem a tela.

O que não deu para resolver (fora da origem, não está no vault nem no commit,
grande demais) fica como está na página e vai para `avisos`.
"""
import base64
import posixpath
import re
from urllib.parse import unquote

from vault_system import arquivos, estado, literal

BINARIOS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".avif": "image/avif", ".ico": "image/x-icon", ".bmp": "image/bmp", ".svg": "image/svg+xml",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
}
TEXTOS = {".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".svg": "image/svg+xml"}
PAGINAS = (".html", ".htm")
EXTRAS = (".css", ".js", ".mjs")
LIMITE_ARQUIVO = 5 * 1024 * 1024
LIMITE_TOTAL = 40 * 1024 * 1024
PROFUNDIDADE_IMPORT = 5

_EXTERNO = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|$)", re.I)
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_CORPO = re.compile(r"^#[^\n]*\n\n(`{3,})[^\n]*\n(.*)\n\1\n?$", re.S)
_CABECALHO = re.compile(r"^---\n[\s\S]*?\n---\n?")
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_SCRIPT_SRC = re.compile(r"<script\b([^>]*?)\ssrc\s*=\s*([\"'])(.*?)\2([^>]*)>\s*</script\s*>", re.I | re.S)
_STYLE = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.I | re.S)
_ATTR_STYLE = re.compile(r"(\sstyle\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
_ATTR_SRC = re.compile(r"(<(?:img|source|image|video|audio|track|input|embed)\b[^>]*?\s(?:src|poster)\s*=\s*)([\"'])(.*?)\2",
                       re.I | re.S)
_URL = re.compile(r"url\(\s*([\"']?)([^\"')]*?)\1\s*\)", re.I)
_IMPORT = re.compile(r"@import\s+(?:url\(\s*)?([\"'])([^\"']+)\1\s*\)?\s*([^;]*);", re.I)


class NaoRenderizavel(Exception):
    pass


def corpo_literal(conteudo):
    """O arquivo de origem dentro de uma nota literal (o inverso de literal.corpo_de)."""
    m = _CORPO.match(_CABECALHO.sub("", conteudo, count=1).lstrip("\n"))
    return m.group(2) if m else None


def _attr(tag, nome):
    m = re.search(rf"\s{nome}\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
    return m.group(2) if m else None


def _ext(caminho):
    return posixpath.splitext(caminho)[1].lower()


class Montador:
    def __init__(self, db, tag):
        self.db, self.tag = db, tag
        self.origens = {o["nome"]: o for o in db.execute("SELECT * FROM origens WHERE tag = ?", (tag,))}
        self.avisos, self.usados = [], []
        self.total = 0
        self._datas = {}

    # --- onde está cada arquivo ------------------------------------------------

    def chave(self, origem, caminho):
        prefixo = "" if origem == "principal" else origem + "/"
        return f"sistemas/{self.tag}/{literal.PASTA}/{prefixo}{caminho}"

    def nota(self, chave):
        """(origem, caminho, commit, texto) de uma nota literal, ou NaoRenderizavel."""
        n = self.db.execute("SELECT * FROM notas_indice WHERE tag = ? AND chave = ?", (self.tag, chave)).fetchone()
        if not n:
            raise NaoRenderizavel(f"{chave}: a nota não existe")
        refs = _json_lista(n["origens"])
        texto = corpo_literal(n["conteudo"]) if n["tipo_nota"] == literal.TIPO_NOTA else None
        if texto is None or len(refs) != 1:
            raise NaoRenderizavel(f"{chave}: não é uma nota literal de Referência")
        origem, caminho = estado.separar_ref(refs[0])
        o = self.origens.get(origem)
        commit = n["commit_origem"] or (o["commit_processado"] if o else None)
        return origem, caminho, commit, texto

    def texto(self, origem, caminho):
        try:
            return self.nota(self.chave(origem, caminho))[3]
        except NaoRenderizavel:
            return None

    def binario(self, origem, caminho, commit):
        """Bytes do arquivo no clone da origem, ou (None, motivo). A leitura é a de vault_system.arquivos."""
        if origem not in self.origens:
            return None, "origem desconhecida"
        if not commit or not _COMMIT.match(commit):
            return None, "sem commit da origem"
        dados, motivo = arquivos.ler_blob(self.tag, origem, commit, caminho, limite=LIMITE_ARQUIVO)
        if dados is None:
            return None, motivo
        if self.total + len(dados) > LIMITE_TOTAL:
            return None, "a página passou do limite total de arquivos embutidos"
        return dados, None

    # --- referências -------------------------------------------------------------

    def resolver(self, base, ref):
        """`ref` relativa ao arquivo `base` (origem, caminho): (origem, caminho), None
        se for externa (http, data:, #) ou levantar aviso se sair da origem."""
        ref = ref.strip()
        if _EXTERNO.match(ref):
            return None
        limpo = unquote(re.split(r"[?#]", ref, maxsplit=1)[0])
        if limpo.startswith("/"):
            raise NaoRenderizavel(f"{ref}: caminho absoluto, não sei de que raiz")
        caminho = posixpath.normpath(posixpath.join(posixpath.dirname(base[1]), limpo))
        if caminho == ".." or caminho.startswith("../"):
            raise NaoRenderizavel(f"{ref}: sai da origem")
        return base[0], caminho

    def data_uri(self, base, ref, commit):
        """`data:` do arquivo, ou None (com aviso) quando não dá."""
        try:
            alvo = self.resolver(base, ref)
        except NaoRenderizavel as e:
            self._avisar(base, str(e))
            return None
        if alvo is None:
            return None
        if alvo in self._datas:
            return self._datas[alvo]
        ext = _ext(alvo[1])
        uri = None
        if ext in TEXTOS:
            t = self.texto(*alvo)
            if t is not None:
                uri = f"data:{TEXTOS[ext]};base64,{base64.b64encode(t.encode()).decode()}"
        if uri is None and ext in BINARIOS:
            dados, motivo = self.binario(alvo[0], alvo[1], commit)
            if dados is None:
                self._avisar(base, f"{ref}: {motivo}")
            else:
                self.total += len(dados)
                uri = f"data:{BINARIOS[ext]};base64,{base64.b64encode(dados).decode()}"
        elif uri is None:
            self._avisar(base, f"{ref}: não está no vault de Referência")
        if uri:
            self.usados.append(estado.ref(*alvo))
        self._datas[alvo] = uri
        return uri

    def _avisar(self, base, texto):
        a = f"{base[1]}: {texto}"
        if a not in self.avisos:
            self.avisos.append(a)

    # --- CSS e HTML ----------------------------------------------------------------

    def css(self, base, texto, commit, profundidade=0):
        def importar(m):
            try:
                alvo = self.resolver(base, m.group(2))
            except NaoRenderizavel as e:
                self._avisar(base, str(e))
                return m.group(0)
            if alvo is None:
                return m.group(0)
            t = self.texto(*alvo)
            if t is None or profundidade >= PROFUNDIDADE_IMPORT:
                self._avisar(base, f"{m.group(2)}: não está no vault de Referência")
                return m.group(0)
            self.usados.append(estado.ref(*alvo))
            dentro = self.css(alvo, t, commit, profundidade + 1)
            midia = m.group(3).strip()
            return f"@media {midia}{{\n{dentro}\n}}" if midia else dentro

        def url(m):
            uri = self.data_uri(base, m.group(2), commit)
            return f'url("{uri}")' if uri else m.group(0)

        return _URL.sub(url, _IMPORT.sub(importar, texto))

    def html(self, base, texto, commit):
        def link(m):
            tag, href = m.group(0), _attr(m.group(0), "href")
            if href is None:
                return tag
            rel = (_attr(tag, "rel") or "").lower().split()
            if "stylesheet" in rel:
                try:
                    alvo = self.resolver(base, href)
                except NaoRenderizavel as e:
                    self._avisar(base, str(e))
                    return tag
                if alvo is None:
                    return tag
                t = self.texto(*alvo)
                if t is None:
                    self._avisar(base, f"{href}: não está no vault de Referência")
                    return tag
                self.usados.append(estado.ref(*alvo))
                midia = _attr(tag, "media")
                return (f'<style data-arquivo="{alvo[1]}"{f" media={chr(34)}{midia}{chr(34)}" if midia else ""}>\n'
                        f"{_seguro(self.css(alvo, t, commit), 'style')}\n</style>")
            uri = self.data_uri(base, href, commit)
            return tag.replace(href, uri, 1) if uri else tag

        def script(m):
            src = m.group(3)
            try:
                alvo = self.resolver(base, src)
            except NaoRenderizavel as e:
                self._avisar(base, str(e))
                return m.group(0)
            if alvo is None:
                return m.group(0)
            t = self.texto(*alvo)
            if t is None:
                self._avisar(base, f"{src}: não está no vault de Referência")
                return m.group(0)
            self.usados.append(estado.ref(*alvo))
            return f'<script{m.group(1)}{m.group(4)} data-arquivo="{alvo[1]}">\n{_seguro(t, "script")}\n</script>'

        def src(m):
            uri = self.data_uri(base, m.group(3), commit)
            return f"{m.group(1)}{m.group(2)}{uri}{m.group(2)}" if uri else m.group(0)

        texto = _SCRIPT_SRC.sub(script, texto)
        texto = _LINK.sub(link, texto)
        texto = _STYLE.sub(lambda m: m.group(1) + self.css(base, m.group(2), commit) + m.group(3), texto)
        texto = _ATTR_STYLE.sub(lambda m: m.group(1) + m.group(2) + self.css(base, m.group(3), commit) + m.group(2), texto)
        return _ATTR_SRC.sub(src, texto)


def _seguro(texto, elemento):
    """Texto dentro de <style>/<script> sem fechar o elemento antes da hora."""
    return re.sub(rf"</({elemento})", r"<\\/\1", texto, flags=re.I)


def _json_lista(texto):
    import json
    try:
        v = json.loads(texto) if texto else []
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def _antes(texto, fechamento, trecho):
    """Põe `trecho` antes do último `</head>`/`</body>`, ou no fim."""
    i = texto.lower().rfind(fechamento)
    return texto[:i] + trecho + texto[i:] if i >= 0 else texto + trecho


def montar(db, tag, pagina, extras=()):
    """A página `pagina` (chave da nota) com tudo embutido e os `extras` (chaves
    de notas CSS/JS) no fim do <head>/<body>."""
    m = Montador(db, tag)
    origem, caminho, commit, texto = m.nota(pagina)
    if _ext(caminho) not in PAGINAS:
        raise NaoRenderizavel(f"{caminho}: a página precisa ser um arquivo .html")
    saida = m.html((origem, caminho), texto, commit)
    for chave in extras:
        o, c, cm, t = m.nota(chave)
        if _ext(c) not in EXTRAS:
            raise NaoRenderizavel(f"{c}: só CSS ou JS entram como extra")
        m.usados.append(estado.ref(o, c))
        if _ext(c) == ".css":
            saida = _antes(saida, "</head>", f'<style data-arquivo="{c}">\n{_seguro(m.css((o, c), t, cm), "style")}\n</style>\n')
        else:
            saida = _antes(saida, "</body>", f'<script data-arquivo="{c}">\n{_seguro(t, "script")}\n</script>\n')
    return {"html": saida, "pagina": {"chave": pagina, "origem": origem, "caminho": caminho, "commit": commit},
            "usados": list(dict.fromkeys(m.usados)), "avisos": m.avisos, "bytes": len(saida.encode())}
