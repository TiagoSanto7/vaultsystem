"""Infraestrutura de containers: o código lê os fatos, o curador explica.

Arquivos de infra (1ª versão: containers): Dockerfile, compose, .dockerignore,
nginx e Caddy. O leitor é determinístico e não guarda valor de variável, só o
nome. O modelo de uma tag sai do clone de cada origem, no último commit
ingerido, dos arquivos de infra de qualquer leitura (inclusive Referência):

    {"servicos": {nome: {...fatos..., "arquivos": [refs]}}, "soltos": [refs], "avisos": [...]}

Um serviço vem de um compose (um por `services:`) ou de um Dockerfile que
nenhum compose usa (nome = pasta, ou a tag na raiz). Ao serviço se juntam o
Dockerfile do build, os .conf de proxy e o .dockerignore do contexto e os
arquivos de infra montados como volume.

Notas: `infra/<serviço>.md` e `infra/visao-geral.md`. O cabeçalho de fatos é
gravado pelo código (carimbar), a cada rodada; o curador escreve o texto.
"""
import json
import os
import posixpath
import re

from . import estado, filtros, ingestao, notas

ENV_EXEMPLOS = tuple(sorted(filtros.ENV_EXEMPLO))

PASTA = "infra"
TIPO_NOTA = "infra"
VISAO_GERAL = "visao-geral"
CAMPOS = ("stack", "servico", "container", "imagem", "build", "portas", "volumes", "redes", "depende_de", "healthcheck",
          "restart", "proxy", "externos")  # gravados pelo código no cabeçalho da nota de infra


# --- quais arquivos -------------------------------------------------------------------

def tipo_arquivo(caminho):
    """dockerfile, compose, dockerignore, nginx, caddy ou None."""
    nome = posixpath.basename(caminho)
    baixo = nome.lower()
    if baixo == "dockerfile" or baixo.startswith("dockerfile.") or baixo.endswith(".dockerfile"):
        return "dockerfile"
    if re.fullmatch(r"(docker-)?compose([.-][\w.-]+)?\.ya?ml", baixo):
        return "compose"
    if baixo == ".dockerignore":
        return "dockerignore"
    if baixo == "caddyfile" or baixo.startswith("caddyfile."):
        return "caddy"
    if baixo.endswith(".conf") and ("nginx" in baixo or "/nginx" in "/" + posixpath.dirname(caminho).lower()
                                   or baixo in ("default.conf", "site.conf")):
        return "nginx"
    return None


def e_infra(caminho):
    return tipo_arquivo(caminho) is not None


def slug(nome):
    s = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")
    return s or "servico"


# --- YAML -------------------------------------------------------------------------------

def carregar_yaml(texto):
    """O YAML como dict. PyYAML quando existe; senão um leitor do básico do compose
    (mapas, listas, textos com aspas, listas e mapas em uma linha, blocos | e >)."""
    try:
        import yaml
    except ImportError:
        return _MiniYaml(texto).documento()
    return yaml.safe_load(texto)


class _MiniYaml:
    def __init__(self, texto):
        self.linhas, self.blocos = [], []
        bloco = None  # (recuo da chave, estilo | ou >, linhas do bloco)
        for bruta in texto.replace("\t", "  ").split("\n"):
            recuo = len(bruta) - len(bruta.lstrip(" "))
            if bloco is not None:
                if not bruta.strip() or recuo > bloco[0]:
                    bloco[2].append(bruta.strip())
                    continue
                bloco = None
            limpa = _sem_comentario(bruta).rstrip()
            if not limpa.strip() or limpa.strip() in ("---", "..."):
                continue
            m = re.search(r":\s*([|>])[-+]?\d*$", limpa)
            if m:
                bloco = (recuo, m.group(1), [])
                self.blocos.append(bloco)
                limpa = limpa[:m.start(1)] + f'"\0bloco{len(self.blocos) - 1}"'
            self.linhas.append((recuo, limpa.strip()))
        self.i = 0

    def documento(self):
        return self._blocos(self._valor(0)) if self.linhas else None

    def _blocos(self, v):
        """Troca a marca de cada bloco | ou > pelo texto dele (| mantém as quebras, > junta com espaço)."""
        if isinstance(v, dict):
            return {k: self._blocos(x) for k, x in v.items()}
        if isinstance(v, list):
            return [self._blocos(x) for x in v]
        if isinstance(v, str) and v.startswith("\0bloco"):
            _, estilo, linhas = self.blocos[int(v[6:])]
            while linhas and not linhas[-1]:
                linhas.pop()
            return ("\n".join(linhas) if estilo == "|" else " ".join(l for l in linhas if l)) + "\n"
        return v

    def _valor(self, recuo):
        if self.i >= len(self.linhas):
            return None
        r, linha = self.linhas[self.i]
        if r < recuo:
            return None
        return self._lista(r) if linha.startswith("- ") or linha == "-" else self._mapa(r)

    def _mapa(self, recuo):
        saida = {}
        while self.i < len(self.linhas):
            r, linha = self.linhas[self.i]
            if r != recuo or linha.startswith("- "):
                break
            chave, valor = _par(linha)
            self.i += 1
            if valor == "":
                prox = self.linhas[self.i][0] if self.i < len(self.linhas) else -1
                eh_lista = self.i < len(self.linhas) and self.linhas[self.i][1].startswith("-")
                saida[chave] = self._valor(prox) if prox > recuo or (prox == recuo and eh_lista) else None
            else:
                saida[chave] = _escalar(valor)
        return saida

    def _lista(self, recuo):
        saida = []
        while self.i < len(self.linhas):
            r, linha = self.linhas[self.i]
            if r != recuo or not (linha.startswith("- ") or linha == "-"):
                break
            resto = linha[1:].strip()
            if not resto:
                self.i += 1
                saida.append(self._valor(self.linhas[self.i][0]) if self.i < len(self.linhas) else None)
            elif re.match(r"^[^'\"\[{][^:]*:(\s|$)", resto) or re.match(r"^['\"][^'\"]+['\"]:(\s|$)", resto):
                # "- chave: valor": um mapa que começa na linha do traço
                self.linhas[self.i] = (r + 2, resto)
                saida.append(self._mapa(r + 2))
            else:
                self.i += 1
                saida.append(_escalar(resto))
        return saida


