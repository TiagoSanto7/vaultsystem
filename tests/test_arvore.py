"""Testes da árvore de pastas: a classificação vira leituras que levam
cada arquivo exatamente aonde a árvore mostra."""
import json
import random

from vault_system import arvore, ingestao
from test_github_app import github_falso
from test_painel import entrar, tela  # noqa: F401 - fixture

REFEITORIO = [
    "README.md", "package.json", "package-lock.json",
    "docs/app-mobile-handoff.md", "docs/manual-suporte/marmitas.md",
    "docs/superpowers/specs/a-design.md", "docs/superpowers/plans/2026-07-21-bug.md",
    "docs/superpowers/plans/2026-07-22-outro.md",
    "api/src/pedidos.ts", "api/src/catraca/wiegand.ts", "api/README.md",
    "marmita_workspace/packages/marmita_app/lib/main.dart",
    "marmita_workspace/packages/marmita_app/android/app/build.gradle",
    "marmita_workspace/packages/marmita_app/ios/Runner/Info.plist",
    "marmita_workspace/packages/marmita_app/assets/logo.svg",
    "marmita_workspace/docs/handoff/integracao.md",
    "marmita_workspace/.superpowers/sdd/progress.md",
    "web/node_modules/react/index.js", ".env", "certs/servidor.pem",
]


def destino(caminho, leituras):
    perfil, _ = ingestao.leitura_de(caminho, leituras, cru=True)
    return perfil or "ignorar"


def conferir(arquivos, classificacao):
    leituras = arvore.leituras(arquivos, classificacao)
    for a in arquivos:
        if arvore.fixo(a):
            assert destino(a, leituras) == "ignorar", a
        else:
            assert destino(a, leituras) == arvore.destino_de(a, classificacao), (a, leituras)
    return leituras


def test_refeitorio_pela_arvore():
    c = {"": "codigo", "docs": "documentos", "docs/superpowers/plans": "ignorar",
         "marmita_workspace/.superpowers": "ignorar", "marmita_workspace/docs": "documentos",
         "README.md": "documentos", "api/README.md": "documentos"}
    leituras = conferir(REFEITORIO, c)
    assert [l["perfil"] for l in leituras] == ["documentos", "codigo"]
    # Código pega tudo menos o ignorado: pasta nova na raiz segue a raiz.
    assert leituras[1]["incluir"] == []
    assert destino("nova-pasta/x.ts", leituras) == "codigo"
    assert destino("docs/novo.md", leituras) == "documentos"  # arquivo novo segue a pasta
    assert destino("docs/superpowers/plans/novo.md", leituras) == "ignorar"


def test_sugestao_inicial():
    arquivos = [{"caminho": a, "fixo": arvore.fixo(a)} for a in REFEITORIO]
    s = arvore.sugestao(arquivos)
    assert s[""] == "codigo-literal" and s["docs"] == "documentos" and s["marmita_workspace/docs"] == "documentos"
    assert s["marmita_workspace/packages/marmita_app/android"] == "ignorar"
    # Os .md ficam com a regra, e não um a um.
    assert s[arvore.MD] == "documentos" and "README.md" not in s and "api/README.md" not in s
    leituras = conferir(REFEITORIO, s)
    assert destino("api/README.md", leituras) == "documentos"
    assert destino("api/src/NOVO.md", leituras) == "documentos"  # .md novo numa pasta de código
    assert destino("marmita_workspace/packages/marmita_app/android/NOVO.md", leituras) == "ignorar"


def test_regra_dos_md():
    c = {"": "codigo", "docs": "documentos", "docs/superpowers/plans": "ignorar", "app/android": "ignorar",
         "app/android/docs": "documentos", "api/NOTAS.md": "codigo", arvore.MD: "documentos"}
    arquivos = ["README.md", "docs/a.md", "docs/superpowers/plans/p.md", "api/x.ts", "api/NOTAS.md", "api/LEIA.md",
                "app/lib/a.dart", "app/android/build.gradle", "app/android/LEIA.md", "app/android/docs/b.md"]
    leituras = conferir(arquivos, c)
    assert [l["perfil"] for l in leituras] == ["documentos", "documentos", "codigo"]
    assert leituras[1]["incluir"] == ["*.md"]
    assert destino("app/lib/NOVO.md", leituras) == "documentos"
    assert destino("docs/superpowers/plans/novo.md", leituras) == "ignorar"
    assert destino("api/NOTAS.md", leituras) == "codigo"  # classificado um a um
    # Sem a regra, o .md segue a pasta.
    sem = {k: v for k, v in c.items() if k != arvore.MD}
    assert destino("app/lib/NOVO.md", conferir(arquivos, sem)) == "codigo"


