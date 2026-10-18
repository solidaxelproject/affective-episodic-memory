# Lux degli engrammi: piano delle fasi 2-12 (dopo la 1.11.0)

La 1.11.0 contiene la fase 1, le correzioni: un ricordo che ne corregge un altro, legato da un arco con i parametri
`{corregge}{codice}`, consegnato in catena nella stessa risposta del tool, con l'originale barrato e mai piu' rinforzato.
Questo documento descrive le due fasi successive. Regola comune: ogni dato nuovo sta dentro le strutture del Lux
(`lux.npz`, engrammi, archi, stato degli archi), mai in file a parte.

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
7. **Dose al richiamo** = carica MASSIMA fra gli archi del ricordo, poi discesa lenta, come il corpo dopo il picco
   (regola picco-fine). La discesa si scandisce con l'ora dei messaggi (il riflesso registra l'arrivo di ogni messaggio,
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

**Da decidere dopo il test per layer:** i valori della tabella delle emozioni (carica, sbiadimento) in unita' di dose.

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
**Fase 6.** Interferenza e oblio indotto dal richiamo: richiamare un ricordo indebolisce i concorrenti simili (oggi il richiamo
   solo rinforza).
**Fase 7.** Familiarita' senza ricordo: "lo conosco ma non so da dove", sotto la soglia del richiamo.
**Fase 8.** Semantizzazione: col tempo l'episodio perde i dettagli e resta il fatto.
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
