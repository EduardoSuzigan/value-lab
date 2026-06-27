---
name: run-backtest
description: >
  Roda o backtest walk-forward de CLV + calibração (Brier/log-loss) de UMA liga e
  resume o resultado. Use quando quiser avaliar o modelo de uma liga e acompanhar
  cada passo no thread principal. Invoque com /run-backtest <liga> (ex.: E0, SP1, BRA).
---
# run-backtest

Argumento: `$0` = código da liga (ex.: `E0`, `SP1`, `D1`, `I1`, `F1`, `BRA`, `SAU`).

Passos:
1. Carregue partidas + odds de fechamento da liga `$0` (banco ou CSV de teste).
2. Walk-forward: para cada jogo, treina só com partidas anteriores e compara a
   prob. do modelo com a odd de fechamento (sem vig).
3. Calcule e reporte, no thread principal:
   - CLV: `beat_closing_rate`, `avg_ev`
   - Calibração: Brier, log-loss, e um resumo da curva por faixa.
4. Diga se o modelo bate a linha de forma consistente nessa liga, ou se o sinal é
   fraco (esperado p/ ligas de histórico curto, ex.: Saudi).

Não otimize por ROI histórico. O critério é CLV.
