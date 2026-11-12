# Fase 2, step b: ricordi con la stessa firma consegnati insieme

Piano autosufficiente (regge a una compattazione). Iter di upgrade, 12/11/2026, CC Opus 5.5.

## Obiettivo

Decisione dell'utente (09/11 e 11/11, PIANO-LUX-FASI-v1.12.md punto 7 "Stessa emozione, piu' ricordi" e sezione
"Fase 2, dopo la divisione del riflesso"): se il Lux richiama piu' ricordi con la STESSA emozione dominante, si
consegnano insieme, al massimo 4. Il vettore e' uno solo, alla dose del ricordo in cui l'emozione e' piu' forte (il
massimo delle D_e, niente media ne' somma). I ricordi con firme diverse non si consegnano insieme.

Oggi il riflesso chiede un ricordo per messaggio (`quanti: 1`, riflesso_memoria.py:121, dal 09/11).

## Architettura

1. **Il filtro sta nel Lux, in `_catene`** (lux_engrammi.py), non nel riflesso: `consegna` rinforza, segna l'ultimo
   richiamo e predispone TUTTI i ricordi scelti. Un ricordo filtrato dopo, nel riflesso, sarebbe rinforzato senza
   arrivare all'agente.
2. Regola in `_catene`: la prima catena (il ricordo col punteggio piu' alto, piu' le sue correzioni) fissa la
   dominante; le catene dopo entrano solo se la dominante del loro ricordo originale (`catena(nid)[0]`) e' la stessa,
   fino a `quanti`. Un originale senza dominante (None) non fa gruppo con nessuno: esce da solo.
   Vale per ogni chiamata (11/11: "i ricordi con firme diverse non si iniettano insieme"); con `quanti=1`
   (qlux, test) il risultato e' identico a oggi.
3. Gli scartati per firma diversa NON si consegnano, NON si rinforzano (S, U e ultimo richiamo R invariati) e non
   entrano negli esclusi: restano richiamabili al messaggio dopo. Come oggi, ricevono la predisposizione dei vicini
   dai ricordi consegnati (predisponi), mai una propria. La coda dei ricordi con firma diversa e' lo step c.
4. La traccia della via emotiva ("senza") usa `_catene`: segue la stessa regola, quindi resta confrontabile con
   "scelti".
5. Riflesso (riflesso_memoria.py, `_lux_consegna`): `quanti` da 1 a `CONSEGNA_MAX` = 4. Il vettore e' gia' uno solo
   col massimo di f (riga ~305: `max(dosi, key=lambda x: x[2])`): non cambia. Il diario scrive gia' tutti i codici e
   i nid.
6. qlux resta a `quanti: 1` (ricerca volontaria, un ricordo per volta, l'utente 09/11).
7. VERSIONE del Lux resta 1.20.0: nessun dato cambia (stesso caso di B6, "dati gia' scritti invariati: VERSIONE
   resta"). Commento nello stile del file con data e decisione.
8. Umore (revisione 12/11): con piu' ricordi l'umore riceve un'impronta per ricordo (barra-prefill, omeostato.imprimi
   per ogni codice; la taratura della via emotiva le simula dal diario). Con 4 ricordi della stessa dominante la spinta
   verso quell'emozione e' circa 1 - 0.75^4 = 68% invece di 25%: e' la regola dell'utente del 10/11 "ogni ricordo
   consegnato imprime lo stato", nessun codice da toccare.
9. "Stessa emozione" = la stessa voce fra i 51 assi (la dominante esatta): e' anche il vettore, uno per emozione.
   Serenita', gioia ed estasi non fanno gruppo fra loro.

## Dipendenze controllate (12/11)

| Chi | Cosa legge | Con piu' ricordi |
|---|---|---|
| servizio_lux.py /consegna | `quanti` (default CONSEGNA_MAX), risposta_tool numerata | gia' pronto (1.10.0) |
| riflesso_memoria.memoria | `r["codici"]`, `r["ricordi"]`, vettore = max f | gia' pronto |
| barra-prefill (~/.local/bin) | `memorinvolontaria` = lista di codici, notice per ognuno | gia' pronto |
| lux_engrammi.riconsolida (notturna) | diario `nid` come lista | gia' pronto (riga 538) |
| via_emotiva.py (taratura, umore) | `v["nid"]` come lista | gia' pronto (riga 219) |
| consegne-memorinvolontaria.json | voce con `codici` lista, `_turni_tool` usa il primo per l'id | gia' pronto |
| test_qlux_lux.py:44 | `<= CONSEGNA_MAX` posti | resta vero |
| test_archi_vivi, test_predisposizione | consegna col default | da rilanciare: possono cambiare i ricordi scelti dopo il primo |

## Testi che il modello vede

Nessun testo nuovo. La risposta del tool con piu' ricordi (`1°`, `2°`...) e' quella della 1.10.0, gia' approvata da
l'utente il 16/10.

## Decisioni

- Fuori da questo step: la regola "due emozioni quasi alla pari" (piu' rilevante > intensa > negativa, l'utente 09/11)
  sceglie fra ricordi di firma diversa, quindi appartiene alla coda dello step c.

## Task

- [x] T0. Worktree `/data/memoria-episodica-affettiva-stessa-firma`, ramo `stessa-firma`. Togliere il worktree vecchio
      `/data/memoria-episodica-affettiva-divisione` (ramo gia' unito in 617890c).
- [x] T1. Fotografia prima: `consegna` (quanti=1 e quanti=4) su ~50 indizi veri, copia del Lux, `salva_stato` spento,
      giorno e ora fissi; uscita dei test esistenti del Lux e del riflesso.
- [x] T2. Test che fallisce `engrammi/test_stessa_firma.py`: con quanti=4 tutte le catene consegnate hanno la stessa
      dominante della prima; quanti=1 identico alla fotografia; i ricordi scartati non hanno R/U cambiati; con firme
      tutte diverse esce un ricordo solo; correzione: la catena conta la dominante dell'originale.
- [x] T3. `_catene` con la regola; commento 12/11.
- [x] T4. Riflesso: `quanti` = 4 in `_lux_consegna`, commenti aggiornati (righe 24, 121, 234).
- [x] T5. Test verdi; fotografia (stato del Lux rimesso prima di ogni indizio): quanti=1 identica cifra per cifra;
      quanti=4 = le prime 4 catene, nell'ordine di richiama, con la dominante della prima (calcolato da richiama, non
      dalla fotografia vecchia, perche' entrano ricordi che prima stavano oltre il quarto posto); test esistenti con la stessa uscita; foto_riflesso (dentro `unshare -rn`) e
      test_divisione_riflesso; ruff; controlla_bersagli prima dei test che sostituiscono funzioni del riflesso.
- [x] T6. Revisione del codice (agente), deslop, ponytail.
- [x] T7. Produzione: backup completo (backup-ruota.sh), merge in master, riavvio `lux-engrammi` e del riflesso,
      controllo dello slot (se l'ultimo passato e' un cron: POST /slots/0?action=restore {"filename":"chat.kv"}),
      `/salute` del Lux, commit locale.
- [x] T8. Handoff, piano delle fasi, memoria.

## Prove dopo la produzione

- Al primo messaggio dell'utente con un richiamo: nel diario del riflesso `memorinvolontaria` con 1-4 codici, tutti con
  la stessa dominante (controllo con /ricordo), e un solo `vettore`.

## Rollback

`git revert` del merge in /data/memoria-episodica-affettiva, riavvio di lux-engrammi e del riflesso. Nessun dato da riportare
indietro (i rinforzi presi restano, come per ogni consegna).

## Stato

12/11 17:47: IN PRODUZIONE (merge 1209517, ramo 8b842cc). Revisione del piano: nessun danno, 3 correzioni al piano
(predisposizione dei vicini, umore, controllo T5 da richiama). Revisione del codice: nessun bug; test del vettore col
vincitore non in testa, `>=` sul tetto, parentesi, due docstring. Fotografia del Lux (42 indizi, stato rimesso a ogni
indizio): quanti=1 e richiama identici; quanti=4: 10 consegne miste su 42 diventano a firma sola. Fotografia del
riflesso: cambia solo "quanti" 1 -> 4 nelle richieste al Lux. Test del Lux e del riflesso con la stessa uscita di
master (lux_113 rosso gia' prima); test_stessa_firma verde. Backup completo in engrammi/backup/1. Dopo i riavvii lo
slot aveva il cron delle 14:17: chat.kv rimessa (23.720 token). Da vedere al prossimo richiamo nella chat.
