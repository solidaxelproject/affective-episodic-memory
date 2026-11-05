# La firma emotiva dei ricordi coi vettori del sé (B1-B7, 31/10-01/11/2026)

Documento di fine fase (regola del 22/10) del piano `PIANO-FIRMA-ENGRAMMI.md`. Numeri presi dal piano, dai file dei
risultati e dai test; dove un numero manca lo dico.

## 1. Obiettivo

Ogni messaggio della conversazione con l'agente (Occamy-1.0, 35B, GGUF Q8_0) riceve una **firma emotiva**: quanto
quel messaggio, letto nel suo contesto, sposta lo stato interno del modello lungo ciascuna emozione. La firma decide
se il messaggio diventa un ricordo (salienza sopra soglia), che emozione porta e quanto resiste all'oblio.

Fino al 31/10 la firma usava direzioni sbagliate e nasceva solo di notte. Il piano ha cambiato tre cose:
1. le **direzioni**: dai vettori della *parola* ai vettori del *sé*;
2. il **posto dell'emozione** nel Lux: dall'engramma all'arco;
3. il **momento**: il ricordo nasce subito, non nella notturna.

## 2. Cosa c'era prima

- Firma = stato del layer 29 (coordinate della lente di Jacobi) del messaggio letto dentro il contesto, meno lo stato
  del contesto, proiettato su 51 direzioni `emovec-18`, ottenute col gradiente sulla parola inglese dell'emozione.
- Le prove di steering di ottobre (RELAZIONE-STEERING.md, E3 ed E9) hanno mostrato che quelle direzioni spingono
  la *parola* ("joy"), non lo stato emotivo. Quindi la firma misurava quanto un messaggio somigliava alla parola.
- La firma di un engramma (frammento di ricordo) era la media dei ricordi che lo contengono.
- Il tagging spegneva il modello dell'agente ogni notte e leggeva col modello HF in bf16.

## 3. Metodo

### 3.1 Direzioni (B1)
24 assi = le 24 emozioni della ruota di Plutchik. Ogni asse ha un vettore unitario per strato, sugli strati 15-31:
- è il **vettore sé** dell'emozione: scene appaiate (stessa scena raccontata con e senza l'emozione) più la direzione
  del sé;
- la fonte di ogni asse è quella che ha dato la sua fascia di dose nelle prove (`vettori_firma.py`).

Gli 8 assi inaccessibili allo steering (ribrezzo, furia, accettazione, apprensione, distrazione, malinconia, noia,
fastidio) restano assi della firma: si leggono ma non si iniettano (D1).

### 3.2 Lettura (B2, B5b)
Firma differenziale, stessa idea della decisione 5-bis di luglio, così conta solo quello che il messaggio aggiunge:

  d_l = media(stati del messaggio letto dentro il contesto) - media(stati del contesto, senza il primo token)

Il primo token si toglie perché è il pozzo dell'attenzione (norma circa 10 volte più grande). Valore per asse:

  r_a = (1/17) Σ_{l=15..31} cos(v_a,l , d_l)

Il coseno toglie le norme diverse fra strati. Contesto = ultimi 320 token delle 24 ore prima; messaggio = primi 320
token. Senza contesto (primo messaggio): d_l = media del messaggio - μ_l, cioè la media di popolazione.

Il lettore è uno solo: il server dell'agente (luxifer, route `/lux-read`). Una modifica fatta per questo legge tutti gli
strati in una decodifica e restituisce somme in doppia precisione:
- 3 letture a firma invece di 34;
- **4.2 s invece di 71 s**.

### 3.3 Salienza e soglia (B3)
- z_a = (r_a - media_a) / sd_a, su una popolazione di **1662 messaggi veri**: i 644 ricordi più 1018 messaggi che non
  sono ricordi.
- Salienza = max_a z_a.
- Soglia scelta per **quota uguale** (D5): la firma vecchia a z ≥ 1.8 faceva diventare ricordo il 37.5% dei messaggi
  (225 su 600 messaggi di settembre). La soglia nuova che dà la stessa quota sul campione nuovo è **1.532**
  (quota misurata 0.3752).
