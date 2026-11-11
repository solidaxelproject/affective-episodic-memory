# Piano 1.14.0: riconsolidamento (fase 2, punto 6 di PIANO-LUX-FASI-v1.12.md)

Aperto l'11/11/2026 (CC Opus 5.5), su ordine dell'utente "prosegui col riconsolidamento". Backup completo prima:
engrammi/backup/4 (11/11 ~01:40).

## Obiettivo
Quando un ricordo viene richiamato, la sua carica emotiva si sposta verso l'emozione che l'agente prova in quel momento,
come nel riconsolidamento umano (Nader 2000: un ricordo richiamato torna modificabile e si risalva). Lo spostamento
c'e' solo se la differenza e' grande (sorpresa, errore di previsione: Sevenster 2013). La carica nuova cambia la dose
del vettore ai richiami dopo (punto 7, S_e) e la forza dell'arco (punto 8).

## Testo del punto 6 (l'utente 17/10, PIANO-LUX-FASI)
`carica <- carica + alfa x (momento - carica)`, alfa = 0.2 / (1 + log(S/S0)), tetto per notte. Parte SOLO se la
differenza supera una soglia di sorpresa, da tarare nel rodaggio. Finestra: la prima risposta dopo il richiamo (~6 ore).
Tetto: la carica non supera mai 0.02 sotto la soglia di eco; avvicinandosi al tetto i passi si riducono. Rinforzo
emotivo a ogni richiamo TOLTO. Punto 8: dalla carica nuova si ricalcola S0, S si scala nella stessa proporzione.
Punto 9: rodaggio di 30 giorni (10% / 30% / 70% / 100%), data di partenza in lux.npz, copia dello stato prima di ogni notte.

## Fatti verificati (11/11, CC)
- Carica = `C` di lux.npz: una riga di 51 valori (ordine EMOZIONI) per arco, oggi uguale per tutti gli archi di un
  ricordo (la firma del ricordo, z da circa -4.5 a 3.9). `C0` (carica alla nascita, D3 del 09/11) NON esiste ancora:
  Lux.forza usa w0 = w.
- La firma del momento c'e' gia', senza GPU di notte: firma_subito firma subito ogni risposta finale dell'agente e la scrive
  in `workspace/memoria/giornata-firma.jsonl` (`firma` a 44 assi, chiavi inglesi), registro tenuto 3 giorni. Il
  diario del riflesso ha ogni consegna con `ts` e `nid`.
