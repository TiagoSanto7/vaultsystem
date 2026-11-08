"""Mapa de relações de um vault (DV-576).

O grafo sai só do índice das notas (`notas_indice`, que o curador grava a cada
rodada): nenhuma relação é inventada para preencher o desenho.

- **compõe:** origem → vault, pasta → vault e nota → pasta (de que é feito).
- **fundamenta:** origem → nota, pelo campo `origens` da nota (os arquivos de
  origem de onde a nota foi escrita).
- **documenta:** documento → assunto, pelas `evidencias` do assunto.
- **menciona:** os outros links `[[...]]` entre notas. É citação, não
  dependência confirmada.

Os índices gerados (`indices/`) ficam de fora: eles só listam as notas.

O mapa mostra a vizinhança de um nó por vez (o foco), com no máximo `limite`
notas; a tela pede mais ou muda o foco (expansão progressiva).
"""
import collections

from . import estado, notas

LIMITE = 24
LIMITE_MAX = 400
ROTULO_PASTA = {"documentos": "Documentos", "assuntos": "Assuntos", "modulos": "Módulos", "regras": "Regras",
                "integracoes": "Integrações", "apis": "APIs", "dados": "Dados",
                "referencia": "Referência", "guias": "Guias", "infra": "Infraestrutura"}
ORDEM_PASTAS = list(ROTULO_PASTA)
# Na lista de vizinhos, o que vem antes quando passa do limite.
PESO_RELACAO = {"documenta": 0, "menciona": 1}


def _repo_curto(repo):
    return repo.removeprefix("https://github.com/").removesuffix(".git").split(":")[-1]


