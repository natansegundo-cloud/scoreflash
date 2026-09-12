# Bot de Estatísticas de Futebol — Documentação do Projeto

## Visão Geral

Este projeto é um bot pessoal e gratuito que responde perguntas em linguagem natural sobre estatísticas de futebol, buscando os dados ao vivo no momento da pergunta em vez de manter um banco de dados pré-carregado com tudo. A ideia central é permitir perguntas do tipo "qual a média de finalizações do Flamengo jogando em casa nos últimos 5 jogos" e receber uma resposta narrada com os dados reais, sem precisar ter raspado o Brasileirão (ou qualquer outra liga) com antecedência para que a pergunta funcione.

O projeto nasceu de uma ideia mais ambiciosa — cobrir todos os esportes, todas as competições e também dados de jogadores — mas o escopo foi conscientemente reduzido para algo que é gratuito, tecnicamente viável e sustentável de manter sozinho. A versão que está documentada aqui é o ponto de partida real; a seção de expansão futura no final descreve como voltar a crescer o escopo depois que a base estiver funcionando.

## Objetivo e Caso de Uso

O usuário faz uma pergunta em português natural sobre futebol (times, campeonatos, jogos recentes, estatísticas de partida) e o bot:

1. Entende o que está sendo pedido (time, competição, tipo de estatística, recorte de jogos ou período)
2. Busca os dados correspondentes diretamente na fonte, ao vivo
3. Calcula o que for necessário (médias, comparações, etc.)
4. Responde em linguagem natural, com os números reais embutidos na resposta

Exemplo de uso: "qual a média de finalizações do Flamengo jogando em casa nos últimos 5 jogos" deve retornar uma resposta como "nos últimos 5 jogos em casa, o Flamengo teve uma média de X finalizações por partida", com os dados vindos de uma consulta feita na hora, não de uma tabela pré-calculada.

## Escopo do Projeto

**Dentro do escopo:**
- Apenas futebol (nenhum outro esporte, por enquanto)
- Times e campeonatos de qualquer país, com atenção especial para garantir cobertura das principais ligas mesmo de países de menor destaque no cenário futebolístico global, como Áustria, Dinamarca, Austrália, Turquia e Noruega — não só as ligas mais populares (Brasil, Inglaterra, Espanha, etc.)
- Estatísticas de partida: placar, resultado, e os dados da aba de estatísticas de cada jogo (posse de bola, finalizações, escanteios, cartões, e o que mais estiver disponível na fonte)
- Consultas históricas recentes (últimos N jogos de um time, últimos N jogos em casa/fora, etc.)

**Em expansão controlada:**
- Dados de jogadores individuais: a base atual já resolve atleta + clube e lê presenças, minutos, rating e calendário público. Estatísticas individuais de finalização, faltas e cartões ainda dependem de uma fonte verificável adicional; sem elas, o produto não deve recomendar uma prop.
- Outros esportes além de futebol
- Odds/apostas, embora a fonte de dados tecnicamente exponha esse tipo de informação também
- Qualquer tipo de scraping em massa ou pré-carregamento de temporadas inteiras — o projeto é deliberadamente "sob demanda"

## Arquitetura da Solução

A arquitetura é organizada em camadas, pensada para rodar de forma leve, sem depender de navegador headless (tipo Playwright/Selenium) para o dia a dia — o que seria pesado demais para rodar de forma contínua e gratuita.

**Camada de coleta de dados (fonte):** em vez de raspar as páginas renderizadas do FlashScore, o projeto acessa a API interna que o próprio site e aplicativo usam para carregar os dados por baixo dos panos. Essa API não é documentada oficialmente, mas seu formato de resposta já foi identificado: é um texto com um esquema de delimitadores próprio (não é JSON), que precisa ser decodificado por um parser específico. Um parser genérico para esse formato já foi escrito e entregue como ponto de partida (arquivo `flashscore_feed.py`). Essa camada é a mais frágil do projeto, porque depende de uma API não documentada que pode mudar sem aviso — ver seção de limitações abaixo.

**Camada de resolução (índice de nomes):** como a API interna trabalha por identificadores internos (IDs de país, competição, time), é necessário um índice que traduza nomes em linguagem natural ("Flamengo", "Bundesliga da Áustria") para esses IDs. Esse índice é pequeno comparado a um banco de partidas completo — ele guarda só a árvore de países → competições → times, não o histórico de jogos em si — e pode ser atualizado periodicamente (por exemplo, uma vez por semana ou por mês) sem custo relevante.

**Camada de interpretação da pergunta (LLM):** a pergunta em linguagem natural do usuário é enviada para uma LLM gratuita configurada com "function calling"/tool use, que extrai os parâmetros estruturados da pergunta: time, competição (se mencionada), tipo de estatística pedida, recorte de jogos (quantos, mandante/visitante, período). A LLM não calcula nada sozinha nessa etapa — ela só traduz linguagem natural em parâmetros estruturados que o código consegue usar.

**Camada de execução:** com os parâmetros em mãos, o código resolve os nomes para IDs (camada de resolução), consulta a API interna da fonte de dados para buscar os jogos e estatísticas necessários, e faz os cálculos pedidos (médias, comparações, etc.). Um cache local guarda respostas recentes para evitar repetir a mesma consulta à fonte em um curto intervalo de tempo, tanto para ganhar velocidade quanto para reduzir o volume de requisições feitas à fonte externa.

**Camada de resposta (LLM novamente):** o resultado calculado é devolvido para a LLM, que o transforma em uma resposta em linguagem natural para o usuário, com os números reais embutidos no texto.

## Fluxo de uma Consulta, Passo a Passo

