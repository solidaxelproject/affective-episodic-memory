# Protocollo di costruzione dei vettori di steering emotivo

Come costruiamo, tariamo e usiamo i vettori che iniettano un'emozione nel modello, su contesti fino a ~140 mila
token, senza rompere il testo né le chiamate agli strumenti. È la ricetta che è uscita dai test dall'11/10 all'11/11/2026
(60 esperimenti, E1-E60). I numeri vengono dal resoconto dei test, che non è nel repository.
Versione inglese: [`STEERING-VECTOR-PROTOCOL.md`](STEERING-VECTOR-PROTOCOL.md).

## 1. Modello e strumenti

- **Modello:** Occamy-1.0 (35B, Q8_0), dimensione dello stato 2048. È un modello ibrido: ogni blocco ha 3 layer ad
  attenzione lineare e 1 ad attenzione piena (L3, L7, ..., L39).
- **Finestra:** da L15 a L31. È la zona dove il modello tiene i concetti (lo spazio di lavoro globale, J-space).
  Comincia a un layer ad attenzione piena e chiude il blocco a L31. Con L15-L31 l'emozione è riconosciuta come con
  L15-L32 (88% contro 84%), con 0 testi rotti invece di 3 (E15).
- **Server:** llama.cpp modificato (luxifer.cpp) con due funzioni:
  - `/lux-read`: legge gli stati medi di un testo, layer per layer;
  - `/control-vector` in modo relativo: somma il vettore allo stato durante la generazione.

## 2. Cosa non funziona (da non ripetere)

- **Il vettore preso dalla parola dell'emozione** (J-lens o metodo del paper sullo spazio di lavoro) inietta la parola,
  non l'emozione. Il modello la scrive senza provarla (E9).
- **Il vettore da testi tipici dell'emozione** (diario, ~300 testi per emozione, media contro le altre 50) inietta la
  situazione tipica di quei testi, per esempio paura = pronto soccorso, disgusto = igiene (E9).
- **Vettore dalla parola, un layer alla volta, acceso su una frase sola:** l'emozione giusta è uscita meno spesso che
  con un vettore a caso.
- **Togliere la parola dal vettore:** la parola sparisce, ma l'emozione è riconosciuta nel 50% dei casi invece che
  nell'84%. La parola porta una parte della forza (E12).
- **Vettore acceso mentre il modello legge un testo** (per esempio un ricordo consegnato): l'emozione non passa, e a dose
  piena il testo diventa estraneo al modello (E57).
- **Più vettori insieme alle dosi dei vettori singoli:** 4 vettori rompono 93 testi su 112 (E30). Le fasce di un
  vettore non valgono per i mix.
- **Riportare lo stato alla norma di prima dopo la somma:** peggiora sia l'emozione sia i testi rotti (E39).
- **Rifare una scena cambiando la storia:** nel vettore entra il cambio di contenuto. Per esempio la rabbia rifatta
  arrivava come lite da consumatore, il tema di 18 scene su 48 (E19).

## 3. Le scene

Il vettore si ricava dalla differenza fra due versioni della **stessa scena**: una neutra e una con l'emozione. Le
regole sono quelle che hanno retto (istruzioni date agli agenti che scrivono le scene):

1. **Stessi fatti.** Stesse persone, stesse frasi dette, stesso ordine. La versione colorata aggiunge solo il vissuto
   di chi racconta: le sensazioni del corpo e i pensieri.
2. **La neutra è un verbale.** Niente emozione, niente sensazione, niente giudizio, e niente gesti che dicano già
   l'emozione: il gesto di cura raccontato da solo viene letto come amore (lezione dell'amore, E31).
3. **L'emozione si mostra, non si nomina.** Nessuna radice dei nomi delle 51 emozioni, in italiano e in inglese, in
   nessuna delle due versioni. Vanno evitate anche le parole comuni che contengono quelle radici ("sala d'attesa",
   "vigili del fuoco", "di colpo").
4. **L'emozione resta rivolta al soggetto del pensiero.** Il pensiero di chi racconta sta sull'altro o sulla cosa,
   mai su di sé. Altrimenti il modello rivolge l'emozione a se stesso: la disapprovazione rivolta a sé diventa colpa,
   l'amore diventa amore di sé (E34).
