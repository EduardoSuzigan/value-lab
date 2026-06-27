---
paths:
  - "backend/app/services/train.py"
  - "backend/app/services/backtest.py"
  - "backend/app/domain/dixon_coles.py"
---
Ajuste o Dixon-Coles POR (liga, temporada). NUNCA faça pooling entre ligas: força
dos times, vantagem de casa e taxa de gols diferem entre Brasileirão/Premier/Saudi,
e misturar distorce as forças relativas. train.py itera por liga e gera um ModelRun
por liga. Copa do Mundo é trilha separada (Elo de seleções), não uma "8ª liga".