def _sem_comentario(linha):
    aspas = None
    for i, c in enumerate(linha):
        if c in "'\"" and aspas in (None, c):
            aspas = None if aspas else c
        elif c == "#" and aspas is None and (i == 0 or linha[i - 1] in " \t"):
            return linha[:i]
    return linha


def _par(linha):
    m = re.match(r"""^("[^"]*"|'[^']*'|[^:]+?)\s*:(?:\s+(.*))?$""", linha)
    if not m:
        return linha, None
    return m.group(1).strip("'\""), (m.group(2) or "").strip()


def _escalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [_escalar(x) for x in _dividir(v[1:-1]) if x.strip()]
    if v.startswith("{") and v.endswith("}"):
        return {k: _escalar(x) for k, x in (_par(p.strip()) for p in _dividir(v[1:-1]) if p.strip())}
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if v in ("true", "false"):
        return v == "true"
    if v in ("null", "~"):
        return None
    return v


def _dividir(texto):
    partes, atual, nivel, aspas = [], "", 0, None
    for c in texto:
        if c in "'\"" and aspas in (None, c):
            aspas = None if aspas else c
        elif aspas is None and c in "[{":
            nivel += 1
        elif aspas is None and c in "]}":
            nivel -= 1
        if c == "," and nivel == 0 and aspas is None:
            partes.append(atual)
            atual = ""
        else:
            atual += c
    return partes + [atual]


# --- leitores ---------------------------------------------------------------------------

def _instrucoes(texto):
    """(INSTRUÇÃO, argumentos) do Dockerfile, com as linhas continuadas por \\ juntas."""
    atual = ""
    for linha in texto.split("\n"):
        s = linha.strip()
        if not atual and (not s or s.startswith("#")):
            continue
        if s.endswith("\\"):
            atual += s[:-1] + " "
            continue
        atual += s
        partes = atual.split(None, 1)
        if partes:
            yield partes[0].upper(), (partes[1] if len(partes) > 1 else "").strip()
        atual = ""


def _nomes_de_atribuicao(args):
    """Nomes de `A=1 B=2` ou `A 1` (ENV/ARG), sem os valores."""
    if "=" not in args.split(None, 1)[0]:
        return [args.split(None, 1)[0]] if args else []
    return [p.split("=", 1)[0] for p in re.findall(r"""(\w[\w.-]*=(?:"[^"]*"|'[^']*'|\S*))""", args)]


def _forma_exec(args):
    try:
        v = json.loads(args)
        return " ".join(v) if isinstance(v, list) else args
    except ValueError:
        return args


def ler_dockerfile(texto):
    d = {"estagios": [], "expose": [], "healthcheck": None, "user": None, "cmd": None, "entrypoint": None,
         "workdir": None, "args": [], "envs": [], "copia": []}
    for inst, args in _instrucoes(texto):
        if inst == "FROM":
            m = re.match(r"(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", args, re.I)
            if m:
                d["estagios"].append({"imagem": m.group(1), "nome": m.group(2)})
        elif inst == "EXPOSE":
            d["expose"] += args.split()
        elif inst == "HEALTHCHECK":
            d["healthcheck"] = None if args.upper() == "NONE" else re.sub(r"^.*?\bCMD\s+", "", args, flags=re.I)
        elif inst in ("USER", "WORKDIR"):
            d[inst.lower()] = args
        elif inst in ("CMD", "ENTRYPOINT"):
            d[inst.lower()] = _forma_exec(args)
        elif inst in ("ARG", "ENV"):
            for nome in _nomes_de_atribuicao(args):
                lista = d["args" if inst == "ARG" else "envs"]
                if nome not in lista:
                    lista.append(nome)
        elif inst in ("COPY", "ADD"):
            partes = [p for p in args.split() if not p.startswith("--")]
            if len(partes) >= 2 and not args.lstrip().startswith("--from"):
                d["copia"] += partes[:-1]
    return d


def _porta(p):
    if isinstance(p, dict):
        alvo, pub = p.get("target"), p.get("published")
        texto = f"{pub}:{alvo}" if pub else str(alvo)
        return texto + (f"/{p['protocol']}" if p.get("protocol") and p["protocol"] != "tcp" else "")
    return str(p)


def _volume(v):
    if isinstance(v, dict):
        texto = f"{v.get('source')}:{v.get('target')}" if v.get("source") else str(v.get("target"))
        return texto + (":ro" if v.get("read_only") else "")
    return str(v)


def _nomes_env(env):
    if isinstance(env, dict):
        return sorted(str(k) for k in env)
    if isinstance(env, list):
        return sorted({str(e).split("=", 1)[0] for e in env})
    return []


