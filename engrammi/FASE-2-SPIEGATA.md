# La fase 2 del Lux, spiegata a un ricercatore ML

Documento di fine fase della fase 2 di `PIANO-LUX-FASI-v1.12.md` ("L'emozione che cambia col richiamo"). Scritto il
13/11/2026. I numeri vengono dai piani dei singoli pezzi (sezioni Stato, risultati, prove), dal blocco di stato di
`HANDOFF-CW-20260729.md`, da `git log` di `/data/memoria-episodica-affettiva` e dal log della notturna del 13/11
(`/tmp/notte-memoria.log`). Dove un numero manca, il testo lo dice.

## 1. Obiettivo

l'agente è un agente (Hermes) che gira su Occamy, un Qwen 35B A3B ibrido, dentro luxifer.cpp. La sua memoria episodica è il
Lux degli engrammi: ogni ricordo è un grafo di engrammi (pezzi di testo) legati da archi; ogni arco ha una forza che
segue una curva dell'oblio (FSRS) e una carica emotiva su 51 emozioni. Quando un ricordo affiora, il riflesso (il
proxy davanti al modello) lo consegna all'agente e inietta un vettore di steering dell'emozione dominante, solo durante il
ragionamento.

Prima della fase 2 la carica emotiva di un ricordo era fissa: la firma letta alla nascita, uguale su tutti gli archi.
La fase voleva una carica che vive:

1. diversa per emozione alla nascita e diversa fra elementi centrali e di contorno;
2. che sbiadisce di notte, ognuna con la sua velocità;
3. che si sposta verso l'emozione del momento quando il ricordo viene richiamato (riconsolidamento);
4. che, insieme all'umore del modello letto in produzione, aiuta a scegliere quale ricordo affiora (via emotiva).

L'11/11 l'utente ha aggiunto alla fase cinque passi di struttura:

5. `memoria.db` superfluo: tutti i dati dei ricordi nel Lux;
6. il riflesso diviso in moduli;
7. ricordi con la stessa emozione dominante consegnati insieme;
8. archi fra ricordi e coda dei ricordi richiamati con emozione diversa;
9. MEMORY.md e USER.md dell'agente divisi in A e B, per uno switch di conversazione con meno prefill.

## 2. Ispirazione dalla mente umana

| Meccanismo nel Lux | Fenomeno umano | Studi citati nei piani |
|---|---|---|
| fattore di carica per emozione alla nascita | le emozioni ad alta attivazione fissano di più il ricordo | Kensinger 2009, McGaugh 2004 |
| carica più alta sugli archi centrali | l'emozione si concentra sugli elementi centrali, il contorno sbiadisce prima | Kensinger 2009; Burke, Heuer e Reisberg 1992; Mather 2007 |
| radicamento S/S0 e prontezza R separati | forza di immagazzinamento e forza di recupero | Bjork e Bjork 1992 |
| sbiadimento per emozione | Fading Affect Bias | Walker 1997, 2003; Ritchie 2015 |
| freno dello sbiadimento | rimuginio, tema aperto, umore, importanza | Verduyn 2009/2011; Klinger; Martin e Tesser; Masicampo e Baumeister 2011; Foerster, Liberman e Higgins 2005; Wrosch; Walker, Skowronski e Gibbons 2003 |
| riconsolidamento | un ricordo richiamato torna modificabile per alcune ore | Nader 2000 |
| soglia di sorpresa | il riconsolidamento parte con un errore di previsione | Sevenster 2013 |
| via emotiva del richiamo | memoria congruente con l'umore, effetto moderato | Bower 1981; Matt, Vazquez e Campbell 1992 |
| peso maggiore senza indizi esterni e con stato intenso | richiamo libero, mente che vaga; intensità | Eich 1995; Ucros 1989 |
| riparazione dell'umore | dopo un umore negativo prolungato si cercano ricordi positivi | Josephson, Singer e Salovey 1996; Rusting e DeHart 2000 |
| inerzia dell'umore | l'emozione già accesa tende a restare | Kuppens 2010 |
| archi fra ricordi e firme che si avvicinano | ricordi riattivati insieme si integrano; l'emozione passa da uno all'altro | Schlichting e Preston 2015; De Houwer 2001; Nader 2000 |

