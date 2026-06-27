# HAND-OFF — value-lab

Estado e instruções para continuar em uma nova sessão. Leia junto com o
[`CLAUDE.md`](./CLAUDE.md) (arquitetura/regras/roadmap) e `.claude/rules/*`.

_Atualizado: 2026-06-27. Branch de trabalho: **`development`** (toda execução parte dela)._

---

## 1. O que já está pronto

**Fase 0 — harness do domínio (100% TDD)** e **slice de ETL real** — 64 testes, ruff limpo.

| Camada | Arquivo | O que faz |
|---|---|---|
| domínio | `backend/app/domain/value.py` | devig (proporcional), EV, Kelly fracionado (25%) |
| domínio | `backend/app/domain/eval.py` | Brier, log-loss, curva de calibração |
| domínio | `backend/app/domain/dixon_coles.py` | Poisson bivariado + tau(rho) + decaimento(xi), MLE L-BFGS-B, `predict()` 1X2/OU2.5/BTTS |
| services | `backend/app/services/backtest.py` | walk-forward de CLV (sem look-ahead) + calibração, `base_rate_brier` |
| etl | `backend/app/etl/sources/registry.py` | registro de fontes por liga (5 europeias + Brasil) |
| etl | `backend/app/etl/football_data.py` | `parse`/`load` (feed `mmz4281`, EU, abertura+fechamento) **+ `parse_new`/`load_new`** (feed `/new/`, Brasil: arquivo único, só fechamento). Registry tem campo `feed`; worker despacha. |
| config | `backend/app/config.py` | `Settings` via env/.env (db, odds_api_key, cron_secret, kelly) |
| models | `backend/app/models.py` | SQLAlchemy 2.0: Team, League, Match (placar None=futuro), Odds, ModelRun (por liga, append-only), Prediction (por run+match+market+selection) |
| db | `backend/app/db.py` | engine/session; `make_engine` (StaticPool + PRAGMA FK p/ SQLite); aponta `settings.database_url` |
| migr | `backend/alembic/` | env.py lê Settings, `render_as_batch` só em SQLite; migration inicial aplicada no Neon; teste de drift |
| etl | `backend/app/etl/persist.py` | `upsert_matches`: DataFrame → Match/Odds, upsert idempotente (chave liga+season+home+away); nunca toca Prediction |
| services | `backend/app/services/dataset.py` | `load_matches_df`: Match/Odds do banco → DataFrame do backtest (decisão c) |
| services | `backend/app/services/train.py` | `train_league`: fit por (liga,temporada) → 1 ModelRun + Predictions (7 mercados/jogo), append-only |
| worker | `backend/worker/run.py` | entrypoint `python -m worker.run --seasons … [--leagues …]`: ETL→train, sem HTTP |

**Resultado honesto em dados reais (E0 2122–2324, 1140 jogos):** calibração boa
(Brier 0.192 < base rates 0.212, curva ~diagonal) mas **sem CLV** (beat_closing 0.40).
Confirma a tese do projeto: probabilidades confiáveis ≠ vencer a linha de fechamento.

**Persistência (Fase 1) PRONTA** — Neon Postgres 17 (sa-east-1) provisionado; `DATABASE_URL`
em `backend/.env` (gitignored). Pipeline validado ponta a ponta no Neon. **6 ligas ingeridas**
(5 europeias 2324–2526 via `mmz4281` + **Brasil** 2023–2025 via feed `/new/`); backtest lê do
banco via `load_matches_df`. **94 testes verdes** (incl. guarda de drift de migration), ruff limpo.

- **Brasil = só calibração, sem CLV.** O feed `/new/BRA.csv` traz só odds de FECHAMENTO
  (sem abertura) → `Odds.open=None`, sem preço de entrada → sem value bet/CLV. O walk-forward
  ignora bets quando falta abertura e ainda calcula calibração (BRA 2025: Brier 0.202 < base 0.212).
- **Reprodutibilidade:** o fit Dixon-Coles tem leve deriva entre processos/ambientes (~0.5pp no
  beat_closing; Brier idêntico). Estável dentro do mesmo ambiente. Se virar problema, fixar
  threads de BLAS / semente do otimizador.