- Misura su 25 coppie vere (consegna -> prima risposta firmata dell'agente entro 6 ore, 10-11/11): differenza RMS sugli
  assi 0.89 / 1.02 / 1.38 / 1.95 / 2.07 (percentili 10/25/50/75/90); sull'asse piu' carico del ricordo
  momento - carica = -3.21 / -2.91 / -2.43 / -1.68 / -1.15: la risposta dell'agente porta SEMPRE molto meno l'emozione del
  ricordo (finora il vettore era quello vecchio o nessuno). Con alfa 0.2 ogni richiamo abbasserebbe la dominante di
  circa 0.5 z: il riconsolidamento, cosi', fa sbiadire i ricordi richiamati.
- La "soglia di eco" (dose a cui l'emozione esce come parola) non e' misurata da nessuna parte (grep di DOSI-EMOZIONI.md
  e della relazione). La carica e' in z della firma, la dose in % della norma: unita' diverse. La dose e' gia' limitata
  dalla formula del punto 7 (mai sopra Dmax).

## Decisioni aperte (dell'utente, una alla volta)
- D1. Soglia di sorpresa e misura della differenza (RMS sugli assi o solo la dominante): RINVIATA (D3) a dopo qualche
  giorno di consegne col vettore nuovo; nel frattempo riconsolida scrive nel diario quanto avrebbe spostato.
- D2. DECISA (l'utente 11/11 ~02:00, opzione 1): nessun tetto sulla carica, solo un freno sul passo per notte. Motivo: la
  formula avvicina la carica al momento senza mai superarlo (il limite e' l'emozione vera dell'agente, firme fino a ~4 z), e
  la dose resta sotto Dmax per costruzione (punto 7). Rischio noto: il circolo del rimuginio (ricordo triste richiamato
  da triste -> piu' carico -> piu' forte, punto 8 -> affiora di piu'); si guarda nel diario del rodaggio.
  Freno: PASSO_MAX = 0.5 z per arco e per notte (valore provvisorio di CC; a effetto zero non agisce).
- D3. DECISA (l'utente 11/11 ~01:50: "prima misura col vettore nuovo"): codice e collaudo adesso (C0, riconsolida,
  rodaggio), ma riconsolida gira a EFFETTO ZERO finche' la soglia di sorpresa (D1) non si fissa su qualche giorno di
  consegne col vettore nuovo nel ragionamento. Domanda di partenza: il dato della misura: oggi il momento e' quasi sempre sotto la carica (l'agente risponde senza l'emozione del
  ricordo), quindi il riconsolidamento abbassa le cariche a ogni richiamo. Va bene cosi', o si aspetta di misurare con il
  vettore nuovo in produzione (11/11 01:30) prima di decidere la soglia?

## Architettura
1. **lux-1.14.0/** costruita alla produzione da `migra_114.py` (copia di lux-1.13.0): lux.npz con in piu'
   - `C0` (= C al momento della migrazione, poi mai toccata; `aggiungi` la scrive uguale a C per gli archi nuovi),
   - `M` (momenti: una riga per consegna riconsolidata: nid, ts della consegna, ts della risposta, RMS, i 51 valori
     del momento; NaN sugli assi assenti) = dato del ricordo nel Lux, e segna fin dove si e' arrivati,
   - `rodaggio_da` (giorno vissuto in cui l'effetto si accende; NaN = effetto zero, D3).
   VERSIONE cambia solo alla produzione. `Lux.forza` usa C0 per w0 (D3 del 09/11). `struttura()` di una cartella
   vecchia senza C0: C0 = C.
2. **riconsolida(oggi)** (funzione del modulo; in produzione la chiama il SERVIZIO con POST /riconsolida, che poi si
   ricarica: il servizio e' a un filo, quindi nessuna sua richiesta salva uno stato vecchio sopra quello nuovo).
   Revisione del piano 11/11 (agente) applicata:
   a. TUTTO sotto lucchetto() e rileggendo dal disco lux.npz, lux-stato.npz e lux-meta.json (un aggiungi di
      firma_subito o una correzione fra la ricarica e la scrittura non si perdono); dentro il lucchetto niente
      salva_stato (stesso processo = stallo): lo stato si scrive diretto; alla fine os.utime(META) cosi' il servizio
      ricarica anche se riconsolida gira da riga di comando;
   b. consegne del diario del riflesso (`memorinvolontaria` + `nid`, e `flusso` dal riflesso nuovo) NON ancora in M
      (insieme delle coppie (ts, nid), non un segnalibro: una consegna saltata si riprende anche dopo una piu' nuova);
   c. risposta = la PRIMA voce dell'agente dello stesso flusso nel registro (giornata-firma.jsonl) dopo la consegna, entro
      6 ore; esclusi i forzati (+lux). Se quella prima voce non ha firma (corto, doppione, errore): la consegna entra in
      M con momento NaN, niente spostamento. Nessuna voce ancora: si riprova la notte dopo;
   d. riga di M sempre; ricordi sconosciuti, corretti (errati) e correzioni (nid >= PRIMO_CORREZIONE, nate con carica
      zero: D4) mai spostati;
   e. effetto (solo con rodaggio_da non NaN e sorpresa >= SOGLIA_SORPRESA, D1): per arco vivo del ricordo, sugli assi
      presenti nel momento, somma della notte di fattore_rodaggio x alfa_arco x (momento - C), alfa_arco =
      0.2 / (1 + max(0, log(S/S0))), poi |somma| <= PASSO_MAX; F ricalcolata (firme_engrammi: gli engrammi sono
      condivisi, la dose di altri ricordi cambia con loro); punto 8 in proporzione:
      S0 *= si(C nuova)/si(C vecchia) e S nello stesso rapporto (si = salienza.stabilita_iniziale con i ranghi del
      ricordo): restano il pavimento delle abitudini e il fattore dei trascinati;
   f. sorpresa = RMS di (momento - C) sugli assi del momento, sulla prima riga di C del ricordo (D1 potra' cambiarla).
   Fattore del rodaggio: giorni da rodaggio_da < 10: 0.1, < 20: 0.3, < 30: 0.7, poi 1.
## Dipendenze controllate (da completare in T2)
- lux_engrammi.py: _apri, struttura, aggiungi (np.savez: chiavi nuove), forza, salva_stato.
- servizio_lux.py: rotta nuova; lux() ricarica quando la notturna riscrive META (aggiungi): riconsolida va DOPO.
- lettori di lux.npz: lux3d.py, lux3d-gif.py, misura_engrammi.py, vettori_l29.py, verifica_post_versioning.py, test.
- NOTA 11/11 (1.15.0): le righe di M scritte dalla 1.14.0 hanno la sorpresa sulla firma grezza, quelle dalla 1.15.0
  su momento x fattore contro la carica x fattore: per tarare D1 si ricalcola la sorpresa dai 51 valori grezzi di M.
- NOTA 11/11 (1.18.0, revisione): con lo sbiadimento la sorpresa (momento contro carica attuale) cresce da sola e il
  riconsolidamento riporterebbe su le cariche sbiadite. Da decidere con D1: confronto con la carica attuale o con C0.
- D4. Correzioni (nid >= 1.000.000): nascono con carica zero; riconsolidarle darebbe loro un'emozione per la prima
  volta. Default di CC: escluse come gli errati. Da chiedere all'utente prima di accendere l'effetto (con D1).

## Task
- [x] T0 backup completo (engrammi/backup/4)
- [x] T1 decisioni D2, D3 (11/11); D1 rinviata (D3)
- [x] T2 revisione del piano (agente, 11/11): 2 gravi (corsa con aggiungi, stallo del lucchetto), 5 medi, 4 bassi: tutti nel piano
- [x] T3 test (test_riconsolida, test_forza), codice, revisione del codice (agente: 7 punti, applicati 1, 3, 4, 7; 2 risolto dalla produzione + guardia C0 nella notturna; 5 e 6 documentati), conservazione (test di prima uguali; test_lux_113 rosso gia' prima, ora confronta lux-1.12.0 esplicita)
- [x] T4 produzione 11/11 11:00: backup/1, VERSIONE 1.14.0, da-precedente, riavvio lux-engrammi (/salute 1.14.0), firma-subito, riflesso; chat.kv rimessa (23720 token)

## Messa in produzione (T4, CC)
1. backup completo (backup-ruota.sh);
2. lux_engrammi.py: VERSIONE = "1.14.0" (PRECEDENTE e' gia' lux-1.13.0), poi
   `cd engrammi && /data/venv-spacy/bin/python lux_engrammi.py da-precedente` (sotto lucchetto della cartella nuova;
   prima fermare nulla: firma_subito scrive nella 1.13.0 fino al cambio, quindi la migrazione va fatta a coda di
   firma-subito vuota e subito prima dei riavvii);
3. riavvio di lux-engrammi, firma-subito, riflesso (CC); dopo il riflesso controllare i token nello slot e rimettere
   chat.kv se serve; /salute deve dire 1.14.0;
4. la notturna di mezzanotte fa la copia e /riconsolida (effetto zero): il giorno dopo M cresce.
Rollback: VERSIONE = "1.13.0" e PRECEDENTE = lux-1.12.0 in lux_engrammi.py (git), notte-memoria.sh.bak-pre-114,
riflesso.py da git, riavvii; lux-1.14.0/ resta li'.

## Stato
11/11 11:05: IN PRODUZIONE a effetto zero. Prima riconsolida: notturna di mezzanotte (copia in lux-1.14.0/notti/, poi
POST /riconsolida, riga nel log della notturna). Prossimo: dopo qualche giorno di consegne col vettore nuovo, misura
di M per D1 (soglia e misura della sorpresa), poi D4 e accensione (rodaggio_da). Limiti noti: riconsolida da riga di
comando solo a servizio spento; il servizio aspetta il lucchetto se un aggiungi di firma_subito e' in corso.
11/11 ~02:30: T3 scritto, test verdi (test_riconsolida sulla copia, test_forza, riflesso, firma_subito, engrammi, qlux,
b7). Prova del servizio su una copia (:8133) coi dati veri: 25 momenti in M, C, F e stato identici. Revisione del codice
in corso (agente).
11/11 ~02:00: D2 e D3 decise, D1 rinviata; architettura scritta; T2 fatto; prossimo T3.
