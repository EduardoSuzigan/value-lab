---
paths:
  - "backend/app/models.py"
  - "backend/app/services/train.py"
  - "backend/app/etl/**"
---
Prediction e ModelRun são APPEND-ONLY. Cada ajuste do modelo cria um NOVO ModelRun;
nunca sobrescreva predições existentes — toda Prediction referencia seu run_id.
O ETL escreve SOMENTE em Match/Odds; NUNCA em Prediction nem ModelRun.
Odds é a fonte de verdade para CLV — não a derive do modelo.
