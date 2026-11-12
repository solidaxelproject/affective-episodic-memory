# Fase 2, step c: archi fra ricordi, firme che si avvicinano, coda dei ricordi richiamati (Lux 1.21.0)

Piano autosufficiente (regge a una compattazione). Iter di upgrade, 12/11/2026, CC Opus 5.5.

## Obiettivo (decisioni dell'utente dell'11/11, PIANO-LUX-FASI-v1.12.md, "Fase 2, insieme allo step qui sopra")

Base: nella memoria umana ricordi riattivati spesso insieme si integrano (Schlichting e Preston 2015) e l'emozione
dell'uno passa all'altro (condizionamento valutativo, De Houwer 2001; riconsolidamento, Nader 2000).
1. Archi fra ricordi nel Lux, accanto agli archi fra engrammi dentro un ricordo.
2. Firme che si avvicinano: quando nasce o si rinforza un arco fra due ricordi con firme diverse, il freno che trattiene
   la firma si riduce e la firma di ENTRAMBI cambia: a ogni richiamo insieme le due firme si avvicinano. Si aggancia al
   riconsolidamento della 1.14.
3. Coda: i ricordi con emozioni diverse che il Lux seleziona non si consegnano insieme; vanno in coda, in ordine di
   recupero, uno per consegna. Un ricordo che entra dopo, se ha una firma piu' intensa o piu' negativa, passa avanti.
4. Dopo 30 minuti i ricordi in coda e non ancora dati escono dalla coda e tornano richiamabili nella CW.
Nascita dell'arco: due ricordi scelti dal Lux nella STESSA SELEZIONE, anche se uno va in coda.

## Decisioni

