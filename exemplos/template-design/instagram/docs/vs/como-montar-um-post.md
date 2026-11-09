---
vs: orientacao
titulo: Do pedido ao PNG
origens:
  - POSTS.md
  - scripts/render.mjs
---
# Do pedido ao PNG

1. O conteúdo vem do pedido. Sem pedido de tema, não se inventa post.
2. Escolha o formato (feed 4:5 por padrão) e copie `exemplo/index.html` para `posts/`.
3. Monte só com tokens e componentes. Se faltar uma peça, crie no `componentes/` e documente aqui, em vez de estilo solto no post.
4. Renderize: `node scripts/render.mjs posts/<arquivo>.html out/<assunto>` (precisa de `npm i` e do Chromium do Playwright; `CHROMIUM_PATH` aponta outro navegador).
5. Abra cada PNG e confira: acentos não cortados pelos blocos, nada fora das zonas seguras, assinatura presente, uma só cor de destaque.
6. Entregue os PNGs e o HTML. Ajustes pedidos depois mexem só no que foi pedido.
