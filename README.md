# value-lab

Ferramenta pessoal de análise estatística + detecção de **value** em apostas
esportivas, começando por **futebol**. Projeto de estudo em Ciência e Análise de
Dados — single-user, hobby.

> **Princípio honesto:** isto não é um sistema de "lucro garantido". O mercado é
> eficiente. O sucesso é medido por **Closing Line Value (CLV)** e por **qualidade
> probabilística** (log-loss, Brier, calibração) — nunca por "ROI no histórico".

Veja [`CLAUDE.md`](./CLAUDE.md) para arquitetura, regras e roadmap completos.

## Arquitetura (resumo)

| Camada | Onde mora | Papel |
|---|---|---|
| Domínio puro | `backend/app/domain/` | Dixon-Coles, value (devig/EV/Kelly), eval (calibração/Brier/log-loss). Sem I/O. |
| ETL | `backend/app/etl/` | Ingestão → `Match`/`Odds`. Registro de fontes por liga. |
| Services | `backend/app/services/` | Orquestra domínio + persistência (train, backtest, value). |
| Read-API | `backend/app/api/` + `api/` | HTTP leve, **sem scipy**, serve resultado pré-computado. |
| Batch | `backend/worker/run.py` | Entrypoint chamável (`python -m worker.run`), disparado por GitHub Actions. |

**Regra de ouro:** a API serve resultados **pré-computados**; nunca treina no caminho da request.

## Deploy (tier grátis)

Frontend (Vite) → **Vercel** · Read-API serverless → **Vercel** · Batch (ETL+treino) →
**GitHub Actions** · Postgres → **Neon**.

## Desenvolvimento

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q            # harness do domínio (Fase 0)
```

## Roadmap (harness-first)

- **Fase 0** — Harness: testes do domínio + backtest walk-forward de CLV (em andamento).
- **Fase 1** — ETL real multi-liga (football-data.co.uk) + Alembic.
- **Fase 2** — Odds ao vivo (The Odds API) + deploy (Actions/Vercel/Neon).
- **Fase 3** — Frontend (dashboard por liga, CLV e calibração).
- **Fase 4** — Refino: xG, decaimento calibrado, trilha da Copa (Elo de seleções).
