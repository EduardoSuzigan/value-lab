# CLAUDE.md — value-lab

Contexto e regras de arquitetura para o Claude Code. Leia antes de implementar.
Projeto de estudo em **Ciência e Análise de Dados**, single-user, hobby.

---

## Propósito e princípio honesto

Ferramenta pessoal de análise estatística + detecção de valor em apostas
esportivas, começando por **futebol**. **Não** é um sistema de "lucro garantido":
o mercado é eficiente e uma modelagem caseira raramente bate a linha de fechamento
de forma consistente.

Dois critérios de sucesso, complementares:

- **Closing Line Value (CLV)** — o modelo encontra valor de forma consistente vs.
  a odd de fechamento? É a métrica honesta de *aposta*. Otimize e avalie por CLV,
  **nunca** por "ROI no histórico" (fácil de superajustar).
- **Qualidade probabilística** — as probabilidades são confiáveis? Avalie com
  **log-loss**, **Brier score** e **curva de calibração** (quando o modelo diz 60%,
  acontece ~60%?). É a métrica honesta de *ciência de dados* e o foco de aprendizado.

CLV responde "tem valor de aposta?"; calibração responde "minhas probabilidades
são confiáveis?". Queremos as duas.

---

## Right-sizing (importante)

Este projeto é single-user e hobby. **NÃO** introduzir Kafka, event-sourcing,
CQRS, bounded contexts, microsserviços **nem orquestradores pesados (Airflow)**.
A única separação que importa é: **ETL ↔ modelagem ↔ serviço de API permanecem
isolados**. Mantenha simples.

- **Airflow: não.** É always-on (scheduler + webserver + metadados + workers) e
  reintroduz o problema de "processo sempre ligado" que esta arquitetura evita.
  O pipeline aqui é um DAG linear de poucos passos. Se um dia a complexidade
  justificar orquestração com retries/dependências/observabilidade, reavaliar
  **Prefect/Dagster** (leves) ou **Temporal** — não antes.
- **dbt: diferido.** dbt transforma SQL; ele não ajusta um MLE de Poisson (o
  trabalho pesado é Python/scipy). Reconsiderar dbt **apenas** se: (a) praticar
  dbt for um objetivo de estudo explícito, ou (b) a camada de transformação
  crescer de fato. Nesse caso, escopo = staging/limpeza + **marts de avaliação**
  (agregados de CLV, bins de calibração, Brier por liga) — nunca o modelo
  estatístico. Para o MVP, SQL via SQLAlchemy (ou pandas) dá conta.

---

## Escopo

**MVP — Futebol, 7 ligas:**

- **Sólidas (5 europeias):** Inglaterra, Espanha, Alemanha, Itália, França.
  Cobertura excelente no football-data.co.uk, **com odds de fechamento** (ideal p/ CLV).
- **Boa:** Brasil (Brasileirão) — disponível nos feeds extras do mesmo site, com
  menos colunas de odds.
- **Experimental:** Arábia (Saudi Pro League) — dados históricos gratuitos com
  odds de fechamento são escassos. Entra com ressalva: histórico curto → modelo
  mais fraco e CLV menos confiável. Confirmar fonte na Fase 1 (talvez FBref via
  `soccerdata` p/ resultados + the-odds-api p/ odds ao vivo).

**Trilha separada — Copa do Mundo 2026:** seleções **não** são uma 8ª liga.
Não têm histórico de liga; o sinal vem de jogos internacionais (amistosos,
eliminatórias, Nations League) e modela-se tipicamente com **Elo/força de seleção**,
não Dixon-Coles. Manter como **módulo à parte** para não contaminar o modelo das
ligas. (O seed sintético com seleções é só placeholder de boot — sai na Fase 1.)

**Futuro:** outros esportes — daí o nome neutro `value-lab` e a separação por esporte
nas camadas de ETL e modelagem.

---

## Camadas e limites

- `app/domain/` — domínio PURO. `dixon_coles.py` (modelo), `value.py`
  (remove_vig/EV/Kelly), `eval.py` (calibração/Brier/log-loss). Sem I/O, sem SQL,
  sem FastAPI. Recebe DataFrames/dicts, devolve números. Testável isolado.
- `app/etl/` — ingestão de fontes externas → tabelas Match/Odds. `sources/` mantém
  um **registro por liga** (cada liga aponta p/ sua URL/parser). **Nunca** escreve
  em Prediction.