def test_referencia_e_a_regra_dos_md():
    """a pasta de referência fica com os .md dela; a regra dos .md vale no resto."""
    c = {"": "codigo", "design": "referencia", "design/assets": "ignorar", arvore.MD: "documentos"}
    arquivos = ["README.md", "src/x.py", "src/LEIA.md", "design/README.md", "design/componentes/botao.md",
                "design/tokens/tokens.css", "design/assets/logo.svg", "design/assets/NOTA.md"]
    leituras = conferir(arquivos, c)
    assert destino("design/componentes/botao.md", leituras) == "referencia"
    assert destino("design/componentes/novo.md", leituras) == "referencia"  # .md novo segue a pasta
    assert destino("design/tokens/tokens.css", leituras) == "referencia"
    assert destino("src/LEIA.md", leituras) == "documentos" and destino("design/assets/NOTA.md", leituras) == "ignorar"
    # De volta: a classificação tirada das leituras leva cada arquivo ao mesmo lugar.
    regs = [{"caminho": a, "fixo": None} for a in arquivos]
    volta = arvore.classificacao_de(regs, leituras)
    assert arvore.mudancas(regs, leituras, volta) == []


def test_sugestao_do_vault_de_referencia():
    arquivos = [{"caminho": p} for p in ("README.md", "tokens/tokens.json", "componentes/botao.md",
                                         "assets/fonts/Branding.otf", "vitrine/index.html", ".claude/settings.local.json")]
    # assets/ entra: as fontes e imagens viram arquivos para baixar.
    assert arvore.sugestao_referencia(arquivos) == {"": "referencia-explicada", ".claude": "ignorar"}


def test_arquivo_da_raiz_nao_pega_o_mesmo_nome_em_outra_pasta():
    # Padrão sem barra casa com o nome em qualquer pasta: README.md da raiz
    # classificado sozinho não pode levar junto o api/README.md.
    arquivos = ["README.md", "api/README.md", "api/x.ts", "a[1]*.md", "b/a[1]*.md", "]x.md", "b/]x.md"]
    for c in ({"": "codigo", "README.md": "documentos", "a[1]*.md": "documentos", "]x.md": "documentos"},
              {"": "codigo", "README.md": "codigo", "a[1]*.md": "ignorar", "]x.md": "ignorar", arvore.MD: "documentos"}):
        conferir(arquivos, c)


def test_classificacoes_aleatorias_sao_exatas():
    sorteio = random.Random(589)
    pastas = ["a", "a/b", "a/b/c", "a/d", "e", "e/f", "e/f/g", "h"]
    for _ in range(300):
        arquivos = sorted({f"{sorteio.choice(pastas)}/{sorteio.choice('xyz')}{sorteio.choice(['.md', '.py'])}"
                           for _ in range(25)} | {"raiz.md", "x.md", "y.py"})
        nos = [""] + sorteio.sample(pastas + arquivos, 6)
        c = {n: sorteio.choice(arvore.CLASSES) for n in nos}
        conferir(arquivos, c)
        conferir(arquivos, {**c, arvore.MD: "documentos"})


