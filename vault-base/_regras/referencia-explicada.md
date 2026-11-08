# Regras do perfil referência + explicação

Valem para as pastas classificadas como "referência + explicação" (DV-600):
design system, normas, manuais já escritos. Somam-se às regras comuns
(`comum.md`). Este arquivo vem de `vault-base/_regras/` no repositório do
serviço; mudança só por PR lá.

## Pastas em `sistemas/<tag>/`

| Pasta | O que tem | Quem escreve |
| --- | --- | --- |
| `referencia/` | uma nota por arquivo da origem, **igual ao arquivo** (`.md` inteiro; outros num bloco de código) | código, sem LLM |
| `infra/` | arquivos de container (Dockerfile, compose, nginx...): um serviço por nota e `visao-geral.md`; o arquivo continua literal em `referencia/` (DV-602) | curador; os fatos do cabeçalho, o código |
| `guias/` | explicação por assunto: para que serve, quando usar, cuidados, com os trechos marcados | curador; os trechos, o código |
| `_meta/registro.md` | uma linha por item da fila processado | curador |

## Trechos

- O curador marca o trecho numa linha sozinha:
  `<!-- trecho: <arquivo>#<id> -->` (elemento HTML com esse id) ou
  `<!-- trecho: <arquivo>:L<n>-L<m> -->` (linhas).
- Os números de linha são os do arquivo de origem (o curador lê a cópia
  numerada em `fontes/` no lote), não os da nota literal, que tem cabeçalho.
  `#<id>` vale só para id de elemento HTML.
- O código cola o trecho exato embaixo, a partir da nota literal, e fecha com
  `<!-- /trecho -->`. Trecho de um `.md` sai com a linguagem do bloco de código
  de onde veio; blocos inteiros saem como estão. A cada rodada os trechos são colados de novo: se a
  origem mudou, o guia acompanha.
- Bloco de código fora de trecho é apagado do guia. O verificador acusa
  `codigo_fora_de_trecho`, `trecho_divergente` e `trecho_corta_bloco` (linhas
  que começam ou terminam no meio de um bloco de código).

## Cabeçalho

O código grava `sistema`, `tipo_nota` (`guia`), `origens` (os arquivos dos
trechos e das notas literais citadas), `commit_origem` e as datas. O curador
grava só `resumo`.

## Regras

- O guia diz só o que o arquivo mostra; dúvida vai como dúvida, no fim.
- Guia novo só para assunto novo; preferir atualizar o que existe.
- Origem apagada: o código tira a nota literal; o curador revisa os guias que
  a usavam.