- `app/services/` — orquestra domínio + persistência (train, backtest, value).
- `app/api/` — só HTTP: valida, chama service/repo, serializa. **Sem matemática
  pesada e sem scipy** (precisa caber em função serverless leve).
- `worker/run.py` — **entrypoint chamável** do pipeline batch (`python -m worker.run`).
  Substitui o antigo loop APScheduler always-on. Disparado pelo GitHub Actions.

**Regra de ouro:** a API serve resultados **pré-computados**; ela **não** treina
modelo no caminho da request.

---

## Modelo de dados

`Team`, `League` (+ `season`), `Match` (placar None = jogo futuro), `Odds` (fonte
de verdade p/ CLV), `ModelRun` (cada ajuste é versionado, **por liga**),
`Prediction` (por run + match + market).

- `Match` referencia `league` + `season` (promovido/rebaixado muda o conjunto de
  times a cada ano; o decaimento temporal precisa da janela certa).
- `ModelRun` é **por liga** (ver Modelagem).
- Predições sempre referenciam o `run_id` — **nunca** sobrescreva; crie novo run.

---

## Modelagem

**Dixon-Coles por liga, NUNCA pooled.** Não misturar Brasileirão, Premier League e
Saudi no mesmo `fit`: força dos times, vantagem de casa e taxa de gols diferem entre
ligas; pooling distorce as forças relativas. `train.py` itera por `(liga, temporada)`
e gera um `ModelRun` por liga.

- Poisson de gols + correção de placares baixos (`rho`) + decaimento temporal (`xi`).
- Mercados: **1X2, Over/Under 2.5, BTTS**.
- Próximo salto de qualidade = incorporar **xG** (Understat/FBref via `soccerdata`)
  em vez de só gols.
- **Escalação:** o Dixon-Coles é cego a escalação (só usa gols históricos). Predição
  sensível a escalação é um **modelo diferente e mais rico** (disponibilidade de
  jogadores / ajuste por xG do XI anunciado) — Fase 4+. Mesmo lá, o treino continua
  offline; só o passo "ajustar o jogo de hoje pelo XI anunciado" roda perto do jogo,
  e é leve.

---

## Deploy e orquestração (grátis)

Topologia (tudo no tier grátis):

- **Frontend (Vite estático) → Vercel.** Encaixe nativo.
- **API de leitura (FastAPI serverless, sem scipy) → Vercel.** Bundle pequeno; só
  `SELECT` + serialização + aritmética leve de `value.py`. Exposta como função
  Python via `@vercel/python` (wrapper em `api/`).
- **Batch (ETL + treino, pesado, com scipy) → GitHub Actions.** `scipy/numpy/pandas`
  e o `L-BFGS-B` moram aqui, longe do teto de bundle (~250 MB) das funções da Vercel.
- **Postgres → Neon** (serverless, free). **Redis → Upstash, opcional/diferido**
  (com dados pré-computados 1x/dia, o cache quase perde função; começar sem).

**Regra:** GitHub Actions em **repositório público** = runners padrão **grátis e
ilimitados**. Segredos (`ODDS_API_KEY`, `DATABASE_URL`) em *Actions Secrets* / env
da Vercel — **nunca no código**.

### Os dois jobs (split por peso × frequência)

1. **`train` — pesado e raro.** `.github/workflows/train.yml`, cron **diário ou por
   rodada**. Roda `python -m worker.run`: ETL → treina Dixon-Coles por liga →
   grava `ModelRun` + `Prediction` no Neon. Resultado de futebol muda no máximo 1x/dia,
   então cadência diária basta.
2. **`refresh-odds` + `recompute-value` — leve e frequente.** Endpoint serverless na
   Vercel (rota protegida por `CRON_SECRET`), disparado por **scheduler HTTP externo**
   (Upstash QStash ou cron-job.org, tier grátis — confirmar limites) na frequência
   desejada perto do jogo. Captura o movimento das odds (o que muda perto do jogo,
   e o que o CLV precisa) e recalcula value bets. Não consome minuto de Actions.

Caveats do cron do Actions: pode atrasar sob carga (não é preciso ao segundo) e é
desabilitado após 60 dias sem atividade no repo — irrelevante p/ uso normal.

---

## Roadmap (harness-first)

