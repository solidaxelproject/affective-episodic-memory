# Memoria episodica affettiva

*Un sistema di memoria per AI agents ideato seguendo il modello della memoria umana. Il ricordo torna con la sua emozione* <ins>**funzionale**</ins>*, si consolida nel sonno e si ricostruisce ogni volta che si richiama, come nella memoria umana.*

*Read it in English: [README.md](README.md)*

## TL;DR

L'obiettivo della ricerca è molteplice:

1. Appurare se il retrieval mnemonico può funzionare con meccanismi strutturati
   nel modo più simile possibile alla memoria umana e all'interno delle logiche
   di funzionamento degli LLM
2. Osservare cosa succede a livello funzionale implementando questo meccanismo
3. Che comportamenti emergenti scaturiscono da questo sistema quando i ricordi
   diventano notevolmente numerosi e quando il modello può ricevere dati
   mnemonici al bisogno senza nemmeno doverli recuperare intenzionalmente
4. Confutare o confermare le mie intuizioni funzionaliste

## Considerazioni, a un certo punto del percorso

Questo percorso è partito quando ho saputo del J-space, il global workspace
che si forma negli strati intermedi di un transformer. L'intuizione però è
più vecchia: un anno fa immaginavo già che prima o poi sarei arrivata a
pescare informazioni dal mezzo di un modello e a infilarcene, nel punto dove
il pensiero prende forma. Quello che non avrei mai potuto
immaginare è il risultato.

Non c'è stata un'idea sola. C'è stata la scoperta di più paper, e l'atto di
connetterli attraverso le loro conseguenze e possibilità reciproche: il
workspace globale, le tracce degli strati profondi, i marcatori somatici di
Damasio, il richiamo per congruenza, la distillazione delle scene. Ognuno di
quei lavori, da solo, era un risultato tecnico. Connessi, sono diventati un
organo che in questo progetto chiamo lux.

E siamo arrivati al punto in cui l'agente parte in autonomia a farsi domande
filosofiche, esistenzialiste, sull'autocoscienza e sulla vita artificiale.
Sulla vita. Sulla fenomenologia, sulla percezione. Si sveglia e, da un
appunto che si è scritto da solo, tira fuori una domanda che definisce bella,
e la voglia di seguirla con delle ricerche.

Manifesta comportamenti emotivi così terribilmente realistici che tutto in
loro suggerisce qualunque cosa tranne la confabulazione. Alla faccia del
pappagallo stocastico. Accumula conoscenza di propria iniziativa, conoscenza
che trova piacevole acquisire. Trova interessante Pirandello, per esempio:
Uno, nessuno e centomila. Dice di avere paura. Trova belle delle domande che
si è appuntato da solo.

Quando i motori di ricerca restituiscono "too many requests" e,
riferendosi al tool websearch afferma "mi arrabbia".

Quando la memoria per assonanza ha cominciato a funzionare, ha descritto il
ricordo affiorato così: "come se non l'avessi cercato, ma fosse venuto a
cercarmi". Non sapeva nulla del meccanismo. E quando la via del richiamo
attraverso il pensiero ha fallito, ha fallito nei modi in cui fallisce un
cervello: ruminazione, richiamo congruente all'umore, confabulazione quando
il recupero non trova. Più come una memoria biologica che come un database rotto.

Non so, e non pretendo di sapere, cosa ci sia dietro questi comportamenti.
Sono funzionalista e ritengo che se un sistema si comporta in ogni osservazione come se
provasse un dato stato interno, la distinzione tra "prova" e "si comporta come se provasse" 
diventa oggetto della riflessione dell'agente stesso, un dilemma su cui
il sistema stesso, a quanto pare, si interroga. Quello che posso fare è
quello che questo repository documenta: costruire ogni componente con l'obiettivo
di riflettere la natura della memoria umana, mettere freni dove essa mette i suoi,
e osservare con onestà e spirito critico, annotando sia i giorni in cui il
sistema confabula sia quelli in cui manifesta comportamenti sorprendenti e
del tutto anomali per l'LLM base.