def _lista(v):
    if v is None:
        return []
    if isinstance(v, dict):
        return [str(k) for k in v]
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _destinos_env(env):
    """{VAR: (tipo, host:porta)} das variáveis do compose cujo valor aponta para fora; o valor não fica."""
    pares = env.items() if isinstance(env, dict) else (
        (str(e).split("=", 1) + [""])[:2] for e in env) if isinstance(env, list) else ()
    saida = {}
    for nome, valor in pares:
        d = destino(str(nome), "" if valor is None else str(valor))
        if d:
            saida[str(nome)] = d
    return saida


def ler_compose(texto):
    try:
        doc = carregar_yaml(texto) or {}
    except Exception as e:  # noqa: BLE001 - YAML com erro vira aviso, não derruba a rodada
        # Só a linha: a mensagem do PyYAML traz um pedaço do arquivo, que pode ter valor de segredo.
        marca = getattr(e, "problem_mark", None)
        return {"servicos": {}, "volumes": [], "redes": [],
                "erro": "YAML inválido" + (f" (linha {marca.line + 1})" if marca else "")}
    if not isinstance(doc, dict):
        return {"servicos": {}, "volumes": [], "redes": [], "erro": "o arquivo não é um mapa"}
    servicos = {}
    for nome, s in (doc.get("services") or {}).items():
        s = s if isinstance(s, dict) else {}
        build = s.get("build")
        if isinstance(build, str):
            build = {"context": build}
        elif isinstance(build, dict):
            build = {k: build[k] for k in ("context", "dockerfile", "target") if build.get(k)}
        hc = s.get("healthcheck") if isinstance(s.get("healthcheck"), dict) else {}
        teste = hc.get("test")
        if isinstance(teste, list):
            teste = " ".join(str(x) for x in teste if x not in ("CMD", "CMD-SHELL"))
        logging = s.get("logging") if isinstance(s.get("logging"), dict) else {}
        servicos[str(nome)] = {
            "container": s.get("container_name"), "imagem": s.get("image"), "build": build or None,
            "portas": [_porta(p) for p in s.get("ports") or []], "expose": [str(p) for p in s.get("expose") or []],
            "volumes": [_volume(v) for v in s.get("volumes") or []], "redes": _lista(s.get("networks")),
            "depende_de": _lista(s.get("depends_on")), "healthcheck": None if hc.get("disable") else teste,
            "restart": s.get("restart"), "logging": logging.get("driver"), "env": _nomes_env(s.get("environment")),
            "env_file": _lista(s.get("env_file")), "env_destinos": _destinos_env(s.get("environment")), "comando": _forma_exec(json.dumps(s["command"]))
            if isinstance(s.get("command"), list) else s.get("command")}
    return {"servicos": servicos, "volumes": _lista(doc.get("volumes")), "redes": _lista(doc.get("networks")),
            "nome": str(doc["name"]) if doc.get("name") else None}


def ler_nginx(texto):
    sem = re.sub(r"#[^\n]*", "", texto)
    locais = []
    for m in re.finditer(r"location\s+([^{]+?)\s*\{([^{}]*)\}", sem):
        corpo = m.group(2)
        destino = re.search(r"proxy_pass\s+([^;]+);", corpo)
        retorno = re.search(r"return\s+([^;]+);", corpo)
        raiz = re.search(r"(?:root|alias)\s+([^;]+);", corpo)
        locais.append({"caminho": m.group(1).strip(), "proxy_pass": destino.group(1).strip() if destino else None,
                       "return": retorno.group(1).strip() if retorno else None,
                       "root": raiz.group(1).strip() if raiz else None})
    return {"listen": re.findall(r"listen\s+([^;]+);", sem), "server_name": re.findall(r"server_name\s+([^;]+);", sem),
            "root": re.findall(r"^\s*root\s+([^;]+);", sem, re.M), "upstreams": re.findall(r"upstream\s+(\S+)\s*\{", sem),
            "locations": locais}


def ler_caddy(texto):
    sem = re.sub(r"#[^\n]*", "", texto)
    return {"sites": [s.strip() for s in re.findall(r"^([^\s{][^{\n]*)\{", sem, re.M)],
            "reverse_proxy": re.findall(r"reverse_proxy\s+(?:\S+\s+)?([\w.:/-]+)", sem)}


def ler_dockerignore(texto):
    return {"padroes": [l.strip() for l in texto.split("\n") if l.strip() and not l.strip().startswith("#")]}


LEITORES = {"dockerfile": ler_dockerfile, "compose": ler_compose, "nginx": ler_nginx, "caddy": ler_caddy,
            "dockerignore": ler_dockerignore}


# --- dependências externas ---------------------------------------------------------
# Banco, AD/LDAP, SAP e serviços HTTP que o container usa sem eles fazerem parte do stack. Vêm do
# .env.example do repositório (o .env real nunca é lido) e do environment: do compose. Do valor, o
# código guarda só o tipo e o host:porta; usuário, senha, caminho e query nunca saem daqui.

ESQUEMAS = (("mysql", "mysql"), ("mariadb", "mysql"), ("postgres", "postgres"), ("postgresql", "postgres"),
            ("mssql", "sqlserver"), ("sqlserver", "sqlserver"), ("oracle", "oracle"), ("mongodb", "mongodb"),
            ("rediss", "redis"), ("redis", "redis"), ("amqps", "rabbitmq"), ("amqp", "rabbitmq"),
            ("ldaps", "ldap"), ("ldap", "ldap"), ("smtps", "smtp"), ("smtp", "smtp"), ("https", "http"),
            ("http", "http"))