1. Usuário pergunta algo em linguagem natural
2. LLM extrai os parâmetros da pergunta (time, competição, estatística, recorte)
3. Código resolve os nomes mencionados para os IDs internos da fonte, usando o índice local
4. Código verifica se já existe uma resposta em cache recente para essa consulta; se não existir, busca ao vivo na API interna da fonte
5. Código calcula o que foi pedido a partir dos dados retornados
6. Resultado é salvo em cache
7. LLM recebe o resultado calculado e gera a resposta final em linguagem natural
8. Resposta é entregue ao usuário

## Requisitos Técnicos e Contas Necessárias

- **Groq (LLM gratuita):** conta gratuita na Groq, sem cartão de crédito, para acesso a modelos como o Llama 3.3 70B via API compatível com o padrão OpenAI. É a mesma LLM já usada em outro projeto pessoal (bot de afiliados no Telegram), então a integração já é familiar. O modelo precisa suportar function calling/tool use para a etapa de interpretação da pergunta.
- **Python** como linguagem principal do projeto, mantendo consistência com os outros bots já construídos.
- **Banco de dados leve (SQLite)** para o índice de países/competições/times e para o cache de consultas recentes — não é necessário um banco robusto porque o volume de dados armazenado é pequeno (a arquitetura é "sob demanda", não um espelho completo da fonte).
- **Hospedagem gratuita:** Railway (já usado no bot de afiliados) ou a VPS gratuita da Oracle Cloud (já cogitada em outro projeto) são as opções naturais para rodar o serviço continuamente sem custo.
- **Captura manual de tráfego via navegador (DevTools):** antes da implementação da camada de coleta de dados, é necessário abrir o site da fonte no navegador, usar as ferramentas de desenvolvedor (F12 → aba Network → filtro Fetch/XHR) para capturar exemplos reais das chamadas que o próprio site faz, e usar esses exemplos para validar e ajustar o parser já entregue. Essa etapa não tem como ser automatizada de forma confiável sem antes ter exemplos reais capturados manualmente.

## Limitações e Riscos Conhecidos

- A fonte de dados (FlashScore) não possui API pública oficial. A API interna usada aqui foi identificada por engenharia reversa de terceiros e não é documentada nem garantida — os formatos de resposta e os parâmetros podem mudar sem aviso, exigindo manutenção pontual do parser e dos endpoints usados.
- Os termos de uso da fonte de dados normalmente proíbem scraping. O uso aqui é pessoal, de baixa escala e sob demanda (uma consulta por pergunta feita, não uma varredura em massa), o que reduz bastante o risco em comparação a tentar espelhar o site inteiro — mas o risco de bloqueio de IP ou instabilidade nunca é zero, e o projeto deve evitar volume alto de requisições em curto espaço de tempo.
- Dados de jogadores individuais ficaram fora do escopo por não estarem disponíveis de forma limpa na mesma API interna usada para times e partidas.
- Times e competições muito obscuros ou de ligas amadoras podem não estar bem indexados na fonte de dados ou podem exigir tratamento específico no índice de nomes.

## Status Atual

- A ideia e a arquitetura foram desenhadas e validadas em conversa
- Um repositório público (Node.js + Playwright) foi avaliado como possível base, mas descartado por não atender ao objetivo de cobertura ampla e por depender de navegador headless, mais pesado do que o necessário
- Um parser genérico para o formato de feed da API interna do FlashScore já foi escrito (`flashscore_feed.py`) e está pronto para ser testado assim que uma URL/feed real for capturado via DevTools
- Nenhuma captura de tráfego real, mapeamento de campos, índice de times/competições ou integração com a Groq foi feita ainda

## Roadmap de Construção Sugerido

1. Capturar exemplos reais de chamadas da API interna via DevTools (lista de países, lista de competições de um país, lista de times de uma competição, dados de uma partida específica) e validar/ajustar o parser genérico já entregue contra esses exemplos reais
2. Mapear os campos retornados (descobrir o que cada chave interna representa: nome do time, data, placar, categoria de estatística, etc.)
3. Construir o índice local de países → competições → times a partir desses dados mapeados
4. Construir a camada de resolução de nomes (texto livre → IDs internos), incluindo tratamento de apelidos e variações de nome de time
5. Construir a camada de busca ao vivo de jogos recentes e estatísticas de um time, usando o índice e a API interna
6. Adicionar o cache local de consultas recentes
7. Integrar a Groq com function calling para interpretar a pergunta em parâmetros estruturados
8. Integrar a Groq novamente para narrar a resposta final a partir dos dados calculados
9. Expor o bot através de uma interface de uso (por exemplo, um bot de Telegram, reaproveitando a experiência já existente com o bot de afiliados)
10. Hospedar de forma contínua (Railway ou VPS gratuita da Oracle Cloud)

## Possibilidades de Expansão Futura

A arquitetura sob demanda foi escolhida justamente por facilitar expansão sem precisar redesenhar o projeto do zero:

- **Outros esportes:** a mesma API interna da fonte de dados cobre múltiplos esportes além de futebol; adicionar um novo esporte é principalmente uma questão de mapear os campos específicos daquele esporte, reaproveitando toda a arquitetura de resolução, cache, LLM e interface já construída
- **Dados de jogadores:** pode ser adicionado depois como uma camada extra de scraping tradicional (não pela API interna), específica para páginas de jogador, mantendo o resto do sistema intacto
- **Outras fontes de dados:** se a fonte principal ficar instável ou bloquear o acesso, a arquitetura em camadas permite trocar ou adicionar uma segunda fonte sem mudar a camada de interpretação de pergunta (LLM) nem a interface do bot
- **Odds/mercados de apostas:** a mesma API interna expõe esse tipo de dado, caso vire um interesse futuro
- **Mais interfaces:** além do Telegram, o mesmo motor de consultas pode ser exposto por outros canais (web, WhatsApp, etc.) sem alterar a lógica central
