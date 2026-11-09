---
vs: elemento
titulo: Formatos e zonas seguras
origens:
  - componentes/post.css
---
# Formatos e zonas seguras

| Classe | Tamanho | Uso |
|---|---|---|
| `post--feed` | 1080×1350 (4:5) | Padrão do feed e de carrossel |
| `post--quadrado` | 1080×1080 (1:1) | Só quando pedido |
| `post--story` | 1080×1920 (9:16) | Story e capa de Reels |

- Margem de 96 px em todos os lados (`--post-margem`).
- No story, o conteúdo fica entre 250 px do topo (barra do perfil) e 340 px do rodapé (resposta e controles), como no motion (texto acima de 330 px do rodapé).
- A grade do perfil mostra o post 4:5 cortado em 3:4: o que importa fica no meio.
- Todos os slides de um carrossel têm o mesmo formato.
