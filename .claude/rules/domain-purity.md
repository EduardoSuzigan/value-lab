---
paths:
  - "backend/app/domain/**"
---
Domínio PURO. Pode usar numpy/scipy/pandas (matemática), mas é PROIBIDO importar
sqlalchemy, httpx, fastapi, redis, ou fazer qualquer I/O de rede/arquivo/SQL aqui.
Funções determinísticas: recebem DataFrames/dicts, devolvem números.
Toda mudança no domínio exige um teste correspondente (harness-first).
