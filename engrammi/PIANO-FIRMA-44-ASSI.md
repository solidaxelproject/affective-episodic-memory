# Piano: firma dei ricordi a 44 assi (24 della ruota + 20 diadi pure), variante C

09/11/2026 sera. Decisione dell'utente (manutenzione, decisione 1 di mainteinance-plan-9-11-26.md): "estendiamo", poi
"sì, procedi con C", "backup prima e test dopo". Iter: skill di upgrade.

## 1. Obiettivo

Oggi la firma ha 24 assi (vettori se' della ruota, firma_se.py) e la dominante (memoria.dominante) sceglie fra le 36
emozioni con vettore di steering: le 20 diadi pure non sono nella firma e non vincono mai (dominanti presenti: 16).
Dopo: firma a 44 assi, cosi' anche le diadi possono essere dominanti.

## 2. Cosa e' C (misurato prima di decidere)

I 20 vettori delle diadi (fonte sé-proprio = vettori-se-proprie.pt) hanno coseno medio 0.94 fra loro: sono quasi lo
stesso vettore (ognuno e' "scene proprie + direzione del se'"). C: per ogni strato 15-31 si fa la media dei 44 vettori
(unitari) e la si toglie da ognuno, poi di nuovo unitari. Il resto della firma e' identico.
Test offline sulle scene con l'emozione nota (scratchpad della sessione 09/11, test_firma44.py: scene proprie di 20
diadi + 4 della ruota, 6 pieghe con i vettori rifatti senza la piega; controllo = 47 scene x 8 emozioni medie),
dominante giusta:

| variante | 20 diadi | 8 medie (controllo) | medie prese da una diade |
|---|---|---|---|
| oggi (24) | 0% | 92% | 0% |
| A diadi grezze | 32% | 92% | 0% |
| B solo sé-proprio centrato | 88% | 70% | 17% |
| **C tutti i 44 centrati** | **76%** | **87%** | **0%** |
| D via solo il se' | 39% | 91% | 0% |

Limite: le scene sono lette da sole (colorata - neutra); la firma vera legge il messaggio nel contesto. Controllo dopo
la rifirma: distribuzione delle dominanti sui ricordi veri (task 5).

## 3. Cosa NON si tocca (domanda dell'utente: "non sminchi i vettori dello steering?")

- I vettori dello steering (vettori-se-proprie.pt, vettori-se-*.pt delle fonti, DOSI-EMOZIONI.md, confronto.py,
  sistema.sorgenti) restano identici.
- vettori-firma.pt (24 assi) resta com'e': lo usano come fonte di steering mix.py e bench.py (prova di accumulo,
  superata). I 44 vettori corretti vanno in un file NUOVO: /data/jspace/out-occamy/vettori-lettura-firma.pt,
  letto solo da firma_se.py.

## 4. Dipendenze controllate (grep 09/11)

| chi | cosa usa | cosa cambia |
|---|---|---|
| engrammi/firma_se.py | VETTORI (vettori-firma.pt), vettori(), proietta | VETTORI -> vettori-lettura-firma.pt (env VETTORI_FIRMA per le prove); nuova diff_server (firma_server = proietta(diff_server)) |
| engrammi/vettori_firma.py | costruisce vettori-firma.pt | nuova funzione lettura(): 44 assi centrati -> vettori-lettura-firma.pt |
| firme-occamy/ricalcola-firme-se.py | --leggi (server :8098), --scrivi | --leggi salva le DIFFERENZE per strato (non solo la proiezione): letture-diff.pt, cosi' la proiezione si rifa' sulla CPU; --scrivi: dominante con memoria.dominante (oggi max su tutti, bug); env LETTURE_SE/STATS_SE/MEM_SAM per le copie |
| engrammi/firma_subito.py | stats()["s"]["assi"], soglia, firma_server | niente da cambiare (generico sugli assi); da RIAVVIARE (ha in cache vettori e statistiche): ordine dell'utente |
| stats-firma-se.pt | assi, mean, M2, mu, soglia | riscritto da --scrivi (44 assi, soglia con la stessa quota, D5 del 01/11) |
| memoria.db / vettori.pt | firma, emo_tag, salienza, addr_emo | riscritti da --scrivi (backup automatico .bak-pre-firme-se-<ts>) |
| engrammi/lux_engrammi.py | SOGLIA_FIRMA = 1.532 scritto a mano; C (51 colonne, firma del ricordo alla nascita) | SOGLIA_FIRMA = soglia nuova; C e F rifatti dalla firma nuova (script aggiorna_c_0911.py, come lux_togli del 01/11) |
| memoria.dominante, lux3d, avatar, omeostato | firma come dict su 51 assi di emozioni.json | niente (le diadi sono gia' fra i 51) |

## 4bis. Correzioni dalla revisione dei danni (agente, 09/11 sera; verificate nel codice)

1. **Vettori e statistiche cambiano INSIEME.** stats-firma-se.pt porta il percorso del file dei vettori (chiave
   "vettori"); firma_subito.stats() imposta F.VETTORI da li' (statistiche vecchie senza la chiave = vettori-firma.pt)
   e controlla len(assi) == len(mean). Cosi' il codice nuovo si puo' mettere prima: un riavvio di firma-subito
   (Restart=always) non mescola mai 44 vettori con statistiche a 24 (sarebbe un errore registrato e il messaggio perso).
2. **firma-subito fermo durante la scrittura.** Oggi llama-35b e' spento: firma-subito resta in Aspetta e non firma
   niente (la lettura del task 4 usa il server :8098, non :8090). Al task 6: l'utente ferma firma-subito, poi --scrivi,
   aggiorna_c, SOGLIA_FIRMA, e l'utente lo riavvia. Stesso ordine per il rollback.
3. **vettori.pt con lucchetto**: --scrivi scrive db e vettori.pt sotto il lucchetto di memoria.db (memoria.db.lock) e
   con memoria._save_vec (file temporaneo + os.replace).
4. **Messaggi senza contesto (8)**: si tengono le medie del messaggio da solo come oggi ("soli"); la differenza si fa in
   --scrivi con mu completo. Le differenze per strato si salvano solo per chi ha contesto.
5. **lettura() scrive "fonte" per tutti i 44 assi** (--scrivi la copia nelle statistiche; test_firme_se la controlla).
   Le 20 diadi: solo quelle di memoria.CON_VETTORE da vettori-se-proprie.pt (28 chiavi: fuori aggressivita',
   indignazione, trionfo e le 5 della ruota); i 24 della ruota dalle loro FONTI; ordine di emozioni.json; assert 44.
6. **Al task 5, oltre a soglia e dominanti**: quota del campione con salienza >= soglia + 1 (FORTE_DELTA, trascinamento)
   e distribuzione di salienza/soglia (salienza.stabilita_iniziale, E fra 1 e 3), a 24 e a 44 assi.
7. **Test da aggiornare a 44 assi e a memoria.dominante**: test_firma_se.py:33 (shape 24), test_firma_subito.py:368
   (firma vera con le statistiche), test_firme_se.py (24 assi, emo_tag = max, 644 nodi: oggi 640), test_pulizia_0111.py:72
   (emo_tag = max, test storico: si lascia e si dice).
8. **Firme vecchie che restano** (registro giornata-firma.jsonl, 3 giorni; firme medie dei temi in persistenza): l'agente e'
   spenta dal 24/10, il registro non ha voci recenti; i temi: da guardare al task 5 e decidere con l'utente.
9. **aggiorna_c_0911.py**: sotto X.lucchetto(), venv-spacy; C[arco] = carica(firma del ricordo) per gli archi dei
   ricordi (le correzioni restano come sono); F = firme_engrammi; S, S0, U intatti (le S0 degli archi vecchi restano
   quelle nate con la firma a 24: DECISIONE DA SCRIVERE, proposta: intatte, perche' sono la storia del ricordo); lux-meta.json
   per ultima (ricarica del servizio); lux3d tiene i colori vecchi fino al suo riavvio.
10. letture-diff in float32, salvate ogni 100 voci; LETTURE di default = letture-diff.pt.
11. Stima del task 4 corretta: il 01/11 5.4 s a voce, ~1660 voci = fino a 2.5 ore.

## 4ter. Regola della dominante (l'utente 09/11 sera, FATTA in memoria.dominante)

"Noi nel modello possiamo steerare solo le emozioni di cui abbiamo il vettore: tutti i ricordi devono essere firmati
con una di quelle; quelli con un'emozione senza vettore si rifirmano con la piu' vicina nello stesso petalo, oppure la
diade piu' vicina." Codice: la piu' forte della firma; se non ha vettore, la media del suo petalo (memoria.PETALO:
accettazione -> fiducia, apprensione -> paura, distrazione -> sorpresa, malinconia -> tristezza, noia e ribrezzo ->
disgusto, fastidio e furia -> rabbia); fuori dalla ruota (oggi nessuna nella firma) la piu' forte fra quelle con
vettore. Prima (09/11 pomeriggio): la piu' forte fra quelle con vettore. test_dominante.py verde (esempio dell'utente:
malinconia 3.0 + gioia 2.5 -> tristezza). Backup memoria.py.bak-pre-petalo-0911. Vale da subito per la rifirma; per
firma-subito e il riflesso al loro riavvio (task 6).

## 5. Task

- [x] 0. Backup completo (backup-ruota.sh) prima del blocco di codice.
- [x] 1. vettori_firma.lettura() + vettori-lettura-firma.pt; test: 44 assi, unitari, coseno medio fra assi ~0,
      vettori-firma.pt invariato (sha256 prima e dopo).
- [x] 2. firma_se: VETTORI nuovo, diff_server; test: firma_server(…) == proietta(diff_server(…)) sul finto server di
      test_firma_subito/test_b5b; test_firma_se, test_b5b, test_firma_subito verdi come prima (uscite salvate).
- [x] 3. ricalcola-firme-se.py: --leggi salva le differenze; --scrivi proietta con i vettori del file e usa
      memoria.dominante; test su copie col finto server.
- [x] 4. LETTURA SUL SERVER :8098 (l'utente lo accende, llama-35b spento): --leggi in letture-diff.pt (~1660 voci;
      con le 3 letture per firma di B5b, stimato meno di 1 ora).
- [x] 5. --scrivi --dry su copie: soglia, quota, salienze, distribuzione delle dominanti (A contro C sui ricordi veri);
      i numeri all'utente prima di scrivere in produzione.
- [x] 6. Backup completo; --scrivi in produzione; aggiorna_c_0911.py sul Lux (C, F, lucchetto, meta per ultimo);
      SOGLIA_FIRMA; riavvio di firma-subito SOLO con ordine dell'utente.
- [x] 7. Test dopo: test_firma_se, test_b5b, test_firma_subito, test_dominante, test_engrammi; /salute del Lux;
      controllo in sola lettura di memoria.db (44 assi in ogni firma, dominanti fra le 36).
- [ ] 8. Relazione (documento a fine fase), handoff con la skill aggiorna-documenti.

## 6. Rollback

memoria.db, vettori.pt, stats-firma-se.pt: i .bak-pre-firme-se-<ts> di --scrivi. Lux: .bak-pre-firma44-0911 dei tre
file. Codice: .bak-pre-firma44-0911 accanto a ogni file, piu' il backup completo. firma_se.VETTORI di nuovo su
vettori-firma.pt e riavvio di firma-subito.

## 7. Stato

09/11 23:12: IN PRODUZIONE. Lettura 1620 voci sul :8098 (5.2 s/voce, letture-diff.pt 339 MB); prova a secco: soglia 1.515
(24) -> 1.9036 (44), quota 37.5% uguale; dominanti diverse 16 -> 35, diadi dominanti 172/640 (27%; tutte tranne la
speranza); dominanti cambiate 408/640 (198 anche a 24, per la regola del petalo). FORTE_DELTA 1.0 -> 0.76 (l'utente: stessa
quota di forti, 5.7%). Prova generale su copie verde (test_firme_se, aggiorna_c). Produzione: firma-subito fermato,
backup completo (posto 4), --scrivi (.bak-pre-firme-se-20261109-230905), aggiorna_c_0911 (C e F di 33424 archi;
.bak-pre-firma44-0911), SOGLIA_FIRMA 1.904, FORTE_DELTA 0.76, test verdi (test_dominante, test_vettori_firma,
test_vettori_lettura, test_firma_subito), firma-subito e lux3d riavviati, /salute 640 ricordi. Vettori dello steering
intatti (sha256). Resta: documento a fine fase (task 8), handoff.