## 3. Setup

- Lux degli engrammi: `engrammi/lux_engrammi.py`, servizio HTTP `servizio_lux.py` (:8132). Dati in
  `lux-<versione>/`: `lux.npz` (archi, cariche `C`, `C0`, `F`, tabelle), `lux-stato.npz` (S, S0, U, ultimo richiamo,
  archi fra ricordi), `lux-meta.json` (ricordi). 655 ricordi all'inizio della fase 2 (11/11), 656 nella notte del 13/11.
- Firma emotiva: 44 assi (24 della ruota di Plutchik più 20 diadi pure, dal 09/11), su 51 emozioni del Lux.
- Riflesso: proxy :8091 davanti a llama-35b (:8090).
- Notturna: a mezzanotte, nell'ordine `riaccendi`, `sbiadisci`, `riconsolida`, `avvicina`.
- Giorni vissuti: orologio della notturna, partito il 09/11 (giorno 3 il 13/11).
- Rodaggio (punto 9 del piano): ogni effetto nuovo parte al 10% per 10 giorni vissuti, poi 30%, 70%, 100%.
- Ogni pezzo è passato dall'iter di upgrade: backup completo, test scritti prima del codice, fotografia del
  comportamento prima e dopo, revisione del piano e del codice con un agente separato, produzione, commit locale.

## 4. I pezzi in produzione

| Pezzo | Versione | In produzione | Commit |
|---|---|---|---|
| riconsolidamento (a effetto zero) | Lux 1.14.0 | 11/11 11:00 | 3fbc939 (11/11 14:13, insieme alla 1.15.0) |
| tabella delle emozioni | Lux 1.15.0 | 11/11 ~14:30 | 3fbc939 |
| carica per arco | Lux 1.16.0 | 11/11, ora non scritta | 3061109 (11/11 14:42) |
| contatori degli engrammi | Lux 1.17.0 | 11/11, ora non scritta | 3061109 |
| sbiadimento di notte | Lux 1.18.0 | 11/11, ora non scritta | 527da1e (11/11 14:49) |
| via emotiva con la J-lens | Lux 1.19.0 | 11/11 19:50 | abcb18e (codice), 24a0f51 (versione) |
| memoria.db superfluo | Lux 1.20.0 | 11/11 21:36 | 5af0b38 (codice), 1be52d8 (versione) |
| riflesso diviso | riflesso | 12/11 10:25 | merge 617890c; pubblico v0.10.2 (8a2827f) |
| stessa firma insieme | Lux 1.20.0 (nessun dato cambiato) | 12/11 17:47 | merge 1209517 |
| archi fra ricordi e coda | Lux 1.21.0 | 12/11 18:21 | merge 9314abc |
| memory e user A/B | riflesso | 12/11 21:27 | merge 750745c |

### 4.1 Riconsolidamento (1.14.0, `PIANO-1.14-RICONSOLIDAMENTO.md`)

**Cosa fa.** Dopo una consegna, la prima risposta dell'agente nello stesso flusso, entro 6 ore, dà la "firma del momento".
Di notte la carica di ogni arco del ricordo si sposta verso quella firma:
`carica <- carica + alfa x (momento - carica)`, con `alfa = 0.2 / (1 + log(S/S0))`. Un ricordo molto radicato si
sposta meno. Dopo lo spostamento S0 e S si scalano nella stessa proporzione (punto 8), così i rinforzi già presi
restano.

**Come.** Nuovi dati in `lux.npz`: `C0` (carica alla nascita, mai più toccata), `M` (una riga per consegna: nid, ora
della consegna e della risposta, differenza RMS, 51 valori del momento) e `rodaggio_da`. La firma del momento c'era già:
`firma_subito` firma ogni risposta finale dell'agente nel registro `giornata-firma.jsonl`. Il calcolo sta nel servizio
(`POST /riconsolida`), sotto lucchetto, rileggendo i dati dal disco.

**Decisioni.** D2: nessun tetto sulla carica, solo un freno sul passo per notte. D3: codice in
produzione subito, ma a EFFETTO ZERO finché la soglia di sorpresa (D1) non si fissa su qualche giorno di consegne col
vettore nuovo. D1 rinviata. D4 (correzioni, che nascono con carica zero): escluse per default, da chiedere all'utente prima
di accendere l'effetto.