- D1 DECISA (l'utente 12/11 sera): "sì, l'arco li fa tornare in mente insieme". Quando affiora uno dei due ricordi
  (consegna), l'altro riceve una spinta nella predisposizione della 1.12 (`predisponi`, emivita 6 ore) proporzionale
  alla forza dell'arco, e affiora piu' facilmente nei messaggi dopo.
- D2 DECISA (l'utente 12/11 sera): l'avvicinamento delle firme parte SUBITO, con il rodaggio di 30 giorni (punto 9:
  10%, 30%, 70%, poi pieno), senza aspettare la soglia di sorpresa del riconsolidamento (che resta a effetto zero).
- D5 DECISA (l'utente 12/11 sera): "sì, la dominante si ricalcola dalla carica". Ogni notte, dopo avvicina, la dominante
  di ogni ricordo toccato si ricalcola dalla carica di adesso (firma equivalente = media di C/(fattore x W) sui suoi
  archi, poi memoria.dominante come alla nascita) e si scrive in ricordi[nid]["dominante"]: vettore, step b e coda la
  seguono. Base: condizionamento valutativo (De Houwer 2001).
- D3 (meccanismo letto da CC dalla decisione dell'11/11): il "freno che trattiene la firma" e' quello del
  riconsolidamento, passo = ALFA / (1 + log(S/S0)) con tetto PASSO_MAX per notte. Per i ricordi legati il freno si
  riduce sul termine della stabilita': ALFA / (1 + FRENO_LEGATI x log(S/S0)). Bersaglio = il profilo dell'altro ricordo.
- D4 DECISA (l'utente 12/11 sera): "prima la negatività, poi l'intensità". Classe della dominante: negativa > neutra >
  positiva (POSITIVE e NEUTRE del Lux); a parita' di classe, piu' intensa = valore della dominante nella firma
  equivalente (D5). Il nuovo passa avanti a un ricordo gia' in coda solo se lo batte cosi'; i ricordi della stessa
  selezione restano nell'ordine del richiamo. Dominante None o firma assente: classe neutra, intensita' 0.

Numeri PROVVISORI di CC (da rivedere sui dati del rodaggio, registrati qui):
- PESO_ARCO_RICORDI = 1.0: spinta della predisposizione per arco fra ricordi = forza dell'arco (0-1), come un engramma
  condiviso (1.12.0).
- FRENO_LEGATI = 0.5: il termine della stabilita' pesa la meta'.
- ALFA_LEGATI = ALFA = 0.2, PASSO_MAX invariato (0.5).
- CODA_DURATA = 1800 s (11/11: 30 minuti, non provvisorio).
- Arco fra ricordi: nasce con S = LUX.S_BASE; cresce con LUX.cresci a ogni co-selezione (come rinforza); forza =
  LUX.curva(oggi - U, S), che scende col tempo vissuto (sbiadimento FSRS, nessun parametro nuovo).

## Architettura

### Lux (engrammi/lux_engrammi.py)

1. **Stato degli archi fra ricordi** in `lux-stato.npz` (chiavi nuove, assenti = nessun arco): `RA` (k x 2, a < b,
   radici delle catene), `RA_S`, `RA_U` (giorno vissuto dell'ultima co-selezione), `RA_N` (co-selezioni), `RA_P`
   (co-selezioni non ancora lavorate dalla notturna). In RAM `self.archi_ric = {(a, b): [S, U, N, P]}`.
   `carica_stato` li legge, `salva_stato` li scrive. `_aggiungi` e `riconsolida` riscrivono lo stato con `**dict(s)`:
   le chiavi nuove restano.
2. **`_coseleziona(radici, oggi)`**: per ogni coppia, arco nuovo (S_BASE, U=oggi, N=1, P=1) o rinforzo (S = cresci(S,
   curva(oggi-U, S)), U=oggi, N+1, P+1). Le correzioni stanno nella catena del loro originale (radice).
3. **`predisponi(nids, ora, oggi)`**: in piu', per ogni arco fra un ricordo consegnato x e un altro y non consegnato,
   spinta[y] += PESO_ARCO_RICORDI x forza dell'arco (poi /sqrt(n) come le altre). D1.
4. **`_catene(scelta, via, quanti, stessa=True)`**: con stessa=False la regola dello step b non si applica (serve
   per la selezione).
5. **`in_coda(coda, nuovi, info)`** funzione pura (D4): coda = radici gia' in coda (vecchie), nuovi in ordine di
   richiamo; ogni nuovo parte dal fondo e passa avanti ai VECCHI che batte; non passa i nuovi.
6. **`consegna(..., coda=None)`**: con `coda=None` (qlux, test, CLI) identica allo step b. Con una lista di codici:
   a. via = esclusi + codici in coda (non si riselezionano);
   b. selezione = `_catene(scelta, via, quanti, stessa=False)`;
   c. coda = `in_coda(coda valida, radici della selezione)`; testa = coda[0];
   d. gruppo = testa + quelli della coda con la stessa dominante + le catene piu' in basso nel richiamo con la stessa
      dominante (regola dello step b), fino a quanti;
   e. co-selezione: tutte le coppie fra le radici della selezione piu' quelle del gruppo prese dal richiamo di adesso
      (una testa che arriva dalla coda non si lega ai ricordi nuovi: non e' la stessa selezione);
   f. consegnati = catene del gruppo, tolti dalla coda; rinforzo, ultimo richiamo, predisposizione come oggi;
   g. `coda[:] = codici della coda nuova` (la lista del chiamante si aggiorna).
7. **`avvicina(oggi)`** (notturna, POST /avvicina, dopo /riconsolida): per ogni arco con P > 0 fra due ricordi
   veri (non correzioni, non errati) con dominanti diverse: profilo di ognuno = media di C/W sui suoi archi con C0;
   per gli archi j del ricordo a: x = rodaggio x ALFA / (1 + FRENO_LEGATI x log(S_j/S0_j)) x forza dell'arco;
   q = 1 - (1 - x)^P; p/W = q x (profilo di b - C_j/W_j), tetto PASSO_MAX; stesso per b verso a, coi profili di prima.
   F ricalcolata, S0 e S scalate come nel riconsolidamento: il blocco che applica i passi si estrae da `riconsolida`
   in una funzione comune `_applica_passi`. P si azzera per tutti gli archi lavorati. Rodaggio da `avvicina_da` in
   lux.npz (giorno vissuto della produzione); senza `avvicina_da`: niente.
8. **Versione 1.21.0**: `da_precedente` copia la 1.20.0 (lux.npz con `avvicina_da` = giorno vissuto di oggi,
   lux-meta.json, lux-stato.npz, lux-l29.npz); PRECEDENTE = lux-1.20.0. La migrazione da memoria.db della 1.20.0
   esce dal codice (resta nella storia di git, commit 1.20.0); MEMORIA_DB non serve piu'. test_lux_120.py va in
   archivio (prova la migrazione 1.19 -> 1.20, fatta).

### Servizio (engrammi/servizio_lux.py)
- /consegna: facoltativo `"coda": [codici]`; con la coda la risposta ha `"coda"` (codici, in ordine) anche quando non
  esce nessun ricordo.
- POST /avvicina {} -> {"archi", "spostati", "rodaggio"}.

### Riflesso (riflesso_memoria.py)
- La coda sta nella voce della conversazione in consegne-memorinvolontaria.json: `"coda": [[codice, ts_recupero], ...]`.
- A ogni lettura nuova a consenso attivo: coda senza i ricordi oltre CODA_DURATA, codici al Lux; la risposta da'
  la coda nuova: i codici gia' presenti tengono il loro ts, i nuovi prendono l'ora di adesso. Salvata con la voce.
- A consenso spento: niente coda (`coda` non mandata: step b).

### Notturna (notte-memoria.sh)
- Dopo /riconsolida: `curl -X POST :8132/avvicina`, riga "avvicina: ..." nel log, fallimento non critico.

## Dipendenze controllate

| Chi | Cosa | Effetto |
|---|---|---|
| qlux (riflesso_memoria._lux_cerca) | /consegna senza coda | invariato |
| test_*.py che chiamano consegna | senza coda | invariati (step b) |
| riconsolida, sbiadisci, _aggiungi | riscrivono lux-stato.npz con dict(s) | le chiavi RA_* restano |
| servizio lux(): ricarica al cambio di META | archi_ric riletti da carica_stato | ok |
| barra-prefill, diario, riconsolida | consegne con 1-4 codici | invariato (step b) |
| notte-memoria.sh: LD = X.DIR | cartella lux-1.21.0 | copia della notte nella cartella nuova |
| avvicina | S0 e S degli archi toccati scalati | oblio e facilita' del richiamo di quei ricordi |
| avvicina (D5) | ricordi[nid]["dominante"] in lux-meta.json | vettore, step b, coda, barra-prefill seguono |

## Correzioni dalla revisione del piano (12/11 sera, verificate nel codice)

1. `_aggiungi` tiene in lux.npz solo le chiavi della lista `resto` (lux_engrammi.py:478): "avvicina_da" va aggiunta,
   con un test aggiungi-poi-avvicina.
2. Rollback riscritto (sopra).
3. Coda valida = coda senza i codici in esclusi (qlux puo' averli gia' dati); test.
4. Con D5 la dominante cambia: `forza(nid, e)` per un'emozione diversa dalla dominante della nascita
   (`dominante_nascita` in ricordi[nid], scritta la prima volta che la dominante cambia) usa la carica di adesso:
   S_e = sum(w_i x F_i,e) / sum(w_i), senza riferimento alla nascita (alla nascita quell'emozione poteva essere zero);
   per la dominante della nascita la formula resta quella della 1.18.0. La via emotiva resta sui profili C0 (1.19.0).
   avvicina scala S0 e S (oblio e facilita' del richiamo): nella tabella delle dipendenze.
5. D4 decisa dall'utente (sopra).
6. Traccia della via emotiva: `traccia["da_coda"]` = i consegnati che arrivano dalla coda di un messaggio prima;
   !verifica emotiva! confronta "scelto" solo quando da_coda e' vuoto.
7. I test che puntano PRECEDENTE a lux-1.18.0 (test_carica_116, test_riconsolida, test_sbiadimento_118,
   test_contatori_117) passano a lux-1.20.0: la da_precedente nuova copia e basta.
8. `salva_stato` scrive anche RA_*; `_coseleziona` prima dei rinforzi (che salvano); /consegna con la coda risponde
   anche senza ricordi ({"coda": [...]}).
9. Riflesso: coda letta con lo stesso ripiego conv/vecchia di `_voci`, salvata dentro tutte[conv].
10. coda=None (qlux, consenso spento): nessun arco. Voluto: a consenso spento il richiamo rinforza ma non lega.
11. `predisponi`: consegnati portati alla radice della catena prima di cercare gli archi; oggi = LUX.orologio() se None.
12. log(S/S0) con max(0, ...) come in riconsolida.

## Task

- [x] T0. Worktree /data/memoria-episodica-affettiva-archi-coda, ramo archi-coda; copiare i file fuori da git
      (engrammi/via-emotiva/traduzione-l29.npz, engrammi/misura-t1a-stati.npz).
- [x] T1. Fotografie prima: consegna senza coda sui 42 indizi (foto dello step b), foto_riflesso.
- [x] T2. Test che falliscono: engrammi/test_archi_coda_121.py (in_coda, consegna con coda, archi e loro
      salvataggio, predisposizione dall'arco, avvicina su una copia del Lux, da_precedente); test_riflesso.py (coda
      salvata, scadenza 30 min, codici mandati).
- [x] T3. Codice del Lux e del servizio. T4. Riflesso. T5. Notturna.
- [x] T6. Test verdi, fotografie (consegna senza coda identica; foto_riflesso: cambia solo la coda nelle richieste),
      test esistenti con la stessa uscita, ruff, controlla_bersagli.
- [x] T7. Revisione del codice, deslop, ponytail.
- [x] T8. Produzione: backup completo; servizi lux-engrammi, firma-subito fermi (lux3d legge); merge; VERSIONE
      1.21.0; `lux_engrammi.py da-precedente`; riavvio lux-engrammi, firma-subito, lux3d, riflesso; controllo dello
      slot; /salute = 1.21.0; commit locale.
- [x] T9. Handoff, piano delle fasi, memoria.

## Rollback (revisione 12/11, punto 2)

Il codice 1.20.0 sui DATI 1.21.0 (firma-subito crea i ricordi nuovi solo nella 1.21.0: tornare ai dati vecchi li
perderebbe e ridarebbe gli stessi nid a ricordi diversi). Servizi lux-engrammi e firma-subito fermi; sotto i lucchetti
di tutte e due le cartelle, copia di lux.npz, lux-meta.json, lux-stato.npz della 1.21.0 dentro lux-1.20.0 (prima una
copia di lux-1.20.0 in lux-1.20.0/prima-del-rollback/); git revert del merge; riavvio dei servizi. La 1.20.0 ignora
RA_* e avvicina_da; le dominanti ricalcolate restano. Si perde solo l'effetto degli archi fra ricordi.

## Stato

12/11 sera: D1, D2, D4, D5 decise; piano scritto e rivisto (correzioni 1-12). Codice fatto nel ramo archi-coda.
Revisione del codice: corretti da_coda nel diario della via emotiva (e verifica_via_emotiva salta quei casi),
dominante_nascita controllata con "in" (anche None), ricalcola-firme-se toglie dominante_nascita, _rango neutro senza
firma; RA_P si azzera su tutti gli archi (voluto, scritto in avvicina); test resi piu' severi (coda non vuota con
esclusi, formula della forza calcolata a mano, arco a dominante uguale che non sposta niente).
Prove: test_archi_coda_121 verde (sulla copia: un ricordo, 416, ha cambiato dominante gia' al primo giorno a rodaggio
10%: aveva due emozioni quasi alla pari); consegna senza coda identica allo step b sui 42 indizi; foto_riflesso:
cambia solo "coda": [] nelle richieste e nella voce; batteria del Lux e del riflesso con la stessa uscita di master
(lux_113 rosso uguale, 18 fallimenti, gia' prima). Con la carica di oggi nessuna delle 655 dominanti cambierebbe.

12/11 18:21: IN PRODUZIONE (merge 9314abc). Backup completo in engrammi/backup/2; firma-subito e lux-engrammi fermi
per da-precedente; /salute 1.21.0 con 655 ricordi; riflesso, lux3d, notturna-web riavviati; slot con la chat (23.720
token), nessun cron dopo le 17:47. Da vedere: prima coda e primi archi nella chat, prima riga "avvicina:" a mezzanotte.