class Grafo:
    def __init__(self, tag, origens, linhas):
        """`origens`: linhas da tabela origens; `linhas`: notas_indice da tag."""
        self.tag = tag
        self.origens = {o["nome"]: _repo_curto(o["repo"]) for o in origens}
        self.notas = {}
        for n in linhas:
            if n["pasta"] == "indices":
                continue
            cab, corpo = notas.separar(n["conteudo"])
            arquivos = collections.defaultdict(list)
            for r in cab.get("origens") or []:
                origem, caminho = estado.separar_ref(str(r))
                arquivos[origem].append(caminho)
            self.notas[n["chave"]] = {"titulo": n["titulo"] or n["chave"].rsplit("/", 1)[-1], "pasta": n["pasta"],
                                      "cab": cab, "corpo": corpo, "arquivos": dict(arquivos)}
        # Arestas entre notas: {(de, para): relação}. documenta substitui menciona no mesmo par.
        self.arestas = {}
        for chave, n in self.notas.items():
            evid = {notas.LINK.fullmatch(str(e).strip()).group(1).strip() if notas.LINK.fullmatch(str(e).strip())
                    else str(e).strip() for e in n["cab"].get("evidencias") or []}
            for alvo in notas.links_de(n["cab"], n["corpo"]):
                if alvo == chave or alvo not in self.notas:
                    continue
                if alvo in evid:
                    self.arestas[(alvo, chave)] = "documenta"
                    self.arestas.pop((chave, alvo), None)
                elif self.arestas.get((alvo, chave)) != "documenta":
                    self.arestas.setdefault((chave, alvo), "menciona")
        self.vizinhos = collections.defaultdict(dict)  # nota -> {outra: (relação, sentido)}
        for (de, para), rel in self.arestas.items():
            for a, b, sentido in ((de, para, "sai"), (para, de, "entra")):
                atual = self.vizinhos[a].get(b)
                self.vizinhos[a][b] = (rel, "ambos" if atual and atual[1] != sentido else sentido)
        self.por_pasta = collections.defaultdict(list)
        for chave, n in self.notas.items():
            self.por_pasta[n["pasta"]].append(chave)
        for lista in self.por_pasta.values():
            lista.sort(key=lambda c: (-len(self.vizinhos[c]), self.notas[c]["titulo"].lower()))

    # --- totais (o que a tela mostra como "no índice") ---------------------------------

    def totais(self):
        rel = collections.Counter(self.arestas.values())
        return {"notas": len(self.notas),
                "pastas": {p: len(self.por_pasta[p]) for p in self._pastas()},
                "relacoes": {"fundamenta": sum(len(a) for n in self.notas.values() for a in n["arquivos"].values()),
                             "documenta": rel["documenta"], "menciona": rel["menciona"]}}

    def _pastas(self):
        return sorted(self.por_pasta, key=lambda p: (ORDEM_PASTAS.index(p) if p in ORDEM_PASTAS else 99, p))

    # --- nós ---------------------------------------------------------------------------

    def no(self, id_):
        tipo, _, resto = id_.partition(":")
        if id_ == "sistema":
            return {"id": id_, "tipo": "sistema", "rotulo": self.tag, "sub": f"{len(self.notas)} notas"}
        if tipo == "origem" and resto in self.origens:
            n = sum(1 for x in self.notas.values() if resto in x["arquivos"])
            return {"id": id_, "tipo": "origem", "rotulo": self.origens[resto], "sub": f"origem {resto}", "notas": n}
        if tipo == "pasta" and resto in self.por_pasta:
            return {"id": id_, "tipo": "pasta", "rotulo": ROTULO_PASTA.get(resto, resto), "pasta": resto,
                    "sub": f"{len(self.por_pasta[resto])} notas", "notas": len(self.por_pasta[resto])}
        if tipo == "nota" and resto in self.notas:
            n = self.notas[resto]
            return {"id": id_, "tipo": "nota", "rotulo": n["titulo"], "chave": resto, "pasta": n["pasta"],
                    "sub": ROTULO_PASTA.get(n["pasta"], n["pasta"]), "ligacoes": len(self.vizinhos[resto])}
        return None

    # --- vizinhança do foco ------------------------------------------------------------

    def vizinhanca(self, foco="sistema", limite=LIMITE):
        """{foco, nos, arestas, notas_vizinhas, notas_mostradas, relacoes?}. Cada nó
        vizinho traz `lado` (esquerda: de onde vem; direita: o que tem ou cita)."""
        limite = max(1, min(int(limite), LIMITE_MAX))
        centro = self.no(foco)
        if not centro:
            return None
        nos, arestas = [], []

        def por(id_, lado, **extra):
            nos.append({**self.no(id_), "lado": lado, **extra})

        def liga(de, para, rel, **extra):
            arestas.append({"de": de, "para": para, "relacao": rel, **extra})

        tipo, _, resto = foco.partition(":")
        vizinhas, mostradas = 0, 0
        saida = {}
        if foco == "sistema":
            for o in self.origens:
                por(f"origem:{o}", "esquerda")
                liga(f"origem:{o}", "sistema", "compõe")
            for p in self._pastas():
                por(f"pasta:{p}", "direita")
                liga(f"pasta:{p}", "sistema", "compõe", n=len(self.por_pasta[p]))
        elif tipo == "origem":
            por("sistema", "esquerda")
            liga(foco, "sistema", "compõe")
            for p in self._pastas():
                n = sum(1 for c in self.por_pasta[p] if resto in self.notas[c]["arquivos"])
                if n:
                    por(f"pasta:{p}", "direita")
                    liga(foco, f"pasta:{p}", "fundamenta", n=n)
        elif tipo == "pasta":
            por("sistema", "esquerda")
            liga(foco, "sistema", "compõe")
            for o in self.origens:
                n = sum(1 for c in self.por_pasta[resto] if o in self.notas[c]["arquivos"])
                if n:
                    por(f"origem:{o}", "esquerda")
                    liga(f"origem:{o}", foco, "fundamenta", n=n)
            lista = self.por_pasta[resto]
            vizinhas, mostradas = len(lista), min(limite, len(lista))
            for c in lista[:limite]:
                por(f"nota:{c}", "direita")
                liga(f"nota:{c}", foco, "compõe")
        else:  # nota
            n = self.notas[resto]
            por(f"pasta:{n['pasta']}", "esquerda")
            liga(foco, f"pasta:{n['pasta']}", "compõe")
            for o, arquivos in n["arquivos"].items():
                if o in self.origens:
                    por(f"origem:{o}", "esquerda")
                    liga(f"origem:{o}", foco, "fundamenta", n=len(arquivos))
            viz = sorted(self.vizinhos[resto].items(),
                         key=lambda kv: (PESO_RELACAO[kv[1][0]], kv[1][1] != "ambos", -len(self.vizinhos[kv[0]]),
                                         self.notas[kv[0]]["titulo"].lower()))
            vizinhas, mostradas = len(viz), min(limite, len(viz))
            for outra, (rel, sentido) in viz[:limite]:
                por(f"nota:{outra}", "esquerda" if sentido == "entra" else "direita", sentido=sentido)
                for de, para in ((outra, resto), (resto, outra)):
                    if self.arestas.get((de, para)):
                        liga(f"nota:{de}", f"nota:{para}", self.arestas[(de, para)])
            # Alternativa em texto ao desenho: todas as relações, não só as desenhadas.
            saida["relacoes"] = [{"chave": outra, "titulo": self.notas[outra]["titulo"], "pasta": self.notas[outra]["pasta"],
                                  "relacao": rel, "sentido": sentido} for outra, (rel, sentido) in viz]
            saida["arquivos"] = [{"origem": o, "repo": self.origens.get(o), "caminhos": sorted(a)}
                                 for o, a in sorted(n["arquivos"].items())]
        return {"foco": centro, "nos": nos, "arestas": arestas, "notas_vizinhas": vizinhas,
                "notas_mostradas": mostradas, "limite": limite, **saida}


def inteiro(g):
    """O grafo inteiro das notas, para a visão de grafo de forças (estilo
    Obsidian): nós com pasta e número de ligações; arestas como pares de
    índices, para o JSON ficar pequeno."""
    chaves = sorted(g.notas)
    pos = {c: i for i, c in enumerate(chaves)}
    return {"nos": [{"chave": c, "titulo": g.notas[c]["titulo"], "pasta": g.notas[c]["pasta"],
                     "ligacoes": len(g.vizinhos[c])} for c in chaves],
            "arestas": [[pos[de], pos[para], rel] for (de, para), rel in sorted(g.arestas.items())]}


def carregar(db, tag):
    origens = db.execute("SELECT nome, repo FROM origens WHERE tag = ? AND removida_em IS NULL ORDER BY nome = 'principal' DESC, nome",
                         (tag,)).fetchall()
    linhas = db.execute("SELECT chave, pasta, titulo, conteudo FROM notas_indice WHERE tag = ?", (tag,)).fetchall()
    return Grafo(tag, origens, linhas)
