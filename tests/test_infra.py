"""Infraestrutura de containers (DV-602): o leitor determinístico, sem valores de variável."""
import builtins

import pytest

from petro_vault import infra

COMPOSE = """name: loja
services:
  web:
    build:
      context: ./web
      dockerfile: Dockerfile.prod
    container_name: loja-web   # comentário
    ports:
      - "8080:80"
      - target: 443
        published: 8443
        protocol: tcp
    depends_on: [api]
    volumes:
      - ./proxy/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    restart: unless-stopped
  api:
    image: "registry/loja-api:1.2"
    environment:
      DATABASE_URL: postgres://loja:SenhaSuperSecreta@db/loja
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/saude || exit 1"]
      interval: 30s
    networks: [interna]
    command: >
      uvicorn app:app
      --port 8000
  db:
    image: postgres:16
    environment:
      - POSTGRES_PASSWORD=OutraSenha123
      - POSTGRES_DB=loja
    volumes:
      - dados:/var/lib/postgresql/data
    networks:
      - interna
volumes:
  dados: {}
networks:
  interna:
"""

DOCKERFILE = """FROM node:22 AS build
ARG NPM_TOKEN=abc123segredo
ENV NODE_ENV=production \\
    API_KEY="chave-que-nao-pode"
COPY package.json ./
RUN npm ci
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s CMD wget -q --spider http://localhost/health
USER nginx
CMD ["nginx", "-g", "daemon off;"]
"""

NGINX = """server {
  listen 80;
  server_name loja.local;
  location /api/ { proxy_pass http://api:8000/; }
  location = /health { return 200 "ok"; }
  location / { root /usr/share/nginx/html; }
}
"""


def _modelo():
    arquivos = {"docker-compose.yml": COMPOSE, "web/Dockerfile.prod": DOCKERFILE, "proxy/nginx.conf": NGINX,
                "web/.dockerignore": "node_modules\n# x\n.env\n", "worker/Dockerfile": "FROM python:3.12\nEXPOSE 9000\n"}
    return infra.modelo({c: (c, t) for c, t in arquivos.items()}, padrao="loja")


def test_tipos_de_arquivo():
    assert [infra.tipo_arquivo(c) for c in ("Dockerfile", "web/Dockerfile.prod", "app.dockerfile", "compose.yaml",
                                            "docker-compose.override.yml", ".dockerignore", "nginx/site.conf",
                                            "nginx.conf", "Caddyfile", "app.conf", "config.yml")] == \
        ["dockerfile", "dockerfile", "dockerfile", "compose", "compose", "dockerignore", "nginx", "nginx", "caddy",
         None, None]


def test_compose_dockerfile_e_proxy_viram_servicos():
    m = _modelo()
    assert sorted(m["servicos"]) == ["api", "db", "web", "worker"]
    web = infra.cabecalho(m["servicos"]["web"])
    assert web["portas"] == ["8080:80", "8443:443"]  # forma curta e longa
    assert web["depende_de"] == ["api"] and web["container"] == "loja-web"
    assert web["build"] == "./web (Dockerfile.prod)" and web["imagem"] == "node:22, nginx:1.27-alpine"
    assert web["healthcheck"] == "wget -q --spider http://localhost/health"  # do Dockerfile
    assert web["proxy"] == ["/api/ → http://api:8000/", "= /health → return 200 \"ok\"", "/ → arquivos"]
    assert m["servicos"]["web"]["arquivos"] == ["docker-compose.yml", "web/.dockerignore", "web/Dockerfile.prod",
                                                "proxy/nginx.conf"]
    api = infra.cabecalho(m["servicos"]["api"])
    assert api["depende_de"] == ["db"] and api["redes"] == ["interna"]
    assert api["healthcheck"] == "curl -f http://localhost:8000/saude || exit 1"
    assert infra.cabecalho(m["servicos"]["db"])["volumes"] == ["dados:/var/lib/postgresql/data"]
    assert m["servicos"]["worker"]["expose"] == ["9000"] and m["servicos"]["worker"]["arquivos"] == ["worker/Dockerfile"]
    assert m["servicos"]["web"]["dockerfile"]["args"] == ["NPM_TOKEN"]
    assert m["servicos"]["web"]["dockerfile"]["envs"] == ["NODE_ENV", "API_KEY"]


def test_nenhum_valor_de_variavel_no_modelo():
    texto = repr(_modelo())
    for segredo in ("SenhaSuperSecreta", "OutraSenha123", "abc123segredo", "chave-que-nao-pode", "postgres://"):
        assert segredo not in texto
    assert "POSTGRES_PASSWORD" in texto and "DATABASE_URL" in texto  # o nome fica


def test_sem_pyyaml_o_leitor_proprio_da_o_mesmo(monkeypatch):
    pytest.importorskip("yaml")
    com = infra.ler_compose(COMPOSE)
    real = builtins.__import__

    def sem_yaml(nome, *a, **k):
        if nome == "yaml":
            raise ImportError(nome)
        return real(nome, *a, **k)
    monkeypatch.setattr(builtins, "__import__", sem_yaml)
    assert infra.ler_compose(COMPOSE) == com