- Non ci sono etichette "giuste": i ricordi di prima non fanno da esempi positivi (D5, l'utente).

### 3.4 L'emozione sull'arco (B4, Lux 1.13.0)
Nel Lux un ricordo è un insieme di engrammi legati da archi. Le scelte (D4) seguono il cervello:
- la valenza sta nel legame con l'amigdala, non nelle cellule dell'engramma (Redondo 2014);
- si accumula a ogni esperienza che riusa le stesse cellule (Cai 2016).

In pratica:
- ogni arco nasce con la firma del suo ricordo (matrice C, una riga per arco);
- la firma di un engramma è la media delle C dei suoi archi vivi.

### 3.5 Ricordo subito e behavioral tagging (B6)
1. A turno chiuso il proxy (riflesso) scrive in coda il messaggio dell'utente, preso prima delle aggiunte del proxy,
   e la risposta finale dell'agente.
2. Un servizio firma dal server vivo, crea il nodo e mette il ricordo nel Lux in pochi secondi.

**Behavioral tagging** (Frey e Morris 1997; Moncada e Viola 2007): un evento forte rende stabili anche le tracce
deboli vicine nel tempo. Nel cervello la cattura vuole anche il substrato condiviso: la traccia debole prende le
proteine della plasticità solo dove condivide cellule o sinapsi col forte, e l'emozione rafforza all'indietro solo i
ricordi legati (Dunsmoor 2015). Regola implementata (B6bis, dopo la prova del §4):
- candidato: messaggio scartato, non un link, entro 60 minuti prima o dopo un ricordo forte (salienza ≥ soglia + 1);
- **cattura** solo con sovrapposizione **parziale** degli engrammi: almeno il 25% degli engrammi del debole già nel
  forte (stessa chiave o coseno bge-m3 ≥ 0.8, la regola con cui il Lux accende gli engrammi) e almeno un engramma
  nuovo (un debole tutto contenuto nel forte è ridondante: separazione dei pattern);
- **stabilità graduale**: S0 del catturato = S0 propria × g, g = 0.25 + 0.75 × q × f, con q = quota in comune e
  f = forza del forte, da 1/3 (soglia + 1) a 1 (soglia + 3).

Finestra e "forte" vengono dalla letteratura sul ratto; quota minima e formula di g sono scelte nostre.

La notturna non spegne più il modello:
- rimette in coda solo quello che il proxy non ha passato;
- poi fa persistenza (eco e temi dei messaggi scartati) e omeostato.

### 3.6 Pulizia (B7)
- Un solo ordine dei 51 assi (emozioni.json).
- Un solo codice del ricordo (`codice_ricordo.py`).
- `emo_alpha` non si calcola più.
- Il registro del giorno si pota da solo.

## 4. Risultati

| Prova | n | Risultato | Controllo |
|---|---|---|---|
| Scene appaiate, 8 emozioni × 6 scene (B2) | 48 | l'asse giusto sale nella versione emotiva rispetto alla neutra 48/48; è il primo per salita 29/48 | a caso primo 2/48. Sono scene da cui vengono i vettori: prova segni e assi, non la generalizzazione |
| Fedeltà server Q8 contro HF bf16 (B2) | 10 messaggi veri | coseno 0.996-0.9999 su 9; 0.934 su 1 (11 token, firma debole 0.175, asse massimo al vicino) | atteso ≥ 0.99: test rosso, deciso un solo lettore (il server) |
| Stabilità numerica del lettore (B5b) | — | firma uguale alla lettura strato per strato entro 5e-4; lo stesso token in passaggi di lunghezza diversa varia fino a 5e-3 | si usa sempre lo stesso metodo e lo stesso lettore |
| Rifirma (B3) | 1662 voci | soglia 1.532, quota 0.3752 contro 0.375; 352/644 ricordi vecchi sotto la soglia nuova (restano tutti); emozione dominante cambiata in 599/644 | quota vecchia da 600 messaggi di settembre |
| Lux 1.13.0 contro 1.12.0 (B4) | 1000 indizi veri | stessi ricordi 1000/1000 (il richiamo non usa la firma) | ricomposizione di tutti i ricordi uguale |
| Soglie della persistenza (B5) | 644 ricordi | eco 1.35 (mediana 0.42), temi 0.84 (mediana 0.70), al 95° percentile contro gli altri ricordi | criterio del 30/09: eco falsa sotto il 5% |
| Selezione sulla chat vera (prova senzall'agente, server di prova) | 1583 messaggi, 1503 firmati | ricordi per soglia 41% (617), quota per giorno 0.30-0.57 (mediana 0.41, 27 giorni); col trascinamento a solo tempo i trascinati erano il 38% (574): 79% di ricordi in tutto | scartati 21% |
| Cattura per sovrapposizione (stessi dati) | 580 deboli entro 60 min da uno dei 91 forti | con quota ≥ 25% e un engramma nuovo: 115 catturati (96 a 30 min, 72 a 15 min); con almeno 1 engramma in comune ma senza quota: 436 | 1 solo debole del tutto ridondante |
| Ricordo subito (B6), stress-test | 200 messaggi da 4 scrittori | tutti firmati nell'ordine della coda, 2.2 s con firma finta; kill -9 a metà: nessun doppione, tutto nel Lux | modello spento, lettore diverso, righe rotte, notturna in contemporanea |
| Richiamo per emozione dopo B7 | 10 emozioni × 10 ricordi | stessi ricordi nello stesso ordine, punteggi entro 1e-4 | prima e dopo la migrazione, su copia |

Il 37.5% di quota è una scelta di continuità, non una misura di qualità. Dice solo che passa la stessa quantità di
messaggi di prima.

## 5. Limiti

- **Nessuna verità di riferimento sulla firma dei messaggi veri.** La prova delle scene (48/48) è dentro il campione
  da cui nascono i vettori; il resto poggia sulle prove di steering dei vettori sé. Non c'è un confronto con giudizi umani sui messaggi dell'agente.
- **Un lettore solo, quantizzato (Q8).** Su un messaggio corto e debole la firma Q8 si allontana da quella bf16
  (coseno 0.934). La soglia è tarata sullo stesso lettore, quindi il sistema è coerente con se stesso.
- **Statistiche fisse** (B3): se la conversazione cambia molto, la quota che passa la soglia cambierà. Va misurata.
- **Cattura tarata solo in parte**: finestra e "forte" vengono dal ratto, quota 25% e formula di g sono scelte nostre.
  La prova misura quanti deboli entrano (115 su 580), non se sono quelli "giusti".
- **La dominante è cambiata in 599 ricordi su 644**: tutta la memoria vecchia ha cambiato emozione. È quello che si
  voleva (D5), ma non c'è un controllo esterno su quale delle due sia "giusta".
- L'omeostato riceve firme a 24 assi su uno stato a 51: gli assi fuori dalla ruota scendono verso 0. Si rivede con D7,
  nella fase 2.
- Il proxy alla consegna di un ricordo inietta ancora coi vettori vecchi (emo-cvec-v2) fino alla funzione dose della
  fase 2 (D7).

## 6. Stato e prossimi passi

- In servizio: firma nuova in memoria.db, Lux 1.13.0, persistenza sul Lux degli engrammi, addr_emo a 51 assi.
- In servizio dal 01/11 sera: unit `firma-subito`, proxy riavviato, cattura per sovrapposizione (servizio del Lux
  riavviato). Manca solo l'avvio del modello col binario nuovo.
- Pulizia dei ricordi (01/11 sera): tolti 3 messaggi di sistema finiti fra i ricordi; 20 ricordi di luglio avevano il
  ragionamento dell'agente davanti alla risposta (firma falsata): ora solo la risposta, firma rifatta. 641 ricordi.
- Prima della fase 2 mancano altri preliminari: prova di accumulo, vettore "just do it" verso la tool call,
  controllo delle diadi, le 27 emozioni fuori dalla ruota.
- Fase 2 (PIANO-LUX-FASI-v1.12.md): funzione dose dalla firma degli engrammi, carica differenziata fra gli archi di
  uno stesso ricordo (Kensinger 2009), proxy sui vettori sé (D7).
- Da misurare al primo giorno vero: quanti messaggi diventano ricordo, quanti ne trascina il tagging, tempo fra la
  risposta e il ricordo nel Lux.