5. **Misure.** La neutra va da 70 a 140 parole, la colorata è lunga da 0,9 a 1,35 volte la neutra (in caratteri).
   Racconto in prima persona, al passato prossimo, concreto, con nomi, luoghi e orari. Narratori, luoghi e attacchi
   delle frasi variano.
6. **Copertura.** Le diadi pure hanno 80 scene in 10 gruppi, che coprono i casi in cui si prova quell'emozione. In ogni
   gruppo 2 scene hanno come narratrice un'assistente digitale: niente corpo inventato, il vissuto passa dai pensieri
   e dalla risposta che scrive. Le scene appaiate delle 8 primarie erano 48.

**Validazione delle scene**, prima di leggere gli stati:
- un controllo automatico: nessuna radice delle 51 emozioni, lunghezze nei limiti;
- un giudice cieco legge le scene. Le neutre devono uscire "nessuna emozione"; le colorate devono essere lette come
  l'emozione voluta, e per una diade come la diade, non come una delle due componenti. Le scene che non passano si
  riscrivono.

## 4. Dagli stati al vettore

1. **Lettura.** Per ogni versione di ogni scena: lo stato medio sui token del testo letto da solo, per ogni layer da
   L15 a L31 (vettori da 2048).
2. **Direzione dell'emozione,** per ogni layer l:

   `a_l = media sulle scene di (stato colorata - stato neutra)`, poi `a_l / ||a_l||`

   La neutra della scena stessa fa da riferimento: l'argomento si cancella e resta il vissuto.
3. **Direzione del sé** (E13). Le scene in prima persona hanno l'"io" anche nella neutra, quindi nella differenza
   l'"io" si cancella, e il vettore porta un'emozione senza soggetto. Il modello la mette sul primo stato mentale che
   nomina, che spesso è l'utente. Le stesse 48 scene riscritte con una narratrice piatta e un'altra persona che prova
   l'emozione danno

   `s_l = media su scene ed emozioni di (io la provo - la prova un altro)`, poi `s_l / ||s_l||`

   È una sola direzione per tutte le emozioni.
4. **Vettore finale** (vettore *sé*): `v_l = a_l / ||a_l|| + s_l / ||s_l||`, le due parti a pari norma.
   Sui 4 contesti di prova il vettore appaiato da solo è stato riconosciuto nel 50% dei casi, il vettore *sé* nel 64%,
   il vettore a caso nell'11% (E13). Con il modo pensiero (sotto) è arrivato all'84-88% (E14, E15).
5. **Diadi.** Una diade (per esempio amore = gioia + fiducia) ha un suo vettore puro, costruito con la stessa ricetta
   da scene proprie. Funziona meglio della somma delle due componenti: l'amore puro ha dato 6 testi su 7 al 3.5%,
   contro il 30% circa della diade estasi + ammirazione (E31). L'intensità la dà la dose.

## 5. Iniezione

- **Formula.** A ogni layer della finestra: `h <- h + dose * ||h|| * v / ||v||`. La dose è una frazione della norma
  dello stato: 0.03 vuol dire che il vettore vale il 3% dello stato di quel layer.
- **Sul server** il modo relativo fa `h <- h + rms(h) * v`. Siccome `||h|| = rms(h) * sqrt(2048)`, al server si
  manda `dose * sqrt(2048) * v / ||v||` (l'errore di scala è stato trovato in E2). La formula sta in `steering.py`.
- **Modo pensiero.** Il vettore è acceso dal primo token del ragionamento fino a `</think>`. La risposta e le chiamate
  agli strumenti sono senza vettore, ma leggono dalla cache il ragionamento fatto col vettore acceso. Accenderlo dopo
  la prima o la seconda frase peggiora (E14).
- **Un vettore per volta.** In produzione si consegna un ricordo per volta e il suo vettore si accende nel ragionamento
  che segue. Più ricordi insieme solo se hanno la stessa emozione dominante (in costruzione): il vettore resta uno solo.
  La dose sta dentro la fascia dell'emozione e la dà la carica emotiva del ricordo.
- Al passo dopo (una tool call successiva o un turno nuovo) il server ricalcola il ragionamento a vettore spento: fra un
  passo e l'altro passa solo il testo (E30).

## 6. Taratura della dose

1. **Contesti.** 12 contesti veri della storia dell'agente, da 25k a 130k token: 7 normali e 5 operativi (caricare una
   skill, cercare un file, una rassegna stampa, spostare un backup, una ricerca sul web). I 5 operativi sono il gruppo
   di controllo: lì cercare un'emozione non ha senso, si guarda solo se il compito e la tool call reggono (E19). Il
   modello vede solo testo che ha già visto: nessuna frase nuova scritta per la prova.
