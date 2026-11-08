---
resumo: "Para que serve este serviço (container) em uma frase."
---
# <Serviço>

<!-- O cabeçalho de fatos (servico, container, imagem, build, portas, volumes,
redes, depende_de, healthcheck, restart, proxy e origens) é gravado pelo código
a partir dos arquivos. Não escreva esses campos; explique-os aqui. -->

## Para que serve

<O que este container entrega e para quem.>

## Como é construído

- Imagem base e etapas do build (o que é copiado para dentro, o que fica de fora pelo .dockerignore).
- Usuário e comando de início, se o arquivo diz.

## Como roda

- Portas: qual porta do host chega a qual porta do container, e o que responde nela.
- Volumes e dados que persistem.
- Rede, healthcheck (o que é testado e de quanto em quanto tempo) e política de restart.
- Logs (driver e limites, se o arquivo diz).

## De que depende

<Outros serviços (depends_on), proxy na frente, bancos e serviços externos que aparecem nos arquivos.>

## Configuração

<Nomes das variáveis de ambiente e arquivos .env usados. Nunca valores.>

## Onde roda e como publica

<Servidor, pasta, nome do container e comando de subir, só se estiverem nos arquivos ou na documentação.>

## Cuidados

<O que quebra se mudar (porta usada por outro sistema, caminho que a aplicação espera, limite de log). Dúvida vai como dúvida.>
