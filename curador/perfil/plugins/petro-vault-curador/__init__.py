"""Plugin do curador do petro-vault (DV-291): a tag garantida no código.

A curadoria (petro_vault/curadoria.py) roda um Hermes por lote, e cada lote é
de uma tag só. O lote vem nas variáveis de ambiente PETRO_VAULT_*, lidas a
cada chamada. No lote da tag X, perfil P:

- leitura (read_file, search_files): o lote (PETRO_VAULT_LOTE_DIR),
  _regras/ e _templates/P/ do vault, e sistemas/X/ (no perfil
  referencia-explicada, menos referencia/: o curador lê a cópia numerada em
  lote/fontes/, DV-600);
- escrita (write_file, patch): só nas pastas do perfil em sistemas/X/ e em
  sistemas/X/_meta/registro.md e conflitos.md. Fica fora: indices/,
  _meta/origem.json e _meta/verificacao.md (gerados pelo código), e todo o
  resto do vault e do disco;
- qualquer outra ferramenta: bloqueada.

Toda chamada (permitida ou não) vai para PETRO_VAULT_PLUGIN_LOG, para
conferir na fonte o que o curador tentou. Adaptado do plugin petro-curador do
Petro Observer (DV-63).
"""
import datetime
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("petro_vault_curador")
ARQUIVOS = ("read_file", "search_files", "write_file", "patch")
ESCRITA = ("write_file", "patch")
PASTAS_DO_PERFIL = {"documentos": ("documentos", "assuntos"),
                    "codigo": ("modulos", "regras", "integracoes", "apis", "dados", "infra"),
                    # DV-600: a cópia literal é do código, não do curador. DV-602: infra/ nos dois perfis.
                    "referencia-explicada": ("guias", "infra")}
META_DO_CURADOR = ("_meta/registro.md", "_meta/conflitos.md")


def _dentro(c: str, pasta: str) -> bool:
    return c == pasta or c.startswith(pasta.rstrip("/") + "/")


def _registrar(decisao: str, ferramenta: str, caminho: str, motivo: str = "") -> None:
    linha = {"em": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "tag": os.environ.get("PETRO_VAULT_TAG", ""), "decisao": decisao, "ferramenta": ferramenta,
             "caminho": caminho, "motivo": motivo}
    (logger.warning if decisao == "bloqueado" else logger.info)("%s: %s %s %s", decisao, ferramenta, caminho, motivo)
    destino = os.environ.get("PETRO_VAULT_PLUGIN_LOG")
    if destino:
        try:
            with open(destino, "a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        except OSError:
            pass


def _bloquear(ferramenta: str, caminho: str, mensagem: str) -> Dict[str, str]:
    _registrar("bloqueado", ferramenta, caminho, mensagem)
    return {"action": "block", "message": mensagem}


def decidir(tool_name: str = "", args: Any = None, **_: Any) -> Optional[Dict[str, str]]:
    tag = os.environ.get("PETRO_VAULT_TAG", "")
    perfil = os.environ.get("PETRO_VAULT_PERFIL", "")
    vault = os.path.realpath(os.environ.get("PETRO_VAULT_VAULT", "/opt/vault"))
    lote = os.path.realpath(os.environ.get("PETRO_VAULT_LOTE_DIR", "/opt/curador/lote"))
    if not tag or perfil not in PASTAS_DO_PERFIL:
        return _bloquear(tool_name, "", "Lote sem tag ou com perfil desconhecido: nada é permitido.")
    if tool_name not in ARQUIVOS:
        return _bloquear(tool_name, "", "O curador só usa as ferramentas de arquivo.")
    if tool_name == "patch" and isinstance(args, dict) and args.get("patch"):
        return _bloquear(tool_name, "", "Use patch com path, old_string e new_string.")
    path = args.get("path") if isinstance(args, dict) else None
    if not isinstance(path, str) or not path.startswith("/"):
        return _bloquear(tool_name, str(path), "Use caminho absoluto.")
    c = os.path.realpath(path)
    da_tag = os.path.join(vault, "sistemas", tag)

    if tool_name in ESCRITA:
        permitidas = [os.path.join(da_tag, p) for p in PASTAS_DO_PERFIL[perfil]]
        permitidas += [os.path.join(da_tag, m) for m in META_DO_CURADOR]
        if not any(_dentro(c, p) for p in permitidas):
            return _bloquear(tool_name, c, f"Escrita só nas pastas {', '.join(PASTAS_DO_PERFIL[perfil])} e em "
                                           f"_meta/registro.md e _meta/conflitos.md de sistemas/{tag}/.")
    else:
        if perfil == "referencia-explicada" and _dentro(c, os.path.join(da_tag, "referencia")):
            # DV-600: a nota tem cabeçalho e desloca as linhas; os marcadores usam as do arquivo.
            return _bloquear(tool_name, c, f"Leia a cópia numerada em {os.path.join(lote, 'fontes')}/<arquivo>: "
                                           "os números de linha dos marcadores são os de lá.")
        permitidas = [lote, da_tag, os.path.join(vault, "_regras"), os.path.join(vault, "_templates", perfil)]
        if not any(_dentro(c, p) for p in permitidas):
            return _bloquear(tool_name, c, f"Leitura só do lote, de _regras/, de _templates/{perfil}/ e de "
                                           f"sistemas/{tag}/.")
    _registrar("permitido", tool_name, c)
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", decidir)
