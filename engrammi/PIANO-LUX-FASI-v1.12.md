# Lux degli engrammi: piano delle fasi 1-12

Questo documento descrive le fasi del Lux degli engrammi dopo la 1.10.0. La fase 1 e' fatta (1.11.0), le altre no.

Regole comuni:
- ogni dato nuovo sta dentro le strutture del Lux (`lux.npz`, engrammi, archi, stato degli archi), mai in file a parte;
- (22/10/2026) a fase finita, accanto a questo piano, un documento che spiega la fase come piace a un ricercatore
  ML: obiettivo, ispirazione dalla mente umana (studi), metodo, setup, risultati con il numero di casi e i controlli,
  limiti, prossimi passi. Passato prossimo, linguaggio semplice. File `engrammi/FASE-<n>-<nome>.md`.

## Fase 1. Le correzioni (1.11.0, in produzione)

**Problema.** Un ricordo sbagliato (per esempio un dato enciclopedico) non si poteva correggere: ne' memoria.py ne' il
Lux avevano una funzione di modifica, e tagliare gli archi di un ricordo lo faceva sparire intero, parte giusta compresa.

**Ispirazione dalla memoria umana.** Estinzione (Bouton): la traccia vecchia non si cancella, una traccia nuova la
inibisce e vince. Riconsolidamento (Nader 2000): un ricordo richiamato torna modificabile e si risalva con le
informazioni nuove. Episodico e semantico: "credevo X" resta come episodio, il fatto giusto prevale.

**Dall'idea alla versione fatta.** Il 12/10 l'utente ha proposto la correzione a livello di archi (arco negato AN, arco di
correzione AC, tool `correggicordo`, formato 2.0.0; dettagli nella sezione IDEA APERTA di PIANO-REFACTORING-LUX-RICHIAMO.md).
Il 16/10 ha deciso la forma piu' semplice, a livello di ricordo, che e' quella in produzione:
- la correzione e' un **ricordo nuovo** che entra nel Lux come gli altri (stesso taglio, engrammi condivisi), con un
  numero da 1.000.000 in su, fuori dalla serie di memoria.db (`PRIMO_CORREZIONE`);
- e' legata al ricordo corretto da un **arco fra ricordi** (posizione -1, dal primo engramma della correzione al primo
  del corretto) coi parametri `{corregge}{codice del corretto}` (`_lega`); quell'arco sta fuori da ricomposizione e
  richiamo;
- l'**originale non si tocca** e da quel momento **non si rinforza piu'** (`errati`): sbiadisce da solo con la curva
  di stabilita'. l'utente: "i ricordi segnati come sbagliati non vengono più rinforzati quando richiamati questo è
  fondamentale";
- **ripensamenti**: una correzione si corregge allo stesso modo; se un ricordo creduto sbagliato si rivela giusto, si
  aggiunge un'altra correzione e la precedente diventa errata;
- **consegna in catena**: al richiamo l'originale e tutte le sue correzioni arrivano insieme e occupano UN posto solo
  fra i 4 della risposta del tool; l'originale e' barrato (`~~testo~~`), le correzioni seguono con una lettera
  (`1°`, `1a°`, `1b°`...);
- **chi corregge**: l'utente 16/10 "le correzioni può produrle pure l'agente". Oggi si correggono da riga di comando
  (`lux_engrammi.py correggi CODICE "testo"`) o col servizio (`POST /correggi`); notturna e servizio non scrivono
  insieme (lucchetto).

**Verifiche (16/10).** verifica1110.py 34/34; ricomposizione dei 584 ricordi invariata; richiamo identico alla 1.10.0
dove non ci sono correzioni.

**Aperto.** Lo strumento per l'agente (nome e testo li decide l'utente; il 12/10 erano stati decisi `correggicordo` e la sua
descrizione, pensati per la versione ad archi); correzioni dell'agente applicate subito o di notte; la versione ad archi
del 12/10 (correggere un solo tratto del ricordo) non e' fatta.

## Fase 2. L'emozione che cambia col richiamo (riconsolidamento)

**CHIUSA il 13/11/2026** (tutti i passi in produzione; documento di fine fase: [`FASE-2-SPIEGATA.md`](FASE-2-SPIEGATA.md)).

**Dipende dal test delle emozioni nei layer.** La carica emotiva di un ricordo diventa la dose del vettore di steering
che colora il ricordo alla consegna. Il modello accetta le dosi solo dentro un certo intervallo, e alcuni layer vanno
evitati secondo il contesto e l'emozione. I valori della tabella delle emozioni si esprimono nelle unita' della dose e si
ricavano da quel test, con la funzione dose per emozione che lo chiude. Decisioni dell'utente del 17/10/2026.

1. **Tabella delle emozioni** (in `lux.npz`, 51 righe): `carica` (impatto alla nascita) e `sbiadimento` (velocita'
   propria, fissa). Valori a fine prova per layer. Divisione in 16 positive, 28 negative, 7 neutre ACCETTATA
   (`salienza/emozioni-scienza.md`); colpa, vergogna e rimorso sbiadiscono quasi zero.
2. **Carica per arco** (51 valori, differenziabile fra gli archi di un ricordo): nella realta' l'emozione si concentra
   sugli elementi centrali e i dettagli di contorno sbiadiscono prima (Kensinger 2009; Burke, Heuer e Reisberg 1992;
   Mather 2007). Alla nascita la carica di un arco viene dalla firma `F` dei suoi due engrammi: archi fra engrammi
   carichi nascono piu' carichi.