def test_arvore_pela_tela(tela, monkeypatch):  # noqa: F811
    cliente, _, _ = tela
    entrar(cliente)
    from vault_system import estado, github_app as gh
    assert cliente.post("/v1/painel/arvores", json={"repo": "git@github.com:O/r.git"}).status_code == 400
    aid = cliente.post("/v1/painel/arvores", json={"repo": "https://github.com/O/r", "ramo": "main"}).json()["id"]
    assert cliente.get(f"/v1/painel/arvores/{aid}").json()["estado"] == "pedido"
    assert cliente.post(f"/v1/painel/arvores/{aid}/leituras", json={"classificacao": {"": "codigo"}}).status_code == 409

    github_falso(monkeypatch, gh, {
        ("GET", "/repos/O/r/installation"): (200, {"id": 7}),
        ("POST", "/app/installations/7/access_tokens"): (201, {"token": "ghs_x"}),
        ("GET", "/repos/O/r/branches/main"): (200, {"commit": {"sha": "abc123"}}),
        ("GET", "/repos/O/r/git/trees/abc123"): (200, {"truncated": False, "tree": [
            {"path": "docs", "type": "tree"}, {"path": "docs/a.md", "type": "blob", "size": 10},
            {"path": "src/x.py", "type": "blob", "size": 10}, {"path": "yarn.lock", "type": "blob", "size": 10}]}),
    })
    arvore.atender(estado.conectar())
    r = cliente.get(f"/v1/painel/arvores/{aid}").json()
    assert r["estado"] == "pronto" and r["commit"] == "abc123"
    assert [(a["caminho"], a["fixo"]) for a in r["arquivos"]] == [("docs/a.md", None), ("src/x.py", None), ("yarn.lock", "lockfile")]
    assert r["sugestao"] == {"": "codigo-literal", "docs": "documentos", "*.md": "documentos"}  # o padrão tem a cópia
    assert r["sugestao_referencia"] == {"": "referencia-explicada"}  # ponto de partida do vault de Referência

    r = cliente.post(f"/v1/painel/arvores/{aid}/leituras", json={"classificacao": r["sugestao"]}).json()
    assert r["totais"] == {"documentos": 1, "referencia-explicada": 0, "referencia": 0, "codigo-literal": 1, "codigo": 0, "ignorar": 0, "fixo": 1}
    assert r["leituras"] == [{"perfil": "documentos", "incluir": ["docs/**"], "excluir": []},
                             {"perfil": "documentos", "incluir": ["*.md"], "excluir": []},
                             {"perfil": "codigo-literal", "incluir": [], "excluir": []}]
    # O cadastro guarda a classificação junto das leituras.
    cad = {"tag": "r", "origens": [{"repo": "https://github.com/O/r", "leituras": r["leituras"],
                                    "classificacao": {"": "codigo", "docs": "documentos"}}]}
    assert cliente.post("/v1/painel/sistemas", json=cad).status_code == 201
    db = estado.conectar()
    assert json.loads(db.execute("SELECT classificacao FROM origens").fetchone()[0]) == {"": "codigo", "docs": "documentos"}

    # Ramo que não existe: erro na própria árvore.
    aid = cliente.post("/v1/painel/arvores", json={"repo": "https://github.com/O/r", "ramo": "nao"}).json()["id"]
    github_falso(monkeypatch, gh, {
        ("GET", "/repos/O/r/installation"): (200, {"id": 7}),
        ("POST", "/app/installations/7/access_tokens"): (201, {"token": "ghs_x"}),
        ("GET", "/repos/O/r/branches/nao"): (404, {}),
    })
    arvore.atender(db)
    r = cliente.get(f"/v1/painel/arvores/{aid}").json()
    assert r["estado"] == "erro" and r["erro"] == "o ramo nao não existe em O/r"


def _como_arvore(caminhos):
    return [{"caminho": a, "fixo": arvore.fixo(a)} for a in caminhos]


def test_classificacao_tirada_das_leituras_do_refeitorio():
    # As leituras de hoje do refeitorio (cadastrado pelo formulário antigo).
    hoje = [{"perfil": "documentos", "incluir": ["docs/**", "**/**.md"],
             "excluir": ["docs/superpowers/plans/**", "**/superpowers/plans/**", "**/.superpowers/**"]},
            {"perfil": "codigo", "incluir": [], "excluir": ["**/android/**", "**/ios/**", "**/assets/**",
                                                            "**/fonts/**", "**/.superpowers/**", "**/superpowers/plans/**"]}]
    app = "marmita_workspace/packages/marmita_app"
    arquivos = _como_arvore(REFEITORIO + [f"{app}/{n}" for n in ("lib/a.dart", "test/a_test.dart", "pubspec.yaml", "analysis_options.yaml")])
    c = arvore.classificacao_de(arquivos, hoje)
    assert arvore.mudancas(arquivos, hoje, c) == []
    # O app fica "código, menos android, ios e assets", e não "ignorar, menos lib".
    assert arvore.classe_de(app, c) == "codigo" and c[f"{app}/android"] == "ignorar"
    # O **/**.md de hoje vira a regra dos .md: api/README.md não precisa de classificação própria.
    assert c[arvore.MD] == "documentos" and "api/README.md" not in c
    # Mudar uma pasta aparece arquivo por arquivo, com o destino de antes e o de depois.
    assert arvore.mudancas(arquivos, hoje, {**c, "docs/superpowers/plans": "documentos"}) == [
        {"caminho": "docs/superpowers/plans/2026-07-21-bug.md", "de": "ignorar", "para": "documentos"},
        {"caminho": "docs/superpowers/plans/2026-07-22-outro.md", "de": "ignorar", "para": "documentos"}]


