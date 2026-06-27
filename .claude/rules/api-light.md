---
paths:
  - "backend/app/api/**"
  - "api/**"
---
A read-API roda como função serverless leve (limite ~250 MB de bundle na Vercel).
PROIBIDO importar scipy/numpy/sklearn/statsmodels aqui, e PROIBIDO treinar modelo
ou fazer matemática de modelo no caminho da request. A API só: valida entrada,
chama service/repo, serializa, e usa value.py (Python puro). Regra de ouro:
a API serve resultado PRÉ-COMPUTADO; quem treina é o batch (worker/run.py).
