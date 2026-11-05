# Piano: firma degli engrammi rifatta e ricordi nel Lux subito (31/10/2026, v1 del 01/11)

Ordine dell'utente (31/10): ricostruire il sistema di firma degli engrammi; un ricordo entra nel Lux subito, senza
aspettare la notturna; riprocessare tutti gli engrammi col sistema nuovo. Prima la situazione oggettiva del codice,
pulizia delle ridondanze, poi il piano. Decisioni D1-D7 prese dall'utente il 31/10; l'esecuzione segue la skill di upgrade (backup, poi codice, poi test).

## 1. Situazione oggi (verificata sul codice il 31/10)

### Dal messaggio all'engramma
1. Cron 00:00 o `notturna` -> `notte-memoria.sh` (guardia 6 ore sul marker `.ultimo-consolidamento`).
2. `estrai-matrix.py` estrae la chat del giorno; l'agente va a dormire (`.dormi-richiesto`).
3. `sincronizza-richiami.py`: i richiami del giorno nel VECCHIO Lux (`workspace/memoria/lux.npz`).
4. `run-tagging.sh` FERMA il 35B e lancia `tagging35b.py` col modello HF su GPU:
   - firma = stato a L29 in coordinate lente del messaggio letto dentro il contesto (ultimi 1200 caratteri)
     meno lo stato del contesto (`leggi_differenziale`, riga 143);
   - proiezione sulle 51 direzioni di `out-occamy/emovec-18.pt` (gradiente sulla PAROLA inglese, riga 195);
   - z-score sulla popolazione (`stats-emo-v2.pt`, Welford, riga 388); salienza = max z; sotto 1.8 il messaggio
     si scarta (salvo `[ricordare]` e coda ricorda-ora);
   - `memoria.add_node` -> `memoria.db` (firma json, emo_tag = asse massimo, emo_alpha, salienza) + `vettori.pt`;
   - poi: vecchio Lux (`alimenta_lux`), omeostato (`stato-emotivo.json`), persistenza (eco e temi sul vecchio Lux,
     nodi "abitudine"), sidecar `addr-sem.npz`.
5. `lux_engrammi.py aggiungi`: taglia i ricordi nuovi in engrammi (taglia.py), vettori bge-m3 (:8094), salienza;
   F di un engramma = MEDIA delle firme dei ricordi che lo contengono (righe 220, 272). Il servizio :8132
   ricarica da solo quando cambia `lux-meta.json`.