**Verifica.** Misura su 25 coppie vere (consegna e prima risposta firmata, 10-11/11): differenza RMS sugli assi
0,89 / 1,02 / 1,38 / 1,95 / 2,07 (percentili 10/25/50/75/90). Sull'asse più carico del ricordo, momento meno carica
= -3,21 / -2,91 / -2,43 / -1,68 / -1,15: la risposta dell'agente portava sempre molto meno l'emozione del ricordo. Con
alfa 0,2 ogni richiamo avrebbe abbassato la dominante di circa 0,5 z: il riconsolidamento, così com'era, avrebbe fatto
sbiadire i ricordi richiamati. Per questo è partito a effetto zero. Prova del servizio su una copia (:8133) coi dati
veri: 25 momenti in M; C, F e stato identici. Test `test_riconsolida`, `test_forza` verdi. Revisione del piano: 2 punti
gravi (corsa con `aggiungi`, stallo del lucchetto), 5 medi, 4 bassi. Revisione del codice: 7 punti.

**Provvisorio.** PASSO_MAX = 0,5 z per arco e per notte (CC).

### 4.2 Tabella delle emozioni (1.15.0, `PIANO-1.15-TABELLA-EMOZIONI.md`)

**Cosa fa.** Ogni emozione ha un fattore alla nascita e uno sbiadimento per notte. La carica di un arco alla nascita è
`firma x fattore`.

**Come.** Tabella decisa dall'utente il 09/11 (`PROPOSTA-TABELLA-EMOZIONI.md`): fattori 1,0 / 0,8 / 0,6 / 0,4 (variabile
0,6); emivite 30 / 90 / 180 / 365 / 3650 notti. Divisione delle 51 emozioni in 16 positive, 28 negative e 7 neutre;
colpa, vergogna e rimorso sbiadiscono quasi zero. L'11/11 l'utente ha scelto l'effetto pieno: il fattore moltiplica la
carica e la dose del vettore scende con lei. Il riconsolidamento confronta il momento nella stessa scala
(momento x fattore); M tiene il momento grezzo.

**Verifica.** Misura sui 633 ricordi: i ricordi con vettore sono scesi da 545 a 453; con fattore 0,4 da quasi tutti a
16 su 83; con fattore 1,0 36 su 42. In produzione: `/forza` di un ricordo di disprezzo da 1,572 a 0,943 (x 0,6). Test
`test_tabella_115` e test di prima verdi.

### 4.3 Carica per arco (1.16.0, `PIANO-1.16-CARICA-PER-ARCO.md`)

**Cosa fa.** Dentro un ricordo gli archi centrali portano più carica di quelli di contorno.

**Come.** Decisione dell'utente: un engramma è centrale quanto il suo vettore bge-m3 è vicino al senso del ricordo
(media normalizzata dei vettori dei suoi engrammi). Centralità dell'arco = media dei coseni dei due engrammi. Peso
`W = (centralità / media del ricordo) ^ CONTRASTO`, riportato a media 1 nel ricordo: la media delle cariche del ricordo
resta `firma x fattore`. Ricordi con un arco solo e correzioni: W = 1.

**Verifica.** Misura su 627 ricordi: col coseno puro i pesi andavano in mediana da 0,88 a 1,10 (circa ±10%); con
CONTRASTO 3 da 0,68 a 1,33. In produzione pesi da 0,27 a 1,71; rapporto centrale/contorno in mediana 2,03; forza del
ricordo in mediana invariata (0,92-1,04); ricordi con vettore 450 invece di 453 (il caso più grande: il ricordo 74 da
0,545 a 0,325). Test `test_carica_116` verde.

**Provvisorio.** CONTRASTO = 3 (CC).

### 4.4 Contatori degli engrammi (1.17.0, `PIANO-1.17-CONTATORI.md`)

**Cosa fa.** Per ogni engramma: giorno di nascita, ultimo giorno in cui è riapparso nei messaggi, quante volte. Per
ogni ricordo: ultimo richiamo. Servono allo sbiadimento, per sapere se un tema è ancora aperto.

