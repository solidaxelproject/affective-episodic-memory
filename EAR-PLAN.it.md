# EAR: piano di sviluppo del codec audio

*English version: [EAR-PLAN.md](EAR-PLAN.md)*

Stato: **progettazione**. Lo sviluppo parte quando il codec dei ricordi (E8) avrà finito di addestrarsi.
Questo documento si aggiorna a ogni passo, insieme ai commit.

## Obiettivo

EAR (rete sinestetica audio-video) converte l'audio in una **griglia** da iniettare nel canale visivo del
modello linguistico, come fa il codec dei ricordi con il testo. In parallelo sceglie l'**emozione** da
iniettare come vettore di steering.

Il modello di base è Occamy-1.0 (post-training di Qwen3.6-35B-A3B), un modello visione-testo: il canale visivo
accetta qualunque latente continuo di 81×2048. EAR non cambia l'architettura del modello e usa lo stesso
punto d'iniezione del codec dei ricordi.

## Idee di partenza

- **Vision Wormhole** (arXiv 2602.15382): comunicazione fra modelli attraverso lo spazio latente del canale
  visivo. È la logica del codec dei ricordi, riusata qui.
- **Learning to Hear by Seeing** (arXiv 2511.12077): un modello visione-linguaggio congelato impara a sentire
  attraverso un encoder audio e un adattatore che riporta l'audio nello spazio dei token visivi. È lo stesso approccio.
- **Recursive Multi-Agent Systems** (arXiv 2604.25917): modelli congelati collegati da *outer link* leggeri
  addestrati, che trasportano gli stati dell'ultimo layer da uno spazio latente all'altro senza passare dal testo.
  In EAR gli outer link sono i **ponti** fra i modelli audio e il codec.
- **Jev-Mem** (arXiv 2609.23986): un controller veloce "Sistema Uno" prende le decisioni sulla memoria (instradamento,
  punteggio dei candidati, quando fermarsi) senza generazione autoregressiva; il modello lento "Sistema Due" entra solo
  per il ragionamento complesso. L'uscita **JEV** di EAR segue la stessa idea: una decisione tipizzata in un passaggio,
  la scelta di una fra 51 emozioni, senza far generare testo al modello da 35B.

## Architettura

