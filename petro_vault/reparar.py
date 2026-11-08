"""Reparo de uma reclassificação de pastas que não devia ter ido (DV-608).

    python -m petro_vault.reparar <tag>            mostra o que faria (não muda nada)
    python -m petro_vault.reparar <tag> --aplicar  faz

Volta o vault para o que está **publicado** (o último commit do repositório do vault):

1. as leituras de cada origem voltam às de `sistemas/<tag>/_meta/origem.json` daquele commit, **sem
   reconciliação** (não gera fila: o vault publicado já reflete essas leituras);
2. os itens pendentes da tag saem da fila (estado `substituido`);
3. as mudanças não publicadas de `sistemas/<tag>/` na pasta de trabalho do vault são descartadas;
4. a tag é reindexada (verificação), para a busca e o MCP lerem o que está publicado.

Rodar com o curador parado (o coordenador também mexe nessas coisas).
"""
import collections
import json
import subprocess
import sys

from . import estado, notas, verificacao


def _git(*args):
    return subprocess.run(["git", "-C", notas.dir_vault(), *args], capture_output=True, text=True)


def plano(db, tag):
    r = _git("show", f"HEAD:sistemas/{tag}/_meta/origem.json")
    if r.returncode != 0:
        raise SystemExit(f"{tag}: não há _meta/origem.json publicado no vault; nada a voltar")
    publicadas = {o["nome"]: o["leituras"] for o in json.loads(r.stdout).get("origens", [])}
    origens = []
    for o in db.execute("SELECT * FROM origens WHERE tag = ? AND removida_em IS NULL", (tag,)):
        atual = json.loads(o["leituras"] or "[]")
        volta = publicadas.get(o["nome"])
        origens.append({"nome": o["nome"], "muda": volta is not None and volta != atual,
                        "antes": collections.Counter(l["perfil"] for l in atual),
                        "depois": collections.Counter(l["perfil"] for l in volta or []), "leituras": volta})
    fila = collections.Counter((l["perfil"], l["acao"]) for l in db.execute(
        "SELECT perfil, acao FROM fila WHERE tag = ? AND estado = 'na_fila'", (tag,)))
    sujos = [l for l in _git("status", "--porcelain", "--", f"sistemas/{tag}").stdout.splitlines() if l.strip()]
    return {"origens": origens, "fila": fila, "sujos": sujos}


def mostrar(tag, p):
    print(f"[reparar] {tag}: volta ao que está publicado no vault")
    for o in p["origens"]:
        if o["muda"]:
            print(f"  origem {o['nome']}: leituras {dict(o['antes'])} -> {dict(o['depois'])}")
        else:
            print(f"  origem {o['nome']}: leituras já são as publicadas")
    total = sum(p["fila"].values())
    print(f"  fila: {total} item(ns) pendente(s) saem" + "".join(
        f"\n    {n} {perfil}/{acao}" for (perfil, acao), n in sorted(p["fila"].items())))
    print(f"  pasta de trabalho: {len(p['sujos'])} arquivo(s) não publicado(s) descartado(s)")


def aplicar(db, tag, p):
    with db:
        for o in p["origens"]:
            if o["leituras"] is not None:
                db.execute("UPDATE origens SET leituras = ?, leituras_antes = NULL, classificacao = NULL "
                           "WHERE tag = ? AND nome = ?", (json.dumps(o["leituras"]), tag, o["nome"]))
        db.execute("UPDATE fila SET estado = 'substituido', motivo = COALESCE(motivo || '; ', '') || "
                   "'reparo DV-608: reclassificação desfeita' WHERE tag = ? AND estado = 'na_fila'", (tag,))
    _git("checkout", "HEAD", "--", f"sistemas/{tag}")
    _git("clean", "-fdq", "--", f"sistemas/{tag}")
    verificacao.main([tag])


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0].startswith("-"):
        raise SystemExit(__doc__)
    tag = args[0]
    db = estado.conectar()
    p = plano(db, tag)
    mostrar(tag, p)
    if "--aplicar" in args:
        aplicar(db, tag, p)
        restam = db.execute("SELECT COUNT(*) FROM fila WHERE tag = ? AND estado = 'na_fila'", (tag,)).fetchone()[0]
        sujos = [l for l in _git("status", "--porcelain", "--", f"sistemas/{tag}").stdout.splitlines() if l.strip()]
        print(f"[reparar] {tag}: feito. Fila pendente: {restam}; não publicados: {len(sujos)}")
    else:
        print("[reparar] nada foi mudado. Para aplicar: acrescente --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