def test_compose_quebrado_vira_aviso_sem_o_conteudo():
    quebrado = "services:\n  api:\n    environment:\n      SENHA: NaoPodeVazar\n      - lista\n"
    m = infra.modelo({"compose.yml": ("compose.yml", quebrado)})
    assert m["servicos"] == {} and m["avisos"] and m["avisos"][0].startswith("compose.yml: YAML inválido")
    assert "NaoPodeVazar" not in repr(m)


def test_caddy():
    assert infra.ler_caddy("loja.local {\n  reverse_proxy api:8000\n}\n") == {"sites": ["loja.local"],
                                                                              "reverse_proxy": ["api:8000"]}


def test_grafo_do_mapa():
    """DV-603: o grafo sai só do leitor: tipos pela imagem, ligações de depends_on e do proxy, portas e volumes."""
    import sqlite3
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE notas_indice (tag, chave, pasta)")
    db.executemany("INSERT INTO notas_indice VALUES ('loja', ?, ?)", [
        ("sistemas/loja/infra/web", "infra"), ("sistemas/loja/infra/visao-geral", "infra"),
        ("sistemas/loja/referencia/docker-compose.yml", "referencia")])
    g = infra.grafo(db, "loja", _modelo())
    por = {s["id"]: s for s in g["servicos"]}
    assert {k: s["tipo"] for k, s in por.items()} == {"web": "proxy", "api": "app", "db": "banco", "worker": "app"}
    assert {(l["de"], l["para"], l["tipo"]) for l in g["ligacoes"]} == {
        ("web", "api", "depende"), ("web", "api", "proxy"), ("api", "db", "depende")}
    assert por["web"]["portas"] == [{"host": "8080", "container": "80", "texto": "8080:80"},
                                    {"host": "8443", "container": "443", "texto": "8443:443"}]
    assert por["db"]["volumes"] == [{"origem": "dados", "destino": "/var/lib/postgresql/data", "somente_leitura": False,
                                     "nomeado": True}]
    assert por["web"]["volumes"][0]["somente_leitura"] and not por["web"]["volumes"][0]["nomeado"]
    assert por["web"]["nota"] == "sistemas/loja/infra/web" and por["api"]["nota"] is None
    assert por["web"]["arquivos"][0] == {"ref": "docker-compose.yml", "tipo": "compose",
                                         "nota": "sistemas/loja/referencia/docker-compose.yml"}
    assert g["redes"] == [{"stack": "loja", "nome": "interna"}] and g["visao_geral"] == "sistemas/loja/infra/visao-geral"
    # Stack (DV-603): o compose tem `name: loja`; o Dockerfile sem compose fica em "sem compose", por último.
    assert [(st["nome"], st["arquivo"], st["servicos"]) for st in g["stacks"]] == [
        ("loja", "docker-compose.yml", ["web", "api", "db"]), ("sem compose", None, ["worker"])]
    assert por["web"]["stack"] == "loja" and por["worker"]["stack"] is None
    assert "SenhaSuperSecreta" not in repr(g)


def test_um_stack_por_compose():
    """Cada compose é um stack com o nome que o docker compose daria: `name:`, a pasta, ou o repositório na raiz."""
    arquivos = {"docker-compose.yml": "services:\n  web:\n    image: nginx\n",
                "monitor/compose.yaml": "services:\n  web:\n    image: grafana/grafana\n",
                "api:docker-compose.yml": "name: Minha API!\nservices:\n  app:\n    image: x\n"}
    m = infra.modelo({r: (r.split(":")[-1], t) for r, t in arquivos.items()}, padrao="tag",
                     raizes={"": "Catraca_TopData", "api:": "loja-api"})
    por = {s["stack_arquivo"]: s["stack"] for s in m["servicos"].values()}
    assert por == {"docker-compose.yml": "catraca_topdata", "monitor/compose.yaml": "monitor",
                   "api:docker-compose.yml": "minhaapi"}
    assert sorted(m["servicos"]) == ["app", "monitor-web", "web"]  # mesmo nome em outro stack: o stack na frente
    assert infra.cabecalho(m["servicos"]["web"])["stack"] == "catraca_topdata"


def test_destino_externo_so_tipo_e_host():
    """DV-604: do valor saem só o tipo e o host:porta; usuário, senha, caminho e query nunca."""
    d = infra.destino
    assert d("DATABASE_URL", "mysql+pymysql://app:S3nha@10.2.2.6:3306/refeitorio?charset=utf8") == ("mysql", "10.2.2.6:3306")
    assert d("DATABASE_URL", "postgresql://u:p@localhost/x") == ("postgres", None)  # local não é endereço
    assert d("LDAP_SERVIDORES", "ldap://10.254.1.10,ldap://10.254.1.11") == ("ldap", "10.254.1.10")
    assert d("SERVICE_LAYER_PROD", "https://sl1.servicos.local:50000/b1s/v1") == ("sap", "sl1.servicos.local:50000")
    assert d("HANA_IP_PROD", "10.120.43.67") == ("sap", "10.120.43.67")
    assert d("HANA_PASS_PROD", "NaoPodeAparecer") == ("sap", None)
    assert d("NOTIFICACAO_URL", "http://10.254.1.17:8003/enviar?token=abc") == ("http", "10.254.1.17:8003")
    assert d("APP_ENV", "production") is None and d("WS_HOST", "0.0.0.0") is None