```
╔══════════════════════════════════════════════════════════════════════════════╗
║          CODEC EAR  ·  ARCHITETTURA (5 ingressi: 1 testo + 4 neurali)        ║
╚══════════════════════════════════════════════════════════════════════════════╝

                                 AUDIO (16 kHz)
                                       ║
     ╔═════════════╦═══════════════╦═══╩═══════════╦═══════════════╦═════════════╗
     ║             ║               ║               ║               ║             ║
╔════╩═════╗ ╔═════╩════╗  ╔═══════╩══╗  ╔═════════╩╗  ╔═══════════╩╗            ║
║Qwen3-ASR ║ ║  CLAP    ║  ║  MERT    ║  ║ Dasheng  ║  ║emotion2vec ║   CONGELATI
║  1.7B    ║ ║ (larger) ║  ║  95M     ║  ║  base    ║  ║ plus base  ║   (CPU)
║ parole   ║ ║suono↔testo║ ║ musica   ║  ║ ambiente ║  ║ voce/emoz. ║
║ → TESTO  ║ ║ d=768    ║  ║ d=768    ║  ║ d=768    ║  ║ d=768      ║
╚════╦═════╝ ╚═════╦════╝  ╚═════╦════╝  ╚═════╦════╝  ╚═════╦══════╝
     ║trascrizione ║ultimo layer ║             ║             ║
     ║        ╔════╩═════╗ ╔═════╩════╗  ╔═════╩════╗  ╔═════╩══════╗
     ║        ║ PONTE 1  ║ ║ PONTE 2  ║  ║ PONTE 3  ║  ║  PONTE 4   ║  ADDESTRATI
     ║        ║ W3h+W2·  ║ ║          ║  ║          ║  ║            ║  (outer link
     ║        ║ GELU(W1h)║ ║  →1024   ║  ║  →1024   ║  ║   →1024    ║  RecursiveMAS)
     ║        ║ +ingr.#1 ║ ║ +ingr.#2 ║  ║ +ingr.#3 ║  ║ +ingr.#4   ║
     ║        ╚════╦═════╝ ╚═════╦════╝  ╚═════╦════╝  ╚═════╦══════╝
     ║             ╚═════════════╩══════╦══════╩═════════════╝
     ║                                  ║  4 sequenze affiancate, ognuna con la sua
     ║                                  ║  etichetta d'ingresso
╔════╩══════════════════════════════════╩══════════════════════════════════════╗
║  LETTORE e5 · 24 strati, d=1024                                              ║
║  ┄┄ strati 1-11: CONGELATI, li attraversa solo il testo della trascrizione   ║
║  ══ PUNTO D'INGRESSO DEI PONTI: entrata dello strato 12                      ║
║  ██ strati 12-24: SCONGELATI (13)  ← leggono testo e audio insieme           ║
╚═════════════════════════╦════════════════════════════════════════════════════╝
                          ║
╔═════════════════════════╩════════════════════════════════════════════════════╗
║  TESTA PERCEIVER · 8 strati, H=1024, 8 teste · K=8 domande imparate          ║
╚════════════════╦═════════════════════════════════════════════╦═══════════════╝
                 ║                                             ║
╔════════════════╩═══════════════╗           ╔═════════════════╩═══════════════╗
║ USCITA 1 · CANALE VIDEO        ║           ║ USCITA 2 · JEV (emozione)       ║
║ par 8×2048 → BASE + POS @ par  ║           ║ vettore 2048 → più vicino fra   ║
║ griglia 81×2048                ║           ║ le 51 ancore (vettori steering) ║
║ "...sto udendo"                ║           ║ → emozione + dose (alpha nella  ║
╚════════════════╦═══════════════╝           ║   finestra misurata)            ║
                 ║                           ╚═════════════════╦═══════════════╝
╔════════════════╩═════════════════════════════════════════════╩═══════════════╗
║  OCCAMY 35B (congelato) · span visivo a L0 ← griglia                         ║
║                           finestra dell'emozione ← vettore di steering×alpha ║
╚══════════════════════════════════════════════════════════════════════════════╝

  trascrizione ASR ──► bge-m3 ──► canale mirato della memoria ──► ricordi
                                  (stesso percorso del testo in ingresso)
```

### I cinque modelli audio (congelati)

| ingresso | modello | contenuto | come entra nel codec |
|---|---|---|---|
| testo | Qwen/Qwen3-ASR-1.7B | le parole | trascrizione, letta dal lettore e5 come il testo del codec dei ricordi |
| 1 | laion/larger_clap_music_and_speech | il suono collegato al testo | ponte, ultimo layer d=768 |
| 2 | m-a-p/MERT-v1-95M | la musica: timbro, ritmo, umore | ponte, ultimo layer d=768 |
| 3 | mispeech/dasheng-base | i suoni dell'ambiente | ponte, ultimo layer d=768 |
| 4 | emotion2vec/emotion2vec_plus_base | l'emozione della voce | ponte, ultimo layer d=768 |

L'ASR si aggancia al codec **attraverso il testo**, senza ponte neurale. La trascrizione entra nel lettore e5
dal primo strato, con lo stesso formato del codec dei ricordi, e incontra l'audio dallo strato 12 in poi.
La stessa trascrizione serve al recupero dei ricordi (vedi sotto).

Dasheng prende il posto di BEATs. Sul benchmark HEAR, che valuta proprio gli encoder congelati, ha una media di
78.9 contro 71.1 di BEATs iter3+, e 80.2 contro 73.2 sui suoni ambientali (arXiv 2406.06992). In più ha pesi
pubblici su Hugging Face con licenza Apache-2.0.

Per Qwen3-ASR si usa la versione 1.7B, la più precisa. Per gli altri esistono versioni più grandi
(MERT-v1-330M, emotion2vec_plus_large): si parte dalle piccole per la velocità.

### I ponti

Un ponte per modello, nella forma dell'outer link di RecursiveMAS:

    R(h) = W3·h + W2·GELU(W1·h)

