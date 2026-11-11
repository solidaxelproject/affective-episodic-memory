# Piano 1.17.0: contatori degli engrammi e ultimo richiamo (fase 2, punto 3 di PIANO-LUX-FASI-v1.12.md)

Aperto l'11/11/2026 (CC Opus 5.5), ordine dell'utente "passiamo al punto successivo". Backup completo prima (backup/1).

## Obiettivo
Per lo sbiadimento (punto 4) serve sapere se un tema e' ancora aperto: un engramma che riappare spesso nei messaggi
tiene vivo il suo tema (Klinger; Martin e Tesser; Masicampo e Baumeister 2011). Servono per engramma il giorno di
nascita, l'ultimo giorno in cui e' riapparso e quante volte; per ricordo l'ultimo richiamo.

## Testo del punto 3 (17/10)
Per engramma `nato_U`, `acceso_U` (ultimo giorno in cui e' riapparso nei messaggi, soglia SOGLIA_SEM 0.8),
`accensioni`. Per ricordo l'ultimo richiamo `[g/m/aaaa|h:mm]`, scritto alla consegna. Giorni = giorni VISSUTI
(orologio della notturna, lux.orologio).

## Scelte di CC (nessuna cambia il comportamento di oggi: i contatori servono solo al punto 4)
1. "Riapparso" = la regola di accendi: stessa chiave o coseno bge-m3 >= SOGLIA_SEM con un engramma di un messaggio
   del giorno (l'utente e l'agente, registro giornata-firma.jsonl, anche i messaggi che non diventano ricordi). Una sola
   accensione per engramma e per giorno.
2. Giorno di un messaggio = quello dell'orologio di allora (giorno_di): l'orologio avanza solo a mezzanotte,
   quindi un messaggio prima dell'ultimo avanzamento e' del giorno prima.
3. Valori iniziali dagli archi dei ricordi esistenti: nato = giorno del ricordo piu' vecchio che contiene l'engramma,
   acceso = del piu' recente, accensioni = giorni distinti dopo la nascita. L'orologio vissuto e' partito il 09/11
   (oggi 2 giorni): quasi tutto parte da 0.
4. Ultimo richiamo: ts della consegna, per ricordo, nello stato del servizio (lux-stato.npz, R_nid e R_ts); il formato
   [g/m/aaaa|h:mm] e' solo come si mostra.
5. Dove: E_nato, E_acceso, E_accensioni e riacceso_fino (ts dell'ultimo messaggio contato) in lux.npz; riaccendi nel
   servizio (POST /riaccendi), dalla notturna prima di /riconsolida.

## Task
- [x] T0 backup
- [x] T1 test (test_contatori_117; test_carica_116 e test_riconsolida adattati), codice, revisione del codice (agente: giorno_di senza conto all'indietro fuori dai valori iniziali, una notturna fallita non apre un giorno; riaccendi taglia ed embed fuori dal lucchetto), conservazione (test di prima verdi)
- [x] T2 produzione 11/11: VERSIONE 1.17.0 + PRECEDENTE 1.16.0 + da-precedente + riavvii; /salute 1.17.0; 230 engrammi gia' accesi piu' di una volta

## Rollback
VERSIONE e PRECEDENTE di prima (git), notte-memoria.sh da git, riavvio lux-engrammi e firma-subito.

## Stato
11/11: IN PRODUZIONE. La prima riaccendi gira nella notturna (riga "riaccendi:" nel log). Limite noto: se riaccendi
fallisce, i messaggi di quel giorno possono uscire dal registro prima della notte dopo (potatura di firma_subito).