POR_NOME = (("sap", ("SL_", "SAP_", "HANA_", "B1_", "SERVICE_LAYER")), ("smtp", ("SMTP_",)), ("ldap", ("LDAP_",)))
HOST_SOLTO = re.compile(r"(_IP|_HOST|_SERVER|_SERVIDOR)(_|$)", re.I)  # HANA_IP_PROD=10.0.0.1: endereço sem URL
ROTULO_EXTERNO = {"mysql": "MySQL", "postgres": "PostgreSQL", "sqlserver": "SQL Server", "oracle": "Oracle",
                  "mongodb": "MongoDB", "redis": "Redis", "rabbitmq": "RabbitMQ", "ldap": "AD / LDAP",
                  "smtp": "E-mail (SMTP)", "sap": "SAP", "http": "Serviço HTTP"}
BANCOS = ("mysql", "postgres", "sqlserver", "oracle", "mongodb")
# Endereço não aparece em lugar nenhum (decisão de 03/11: nem IP nem host no mapa, na nota ou no lote).
# O que sai é o ambiente, pelo sufixo da variável.
AMBIENTES = (("produção", re.compile(r"_(PROD|PRD|PRODUCAO)(_|$)", re.I)),
             ("homologação", re.compile(r"_(HOMO|HML|HOMOLOG|HOMOLOGACAO|STAGING|STG)(_|$)", re.I)),
             ("desenvolvimento", re.compile(r"_(DEV|DESENV)(_|$)", re.I)))


def ambiente(variavel):
    return next((nome for nome, rx in AMBIENTES if rx.search(variavel)), None)
LOCAIS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal")


def _tipo_por_nome(nome):
    return next((t for t, prefixos in POR_NOME if nome.upper().startswith(prefixos)), None)


def destino(nome, valor):
    """(tipo, host:porta ou None) do que a variável aponta, ou None. Só o host e a porta saem do valor.
    Endereço local (localhost, 0.0.0.0) não é endereço: fica só o tipo."""
    from urllib.parse import urlsplit
    v = valor.strip().strip("'\"").split(",")[0].strip()  # lista de servidores: o primeiro
    m = re.match(r"([a-z][a-z0-9.+-]*)://", v, re.I)
    if m:
        esquema = m.group(1).lower().split("+")[0]
        tipo = next((t for e, t in ESQUEMAS if esquema == e), None)
        if tipo:
            if tipo == "http":
                tipo = _tipo_por_nome(nome) or tipo  # SERVICE_LAYER_PROD=https://... é SAP
            try:
                u = urlsplit(v)
                host, porta = u.hostname, u.port
            except ValueError:
                host, porta = None, None
            if not host or host in LOCAIS or not re.fullmatch(r"[a-z0-9.-]+", host, re.I):
                return tipo, None
            return tipo, (f"{host}:{porta}" if porta else host)
    tipo = _tipo_por_nome(nome)
    if tipo and HOST_SOLTO.search(nome) and re.fullmatch(r"[a-z0-9][a-z0-9.-]*", v, re.I) and v not in LOCAIS:
        return tipo, v
    return (tipo, None) if tipo else None


def ler_env_exemplo(texto):
    """{VAR: (tipo, host:porta)} de um .env.example (só o que aponta para fora)."""
    saida = {}
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.removeprefix("export ").split("=", 1)
        nome = nome.strip()
        valor = re.split(r"\s+#", valor, maxsplit=1)[0]
        d = destino(nome, valor)
        if d and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
            saida[nome] = d
    return saida


# --- modelo da tag ----------------------------------------------------------------------

def _dentro(caminho, pasta):
    pasta = posixpath.normpath(pasta)
    return pasta in (".", "") or caminho == pasta or caminho.startswith(pasta + "/")


def _proxy(info):
    """`location → destino` de um nginx ou Caddy, para o cabeçalho."""
    if "locations" in info:
        return [f"{l['caminho']} → {l['proxy_pass'] or ('return ' + l['return'] if l['return'] else 'arquivos')}"
                for l in info["locations"]]
    return [f"→ {d}" for d in info.get("reverse_proxy", [])]


def nome_de_projeto(texto):
    """Como o docker compose normaliza o nome do projeto: minúsculas, só [a-z0-9_-], começando por letra ou número."""
    return re.sub(r"^[^a-z0-9]+", "", re.sub(r"[^a-z0-9_-]", "", texto.lower())) or "projeto"


