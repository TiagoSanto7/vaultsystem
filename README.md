<p align="center">
  <img src="assets/vault-system-banner.svg" alt="Vault System — Conhecimento distribuído" width="960">
</p>

<h1 align="center">Vault System</h1>
<p align="center"><strong>Conhecimento distribuído para pessoas, agentes e ferramentas.</strong></p>
<p align="center"><a href="#como-funciona">Como funciona</a> · <a href="#estado-do-projeto">Estado do projeto</a></p>

Vault System reúne conhecimento que vive espalhado entre código, documentação e decisões de projeto. Ele relaciona essas informações com suas fontes e ajuda a levar o contexto certo para pessoas, agentes e ferramentas.

## Como funciona

| Etapa | O que acontece |
| --- | --- |
| **01 · Reunir** | Código, documentos e decisões entram na órbita do projeto. |
| **02 · Conectar** | As relações entre as fontes dão contexto a cada informação. |
| **03 · Distribuir** | Pessoas, agentes e ferramentas reaproveitam esse contexto onde trabalham. |

## Estado do projeto

Primeira versão executável: o hub (API e tela), a VS CLI e a curadoria opcional Vault-I.

| Parte | O que faz |
| --- | --- |
| **Hub** | Guarda os vaults, mostra as notas com origem e emite os tokens. |
| **VS CLI** | `vs login`, `vs init` e `vs sync` ligam uma pasta de projeto a um vault. No modo documentado, as notas que o agente do projeto escreveu entram já curadas. |
| **Vault-I** | Curadoria interna com chave de API (Claude ou OpenAI), só quando você pede. |

Para rodar na sua máquina, veja [local/README.md](local/README.md). Próximos passos: o comando `vs lock` e a CLI como binário sem Python.