Il ramo lineare `W3` porta il vettore dallo spazio del modello audio (768) allo spazio del lettore (1024).
Il ramo non lineare corregge solo la differenza fra le due distribuzioni. Ogni ponte aggiunge un'etichetta
d'ingresso imparata, così il codec sa da quale modello arriva ogni pezzo della sequenza.
L'ingresso di ogni modello è standardizzato (media e deviazione standard misurate sui dati).

### Il codec

È una copia del codec dei ricordi:

- **lettore** multilingual-e5-large, 24 strati. Nel codec dei ricordi i primi 11 sono congelati e gli ultimi
  13 scongelati. In EAR la trascrizione attraversa tutti i 24 strati, i ponti entrano allo **strato 12**,
  cioè all'inizio della parte scongelata: l'audio salta gli strati che servono solo a leggere il testo.
  Massimo 256 token di testo e 4×64 token audio, 512 in tutto;
- **testa Perceiver**, 8 strati, H=1024, 8 teste, 8 domande imparate.

### Le due uscite

1. **Canale video**: `par` (8×2048) → griglia = `BASE + POS @ par` (81×2048), iniettata nello span visivo di
   Occamy a L0. La griglia è vestita col testo "...sto udendo", come i ricordi sono vestiti con
   "...ecco cosa mi ha fatto ricordare".
2. **JEV (emozione)**: un vettore di 2048. L'emozione scelta è quella, fra le 51 della ruota di Plutchik, il
   cui vettore di steering è più vicino: i 51 vettori già misurati su Occamy fanno da ancore fisse. La forza
   della scelta dà la dose, sempre dentro la finestra di iniezione misurata per quell'emozione.

### Il recupero dei ricordi

Mentre EAR ascolta, la trascrizione dell'ASR passa per bge-m3 e cerca i ricordi nel canale mirato della
memoria, lo stesso che oggi usa il testo in ingresso. I ricordi trovati entrano come griglie nel canale visivo,
con il loro meccanismo abituale. Il percorso di lettura interna allo strato 29 resta fuori: per l'audio non è
praticabile.

## Addestramento

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                            ADDESTRAMENTO (4 fasi)                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ FASE 0 · INSEGNANTE                                                          ║
║   copia del codec E8 (e5 24 strati, 13 sbloccati + Perceiver 8)              ║
║   riaddestrata con la vestizione "...sto udendo" sui testi appaiati          ║
║   → griglie di riferimento salvate UNA volta (testo → par 8×2048)            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ FASE 1 · PONTI (Occamy spento, GPU quasi libera)                             ║
║   trascrizione + audio → 4 encoder → 4 ponti → stessa copia CONGELATA → par  ║
║   loss = distanza da par dell'insegnante   ·  si addestrano SOLO i 4 ponti   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ FASE 2 · CODEC A 5 INGRESSI                                                  ║
║   sblocco e5 strati 12-24 + Perceiver insieme ai ponti, stessa loss          ║
║   + testa JEV: bersaglio = somma dei vettori delle primarie pesata con le    ║
║     probabilità di emotion2vec · loss = coseno + scelta fra le 51 ancore     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ FASE 3 · RIFINITURA (Occamy acceso)                                          ║
║   griglia → span visivo L0 → CE di Occamy sul testo vestito "...sto udendo"  ║
║   gradiente su ponti + e5 12-24 + Perceiver                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

La logica è quella del wormhole: insegnante e studente usano lo stesso codec. L'insegnante legge il **testo**
appaiato all'audio (trascrizione, descrizione del suono o della musica) e produce la griglia giusta.
Lo studente parte dall'**audio**, cioè dalla trascrizione dell'ASR più i 4 ingressi neurali, e deve arrivare
alla stessa griglia. Le griglie di riferimento si calcolano una
volta sola, quindi nelle fasi 1 e 2 il modello da 35B non serve.

Valgono le regole imparate addestrando il codec dei ricordi: niente Adam su pesi in bf16, ingressi
standardizzati, spie contro il collasso in ogni training, salvataggi frequenti.