- **Fase 0 — Harness:** testes do domínio. `pytest` para DixonColes (recupera forças
  sintéticas conhecidas), para value/remove_vig/Kelly, e para `eval` (calibração/Brier/
  log-loss). Backtest walk-forward de CLV ponta a ponta sobre **uma liga real**.
  NADA de feature nova antes disso.
- **Fase 1 — ETL real + multi-liga:** football-data.co.uk (5 europeias + Brasil),
  registro de fontes por liga, dimensão liga/temporada. Alembic para migrations
  (substituir o `create_all` do boot). Treino por liga no `worker/run.py`.
- **Fase 2 — Odds ao vivo + deploy:** The Odds API com captura de odds de fechamento;
  `train.yml` no Actions; endpoint leve `refresh-odds`/`recompute-value` na Vercel +
  scheduler externo; Neon como Postgres de produção.
- **Fase 3 — Frontend:** dashboard por liga (jogos, probabilidades, value bets) +
  painel de **CLV histórico** e **calibração** (as métricas que importam).
- **Fase 4 — Refino:** xG, decaimento calibrado, dixon-coles bivariado/bayesiano;
  trilha separada da Copa (Elo de seleções); explorar modelo sensível a escalação.

---

## Convenções

- Python: type hints; funções puras no domínio; sem lógica de negócio na API.
- Sem segredos no código (tudo via `app/config.Settings` / `.env` / Actions Secrets).
- Stake sempre via **Kelly fracionado** (default 25%); **nunca** Kelly cheio.
- Toda mudança no domínio precisa de teste correspondente (harness-first).
- A API nunca importa scipy nem treina; o batch nunca serve HTTP.

---

## Estrutura de pastas (alvo)

```
value-lab/
├─ CLAUDE.md
├─ README.md
├─ vercel.json
├─ .github/workflows/train.yml      # cron: ETL + treino (pesado)
├─ api/                             # Vercel Python serverless (wrapper da read-API)
│  └─ index.py
├─ backend/
│  ├─ app/
│  │  ├─ domain/      dixon_coles.py · value.py · eval.py
│  │  ├─ etl/         football_data.py · odds_api.py · sources/  (registro por liga)
│  │  ├─ services/    train.py · backtest.py · value_service.py
│  │  ├─ api/         routes.py  (leitura + refresh leve; sem scipy)
│  │  ├─ models.py · schemas.py · config.py · db.py · cache.py
│  ├─ worker/run.py   # entrypoint chamável (substitui o jobs.py always-on)
│  ├─ tests/          # Fase 0
│  ├─ alembic/        # Fase 1
│  └─ requirements.txt
└─ frontend/          # Vite 8 + React 19 + TS
```

---

## Versões (verificadas — jun/2026)

- **Node 24 LTS** (não usar Node 26 Current).
- **Python 3.13** (ecossistema científico estável; 3.14 é opcional).
- **FastAPI 0.132.x** (`fastapi[standard]`) · **Starlette 1.0** · **SQLAlchemy 2.0.47**
  · **Pydantic 2.13.x** + **pydantic-settings 2.14.x** · **uvicorn** atual.
- **scipy / numpy / pandas** atuais (só no backend/batch, nunca na função serverless).
- **Vite 8.1** + **@vitejs/plugin-react v6** · **React 19** · **TypeScript 5.x**.
  (Vite 7.3 é fallback zero-drama se preferir.)
- **Alembic** a partir da Fase 1.

---

## Tarefas iniciais sugeridas para o Claude Code

1. Renomear o namespace do projeto de `copa-value` p/ `value-lab`; tirar o
   `worker/jobs.py` always-on e criar `worker/run.py` como entrypoint chamável.
2. Criar `backend/tests/` com pytest cobrindo `domain/` (Fase 0), incluindo `eval`.
3. Adicionar dimensão `League`/`season` no `models.py` e fazer `train.py` iterar
   por liga (um `ModelRun` por liga).
4. Implementar walk-forward CLV de ponta a ponta sobre uma liga real.
5. Adicionar Alembic e remover `create_all` do lifespan.
6. Endpoints `/api/clv` e `/api/calibration` expondo backtest/avaliação p/ o dashboard.
7. `.github/workflows/train.yml` (cron diário rodando `python -m worker.run`).
8. Adaptar a read-API p/ função serverless da Vercel (`api/index.py`) + rota leve
   `refresh-odds`/`recompute-value` protegida por `CRON_SECRET`.
