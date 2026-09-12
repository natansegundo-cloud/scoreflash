# ScoreFlash

## Versão para amigos

O projeto está preparado para ser publicado na Vercel sem expor chaves no navegador. Siga [DEPLOY-VERCEL.md](DEPLOY-VERCEL.md): ele explica cada clique em linguagem simples e gera uma URL pública para seus amigos.

O ScoreFlash é um analista local de estatísticas de futebol. Você escreve uma pergunta em português, ele encontra a equipe, consulta partidas recentes, calcula a resposta e explica a tendência com os jogos usados como evidência.

## Usar é fácil

1. Abra esta pasta.
2. Dê dois cliques em `INICIAR-SCOREFLASH.cmd`.
3. Espere alguns segundos. O navegador abrirá sozinho em `http://127.0.0.1:5173`.
4. Faça uma pergunta, por exemplo:

   - `Qual a média de finalizações do Flamengo nos últimos 5 jogos?`
   - `Qual a média de escanteios do Palmeiras em casa nos últimos 5 jogos?`
   - `Qual a média de posse de bola do Newell's fora de casa nos últimos 3 jogos?`

Não é preciso procurar, copiar nem preencher `x-fsign`: o programa obtém automaticamente a configuração pública atual da página antes de consultar os dados.

## O que já funciona

- Descoberta dinâmica de equipes de futebol pelo nome, sem catálogo manual.
- Médias de finalizações, chutes, escanteios, posse de bola, cartões amarelos e faltas.
- Recortes “em casa”, “fora de casa” e quantidade de jogos.
- Texto humano que explica a tendência recente e informa o nível de confiança da amostra.
- Lista das partidas que entraram no cálculo.
- Cache local de respostas recentes para evitar consultas repetidas.
- Perguntas sobre atleta, como `Léo Ortiz vale mais de 0.5 finalizações amanhã pelo Flamengo?`: o sistema confirma atleta, clube, presenças recentes, minutos, rating e próximo jogo.
- Com `API_FOOTBALL_API_KEY` configurada: cartões de oportunidade para finalizações, chutes no alvo, faltas cometidas e cartões amarelos, com média, frequência da linha e os jogos individuais usados.

## Única configuração necessária para os cartões de oportunidade

Você só precisa fazer isto uma vez:

1. Abra [a página de cadastro da API-Football](https://dashboard.api-football.com/register).
2. Crie uma conta gratuita e copie a chave exibida no painel.
3. Nesta pasta, abra o arquivo `.env` com o Bloco de Notas. Se ele não existir, dê dois cliques em `INICIAR-SCOREFLASH.cmd` uma vez: ele será criado automaticamente.
4. Encontre a linha `API_FOOTBALL_API_KEY=` e cole a chave depois do sinal `=`.
5. Salve, feche o ScoreFlash se ele estiver aberto e dê dois cliques em `INICIAR-SCOREFLASH.cmd` novamente.

Não envie essa chave por mensagem, imagem ou conversa. Ela fica somente no seu computador. O plano gratuito anunciado pela API-Football tem 100 consultas por dia, mas a própria fonte limita as temporadas disponíveis nele; teste a cobertura antes de considerar qualquer plano pago.

## Limite honesto da análise de jogador

O cartão só recebe uma leitura `favorável`, `neutro` ou `evitar` quando houver pelo menos três jogos com a métrica individual registrada. A leitura compara a linha pedida com o histórico recente, mas não considera odds, escalação confirmada ou garante resultado.

## O que vem a seguir

O sistema já é a base para o produto de perguntas livres. As próximas capacidades são:

- reconhecer jogador, time, jogo e mercado na mesma pergunta;
- escalações e desfalques;
- comparação “com e sem o jogador”;
- cartões de oportunidade para props, com risco, recorte e evidência;
- calendário e análises de confrontos futuros.

## Sobre a chave Groq

A chave é opcional por enquanto. Sem ela, o ScoreFlash já encontra equipes e entende consultas de média comuns. Com uma chave Groq configurada no arquivo `.env`, ele passa a usar uma LLM para organizar perguntas mais livres em um plano estruturado antes de buscar os dados.

Nunca coloque chaves no código ou em conversas. A chave que apareceu anteriormente deve ser revogada e não deve ser usada.

## Para desenvolvimento

```powershell
# API e testes
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Interface
Set-Location web
npm run build
```

## Estrutura principal

- `src/scoreflash/providers/search.py`: descoberta pública de equipes.
- `src/scoreflash/services/discovery.py`: resolução e persistência da equipe encontrada.
- `src/scoreflash/services/insights.py`: tradução determinística da amostra em texto humano.
- `src/scoreflash/llm/groq.py`: interpretação estruturada de perguntas livres via Groq.
- `web/`: interface React que conversa com a API local.
- `INICIAR-SCOREFLASH.cmd`: atalho para iniciar sem digitar comandos.
