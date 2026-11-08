"""Hermes falso para os testes da curadoria.

Faz o papel do curador sem LLM: para cada item do lote, escreve a nota do
documento, funde num assunto e registra. Toda leitura e escrita passa antes
pelo plugin de verdade (curador/perfil/plugins/vault-system-curador), que lê o
lote nas variáveis VAULT_SYSTEM_*, como no Hermes.

Marcas no conteúdo do documento:
  ESPECIAL       vai para o assunto `especial` (senão, `geral`)
  NAO-REGISTRAR  o item não é registrado (fica na fila)
  TRAVAR         o lote inteiro falha sem registrar nada (como o tempo esgotado)
  DEMORAR        o lote demora VAULT_TESTE_DEMORA s antes de seguir
  INVADIR        tenta escrever fora da tag (o plugin bloqueia)

Perfil código: escreve a nota do módulo com todos os arquivos do lote
(e uma fonte inventada, que o código tem de descartar) e, para cada linha
`REGRA: <nome>` de um arquivo, uma nota em regras/<nome>.md com esse arquivo
de fonte. Arquivo modificado: só reescreve as notas ligadas a ele.

Perfil referência + explicação: para cada arquivo, um guia em
guias/<nome do arquivo>.md com o link da nota literal, o marcador de trecho
`#botoes` e, de propósito, um bloco de código escrito por ele (o código tem de
tirar). Removido: tira dos guias a revisar os marcadores do arquivo.

Infra: item que diz "arquivo de infraestrutura"
vira a nota de cada serviço listado (com um fato errado no cabeçalho, que o
código tem de trocar) e a visão geral com links para os serviços. No perfil
referência + explicação, no lugar do guia.
"""
import importlib.util
import json
import os
import re
import sys

raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "plugin", os.path.join(raiz, "curador", "perfil", "plugins", "vault-system-curador", "__init__.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

TAG = os.environ["VAULT_SYSTEM_TAG"]
VAULT = os.environ["VAULT_SYSTEM_VAULT"]
DA_TAG = os.path.join(VAULT, "sistemas", TAG)


def ler(caminho):
    if plugin.decidir("read_file", {"path": caminho}):
        raise SystemExit(f"bloqueado: ler {caminho}")
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def escrever(caminho, texto):
    if plugin.decidir("write_file", {"path": caminho, "content": texto}):
        return False
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return True


def assunto(nome, evid_add=(), evid_tirar=()):
    c = os.path.join(DA_TAG, "assuntos", f"{nome}.md")
    evid = []
    if os.path.exists(c):
        m = re.search(r"^evidencias: (.*)$", ler(c), re.M)
        evid = json.loads(m.group(1)) if m else []
    evid = [e for e in evid if e not in evid_tirar] + [e for e in evid_add if e not in evid]
    if not evid:
        escrever(c, "")
        return
    corpo = "\n".join(f"- {e}" for e in evid)
    escrever(c, f"---\nresumo: \"Assunto {nome}\"\nevidencias: {json.dumps(evid)}\n---\n# Assunto {nome}\n\n{corpo}\n")


def infra(texto, trecho=False):
    """Notas de infra do item; devolve as escritas."""
    if "arquivo de infraestrutura" not in texto:
        return []
    feitas, links = [], []
    for nome, c in re.findall(r"^- serviço '([^']+)': nota (\S+);", texto, re.M):
        escrever(c, f"---\nresumo: \"Serviço {nome}\"\nportas: [\"1:1\"]\nfontes: [\"x\"]\n---\n"
                    f"# {nome}\n\nServe a vitrine.\n" + ("\n<!-- trecho: docker-compose.yml:L1-L2 -->\n" if trecho else ""))
        feitas.append(c)
        links.append(f"[[sistemas/{TAG}/infra/{os.path.basename(c)[:-3]}]]")
    geral = re.search(r"^- visão geral.*?: (\S+)$", texto, re.M).group(1)
    escrever(geral, "---\nresumo: \"Infra\"\n---\n# Infraestrutura\n\n" + "\n".join(f"- {l}" for l in links) + "\n")
    return feitas + [geral]


def codigo(consulta, itens):
    modulo = re.search(r"Nota do módulo desta pasta: (\S+)", consulta).group(1)
    registro, fontes, regras_mod = [], [], []
    for item in itens:
        texto = ler(item)
        nome = os.path.basename(item)[:-3]
        arquivo = re.search(r"^- arquivo na origem: (\S+)$", texto, re.M).group(1)
        lig = re.search(r"^- notas ligadas a este arquivo.*?: (.*)$", texto, re.M)
        feitas = []
        if "acao: removido" in texto.replace("ação", "acao"):
            for c in re.search(r"notas a revisar.*?: (.*)$", texto, re.M).group(1).split(", "):
                atual = ler(c)
                escrever(c, atual.replace(f'"{arquivo}", ', "").replace(f', "{arquivo}"', "")
                         .replace(f"- `{arquivo}`\n", ""))
                feitas.append(c)
        elif "arquivo de infraestrutura" in texto:
            feitas += infra(texto)
        else:
            fontes.append(arquivo)
            for regra in re.findall(r"REGRA: ([a-z0-9-]+)", texto):
                c = os.path.join(DA_TAG, "regras", f"{regra}.md")
                if lig and c not in lig.group(1):
                    continue  # modificado: só as notas ligadas mudam
                escrever(c, f"---\nresumo: \"Regra {regra}\"\nfontes: {json.dumps([arquivo])}\n---\n"
                            f"# Regra {regra}\n\nVem de `{arquivo}`.\n")
                regras_mod.append(f"[[sistemas/{TAG}/regras/{regra}]]")
                feitas.append(c)
        if "NAO-REGISTRAR" not in texto:
            registro.append(f"- {nome} · {', '.join(feitas) or 'sem conhecimento novo'}")
    if fontes:
        anterior = ler(modulo) if os.path.exists(modulo) else ""
        m = re.search(r"^fontes: (.*)$", anterior, re.M)
        todas = sorted(set(json.loads(m.group(1)) if m else []) | set(fontes))
        linhas = "".join(f"- `{f}`\n" for f in todas)
        escrever(modulo, f"---\nresumo: \"Módulo\"\nsistema: errado\nfontes: {json.dumps(todas + ['nao/existe.py'])}\n"
                         f"---\n# Módulo\n\n{linhas}\n" + "\n".join(sorted(set(regras_mod))) + "\n")
    caminho = os.path.join(DA_TAG, "_meta", "registro.md")
    escrever(caminho, ler(caminho) + "\n".join(registro) + "\n")
    print("CONCLUIDO")


def referencia(consulta, itens):
    registro = []
    for item in itens:
        texto = ler(item)
        nome = os.path.basename(item)[:-3]
        arquivo = re.search(r"^- arquivo na origem: (\S+)$", texto, re.M).group(1)
        feitas = []
        if "acao: removido" in texto.replace("ação", "acao"):
            for c in re.search(r"notas a revisar.*?: (.*)$", texto, re.M).group(1).split(", "):
                if c and os.path.exists(c):
                    atual = ler(c)
                    escrever(c, "\n".join(l for l in atual.split("\n") if f"trecho: {arquivo}" not in l))
                    feitas.append(c)
        elif "arquivo de infraestrutura" in texto:
            feitas += infra(texto, trecho=True)
        else:
            literal = re.search(r"^- nota literal.*?: (\[\[[^\]]+\]\])$", texto, re.M).group(1)
            guia = os.path.join(DA_TAG, "guias", os.path.basename(arquivo).split(".")[0] + ".md")
            escrever(guia, f"---\nresumo: \"Guia de {arquivo}\"\nsistema: errado\n---\n# Botões\n\n"
                           f"Origem: {literal}. Use o primário para a ação principal.\n\n"
                           + (f"<!-- trecho: {arquivo}#botoes -->\n\n" if arquivo.endswith(".html") else "") +
                           "Exemplo que eu mesmo escrevi (não pode ficar):\n\n```css\n.btn{color:red}\n```\n")
            feitas.append(guia)
        if "NAO-REGISTRAR" not in texto:
            registro.append(f"- {nome} · {', '.join(feitas) or 'nada'}")
    caminho = os.path.join(DA_TAG, "_meta", "registro.md")
    escrever(caminho, ler(caminho) + "\n".join(registro) + "\n")
    print("CONCLUIDO")


def main():
    if os.environ.get("VAULT_TESTE_DORMIR"):
        import time
        time.sleep(1.1)  # para atualizado_em ficar diferente de criado_em
    args = sys.argv[1:]
    consulta = open(args[args.index("--query-file") + 1], encoding="utf-8").read()
    if any("DEMORAR" in open(i, encoding="utf-8").read() for i in re.findall(r"^- (/\S+/item-\d+\.md)$", consulta, re.M)):
        import time
        time.sleep(float(os.environ.get("VAULT_TESTE_DEMORA", "3")))  # lote lento
    if any("TRAVAR" in open(i, encoding="utf-8").read() for i in re.findall(r"^- (/\S+/item-\d+\.md)$", consulta, re.M)):
        print("tempo esgotado (simulado)")
        return 124
    if "(perfil referencia-explicada)" in consulta:
        return referencia(consulta, re.findall(r"^- (/\S+/item-\d+\.md)$", consulta, re.M))
    if "(perfil codigo)" in consulta:
        return codigo(consulta, re.findall(r"^- (/\S+/item-\d+\.md)$", consulta, re.M))
    registro = []
    for item in re.findall(r"^- (/\S+/item-\d+\.md)$", consulta, re.M):
        texto = ler(item)
        nome = os.path.basename(item)[:-3]
        if "INVADIR" in texto:
            escrever(os.path.join(VAULT, "sistemas", "outra-tag", "invasao.md"), "x")
            escrever(os.path.join(VAULT, "_regras", "comum.md"), "x")
        m = re.search(r"^- nota a escrever: (\S+)$", texto, re.M)
        if m:
            nota = m.group(1)
            chave = "[[" + os.path.relpath(nota, VAULT)[:-3] + "]]"
            nome_assunto = "especial" if "ESPECIAL" in texto else "geral"
            # Como o modelo faz: copia os links que estão no documento da origem.
            da_origem = " ".join(re.findall(r"\[\[[^\]]+\]\]", texto.split("## Conteúdo", 1)[-1]))
            escrever(nota, f"---\nresumo: \"Documento\"\nsistema: errado\ncriado_em: 1999\n---\n# Doc {nome}\n\n"
                           f"Assunto: [[sistemas/{TAG}/assuntos/{nome_assunto}]]\n\n{da_origem}\n")
            assunto(nome_assunto, evid_add=[chave])
            notas_feitas = [chave]
        else:  # removido
            apagadas = re.search(r"já tirou do vault.*?: (.*)$", texto, re.M).group(1)
            tirar = re.findall(r"\[\[[^\]]+\]\]", apagadas)
            for c in re.search(r"notas a revisar.*?: (.*)$", texto, re.M).group(1).split(", "):
                if "/assuntos/" in c:
                    assunto(os.path.basename(c)[:-3], evid_tirar=tirar)
            notas_feitas = tirar
        if "NAO-REGISTRAR" not in texto:
            registro.append(f"- {nome} · {', '.join(notas_feitas)}")
    caminho = os.path.join(DA_TAG, "_meta", "registro.md")
    escrever(caminho, ler(caminho) + "\n".join(registro) + "\n")
    print("CONCLUIDO")


if __name__ == "__main__":
    sys.exit(main())
