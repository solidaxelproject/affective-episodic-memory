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
   S_e   = sum_i(w_i x F_i,e) / sum_i(w_i)          media delle firme degli engrammi, pesata per la carica degli archi
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
   Poi discesa lenta, come il corpo dopo il picco (regola picco-fine). La discesa si scandisce con l'ora dei messaggi (il riflesso registra l'arrivo di ogni messaggio,
   l'agente ne vede uno ogni 5). Durata = permanenza dell'emozione x dose di partenza x importanza (Verduyn 2009/2011).
   La dose per engramma, token per token, resta per quando il motore lo permettera'.
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
11. **Hardware.** Tutti questi calcoli sono leggeri (CPU, millisecondi): possono girare con l'agente sveglia. Solo la firma
    del momento richiede il 35B.

Cablaggi nella notturna: `refactoring-notturna.md`.

**Da decidere dopo i giri della ruota:** i valori della tabella delle emozioni (carica, sbiadimento) in unita' di dose,
Dmin_e e Dmax_e per emozione (punto 7).

**Dal piano di refactoring (22/10): via emotiva nel richiamo.** Il piano del 10/10 prevedeva tre vie del richiamo
(testuale, semantica, emotiva); oggi `accendi` ha solo le prime due ("via emotiva assente" in `lux_engrammi.py`). In
questa fase la carica degli archi puo' diventare anche un indizio: un ricordo affiora piu' facilmente se la sua emozione
somiglia a quella del momento (memoria congruente con l'umore, Bower 1981).

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

**Chiusura della fase 2 (22/10): i difetti di `memoria.db`.**
1. Indice testuale (`nodi_fts`) aggiornato solo all'inserimento (trigger `nodi_ai`): aggiungere i trigger di modifica
   e di cancellazione, cosi' la ricerca per parole non trova mai un testo vecchio.
2. Un solo arco fra due ricordi (chiave `archi(a, b)`): chiave che comprende il tipo, cosi' un arco hebbiano e uno di
   altro tipo possono stare insieme; `ricorda.py` e `_hebb_boost` rinforzano solo gli archi hebbiani.
3. Schema nel codice diverso dal db: la stringa `SCHEMA` di `memoria.py` riceve la colonna `tipo` degli archi.
Oggi nessun codice modifica o cancella testi e i 194 archi sono tutti hebbiani: nessun danno in corso. La modifica
tocca il db vivo, quindi si fa con l'iter di upgrade (backup, prova su copia, via dell'utente). Se il passaggio al Lux
qui sopra arriva prima, questi tre punti cadono: il db resta solo come archivio.

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

**Notturna (16/10):** da rivedere piu' in la'. Le sue funzioni attuali (fusione in schemi, potatura) potrebbero
non essere coerenti col funzionamento della memoria umana e andare deprecate. Per ora resta com'e'.