**Ainda NÃO existe:** camada `api/` (read-API serverless), frontend, GitHub Actions (`train.yml`).

---

## 2. Ambiente (importante — peculiaridades desta máquina WSL2)

- **Venv via `uv`** (o `python3.14-venv`/`pip` do sistema não existem). Venv em `backend/.venv`.
  - Rodar testes: `cd backend && .venv/bin/python -m pytest -q`
  - Lint/format: `.venv/bin/ruff check app/ tests/` · `.venv/bin/ruff format ...`
  - Instalar pacote novo: `uv pip install --python .venv <pkg>` (e adicionar ao `requirements.txt`).
  - `uv` está em `~/.local/bin`.
- **`gh` CLI tem DNS quebrado** (resolvedor Go → `10.255.255.254:53 no such host`). `curl`/`git`/Python
  funcionam (glibc). Para GitHub: use `git` (push/pull já funcionam — `gh` é credential helper) e,
  para a API, `curl` com `gh auth token`. **Não** use `gh repo/pr/api` direto. Rede **não** precisa ser `mirrored`.
- **Comandos de rede** (download de dados, push): rode com o sandbox desabilitado.
- Hooks do `.claude` (`format`/`test-domain`) já acham `ruff`/`pytest` no venv automaticamente.

---

## 3. Invariantes a respeitar (resumo — detalhes em `.claude/rules/`)

- **Domínio puro:** `app/domain/` só matemática (numpy/scipy/pandas). Proibido sqlalchemy/httpx/fastapi/redis/I-O.
- **Fit por (liga, temporada), nunca pooled.** Copa = trilha separada (Elo), não 8ª liga.
- **Append-only:** `Prediction`/`ModelRun` nunca sobrescritos; ETL escreve só `Match`/`Odds`. Odds = fonte de verdade do CLV.
- **API leve:** `api/` e `app/api/` sem scipy/numpy, sem treinar no caminho da request (hook bloqueia).
- **Honestidade:** otimizar/avaliar por **CLV + calibração**, nunca ROI histórico.
- **Harness-first/TDD:** toda mudança no domínio vem com teste (red→green).
- **Segredos:** só via `Settings`/`.env`/Actions Secrets.

---

## 4. Fase 1 — fechada (persistência + multi-liga). O que falta

Itens 1–6 **prontos** (TDD; ver tabela da seção 1). 6 ligas ingeridas no Neon
(5 europeias + Brasil). **Decisões resolvidas nesta sessão:**
(a) **Neon** p/ app+migrations, **SQLite in-memory** p/ testes (schema dialect-agnóstico);
(b) `Prediction` por **(run, match, market, selection)** — todos os mercados de uma vez;
(c) backtest **lê do banco** via `load_matches_df`, mantendo o `walk_forward_clv` puro.

Próximos passos:

1. **Perf do upsert** — hoje é linha-a-linha sobre a rede (~3 min/liga/3 temporadas no Neon).
   Trocar por `bulk_insert`/batch quando incomodar (não muda correção, só velocidade).
2. **Fase 2 — Odds ao vivo + deploy:** The Odds API (captura write-once da linha de
   FECHAMENTO — não sobrescrever como o ETL atual faz), `train.yml` no Actions, endpoint
   leve `refresh-odds`/`recompute-value` na Vercel + scheduler externo.
3. **Camada `api/`** — read-API serverless (sem scipy): `/api/clv`, `/api/calibration`,
   jogos+probabilidades+value bets a partir de `ModelRun`/`Prediction`/`Odds` pré-computados.
4. **Mercados OU25/BTTS no ETL** — `Prediction`/schema já suportam; falta o parser de odds
   desses mercados em `football_data.py` (hoje só persiste 1X2).
5. **Fase 3 — Frontend:** dashboard por liga + painéis de CLV histórico e calibração.

### Verificação rápida ao abrir a sessão
```bash
cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check app/ tests/
```
Pipeline end-to-end (rede; rodar com sandbox desabilitado):
`python -m worker.run --seasons 2324 2425 2526 --leagues E0` (ETL→train no Neon).
Backtest do banco: `load_matches_df(session, "E0", "2526")` → `backtest.walk_forward_clv`.
