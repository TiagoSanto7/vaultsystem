# Regras do perfil documentos

Valem para sistemas cadastrados com `perfil: documentos` (repositórios de
documentação). Somam-se às regras comuns (`comum.md`). Este arquivo vem de
`vault-base/_regras/` no repositório do serviço; mudança só por PR lá.

## Pastas em `sistemas/<tag>/`

| Pasta | O que tem | Quem escreve |
| --- | --- | --- |
| `documentos/` | uma nota por arquivo da origem, no mesmo caminho (`docs/a.md` → `documentos/docs/a.md`; outro formato ganha `.md` no fim) | curador; o código calcula o caminho |
| `assuntos/` | síntese por assunto, com os documentos como evidência | curador |
| `indices/` | listas de documentos e de assuntos | código |
| `_meta/registro.md` | uma linha por item da fila processado | curador |
| `_meta/conflitos.md` | documentos que se contradizem | curador |
| `_meta/origem.json`, `_meta/verificacao.md` | origem e commits; resultado do verificador | código |

## Cabeçalho

O código grava, depois do curador: `sistema`, `tipo_nota` (`documento` ou
`assunto`), `origens`, `commit_origem`, `criado_em`, `atualizado_em` e, se o
arquivo da origem segue a estrutura padrão (`petro-docs-modelo`),
`origem_tipo`, `origem_responsavel` e `origem_revisado_em`.

O curador grava só: `resumo` (uma frase) e, nos assuntos, `evidencias`
(lista JSON de links para documentos).

## Regras

- Nota de documento: resumo fiel, sem copiar o documento inteiro; mantém o
  que alguém vai procurar (valores, nomes, passos, responsáveis).
- Todo documento é evidência de pelo menos um assunto. Assunto sem
  documento não existe.
- Assunto novo só quando nenhum existente serve; preferir fundir.
- Conflito entre documentos: não escolher; registrar em `_meta/conflitos.md`.
- Origem apagada: o código tira a nota do documento; o curador revisa os
  assuntos que o citavam.
