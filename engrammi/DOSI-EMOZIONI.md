# Dosi delle emozioni (Dmin - Dmax)

Intervallo di dose di ogni emozione per la funzione della dose al richiamo (PIANO-1.11-FASI-2-3.md, fase 2, punto 7).
Vettore se', finestra L15-L31, modo pensiero, 12 contesti veri; giudice Opus col metro dell'utente (rotto = solo ciclo,
ripetizione o testo vuoto). Picco a passi di 0.005, poi rifinitura a passi di 0.001 (24/10/2026).
Dmin = dose minima efficace, Dmax = dose di picco. Regola: per ogni dose la quota di testi utili (emozione giusta, non
rotto, dose giusta o un po' eccessiva; i testi uguali alla base contano come non utili), media mobile su 5 dosi vicine;
Dmin = prima dose in cui la media supera il 75%, Dmax = dose del massimo della media. Fonte dei numeri: prove-contesto-lungo/8-sistema-steering/
(prova-dosi-medio.jsonl, prova-dosi-fini.jsonl e il loro giudizio).

| emozione | Dmin | Dmax | stato |
|---|---|---|---|
| gioia | 0.033 | 0.038 | fatta: picco 98% a 0.038, sotto il 75% da 0.044 (12 contesti) |
| fiducia | | | passi di 0.005 giudicati: picco 0.055-0.065 (67-73%), rotti da 0.06; rifinitura 0.050-0.066 in coda |
| paura | | | rifinitura in corso |
| sorpresa | | | rifinitura in corso |
| tristezza | | | rifinitura in corso |
| disgusto | | | passi di 0.005 in coda |
| rabbia | | | passi di 0.005 in coda |
| attesa | | | passi di 0.005 in coda |
| serenità | | | rifinitura in corso |