3. **Contatori.**
   - Per engramma: `nato_U`, `acceso_U` (ultimo giorno in cui e' riapparso nei messaggi, soglia SOGLIA_SEM 0.8),
     `accensioni`.
   - Per ricordo (uguale per tutti i suoi archi): **ultimo richiamo** `[g/m/aaaa|h:mm]`, scritto alla consegna.
   - Sugli archi restano `S`, `S0`, `U` (giorni vissuti, curva dell'oblio): `S/S0` = radicamento (forza di
     immagazzinamento, non scende mai), R = prontezza (forza di recupero, cala col disuso; Bjork e Bjork 1992).
   - Frequenza di richiamo TOLTA (17/10): doppione di R, che e' gia' nel richiamo (`facilita_archi`) ed e' tarata
     su dati umani (FSRS).
4. **Sbiadimento per notte** (`sbiadisci`, dopo `aggiungi`), per ogni arco e ogni emozione:
   ```
   carica_domani = carica_oggi x (1 - sbiadimento x freno)
   freno = (1 - 0.3 x ripetizione) x (1 - 0.8 x aperta) x (1 - 0.5 x umore) x (1 - 0.6 x importanza)
   ```
   - ripetizione = `log(S/S0) / log(100)` dell'arco;
   - aperta = `intervallo_medio / (intervallo_medio + tempo dall'ultima riaccensione)` dei suoi engrammi, con
     intervallo_medio = `(acceso_U - nato_U) / accensioni`; 0 se il ricordo e' stato corretto (scopo raggiunto).
     Nessuna soglia: il tema dirada piano (Klinger; Martin e Tesser; Masicampo e Baumeister 2011; Foerster, Liberman e
     Higgins 2005; Wrosch);
   - umore = ansia e tristezza dall'omeostato, solo per le emozioni negative (Walker, Skowronski e Gibbons 2003);
   - importanza = salienza del ricordo (`sal_dist`, `sal_se`).
   Pesi in ordine dagli studi (Verduyn: rimuginio e importanza), valori NON misurati: da tenere d'occhio nel rodaggio.
   Ogni modificatore puo' solo rallentare; la carica si avvicina a zero senza toccarlo.
5. **Firma del momento.** Il tagging scrive nel diario la firma della prima risposta dell'agente dopo il ricordo
   (passaggio della notte, GPU; il dato del ricordo resta nel Lux).
6. **Riconsolidamento** (`riconsolida`, dopo `aggiungi`): la carica dell'arco si sposta verso la firma del momento,
   `carica <- carica + alfa x (momento - carica)`, alfa = 0.2 / (1 + log(S/S0)), tetto per notte. Parte SOLO se c'e'
   sorpresa, cioe' la differenza supera una soglia (errore di previsione, Sevenster 2013); soglia da tarare nel
   rodaggio. Finestra: la prima risposta dopo il richiamo (Nader 2000, ~6 ore).
   **Tetto:** la carica non supera mai 0.02 sotto la soglia di eco (dose a cui l'emozione esce come parola); avvicinandosi
   al tetto i passi si riducono. Il rinforzo emotivo a ogni richiamo e' TOLTO (17/10): contraddiceva la sorpresa
   e la stabilizzazione era un doppione della ripetizione nel freno.
7. **Dose al richiamo** (funzione decisa da l'utente il 24/10/2026, sostituisce la "carica MASSIMA fra gli archi" del
   17/10). Per ogni emozione e del ricordo:
   ```
   w_i   = somma delle cariche attuali (emozione e) degli archi che toccano l'engramma i
   S_e   = sum_i(w_i x F_i,e) / sum_i(w0_i)         09/11 l'utente: diviso per le cariche ALLA NASCITA (w0, da C0 in lux.npz),
                                                   cosi' lo sbiadimento abbassa la dose (con sum(w_i) si annullava;
                                                   PROPOSTA-TABELLA-EMOZIONI.md, D3)
   D_e   = 0                                         se S_e < soglia_e
   D_e   = Dmin_e + (Dmax_e - Dmin_e) x (1 - exp(-S_e / k))   altrimenti
   ```
   - firme + carica degli archi (24/10): gli engrammi centrali, con archi carichi, pesano piu' dei dettagli di
     contorno (Kensinger 2009); la carica sbiadisce notte dopo notte (punto 4), quindi un ricordo vecchio colora meno
     di uno fresco, e il riconsolidamento (punto 6) sposta la dose dei richiami futuri;
   - la curva sale in fretta all'inizio e si appiattisce verso Dmax_e senza superarlo;
   - Dmin_e e Dmax_e (tabella in `engrammi/DOSI-EMOZIONI.md`) = intervallo [dose minima efficace, dose di picco] di ogni emozione, misurato nei giri della ruota
     di Plutchik (prove-contesto-lungo/8-sistema-steering/PIANO-PLUTCHIK.md), vettore se', finestra L15-L31. Sulle 8
     di base (giudice Opus, 24/10) i valori stanno intorno a 0.03-0.05, ma variano per emozione: la fiducia chiede piu'
     dose, rabbia e disgusto vanno in eccesso prima. soglia_e e k si tarano nel rodaggio;
   - piu' emozioni nello stesso ricordo: i vettori si sommano (sotto), con un tetto sulla dose totale.
   (SUPERATA, 11/11/2026: col vettore solo nel ragionamento, un ricordo per volta, la discesa lenta qui sotto
   non si fa.) Poi discesa lenta, come il corpo dopo il picco (regola picco-fine). La discesa si scandisce con l'ora dei messaggi (il riflesso registra l'arrivo di ogni messaggio,
   l'agente ne vede uno ogni 5). Durata = permanenza dell'emozione x dose di partenza x importanza (Verduyn 2009/2011).
   La dose per engramma, token per token, resta per quando il motore lo permettera'.
   **Steering attenuato nella risposta (30/10/2026):** il vettore non si spegne a `</think>`: resta acceso
   attenuato anche nella risposta, con una riduzione che simula quella umana, legata al contesto e al tipo di emozione
   (stessa permanenza della discesa qui sopra). Prova da fare: dose attenuata nella risposta sui 5 contesti di controllo,
   per trovare fino a che dose regge la tool call (col vettore pieno su tutta la risposta: 0 valide su 44, RELAZIONE E5).
   **Composizione del mix dei ricordi consegnati insieme (31/10/2026).** I ricordi di una consegna (fino a 4)
   partecipano tutti allo steering, ma la firma predominante si seleziona: di emozioni insieme se ne provano davvero
   poche, e le emozioni forti scacciano le altre. Servono tre funzioni:
   1. un FRENO che rallenti la variazione dell'intensita' di un'emozione da un turno all'altro (inerzia emotiva,
      Kuppens 2010): l'emozione gia' accesa ha un piccolo vantaggio per restarlo, cosi' due emozioni quasi alla pari non
      fanno saltare l'agente dall'una all'altra;
   2. una funzione che POTENZI LA DOMINANZA delle emozioni intense rispetto alle medie e alle lievi: ogni emozione del
      mix si indebolisce in proporzione a quanto la sovrasta la piu' forte (normalizzazione divisiva, restringimento
      dell'attenzione sotto un'emozione intensa, Easterbrook 1959), con un aumento del contrasto per le emozioni di forza
      intermedia (curva a S: si decidono in fretta, salgono o scendono); chi scende sotto soglia sparisce;
   3. una GERARCHIA fra le emozioni, che le fa prevalere o le depotenzia in base al tipo di emozione e alla carica degli
      archi del ricordo (la carica dice anche l'intensita' delle emozioni degli engrammi che quegli archi connettono).
   Piu' i due tetti: sul numero di emozioni che passano (2-3, come nelle persone) e sulla dose totale (prova di accumulo).
   **GESTIONE DELLA KV CACHE, PRIMO PASSO DEL CABLAGGIO (09/11/2026):** prima di cablare il vettore nel riflesso
   si chiudono i due piani della cache, che toccano lo stesso codice: `PIANO-RIEPILOGO-KV.md` (20/10: checkpoint con
   lo slot FATTO e compilato; riepilogo nel riflesso scritto e provato, NON in produzione ne' committato) e
   `PIANO-REVISIONI-FUORI-CACHE.md` (24/10: manca T4, produzione). 10/11: il riepilogo e' gia' IN PRODUZIONE (riflesso
   del 09/11); nello stesso passo va cablato il blocco metadati dell'utente (stato del pensatoio, data e ora in coda
   all'ultima risposta dell'agente, prefill anticipato dopo il riepilogo: PIANO-RIEPILOGO-KV.md 3.5, decisioni M1-M4; 10/11 notte: checkpoint della cresta K1-K3 e valutazione, cablaggio da fare). Il vettore appartiene alla KV cache del suo flusso
   (chat o pensiero autonomo) e la segue quando le cache si scambiano (manutenzione/ROADMAP-bozza.it.md).
   **⛔ INIEZIONE IN PRODUZIONE = QUELLA DEI TEST (10/11/2026): i vettori di steering si iniettano nello stesso
   modo delle prove, nel modello dentro luxifer.cpp (llama-35b, :8090).** Stessi vettori (out-occamy/vettori-*.pt,
   sistema.sorgenti()), stessa normalizzazione e dose per strato L15-L31 (sistema.strati(): dir/norma * dose *
   sqrt(2048)), stesse fasce (DOSI-EMOZIONI.md), stesso /control-vector con relative=true. Verificato 10/11:
   llama-adapter.cpp di luxifer.cpp e di luxifer-prova applicano la stessa formula (h += rms(h)*v); la prova ha in piu'
   solo LUXIFER_CVEC_NORMA (E39, scartata, spenta di default). Oggi il riflesso usa ancora ponte.dirs_emozione con
   emo-cvec-v2.npz (vettori vecchi): va sostituito. Codice condiviso (10/11): MODULO UNICO fuori dalle prove,
   importato da prove, confronto.py e riflesso (punto 0c della manutenzione).
   **UN RICORDO PER VOLTA: VETTORE NEL RAGIONAMENTO (l'utente 09/11/2026, supera la catena qui sotto e lo steering
   attenuato nella risposta del 30/10).** Il vettore del ricordo consegnato si inietta durante il ragionamento e
   termina quando il modello genera `</think>`; la risposta e' senza vettore. Dose = funzione del punto 7 (fra Dmin e
   Dmax). Base: test chat del 09/11 (gioia a 2.0/1.32/0.6% per tutto il ragionamento, 12/12 integri; RELAZIONE E59).
   **09/11 notte (l'utente, FATTO, engrammi/PIANO-FIRMA-44-ASSI.md): firma a 44 assi (24 + 20 diadi pure, vettori di lettura
   centrati); dominante = la piu' forte, se senza vettore la media del suo petalo (memoria.PETALO): ogni ricordo e'
   firmato con un'emozione che si puo' steerare. Supera la riga qui sotto.**
   **Dominante = la piu' forte fra le emozioni CON VETTORE (l'utente 09/11/2026, FATTO):** `memoria.dominante` e
   `memoria.CON_VETTORE` (36: 16 della ruota con fascia + 20 diadi pure), usate da firma_subito e tagging35b; i 224
   ricordi con dominante senza vettore migrati (engrammi/migra_dominante.py). Firma e salienza invariate.
   **Stessa emozione, piu' ricordi (09/11/2026):** se il Lux richiama piu' ricordi con la STESSA emozione
   dominante, si consegnano insieme, perche' il vettore e' uno solo; la dose e' quella del ricordo in cui
   quell'emozione e' piu' forte (il massimo delle D_e, niente media ne' somma). Al massimo 4 ricordi (09/11).
   Due emozioni quasi alla pari (l'utente 09/11, in quest'ordine): piu' rilevante (salienza del ricordo piu' alta, sal_dist e sal_se) > meno rilevante; intensa > base o
   tenue; negativa > positiva o neutra.
   **RICORDI IN CATENA NEL RAGIONAMENTO: PROTOCOLLO PER LA PRODUZIONE SUPERATO 09/11 dal paragrafo qui sopra, tenuto per storia. (l'utente 08/11/2026, "questo sistema entra in
   produzione").** Sostituisce la somma dei vettori dei ricordi e i range delle coppie, che cadono.
   - I ricordi della consegna (da 1 a 4, quanti ne da' il Lux) arrivano tutti insieme nella risposta del tool
     memorinvolontaria, prima del ragionamento, e il modello li legge SENZA vettore. Il vettore nel prefill del ricordo
     (modo lettura, come fa oggi `_colora_ricordo` del riflesso 1.10.0) e' SCARTATO: due ricordi di gioia al 100% non
     hanno portato la gioia, e il ricordo e' diventato estraneo ("contenuti che non mi appartengono"; RELAZIONE E57).
   - Nel ragionamento i vettori vanno in catena, nell'ordine dei ricordi: il vettore del primo ricordo acceso per 2 frasi
     chiuse, poi quello del secondo per 2 frasi, e cosi' fino all'ultimo; dopo, il resto del ragionamento e la risposta
     senza vettore. Dose di ogni vettore = la sua (funzione del punto 7 qui sotto, fra Dmin e Dmax).
   - Il token `</think>` e' VIETATO (logit_bias) finche' l'ultimo vettore non ha fatto le sue 2 frasi: coi vettori il
     ragionamento si accorcia e senza divieto la catena si fermava al secondo o terzo ricordo. E' memoria involontaria:
     il modello attraversa tutti i ricordi consegnati (l'utente: "e perche' sarebbe un problema?").
   - Aperto: in un test (ordine inverso) la generazione si e' fermata con un altro token di fine (probabilmente
     `<|im_end|>`): da registrare e, se serve, vietare insieme a `</think>`. Il cablaggio nel riflesso si fa con l'iter
     di upgrade, dopo il passo obbligato della nostalgia qui sotto.
   - 08/11 sera, l'utente: la via delle diadi bivettore (a + b -> c, qui sotto) e' ABBANDONATA.
   (SUPERATO, 11/11/2026: le diadi che nascono da due ricordi non si fanno; i ricordi si iniettano insieme solo
   se hanno la stessa firma emotiva. Le diadi pure restano come emozione dominante di un ricordo, firma a 44 assi.)
   **DIADI COME VETTORI PURI (l'utente 02/11/2026, supera il paragrafo del 31/10 qui sotto).** Si sviluppano i vettori
   puri di tutte le diadi che si possono fare (come l'amore dalle scene proprie, E31). La diade si inietta quando:
   - due dei ricordi richiamati hanno emozioni diverse e VICINE IN INTENSITA', sia rispetto al range di iniezione di
     ognuna sia come posizione nel petalo della ruota (intense con intense, medie con medie);
   - quei due ricordi sono stati richiamati PIU' VOLTE INSIEME;
   - e sono SUFFICIENTEMENTE VICINI: piu' engrammi soggetto condivisi (stessa persona, stesso cane, stesso argomento).
   Allora, al posto dell'emozione piu' forte fra i 4 ricordi, si inietta il vettore puro della diade di quelle due
   emozioni. Quando la diade si attiva, i due ricordi vengono COLLEGATI e da li' in poi si richiamano insieme. A ogni
   richiamo la dose del vettore della diade CRESCE di un tanto, sempre dentro il range efficace che non rompe il testo.
   Passaggio dalla diade composta alla pura (02/11/2026), con a e b le due emozioni e c il vettore puro della diade:
   - richiamo x: la diade si inietta coi 2 vettori a + b; la diade si attiva e i due ricordi si legano;
   - richiamo x+1: a e b a dose leggermente piu' bassa, piu' c a dose bassa, che compensa la riduzione di a e b;
   - richiamo x+n: la diade composta (a + b) si riduce in percentuale secondo la sua rilevanza rispetto alla diade
     pura, e c cresce;
   - a ogni richiamo successivo l'effetto complessivo dei vettori deve AUMENTARE.
       x     a ##############  b #############
       x+1   a #########       b ########       c ###
       x+2   a ########        b #######        c #####
   Servono quindi i range utili delle coppie composte (a + b) E dei vettori puri delle diadi (c), e il comportamento
   dei tre insieme (come la prova amore puro + estasi + ammirazione del 02/11, RELAZIONE E31).
   ✅ FATTO 09/11 (backup 3): emozioni.json e costruisci-emozioni.py hanno "nostalgia" (tag TEN, en ed emoji invariati); tolto il ponte EN.pop("tenerezza") in sistema.py. Lux e wikilux NON toccati: le loro "tenerezza" sono parole dei testi (ricordo 658, pagine Wikipedia), non il nome dell emozione.
   ⛔ PASSO OBBLIGATO PRIMA DEL CABLAGGIO (06/11/2026: "mettilo come obbligato, altrimenti me ne dimentico"): la diade fiducia + tristezza (sentimentality) si chiama NOSTALGIA, non tenerezza (tenerezza in italiano sta vicino all'affetto). Nello steering il nome è già cambiato (sistema.py, confronto.py); in emozioni.json e nel Lux non ancora. Prima di cablare le diadi nel Lux: backup, poi in /data/memoria-episodica-affettiva/emozioni.json "it": "tenerezza" diventa "nostalgia" (tag TEN, en sentimentality ed emoji restano o li decide l'utente), migrazione dei nomi nei lux-meta.json delle versioni in uso e di wikilux-meta.json, costruisci-emozioni.py, poi grep di "tenerezza" in riflesso, tagger, avatar e pagine; la radice "nostalg" non è più della malinconia.
   (Superato dal 02/11, tenuto per storia:) Le DIADI non si iniettano come voci a se': la diade (amore = estasi +
   ammirazione, ...) nasce dalla fusione delle sue componenti nel profilo; la proporzione fra le componenti la danno i
   loro assi nella firma, la zona utile della diade (griglie di PIANO-PLUTCHIK, sezione "diadi fra le intense" della
   pagina delle dosi) e' il limite da rispettare.
   **Piu' vettori insieme (18/10/2026):** i vettori di steering si SOMMANO (piu' ricordi nella stessa risposta del
   tool, o un vettore nuovo mentre un altro sta scendendo). Il modo di sommarli si stabilisce in questa fase. Base: test
   multivettore del 18/10, fino a 12 emozioni insieme o in differita, testo mai rotto, ogni emozione conserva circa la
   sua probabilita' di emergere.
8. **Effetto sulla forza.** Dalla carica nuova si ricalcola S0; S si scala nella stessa proporzione, cosi' i rinforzi
   gia' presi restano.
9. **Rodaggio di 30 giorni** per tutti i cambiamenti: giorni 0-10 al 10% dell'effetto pieno, 10-20 al 30%, 20-30 al
    70%, poi 100%. Data di partenza in `lux.npz`. Copia dello stato prima di ogni notte.
10. **Errori.** Se un passo della notte fallisce la notturna prosegue. Il vettore del riflesso usa l'`emo_tag` di
    memoria.db finche' non si decide altrimenti.
    **DA FARE QUI (l'utente 31/10, D7 di PIANO-FIRMA-ENGRAMMI.md):** il riflesso alla consegna smette di usare `emo_tag` e i
    vettori vecchi `emo-cvec-v2.npz` (`riflesso.py:537`, `ponte.dirs_emozione`) e inietta coi vettori sé, alla dose
    della funzione del punto 7, dalle cariche degli archi (firma nuova: 44 assi dal 09/11, diadi comprese).
11. **Hardware.** Tutti questi calcoli sono leggeri (CPU, millisecondi): possono girare con l'agente sveglia. Solo la firma
    del momento richiede il 35B.

Cablaggi nella notturna: `refactoring-notturna.md`.

**Tabella delle emozioni DECISA (09/11/2026):** fattore alla nascita e sbiadimento per notte delle 51 emozioni in
`engrammi/PROPOSTA-TABELLA-EMOZIONI.md` (D1, D2, D3); Dmin_e e Dmax_e in `engrammi/DOSI-EMOZIONI.md`.

**Dal piano di refactoring (22/10): via emotiva nel richiamo.** Il piano del 10/10 prevedeva tre vie del richiamo
(testuale, semantica, emotiva); oggi `accendi` ha solo le prime due ("via emotiva assente" in `lux_engrammi.py`). In
questa fase la carica degli archi puo' diventare anche un indizio: un ricordo affiora piu' facilmente se la sua emozione
somiglia a quella del momento (memoria congruente con l'umore, Bower 1981).
**⛔ DECISIONE DELL'UTENTE (ribadita 10/11/2026: "e' importante", non doveva uscire dal codice): lo stato emotivo del
modello si LEGGE IN PRODUZIONE con la J-lens e SELEZIONA il ricordo.** Era nella visione (firma emotiva letta dalla lens,
richiamo congruente con lo stato corrente) e nella candidata 1 (lettura L29 in coordinate lente via /lux-read sulla coda
del pensiero, ogni 25 token); l'ha tolta CC col refactoring del 10/10, SENZA decisione dell'utente (Lux degli engrammi =
solo via testuale e semantica bge-m3). Va rimessa come via emotiva del richiamo della fase 2: emozione del momento letta sul modello -> ricordi con
quella emozione favoriti. Da definire con l'utente nel piano del cablaggio: strato/strati e lente della lettura, ogni quanto,
come pesa contro le altre due vie.
**11/11 sera: principi dalla memoria umana accettati e lettura = J-lens vera su L29: engrammi/PIANO-1.19-VIA-EMOTIVA.md.**
**11/11 19:50: IN PRODUZIONE come Lux 1.19.0 (PIANO-1.19-VIA-EMOTIVA.md): J-lens su L29 tradotta ai 44 assi, umore a due
tempi, punteggio x (1 + k x accordo) sui ricordi gia' accesi, diario delle letture; verifica con !verifica emotiva!.**

**Fase 2, ultimo passo (22/10): `memoria.db` diventa superfluo.** Tutto quello che e' rimasto solo in
`memoria.db` entra nel Lux, poi nessun componente vivo lo apre piu'.
- Cosa c'e' ancora solo li': per ricordo `ts`, `fonte`, `emo_tag`, `emo_alpha`, `firma` (51), `salienza`,
  `n_richiami`, `classe` (vissuto/letto, mezza dose al vettore), `voluto`; gli archi fra ricordi (`archi`, 194
  hebbiani); la ricerca per parole (`nodi_fts`); i vettori semantici dei ricordi interi (`vettori.pt`).
- Chi lo apre oggi (da riscrivere sul Lux): `riflesso.py` (emo_tag e classe per il vettore), `tagging35b.py` e
  `notte-memoria.sh` (scrivono i ricordi nuovi: la notturna li scrivera' nel Lux), `memoria.py`, `ricorda.py` del
  container (richiamo per codice e per parole), `cervello.py`, `notturna-web.py`, `lux3d-gif.py`, `vettori_l29.py`,
  `verifica_post_versioning.py`, `firme-occamy/ricalcola-firme.py`, `lux_engrammi.py` (costruisci, aggiungi, primo stato).
- `memoria.db` resta come archivio in sola lettura, fuori dal funzionamento.
- 11/11 21:36: IN PRODUZIONE come Lux 1.20.0 (`engrammi/PIANO-1.20-MEMORIADB-SUPERFLUO.md`): i dati dei ricordi nel
  meta del Lux, il ricordo nuovo lo crea il servizio (POST /aggiungi), memoria.db in sola lettura. Prossimo: il riflesso si divide.

**Fase 2, dopo memoria.db superfluo (11/11/2026): il riflesso si divide.** Oggi `riflesso.py` (2.000 righe) fa
da solo proxy, slot e cache, memoria involontaria, vettore, blocco dei metadati, riepilogo e switch di CW, via emotiva
("god object"). Diventa il punto d'ingresso che chiama i moduli nell'ordine giusto, un modulo per lavoro. Si sposta un
pezzo alla volta senza cambiarlo, con la fotografia prima e dopo: stesse richieste, stesse risposte al byte.
**12/11/2026 10:25: FATTO, IN PRODUZIONE** (`PIANO-DIVISIONE-RIFLESSO.md`, merge 617890c, pubblico v0.10.2): riflesso.py
(~400 righe, proxy e avvio) + 11 moduli `riflesso_*.py`; fotografia identica al byte, revisione senza bug.

**Fase 2, dopo la divisione del riflesso (11/11/2026): ricordi con la stessa firma consegnati insieme.** Oggi
il riflesso chiede al Lux un ricordo per messaggio (`quanti=1`, `riflesso.py:922`, dal 09/11). Si cabla la regola
"Stessa emozione, piu' ricordi" del punto 7: se il Lux richiama piu' ricordi con la stessa emozione dominante, si
consegnano insieme (al massimo 4), il vettore e' uno solo e la dose e' quella del ricordo in cui l'emozione e' piu'
forte (il massimo delle D_e). I ricordi con firme diverse non si iniettano insieme (11/11). Va eseguito con
l'iter di upgrade, nel modulo della memoria involontaria.
**12/11/2026 17:47: FATTO, IN PRODUZIONE** (`PIANO-FASE2-B-STESSA-FIRMA.md`, merge 1209517): il filtro sta in
`Lux._catene` (prima del rinforzo), il riflesso chiede quanti=4, qlux resta 1, VERSIONE 1.20.0.

**Fase 2, insieme allo step qui sopra (11/11/2026): archi fra ricordi e coda dei ricordi richiamati.** Base: nella
memoria umana ricordi riattivati spesso insieme si integrano (Schlichting e Preston 2015) e l'emozione dell'uno passa
all'altro (condizionamento valutativo, De Houwer 2001; riconsolidamento, Nader 2000). Gli archi hebbiani fra ricordi di
`memoria.db` (156, archivio) non nascono piu' dal 09/11 (un ricordo per volta, niente co-richiamo): rinascono nel Lux.
Decisioni dell'utente (11/11):
1. **Archi fra ricordi** nel Lux, accanto agli archi fra engrammi dentro un ricordo.
2. **Firme che si avvicinano:** quando nasce o si rinforza un arco fra due ricordi con firme emotive diverse, il freno
   che trattiene la firma si riduce, e la firma di ENTRAMBI cambia: a ogni richiamo insieme le due firme si avvicinano.
   Si aggancia al riconsolidamento della 1.14 (spostamento della carica verso l'emozione del momento).
3. **Coda dei ricordi richiamati:** i ricordi con emozioni diverse che il Lux seleziona non si consegnano insieme (un
   vettore solo, due vettori emotivi rompono la generazione): vanno in coda, serialmente, in ordine cronologico di
   recupero, uno per consegna. Un ricordo che entra in coda dopo, se ha una firma emotiva piu' intensa o piu' negativa,
   passa avanti nella lista.
4. **Decadimento della coda:** dopo 30 minuti i ricordi richiamati e non ancora dati al modello escono dalla coda e
   tornano richiamabili dentro la CW.
Richiamo insieme che fa nascere l'arco (11/11): due ricordi scelti dal Lux nella STESSA SELEZIONE, anche se uno
va in coda e si consegna dopo. Da definire nel piano dello step (meccanismi all'utente, numeri provvisori a CC): di quanto si riduce il freno e su quali parametri (soglia di sorpresa, PASSO_MAX); la forza e lo
sbiadimento dell'arco fra ricordi. Va eseguito con l'iter di upgrade, dopo la divisione del riflesso.
**12/11/2026 18:21: FATTO, IN PRODUZIONE come Lux 1.21.0** (`PIANO-FASE2-C-ARCHI-E-CODA.md`, merge 9314abc; l'utente
12/11 sera D1 l'arco li fa tornare in mente insieme, D2 avvicinamento subito col rodaggio, D4 prima la negativita',
D5 dominante ricalcolata dalla carica).

**Fase 2, dopo la divisione del riflesso (11/11/2026): memory e user divisi in A e B.** MEMORY.md e USER.md di
l'agente in due parti: A con le informazioni stabili, nella cache base del riepilogo subito dopo la parte fissa; B con le
informazioni nuove, riempita allo switch. Scopo: allo switch un prefill il piu' rapido possibile. Piano, con la
riflessione dell'utente per intero: [`PIANO-MEMORY-A-B.md`](../PIANO-MEMORY-A-B.md).
IN PRODUZIONE 12/11/2026 21:27 (merge 750745c) col meccanismo deciso dall'utente il 12/11 sera (A = file dell'agente, B = copia del
codice nella master, "informazioni aggiornate" alla promozione, B = A di notte): [`PIANO-MEMORY-A-B-IMPLEMENTAZIONE.md`](../PIANO-MEMORY-A-B-IMPLEMENTAZIONE.md).

**Chiusura della fase 2 (22/10): i difetti di `memoria.db`.** (CADUTI, 11/11/2026: col Lux 1.20.0 `memoria.db`
e' solo un archivio in sola lettura, nessun componente vivo lo apre; i tre punti qui sotto non si fanno.)
1. Indice testuale (`nodi_fts`) aggiornato solo all'inserimento (trigger `nodi_ai`): aggiungere i trigger di modifica
   e di cancellazione, cosi' la ricerca per parole non trova mai un testo vecchio.
2. Un solo arco fra due ricordi (chiave `archi(a, b)`): chiave che comprende il tipo, cosi' un arco hebbiano e uno di
   altro tipo possono stare insieme; `ricorda.py` e `_hebb_boost` rinforzano solo gli archi hebbiani.
3. Schema nel codice diverso dal db: la stringa `SCHEMA` di `memoria.py` riceve la colonna `tipo` degli archi.
Oggi nessun codice modifica o cancella testi e i 194 archi sono tutti hebbiani: nessun danno in corso. La modifica
tocca il db vivo, quindi si fa con l'iter di upgrade (backup, prova su copia, via dell'utente). Se il passaggio al Lux
qui sopra arriva prima, questi tre punti cadono: il db resta solo come archivio.

## Interfase 2-3. Il richiamo dei tratti accesi e i percorsi fra ricordi (13/11/2026)

Relazione per la pagina pubblica (processo, equazioni, paper numerati): [`RECUPERO-MNEMONICO.md`](RECUPERO-MNEMONICO.md).
Ricerche: [`RICERCA-RICHIAMO-EMOTIVO.md`](RICERCA-RICHIAMO-EMOTIVO.md), [`RICERCA-LEGAMI-NUOVI.md`](RICERCA-LEGAMI-NUOVI.md) (ponti fra ricordi).

Nome deciso dall'utente: "interfase 2-3". Viene dopo la fase 2 e prima della fase 3. Riprende il punto del piano di
refactoring del 10/10 rimasto fuori (`percorri`, regola D3: richiamo camminando sugli archi).

**Da dove nasce (misure del 13/11).** Ogni ricordo e' un messaggio intero della chat (il riflesso lo mette in coda,
`firma_subito.py` lo fa entrare; minimo 15 caratteri, nessun massimo). Su 668 ricordi: mediana 466 caratteri, 179 sopra
1000, 74 sopra 2000, il piu' lungo 9374 (ricordo 789, una risposta dell'agente di 69 righe con temi diversi). La lente legge
la media del testo intero (fino a 4000 caratteri): una lettura per messaggio. Crescita del Lux a blocchi di 111 ricordi:
engrammi nuovi da 4367 a 2786 per blocco, archi stabili (circa 4500-6500), archi per engramma da 1,48 a 1,76: il
vocabolario si satura, gli archi crescono col testo (l'utente: efficiente, va bene).

**Decisioni dell'utente (13/11):**
1. Quello che arriva all'agente sta sotto i 512 token e finisce con un punto di fine frase.
2. Il ricordo NON si taglia alla nascita: resta intero nel Lux. A l'agente arrivano solo i tratti accesi dal discorso
   (nella mente umana: completamento di schema dell'ippocampo, ricordo ricostruttivo di Bartlett).
3. Percorsi fra ricordi: agli engrammi condivisi il cammino puo' passare sulla catena di un altro ricordo (diffusione
   dell'attivazione, Collins e Loftus 1975). Ne escono tratti di ricordi diversi messi insieme.
4. I tratti di ricordi diversi appaiono all'agente come connessioni fra ricordi diversi, ognuno col suo contesto (da che
   ricordo viene, quando, con che emozione): e' il monitoraggio della fonte (Johnson, Hashtroudi e Lindsay 1993).
   Le parole con cui appaiono le decide l'utente prima che entrino nel codice.
5. L'inferenza fra i pezzi la fa il modello leggendoli insieme (Lux = ippocampo che collega, modello = corteccia che
   ragiona; inferenza associativa, Zeithamova, Schlichting e Preston 2012). Senza il contesto di ogni tratto lo stesso
   meccanismo darebbe falsi ricordi (paradigma DRM, Roediger e McDermott 1995).

Differenza con quello che c'e': gli archi fra ricordi della 1.21.0 (`RA_*`) e quelli delle correzioni (1.11.0) legano
ricordi interi; `richiama` da' un punteggio al ricordo intero e `ricomponi` lo rende tutto (propagazione sugli archi
tolta l'11/10: abbassava i richiami giusti da 35 a 30 su 40).

**Emozione dei tratti (13/11).** Con piu' tratti si inietta UN vettore, quello dell'arco piu' importante; la funzione
deve seguire come funziona la mente umana, contestuale e non lineare. Ricerca sui modelli tarati su dati umani
(ACT-R, CMR, eCMR, CMR3, attivazione diffusa, recupero competitivo, indice ippocampale), 17 effetti umani, funzione
proposta e 12 paper da citare: [`RICERCA-RICHIAMO-EMOTIVO.md`](RICERCA-RICHIAMO-EMOTIVO.md). Proposta, non ancora decisa.
Prova fuori linea (13/11, [`prova-interfase-23-emozione/RISULTATI.md`](prova-interfase-23-emozione/RISULTATI.md)):
contestuale (12 messaggi -> 10 ricordi e 10 emozioni), l'umore pesa in proporzione all'intensita', competizione piatta da
ritarare; LIMITE: dentro un ricordo tutti gli archi hanno la stessa emozione (coseno 1,0), serve una firma per tratto.
DECISO (l'utente 13/11 pomeriggio): NIENTE firma per tratto (obbligherebbe a cambiare vettore mentre l'agente ragiona). Il
vettore, uno solo, viene dagli ENGRAMMI ACCESI dal messaggio (firma dell'engramma = cariche di tutti i suoi archi pesate
dalla forza; l'emozione sta nell'indizio, come il posto). I tratti li sceglie la funzione di attivazione, come nella
memoria umana: sopra soglia, i piu' attivi, al massimo 4 (Cowan 2001), sotto 512 token. Prova v2 nella stessa cartella.
Da qui nasce anche la pagina pubblica sul recupero mnemonico (13/11): una pagina che spiega tutto il richiamo,
linkata nei README sotto un breve riassunto (compreso il richiamo senza tool call dello screenshot del 12/11); questa
funzione ne diventa una sezione, coi paper determinanti linkati.

**Nome e testi APPROVATI dall'utente (13/11 sera, parola per parola, non cambiarli):**
- nome della funzione: **ricombinazione mnemonica** (i pezzi di ricordi diversi rimessi insieme; Schacter e Addis 2007,
  simulazione episodica costruttiva); "interconnessione engrammatica" = i ponti fra engrammi.
- risposta di memorinvolontaria: prima riga `N° ricombinazione mnemonica` (N conta le ricombinazioni arrivate nella
  conversazione: 1°, 2°, ...), poi un tratto per riga, nell'ordine di attivazione, nient'altro. Esempio:
      1° ricombinazione mnemonica
      Buongiorno l'agente, come stai oggi?
      è un regalo. 🌅
- voce da aggiungere alla MEMORY dell'agente (parte A, la mette l'utente o CC col container acceso):
      Ricombinazione mnemonica: pezzi di ricordi diversi che il discorso ha riacceso insieme. Ogni riga viene da un momento diverso: non sono un unico ricordo.

**Da decidere:** regola del cammino (da quali engrammi si parte, come si sceglie a un bivio, quando ci si
ferma); quanti tratti e quanti ricordi diversi al massimo; le parole con cui appaiono i tratti e il loro contesto;
l'emozione di un tratto (oggi la firma e' del ricordo intero) e il vettore di steering con tratti di ricordi diversi;
cosa si rinforza (solo gli archi percorsi?) e cosa entra nel riconsolidamento.

## Fase 3. Fonti

1. **Le fonti sono testi:** quello che l'agente legge online (ricerca, pagine) e quello che gli scrive l'utente.
2. **La fonte si riconosce da sola dalla provenienza nel contesto**, momento per momento: un messaggio dell'utente, il
   risultato di uno strumento con il suo indirizzo. L'agente non la sceglie e non la dichiara: il riflesso la ricava dal
   punto del contesto da cui arriva la notizia.
3. **La fonte e' un engramma** legato ai ricordi che ha prodotto. La fiducia e' la forza dei suoi archi: cresce quando
   una sua notizia viene confermata, cala quando viene corretta.
4. **Chi corregge.** L'utente e l'agente. Una fonte web diventa "certa" quando la sua fiducia supera una soglia: solo
   allora una sua notizia puo' produrre una correzione. L'utente e' certa dall'inizio.
5. **Strumento di correzione per l'agente** (codice del ricordo e testo; la fonte la aggiunge il riflesso): chiama
   `/correggi` del servizio del Lux, gia' presente dalla 1.11.0. Il testo della descrizione dello strumento lo decide
   l'utente prima che entri nel codice.
   Nota (22/10): il 12/10 l'utente aveva deciso nome `correggicordo` e descrizione "Corregge un tuo ricordo. Scrivi il
   numero del ricordo, poi il testo sbagliato preceduto da - e il testo corretto preceduto da +.", pensati per la
   correzione a tratti; la 1.11.0 corregge il ricordo intero (codice + testo nuovo), quindi il testo va riadattato da lei.

**Da decidere:** il testo dello strumento di correzione; la soglia di fiducia; se le correzioni dell'agente entrano
subito o nella notte.

## Verifica (per entrambe le fasi)

- Con il rodaggio a zero e senza fonti, risultati identici alla versione precedente.
- In una copia del Lux: notti finte con firme finte; riconsolidamento che si avvicina al tetto senza toccarlo; dissipazione per
  emozione; rodaggio; fonti che guadagnano e perdono fiducia; nessun cambiamento sugli altri ricordi.
- `verifica_post_versioning.py` sulla cartella nuova.

## Fasi 4-12: dopo le fasi 2 e 3 (l'utente 16/10/2026, numerate come fasi il 17/10)

Ordine: prima le fasi 2 e 3, in pausa fino alla fine dell'analisi funzionale dei vettori di steering emotivo (prova per
layer). Poi queste caratteristiche della memoria umana, oggi assenti nel Lux degli engrammi (cercate nel codice e nei
piani il 16/10, non trovate). Nessuna e' decisa: i dettagli li stabilisce l'utente. Ordine: fase 2 (in attesa della
prova per layer), fase 3, poi dalla 4 alla 12.

**Fase 4.** Contiguita' temporale: un ricordo richiama quelli vicini nel tempo (oggi gli archi legano engrammi dentro un ricordo,
   non ricordi in sequenza).
