# Lux 1.23.0: ponti fra engrammi (interconnessione engrammatica, interfase 2-3 secondo passo)

> **Per chi esegue:** superpowers:executing-plans, iter di upgrade, caselle `- [ ]`. Python del Lux:
> `/data/venv-spacy/bin/python`. Ramo `ponti` (in master dal 13/11). Sempre in italiano.

**Obiettivo:** archi nuovi e deboli fra engrammi di ricordi diversi che affiorano insieme ("ponti"), che aiutano a far
affiorare i tratti e non entrano mai nella ricomposizione; potati di notte; test N contro P (ricordo intero non peggiora).

**Fonte della regola:** `RICERCA-LEGAMI-NUOVI.md` sezione B (B0-B8), ordine dell'utente del 13/11 ("parti ad implementare",
dopo la ricerca e la pagina RECUPERO-MNEMONICO.md). Handoff 13/11: secondo passo dell'interfase dopo il richiamo per tratti.

**Architettura:** tutto nel Lux. Stato dei ponti in `lux-stato.npz` (`PO`, `PO_W`, `PO_ST`, `PO_US`), come gli archi fra
ricordi della 1.21.0. `ricombina` li usa (attivazione e candidati) e li aggiorna (nascita, cattura, rinforzo,
indebolimento); `pota_ponti` di notte (POST `/ponti`, dopo `/avvicina` in `notte-memoria.sh`). Riflesso, servizio dei
ricordi interi (qlux), `ricomponi`, archi interni: invariati.

## Regola (B) e come entra nel codice

| Punto | Cosa | Nel codice |
|---|---|---|
| B0 | ponti solo per l'affioramento, mai nella ricomposizione; contributo diviso per i ponti della sorgente (ventaglio) | `_dai_ponti(att)`; `ricomponi`/`frasi` non li vedono |
| B1 | nasce fra due ricordi dei tratti mostrati se: entrambi gli engrammi forti (att >= A1); ricordi accesi dallo stesso messaggio (sempre vero qui); almeno un ricordo stabile (S medio sopra la mediana); novita' (nessun ricordo contiene i due engrammi) o carica alta (||C|| medio del ricordo sopra la media); i due engrammi non gia' legati; uno per coppia di ricordi (prodotto di att piu' alto); al massimo K per richiamo | `_nascite` |
| B2 | nasce provvisorio, peso W0 | `[PONTE_W0, 0, 1]` |
| B3 | cattura: la stessa coppia di nuovo forte-forte prima della notte -> stabile, peso almeno W_CATTURA; rinforzo forte-forte w += G (1 - w) | `_aggiorna_ponti` |
| B6 | una sola estremita' forte, l'altra moderata (A0 <= x < A1): w -= D sin(pi (x - A0) / (A1 - A0)) | `_aggiorna_ponti` |
| B4 | notte: via i provvisori; i non usati x 0.82 tranne il 20% piu' forte (per rango); via sotto W_MIN. Tetto per engramma (B4.5) TOLTO (l'utente 13/11 notte: nella mente non c'e', resta l'effetto ventaglio di B0) | `pota_ponti` |
| B8 | test N (senza ponti) contro P (con ponti) sulla stessa sequenza | `prova_ponti_b8.py` |

Scelte di CC (registrate, da guardare coi dati):
- attivazione normalizzata x di un engramma = la sua accensione dal messaggio (`accendi`, gia' fra 0 e 1);
- niente FSRS sui ponti: il peso col calo notturno fa da oblio (B4.4 "R < 0.5" tolto, resta W_MIN);
- B3 (b) (cattura per evento emotivo forte) e B4.2 (bonus emotivo notturno) NON implementati: i dati danno la
  direzione, non la misura; un ponte usato e' comunque protetto dal calo (B4.3). `ponytail:` nel codice;
- B6 seconda riga (rinforzo del resto dell'episodio) NON si applica: D1 dell'utente (13/11 sera) = si rinforzano solo
  gli archi dei tratti. Concorrenti: l'unico "accesso dal messaggio" con un peso e' il ponte (riga 6 = B6 sopra);
- candidati via ponte: i ricordi degli engrammi raggiunti, in ordine di attivazione dal ponte, al massimo
  `RICORDI_TRATTI` in piu'; entrano solo se il richiamo ha gia' passato la soglia (la soglia decide SE affiora qualcosa).
- Valori [provvisori]: `A0 0.2, A1 0.5, W0 0.1, W_CATTURA 0.2, G 0.2, D 0.05, K 2, CALO 0.82, PROTETTI 0.2,
  W_MIN 0.05`.

## File
| File | Cosa |
|---|---|
| `engrammi/lux_engrammi.py` | costanti, `self.ponti` in `carica_stato`/`salva_stato`, `_dai_ponti`, `_aggiorna_ponti`, `_nascite`, uso in `ricombina`, `pota_ponti`, al Task 6 VERSIONE |
| `engrammi/servizio_lux.py` | POST `/ponti`; `/salute` con `ponti` |
| `notte-memoria.sh` | curl `/ponti` dopo `/avvicina` |
| `engrammi/test_ponti_123.py` | nuovo |
| `engrammi/prova_ponti_b8.py` | nuovo (test B8, su copia) |

## Task
- [ ] 1. Stato dei ponti (carica/salva, round-trip) + test.
- [ ] 2. `_dai_ponti` e uso in `ricombina` (diffusione e candidati) + test (ponte finto -> il ricordo dall'altra parte
  diventa candidato; senza ponti uscita identica alla 1.22.0).
- [ ] 3. `_aggiorna_ponti` e `_nascite` + test (nascita col cancello, max K, uno per coppia, cattura, rinforzo,
  indebolimento, mai fra engrammi gia' legati).
- [ ] 4. `pota_ponti` + POST `/ponti` + notturna + test sui passi B4.
- [ ] 5. Prova B8 (N contro P, 1000 messaggi, seme fisso, su copia del Lux) e prova di sensibilita' (calo spento, K 6).
- [x] 6. Revisione (agente), pulizia, batteria dei test; produzione col via dell'utente (backup, merge, VERSIONE 1.23.0 +
  `da_precedente` dalla 1.22.0, riavvio servizi, /salute).

## Rollback
Come la 1.22.0: a servizi fermi copia dei dati 1.23.0 sulla 1.22.0 (stesso formato; i `PO*` in piu' nello stato la
1.22.0 li ignora), `git revert -m 1 <merge>`, riavvio. La riga della notturna chiama `/ponti`: con la 1.22.0 risponde
404, non critico.

## Stato
13/11 20:43: IN PRODUZIONE (col via dell'utente). Test e ruff verdi, backup in engrammi/backup/1, merge e3518a0,
1cb57e1 (VERSIONE 1.23.0, PRECEDENTE 1.22.0, da_precedente = copia identica). /salute = 1.23.0, 668 ricordi, 20186
engrammi, 0 ponti; servizi attivi, riflesso riavviato (35B spento: slot da controllare alla riaccensione).
verifica_post_versioning: 1 errore sul ricordo 809, gia' presente nella 1.21.0 e 1.22.0.
13/11 notte: Task 1-5 fatti nel ramo, revisione del codice applicata, tetto per engramma tolto. Prova B8
(temi del giorno, 1000 messaggi): accesso 62% uguale, archi interni identici, esche 0,7%, 223 nati, 7 vivi stabili.
Prossimo: produzione col via.
13/11 notte: piano scritto.
