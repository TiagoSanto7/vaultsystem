---
vs: orientacao
titulo: Como montar uma tela
origens:
  - exemplo/index.html
  - tokens/cores.css
  - tokens/tipografia.css
  - componentes/botao.css
  - componentes/cartao.css
---
# Como montar uma tela

`exemplo/index.html` é a tela de referência. Para uma nova:

1. Importe os tokens primeiro (`tokens/cores.css`, `tokens/tipografia.css`) e
   depois os componentes que usar.
2. Envolva o conteúdo numa coluna de até 960 px, centrada, com 16 px de margem
   lateral.
3. Topo: símbolo + nome, depois `.vs-sobretitulo`, o `h1` e um parágrafo curto.
4. Ações logo abaixo: um `.vs-botao--primario` e, se precisar, secundários.
5. Conteúdo em grade de cartões (`auto-fit`, mínimo de 240 px), com o primeiro
   em `.vs-cartao--destaque`.
6. Confira as regras de uso da marca e de contraste antes de publicar.