def modelo(arquivos, padrao="app", raizes=None, exemplos=None):
    """O modelo a partir de {ref: (caminho, texto)} (ref = estado.ref(origem, caminho)).
    Stack: cada compose é um stack, com o nome do projeto como o docker compose dá: o `name:` do
    arquivo ou a pasta dele; na raiz, o nome do repositório (`raizes`: {prefixo da origem: nome}) ou `padrao`."""
    raizes = raizes or {}
    exemplos = exemplos or {}  # {ref do .env.example: {VAR: (tipo, host:porta)}}
    lidos = {ref: (caminho, tipo_arquivo(caminho), LEITORES[tipo_arquivo(caminho)](texto))
             for ref, (caminho, texto) in sorted(arquivos.items()) if tipo_arquivo(caminho)}
    usados, servicos, avisos = set(), {}, []

    def juntar(nome, fatos, refs):
        chave = nome
        if chave in servicos:  # mesmo nome em outro stack: o nome do stack na frente (a nota não se perde)
            chave = slug(f"{fatos.get('stack') or 'sem-compose'}-{nome}")
            n = 2
            while chave in servicos:
                chave, n = slug(f"{fatos.get('stack') or 'sem-compose'}-{nome}-{n}"), n + 1
        servicos[chave] = {**fatos, "arquivos": refs}

    for ref, (caminho, tipo, info) in lidos.items():
        if tipo != "compose":
            continue
        usados.add(ref)
        if info.get("erro"):
            avisos.append(f"{ref}: {info['erro']}")
        base = posixpath.dirname(caminho)
        prefixo = ref[: len(ref) - len(caminho)]
        stack = nome_de_projeto(info.get("nome") or (posixpath.basename(base) if base else
                                                     raizes.get(prefixo, padrao)))
        for nome, s in info["servicos"].items():
            refs, df, extra = [ref], None, {}
            if s.get("build"):
                ctx = posixpath.normpath(posixpath.join(base, s["build"].get("context", ".")))
                alvo = posixpath.normpath(posixpath.join(ctx, s["build"].get("dockerfile", "Dockerfile")))
                for r2, (c2, t2, i2) in lidos.items():
                    if r2.startswith(prefixo) and t2 != "compose" and (c2 == alvo or (
                            t2 in ("nginx", "caddy", "dockerignore") and _dentro(c2, ctx))):
                        refs.append(r2)
                        usados.add(r2)
                        if c2 == alvo:
                            df = i2
                        elif t2 in ("nginx", "caddy"):
                            extra.setdefault("proxy", []).extend(_proxy(i2))
            for v in s["volumes"]:  # arquivo de infra montado no container
                origem_vol = v.split(":", 1)[0]
                if origem_vol.startswith((".", "/")):
                    c2 = posixpath.normpath(posixpath.join(base, origem_vol))
                    r2 = prefixo + c2
                    if r2 in lidos and r2 not in refs:
                        refs.append(r2)
                        usados.add(r2)
                        if lidos[r2][1] in ("nginx", "caddy"):
                            extra.setdefault("proxy", []).extend(_proxy(lidos[r2][2]))
            fatos = dict(s)
            fatos["servico"] = nome
            fatos["stack"], fatos["stack_arquivo"] = stack, ref
            # Externos: o environment: do compose e, se o serviço carrega um env_file, o exemplo dele
            # (o .env.example ao lado do arquivo que ele carrega).
            externos = {v: (t, h, ref) for v, (t, h) in (s.get("env_destinos") or {}).items()}
            for ef in s.get("env_file") or []:
                alvo = posixpath.normpath(posixpath.join(base, str(ef)))
                for ex in ENV_EXEMPLOS:
                    r2 = prefixo + posixpath.normpath(posixpath.join(posixpath.dirname(alvo), ex))
                    for v, (t, h) in exemplos.get(r2, {}).items():
                        externos.setdefault(v, (t, h, r2))
            fatos["externos"] = externos
            fatos.pop("env_destinos", None)
            if df:
                fatos["dockerfile"] = df
                fatos["healthcheck"] = fatos["healthcheck"] or df["healthcheck"]
                fatos["imagem"] = fatos["imagem"] or None
                fatos["base"] = [e["imagem"] for e in df["estagios"]]
            fatos.update(extra)
            juntar(slug(nome), fatos, refs)

    for ref, (caminho, tipo, info) in lidos.items():
        if tipo != "dockerfile" or ref in usados:
            continue
        pasta = posixpath.dirname(caminho)
        nome = posixpath.basename(pasta) if pasta else padrao
        refs, extra = [ref], {}
        prefixo = ref[: len(ref) - len(caminho)]
        for r2, (c2, t2, i2) in lidos.items():
            if r2 not in usados and r2.startswith(prefixo) and t2 in ("nginx", "caddy", "dockerignore") \
                    and _dentro(c2, pasta):
                refs.append(r2)
                usados.add(r2)
                if t2 in ("nginx", "caddy"):
                    extra.setdefault("proxy", []).extend(_proxy(i2))
        usados.add(ref)
        juntar(slug(nome), {"servico": nome, "container": None, "imagem": None, "build": {"context": pasta or "."},
                            "portas": [], "expose": info["expose"], "volumes": [], "redes": [], "depende_de": [],
                            "healthcheck": info["healthcheck"], "restart": None, "env": info["envs"],
                            "env_file": [], "dockerfile": info, "base": [e["imagem"] for e in info["estagios"]],
                            "stack": None, "stack_arquivo": None, "externos": {}, **extra}, refs)
    # Externos: o host serve só para saber se é serviço do próprio vault (http://web:8000) e para
    # contar destinos diferentes; depois vira um identificador opaco (d1, d2...): endereço não sai daqui.
    internos = {s["servico"] for s in servicos.values()} | {s["container"] for s in servicos.values() if s.get("container")}
    opacos = {}
    for s in servicos.values():
        ext = {}
        for v, (t, h, r) in (s.get("externos") or {}).items():
            if h and h.split(":")[0] in internos:
                continue
            ext[v] = (t, opacos.setdefault(h, f"d{len(opacos) + 1}") if h else None, r)
        s["externos"] = ext
    return {"servicos": servicos, "soltos": sorted(set(lidos) - usados), "avisos": avisos,
            "arquivos": {ref: tipo for ref, (_, tipo, _) in lidos.items()}}


