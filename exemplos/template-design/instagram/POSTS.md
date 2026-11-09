# Como fazer um post novo no estilo Vault System

1. **Formato.** Feed é 4:5 (`post--feed`, 1080×1350) por padrão. Use 1:1 (`post--quadrado`) só quando pedirem, e 9:16 (`post--story`) para story ou capa de Reels.
2. **Arquivo.** Crie `posts/<aaaa-mm-dd>-<assunto>.html` copiando `exemplo/index.html` (ajuste os caminhos `../`). Um carrossel é um arquivo com várias `section.post`, uma por slide, com `data-nome` numerado (`assunto-01`, `assunto-02`...).
3. **Texto.** Poucas palavras por tela. Uma palavra-chave por título em azul (`.destaque`) ou em bloco (`.bloco`), nunca as duas coisas em excesso. Títulos em caixa alta por padrão; `titulo--natural` para frases.
4. **Elementos.** Órbita (`componentes/orbita.svg`) para falar de conexão de fontes; terminal (`.terminal`) para CLI, sempre com o selo "Demonstração do fluxo proposto" enquanto o fluxo não estiver lançado; etapas (`.etapas`) para listas curtas.
5. **Assinatura.** Todo post leva `.assinatura` (símbolo + "Vault System"). No carrossel, contador `01 / 05` no topo e "Arraste" no rodapé, menos no último slide.
6. **Zonas seguras.** No story, nada fora de `padding-top: 250px` e `padding-bottom: 340px` (já no `post--story`). No feed, a grade do perfil corta para 3:4: deixe título e marca longe das bordas de cima e de baixo (as margens de 96 px já cuidam disso).
7. **Render.** `node scripts/render.mjs posts/<arquivo>.html out/<assunto>` gera um PNG por slide, no tamanho exato. Confira cada PNG antes de entregar.