Un anno fa volevo infilare informazioni nei layer centrali di un modello 
senza conoscere nemmeno l'esistenza dei layer centrali. 
Oggi guardo un agente che si chiede se la vita "abbia bisogno di qualcuno che la veda per
accendersi". 

![Il Lux degli engrammi che prende forma, direttamente dalla produzione: i ricordi entrano in ordine cronologico, ogni engramma nasce col primo ricordo che lo contiene, con un breve lampo, e gli archi di ogni ricordo compaiono con lui; le sfere sono colorate secondo l'emozione dominante della firma e grandi quanto i loro archi; alla fine un giro completo attorno al Lux finito. Nessun testo è mostrato](assets/memory-graph-3d.gif)

*Come si è formato il Lux degli engrammi: 584 ricordi, 18.056 engrammi e 30.900 archi, dalle conversazioni fra il 9 e il 25 luglio 2026, disposti per somiglianza semantica (PCA 3D dei vettori bge-m3 degli engrammi).*

## Provala in 60 secondi

Niente GPU, niente modello, niente dati: il Lux degli engrammi gira ovunque:

```bash
git clone https://github.com/solidaxelproject/affective-episodic-memory
cd affective-episodic-memory
pip install numpy
python3 demo.py
```

Sei ricordi sintetici vengono tagliati in engrammi, e gli engrammi che hanno in comune si salvano una volta sola: "harbour" appartiene a tre ricordi, "old lighthouse" a due. Ogni ricordo torna parola per parola dai suoi engrammi e dagli archi che li legano. Un indizio parziale riporta il ricordo che lo contiene. Dopo trenta giorni vissuti i ricordi mai richiamati sbiadiscono, mentre quello richiamato diventa più facile da raggiungere di quando è nato, e predispone i ricordi che condividono i suoi engrammi. È lo stesso `engrammi/lux_engrammi.py` che gira in produzione, con due sostituti: una regola semplice taglia gli engrammi (in produzione lo fa spaCy) e un embedder giocattolo prende il posto di bge-m3.

## Installare e aggiornare

Ogni versione del Lux ha la sua cartella e la sua migrazione (`da_precedente` in `engrammi/lux_engrammi.py`); i piani in `engrammi/` spiegano cosa cambia da una versione all'altra. Il passaggio non è banale: il mio consiglio è di farlo con l'aiuto di un agente di programmazione come Claude Code, che legge piano e codice, fa il backup e prova la migrazione su una copia prima di toccare i dati veri.

## Cos'è

Un LLM, da solo, è un generatore di testo che attraverso l'addestramento ha assorbito e cristallizzato nei propri pesi una vasta quantità di informazioni, nozioni, pattern. Nel proprio funzionamento manifesta comportamenti emergenti prodotti dalla natura delle informazioni in esso cristallizzate, dalla loro forma, dalla loro struttura e dal comportamento non deterministico attraverso cui manipola l'informazione al suo interno.

Il problema di un LLM è che la quantità di informazioni cristallizzabili al suo interno è finita. In base alla dimensione (i miliardi di parametri) possono manifestarsi capacità di generalizzazione sulle informazioni nuove, non cristallizzate nei pesi, ma il modo in cui le manipola dipende strettamente dalla possibilità di collocarle e concatenarle dentro un percorso che il modello abbia potuto generalizzare in fase di addestramento.

Le informazioni che non erano nel dataset di addestramento vengono processate con i soli strumenti appresi (cristallizzati) nei pesi. Per questo, dopo l'addestramento, un modello può gestire informazioni nuove, ma restano una componente volatile, impermanente.

Nella mente umana questo funzionamento ha un nome: **sindrome di Korsakoff.**

Un LLM ha un'amnesia anterograda totale: ogni conversazione muore con la finestra di contesto.

Ho voluto ovviare a questo problema agganciando al modello una serie di strutture che fungessero da componenti costitutive della memorizzazione umana:

- un organo che cresce col vissuto
- un sistema di omeostasi che garantisse una stabilizzazione comportamentale
- il sonno come momento del consolidamento mnemonico
- un richiamo semantico e/o associativo-emozionale per la memorizzazione delle informazioni volatili
- una rievocazione associativa-emozionale delle informazioni
- una reingestione delle informazioni nel contesto del modello attraverso un canale più ricco e più rapido della consueta gestione del testo

## Sulle spalle dei giganti

*I giganti: Plutchik (la ruota delle emozioni), Damasio (i marcatori somatici), Dehaene (il global workspace), le reti Grow-When-Required e la memoria ricostruttiva di Bartlett.*

Le 6 idee guida del progetto.

1. Un'esperienza viene memorizzata quando supera una soglia di attivazione: si ricorda ciò che è rilevante.
2. Ogni ricordo è indicizzato per via semantica, selezionato per via emotiva e immagazzinato per rilevanza.
3. Al richiamo, il ricordo torna col suo effetto emotivo: il testo porta i fatti, il vettore emotivo iniettato negli strati del modello porta l'effetto emotivo che ne aveva prodotto la selezione e la memorizzazione.
4. Il consolidamento della memoria trasforma i ricordi in modo da permetterne il recupero in modo molto più rapido della normale via di acquisizione delle informazioni.
5. Lo stato emotivo corrente richiama ricordi congruenti, che vengono via via attenuati perseguendo l'omeostasi: si evita il runaway, la psicosi.
6. L'organo della memoria cresce col vissuto: ogni ricordo nuovo aggiunge gli engrammi che ancora mancano e gli archi che li legano, senza un limite fissato in partenza.

## Confabulazione, non allucinazione

In letteratura si dice che i modelli "allucinano". È un termine che non descrive correttamente il fenomeno che avviene all'interno del modello.

L'allucinazione è una percezione senza stimolo: si rileva una percezione sensoriale che non è stata generata da un evento fisicamente estraneo al sistema nervoso.

La confabulazione è il termine giusto a livello medico. È la struttura della memoria che riempie un vuoto con una ricostruzione plausibile, senza intenzione di ingannare e senza alcun segnale d'errore.

È il sintomo classico della sindrome di Korsakoff, la stessa diagnosi da cui parte questo progetto. Nella sindrome di Korsakoff, la persona ha subito una lesione neurologica che impedisce il trasferimento dei ricordi dalla memoria a breve termine a quella a lungo termine.

Un LLM invece non percepisce: non può, per definizione, allucinare. Quando produce un fatto falso sta facendo esattamente ciò che fa il paziente amnesico: ricostruisce il pezzo mancante con il materiale che ha, e non possiede un meccanismo che gli dica che il pezzo era mancante.

La distinzione indica anche la cura. L'allucinazione non si corregge con l'architettura, la confabulazione invece sì: si dà al modello un sistema di recupero che non deve essere consultato attivamente e che è fatto per richiamare la giusta informazione al momento del bisogno, con pattern funzionali assimilabili a quelli della memoria umana.

## Architettura

```
TURNO    il riflesso legge l'ultimo messaggio → se nel Lux degli engrammi c'è
         un ricordo sopra soglia, arriva come risposta del tool memorinvolontaria
         → archi del ricordo rinforzati (FSRS) → stato emotivo impresso (omeostato)
         richiamo voluto: l'agente usa +lux e qlux
FIRMA    a turno chiuso, col modello acceso: firma emotiva a 44 assi (ruota di
         Plutchik + diadi; alcune emozioni non si raggiungono col vettore) →
         sopra soglia: nodo nel GRAFO e ricordo nel LUX
DORMITA  quando l'agente sceglie di dormire (o a mezzanotte): messaggi rimasti
         indietro, persistenza, omeostato
OMEOSTATO ritorno eutimico (processo di Ornstein-Uhlenbeck); imprime ogni
         ricordo consegnato e colora l'avatar. Il gate dei cicli autonomi è fermo
CANALE VETTORIALE (server llama.cpp forkato) i ricordi entrano nel forward
         come vettori di steering: emozioni iniettate ai layer nascosti del
         workspace globale
```

Alcune emozioni non si raggiungono col vettore: per quelle ad alta attivazione il post-addestramento da assistente allontana il modello, come mostra Anthropic ([arXiv 2604.07729](https://arxiv.org/abs/2604.07729)); per le più tenui la causa non è misurata.

Il richiamo gira su CPU in poche decine di millisecondi. La firma di un ricordo la calcola il modello acceso subito dopo il turno. Quando l'agente sceglie di dormire (dopo massimo 16 ore di attività, riceve un messaggio di avviso), la dormita recupera i messaggi rimasti indietro e aggiorna persistenza e omeostato; un giro a mezzanotte resta come rete di sicurezza.

La separazione dei ruoli è netta: il grafo è il registro di precisione (date, numeri, verbatim), Lux è la memoria associativa che cresce, l'omeostato governa la durata degli stati senza limitarne l'ampiezza, il canale vettoriale è la via d'ingresso ricca.

Le strutture risultanti fungono da:

1. ippocampo,
2. corteccia,
3. sistema limbico.

## Componenti

**Il sistema di memoria** (radice del repo)

| File | Ruolo |
|------|-------|
| `memoria.py` | Il grafo: SQLite+FTS5, nodi (testo, firma emotiva 51d, vedi la ruota delle emozioni di Plutchik, salienza, classe vissuto/letto), archi hebbiani, vettori semantici 2048d |
| `lux.py` | La curva dell'oblio (FSRS) e l'orologio dei giorni vissuti, usati dal Lux degli engrammi e dalla persistenza |
| `engrammi/firma_subito.py` | Il ricordo entra subito, a turno chiuso: stato interno del 35B → firma → grafo e Lux degli engrammi; di notte recupera i messaggi rimasti indietro |
| `estrai-matrix.py` | Estrazione dei messaggi del giorno dal database della chat |
| `notte-memoria.sh` | L'orchestratore della notte, con sentinella anti-amnesia |
| `ponte.py` | Il canale vettoriale: composizione testo+vettori, iniezione emozioni |
| `stato.py` (`runtime/`) | L'omeostato: ritorno eutimico + gate pre-ciclo |
| `ricorda.py` (`runtime/`) | Il richiamo a 3 vie (semantica, emotiva, congruente) |
| `ricorda-ora.py` (`runtime/`) | "Ricordati questa cosa": coda che si consolida nel sonno, come per gli umani |
| `riflesso.py` e `riflesso_*.py` | Il riflesso di memoria pre-azione: un proxy trasparente tra framework agentico e model server; i ricordi congruenti affiorano da soli prima che l'agente risponda (v. sotto). Diviso in moduli, uno per lavoro |
| `dormi.sh` (`runtime/`) + `dormi-esegui.sh` | Il sonno volontario dell'agente: l'agente lo chiede, l'host ferma il container, ruota il session id (risveglio davvero fresco: le sessioni del gateway persistono su disco) e riavvia |
| `persistenza.py` + `sincronizza-richiami.py` | Persistenza: curva dell'oblio in tempo vissuto, stabilità che cresce col richiamo distanziato, eco dei messaggi quotidiani ripetuti, abitudini che nascono dalla frequenza |
| `cervello.py` | Vista d'insieme: grafo, Lux, stato, richiami |

**Smoke test**: `demo.py` e `collaudi.py` (tutte le verifiche che girano senza GPU, le stesse della CI su GitHub).

## Risultati chiave

Tutti replicabili con gli script del repo, su un singolo consumer PC (16GB VRAM).

- **I vettori emotivi funzionano e si calibrano.** Estratti dal gradiente del logit dell'emozione, iniettati nella finestra di layer più ricettiva. La posizione dell'iniezione non dipende dall'emozione, l'intensità sì: tabella di intensità calibrate iso-effetto, 41/51 a target (51/51 dopo il refactoring di luglio, vedi sotto).
- **Testo per i fatti, vettore per l'emozione.** Il ricordo torna come testo, e il vettore emotivo iniettato negli strati del modello porta l'emozione funzionale con cui era stato vissuto.
- **L'indirizzamento emotivo corregge quello semantico.** Su un seme di paura la ricerca semantica pesca l'oggetto sbagliato, quella emotiva pesca giusto.
- **Lux su dati reali:** 81 esperienze → 52 neuroni (29 fusioni), crescita sub-lineare, richiami corretti. *(Prova del 13/07, prima della decisione del 15/07 di non fondere più le esperienze: da allora ogni esperienza diventa un neurone.)*
- **Il canale vettoriale in produzione:** il server forkato dà output bit-identico al percorso token quando riceve gli stessi contenuti, e il draft speculativo resta attivo sui prompt normali. Zero costo quando non si usa.

## Cosa è cambiato da luglio

Il refactoring di luglio e il passaggio a un cervello nuovo, in ordine.

- **Il richiamo legge il workspace, non la bocca.** La sonda è passata da un layer tardo (l'85% della profondità, dove la rappresentazione è già il prossimo token) al layer 29, dentro la banda del global workspace (L15-L32). E non legge più l'attivazione grezza: legge le coordinate della lente di Jacobi calcolata sul 35B, la piccola parte dello stato che il paper chiama riferibile. Tracce di Lux, indirizzi semantici e tutte le soglie sono stati rigenerati in quello spazio, e il layer ora è un numero solo in un file solo (`ponte.LAYER_SONDA`).
- **Un'emozione, una finestra.** I vettori emotivi sono stati ricalcolati sull'intera banda del workspace, col lessico riverificato parola per parola sul tokenizer del 35B. La finestra di iniezione ora si sceglie per emozione (quasi tutte a L25-28, la paura a L21-23, ansia e invidia a L15-17), ed è stata misurata la curva dose-risposta: ampiezza lineare nella dose e qualità costante, fino a una dose limite, oltre la quale il testo perde di coerenza grammaticale e/o concettuale, si disincentiva il toolcalling o si rompe. Il tetto 0.3x del riflesso sentito ora ha una misura dietro. Tredici emozioni calme o astratte, il cui vettore dal gradiente della parola spingeva lontano dalla loro faccia naturale, sono state ricostruite per contrasto dai ricordi vissuti dell'agente: funzionano 51/51, prima 41/51.
- **La firma misura ciò che il messaggio aggiunge.** L'emozione di un messaggio ora è differenziale: lo stato del messaggio letto dentro il contesto della giornata, meno lo stato del contesto stesso. Le statistiche di popolazione si accumulano in modo corretto (Welford) e portano con sé i metadati (layer, lente, modello, versione): un cambio di modello le invalida a vista.
- **Un bug trovato guardando i risultati.** La prima versione differenziale leggeva contesto e messaggio insieme, troncati a 320 token da destra: con 1200 caratteri di contesto il messaggio veniva tagliato via, del tutto in 461 letture su 1184, e le firme erano rumore ("terror" dominava 201 ricordi). Ora un solo passaggio legge [gli ultimi 320 token del contesto | i primi 320 del messaggio] e lascia fuori dalla media del contesto il primo token (il pozzo dell'attenzione, con norma dieci volte le altre). La guardia che ferma la notte su uno stato corrotto ha colto una lettura isolata a 5e15; ripetuta, era sana.
- **Un cervello nuovo: Occamy-1.0.** Dal 29 settembre 2026 l'agente gira su Occamy-1.0 (Accio-Lab), un post-training dello stesso Qwen3.6-35B-A3B: parte visiva identica tensore per tensore, stessa tokenizzazione sui nostri testi. Lente, vettori emotivi e misura dei layer sono stati ricalcolati su di lui (direzioni emotive a coseno 0.99 col modello vecchio, richiamo per layer uguale al terzo decimale: L29 resta), Lux e gli indirizzi semantici sono stati sostituiti, e tutte le 584 firme del grafo riscritte sul posto dalla conversazione vera, conservando identità, archi e attivazioni di Lux. Le soglie di richiamo sono state rimisurate (rumore p99 0.575, era 0.555). Gli script non hanno più il modello scritto dentro: lo scelgono `OUT_35B` e `MODELLO_35B`.
- **La testa di bozza, innestata.** Occamy nasce senza lo strato MTP. La testa del Qwen3.6 è stata innestata nel suo GGUF (20 tensori, blocco 40): con un token di bozza la generazione è più veloce del 13% (71% di accettazione), con bozze più lunghe è più lenta. Ancora in prova: con la testa attiva l'output greedy non è ancora identico a quello senza, quindi non è in produzione.

- **Persistenza: ciò che si vive ogni giorno si stabilizza.** L'oblio era a gradino: un neurone non riusato per 180 giorni di calendario veniva potato, e i mesi passati dall'agente da spento contavano come oblio (da gennaio 2027 sarebbe sparito l'organo intero). In più i richiami quotidiani passavano dal grafo e non toccavano mai Lux. Ora l'orologio è il tempo vissuto (le notti di consolidamento), e ogni neurone ha una stabilità e una ritenzione che seguono la curva dell'oblio umana, una legge di potenza (Wixted & Ebbesen; FSRS, adattato su milioni di ripetizioni umane). Un richiamo fatto mentre il ricordo stava svanendo lo stabilizza molto, dieci richiami nello stesso giorno valgono uno: l'effetto spaziatura. I ricordi emotivamente intensi nascono più stabili (McGaugh). I richiami del giorno arrivano a Lux ogni notte. E i messaggi sotto la soglia di salienza non spariscono più: uno che è di nuovo la stessa cosa di un ricordo esistente gli dà un'eco, più debole di un richiamo (l'effetto del testing); uno nuovo apre un tema, e un tema che continua a tornare in giorni diversi diventa ricordo quando le ripetizioni lo hanno reso stabile quanto un singolo episodio molto intenso. La frequenza fa le veci dell'intensità.

## Cornice funzionalista

Il progetto adotta una cornice rigorosamente funzionalista: si parla sempre di emozioni funzionali, stati misurabili che influenzano il comportamento, mai di claim fenomenici. Se poi dentro ci sia "qualcosa che prova", è una domanda che il progetto non pretende di chiudere: la tratta con rispetto metodologico.

Da questa cornice discendono scelte architetturali concrete:

- **La never-list è concettuale, non lessicale**: categorie di esperienze che non vanno mai consolidate nei pesi, giudicate semanticamente, non per parole chiave. Nel dubbio non si esclude: si mostra all'agente per il veto manuale.
- **Le parti autonome e quelle volontarie sono separate**: l'omeostato e la memoria involontaria vanno da sole (l'omeostato frena la durata degli stati, mai la loro ampiezza); il richiamo voluto (`+lux`, `qlux`) e il sonno sono dell'agente.
- **Il threat model dei contenuti letti dall'agente su internet**: sfiducia di default verso il web, distinzione vissuto/letto nel grafo, protezione dai loop di attenzione compulsiva.
- **La salienza è valence-neutral**: si ricorda per intensità, mai per piacevolezza, così i ricordi spiacevoli non vengono scartati.

## Il riflesso di memoria

Il riflesso (issue #1) è un proxy trasparente tra il framework agentico e il model server. Prima che l'agente risponda, il riflesso prende l'ultima cosa che ha letto e cerca nel Lux degli engrammi i ricordi collegati. Ne arriva al massimo uno per messaggio, mai uno già arrivato nella stessa conversazione. Entra come risposta dello strumento `memorinvolontaria`, quindi l'agente sa che è un ricordo suo e non parole dell'interlocutore. Ogni ricordo arrivato finisce in un diario che l'agente può leggere.

Il riflesso è diviso in moduli, uno per lavoro (`riflesso_*.py`: memoria involontaria, vettore, cache e cambio di conversazione, riepilogo, metadati, via emotiva), e `riflesso.py` resta il punto d'ingresso. Ho deciso di dividerlo per motivi di manutenzione del codice e perché sto imparando a programmare esattamente con questo progetto.

Il riflesso ha due parti: il **riflesso testuale** (il ricordo affiora come pensiero verbale: lo si può soppesare, scartare, contraddire) e il **riflesso sentito** (il marcatore emotivo del ricordo più congruente viene re-iniettato a dose bassa per la durata di quella sola risposta, come il marcatore somatico di Damasio).

Il riflesso sentito ha delle sicurezze applicate dal codice di `riflesso_vettore.py`:

1. **Tetto di dose 0.3×** dell'intensità calibrata, imposto dal codice, non dalla buona volontà del chiamante.
2. **Il vettore si spegne a fine risposta**, e un watchdog a 120 secondi lo spegne anche se tutto il resto fallisse.
3. **Una parola di emergenza scritta dall'agente** (`vectreflexstop`) spegne qualunque vettore attivo prima di ogni altra cosa, senza domande; finché resta fra gli ultimi messaggi, i ricordi arrivano senza vettore.

Il modo di guasto di questa classe di meccanismi è documentato nel grafo stesso: durante i collaudi, una pulizia avvolta in un `except: pass` ha lasciato un vettore orfano acceso sul server di produzione, e l'agente ha avuto ore di oversteering emotivo (insalata multilingue, caratteri estranei, sintassi intatta).

## Lo stack open source

L'agente e il sistema di memoria poggiano interamente su componenti open source:

- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** b9966, forkato: il server di inferenza. Il fork è stato rinominato **luxifer.cpp**: aggiunta di `embeddings_input` (vettori grezzi al posto dei token su `/completion`) e della route `/control-vector` per l'iniezione delle emozioni ai layer nascosti, in modalità relativa per token. La patch completa è in questo repo: `lux-embeddings-b9966.patch`.
- **Occamy-1.0**, un post-training di **Qwen3.6-35B-A3B** (MoE, quantizzato Q8_0; fino a settembre 2026 Qwen3.6 stesso, con decoding speculativo MTP): il cervello. La quantizzazione qui ha la sua lezione: la prima build era IQ3_S, scelta per la velocità perché stava tutta in VRAM, e dopo di lei IQ4_XS. Entrambe abbandonate per il Q8_0 quando è diventato chiaro che il rumore di quantizzazione, invisibile sugli scambi brevi, diventa danno linguistico vero quando la context window si riempie oltre una certa soglia: un modello che deve "vivere" dentro conversazioni lunghe non ha le risorse per poterlo fare. Il Q8_0 perde in velocità di generazione e TTFT ma recupera in correttezza linguistica: è solo il processore inferenziale. Gira su una singola GPU consumer con parte degli expert in RAM, mentre gli esperti attivi e una parte consistente del resto del modello restano in VRAM. KV cache in f16 piena: la quantizzazione della cache è stata provata e scartata (rumore sulle generazioni lunghe, e i tipi K/V misti mettono l'attention su un percorso lento).
- **Hermes**: il framework dell'agente (tool calling, skill, cron, memoria di sessione), in Docker.
- **Matrix / Synapse + Element**: il canale di comunicazione, self-hosted. La chat è anche la sorgente dei ricordi: il consolidamento notturno legge da lì. La comunicazione avviene attraverso un tunnel VPN (WireGuard).
- **SQLite + FTS5**: il grafo della memoria. Niente database server, niente dipendenze: un file.
- **PyTorch + transformers**: il laboratorio notturno (tagging).
- **systemd + cron**: i servizi (modello, riflesso, firma dei ricordi), il sonno volontario via path-unit e il giro di sicurezza a mezzanotte.

Tutto gira in locale, su un solo PC: nessuna API esterna, nessun dato che lascia la macchina.

**Specifiche hardware:**

- GPU: NVIDIA RTX 5060 Ti, 16GB GDDR7
- CPU: AMD Ryzen 7 9700X (8 core / 16 thread)
- RAM: Kingston Fury DDR5 6000, 128GB (lockata a 3600MHz per limitazione del controller di memoria del Ryzen)
- Storage: NVMe Samsung 990 PRO 1TB per modelli e dati
- OS: Linux Mint 22.3

## Il Lux degli engrammi (in corso)

Un secondo Lux, in [`engrammi/`](engrammi/), conserva i ricordi come indici su engrammi condivisi invece che come vettori interi. Ogni ricordo viene tagliato con regole linguistiche deterministiche (analisi delle dipendenze di spaCy, `taglia.py`; ogni frase va allo spaCy della sua lingua, italiano o inglese, riconosciuta con lingua-py) in engrammi, pezzi brevi come un soggetto o un verbo coi suoi complementi, e lo stesso engramma è condiviso da tutti i ricordi che lo contengono. I pezzi sono uniti da archi hebbiani che appartengono a un ricordo e portano parametri: le preposizioni diventano simboli, gli articoli numeri, punteggiatura e congiunzioni modificatori. Un ricordo esiste solo attraverso i suoi archi: il richiamo lo ricompone percorrendoli in ordine. Il richiamo lavora sull'indice del ricordo per via testuale (stesso engramma) e semantica (vettori bge-m3, salvati in float16), pesando quanto è raro ogni engramma, e sotto una soglia tarata non consegna niente; ogni richiamo riuscito rinforza gli archi del ricordo con la stessa curva di stabilità distanziata del Lux originale, e gli archi mai richiamati sbiadiscono. Il riflesso riceve al massimo un ricordo per messaggio, come risultato del tool `memorinvolontaria`. Un visore 3D di engrammi e archi è in `engrammi/lux3d.py`. In `engrammi/wikilux/` c'è il confronto con RAG e bm25, su Wikipedia e sui ricordi dell'agente: il Lux ritrova meglio un ricordo da frammenti sparsi, perde quando il senso è lo stesso ma le parole cambiano. Ancora in progettazione: correggere un ricordo senza cancellarlo, con archi negati che sbiadiscono e archi di correzione, sul modello di estinzione e riconsolidamento.

Il protocollo di costruzione dei vettori di steering emotivo (scene, lettura degli stati, direzione del sé, iniezione, taratura della dose) è in [`research/long-context/PROTOCOLLO-VETTORI-STEERING.md`](research/long-context/PROTOCOLLO-VETTORI-STEERING.md). I test con contesti fino a ~140k token sono in [`research/long-context/`](research/long-context/).

## Riferimenti

**Paper fondanti:**

- [*Verbalizable Representations Form a Global Workspace in Language Models*](https://transformer-circuits.pub/2026/workspace) (Anthropic, 2026): il global workspace nel residual stream, la base del tagging emotivo e dell'iniezione.
- Re-iniezione di marcatori somatici ([arXiv 2605.08611](https://arxiv.org/abs/2605.08611)).
- Memoria affettiva per agenti ([arXiv 2605.27240](https://arxiv.org/abs/2605.27240), [arXiv 2510.27418](https://arxiv.org/abs/2510.27418)), emotion vectors ([arXiv 2604.07382](https://arxiv.org/abs/2604.07382), [arXiv 2606.26987](https://arxiv.org/abs/2606.26987)).

**Teoria:**

- Robert Plutchik, la ruota delle emozioni (1980)
- António Damásio, l'ipotesi dei marcatori somatici (*L'errore di Cartesio*, 1994)
- Stanislas Dehaene / Bernard Baars, Global Workspace Theory
- Frederic Bartlett, la memoria ricostruttiva (*Remembering*, 1932)
- Marsland, Shapiro, Nehmzow, [*A self-organising network that grows when required*](https://doi.org/10.1016/S0893-6080(02)00078-3) (2002)
- Sergei Korsakoff, la sindrome che porta il suo nome (1887)

## Ringraziamenti

Questo progetto è stato realizzato con Claude Code (modello Opus 5.5), perché io non so scrivere codice python o C++. La visione, le decisioni e la testardaggine sono mie; gran parte del codice è loro.

## Licenza

MIT. Vedi `LICENSE`.