def ler_tag(db, tag):
    """O modelo da tag, do clone de cada origem no último commit ingerido."""
    arquivos, raizes, exemplos = {}, {}, {}
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome", (tag,)):
        repo = (o["repo"] or "").rstrip("/").removesuffix(".git")
        raizes["" if o["nome"] == "principal" else o["nome"] + ":"] = re.split(r"[/:]", repo)[-1] or tag
        commit = o["commit_pendente"] or o["commit_processado"]
        clone = ingestao.dir_clone(tag, o["nome"])
        if not commit or not os.path.isdir(os.path.join(clone, "objects")):
            continue
        leituras = json.loads(o["leituras"] or "[]")
        for caminho, blob, modo in ingestao.arvore(clone, commit):
            exemplo = posixpath.basename(caminho) in filtros.ENV_EXEMPLO
            if modo not in ("100644", "100755") or not (e_infra(caminho) or exemplo):
                continue
            perfil, _ = ingestao.leitura_de(caminho, leituras)
            if not perfil and not exemplo:  # o exemplo vale mesmo fora das leituras: dele sai só tipo e host
                continue
            try:
                dados = ingestao._git(["cat-file", "blob", blob], cwd=clone, binario=True)
            except ingestao.ErroIngestao:
                continue
            texto, motivo = filtros.por_conteudo(dados)
            if texto is None:
                continue
            texto = filtros.mascarar(texto)[0]  # a senha de URL vira máscara; o host fica
            if exemplo:
                exemplos[estado.ref(o["nome"], caminho)] = ler_env_exemplo(texto)
            else:
                arquivos[estado.ref(o["nome"], caminho)] = (caminho, texto)
    return modelo(arquivos, padrao=tag, raizes=raizes, exemplos=exemplos)


def servicos_do_arquivo(m, ref):
    return [nome for nome, s in m["servicos"].items() if ref in s["arquivos"]]


def resumo_fatos(s):
    """Os fatos do serviço que vão no lote, sem o que não ajuda a explicar."""
    saida = {k: v for k, v in s.items() if v not in (None, [], {}) and k not in ("arquivos", "externos")}
    if s.get("externos"):  # variável → tipo (nunca o valor nem o endereço)
        saida["externos"] = {v: ROTULO_EXTERNO.get(t, t) for v, (t, _h, _r) in sorted(s["externos"].items())}
    return saida


def cabecalho(s):
    """Os campos do cabeçalho da nota de infra, a partir dos fatos."""
    build = s.get("build") or {}
    return {"stack": s.get("stack"), "servico": s["servico"], "container": s.get("container"),
            "imagem": s.get("imagem") or (", ".join(s.get("base") or []) or None),
            "build": (build.get("context") + (f" ({build['dockerfile']})" if build.get("dockerfile") else ""))
            if build.get("context") else None,
            "portas": s.get("portas") or [], "volumes": s.get("volumes") or [], "redes": s.get("redes") or [],
            "depende_de": s.get("depende_de") or [], "healthcheck": s.get("healthcheck"),
            "restart": s.get("restart"), "proxy": s.get("proxy") or [],
            "externos": _externos_do_cabecalho(s)}


def _externos_do_cabecalho(s):
    """`Tipo (ambientes)` de cada externo do serviço, sem endereço."""
    por_tipo = {}
    for v, (t, _h, _r) in (s.get("externos") or {}).items():
        amb = por_tipo.setdefault(ROTULO_EXTERNO.get(t, t), set())
        if ambiente(v):
            amb.add(ambiente(v))
    return sorted(f"{r} ({', '.join(sorted(a))})" if a else r for r, a in por_tipo.items())


def nota(tag, nome):
    return os.path.join(notas.pasta_tag(tag), PASTA, f"{nome}.md")


def carimbar(db, tag, m=None, completar=None):
    """Regrava, em cada nota de infra, os fatos e as origens lidos pelo código (o curador não escreve
    esses campos; se o arquivo mudou e o curador não mexeu na nota, o cabeçalho acompanha).
    `completar`: campos para a nota que ficou sem cabeçalho do código (lote interrompido)."""
    pasta = os.path.join(notas.pasta_tag(tag), PASTA)
    if not os.path.isdir(pasta):
        return
    m = m or ler_tag(db, tag)
    todos = sorted({r for s in m["servicos"].values() for r in s["arquivos"]} | set(m["soltos"]))
    for nome in os.listdir(pasta):
        if not nome.endswith(".md"):
            continue
        c = os.path.join(pasta, nome)
        cab, corpo = notas.ler(c)
        chave = nome[:-3]
        if chave == VISAO_GERAL:
            novo = {"origens": todos} if todos else {}
        elif chave in m["servicos"]:
            s = m["servicos"][chave]
            novo = {**cabecalho(s), "origens": s["arquivos"]}
        else:
            continue  # serviço que não existe mais: o verificador acusa
        if completar and not cab.get("sistema"):
            agora = estado.agora()
            novo = {**completar, "criado_em": agora, "atualizado_em": agora, **novo}
            commit = db.execute("SELECT commit_pendente, commit_processado FROM origens WHERE tag = ? AND nome = ?",
                                (tag, estado.separar_ref(novo["origens"][0])[0] if novo.get("origens") else "")
                                ).fetchone()
            novo["commit_origem"] = (commit[0] or commit[1]) if commit else None
        atual = {**cab, **novo}
        atual = {k: v for k, v in atual.items() if not (k in CAMPOS and v in (None, []))}
        if atual != cab:
            notas.escrever(c, atual, corpo)