def test_externos_do_env_example_por_tipo_e_fora_do_stack():
    import sqlite3
    compose = ("services:\n  web:\n    image: app\n    env_file: [.env]\n    environment:\n"
               "      CACHE_URL: redis://cache.interno:6379/0\n"
               "  vigia:\n    image: app\n    environment:\n      VIGIA_API_URL: http://web:8000\n")
    exemplo = ("# banco\nDATABASE_URL=mysql+pymysql://app:SenhaDoExemplo@10.2.2.6:3306/refeitorio\n"
               "LDAP_SERVIDORES=ldap://10.254.1.10\nLDAP_DOMINIO=PETROVINA\nFOTOS_BASE_URL=http://10.2.2.3:9800/fotos/\n"
               "PETROAI_URL=http://10.2.2.31:8000\n")
    from petro_vault import filtros
    m = infra.modelo({"docker-compose.yml": ("docker-compose.yml", compose)}, padrao="t",
                     exemplos={".env.example": infra.ler_env_exemplo(filtros.mascarar(exemplo)[0])})
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE notas_indice (tag, chave, pasta)")
    db.executemany("INSERT INTO notas_indice VALUES ('t', ?, ?)", [("sistemas/t/integracoes/ad-ldap", "integracoes"),
                                                                  ("sistemas/t/dados/pedidos", "dados")])
    g = infra.grafo(db, "t", m)
    por = {e["tipo"]: e for e in g["externos"]}
    assert list(por) == ["mysql", "redis", "ldap", "http"]  # web:8000 é serviço do stack: não é externo
    assert por["mysql"]["ambientes"] == [{"ambiente": None, "variaveis": ["DATABASE_URL"]}]
    assert por["mysql"]["servicos"] == ["web"] and por["mysql"]["notas_dados"] == 1
    assert por["ldap"]["variaveis"] == ["LDAP_DOMINIO", "LDAP_SERVIDORES"] and por["ldap"]["notas"] == ["sistemas/t/integracoes/ad-ldap"]
    assert por["http"]["rotulo"] == "Serviços HTTP" and por["http"]["destinos"] == 2
    assert por["redis"]["origens"] == ["docker-compose.yml"]
    assert {(l["de"], l["para"]) for l in g["ligacoes"] if l["tipo"] == "externo"} == {
        ("web", "ext-mysql"), ("web", "ext-redis"), ("web", "ext-ldap"), ("web", "ext-http")}
    tudo = repr(g) + repr(m) + repr(infra.cabecalho(m["servicos"]["web"])) + repr(infra.resumo_fatos(m["servicos"]["web"]))
    # Nem endereço (decisão de 03/11: IP fora do mapa, da nota e do lote), nem usuário, senha ou caminho.
    for proibido in ("SenhaDoExemplo", "app:", "/refeitorio", "/fotos/", "PETROVINA", "10.2.2.6", "10.254.1.10",
                     "cache.interno", "10.2.2.3", "3306"):
        assert proibido not in tudo, proibido
    assert infra.cabecalho(m["servicos"]["web"])["externos"] == ["AD / LDAP", "MySQL", "Redis", "Serviço HTTP"]


def test_ambiente_pelo_sufixo_da_variavel():
    import sqlite3
    m = infra.modelo({"compose.yml": ("compose.yml", "services:\n  web:\n    image: x\n    env_file: .env\n")},
                     exemplos={".env.example": {"HANA_IP_PROD": ("sap", "10.0.0.1"), "HANA_IP_HOMO": ("sap", "10.0.0.2"),
                                                "SL_COMPANY_DB_PROD": ("sap", None), "SAP_TIMEOUT": ("sap", None)}})
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE notas_indice (tag, chave, pasta)")
    [sap] = infra.grafo(db, "t", m)["externos"]
    assert sap["ambientes"] == [{"ambiente": "produção", "variaveis": ["HANA_IP_PROD", "SL_COMPANY_DB_PROD"]},
                                {"ambiente": "homologação", "variaveis": ["HANA_IP_HOMO"]},
                                {"ambiente": None, "variaveis": ["SAP_TIMEOUT"]}]
    assert infra.cabecalho(m["servicos"]["web"])["externos"] == ["SAP (homologação, produção)"]
    assert "10.0.0" not in repr(infra.grafo(db, "t", m)) + repr(infra.resumo_fatos(m["servicos"]["web"]))