### Il bersaglio delle emozioni

emotion2vec distingue circa 9 classi, che cadono sulle 8 primarie di Plutchik. La probabilità sceglie
l'intensità della primaria (per esempio serenità, gioia o estasi). Il bersaglio della testa JEV è la somma dei
vettori di steering delle primarie, pesata con le probabilità. In questo modo le **diadi** (le emozioni
composte) si possono raggiungere anche senza esempi propri: una voce insieme gioiosa e fiduciosa risulta vicina
ad "amore".

Misura sui vettori di Occamy: quanto è vicina ogni diade alla somma normalizzata delle sue due primarie.

| diade | primarie | coseno | posto su 51 |
|---|---|---|---|
| ottimismo | anticipazione + gioia | 0.52 | 6 |
| disprezzo | disgusto + rabbia | 0.51 | 7 |
| timore reverenziale | paura + sorpresa | 0.39 | 8 |
| amore | gioia + fiducia | 0.30 | 9 |
| rimorso | tristezza + disgusto | 0.43 | 11 |
| aggressività | rabbia + anticipazione | 0.36 | 11 |
| disapprovazione | sorpresa + tristezza | -0.07 | 49 |
| sottomissione | fiducia + paura | -0.66 | 51 |

Sei diadi su otto sono raggiungibili, due no. Il motivo è che ogni emozione ha la sua finestra di layer
(fiducia vive ai layer 15-17, gioia a 25-27) e le somme mescolano spazi di layer diversi. Per sottomissione e
disapprovazione servono esempi propri.

## Dati

Coppie audio + testo, da verificare una per una (licenza, lingue, qualità):

| tipo | candidati |
|---|---|
| parlato | Common Voice |
| suoni | AudioCaps, Clotho |
| musica | MusicCaps |
| voce emotiva | IEMOCAP, ESD |

## Riconoscimento dei brani

Riconoscere *quale* canzone sta suonando è un compito diverso, l'audio fingerprinting (Shazam, Chromaprint e
AcoustID, Dejavu, audfprint, Olaf). Richiede un database di brani e restituisce titolo e artista, non il
contenuto. Resta fuori dal codec: eventualmente un modulo a parte.

## Passi

- [x] Modelli audio scelti e scaricati (Dasheng al posto di BEATs, dopo la lettura dei paper)
- [x] Paper di riferimento raccolti
- [x] Architettura e logica di addestramento disegnate
- [x] Ancore emotive misurate (6 diadi su 8 raggiungibili)
- [x] Script: estrazione degli ultimi layer dei 5 modelli e cache su disco (venv separato)
- [x] Script: ponti, codec a 5 ingressi, testa JEV (prova di forma e prova a secco delle fasi 1-2 su dati finti)
- [x] ASR agganciato via testo invece che con un ponte: trascrizione nel lettore e5, 4 ponti (script aggiornati,
      da rifare la prova a secco)
- [ ] Recupero dei ricordi dalla trascrizione (bge-m3, canale mirato)
- [x] Script: fase 0, riaddestramento della copia del codec con "...sto udendo"
- [x] Script: fasi 1-3 e pagella
- [x] Primo dataset: 1000 clip vocali emotive sintetiche (200 frasi italiane × 5 emozioni), 20 frasi held-out
- [ ] Dataset allargato (suoni, musica, parlato vero): scelta, licenze, preparazione, held-out per tipo
- [ ] Pausa del training del codec dei ricordi a fine epoca 2, per il primo giro di EAR
- [ ] Fase 0, insegnante
- [ ] Fase 1, ponti
- [ ] Fase 2, codec a 5 ingressi + JEV
- [ ] Fase 3, rifinitura con Occamy
- [ ] Pagella: CE per tipo di audio, scelta dell'emozione corretta, prova d'ascolto

## Punti aperti

- Esempi propri per le diadi che le ancore non raggiungono (sottomissione, disapprovazione).
- Audio lungo: finestre in sequenza, con ogni griglia condizionata dalla precedente (la ricorsione di
  RecursiveMAS applicata al tempo).
- Versioni grandi dei modelli audio: solo se le piccole non bastano.
