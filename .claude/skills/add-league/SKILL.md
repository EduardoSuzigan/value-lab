---
name: add-league
description: >
  Procedimento para registrar uma NOVA liga no pipeline (fonte de dados, parser,
  temporada, smoke test). Use ao expandir além das ligas iniciais. Invoque com
  /add-league ou deixe auto-disparar quando a tarefa for "adicionar liga X".
---
# add-league

Adicionar uma liga deve tocar SEMPRE estes pontos, em ordem:

1. **Identidade**: adicione a `League` (código + nome + país) e a `season` correta.
   Confirme normalização de nomes de times com as fontes.
2. **Fonte de dados** (`backend/app/etl/sources/`): crie/registre o parser da liga
   apontando p/ a URL (football-data.co.uk p/ europeias + Brasil; p/ Saudi, avalie
   FBref via `soccerdata` + the-odds-api, e MARQUE como experimental).
3. **ETL**: mapeie placar + odds de fechamento p/ Match/Odds. Nunca toque Prediction.
4. **Treino**: garanta que `train.py` gera um `ModelRun` próprio p/ a liga
   (fit por liga, nunca pooled).
5. **Smoke test**: ingere uma amostra e treina sem erro; se a liga tiver histórico
   curto, registre a ressalva de confiabilidade do CLV.
6. **Frontend**: a liga aparece no seletor do dashboard.

Saída: resuma o que foi adicionado e rode `/run-backtest <liga>` para validar.