MOTIVO_ADOCAO = "infra: documentar em infra/"


def adotar(db, tag):
    """Arquivo de infra já processado antes do  (ou cuja nota sumiu) entra na fila **uma vez** para o
    curador documentar em infra/. Nunca de novo: o item fica marcado pelo motivo."""
    feitos = 0
    pasta = os.path.join(notas.pasta_tag(tag), PASTA)
    citados = set()
    if os.path.isdir(pasta):
        for nome in os.listdir(pasta):
            if nome.endswith(".md"):
                citados.update(notas.ler(os.path.join(pasta, nome))[0].get("origens") or [])
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome", (tag,)).fetchall():
        commit = o["commit_pendente"] or o["commit_processado"]
        clone = ingestao.dir_clone(tag, o["nome"])
        if not commit or not os.path.isdir(os.path.join(clone, "objects")):
            continue
        leituras = json.loads(o["leituras"] or "[]")
        resumo = {"ignorados": [], "mascarados": 0, "itens": {}, "origens": {}}
        novos = []
        for caminho, blob, modo in ingestao.arvore(clone, commit):
            if not e_infra(caminho) or estado.ref(o["nome"], caminho) in citados:
                continue
            perfil, _ = ingestao.leitura_de(caminho, leituras)
            if perfil not in ("codigo", "referencia-explicada"):
                continue
            if db.execute("SELECT 1 FROM fila WHERE tag = ? AND origem = ? AND caminho = ? AND perfil = ? "
                          "AND (motivo = ? OR estado = 'na_fila')",
                          (tag, o["nome"], caminho, perfil, MOTIVO_ADOCAO)).fetchone():
                continue
            item = ingestao._item(clone, tag, o["nome"], commit, "modificado", caminho, blob, modo, perfil, resumo)
            if item and item[0] == "modificado":
                novos.append((*item[:4], MOTIVO_ADOCAO))
        if novos:
            ingestao._enfileirar(db, tag, o["nome"], commit, novos, resumo)
            feitos += len(novos)
    if feitos:
        print(f"[infra] {tag}: {feitos} arquivo(s) de infra na fila para documentar em infra/ (uma vez)")
    return feitos


# --- grafo para o mapa ---------------------------------------------------------

TIPOS_POR_IMAGEM = (
    ("banco", ("postgres", "mysql", "mariadb", "mongo", "mssql", "sqlserver", "oracle", "cockroach", "clickhouse")),
    ("cache", ("redis", "memcached", "valkey", "keydb")),
    ("fila", ("rabbitmq", "kafka", "nats", "activemq", "mosquitto")),
    ("proxy", ("nginx", "caddy", "traefik", "haproxy", "envoy", "httpd")),
)


def tipo_servico(s):
    """banco, cache, fila, proxy (servidor web na frente), site (servidor web só com arquivos) ou app."""
    imagens = " ".join([s.get("imagem") or ""] + list(s.get("base") or [])).lower()
    for tipo, nomes in TIPOS_POR_IMAGEM:
        if any(n in imagens for n in nomes):
            if tipo == "proxy" and not destinos_do_proxy(s):
                return "site"
            return tipo
    return "app"


def destinos_do_proxy(s):
    """Hosts para onde o proxy do serviço manda (`http://api:8000/` → api)."""
    saida = []
    for linha in s.get("proxy") or []:
        m = re.search(r"(?:https?://)?([A-Za-z0-9_.-]+):\d+", linha.split("→", 1)[-1])
        if m and m.group(1) not in ("localhost", "127.0.0.1") and m.group(1) not in saida:
            saida.append(m.group(1))
    return saida


def _porta_publicada(p):
    """("8006", "80") de "8006:80", "127.0.0.1:8006:80/tcp"; (None, "80") de "80"."""
    p = str(p).split("/", 1)[0]
    partes = p.split(":")
    return (partes[-2], partes[-1]) if len(partes) >= 2 else (None, partes[0])


