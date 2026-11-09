# Posts de Instagram do Vault System (design:instagram)

Pacote para fazer posts estáticos com a identidade do Vault System: tokens de marca, Ubuntu local,
símbolo, grafo orbital, terminal claro, os formatos do Instagram e um script que renderiza cada post em PNG.
É o par estático de `design:motion-vs` (vídeos): mesmas cores, fontes e regras.

```sh
vs add template design:instagram dir=posts
cd posts
npm i && npx playwright install chromium
npm run render:exemplo        # gera out/exemplo-*.png
```

Comece por `POSTS.md` (passo a passo). As regras, os elementos e as decisões estão em `docs/vs/`.

## O que vem no pacote

| Pasta | Conteúdo |
|---|---|
| `tokens/marca.css` | Cores, Ubuntu (400/500/700 locais), escala de texto para 1080 px |
| `componentes/post.css` | Formatos (`post--feed` 4:5, `post--quadrado` 1:1, `post--story` 9:16), névoa, título, bloco azul |
| `componentes/elementos.css` | Assinatura, contador de carrossel, "arraste", terminal, selo, etapas |
| `componentes/orbita.svg` | Grafo orbital (fontes ligadas ao núcleo) |
| `assets/` | Símbolo orbital e fontes Ubuntu |
| `exemplo/index.html` | Um post de cada formato, montado só com os componentes |
| `scripts/render.mjs` | Renderiza cada `.post[data-nome]` de um HTML em PNG no tamanho exato |
