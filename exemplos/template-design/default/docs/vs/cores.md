---
vs: elemento
titulo: Cores
origens:
  - tokens/cores.css
---
# Cores

A paleta tem um azul de marca e neutros azulados. Todo componente usa os tokens
`--vs-*` de `tokens/cores.css`, nunca o valor hexadecimal solto: é isso que
permite o tema escuro trocar só os neutros.

| Token | Uso |
| --- | --- |
| `--vs-azul` (#0758ed) | ação principal, links e destaque. Um por área. |
| `--vs-azul-profundo` (#0345bb) | hover e estado pressionado do azul. |
| `--vs-azul-claro` (#82baff) | órbitas do símbolo, ilustração e foco. |
| `--vs-azul-nevoa` (#eaf2ff) | fundo de cartão em destaque. |
| `--vs-tinta` / `--vs-tinta-suave` | texto principal e secundário. |
| `--vs-papel` / `--vs-papel-azulado` | fundo da página e de seção. |
| `--vs-linha` | bordas e divisórias. |

No tema escuro (`prefers-color-scheme: dark`), só os neutros mudam; o azul de
marca continua o mesmo. Veja a regra de contraste antes de pôr texto sobre azul.