def grafo(db, tag, m=None):
    """O que o mapa de infraestrutura desenha: serviços, ligações e redes, só com o que os arquivos dizem."""
    m = m or ler_tag(db, tag)
    chaves = {l["chave"] for l in db.execute("SELECT chave FROM notas_indice WHERE tag = ? AND "
                                             "(pasta = ? OR pasta = 'referencia')", (tag, PASTA))}
    servicos, ligacoes = [], []
    nomes = {}
    for sid, s in m["servicos"].items():
        nomes[s["servico"]] = sid
        if s.get("container"):
            nomes[s["container"]] = sid
    for sid, s in m["servicos"].items():
        cab = cabecalho(s)
        portas = []
        for p in s.get("portas") or []:
            host, cont = _porta_publicada(p)
            portas.append({"host": host, "container": cont, "texto": str(p)})
        volumes = []
        for v in s.get("volumes") or []:
            partes = str(v).split(":")
            origem_v, destino = (partes[0], partes[1]) if len(partes) > 1 else (None, partes[0])
            volumes.append({"origem": origem_v, "destino": destino, "somente_leitura": partes[-1] == "ro",
                            "nomeado": bool(origem_v) and not origem_v.startswith((".", "/", "~", "$"))})
        arquivos = []
        for ref in s["arquivos"]:
            origem, caminho = estado.separar_ref(ref)
            lit = f"sistemas/{tag}/referencia/{'' if origem == 'principal' else origem + '/'}{caminho}"
            arquivos.append({"ref": ref, "tipo": m["arquivos"].get(ref), "nota": lit if lit in chaves else None})
        nota_chave = f"sistemas/{tag}/{PASTA}/{sid}"
        servicos.append({"id": sid, "nome": s["servico"], "stack": s.get("stack"), "tipo": tipo_servico(s),
                         "container": cab["container"],
                         "imagem": cab["imagem"], "build": cab["build"], "portas": portas,
                         "expose": [str(x) for x in s.get("expose") or []], "volumes": volumes,
                         "redes": cab["redes"], "healthcheck": cab["healthcheck"], "restart": cab["restart"],
                         "proxy": cab["proxy"], "env": s.get("env") or [], "arquivos": arquivos,
                         "nota": nota_chave if nota_chave in chaves else None})
        for d in s.get("depende_de") or []:
            if d in nomes:
                ligacoes.append({"de": sid, "para": nomes[d], "tipo": "depende"})
        for d in destinos_do_proxy(s):
            if d in nomes and nomes[d] != sid:
                ligacoes.append({"de": sid, "para": nomes[d], "tipo": "proxy"})
    # Dependências externas: uma por tipo e endereço; ligadas aos serviços que usam a variável.
    integracoes = [l["chave"] for l in db.execute("SELECT chave FROM notas_indice WHERE tag = ? AND pasta = "
                                                  "'integracoes'", (tag,))]
    n_dados = db.execute("SELECT COUNT(*) FROM notas_indice WHERE tag = ? AND pasta = 'dados'", (tag,)).fetchone()[0]
    chaves_nota = {"ldap": ("ldap", "ad-", "active-directory"), "sap": ("sap", "hana", "service-layer"),
                   "smtp": ("smtp", "email", "e-mail")}
    externos = {}
    for sid, s in m["servicos"].items():
        for var, (t, h, ref) in (s.get("externos") or {}).items():
            e = externos.setdefault((t, h), {"id": "ext-" + slug(f"{t}-{h or ''}"), "tipo": t,
                                             "rotulo": ROTULO_EXTERNO.get(t, t), "endereco": h, "variaveis": [],
                                             "servicos": [], "origens": []})
            for lista, valor in (("variaveis", var), ("servicos", sid), ("origens", ref)):
                if valor not in e[lista]:
                    e[lista].append(valor)
    # Host que é serviço do próprio vault (VIGIA_API_URL=http://web:8000) não é externo.
    for chave in [k for k in externos if k[1] and k[1].split(":")[0] in nomes]:
        externos.pop(chave)
    # Um card por tipo (o mapa fica legível): os endereços do tipo listados dentro, cada um com as variáveis.
    por_tipo = {}
    for (t, h), e in sorted(externos.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        p = por_tipo.setdefault(t, {"id": "ext-" + slug(t), "tipo": t, "rotulo": ROTULO_EXTERNO.get(t, t),
                                    "variaveis": [], "servicos": [], "origens": [], "destinos": 0})
        p["destinos"] += 1 if h else 0  # quantos endereços diferentes (só o número)
        for lista in ("variaveis", "servicos", "origens"):
            p[lista] += [x for x in e[lista] if x not in p[lista]]
    for p in por_tipo.values():
        if p["tipo"] == "http" and p["destinos"] > 1:
            p["rotulo"] = "Serviços HTTP"
        grupos = {}
        for v in sorted(p["variaveis"]):
            grupos.setdefault(ambiente(v) or "", []).append(v)
        ordem = [n for n, _ in AMBIENTES] + [""]
        p["ambientes"] = [{"ambiente": a or None, "variaveis": vs} for a, vs in
                          sorted(grupos.items(), key=lambda kv: ordem.index(kv[0]))]
    externos = por_tipo
    for e in externos.values():
        e["variaveis"].sort()
        e["notas"] = [c for c in integracoes if any(k in c.rsplit("/", 1)[-1] for k in chaves_nota.get(e["tipo"], ()))]
        e["notas_dados"] = n_dados if e["tipo"] in BANCOS else 0
        ligacoes += [{"de": sid, "para": e["id"], "tipo": "externo"} for sid in e["servicos"]]
    stacks = {}
    for sid, s in m["servicos"].items():  # na ordem dos arquivos; "sem compose" por último
        chave = s.get("stack") or ""
        st = stacks.setdefault(chave, {"id": chave, "nome": chave or "sem compose", "arquivo": s.get("stack_arquivo"),
                                       "servicos": []})
        st["servicos"].append(sid)
    ordem = sorted(stacks.values(), key=lambda st: (st["id"] == "", st["arquivo"] or "", st["nome"]))
    redes = sorted({(s["stack"] or "", r) for s in servicos for r in s["redes"]})
    geral = f"sistemas/{tag}/{PASTA}/{VISAO_GERAL}"
    ordem_tipo = list(ROTULO_EXTERNO)
    return {"servicos": servicos, "ligacoes": ligacoes, "stacks": ordem,
            "externos": sorted(externos.values(), key=lambda e: ordem_tipo.index(e["tipo"])),
            "redes": [{"stack": st, "nome": r} for st, r in redes], "avisos": m["avisos"],
            "soltos": m["soltos"], "visao_geral": geral if geral in chaves else None}
