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
| etl | `backend/app/etl/football_data.py` | `season_url`/`parse`/`download`/`load` → schema **Match/Odds** normalizado (odds de abertura+fechamento) |
| config | `backend/app/config.py` | `Settings` via env/.env (db, odds_api_key, cron_secret, kelly) |

**Resultado honesto em dados reais (E0 2122–2324, 1140 jogos):** calibração boa
(Brier 0.192 < base rates 0.212, curva ~diagonal) mas **sem CLV** (beat_closing 0.40).
Confirma a tese do projeto: probabilidades confiáveis ≠ vencer a linha de fechamento.

**Ainda NÃO existe:** persistência (sem `models.py`/`db.py`/Alembic), `worker/run.py`,
`services/train.py`, camada `api/`, frontend, GitHub Actions. ETL hoje devolve DataFrame
em memória (ainda não grava em banco) — foi a escolha deliberada de "ver os dados antes do schema".

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

## 4. Próximos passos — fechar a Fase 1 (persistência + multi-liga)

Ordem sugerida (TDD onde houver lógica; migrations não precisam de teste):

1. **`models.py` (SQLAlchemy 2.0) + `db.py`** — `Team`, `League(+season)`, `Match`
   (placar `None` = jogo futuro, FK liga+season), `Odds` (abertura/fechamento por mercado,
   FK match), `ModelRun` (por liga, append-only), `Prediction` (por run+match+market, append-only).
   `db.py` = engine/session (SQLite local via `settings.database_url`; Neon fica p/ Fase 2).
2. **Alembic** — `alembic init`, configurar `target_metadata`, 1ª migration; remover qualquer `create_all`.
   (Atenção: SQLite precisa de `render_as_batch=True` p/ ALTER.)
3. **ETL persistente** — função que pega o DataFrame do `football_data.load()` e faz **upsert
   idempotente** em `Match`/`Odds` (chave natural: liga+season+date+home+away). Nunca toca Prediction.
4. **`services/train.py`** — itera por `(liga, temporada)`, faz `dixon_coles.fit` por liga (use `xi>0`),
   grava um `ModelRun` por liga + `Prediction` por match/market. Reaproveita `domain/`.
5. **`worker/run.py`** — entrypoint `python -m worker.run`: ETL (ligas do registry) → train. Sem HTTP.
6. **Multi-liga** — baixar as 5 europeias + Brasil (registry já tem; siga `.claude/skills/add-league`),
   smoke test por liga, marcar histórico curto onde o CLV é menos confiável.

**Decisões a confirmar no início da próxima sessão:** (a) SQLite local agora vs. já apontar Neon;
(b) granularidade de `Prediction` (todos os mercados 1X2/OU2.5/BTTS de uma vez?); (c) backtest deve
ler do banco ou continuar consumindo DataFrame.

### Verificação rápida ao abrir a sessão
```bash
cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check app/ tests/
```
Demo end-to-end de referência (rede): havia um script em scratchpad fazendo
`football_data.load("E0", ...)` → `backtest.walk_forward_clv`; replicável em `worker/run.py`.