def test_classificacao_tirada_das_leituras_e_exata():
    # Qualquer classificação vira leituras; das leituras volta uma classificação
    # que leva cada arquivo ao mesmo lugar, nunca com mais nós que a original.
    sorteio = random.Random(5892)
    pastas = ["a", "a/b", "a/b/c", "a/d", "e", "e/f", "e/f/g", "h"]
    for _ in range(300):
        caminhos = sorted({f"{sorteio.choice(pastas)}/{sorteio.choice('xyz')}{sorteio.choice(['.md', '.py'])}"
                           for _ in range(25)} | {"raiz.md", "x.md", "y.py"})
        nos = [""] + sorteio.sample(pastas + caminhos, 6)
        original = {n: sorteio.choice(arvore.CLASSES) for n in nos}
        if sorteio.random() < 0.5:
            original[arvore.MD] = "documentos"
        arquivos = _como_arvore(caminhos)
        c = arvore.classificacao_de(arquivos, arvore.leituras(caminhos, original))
        assert all(arvore.destino_de(a, c) == arvore.destino_de(a, original) for a in caminhos)
        assert len(c) <= len(original) + 1  # + a regra dos .md, quando ela enxuga


def test_editar_pela_arvore(tela, monkeypatch):  # noqa: F811
    cliente, _, _ = tela
    entrar(cliente)
    from vault_system import estado, github_app as gh
    hoje = [{"perfil": "documentos", "incluir": ["docs/**"], "excluir": []}, {"perfil": "codigo"}]
    cad = {"tag": "r", "origens": [{"repo": "https://github.com/O/r", "leituras": hoje}]}
    assert cliente.post("/v1/painel/sistemas", json=cad).status_code == 201
    aid = cliente.post("/v1/painel/arvores", json={"repo": "https://github.com/O/r", "ramo": "main"}).json()["id"]
    assert cliente.post(f"/v1/painel/arvores/{aid}/atual", json={"tag": "r", "origem": "principal"}).status_code == 409
    github_falso(monkeypatch, gh, {
        ("GET", "/repos/O/r/installation"): (200, {"id": 7}),
        ("POST", "/app/installations/7/access_tokens"): (201, {"token": "ghs_x"}),
        ("GET", "/repos/O/r/branches/main"): (200, {"commit": {"sha": "abc123"}}),
        ("GET", "/repos/O/r/git/trees/abc123"): (200, {"truncated": False, "tree": [
            {"path": "docs/a.md", "type": "blob", "size": 10}, {"path": "docs/velho/b.md", "type": "blob", "size": 10},
            {"path": "src/x.py", "type": "blob", "size": 10}]}),
    })
    arvore.atender(estado.conectar())
    # Origem do formulário antigo: a classificação sai das leituras.
    r = cliente.post(f"/v1/painel/arvores/{aid}/atual", json={"tag": "r", "origem": "principal"}).json()
    assert r == {"classificacao": {"": "codigo", "docs": "documentos"}, "gravada": False}
    assert cliente.post(f"/v1/painel/arvores/{aid}/atual", json={"tag": "r", "origem": "nao"}).status_code == 404

    nova = {"": "codigo", "docs": "documentos", "docs/velho": "ignorar"}
    r = cliente.post(f"/v1/painel/arvores/{aid}/leituras", json={"classificacao": nova, "tag": "r", "origem": "principal"}).json()
    assert r["mudancas"] == [{"caminho": "docs/velho/b.md", "de": "documentos", "para": "ignorar"}] and r["total_mudancas"] == 1
    assert r["impacto"] == {"ao_curador": 0, "lotes": 0, "copia": 0, "saem": 1, "por_destino": {}}
    assert "mudancas" not in cliente.post(f"/v1/painel/arvores/{aid}/leituras", json={"classificacao": nova}).json()

    # Salvar grava as leituras e a classificação; a próxima edição parte da gravada.
    ed = {"ramo": "main", "leituras": r["leituras"], "classificacao": nova}
    assert cliente.put("/v1/painel/sistemas/r/origens/principal", json=ed).json()["origens"][0]["classificacao"] == nova
    r = cliente.post(f"/v1/painel/arvores/{aid}/atual", json={"tag": "r", "origem": "principal"}).json()
    assert r == {"classificacao": nova, "gravada": True}
    # Editar pelo formulário de leituras apaga a classificação (ela não descreveria mais as leituras).
    ed = {"ramo": "main", "leituras": hoje}
    assert cliente.put("/v1/painel/sistemas/r/origens/principal", json=ed).json()["origens"][0]["classificacao"] is None

    # trocar um vault de Sistema para Referência pela edição (03/11: a edição recusava a classe nova).
    for classe in ("referencia-explicada", "referencia"):
        ref = {"": classe, "docs/velho": "ignorar"}
        r = cliente.post(f"/v1/painel/arvores/{aid}/leituras", json={"classificacao": ref, "tag": "r", "origem": "principal"}).json()
        assert {(m["caminho"], m["para"]) for m in r["mudancas"]} >= {("docs/a.md", classe), ("src/x.py", classe)}
        ed = {"ramo": "main", "leituras": r["leituras"], "classificacao": ref}
        o = cliente.put("/v1/painel/sistemas/r/origens/principal", json=ed)
        assert o.status_code == 200, o.text
        assert o.json()["origens"][0]["classificacao"] == ref and o.json()["origens"][0]["leituras"][0]["perfil"] == classe


