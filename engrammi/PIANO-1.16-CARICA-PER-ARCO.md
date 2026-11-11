# Piano 1.16.0: carica diversa fra gli archi di un ricordo (fase 2, punto 2 di PIANO-LUX-FASI-v1.12.md)

Aperto l'11/11/2026 (CC Opus 5.5), ordine dell'utente "2". Backup completo prima (engrammi/backup/4).

## Obiettivo
Dentro un ricordo l'emozione si concentra sugli elementi centrali; i dettagli di contorno ne portano meno (Kensinger
2009; Burke, Heuer e Reisberg 1992; Mather 2007). Il testo del punto 2 (carica dell'arco dalla F dei suoi engrammi) e'
stato rovesciato da D4 di PIANO-FIRMA-ENGRAMMI (31/10): l'arco prende la firma del ricordo. Resta la differenza
fra centrali e contorno.

## Decisioni
- 11/11 (l'utente, "vicinanza al senso"): un engramma e' centrale quanto il suo vettore bge-m3 e' vicino al senso del
  ricordo (media normalizzata dei vettori dei suoi engrammi). Centralita' dell'arco = media dei coseni dei suoi due
  engrammi (negativi a zero).
- Peso dell'arco W = (centralita' / media del ricordo) ^ CONTRASTO, poi riportato a media 1 nel ricordo: la media delle
  cariche del ricordo resta firma x fattore. CONTRASTO = 3, valore PROVVISORIO di CC (misura 11/11 su 627 ricordi: col
  coseno puro i pesi vanno in mediana da 0.88 a 1.10, cioe' +-10%; con 3 circa 0.68-1.33). Lo decide l'utente.
- Ricordi con un arco solo, correzioni (carica zero) e legami fra ricordi: W = 1.

## Architettura
1. lux.npz: `W` (un peso per arco, float32). C = firma x fattore x W, C0 uguale alla nascita.
2. pesi_archi(A, V, righe): funzione unica, usata da costruisci, da_precedente (1.15.0 -> 1.16.0: C e C0 per W, F
   ricalcolata) e _aggiungi (archi nuovi).
3. riconsolida: il momento di ogni arco e' momento x fattore x W[j] (bersaglio piu' alto sugli archi centrali); sorpresa
   e stabilita' iniziale sulla carica riportata alla firma grezza (C / (fattore x W)).

## Task
- [x] T0 backup
- [x] T1 test (test_carica_116; test_riconsolida e test_tabella_115 adattati), codice, revisione del codice (agente: freno PASSO_MAX sulla firma grezza, pulisci_ricordi_0111.py bloccato dalla 1.14.0), conservazione (test di prima verdi)
- [x] T2 produzione 11/11: VERSIONE 1.16.0 + PRECEDENTE 1.15.0 + da-precedente + riavvii; /salute 1.16.0; pesi da 0.27 a 1.71

## Rollback
VERSIONE e PRECEDENTE di prima (git), riavvio lux-engrammi e firma-subito; lux-1.16.0/ resta li'.

## Stato
11/11: IN PRODUZIONE. Misura: rapporto centrale/contorno in mediana 2.03; forza del ricordo in mediana invariata
(0.92-1.04); col vettore 450 ricordi invece di 453 (6 scendono sotto 0.5, 3 salgono, tutti gia' fra 0.50 e 0.55
tranne il 74: 0.545 -> 0.325).