**Come.** "Riapparso" = stessa chiave o coseno bge-m3 >= 0,8 con un engramma di un messaggio del giorno (dell'utente o di
l'agente), una volta al giorno al massimo. Giorni vissuti. Calcolo nel servizio (`POST /riaccendi`), dalla notturna prima
del riconsolidamento.

**Verifica.** Alla produzione 230 engrammi risultavano già accesi più di una volta. Test `test_contatori_117` verde.
Nella notte del 13/11: 5 messaggi, 112 engrammi riaccesi.

### 4.5 Sbiadimento di notte (1.18.0, `PIANO-1.18-SBIADIMENTO.md`)

**Cosa fa.** Ogni notte, per ogni arco e ogni emozione:

```
carica_domani = carica_oggi x (1 - sbiadimento x freno)
freno = (1 - 0.3 x ripetizione) x (1 - 0.8 x aperta) x (1 - 0.5 x umore) x (1 - 0.6 x importanza)
```

ripetizione = `log(S/S0) / log(100)`; aperta = quanto il tema dei suoi engrammi è ancora vivo (dai contatori, senza
soglia); umore = ansia e tristezza dell'omeostato, solo per le emozioni negative; importanza = salienza del ricordo.
Ogni termine può solo rallentare. La carica si avvicina a zero senza toccarlo. Lo sbiadimento non cambia S e S0:
sbiadisce l'emozione, il ricordo ha già la sua curva dell'oblio. `C0` resta quella della nascita, quindi la dose del
vettore scende con la carica.

**Come.** `POST /sbiadisci` nella notturna, una volta per giorno vissuto, rodaggio da `sbiadimento_da`.

**Verifica.** Test `test_sbiadimento_118` verde. Notte del 13/11: giorno 3, rodaggio 0,1, umore 0,459, freno medio
0,641.

**Provvisorio.** I pesi 0,3 / 0,8 / 0,5 / 0,6 vengono dall'ordine degli studi (Verduyn), i valori NON sono misurati.
Scelte di CC: umore = max(ansia, tristezza, 0) / 2; importanza = media dei due ranghi di salienza.

### 4.6 Via emotiva del richiamo (1.19.0, `PIANO-1.19-VIA-EMOTIVA.md`)

**Cosa fa.** Lo stato emotivo del modello, letto in produzione, alza un poco il punteggio dei ricordi con la stessa
emozione, fra quelli già accesi da parole e senso. Da sola l'emozione non accende nessun ricordo.

**Come.** Ogni testo in arrivo (messaggio dell'utente, risposta finale dell'agente, risultato di uno strumento, riga
dell'appunto nel pensatoio) passa dalla J-lens sullo strato 29 (lente di Jacobi), con una traduzione appresa (ridge)
dallo stato nella lente ai 44 assi della firma. Schema a due tempi: la lettura del messaggio è l'emozione suscitata
(veloce); ogni lettura imprime l'omeostato con peso p = 0,12, che dà l'umore (lento, ritorno alla calma).
L'indizio emotivo è metà messaggio e metà umore (a = 0,5). Punteggio del ricordo `x (1 + k x accordo)`, con
`k = 0,2 x D / D_normale`, fra 0,1 e 0,4 (D = distanza dell'umore dalla calma). Pensatoio come la chat. Riparazione:
se la negatività dell'umore resta sopra soglia per 3 letture di fila, la metà dell'umore dell'indizio favorisce le
emozioni positive. Lente lenta (oltre 20 s) o rotta: consegna senza emozione, mai bloccata. Ogni lettura va nel diario
`diario-via-emotiva.jsonl`, con tutti i candidati, così ogni scelta si può rigiocare con altri parametri
(`verifica_via_emotiva.py`, comando "!verifica emotiva!").

**Risultati delle misure (579 ricordi con stati L29, validazione a 5 parti).**

| Lettura | Correlazione media con la firma | Dominante giusta al primo posto |
|---|---|---|
| lettura diretta della lente, L29 | 0,14 | 4% (a caso 2,3%) |
| lettura diretta, media L15-L31 | 0,160 | 4,5% |
| traduzione appresa 51 parole -> 44 assi | 0,59 | 19% |
| traduzione appresa stato nella lente -> 44 assi | 0,69 | 24% |
| controllo: sola lunghezza del ricordo | 0,30 | |
| controllo: bersagli rimescolati | 0,01 | |

- Strato quasi indifferente: tutti fra 0,677 (L31) e 0,690 (L25); la lente batte di poco lo stato grezzo (posto
  medio del ricordo nel richiamo 64 contro 72, a caso 290).
- Solo la forma dell'emozione, senza intensità: 0,675, quindi l'intensità comune non spiega il risultato.
- Nessun parametro (token letti, preparazione, componenti, forza, numero di ricordi) ha spostato più di un centesimo;
  altopiano da 400 ricordi. Conta quanto testo si legge: un pezzo corto di un ricordo lungo rappresenta male il tutto,
  un messaggio corto intero si legge bene. Anche 2 token distinguono sopra il caso (0,452 / 0,708 su tutti).
- Lettura di CC: la traduzione è forte anche perché la firma stessa è una lettura lineare degli strati 15-31, L29
  compreso. La lettura diretta è l'unica indipendente, ma è debole.
- Peso k su 165 messaggi dell'utente che sono ricordi: con k = 0,2 il primo ricordo cambia nel 13,9% dei casi, i primi 3
  nel 30,9%; il punteggio di parole e senso del primo resta al 99,2%. Senza emozione l'accordo emotivo del primo era
  già 0,347 (un candidato a caso -0,114).
- Umore (sequenza vera dei 579 messaggi-ricordo): sposta poco la scelta (accordo con l'umore al massimo 0,12).
- Intensità di un messaggio singolo letta male (correlazione 0,28 con l'intensità del Lux): per questo il peso segue
  l'intensità dell'umore.

**Verifica del codice.** Test `test_via_emotiva.py`: con l'emozione spenta il richiamo è identico cifra per cifra alla
1.18.0 su 50 indizi veri. `/lux-read` sul 35B di produzione: 0,44 s per 11 token, 4,9 s per 1500 token. Il 13/11 il
diario aveva 8 righe.

**Provvisorio.** k = 0,2, a = 0,5 e p = 0,12 sono decisi dall'utente ma da rivedere coi dati; D normale 1,1095 (taratura
simulata con letture, consegne e notti; da ritarare con la mediana vera); riparazione 0,1439 per 3 letture; 4000
caratteri letti; 20 s di attesa massima. Tutti in `VERIFICA-VIA-EMOTIVA.md`.

### 4.7 memoria.db superfluo (1.20.0, `PIANO-1.20-MEMORIADB-SUPERFLUO.md`)

**Cosa fa.** Testo, firma, dominante, fonte, cattura, salienza e voluto di ogni ricordo stanno in `lux-meta.json`. Il
ricordo nuovo lo crea il servizio del Lux (`POST /aggiungi`, dedup sul testo esatto, nid = massimo + 1). Il riflesso e
barra-prefill leggono dal servizio. `memoria.db` resta in sola lettura come archivio; i componenti fuori uso sono
andati in `archivio-20261111/`.

**Obiettivo dichiarato: effetto zero.** Cambiano solo il posto dei dati e chi assegna il nid.

**Verifica.** Migrazione vera: 655 ricordi identici al db; `lux.npz` e stato identici al byte alla 1.19.0. Su una
copia: fotografia della dose del vettore e dell'avviso identica sui 655 codici; richiamo su 50 messaggi identico al
byte. Revisione dei danni: 12 punti; revisione del codice: 3 medi, 4 bassi. Scarto noto: più ricordi nuovi nello stesso
giro ora entrano uno per volta, quindi S0 può cambiare di poco. Notte del 13/11: sentinella verde, 656 ricordi nel Lux.

### 4.8 Riflesso diviso (`PIANO-DIVISIONE-RIFLESSO.md`)

**Cosa fa.** `riflesso.py` (1.996 righe, un solo file che faceva proxy, cache, memoria involontaria, vettore, metadati,
riepilogo, via emotiva) è diventato un punto d'ingresso di circa 400 righe più 11 moduli `riflesso_*.py`. Nessun
cambio di comportamento.

**Come.** Uno script basato su `ast` ha spostato le funzioni un modulo per volta; fra moduli le chiamate passano per
attributo, così ogni oggetto esiste una volta sola.

**Verifica.** Una fotografia del proxy (server finto, rete isolata, orologio finto, 9 scenari: chat con e senza
ricordo, stop del vettore, pensatoio, cron, +lux e qlux, riepilogo, promozione, switch) produce un JSON di richieste,
risposte e file; il suo sha256 (211ccd10...) è rimasto identico dopo ognuno degli 11 spostamenti. 5 test esistenti
verdi e uguali all'uscita di partenza. Revisione con `ast` e `symtable`: le 96 funzioni hanno lo stesso albero di
prima a parte il prefisso del modulo, nessun bug. Rami non coperti dalla fotografia: pensatoio con 503 o interrotto,
switch rimandato, watchdog, sentinella e altri elencati nel piano. Sulla CI pubblica un test (3b, "switch rimandato")
è risultato instabile: rosso al primo tentativo, verde al secondo; in locale 0 fallimenti su 30.

### 4.9 Ricordi con la stessa firma insieme (`PIANO-FASE2-B-STESSA-FIRMA.md`)

**Cosa fa.** Il riflesso chiede al Lux fino a 4 ricordi. Dopo il primo entrano solo quelli con la stessa emozione
dominante (la stessa voce fra le 51). Il vettore resta uno, alla dose del ricordo dove l'emozione è più forte (massimo,
niente media né somma). Gli scartati non si consegnano e non si rinforzano: restano richiamabili.

**Come.** Il filtro sta nel Lux (`_catene`), prima del rinforzo, così un ricordo scartato non viene rinforzato senza
arrivare all'agente. qlux (ricerca volontaria) resta a un ricordo.

**Verifica.** Fotografia del Lux su 42 indizi, stato rimesso a ogni indizio: con un ricordo, risultato identico; con 4,
10 consegne miste su 42 sono diventate a firma sola. Fotografia del riflesso: cambia solo `quanti` da 1 a 4. Test
`test_stessa_firma` verde.

**Effetto collaterale previsto.** Ogni ricordo consegnato imprime l'umore (regola del 10/11): con 4 ricordi della
stessa dominante la spinta verso quell'emozione è circa 68% invece di 25% (1 - 0,75^4).

### 4.10 Archi fra ricordi e coda (1.21.0, `PIANO-FASE2-C-ARCHI-E-CODA.md`)

**Cosa fa.**
- Due ricordi scelti nella stessa selezione del Lux formano un arco fra ricordi (o lo rinforzano), anche se uno va in
  coda.
- Quando uno dei due affiora, l'altro riceve una spinta nella predisposizione e affiora più facilmente nei messaggi
  dopo (D1).
- Di notte (`POST /avvicina`) le cariche dei due ricordi legati con dominanti diverse si avvicinano, con il freno del
  riconsolidamento ridotto; parte subito, col rodaggio (D2), senza aspettare la soglia di sorpresa.
- La dominante dei ricordi toccati si ricalcola dalla carica di adesso (D5); la prima resta in `dominante_nascita`.
- I ricordi con emozione diversa vanno in una coda per conversazione e si consegnano uno per volta. Chi entra dopo
  passa avanti se è più negativo, a pari classe se è più intenso (D4). Dopo 30 minuti escono dalla coda.

**Verifica.** Consegna senza coda identica allo step b sui 42 indizi; fotografia del riflesso: cambia solo `"coda": []`.
Su una copia del Lux un ricordo (416) ha cambiato dominante già al primo giorno a rodaggio 10%: aveva due emozioni quasi
alla pari. Con la carica di quel giorno nessuna delle 655 dominanti sarebbe cambiata. Revisione del piano: 12
correzioni. Notte del 13/11: 1 arco fra ricordi, 4 archi spostati, rodaggio 0,1, 0 dominanti cambiate.

**Provvisorio.** PESO_ARCO_RICORDI = 1,0; FRENO_LEGATI = 0,5; ALFA_LEGATI = 0,2; PASSO_MAX 0,5. CODA_DURATA = 1800 s è
dell'utente.

### 4.11 Memory e user A/B (`PIANO-MEMORY-A-B.md`, `PIANO-MEMORY-A-B-IMPLEMENTAZIONE.md`)

**Problema.** Hermes mette MEMORY.md e USER.md dell'agente nel prompt di sistema come copia congelata. Allo switch di
conversazione la cache nuova doveva riprocessarli al primo messaggio: circa 4-5 mila token (l'11/11 MEMORY 24 voci e
9.211 caratteri, USER 24 voci e 5.600 caratteri).

**Cosa fa (meccanismo dell'utente del 12/11).** A = i file che l'agente scrive con lo strumento, come prima. B = una copia
tenuta dal codice (`memoria-b.json`, resa da Hermes stesso). Nel system della chat il riflesso mette B al posto della
copia di Hermes, subito dopo la parte fissa, quindi B sta nella cache master su disco e il prefisso non cambia quando
l'agente scrive. Alla promozione della cache le voci di A diverse da B vanno in fondo, sotto "informazioni aggiornate"; le
voci tolte sotto "avviso! informazioni obsolete:". Il confronto è per voce (separatore § di Hermes), con `difflib`,
resistente allo spostamento; dentro una sostituzione le coppie vecchia/nuova si fanno per somiglianza. Di notte
B = A e la master si rifà.

**Verifica.** Prova del 12/11 sul 35B, fuori dal riflesso, col system vero, 10 scambi veri e 3 contraddizioni false
(approvate dall'utente): col formato finale l'agente ha usato tutti e tre i valori nuovi in 3 giri su 3 (prima prova, col
formato meno/più: 5 su 6). Prefill del blocco (220 token) circa 1 s; chat intera da zero 8.629 token in 45,5 s
(190 token/s). Revisioni: piano 9 correzioni, codice 7. Test `test_memoria_ab.py` verde, fotografia del percorso vecchio
identica al byte. Notte del 13/11: "memoria B: B aggiornato; master.json assente, la base la rifà il primo
riepilogo"; il primo riepilogo (00:02) ha fatto nascere master.json e la master con B. **Primo switch dal vivo
(13/11 00:04, log di llama-35b):** il primo messaggio dopo la promozione ha ripreso riepilogo.kv e prefillato 598 token
in 3,7 s; il primo messaggio della sessione prima (23:57, chat rifatta da zero) ne aveva prefillati 19.249 in 82 s.
n = 1: un solo switch, da ripetere sui prossimi.

**Provvisorio.** SOGLIA_STESSA_VOCE = 0,5 (CC).

## 5. Altri punti della fase, già coperti

- Firma del momento (punto 5): la dà `firma_subito`, senza GPU di notte.
- Dose al richiamo (punto 7): `S_e = sum(w_i x F_i,e) / sum(w0_i)`, poi curva fra Dmin_e e Dmax_e
  (`DOSI-EMOZIONI.md`). Vettore solo nel ragionamento, spento a `</think>`, in produzione dall'11/11 (piano dello
  steering del riflesso). Valori provvisori: soglia_e 0,5 e k 1,13 (dal blocco di stato dell'handoff).
- Superati dall'utente l'11/11: discesa lenta del vettore dopo il picco, diadi nate da due ricordi, steering attenuato
  nella risposta, i tre difetti di `memoria.db` (caduti con la 1.20.0).

## 6. Prima notte con tutto acceso (13/11 00:00, `/tmp/notte-memoria.log`)

| Passo | Esito |
|---|---|
| giorni vissuti | 3 |
| sentinella | tutti i ricordi nel Lux 1.21.0 (656) |
| riaccendi | 5 messaggi, 112 engrammi |
| sbiadisci | giorno 3, rodaggio 0,1, umore 0,459, freno medio 0,641 |
| riconsolida | 258 consegne, 26 momenti, 0 spostati, sorpresa media 0,965, effetto 0 |
| avvicina | 1 arco, 4 spostati, rodaggio 0,1, 0 dominanti cambiate |

## 7. In attesa di dati

- **Riconsolidamento a effetto zero.** Resta da fissare D1: la soglia di sorpresa e la misura (RMS sugli assi o solo
  la dominante), su qualche giorno di consegne col vettore nuovo nel ragionamento. Due note da sciogliere con D1:
  le righe di M scritte dalla 1.14.0 hanno la sorpresa sulla firma grezza, dalla 1.15.0 sulla scala x fattore (va
  ricalcolata dai 51 valori grezzi); con lo sbiadimento la sorpresa contro la carica attuale cresce da sola, e il
  riconsolidamento riporterebbe su le cariche sbiadite (alternativa: confronto con C0). Poi D4 (correzioni) e
  l'accensione (`rodaggio_da`).
- **Via emotiva.** Ritarare D normale con la mediana vera del diario; rivedere k, a, p e la riparazione con
  "!verifica emotiva!"; accordo della traduzione sui ricordi nati dopo l'11/11 (se scende sotto 0,6, rifare la
  traduzione).
- **Sbiadimento e archi fra ricordi.** I pesi del freno, PESO_ARCO_RICORDI e FRENO_LEGATI vanno guardati nel rodaggio.
- **Controlli dal vivo ancora da leggere:** prima coda nella chat; altri switch con B nella master. Gia' visti il
  13/11 alle 00:04: la prima consegna con piu' ricordi della stessa dominante (due ricordi di attesa, nid 499 e 813,
  un vettore solo; il secondo portava all'agente l'informazione di servizio che le serviva, senza chiamate a strumenti) e
  il primo switch con B nella master (598 token rifatti).

## 8. Limiti

- Quasi tutti gli effetti nuovi sono al 10% del rodaggio, e il riconsolidamento è spento: la fase è in produzione, ma
  il suo effetto sul comportamento dell'agente non è ancora misurato. Le verifiche fatte provano che il codice fa quello
  che il piano dice, e che i pezzi con effetto zero dichiarato lasciano tutto identico.
- La misura che ha fermato il riconsolidamento (n = 25 coppie) è stata fatta col vettore vecchio o senza vettore.
- La traduzione della via emotiva impara dalla firma, che è anch'essa una lettura lineare degli strati 15-31:
  l'accordo 0,69 è in parte circolare. La sola lettura indipendente (diretta) arriva a 0,14-0,16.
- Le misure della via emotiva sono su ricordi interi (579) e su 165 messaggi dell'utente. Fra due ricordi passano ore,
  quindi la simulazione dell'umore è povera; la taratura con le consegne e le notti è ancora simulata.
- Molti numeri (pesi del freno, CONTRASTO, PASSO_MAX, PESO_ARCO_RICORDI, FRENO_LEGATI, soglia_e, k della dose,
  SOGLIA_STESSA_VOCE) non sono misurati: vengono dall'ordine degli studi o da una scelta di CC.
- La "soglia di eco" del piano (dose a cui l'emozione esce come parola) non è misurata da nessuna parte; per questo il
  tetto sulla carica è stato sostituito dal freno sul passo (D2).
- Rischio noto, scritto in D2: un ricordo triste richiamato in uno stato triste può caricarsi di più e affiorare di
  più (circolo del rimuginio). Va guardato nel diario quando il riconsolidamento si accende.
- Un test del riflesso (3b) è instabile sulla CI pubblica, causa non trovata.

## 9. Prossimi passi

1. Raccolta dati per D1 del riconsolidamento e per "!verifica emotiva!"; controllo delle righe della notturna e dei
   casi dal vivo degli step b, c, d oltre ai primi.
2. Riga del riflesso nei README pubblici (oggi "al massimo uno per messaggio").
3. **Fase 3, Fonti** (`PIANO-LUX-FASI-v1.12.md`): le fonti sono testi (quello che l'agente legge online e quello che
   gli scrive l'utente); la fonte si riconosce dalla provenienza nel contesto; diventa un engramma legato ai ricordi che
   ha prodotto, con una fiducia che cresce con le conferme e cala con le correzioni; una fonte web corregge solo sopra
   una soglia di fiducia, l'utente è certa dall'inizio; strumento di correzione per l'agente su `/correggi`. Da
   decidere con l'utente: il testo dello strumento, la soglia di fiducia, se le correzioni dell'agente entrano subito o di
   notte.
4. Dopo: fasi 4-12 (contiguità temporale, contesto di codifica, interferenza, familiarità, semantizzazione, memoria
   prospettica e scopi, ripasso nel sonno, ricordi flashbulb, storia di sé) e fase 13 (dump, aggiornamento e
   ripristino del Lux).
