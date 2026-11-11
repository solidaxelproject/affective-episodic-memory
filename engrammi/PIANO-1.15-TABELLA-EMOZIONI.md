# Piano 1.15.0: tabella delle emozioni nel Lux (fase 2, punto 1 di PIANO-LUX-FASI-v1.12.md)

Aperto l'11/11/2026 (CC Opus 5.5), ordine dell'utente "parti dall'1". Backup completo prima (backup-ruota.sh).

## Obiettivo
Le 51 emozioni hanno nel Lux il loro fattore alla nascita e il loro sbiadimento per notte (tabella decisa dall'utente il
09/11, engrammi/PROPOSTA-TABELLA-EMOZIONI.md, D1 e D2). La carica di un arco alla nascita = fattore dell'emozione x
firma: le emozioni ad alta attivazione fissano di piu' il ricordo (Kensinger 2009, McGaugh 2004).

## Decisioni
- 09/11: D1 fattori 1.0 / 0.8 / 0.6 / 0.4, variabile 0.6; D2 emivite 30 / 90 / 180 / 365 / 3650 notti.
- 11/11 (l'utente, "sulla carica, effetto pieno"): il fattore moltiplica la carica e la dose del vettore scende con lei.
  Misura sui 633 ricordi: col vettore da 545 a 453; a fattore 0.4 da quasi tutti a 16 su 83; a 1.0 36 su 42.
- Conseguenza (CC): il riconsolidamento confronta la carica col momento nella stessa scala, momento x fattore (se no il
  riconsolidamento riporterebbe la carica alla firma grezza e annullerebbe il fattore). M tiene il momento grezzo.

## Architettura
1. lux.npz: `fattore` e `sbiadimento` (51 valori, ordine EMOZIONI) letti da PROPOSTA-TABELLA-EMOZIONI.md
   (tabella_emozioni()); sbiadimento = quello per notte (colonna 6), usato dal punto 4.
2. da_precedente (1.14.0 -> 1.15.0): C e C0 moltiplicate per il fattore (riga per riga sulle colonne), F ricalcolata,
   M e rodaggio_da copiati, stato e meta identici.
3. _aggiungi: gli archi nuovi nascono con C = firma x fattore (C0 uguale); costruisci idem.
4. riconsolida: momento x fattore prima del confronto (sorpresa e passo).
5. Dose (Lux.forza, riflesso): nessun cambio di codice, S_e scende da sola.

## Task
- [x] T0 backup
- [x] T1 test (test_tabella_115, test_riconsolida, test_forza adattati), codice, revisione del codice (agente: stabilita' iniziale sulla firma grezza in riconsolida, aggiorna_c_0911.py bloccato dalla 1.15.0), conservazione (test di prima verdi)
- [x] T2 produzione 11/11 ~14:30: a coda di firma vuota, VERSIONE 1.15.0 + PRECEDENTE 1.14.0 + da-precedente + riavvii nello stesso comando; /salute 1.15.0; /forza di gerdpjaerqfssyvk (disprezzo) 1.572 -> 0.943 (x 0.6)

## Rollback
VERSIONE e PRECEDENTE di prima in lux_engrammi.py (git), riavvio lux-engrammi e firma-subito; lux-1.15.0/ resta li'.

## Stato
11/11 ~14:30: IN PRODUZIONE. Da sapere: lux3d colora gli engrammi con argmax di F, che col fattore pende verso le
emozioni ad alto impatto; in M la sorpresa delle righe 1.14.0 e' sulla firma grezza, dalla 1.15.0 sulla scala x fattore
(tenerne conto per D1 del piano 1.14).
