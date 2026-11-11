# Piano 1.18.0: sbiadimento della carica di notte (fase 2, punto 4 di PIANO-LUX-FASI-v1.12.md)

Aperto l'11/11/2026 (CC Opus 5.5), ordine dell'utente "si'". Backup completo prima (backup-ruota.sh).

## Obiettivo
L'emozione di un ricordo sbiadisce notte dopo notte, ognuna con la sua velocita' (Fading Affect Bias: Walker 1997,
2003; Ritchie 2015), piu' piano se il ricordo e' ripetuto, il tema e' aperto, l'umore e' negativo (per le emozioni
negative) o il ricordo e' importante (Verduyn 2009/2011). La carica si avvicina a zero senza toccarlo. C0 resta
quella della nascita: la dose del vettore scende con la carica (D3 del 09/11).

## Testo del punto 4 (17/10)
    carica_domani = carica_oggi x (1 - sbiadimento x freno)
    freno = (1 - 0.3 x ripetizione) x (1 - 0.8 x aperta) x (1 - 0.5 x umore) x (1 - 0.6 x importanza)
- ripetizione = log(S/S0) / log(100) dell'arco;
- aperta = intervallo_medio / (intervallo_medio + tempo dall'ultima riaccensione) dei suoi engrammi, intervallo_medio
  = (acceso_U - nato_U) / accensioni; 0 se il ricordo e' stato corretto;
- umore = ansia e tristezza dall'omeostato, solo per le emozioni negative;
- importanza = salienza del ricordo (sal_dist, sal_se).
Pesi dagli studi, valori NON misurati: da tenere d'occhio nel rodaggio. Sbiadimento per emozione: tabella del 09/11
(lux.npz, chiave sbiadimento).

## Scelte di CC (provvisorie, le decide l'utente)
1. ripetizione e aperta fra 0 e 1 (taglio); aperta dell'arco = media dei suoi due engrammi; un engramma mai
   riapparso (accensioni 0) ha aperta 0.
2. umore = max(ansia, tristezza, 0) / 2 dell'omeostato (stato-emotivo.json, z; 2 z = umore pieno), letto senza
   toccare il file; negative = le 28 della divisione accettata il 16/10 (positive 16, neutre 7 = "solo attivazione").
3. importanza = media dei due ranghi di salienza del ricordo (0-1).
4. Rodaggio (punto 9) da un suo giorno di partenza, `sbiadimento_da` = giorno vissuto della produzione: 10% per 10
   giorni, 30%, 70%, poi 100%. Una sola volta per giorno vissuto (`sbiadito_fino`).
5. Lo sbiadimento NON cambia S0 e S (il punto 8 vale per il riconsolidamento): sbiadisce l'emozione, non il ricordo,
   che ha gia' la sua curva dell'oblio.
6. Nel servizio (POST /sbiadisci, notturna fra /riaccendi e /riconsolida), come riconsolida.

## Task
- [x] T0 backup
- [x] T1 test (test_sbiadimento_118; test_contatori_117 adattato), codice, revisione del codice (agente: difese su S0 = 0, omeostato con null, stato assente; decisione dell'utente 11/11 "stessa proporzione": la forza usa F0, firma degli engrammi alla nascita), conservazione (test di prima verdi)
- [x] T2 produzione 11/11: VERSIONE 1.18.0 + PRECEDENTE 1.17.0 + da-precedente + riavvii; /salute 1.18.0

## Rollback
VERSIONE e PRECEDENTE di prima (git), notte-memoria.sh da git, riavvio lux-engrammi e firma-subito.

## Stato
11/11: IN PRODUZIONE. Prima notte di sbiadimento: la notturna di stanotte (riga "sbiadisci:" nel log), rodaggio 10%.
Aperto per D1 del piano 1.14 (revisione 11/11): la sorpresa del riconsolidamento confronta il momento con la carica
SBIADITA, quindi cresce con lo sbiadimento e il riconsolidamento lo annullerebbe in parte; alternativa: confronto con C0.
