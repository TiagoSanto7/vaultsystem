# Regras do perfil código

Valem para as leituras de código (`perfil: codigo`) de um sistema. Somam-se
às regras comuns (`comum.md`). Este arquivo vem de `vault-base/_regras/` no
repositório do serviço; mudança só por PR lá.

O curador escreve **conhecimento sobre o código**, nunca o código: o que o
sistema faz, as regras de negócio, as integrações, o que expõe e que dados
guarda. Na leitura "código + cópia literal" (`perfil: codigo-literal`, DV-608),
o próprio código do serviço também copia cada arquivo como está para
`referencia/` (sem LLM) e põe no fim de cada nota de código o bloco
`<!-- arquivos -->` com os links para essas cópias. O curador não escreve nem
edita esse bloco nem as notas de `referencia/`: o código refaz a cada rodada.

## Pastas em `sistemas/<tag>/`

| Pasta | O que tem | Quem escreve |
| --- | --- | --- |
| `modulos/` | uma nota por pasta da origem (`painel/app/rotas` → `modulos/painel--app--rotas.md`; raiz → `modulos/raiz.md`) | curador; o código calcula o caminho |
| `regras/` | regras de negócio, uma por nota | curador |
| `integracoes/` | sistemas externos que o código chama, um por nota | curador |
| `apis/` | o que o sistema expõe (rotas, ferramentas, comandos) | curador |
| `dados/` | tabelas, arquivos e estruturas que o sistema guarda | curador |
| `infra/` | um serviço (container) por nota, mais `visao-geral.md`: como é construído, como roda e como se liga (DV-602) | curador; os fatos do cabeçalho, o código |
| `indices/codigo.md` | lista das notas de código | código |
| `referencia/` | só em `codigo-literal`: o arquivo da origem como está, um por nota | código (sem LLM) |

## Cabeçalho

O código grava, depois do curador: `sistema`, `tipo_nota` (`modulo`,
`regra`, `integracao`, `api` ou `dado`, pela pasta), `origens`,
`commit_origem`, `criado_em` e `atualizado_em`.

O curador grava: `resumo` (uma frase) e `fontes` (lista JSON dos arquivos da
origem de onde tirou o conhecimento). O código confere cada fonte no commit
da origem; só as que existem viram `origens`, e `fontes` sai do cabeçalho.

## Regras

- Sem código copiado: no máximo nomes de função, rota ou variável entre crases.
- Sem valor de segredo: só o nome da variável de ambiente ou do cofre.
- Uma regra, integração, API ou entidade por nota; o módulo liga todas as
  notas que saíram da pasta.
- Arquivo modificado: só as notas que o têm em `origens` mudam (o código
  avisa no log se outra mudar); nota nova só para conhecimento novo.
- Arquivo apagado: o código tira o arquivo das `origens`; nota sem origem é
  apagada pelo código; as outras o curador revisa.
- O verificador procura padrões de segredo em toda nota e acusa.
- Infra (Dockerfile, compose, .dockerignore, nginx, Caddy): o código lê os
  fatos (serviço, container, imagem, build, portas, volumes, redes,
  depende_de, healthcheck, restart, proxy) e grava no cabeçalho de
  `infra/<serviço>.md` a cada rodada, com `origens`. Variável de ambiente
  só pelo nome. Nota de infra de serviço que sumiu dos arquivos: o
  verificador acusa (`infra_sem_servico`).