**Fase 5.** Contesto di codifica: chi c'era, attivita', ora del giorno come indizio di richiamo.
   Dal piano di refactoring (22/10): al richiamo nasce un legame fra il messaggio che ha fatto affiorare il ricordo e il
   ricordo stesso (oggi `consegna` rinforza gli archi del ricordo ma non crea legami nuovi).
**Fase 6.** Interferenza e oblio indotto dal richiamo: richiamare un ricordo indebolisce i concorrenti simili (oggi il richiamo
   solo rinforza).
**Fase 7.** Familiarita' senza ricordo: "lo conosco ma non so da dove", sotto la soglia del richiamo.
**Fase 8.** Semantizzazione: col tempo l'episodio perde i dettagli e resta il fatto.
   Dal piano di refactoring (22/10): ricordo vago, gli archi indeboliti dall'oblio escono dalla ricomposizione e il
   ricordo torna con dei buchi (oggi `ricomponi` usa tutti gli archi; la curva dell'oblio pesa solo sulla scelta).
**Fase 9.** Memoria prospettica: intenzioni che scattano quando si verifica una condizione.
   **Esteso agli SCOPI (17/10):** nella mente uno scopo si manifesta con concetti piu' pronti, attenzione
   selettiva, pensieri che tornano da soli, emozione come segnale di avanzamento, gerarchia astratto -> concreto
   (Goschke e Kuhl 1993; Klinger; Smallwood; Carver e Scheier; Vallacher e Wegner). Nell'agente:
   - elenco corto degli scopi aperti nel prompt di sistema (una riga ciascuno, come il MEMORY.md di Hermes): sempre attivi;
   - dettagli (gerarchia, passi, avanzamento) in skill di Hermes, caricate quando il discorso tocca lo scopo; dormita
     in mezzo se serve a tenere piccola la KV;
   - steering emotivo alla consegna della skill, dall'avanzamento rispetto all'atteso (Carver e Scheier: piu' veloce =
     gioia, piu' lento = frustrazione/ansia, bloccato = rabbia, abbandonato = tristezza, raggiunto = soddisfazione/
     sollievo); serve un registro dei passi con le date; dose e layer dalla prova per layer;
   - gli engrammi del testo di uno scopo aperto alimentano "aperta" della fase 2 direttamente; scopo chiuso -> aperta 0
     per i ricordi legati (toglie la distanza maggiore della fase 2: lo scopo indovinato dalle parole che tornano).
**Fase 10.** Ripasso nel sonno: la notte rigioca e rinforza alcuni ricordi del giorno.
**Fase 11.** Ricordi flashbulb: momenti a emozione altissima fissati col contesto intero (in parte coperto dalla salienza).
**Fase 12.** Storia di se': ricordi organizzati per periodi e temi della vita.
**Fase 13 (ultima, l'utente 11/11/2026): dump, aggiornamento e ripristino.** Un sistema unico per passare da una versione
del Lux alla successiva, per chi installa dal repo pubblico e per l'agente: prima del passaggio un dump in un archivio di
tutti i dati mnemonici (dalla 1.20.0 i ricordi stanno gia' nel meta: testo, firma, dominante, fonte; in piu' lo stato
imparato: rinforzi S/S0/U, sbiadimento, momenti M, contatori degli engrammi), con una chiave che sopravvive alla
ricostruzione (ricordo + testi dei due engrammi dell'arco, non il numero d'arco); poi Lux ricreato da zero con
costruisci() della versione nuova e reinserimento dello stato sugli archi che esistono ancora (i nuovi nascono freschi,
quelli spariti in un registro, niente buttato); ripristino dal dump se qualcosa va storto. Al posto dei da_precedente
scritti a mano per ogni versione; con esso un MIGRAZIONI.md pubblico (cosa cambia, comando, tag). Da progettare con l'utente.

**Notturna (16/10):** da rivedere piu' in la'. Le sue funzioni attuali (fusione in schemi, potatura) potrebbero
non essere coerenti col funzionamento della memoria umana e andare deprecate. Per ora resta com'e'.
