# Documento de execução do PetroVault

Consolidação do protótipo e dos fluxos de produto aprovados em 26/10/2026.

- [Especificação em Markdown](PetroVault_Documento_de_Execucao_v1.md)
- [Versão editável em Word](PetroVault_Documento_de_Execucao_v1.docx)

## Relação com a implementação existente

Este documento descreve a evolução pretendida. As propostas de arquitetura não substituem automaticamente as decisões de [arquitetura](../arquitetura.md), o código ou os contratos existentes.

Antes de executar as etapas, conciliar explicitamente:

- PAT por fonte com as deploy keys utilizadas atualmente;
- autorização por sistema com o modelo atual de credenciais e tags;
- revisão editorial das notas com o verificador existente;
- persistência proposta com SQLite e vault Git existentes;
- contratos de consulta propostos com a API e o MCP já implementados.

Registrar as decisões de compatibilidade e migração antes de alterar comportamento. Este PR adiciona somente documentação e não altera serviços nem configuração de implantação.

O protótipo navegável e o pacote visual estão em [`prototipo/`](prototipo/). A conciliação com o que já existe está em [conciliacao.md](conciliacao.md).