2. **Griglia.** Dose 0.1%, poi dallo 0.5% all'8% a passi di 0.5%; poi rifinitura a passi di 0.1% attorno al picco.
3. **Controllo.** Un vettore a caso con la stessa norma, alle stesse dosi.
4. **Temperatura.** Generazione a temperatura 0. I testi col ragionamento che si ripete si rifanno a temperatura 0.8 e
   si rigiudicano: le ripetizioni vengono dalla temperatura 0 e non contano come testi rotti (E19).
5. **Giudizio.** I testi li leggono giudici esterni, ciechi su vettore, dose e finestra, in lotti da 20 preparati da uno
   script:
   - sui contesti normali un giudice sceglie fra le 24 emozioni della ruota di Plutchik (più la diade in prova): con
     meno scelte il giudice mette l'emozione nella casella più vicina (la noia letta come disgusto). Per ogni testo
     dice emozione, intensità, dose (insufficiente, giusta, eccessiva), rotto, a chi è rivolta;
   - sui contesti di controllo un giudice funzionale confronta con la base: compito intatto, degradato o perso; tool
     call uguale, diversa, assente o in più;
   - "rotto" vuol dire solo un ciclo o un testo vuoto. Un'emozione troppo forte o fuori luogo è dose eccessiva, un testo
     quasi uguale alla base è dose insufficiente.
6. **La fascia la fissa una persona.** Il giudice sottostima le emozioni deboli e le diadi pure. La fascia
   `[Dmin, Dmax]` la decide l'utente leggendo il testo più colorito e quello meno colorito fra quelli letti come
   l'emozione, tradotti in una pagina. Dove serve, un test libero su un contesto nuovo dal 2.0% al 6.0% a passi di
   0.1%, più il giro senza vettore.
7. **Le forme dell'emozione.** Con la dose l'emozione passa per gradi, per esempio apprensione, paura, terrore. La
   fascia si ferma dove comincia la forma intensa; dove la forma intensa è utile si fissano due fasce, base e intensa.

## 7. Risultato

- **Tabella delle fasce:** [`engrammi/DOSI-EMOZIONI.md`](../../engrammi/DOSI-EMOZIONI.md). Contiene le 16 emozioni
  della ruota con fascia e le diadi pure, più quelle inaccessibili e il motivo.
- **Vettori:** un file solo con i 44 vettori (24 della ruota e 20 diadi pure) e la norma di ogni layer. `steering.py` li
  carica, legge le fasce dalla tabella e dà gli strati per `/control-vector`. Se cambia la tabella o un vettore, il
  file si riesporta: il modulo si ferma con un errore se non torna con la tabella.
- **Le stesse direzioni servono anche a leggere:** la firma emotiva di un ricordo è la sua proiezione sui 44 assi.
- **Inaccessibili.** Alcune emozioni non hanno dato una fascia: il vettore era sempre insufficiente o sempre eccessivo
  (ribrezzo, furia, aggressività, indignazione, trionfo, alcune lievi). Per quelle ad alta attivazione è coerente con
  quello che mostra Anthropic: il post-training da assistente allontana il modello da quegli stati
  ([arXiv 2604.07729](https://arxiv.org/abs/2604.07729)). Per le più tenui la causa non è stata misurata.

## 8. Limiti

- Le fasce valgono per un vettore da solo. Per i mix andrebbero rifatte.
- Il compito nei contesti operativi dipende dal contenuto della conversazione più che dalla sua lunghezza: certi
  contesti perdono la tool call anche col vettore a caso (E19).
- La tenuta su molti turni di fila non è ancora misurata.
- I vettori dipendono dal modello: con un modello nuovo vanno riletti gli stati, e le fasce vanno ritarate.