def test_impacto_da_reclassificacao(monkeypatch):
    """quanto vai ao curador e quantos lotes, para a tela confirmar antes de salvar."""
    monkeypatch.delenv("VAULT_LOTE", raising=False)
    monkeypatch.delenv("VAULT_LOTE_CODIGO", raising=False)
    m = ([{"caminho": f"src/a/{i}.py", "de": "documentos", "para": "codigo"} for i in range(13)]  # 2 lotes (12 + 1)
         + [{"caminho": "src/b/x.py", "de": "ignorar", "para": "codigo"}]  # pasta outra: mais 1 lote
         + [{"caminho": f"docs/{i}.md", "de": "codigo", "para": "referencia-explicada"} for i in range(6)]  # 2 lotes
         + [{"caminho": f"lib/{i}.ts", "de": "codigo", "para": "referencia"} for i in range(4)]  # cópia, sem LLM
         + [{"caminho": "velho.md", "de": "documentos", "para": "ignorar"}])
    assert arvore.impacto(m) == {"ao_curador": 20, "lotes": 5, "copia": 4, "saem": 1,
                                 "por_destino": {"codigo": 14, "referencia-explicada": 6}}
    # Código ↔ código + cópia literal: zero lotes, só cópia (a fila do curador é a mesma).
    troca = [{"caminho": f"src/{i}.py", "de": "codigo", "para": "codigo-literal"} for i in range(30)]
    assert arvore.impacto(troca) == {"ao_curador": 0, "lotes": 0, "copia": 30, "saem": 0, "por_destino": {}}
    volta = [{**t, "de": "codigo-literal", "para": "codigo"} for t in troca]
    assert arvore.impacto(volta)["lotes"] == 0 and arvore.impacto(volta)["copia"] == 0
    novo = [{"caminho": "src/n.py", "de": "ignorar", "para": "codigo-literal"}]
    assert arvore.impacto(novo) == {"ao_curador": 1, "lotes": 1, "copia": 1, "saem": 0, "por_destino": {"codigo-literal": 1}}
    monkeypatch.setenv("VAULT_LOTE_CODIGO", "20")
    assert arvore.impacto(m)["lotes"] == 4
    assert arvore.impacto([]) == {"ao_curador": 0, "lotes": 0, "copia": 0, "saem": 0, "por_destino": {}}
