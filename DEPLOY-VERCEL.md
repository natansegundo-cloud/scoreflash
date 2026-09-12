# Publicar o ScoreFlash na Vercel

O ScoreFlash é publicado em **dois projetos Vercel**. Pense em dois cômodos:

- **API**: é o cérebro. Ela busca dados e guarda as chaves.
- **Web**: é a tela que seus amigos abrem.

Fazemos assim para nenhuma chave aparecer no navegador de outra pessoa.

## Antes de começar

Você precisa de uma conta na Vercel e de um repositório no GitHub contendo esta pasta. Não envie o arquivo `.env` para o GitHub.

> A chave da Groq que foi compartilhada anteriormente deve ser revogada. Crie uma nova antes de publicar.

## Parte 1 — publicar o cérebro

1. Abra [vercel.com/new](https://vercel.com/new) e entre com sua conta.
2. Importe o repositório do ScoreFlash.
3. Em **Root Directory**, deixe vazio (a pasta principal do projeto).
4. Clique em **Deploy**. A Vercel reconhece o FastAPI automaticamente.
5. Quando terminar, abra **Settings** > **Environment Variables**.
6. Clique em **Add** e crie estas variáveis para **Production**:

| Nome | O que colar |
| --- | --- |
| `GROQ_API_KEY` | A nova chave da sua conta Groq. É opcional, mas deixa perguntas livres mais inteligentes. |
| `API_FOOTBALL_API_KEY` | Sua chave da API-Football. Necessária apenas para métricas individuais de jogador. |
| `SCOREFLASH_ALLOW_LOCAL_KEY_SETUP` | `false` |

7. Clique em **Deployments**, abra os três pontos do último deploy e escolha **Redeploy**.
8. Copie a URL que termina em `.vercel.app`. Ela é a URL da sua API.

## Parte 2 — publicar a tela

1. Volte em [vercel.com/new](https://vercel.com/new) e importe **o mesmo repositório mais uma vez**.
2. Desta vez, em **Root Directory**, escolha `web`.
3. Antes de clicar em Deploy, abra **Environment Variables** e adicione:

| Nome | O que colar |
| --- | --- |
| `VITE_API_BASE_URL` | A URL da API copiada na Parte 1. Exemplo: `https://scoreflash-api.vercel.app` |
| `VITE_ENABLE_LOCAL_KEY_SETUP` | `false` |

4. Clique em **Deploy**.
5. Abra a URL final no celular e faça uma pergunta de teste, por exemplo: `Qual a média de finalizações do Flamengo nos últimos 5 jogos?`

Pronto: a segunda URL é a que você manda aos seus amigos.

## O que acontece na versão pública

- Qualquer visitante consulta médias de times sem criar conta e sem configurar nada.
- As chaves ficam só na Vercel, fora do navegador.
- O botão de configuração de chave desaparece da versão pública.
- Equipes ainda são encontradas automaticamente. Como o armazenamento temporário da Vercel pode ser reiniciado, o cache e os nomes já descobertos podem sumir ocasionalmente — mas uma nova busca encontra a equipe de novo.

## Se uma atualização não aparecer

Depois de alterar uma variável na Vercel, faça **Redeploy**. Variáveis novas só entram em deploys criados depois da alteração, conforme a [documentação da Vercel](https://vercel.com/docs/environment-variables).

O backend usa a runtime Python/FastAPI oficial da Vercel; a documentação atual confirma que ela identifica uma aplicação `app` definida no projeto e a executa como Function: [guia FastAPI da Vercel](https://vercel.com/docs/frameworks/backend/fastapi).
