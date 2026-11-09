# AGENTS.md

<!-- vs:inicio (seção gerenciada pelo Vault System) -->
## Protocolo Vault System

Este projeto está ligado a um vault no hub do Vault System (veja `.vs`). Quem
envia é `vs sync`: ele empacota a pasta (respeitando o `.gitignore`) e manda
para o hub. No modo **documented** (literal + documentado), as notas descritas aqui entram no vault
**já curadas**, sem curador no hub. Mantenha as notas em dia sempre que mudar
o que elas explicam.

**Onde e como escrever.** Uma nota por assunto, em Markdown, em `docs/vs/`
(ou em outra pasta do projeto), com este cabeçalho:

```markdown
---
vs: regra
titulo: Desconto máximo do catálogo
origens:
  - app/precos.py
---
# Desconto máximo do catálogo

O desconto nunca passa de 15%: `preco_final` limita o valor recebido.
```

- `vs`: o tipo da nota.
  - `elemento`: uma peça reutilizável (componente, token, ícone, tela).
  - `regra`: o que precisa valer sempre (de negócio, de uso, de estilo).
  - `orientacao`: como fazer ou montar algo, passo a passo.
  - `decisao`: o que foi decidido, por quê e o que ficou de fora.
  - `modulo`, `integracao`, `api`, `dado`: o código por pasta, serviço
    externo, rota e estrutura de dados.
  - `nota`: o que não se encaixa nos outros.
- `origens`: os arquivos do projeto que a nota explica, com o caminho a partir
  da raiz. O hub liga a nota à cópia de cada um. Arquivo que não existe sai da
  nota, com aviso.
- O corpo começa com `# Título`. Explique o comportamento e o porquê; os
  arquivos em si já vão junto, como estão. Trechos curtos podem ser citados.
- **Nunca** escreva credenciais, tokens, senhas ou dados pessoais. O hub mascara
  o que tiver cara de segredo e avisa.

**Ao terminar uma mudança:** atualize ou crie as notas afetadas, apague as que
deixaram de valer e envie:

```bash
vs sync --dry-run   # confira a lista; as notas aparecem marcadas com *
vs sync
```

**Comandos que o agente usa** (referência completa: `vs help`):
- `vs sync`: envia esta pasta ao vault do `.vs`. Nunca rode `vs init` de novo
  numa pasta que já tem `.vs`, e não troque o vault ou o modo sem pedido.
- `vs sync --dry-run`: mostra o que iria, sem enviar.
- `vs list templates` e `vs add template <type:name>`: listam e aplicam
  templates do hub. Use `--dry-run` antes; nunca use `--force` sem pedido.
- Não use `--curate`: ele abre um agente para curar a pasta, e você já é o agente.
<!-- vs:fim -->

## Este projeto