### Chi usa la firma
- `nodi.emo_tag`: il riflesso, alla consegna di un ricordo, inietta quell'emozione coi VECCHI vettori
  `emo-cvec-v2.npz` alla loro dose "centro" (`riflesso.py:537`, `ponte.dirs_emozione`). Il lavoro di ottobre
  (vettori sé, fasce dell'utente) in produzione non c'e' ancora: arrivera' con la funzione dose della fase 2.
- `nodi.firma`: `ricorda.py` dell'agente (richiamo emotivo e congruente), omeostato, stabilita' iniziale degli archi del
  Lux degli engrammi (`s0_ricordi`), F.
- F del Lux degli engrammi: oggi solo il colore in lux3d. Il richiamo non lo usa ("via emotiva assente").
- `emo_alpha`, `nodi.salienza`: nessun uso in produzione (solo grafo3d).

### Cosa non va
- Le direzioni della firma sono quelle della parola (E3 ed E9 della relazione: spingono la parola, non l'emozione).
  Gli assi delle diadi (amore, sottomissione...) sono parole a se', non la somma dei petali.
- F non e' la firma dell'engramma: e' la media dei ricordi che lo contengono.
- La firma nasce solo di notte, col 35B spento.

## 2. Pulizia

Fatta oggi (backup `.bak-pre-firma-3110`):
- `PIANO-MANUTENZIONE.md` corretto in 7 righe (lux-engrammi attivo, aggancia-appunti dormiente, chi importa chi,
  dati di tagging35b, unit della prova per layer sparita).
- `stats-popolazione.pt` (radice e workspace, nessun lettore) in `archivio-firma-3110/`.

Da fare DENTRO il refactoring (il codice che toccano si riscrive comunque):
- P1 `aggiorna_sidecar` e `addr-sem.npz`: la via semantica del riflesso non esiste piu', lo legge solo un attrezzo.
- P2 `emo_alpha`: nessun lettore; resta la colonna in memoria.db, non si calcola piu'.
- P3 tre ordini dei 51 assi (dict di emovec, emozioni.json, alfabetico): uno solo, quello di `emozioni.json`.
- P4 `codice(ts)` copiato in lux_engrammi.py:72, riflesso.py:551, ricorda.py:39: una sola funzione
  (ricorda.py gira nel container: resta la sua copia, con un test che le confronta).
- P5 la firma ricostruita tre volte in tagging35b.py (239, 275, 301): una funzione.
- P6 la sentinella di notte-memoria.sh controlla il vecchio lux.npz: va sul Lux degli engrammi.
- P7 il vecchio Lux (`lux.py`, classe Lux): scritto ogni notte, letto solo da persistenza (eco e temi). Vedi D6.

## 3. Il sistema nuovo

### Firma
- Direzioni = i vettori sé in uso per ogni emozione (sé-medio, sé-interno, sé-esterno, sé-nuovo, sé-proprio, come in
  `DOSI-EMOZIONI.md` e `pagina_dosi.py`), raccolti in UN file `out-occamy/vettori-firma.pt` con l'emozione, la fonte
  e l'ordine di `emozioni.json`.
- Lettura dal server vivo: `/lux-read` di luxifer esiste gia' (contesto dedicato, non tocca la generazione, 0.3-0.4 s)
  e con `per_token` separa i token del contesto da quelli del messaggio. Firma differenziale come oggi (messaggio
  dentro il contesto meno il contesto), proiettata sulle direzioni sé.
- z-score sulla popolazione, statistiche nuove (file nuovo, coi metadati delle direzioni).
- Le diadi non sono assi: escono dalla concomitanza degli assi della ruota nel profilo (31/10) e la gerarchia
  della fase 2, punto 7, sceglie cosa si inietta.

### Ricordo nel Lux subito
- Dopo ogni turno chiuso il riflesso (che vede gia' i messaggi) manda il messaggio a un passo nuovo: firma da
  `/lux-read`, salienza, sopra soglia nodo in memoria.db e `lux_engrammi._aggiungi` sul solo ricordo nuovo; il
  servizio :8132 ricarica. Fuori dal percorso della risposta (in coda, mai prima della risposta all'utente).
- Di notte restano: omeostato, persistenza, SHY, oblio, orologio vissuto. Il tagging su GPU col 35B spento sparisce.
- Collegamento col riepilogo della cache (riflesso.py:281-421, in produzione; ultima promozione nel diario fallita
  con "Connection refused"): con i ricordi gia' nel Lux, il cambio di cache a CW piena non deve aspettare la notte.

### Riprocessare tutto
- Precedente: `firme-occamy/ricalcola-firme.py` (29-30/09) ha rifirmato i 584 nodi col contesto della chat vera
  (`chat-completa.jsonl`), con backup e `--dry`. Si riusa lo stesso schema con le direzioni nuove.
- 644 nodi in memoria.db (642 vissuti, 2 letti). Poi ricostruzione del Lux degli engrammi in una versione nuova
  (`lux-1.13.0`: MINOR, archi e rinforzi restano, si aggiunge la carica per arco; vedi B4), la 1.12.0 resta.

## 4. Decisioni dell'utente

- D1 DECISA (31/10): le inaccessibili (ribrezzo, furia, accettazione, apprensione, distrazione, malinconia,
  noia, fastidio) "restano come assi ma non si iniettano": assi della firma col loro vettore sé, escluse
  dall'iniezione (la funzione dose della fase 2 le salta).
- D2 DECISA (31/10): firma sui 24 assi della ruota. Delle 27 fuori, 23 sono diadi di Plutchik (8 primarie + 15
  secondarie/terziarie: colpa, curiosita', disperazione, invidia, cinismo, orgoglio, speranza, diletto, tenerezza,
  vergogna, indignazione, pessimismo, morbosita', dominanza, ansia): si leggono come concomitanza delle componenti e si
  iniettano coi vettori delle componenti; se un'emozione non c'e', si inietta la piu' vicina. Non diadi: trionfo,
  purificazione, sgomento, gelosia: anche queste come MIX VETTORIALE (31/10): trionfo = estasi + un po' di
  rabbia (dall'orgoglio); purificazione = serenita' + fiducia (il petalo opposto al disgusto); sgomento = stupore +
  paura (soggezione intensa); gelosia = rabbia + paura + tristezza (rabbia e paura opposte: emozione in conflitto).
  Proporzioni del mix: dalla firma, come per le diadi.
- (testo originale di D2) Le 27 fuori dalla ruota (trionfo, dominanza, purificazione... diadi comprese: oggi sono l'asse dominante nel 56% dei
  19.501 engrammi):
  fuori dalla firma finche' non hanno un vettore sé, o tenute dalla firma vecchia intanto?
- D3 DECISA (31/10): lettura dal 15 al 31, gli strati dell'iniezione; per strato la proiezione sul vettore sé
  di quello strato, poi media sui 17 strati. `/lux-read` legge uno strato per chiamata e serve leggere contesto e
  contesto + messaggio: 34 chiamate (~12 s per messaggio, misura del B2), fuori dal percorso della risposta.
- D4 Firma dell'engramma: media dei ricordi che lo contengono (come oggi) o firma del frammento stesso, letto dentro
  il suo ricordo (differenziale: frammento nel ricordo meno il ricordo)?
- D5 DECISA (l'utente 31/10, "va bene la tua proposta"): (1) firma nuova su ~2000 messaggi veri di chat-completa.jsonl
  (come il 29/09) -> statistiche di popolazione nuove; (2) soglia nuova = quella che fa passare la STESSA QUOTA di
  messaggi del campione che passava con la firma vecchia (1.8 su 51 assi). Nessuna lettura dei dissensi (l'utente: "la
  firma giusta e' quella nuova fatta coi vettori funzionanti"). I 644 ricordi di oggi NON fanno da esempi giusti.
- D7 DECISA (31/10): il vettore del riflesso alla consegna passa ai vettori sé nella fase 2 (funzione dose),
  segnato in PIANO-LUX-FASI-v1.12.md fase 2 punto 10. Fino ad allora il riflesso resta coi vettori emo-cvec-v2.
  BEHAVIORAL TAGGING (l'utente 31/10, Moncada e Viola 2007; Frey e Morris 1997): un messaggio sotto soglia vicino nel tempo
  a uno forte entra lo stesso, piu' debole (S0 piu' basso). Nel ricordo subito: i messaggi scartati di recente restano
  in una coda; quando arriva un messaggio forte entrano quelli della coda dentro la finestra prima, e per la finestra
  dopo entra anche chi arriva. Da decidere con l'utente al codice: soglia del "forte", ampiezza della finestra (nei ratti
  circa un'ora prima e dopo), S0 dei ricordi trascinati.
- D5 (testo originale) Soglia del ricordo: oggi salienza 1.8 sulla firma vecchia. Con gli assi nuovi va ritarata: su cosa (i 644
  nodi di oggi come positivi e un campione di messaggi scartati come negativi)?
- D6 DECISA (31/10): "il vecchio lux si archivi e non venga piu' usato, si usa il nuovo, punto". Il vecchio
  Lux (classe Lux di lux.py, workspace/memoria/lux.npz) va in archivio; persistenza (eco, temi, abitudine) e
  sincronizza-richiami passano al Lux degli engrammi; di lux.py restano solo le funzioni FSRS e l'orologio vissuto.
- D4 DECISA (31/10): "l'emozione sull'arco". Alla nascita ogni arco di un ricordo prende la firma del ricordo
  (24 assi); la firma F di un engramma = somma pesata delle cariche dei suoi archi. ROVESCIA la fase 2 punto 2
  (PIANO-LUX-FASI-v1.12.md: la carica dell'arco nasceva dalla F dei suoi due engrammi): da correggere li' al momento
  della scrittura del codice. Carica differenziata fra gli archi dello stesso ricordo (centrali contro contorno,
  Kensinger 2009): resta alla fase 2.
- D4, nota del 31/10: nel cervello la valenza non sta nelle cellule dell'engramma ma nel loro legame con l'amigdala
  (Redondo 2014), si accumula a ogni esperienza (Cai 2016, ricordi che condividono cellule) e si riscrive al
  richiamo (Nader 2000). Proposta: emozione sull'arco (carica per arco, fase 2), firma dell'engramma = somma pesata
  delle cariche dei suoi archi, non media dei ricordi.
- D7 `nodi.emo_tag` per il riflesso: fino alla funzione dose della fase 2 il riflesso inietta coi vettori vecchi
  emo-cvec-v2. Si lascia cosi' fino alla fase 2, o emo_tag passa subito ai vettori sé con la dose a meta' fascia?

## 5. Blocchi di lavoro (regola di 31/10: backup PRIMA di ogni blocco, test di verifica DOPO ogni blocco)

Regole per tutti i blocchi (01/11: "i test passati sono il trigger del blocco successivo"; i test devono testare
per davvero, devono essere STRESS-TEST):
- Si va avanti da soli: test verde = blocco successivo, senza chiedere. Test rosso = ci si ferma, si cerca la causa
  (mai allentare il test per farlo passare) e lo si dice all'utente.
- Stress-test: oltre al caso normale, i casi peggiori veri (testi strani, limiti, raffiche, concorrenza, crash a meta',
  servizio giu', dati gia' presenti), ognuno con un assert. Elenco minimo per blocco qui sotto.
- Restano all'utente solo le sue regole fisse: accendere/spegnere llama-35b (l'agente) e riavviare il riflesso. CC prepara,
  avvisa e aspetta solo su quei due passi.
- Backup: `~/.claude/skills/upgrade/backup.sh` prima dei blocchi che toccano produzione (B3-B7); copia
  `.bak-pre-<blocco>-<data>` di ogni file prima di modificarlo, in tutti i blocchi.
- Test: ogni blocco ha il suo `test_*.py` (assert, niente framework), che finisce con "TUTTO VERDE".
- GPU: i passi col modello HF girano solo con llama-35b spento (lo spegne l'utente) e la GPU libera; il server di prova
  8098 lo accende CC solo a GPU libera, come la pagina del confronto.
- Nessuna stringa nuova davanti al modello: la firma legge, non genera.

### B1. Vettori della firma (CPU, niente produzione)
- [x] FATTO 01/11: `vettori_firma.py` -> `out-occamy/vettori-firma.pt`, `test_vettori_firma.py` TUTTO VERDE.
- Script `engrammi/vettori_firma.py` -> `out-occamy/vettori-firma.pt` = {"assi": 24 nomi inglesi nell'ordine di
  emozioni.json, "fonte": {asse: fonte}, "vettori": {asse: {strato: vettore unitario 2048}} per gli strati 15-31}.
- Fonti (quelle delle fasce): gioia, fiducia, paura, sorpresa, tristezza, disgusto, rabbia = sé-medio; attesa,
  vigilanza (vettore vecchio, quello della diade), accettazione, apprensione, distrazione, noia, fastidio, interesse =
  sé-nuovo; serenità, malinconia = sé-esterno; estasi, ammirazione, cordoglio = sé-interno; terrore, stupore,
  ribrezzo, furia = sé-proprio.
- Stress-test `engrammi/test_vettori_firma.py`: 24 assi, ognuno con gli strati 15-31, norma 1 (+-1e-4); ogni vettore uguale
  (coseno > 0.9999) a quello che `confronto.py` / `sistema.strati` usano per la stessa emozione; nessun asse fuori
  dalla ruota.

### B2. La funzione di firma (CPU + server, niente produzione)
- [x] FATTO 01/11: `firma_se.py`, `test_firma_se.py` TUTTO VERDE (20 messaggi veri, testi strani, contesto vuoto e
  lunghissimo, determinismo, server giu' e morente; scene: asse giusto piu' alto 48/48, primo per salita 29/48, a caso
  2/48). Corretto: contesto con spazio finale (fondeva col "\n": niente prefisso) -> `rstrip`. Tempo: 71 s a firma
  (34 letture da 1-1.7 s) -> B5b. Fedelta' server (Q8) contro HF (bf16), `test_fedelta_hf.py`: ROSSO, coseno 0.996-
  0.9999 su 9 messaggi, 0.934 sul 208 (11 token, firma debole 0.175; asse massimo al vicino). DECISO (l'utente "come
  ritieni piu' opportuno"): un solo lettore per tutto, il server col GGUF dell'agente; B5b prima di B3; B3 rifirma dal
  server di prova; `firma_hf` non si usa (resta per il confronto). Dati: fedelta-server.json, fedelta-hf.json.
- Modulo `engrammi/firma_se.py`:
  - `proietta(stati)`: stati = {strato: vettore 2048 della differenza messaggio - contesto} -> 24 valori =
    media sui 17 strati del coseno fra la differenza e il vettore dell'asse (il coseno toglie le norme diverse fra
    strati);
  - `firma_server(contesto, messaggio, url)`: per ogni strato 15-31 due letture `/lux-read`: il contesto con
    `per_token` (fino a 512 token: si toglie il primo, il pozzo dell'attenzione, come tagging35b) e contesto + "\n" +
    messaggio senza `per_token` (media x n_tokens = somma); somma del messaggio = differenza delle somme, diviso i suoi
    token. 34 letture, circa 12 s a messaggio. ponytail: una lettura per strato; se serve piu' velocita', una
    modifica a luxifer che legga piu' strati nella stessa chiamata;
  - `firma_hf(modello, contesto, messaggio)`: la stessa cosa col modello HF (un forward, ActivationRecorder sugli strati
    15-31, stessa ricetta di `leggi_differenziale`), per la rifirma di tutto (B3).
- Test `engrammi/test_firma_se.py` (CPU): `proietta` su stati finti uguali a un vettore dell'asse -> quell'asse a 1 e
  gli altri al loro coseno; i token di "contesto" sono un prefisso di quelli di "contesto\nmessaggio" (`/tokenize`,
  su 20 testi veri: se no la differenza delle somme non vale). Stress: emoji, apostrofi italiani, codice, URL,
  testo inglese, contesto vuoto (primo messaggio del giorno: messaggio - mu come oggi), contesto oltre 512 token
  (taglio), messaggio di un solo token, 100 chiamate di fila (nessun errore, stessi numeri: lettura deterministica),
  server giu' a meta' (errore chiaro, nessuna firma a meta').
- Test di fedelta' server contro HF (GPU, li lancia l'utente in due tempi, perche' 16 GB non tengono tutti e due): 10
  messaggi veri; prima col server di prova (8098), poi col modello HF a server spento; atteso coseno fra le due firme
  >= 0.99 e stesso asse massimo in almeno 9 su 10 (come la fedelta' 0.99 del 16/07).

### B3. Rifirma di tutti i ricordi e soglia nuova (GPU per la lettura, CPU per la scrittura)
- [x] FATTO 01/11: `ricalcola-firme-se.py`, `test_firme_se.py` TUTTO VERDE. Chat rietratta (chat-completa-0111.jsonl,
  fino al 24/10: la vecchia finiva al 26/07, 39 nodi senza contesto). Voci 1662 (644 nodi + 1018 messaggi non nodo: la
  chat intera non arriva a 2000), 8 senza contesto (messaggio - mu, mu = media dei messaggi letti da soli). Quota
  vecchia 0.375 (225/600 di settembre con z >= 1.8) -> SOGLIA NUOVA 1.532 (quota 0.3752 sul campione). Nodi: salienza
  p50 1.44, 352/644 sotto la soglia nuova (restano tutti); dominante cambiata 599/644. Scritti firma (24 assi z),
  emo_tag, salienza in memoria.db + addr_emo in vettori.pt (coerenza con memoria.py); emo_alpha non toccato (P2).
  `stats-firma-se.pt` coi metadati. Backup .bak-pre-firme-se-20261101-145535. Corretto in `firma_se.py`: contesto che
  comincia con un carattere in piu' token (emoji 🔐) -> il carattere si toglie (1 voce; test di B2 con i casi nuovi
  verde). 5.2 s a voce.
- ORDINE CAMBIATO 01/11: B3 dopo B5b, e la lettura e' quella del server (firma_server col server di prova 8098, stesso
  GGUF dell'agente), non HF.
- Script `firme-occamy/ricalcola-firme-se.py`, stesso schema di `ricalcola-firme.py` (29-30/09):
  - `--leggi` (server di prova 8098 a GPU libera, l'agente spenta, con ripresa): i 1184 messaggi gia' letti a settembre
    (`letture-v3.pt`: 584 nodi di allora + 600 messaggi non nodo) + i nodi nati dopo + altri messaggi di
    `chat-completa.jsonl` fino a circa 2000 -> `letture-se.pt`;
  - `--scrivi` (CPU): statistiche nuove `stats-firma-se.pt` (con metadati: assi, strati, fonti); quota vecchia = quota
    dei 600 messaggi non nodo con z vecchio >= 1.8 (da `letture-v3.pt` e `stats-emo-v2.pt`); soglia nuova = quantile
    che da' la stessa quota sul campione nuovo; riscrive in `memoria.db` firma (24 assi), emo_tag (asse massimo),
    salienza; backup `.bak-pre-firme-se-<ts>` di memoria.db; `--dry` = solo resoconto.
- Stress-test: `--dry` prima, poi dopo la scrittura `test_firme_se.py`: tutti i 644 nodi con firma a 24 assi, emo_tag fra i
  24, statistiche coi metadati giusti, quota del campione con la soglia nuova uguale alla vecchia (+-1 punto); il
  riflesso legge ancora emo_tag (nome presente in `emo-cvec-v2.npz`). Stress: `--scrivi` lanciato due volte = stesso
  risultato (idempotente); `--leggi` interrotto e ripreso = stesse letture; ripristino dal backup riporta memoria.db
  byte per byte; nodi senza contesto (primo del giorno) e nodi "letto" firmati come gli altri.

### B4. Lux 1.13.0: l'emozione sull'arco (CPU)
- [x] FATTO 01/11: `lux_engrammi.py` 1.13.0 (backup .bak-pre-1.13.0), comando `da-precedente` (copia la 1.12.0, C dalla
  firma dei ricordi in memoria.db, F ricalcolata; la 1.12.0 resta), `test_lux_113.py` TUTTO VERDE: dati e stato
  identici alla 1.12.0, C = firma del ricordo su 34.043 archi, F contata a mano su 2050 engrammi, 1000/1000 indizi
  uguali alla 1.12.0, aggiungi e correggi su copia, servizio che rinforza durante aggiungi. Prova del Lux identica
  alla 1.12.0 (121/644 e 350/644, richiamo 33/40); test_archi_vivi, test_predisposizione, test_apostrofi verdi.
  Corretti: `aggiungi` ricalcola F di tutti gli engrammi (prima quelli gia' noti restavano fermi); `salva_stato`
  tiene gli archi gia' su disco in piu' di quelli del Lux in memoria (un servizio caricato prima di aggiungi/correggi
  li avrebbe cancellati). Servizio lux-engrammi riavviato: /salute 1.13.0, 644 ricordi, 19.501 engrammi.
  Da fare in B6: `salienza.stabilita_iniziale` divide la firma per 1.8 (soglia vecchia): con la firma nuova va la
  soglia di stats-firma-se.pt (1.532). Tocca solo i ricordi che entrano da adesso.
- `lux_engrammi.py`: VERSIONE 1.13.0, PRECEDENTE lux-1.12.0. Nuova matrice `C` in `lux.npz` (una riga per arco, 51
  colonne nell'ordine di emozioni.json, zero fuori dai 24): alla nascita ogni arco prende la firma del suo ricordo. F
  di un engramma = media delle C dei suoi archi vivi (la pesatura per carica arriva con la fase 2, punto 7).
  ponytail: MINOR, perche' A, P, V e i ricordi restano identici: `lux-stato.npz` (S, S0, U) si copia dalla 1.12.0 e i
  rinforzi restano.
- Stress-test `engrammi/test_lux_113.py`: A, P, V, meta uguali alla 1.12.0; C con 34.043+ righe, ogni arco uguale alla firma
  del suo ricordo; F = media delle C; `prova` del Lux (ricomposizione di tutti i ricordi + richiamo da indizi) verde come
  per ogni versione; stato copiato identico. Stress: 1000 indizi a caso dai ricordi veri danno gli stessi ricordi
  della 1.12.0 (il richiamo non usa F); `aggiungi` di un ricordo nuovo aggiunge le sue righe di C; correzione
  (`correggi`) con arco a posizione -1 ha la sua C; `aggiungi` mentre il servizio salva lo stato (lucchetto) non
  perde ne' archi ne' rinforzi.
- Poi servizio del Lux sulla 1.13.0 (riavvio lux-engrammi), controllo `/salute` (versione, numero di ricordi ed engrammi).

### B5. Vecchio Lux in archivio (D6)
- [x] FATTO 01/11 (backup posto 3 + `.bak-pre-B5-0111` di ogni file). `test_persistenza_lux.py` TUTTO VERDE (su copie,
  servizio di prova :8133 con LUX_DIR); test_lux_113, test_archi_vivi, test_predisposizione, test_apostrofi,
  test_engrammi di nuovo verdi.
  - Soglie (`taratura_persistenza.py` -> taratura-persistenza.json, criterio del 30/09 sui 644 ricordi veri, 95
    percentile del massimo contro gli ALTRI): eco 1.35 sul punteggio di `/richiama` (mediana 0.42), temi 0.84 sul
    coseno bge-m3 del messaggio intero (mediana 0.70). bge-m3 legge al massimo 2048 token: testo ai primi 6000 caratteri.
  - `servizio_lux.py`: `POST /rinforza {nid, peso}` (peso in (0, 1]; corretto = non si rinforza; sconosciuto = 400) e
    `POST /richiama {testo, quanti}` (sola lettura, senza predisposizione); coda di connessioni 64 (con il default 5
    lo stress-test di 50 richieste insieme veniva rifiutato). Servizio riavviato: /salute 1.13.0, 644, 19.501.
  - `lux_engrammi.py` (resta 1.13.0, dati invariati): `rinforza(..., peso)`; ricordi con fonte "abitudine" nascono con
    S0 >= S_ABITUDINE (S_BASE x AROUSAL_MAX, come prima); `LUX_DIR` punta una copia.
  - `persistenza.py`: eco = `/richiama` sopra 1.35 -> `/rinforza` a 0.5 (una per ricordo per notte); temi su bge-m3
    in `workspace/memoria/temi-engrammi.npz` (firma come dict); 47 temi migrati dal vecchio buffer (`migra`).
    Gira nel venv di jspace (torch per memoria.add_node): col Lux parla solo via servizio, niente spacy.
  - `tagging35b.py`: tolti `alimenta_lux` e `aggiorna_sidecar`; la persistenza riceve (testo, firma, ts); addr_sem
    dell'abitudine = bge-m3 del testo (1024).
  - `sincronizza-richiami.py`: solo diario-richiami (ricorda.py) -> `/rinforza` a peso 1; diario-riflessi ignorato
    (la consegna rinforza gia'). Prova a secco sui diari veri: 241 richiami di 178 ricordi in attesa dal 24/10 (le
    notturne senza messaggi escono prima della sincronia): entrano alla prima notturna con messaggi.
  - `notte-memoria.sh`: sentinella `sentinella_lux.py` (ogni ricordo di memoria.db nel Lux in servizio), verde 644/644.
  - Archivio: lux.npz, lux-meta.json, temi-candidati.npz in `archivio-firma-3110/` (LEGGIMI.txt). Non funzionano piu':
    lux-demo, parte Lux di cervello, grafo3d*.py, aggancia-appunti (dormiente): segnati in PIANO-MANUTENZIONE.md.
  - Fino a B6 il tagging notturno firma ancora con emovec-18 e soglia 1.8 (stanotte niente: l'agente spenta, chat vuota).
- NOTE DI LAVORO 01/11 sera (CC, lette prima di cominciare; backup completo prima di B5 GIA' FATTO: posto 3):
  - `persistenza.notte` oggi vuole (stato L29 grezzo, firma 51, testo, ts) e lavora sulle tracce del vecchio Lux
    (`organo.encode`, `tracce`, `rinforza`, `esperisci`, `pota`). Nel nuovo: (testo, firma 51 nell'ordine di
    EMOZIONI, ts), niente stato; eco con `Lux.richiama` del Lux degli engrammi (lettura in processo) e rinforzo con
    `POST /rinforza` del servizio; temi coi vettori bge-m3 del messaggio intero (:8094, `lux_engrammi.embed`).
  - Taratura delle due soglie col criterio del 30/09 sui 644 ricordi veri: per ogni ricordo il punteggio massimo
    contro gli ALTRI ricordi (richiama per l'eco, coseno bge-m3 per i temi); soglia = 95° percentile (eco falsa sotto
    il 5% per messaggio). Numeri nella relazione all'utente.
  - `temi-candidati.npz`: 47 temi nello spazio vecchio. Si rifanno i centri dai testi dei rappresentanti (bge-m3),
    il resto (n, giorni, stabilita') resta.
  - `tagging35b.persistenza_notte` passa la firma nell'ordine `sorted(emos)` (P3: ordini diversi). Da adesso
    `carica()` di lux_engrammi (ordine di emozioni.json). `promuovi` chiama `memoria.add_node(testo, firma, addr_sem,
    ...)` che vuole un tensore addr_sem (vettori.pt): senza stato L29 serve un vettore; proposta: il bge-m3 del testo
    (la via semantica vecchia non esiste piu', P1). Stessa questione in B6.
  - `sincronizza-richiami.py` usa `lux.Lux` (neurone_di dai nodi): diventa una chiamata `/rinforza` per ricordo
    richiamato (route nuova in `servizio_lux.py`, rinforzo FSRS a peso 1; l'eco a peso 0.5).
  - notte-memoria.sh: sentinella sul `lux-stato.npz`/`lux-meta.json` della versione in servizio invece che su
    `workspace/memoria/lux.npz`.
- `tagging35b.py`: tolti `alimenta_lux` e `aggiorna_sidecar` (P1). `notte-memoria.sh`: sentinella sul Lux degli
  engrammi (P6).
- `sincronizza-richiami.py`: i richiami del giorno (ricorda.py dell'agente e riflesso) rinforzano gli archi del Lux degli
  engrammi, attraverso il servizio (nuova route `POST /rinforza {"nid", "peso"}` in `servizio_lux.py`, cosi' il
  servizio resta l'unico che scrive lo stato).
- `persistenza.py` sul Lux degli engrammi: eco = messaggio scartato il cui richiamo (`Lux.richiama`) supera la soglia
  d'eco -> rinforzo a peso 0.5 (`/rinforza`); temi nello spazio bge-m3 del messaggio intero. Le soglie del vecchio
  spazio (0.85) non valgono: si ritarano con lo stesso criterio del 30/09 (eco falsa sotto il 5% per messaggio) sui
  ricordi veri; numeri all'utente.
- Dati del vecchio Lux (`workspace/memoria/lux.npz`, `lux-meta.json`, `temi-candidati.npz`) in
  `archivio-firma-3110/`. Di `lux.py` restano le funzioni FSRS e l'orologio; attrezzi che usano la classe vecchia
  (lux-demo, cervello) e aggancia-appunti (dormiente) segnati in PIANO-MANUTENZIONE.md come non funzionanti.
- Stress-test: `test_persistenza_lux.py` su una COPIA del Lux (eco vera rinforza, messaggio estraneo no, tema che torna
  matura); `sincronizza-richiami.py --dry` sui diari veri; notturna di prova su copia (`notte-memoria.sh` con le
  cartelle puntate a una copia) senza errori. Stress: 50 `/rinforza` in parallelo = 50 rinforzi contati, nessuno perso;
  notturna interrotta a meta' (kill) e rilanciata = nessun rinforzo contato due volte (marcatore); servizio giu'
  durante sincronizza = errore e marcatore fermo, la notte dopo rimedia.

### B5b. Lettura di piu' strati in una chiamata (luxifer), prima di B6
- [x] FATTO 01/11 sulla COPIA DI PROVA (luxifer-prova, server 8098): "layers" c'era gia' (prova del 12/10); aggiunto
  "somme": true -> "sums" in doppia precisione (server-context.cpp, backup .bak-pre-somme-0111, build-prova
  ricompilata). `firma_se.firma_server` = 3 letture (contesto + messaggio, contesto, primo token): 4.2 s a firma (era
  71). `test_b5b.py` TUTTO VERDE: uguale alla firma di B2 entro 5e-4 (resto delle medie float32 della vecchia),
  deterministica, generazione identica durante le letture, 16 firme in parallelo identiche, errori chiari.
  MISURATO: un valore "esatto" unico non esiste, lo stesso token letto in passaggi di lunghezza diversa esce diverso
  fino a 5e-3 sulla firma (kernel della GPU per numeri di token diversi): conta usare SEMPRE lo stesso metodo e lo
  stesso lettore. La lettura "ultimi"/"lungo" della prova non va usata per la firma (risultati incoerenti).
- [x] FATTO 01/11: "layers" e "somme" portati nel luxifer di PRODUZIONE (solo il blocco di /lux-read: niente
  "lungo"/"ultimi"/"speciali" della prova; i checkpoint del 20/10 restano), build-cuda ricompilata (libllama-server-impl.so
  15:47). Prova del binario di produzione sull'8098 (server di prova spento e poi riacceso): test_b5b.py TUTTO VERDE,
  4.31 s a firma (max 5.22). Ritorno indietro: server-context.cpp.bak-pre-layers-somme-0111 + ricompilare.
  DEPLOY al prossimo avvio di llama-35b, che fa l'utente.
- Misura del B2 (01/11): `/lux-read` legge uno strato per chiamata, 1-1.7 s a lettura con `--n-cpu-moe 34` (come il
  server dell'agente): 34 letture = 71 s a firma, troppo per firmare a ogni messaggio senza rallentare l'agente.
- Route estesa: `"layers": [15, ..., 31]` (medie per strato in una sola decodifica) e `"from": n` (media dai token n in
  poi). Firma = 2 chiamate: contesto + messaggio da `from` = token del contesto (media del messaggio), contesto da
  `from` = 1 (senza il pozzo). Misurato 4.2 s a firma (01/11).
- Prima su luxifer-prova (server 8098), poi sul luxifer di produzione: il binario del servizio e' la build, ogni build
  diventa deploy al riavvio di llama-35b (lo fa l'utente).
- Stress-test: firma con la route nuova = firma con la vecchia (stessi numeri a 1e-5) sui 20 messaggi veri e sui testi
  strani; "layers" fuori range, vuoto, doppioni, "from" oltre i token -> errore chiaro; 50 letture concorrenti con una
  generazione in corso: generazione identica byte per byte (come il 16/07) e nessun errore; tempo a firma <= 5 s.

### B6. Il ricordo entra subito
- [x] CODICE E TEST FATTI 01/11 sera (backup completo posto 4 + `.bak-pre-B6-0111` di riflesso.py, memoria.py,
  notte-memoria.sh, lux_engrammi.py, salienza.py). `test_firma_subito.py` TUTTO VERDE (due giri): forte, debole,
  forzato col marcatore (anche corto), doppione, URL = letto, trascinamento prima/dopo (S0 a meta' misurata nel Lux,
  fuori finestra e nodo non forte = niente), righe rotte e riga a meta', lettore diverso e 35B spento (coda ferma),
  firma vera dal finto server e testo rifiutato (HTTP 400 = errore, la coda va avanti), raffica di 200 da 4
  scrittori (2.2 s, ordine della coda), kill -9 a meta' (nessun doppione, tutto nel Lux), notturna insieme (lucchetti),
  recupera (solo i mancanti, marcatore, 24 ore, ricorda-ora, uscita 1 a coda ferma, niente due volte), notte,
  riflesso (righe solo per le risposte finali). I 9 test dei blocchi prima: uscite identiche.
  Revisioni (agenti): dal piano, testo dell'utente preso prima di ora/coda, pensatoio con aggancio suo, add_node atomico,
  forzati; dal codice, chiave del recupero col marcatore tolto, dedup del recupero nelle 24 ore, attesa della coda =
  10 minuti SENZA AVANZARE (non 30 fissi), omeostato prima della persistenza, segnalibro che riparte se la coda e'
  ricreata. Misurato: la ricarica del Lux nel servizio dopo un aggiungi costa 0.1 s.
  MANCA: accendere la unit (`cp engrammi/firma-subito.service ~/.config/systemd/user/ && systemctl --user
  daemon-reload && systemctl --user enable --now firma-subito`, a CC il permesso e' stato negato), riavviare il
  riflesso, avviare llama-35b (binario con layers e somme). notte-memoria.sh nuovo e' gia' su disco: senza la unit una
  notte con messaggi fallisce dopo 10 minuti (marker fermo, la notte dopo rimedia, come un tagging fallito).
  Limiti noti: giornata-firma.jsonl non si accorcia mai (da potare in B7); test 15 non esercita do_POST intero.
Testo originale del piano (31/10), che resta valido:
- `riflesso.py`: a turno chiuso, dopo la risposta, una riga in `workspace/memoria/coda-firma.jsonl` (messaggio,
  autore, ts, contesto = ultimi 1200 caratteri come il tagging). Nessun lavoro nel percorso della risposta.
- Unit nuova `firma-subito.service` (`engrammi/firma_subito.py`): legge la coda; per ogni messaggio pulizia e dedup
  come `tagging35b` (`pulisci`, `dedup`, marcatore `[ricordare]`), `firma_server`, z con `stats-firma-se.pt`; sopra
  soglia (o forzato) -> nodo in memoria.db (`memoria.add_node`) e ricordo nel Lux (`lux_engrammi._aggiungi` sul solo
  ricordo nuovo, sotto il lucchetto; il servizio ricarica da solo). Sotto soglia -> coda degli scartati del giorno
  (per persistenza e behavioral tagging).
- Behavioral tagging: un messaggio forte trascina gli scartati della coda dentro la finestra prima e quelli che
  arrivano nella finestra dopo, con S0 ridotto. Valori di partenza dalla letteratura, per non fermare il piano (l'utente
  li cambia quando vuole, sono tre costanti): finestra 60 minuti prima e dopo (Moncada e Viola 2007, nel ratto circa
  un'ora); "forte" = salienza almeno un punto z sopra la soglia; S0 del trascinato = meta' di quello che avrebbe da
  solo.
- Se il 35B e' spento la coda aspetta (nessuna firma da altri modelli).
- Notturna: via `run-tagging.sh` (niente piu' 35B spento di notte); restano estrazione e dormita, sincronizza,
  persistenza sugli scartati del giorno, omeostato (dai ricordi nati nel giorno), SHY, orologio.

DETTAGLIO DI ESECUZIONE (CC 01/11 sera, dopo la lettura del codice; scelte di CC segnate "CC"):
- Ambienti: il riflesso gira col python3 di sistema (solo libreria standard); firma_subito.py nel venv di jspace
  (torch per firma_se e memoria.add_node, come persistenza); il Lux (spacy) solo nel venv-spacy, quindi l'ingresso nel
  Lux e' `venv-spacy/bin/python lux_engrammi.py aggiungi` lanciato da firma_subito dopo add_node (lucchetto gia' dentro
  aggiungi; nessun ricordo nuovo = "nessun ricordo nuovo").
- Riflesso (`_dopo_chat`, thread, dopo lo specchio del KV): solo risposte FINALI (finish stop, niente tool call, testo
  non vuoto). Flusso chat: due righe, il messaggio dell'utente (ultimo user con prefisso "[handle] ", stessa regola di
  estrai-matrix: handle minuscolo -> autore @handle:localhost, testo senza prefisso; "[" senza handle = sistema,
  niente riga) e la risposta dell'agente (autore @agente:localhost). Flusso pensatoio (CC, per parita' con
  estrai-matrix che legge anche il pensatoio): solo la risposta finale dell'agente. ts = ora d'arrivo della richiesta
  finale (messaggio) e ora di fine risposta (l'agente): due ts diversi, perche' il codice del ricordo nasce dal ts.
  Riga = {"ts", "autore", "testo"}; il contesto NON lo scrive il riflesso (CC): lo costruisce firma_subito dai
  messaggi gia' visti nelle 24 ore prima (stessa regola di B3: contesto_di dei messaggi con ts nella finestra), cosi'
  vale anche per i messaggi recuperati dalla notturna. Scrittura in append con una sola write e flush: una riga
  intera o niente; mai un errore che tocchi la risposta (try/except col diario).
- firma_subito.py, giro del servizio (ogni 5 s):
  - coda-firma.jsonl si legge da un segnalibro (byte gia' elaborati, file coda-firma.pos, scritto atomico DOPO il
    lavoro di ogni riga); riga rotta (json invalido, campi mancanti) -> segnata in coda-firma-rotte.jsonl, saltata.
  - prima di firmare: il server (URL_FIRMA, default :8090) deve rispondere e avere lo stesso modello del lettore di
    stats-firma-se.pt ("lettore"); se no la coda ASPETTA (segnalibro fermo, riprova al giro dopo, un avviso nel log
    per cambio di stato).
  - pulisci (tagging35b), almeno 15 caratteri, marcatore [ricordare] (applica_marcatore), dedup contro i messaggi gia'
    visti nelle 24 ore (stessa chiave di tagging35b.dedup: autore + primi 200 caratteri).
  - firma_server(contesto, testo, URL, mu delle stats) -> z = (r - mean) / (sd + 1e-6) con le stats di B3, FISSE
    (CC: niente Welford online; la soglia e' legata alla quota misurata in B3). Firma salvata = dict dei 24 assi a 3
    decimali, emo_tag = asse massimo, salienza = z massimo, come B3. emo_alpha = None (P2: non si calcola piu').
  - sopra soglia (1.532) o forzato: memoria.add_node(testo, firma, addr_sem = bge-m3 del testo (come le abitudini di
    B5), emo_tag, None, salienza, fonte=autore, ts, classe letto/vissuto, voluto) e poi Lux aggiungi.
  - sotto soglia: resta nel registro del giorno come scartato.
  - registro del giorno `workspace/memoria/giornata-firma.jsonl`: una riga per messaggio elaborato {ts, autore,
    testo, firma, salienza, esito: nodo | scartato | trascinato | doppione | corto, nid}; serve a contesto, dedup,
    trascinamento e notturna.
  - behavioral tagging: un nodo con salienza >= soglia + 1 (FORTE_DELTA) alle ts t trascina gli scartati del registro
    con ts in [t - 3600, t) e gli scartati che arrivano con ts in (t, t + 3600]; il trascinato diventa nodo con
    fonte = "trascinato" (CC: il campo fonte e' gia' la marca dell'abitudine), e nel Lux nasce con S0 a meta'
    (TRASCINATO_S0 = 0.5 in lux_engrammi._aggiungi, come S_ABITUDINE per le abitudini). Gli URL ("letto") non si
    trascinano (regola 2: la persistenza non li tiene).
  - crash a meta': add_node deduplica sul testo e Lux aggiungi prende solo i ricordi che mancano, quindi rifare la
    stessa riga non crea doppioni; il segnalibro avanza solo a riga finita.
- memoria.add_node: lucchetto (flock su memoria.db.lock) attorno a "c'e' gia' il testo? / insert / vettori.pt": il
  servizio e la persistenza della notturna possono scrivere insieme (oggi vettori.pt si legge e si riscrive intero).
- lux_engrammi: `stabilita_iniziale` divide la firma per la soglia nuova (SOGLIA_FIRMA = 1.532, letta da
  stats-firma-se.pt nel test) invece di 1.8 (nota di B4), solo per gli archi che nascono da adesso; trascinati a
  S0 x 0.5. VERSIONE resta 1.13.0 (come B5: i dati gia' scritti non cambiano).
- Notturna (notte-memoria.sh): estrazione, dormita, sincronizza come oggi; al posto di run-tagging.sh:
  `firma_subito.py recupera J`: (CC) i messaggi della giornata estratta che non sono nel registro (riflesso giu',
  vecchio riflesso non ancora riavviato, pensatoio) e le voci di da-ricordare.jsonl (ricorda-ora, forzate) vanno in
  coda; poi aspetta che il servizio svuoti la coda (massimo 30 minuti; 35B spento o servizio fermo = fallito, marker
  fermo, la notte dopo rimedia, come oggi col tagging). da-ricordare.jsonl si toglie solo a coda svuotata.
  Poi `firma_subito.py notte`: persistenza.notte sugli scartati del registro dal marker in poi (ne' trascinati ne'
  URL) e omeostato.imprimi dalle firme dei nodi nati dal marker in poi. Restano orologio, SHY, Lux aggiungi (prende
  le abitudini promosse), sentinella. run-tagging.sh e tagging35b.main restano su disco (pulisci, dedup e marcatore
  si usano da li').
- Omeostato: imprimi riceve firme a 24 assi; gli assi vecchi fuori dalla ruota tendono a 0 (la revisione e' D7, fase 2).
- Unit firma-subito.service: Restart=always, venv di jspace, nice 10. La installa e la accende CC (non e' l'agente ne' il
  riflesso); senza il riflesso nuovo la coda resta vuota e il recupero notturno fa il lavoro.
- Messa in produzione: unit accesa da CC; riflesso nuovo al riavvio che fa l'utente; firma vera solo col luxifer nuovo
  (layers e somme) cioe' al prossimo avvio di llama-35b fatto dall'utente (con il binario vecchio: "il server non da'
  le somme" -> la coda aspetta).
- Rollback: .bak-pre-B6-0111 di riflesso.py, memoria.py, notte-memoria.sh, lux_engrammi.py; unit disattivata.

Stress-test `engrammi/test_firma_subito.py` con un finto server `/lux-read` (come `test_confronto.py`): messaggio forte ->
  nodo + ricordo nel Lux di una copia; debole -> coda degli scartati; forzato -> entra; doppione -> fuori; tagging
  trascina il vicino debole. Stress: raffica di 200 messaggi (tutti firmati, in ordine, nessuno perso); 35B spento a
  meta' (la coda aspetta e riparte da dove era); crash del servizio a meta' messaggio (al riavvio nessun doppione e
  nessun messaggio perso); notturna e firma-subito insieme (lucchetto, nessuna scrittura persa); coda corrotta (riga
  rotta: saltata e segnata, le altre passano). Poi prova sul vivo al primo riavvio del riflesso fatto dall'utente.
  In piu' (CC): lettore con un altro modello -> la coda aspetta; recupera mette in coda solo i messaggi che mancano
  e una seconda volta niente; notte passa alla persistenza solo gli scartati; riflesso: riga scritta solo per la
  risposta finale, prefisso tolto, nessuna riga per "[" di sistema, eccezione nella scrittura non tocca la risposta.

### B6bis. Cattura graduale nel behavioral tagging (l'utente 01/11 sera, dopo la prova della selezione)
- [x] FATTO (codice + test, backup posto 3 + .bak-pre-cattura-0111). Prova della selezione sulla chat vera (1583 messaggi,
  prova_selezione.py): col solo tempo i trascinati erano il 38% (79% di ricordi in tutto). l'utente: piu' vicino alla
  memoria umana. Regola nuova: un debole (non URL) entro 60 minuti da un forte (salienza >= soglia + 1) e' catturato
  solo se almeno QUOTA_MIN = 25% dei suoi engrammi sta gia' nel forte e almeno uno e' nuovo (cattura sinaptica: cellule
  condivise; Dunsmoor 2015: solo i ricordi legati; separazione dei pattern contro i ridondanti). S0 del trascinato = S0
  propria x g, g = 0.25 + 0.75 x quota x forza, forza = (z_forte - soglia) / 3 fra 1/3 e 1 (scelte di CC, costanti in
  firma_subito). Sulla prova la regola cattura 115 deboli su 580 vicini (sovrapposizione_prova.py).
  Codice: Lux.sovrapposizione + route POST /sovrapposizione del servizio (sola lettura; spaCy sta li'); colonna
  nodi.cattura (memoria.add_node, aggiunta anche in produzione); _aggiungi usa cattura (0.5 se manca); il forte entra
  nel Lux subito, prima dei trascinamenti all'indietro. test_firma_subito.py punto 5 riscritto con testi legati ed
  estranei: legato prima e dopo catturati con g ricalcolato a mano, estranei scartati anche se vicini, ridondante
  scartato, S0 nel Lux = S0 x g. TUTTO VERDE; test_b7 verde (ora parte dalla copia di prima della pulizia).
  test_lux_113 e test_firme_se: fotografie dello stato di B4 e B3, rossi per la pulizia dei ricordi del 01/11 sera
  (23 ricordi cambiati, voluta dall'utente): non si correggono.
  IN SERVIZIO dal 01/11 21:41 (lux-engrammi e firma-subito riavviati, l'utente); route verificata su un ricordo vero.

### B7. Pulizia rimasta
- [x] FATTO 01/11 sera (backup completo posto 1 + .bak-pre-B7-0111 dei file, vettori.pt compreso). `test_b7.py` TUTTO
  VERDE: codice(ts) uguale in modulo, riflesso, Lux e copia di ricorda.py su ~9.600 ts, codici del Lux in servizio =
  codice(ts) dei 644 ricordi; addr_emo migrata su copia con richiamo per emozione identico (stessi id, punteggi entro
  1e-4, anche col nome italiano), migrazione ripetuta = uguale, add_node nel formato nuovo; potatura (vecchie fuori,
  dal marker dentro dopo notti fallite, ultima riga vince, riga rotta, contesto uguale, voce piu' vecchia del registro
  saltata, potatura guasta non ferma il giro). MIGRATA LA PRODUZIONE: `memoria.py migra-addr-emo`, 644/644 addr_emo =
  firma a 51 assi. test_firma_subito di nuovo verde, i 9 test dei blocchi prima con uscite identiche. Revisione del
  codice (agente): ricalcola-firme.py scriveva ancora l'ordine vecchio (corretto), voci vecchie dopo un segnalibro
  perso (saltate), potatura che falliva bloccava il giro (corretto).
- P2 emo_alpha non si calcola piu'; P3 ordine unico dei 51 assi (emozioni.json) in tagging e memoria.py; P4
  `codice(ts)` in un solo posto (+ test che confronta la copia di ricorda.py); P5 firma costruita una volta sola.
- Test: tutti i test dei blocchi precedenti di nuovo verdi.

DETTAGLIO DI ESECUZIONE (CC 01/11 sera, dopo la lettura del codice; backup completo posto 1 + .bak-pre-B7-0111):
- P2: firma_subito passa gia' emo_alpha = None; tagging35b (dopo B6 fuori dalla notturna, resta come attrezzo) non lo
  calcola piu' (None), via emo-cvec-v2 dal tagger.
- P3: l'unico vettore senza nomi e' addr_emo in vettori.pt (ordine alfabetico delle chiavi della firma; lo legge
  memoria.recall in modo emotiva, cioe' recall.py --emo). Da adesso `memoria.addr_emo(firma)` = 51 valori nell'ordine di
  emozioni.json (zero fuori dalla firma), usata da add_node e da ricalcola-firme-se.py; recall per nome accetta il nome
  inglese o italiano di emozioni.json. Migrazione: `memoria.py migra-addr-emo` riscrive addr_emo di tutti i nodi dalla
  firma in memoria.db (backup .bak-pre-B7 di vettori.pt, scrittura atomica, sotto il lucchetto di add_node).
- P4: `codice_ricordo.py` (libreria standard) con codice(ts); lux_engrammi e riflesso lo importano; ricorda.py (nel
  container) tiene la sua copia; `test_b7.py` (punto 1) confronta le tre su ~9.600 ts (veri e a caso) e i codici del Lux.
- P5: in tagging35b una funzione `firma_di(Z, i, emos)` al posto delle tre costruzioni.
- Registro del giorno: firma_subito pota giornata-firma.jsonl una volta ogni 6 ore dentro il servizio (unico che lo
  scrive, nessuna corsa): restano le voci con ts >= min(adesso - 3 giorni, marker della notturna - 1 giorno), una riga
  per voce (l'ultima), scrittura atomica.
- Stress-test `test_b7.py`: addr_emo = firma in ordine emozioni.json per ogni nodo dopo la migrazione (su copia), recall
  per nome (en e it) uguale a prima sul contenuto; migrazione ripetuta = stesso file; add_node scrive il formato nuovo;
  potatura: voci vecchie fuori, quelle dal marker dentro anche se vecchie, ultima riga vince, registro corrotto a meta'
  non perde le voci intere, il servizio dopo la potatura continua (contesto e dedup uguali).

### B8. Documento per ricercatori ML (regola del 22/10)
- [x] FATTO 01/11 sera: `engrammi/FIRMA-ENGRAMMI.md` (obiettivo, metodo, risultati con n e controlli, limiti).
- `engrammi/FIRMA-ENGRAMMI.md`: cosa cambia, perche' (vettori della parola contro vettori sé, emozione sull'arco,
  behavioral tagging), numeri della fedelta' e della soglia.

Fase 2 dopo: D7 (riflesso ai vettori sé), punto 2 della fase 2 da rovesciare (D4).
