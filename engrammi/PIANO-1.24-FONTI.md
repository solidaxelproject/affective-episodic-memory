# Lux 1.24.0: fonti (fase 3)

> **Per chi esegue:** superpowers:executing-plans, iter di upgrade (skill di upgrade), caselle `- [ ]`. Python del Lux:
> `/data/venv-spacy/bin/python`. Ramo `fonti` in un worktree (copiare dentro i file fuori da
> git: `engrammi/via-emotiva/traduzione-l29.npz`, `engrammi/misura-t1a-stati.npz`). Sempre in italiano.
> Decisioni dell'utente D1-D10 in `engrammi/PIANO-LUX-FASI-v1.12.md`, sezione "Fase 3. Fonti": qui riportate.

**Obiettivo:** il Lux sa da quale sito viene un ricordo, ogni sito ha una fiducia che sale con le conferme e scende con
le correzioni, e l'agente ha uno strumento `correggicordo` per correggere un ricordo, rifiutato se ha appena letto un sito
non certo.

**Architettura:** il riflesso ricava i siti dalle pagine lette (URL negli argomenti della chiamata dello strumento il cui
risultato e' una lettura, >= 400 caratteri di prosa), li mette nella riga dell'agente della coda di firma e tiene un registro
delle letture recenti. Il Lux fa di ogni sito un engramma (D9) legato con un arco speciale (posizione -1, come le
correzioni) al primo engramma di ogni ricordo del sito; la fiducia per sito sta in `lux-stato.npz` (`FO_*`). Il plugin
di Hermes registra `correggicordo`, che passa dal riflesso (controllo D10) al servizio del Lux (`/correggi`).

**Tech stack:** Python 3 (numpy), servizio HTTP del Lux (:8132), riflesso (:8091), plugin di Hermes nel container.

---

## Decisioni (l'utente 13/11 sera)

| | Decisione |
|---|---|
| D1 | La fonte web e' il SITO (dominio), non la pagina. |
| D2 | Conferma automatica: un ricordo nuovo con lo stesso contenuto (sovrapposizione) arriva da una fonte gia' certa (l'utente o un sito certo) e nessuna correzione lo smentisce. Niente strumento di conferma. |
| D3 | Le correzioni entrano SUBITO (ricordo corretto nel Lux e fiducia giu' alla chiamata). |
| D4 | Nome `correggicordo`, descrizione (alla lettera): "Corregge un tuo ricordo. Scrivi il codice del ricordo e il testo corretto, intero." |
| D5 | Fonte nel contesto = sito non certo: `correggicordo` rifiuta. La certezza la decide il conto della fiducia; l'utente certa dall'inizio. |
| D6 | Risposta al rifiuto (alla lettera, senza punto finale): `mmm non sono sicura che questa informazione sia veritiera, questa fonte, non mi pare ancora credibile` |
| D7 | Risposta a correzione fatta (alla lettera): `Ricordo corretto. Il nuovo codice è <codice>.` (`<codice>` = 16 caratteri del ricordo nuovo) |
| D8 | Dopo una RICERCA (elenco di risultati, nessuna pagina aperta): nessun sito, il ricordo resta dell'agente. |
| D9 | Il sito e' un ENGRAMMA vero, legato con arco speciale ai ricordi; fiducia per sito in una tabella. |
| D10 | Rifiuto se fra le ultime N pagine lette, e solo dentro gli ultimi M minuti, c'e' almeno un sito non certo. |

## Testi APPROVATI (l'utente 13/11 sera, "vanno bene"): alla lettera

Il modello li vede: si copiano parola per parola, mai cambiarli.
- descrizione del parametro `codice`: "Il codice del ricordo da correggere, come te l'ha dato la memoria."
- descrizione del parametro `testo`: "Il ricordo corretto, scritto intero come vorrai ritrovarlo."
- risposta con codice sconosciuto o testo vuoto: "Non trovo questo ricordo: controlla il codice e scrivi il testo corretto."
- se il Lux non risponde: si riusa `R_GIU` gia' approvato il 09/11 ("La memoria non risponde, riprova più tardi.").

## Numeri provvisori di CC (per la verifica del Lux, non decisi dall'utente)

| Costante | Valore | Motivo |
|---|---|---|
| `FIDUCIA_W0` | 0.1 | sito nuovo: fiducia bassa |
| `FIDUCIA_G` | 0.2 | conferma: w += G x (1 - w) (Rescorla-Wagner, come il rinforzo dei ponti) |
| `FIDUCIA_D` | 0.5 | correzione: w x= (1 - D); una smentita pesa piu' di una conferma (asimmetria della fiducia, Slovic 1993) |
| `FIDUCIA_CERTA` | 0.5 | certo da w >= 0.5: da 0.1 servono 3 conferme (0.28, 0.42, 0.54) |
| `CONFERMA_QUOTA` | 0.5 | sovrapposizione presi/n minima perche' due ricordi dicano la stessa cosa |
| `LETTURE_N`, `LETTURE_MIN` | 5, 30 | D10: ultime 5 pagine, solo negli ultimi 30 minuti |

Dominio = `hostname` dell'URL senza `www.` (it.wikipedia.org e en.wikipedia.org restano due siti: provvisorio).

## Dipendenze controllate

| File | Cosa cambia |
|---|---|
| `riflesso_fonte.py` | `dominio(url)`, `letture(msgs)` (id, dominio) delle pagine lette, `siti_del_turno(msgs)` |
| `riflesso.py:~255` | in `do_POST`: registra le letture e calcola i siti del turno; `/correggicordo` come `/memorinvolontaria` |
| `riflesso_firma.py:22` | `_accoda_firma(..., siti=())`: la riga dell'agente porta `siti` |
| `riflesso_memoria.py` | `correggicordo(args)`: controllo D10 con `/fiducia`, poi `/correggi`; registro delle letture |
| `engrammi/firma_subito.py:176` | `nodo` passa `siti` al Lux |
| `engrammi/lux_engrammi.py` | `CAMPI` + `siti`; `FONTE = "fonte"`; `_lega_siti` in `_aggiungi`; `Lux._apri`: `siti_di`, `ricordi_di_sito`; stato `FO_*`; `conferma(nid)`, `smentisci(o)`, `certo(sito)`; `correggi(..., campi)`; VERSIONE al Task 8 |
| `engrammi/servizio_lux.py` | `/aggiungi` e `/correggi` chiamano conferma/smentisci; POST `/fiducia`; `/salute` con `siti` |
| `hermes-plugin/memorinvolontaria/` | secondo strumento `correggicordo` (plugin.yaml + `__init__.py`) |
| `/data/agente-docker/config.yaml` | niente: il toolset del plugin e' gia' abilitato (verificare al Task 5 se Hermes vuole il nome del toolset nuovo) |

Chi legge `CAMPI` o gli archi a posizione -1: `_apri` (corregge, filtrato su parametro `corregge` e n == 2: gli archi
dei siti hanno n == 1 e parametro `fonte`, non si confondono), `costruisci` (ricostruisce i legami delle correzioni da
`Lp.corregge`: va esteso ai siti, Task 3), `_inserisci` (campi nel meta).

## Task

### Task 1: siti nel riflesso (riflesso_fonte.py)
- [ ] Test `test_fonti_124.py` (radice, accanto agli altri test del riflesso), parte 1: messaggi finti con una chiamata
  `terminal` `{"command": "web_extract https://www.example.org/a"}` e risultato di 500 caratteri -> `letture` =
  `[(id, "example.org")]`; risultato di 50 caratteri -> niente; `web_search "x"` -> niente (D8); due pagine dopo
  l'ultimo user -> `siti_del_turno` = i due domini senza doppioni; pagina prima dell'ultimo user -> non nel turno.
- [ ] Codice:
```python
from urllib.parse import urlsplit
_URL = re.compile(r"https?://[^\s\"'<>]+")


def dominio(url):
    """D1 (13/11): il sito e' il dominio, senza www."""
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def letture(msgs):
    """1.24.0 (D1, D8): [(id della chiamata, dominio)] delle pagine lette: risultato di uno strumento con almeno
    LETTURA_MIN caratteri di prosa e un URL negli argomenti della chiamata (una ricerca non ha URL: D8)"""
    args = {tc.get("id"): str((tc.get("function") or {}).get("arguments", "")) for m in msgs
            if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])}
    ids = _ids_ricordo(msgs)
    out = []
    for m in msgs:
        if m.get("role") != "tool" or _e_ricordo(m, ids) or not isinstance(m.get("content"), str):
            continue
        u = _URL.search(args.get(m.get("tool_call_id"), ""))
        if u and dominio(u.group()) and len(_leggibile(m["content"])) >= LETTURA_MIN:
            out.append((m.get("tool_call_id"), dominio(u.group())))
    return out


def siti_del_turno(msgs):
    """i siti letti dopo l'ultimo messaggio user (il turno della risposta finale dell'agente)"""
    u = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
    return list(dict.fromkeys(d for _, d in letture(msgs[u + 1:])))
```
  Attenzione: `letture(msgs[u+1:])` trova gli argomenti solo se la chiamata e' dopo `u`: e' cosi' (le chiamate del turno
  seguono l'user).
- [ ] Test verdi, commit nel ramo.

### Task 2: siti nella coda di firma e nel Lux alla nascita
- [ ] `riflesso_firma._accoda_firma(flusso, ultimo, arrivo, esito, siti=())`: la riga dell'agente prende `"siti": list(siti)`
  se non vuota. `riflesso.py`: dove legge `d0["messages"]` salva `self._siti = FO.siti_del_turno(...)` (solo `chat`,
  vale anche per il pensatoio: stesso percorso) e lo passa a `_accoda_firma`. Inizializzare `self._siti = ()` accanto a
  `self._altro = False`.
- [ ] `firma_subito.nodo`: `corpo["siti"] = v.get("siti") or []`. La riga della coda arriva in `v` con `dict(m, ...)`:
  verificare che `siti` passi (gia' cosi' per `flusso`).
- [ ] Lux: `CAMPI = (..., "siti")`; `FONTE = "fonte"` (parametro dell'arco del sito); in `_aggiungi`, dopo `_lega`:
```python
def _lega_siti(righe, A, C, par_lista, tab, eid, testi, tutti):
    """1.24.0 (D9, l'utente 13/11): il sito e' un engramma (testo = dominio) legato al primo engramma del ricordo da un
    arco a posizione -1 (fuori da ricomposizione e richiamo) con parametro {fonte}. Carica zero."""
    for r in righe:
        for s in (r[5].get("siti") or []) if len(r) > 5 else []:
            k = chiave(s)
            if k not in eid:
                eid[k] = len(testi)
                testi.append(s)
            A.append((r[0], -1, eid[k], _primo(tutti, r[0]), len(par_lista), 1))
            C.append(carica(None))
            par_lista.append(param_id(FONTE, tab))
```
  Chiamata in `_aggiungi` PRIMA di `nuovi = testi[n_e:]` (cosi' il dominio nuovo prende il vettore bge-m3), con `tutti`
  = archi vecchi + nuovi come per `_lega`. Gli archi nuovi dei siti prendono S/S0/U come gli altri (stessa coda).
- [ ] `Lux._apri`: nel ciclo sugli archi `~vivi`, se `n == 1` e il parametro e' `FONTE`: `self.siti_di[r].append(testo
  dell'engramma a)` e `self.ricordi_di_sito[sito].add(r)`. Inizializzare i due dict prima del ciclo.
- [ ] Test (su copia del Lux in /tmp, `LUX_DIR`): `aggiungi_ricordo` con `siti=["example.org"]` -> un engramma
  `example.org`, un arco -1 con parametro `fonte`, `L.siti_di[nid] == ["example.org"]`; il richiamo e la ricomposizione
  del ricordo identici a uno senza siti (stesso testo, ricomposizione uguale); un secondo ricordo dello stesso sito
  riusa l'engramma.
- [ ] Commit.

### Task 3: costruisci() conserva i legami dei siti
- [ ] In `costruisci`, accanto ai legami delle correzioni: le righe portano gia' `siti` nei campi (dal meta della
  PRECEDENTE), quindi basta chiamare `_lega_siti(righe, ...)` dopo `_lega`. Test: costruisci su copia con un ricordo con
  siti -> stesso `siti_di`.
- [ ] Commit.

### Task 4: fiducia, conferme e smentite
- [ ] Stato: `self.fiducia = {}` (sito -> [w, conferme, correzioni]) e `self.confermati = set()` (ricordi di siti gia'
  confermati, una volta sola) in `carica_stato`; in `salva_stato` `FO` (stringhe, `np.asarray(list, dtype=str)`),
  `FO_W`, `FO_C`, `FO_X`, `FO_OK` (int64). Caricamento con `"FO" in z.files`.
- [ ] Metodi:
```python
    def certo(self, sito):
        """D5 (13/11): certo quando la fiducia supera la soglia; un sito mai visto parte da FIDUCIA_W0"""
        return self.fiducia.get(sito, [FIDUCIA_W0])[0] >= FIDUCIA_CERTA

    def conferma(self, nid):
        """D2 (13/11): il ricordo nid viene da una fonte certa (l'utente o un sito certo): ogni ricordo di un ALTRO
        sito che dice la stessa cosa (sovrapposizione >= CONFERMA_QUOTA), non corretto e non gia' confermato, alza la
        fiducia del suo sito. -> siti confermati"""
        r = self.ricordi.get(nid, {})
        miei = set(self.siti_di.get(nid, []))
        if r.get("fonte") != FONTE_CERTA and not any(self.certo(s) for s in miei):
            return []
        fatti = []
        for s, nids in self.ricordi_di_sito.items():
            if s in miei:
                continue
            for m in sorted(nids - self.confermati - self.errati - {nid}):
                n, presi = self.sovrapposizione(r["testo"], m)
                if n and presi / n >= CONFERMA_QUOTA:
                    w = self.fiducia.setdefault(s, [FIDUCIA_W0, 0, 0])
                    w[0] += FIDUCIA_G * (1 - w[0])
                    w[1] += 1
                    self.confermati.add(m)
                    fatti.append(s)
        return fatti

    def smentisci(self, o):
        """D3 (13/11): il ricordo o e' stato corretto: la fiducia dei suoi siti scende subito"""
        for s in self.siti_di.get(o, []):
            w = self.fiducia.setdefault(s, [FIDUCIA_W0, 0, 0])
            w[0] *= 1 - FIDUCIA_D
            w[2] += 1
        return self.siti_di.get(o, [])
```
  `FONTE_CERTA = "@utente:localhost"` (valore del campo `fonte` dei messaggi dell'utente; nome della costante neutro,
  vedi ruff/an()). Nota: `sovrapposizione` embedda il testo per ogni m; se i ricordi dei siti diventano centinaia,
  embeddare una volta sola (ponytail: non ora).
- [ ] Servizio: `_aggiungi` dopo `lux()`: `L.conferma(nid)` e `L.salva_stato()` se ha confermato; `/correggi`: prima
  `o = lux().da_codice[codice]`, poi `X.correggi(codice, testo, campi={"fonte": d.get("fonte", ""), "siti":
  d.get("siti", [])})`, `_meta[0] = None; lux()`, `L.smentisci(o)`, `L.conferma(nid della correzione)`,
  `L.salva_stato()`. POST `/fiducia {"siti": [...]}` -> `{"certi": {s: bool}}`. `/salute` + `"siti":
  len(L.ricordi_di_sito)`. Attenzione: `lux()` ricarica e rifa' `carica_stato` dal disco: lo stato `FO_*` va salvato
  PRIMA di ogni ricarica (stesso schema dei ponti).
- [ ] `correggi(codice_errato, testo, ts=None, campi=None)`: la riga diventa `(nid, testo, None, "correzione", ts,
  campi or {})`; `_lega_siti` lega anche la correzione ai suoi siti. Torna il codice (come oggi) e il servizio ricava
  il nid da `da_codice`.
- [ ] Test: l'utente scrive un ricordo uguale a uno di example.org -> fiducia 0.28, conferme 1; la seconda volta lo stesso
  ricordo non conta di nuovo; tre ricordi confermati -> `certo` vero; correzione di un ricordo del sito -> fiducia
  dimezzata, `certo` falso; un ricordo dell'agente senza siti non conferma niente; un sito non conferma se stesso; stato
  salvato e ricaricato identico.
- [ ] Commit.

### Task 5: correggicordo (plugin + riflesso), dopo l'approvazione dei testi
- [ ] Riflesso, `riflesso_memoria.py`:
```python
R_CORRETTO = "Ricordo corretto. Il nuovo codice è {codice}."   # D7 (13/11), alla lettera
R_DUBBIO = "mmm non sono sicura che questa informazione sia veritiera, questa fonte, non mi pare ancora credibile"   # D6
R_CODICE = "Non trovo questo ricordo: controlla il codice e scrivi il testo corretto."   # l'utente 13/11
LETTURE_N, LETTURE_MIN = 5, 30   # D10: numeri provvisori di CC
_letture = collections.deque(maxlen=200)   # (ts, id della chiamata, dominio), dal riflesso a ogni richiesta
_letture_lock = threading.Lock()


def registra_letture(msgs):
    with _letture_lock:
        visti = {x[1] for x in _letture}
        for i, s in FO.letture(msgs):
            if i not in visti:
                _letture.append((time.time(), i, s))


def _recenti():
    """D10: i domini delle ultime LETTURE_N pagine, solo dentro gli ultimi LETTURE_MIN minuti"""
    with _letture_lock:
        ultime = list(_letture)[-LETTURE_N:]
    return [s for t, _, s in ultime if time.time() - t <= LETTURE_MIN * 60]


def correggicordo(args):
    codice, testo = str(args.get("codice", "")).strip(), str(args.get("testo", "")).strip()
    recenti = _recenti()
    certi = _lux_post("/fiducia", {"siti": recenti})["certi"] if recenti else {}
    if any(not certi.get(s) for s in recenti):
        return R_DUBBIO
    fonte = "@utente:localhost" if S.ultima_fonte_utente() else "@agente:localhost"
    try:
        r = _lux_post("/correggi", {"codice": codice, "testo": testo, "fonte": fonte, "siti": sorted(set(recenti))})
    except urllib.error.HTTPError as e:
        return R_CODICE if e.code == 400 else R_GIU
    return R_CORRETTO.format(codice=r["codice"])
```
  `_lux_post`: helper con l'URL base del servizio (oggi `LUX` punta a /consegna: ricavare la base). `fonte`: chi
  corregge = l'utente se l'ultimo ingresso da fuori nella richiesta che ha prodotto la chiamata e' un suo messaggio,
  altrimenti l'agente; il riflesso salva `S._ultima_fonte_utente[0]` in `do_POST` da `FO._fonte_indice` (ruolo user).
  `registra_letture(d0["messages"])` in `do_POST` per chat e pensatoio. `/correggicordo` in `do_POST` come
  `/memorinvolontaria` (stesso `_ammesso`).
- [ ] Plugin: in `__init__.py` secondo schema `correggicordo` (descrizione D4, parametri con i testi approvati,
  `required: ["codice", "testo"]`), handler che fa POST a `.../correggicordo`, `R_GIU` sull'errore;
  `ctx.register_tool(name="correggicordo", toolset="memorinvolontaria", ...)`; `plugin.yaml`: `provides_tools` +
  `correggicordo`.
- [ ] Test (riflesso con Lux finto, come i test esistenti di memorinvolontaria; `controlla_bersagli.py` prima): pagina di
  sito non certo letta 10 minuti fa -> R_DUBBIO e il Lux non riceve /correggi; letta 40 minuti fa -> correzione;
  sesta pagina dopo quella dubbia (tutte certe) -> correzione; codice sconosciuto -> R_CODICE; Lux giu' -> R_GIU.
- [ ] Commit.

### Task 6: prova su copia
- [ ] Copia del Lux 1.23.0 in /tmp, 20 ricordi finti di 3 siti, 10 ricordi "dell'utente" che ripetono 4 di quelli del sito
  A: A certo dopo 3, B no; una correzione su A -> A sotto soglia; richiama/ricomponi sui 668 ricordi veri identici
  prima e dopo (fotografia con `richiama` su 50 indizi a giorno vissuto fisso: nessuna differenza, gli archi -1 sono
  fuori). Risultati in `engrammi/prova-fonti-124/`.

### Task 7: revisione, pulizia, batteria
- [ ] Agente in sola lettura sul diff; deslop + ponytail; test esistenti con la stessa uscita; ruff; py_compile;
  `controlla_bersagli.py`; `foto_riflesso.py` (dentro `unshare -rn`).

### Task 8: produzione (SOLO col via dell'utente)
- [ ] Backup completo (`backup-ruota.sh`). Merge in master; `VERSIONE = "1.24.0"` + riga di storia, `PRECEDENTE` 1.23.0,
  `da_precedente` copia identica. Commit.
- [ ] `systemctl --user stop firma-subito lux-engrammi lux3d`; `lux_engrammi.py da-precedente`; start dei tre; restart
  `riflesso`; slot del 35B se acceso (chat.kv).
- [ ] Plugin nel container: SOLO quando l'utente riaccende/riavviall'agente (il container lo riavvia lei): `docker cp` come nel
  PIANO-MEMORINVOLONTARIA-LUX.md punto 3. Fino ad allora correggicordo non esiste per l'agente, il resto (siti, fiducia)
  lavora gia'.
- [ ] `/salute` = 1.24.0; `verifica_post_versioning.py`; diario alla prima pagina letta (righe di coda-firma con `siti`).

## Correzioni della revisione del piano (agente, 13/11 sera; verificate nel codice) - VALGONO SUI TASK

1. Task 1, `letture`: gli `arguments` di Hermes sono una stringa JSON (`\"` attorno all'URL): `json.loads` degli
   arguments (fallback alla stringa) e URL cercato nei VALORI decodificati; `dominio` in try (urlsplit alza ValueError
   su URL malformati: niente sito). Test con `web_extract "https://example.org"` (virgolette) e con URL malformato.
   In `riflesso.py` `registra_letture`/`siti_del_turno` in un try PROPRIO, mai nel try prima di `C._stop_chiesto`
   (PATTO clausola 3: un errore non deve saltare lo spegnimento del vettore).
2. Task 5, `correggicordo`: in testa `if not C.consenso_attivo(): return R_GIU` (come memorinvolontaria, riga 221).
3. Task 5, chi corregge: `S._fonte_utente = [False]` in riflesso_stato.py; aggiornato SOLO con `flusso == "chat"`, dall'
   ultimo user con `C._HANDLE` e l'handle dell'utente (CC "[cc] ...", il pensatoio e i cron "altro" non sono l'utente).
4. Task 2, `_apri`: il nome del sito e' `chiave(self.testi[a])` (nel Lux ci sono gia' engrammi come `OilPrice.com`,
   `Inc.com`: con il testo grezzo conferme e `certo()` userebbero due nomi diversi). Anche `ricordi_di_sito` per chiave.
5. Task 2, `_apri`: `profz` (profilo emotivo, righe ~910-916) solo sugli archi `self.vivi` (oggi media su tutti: gli
   archi-sito a carica zero diluirebbero il profilo e `accordi()`). Sui dati attuali identico: test.
6. Task 4, `conferma`: embed del testo nuovo UNA volta (`sovrapposizione` accetta vettori gia' calcolati), perche' gira a
   ogni `/aggiungi` e `/correggi` sul servizio a un filo (timeout del riflesso 30 s, del plugin 45 s: un R_GIU dopo
   una correzione gia' fatta farebbe riprovare l'agente = doppia correzione e doppia smentita).
7. Task 4, `conferma`: "stesso contenuto" = sovrapposizione nei DUE versi (min di presi/n del testo nuovo sul ricordo
   del sito e del ricordo del sito sul nuovo) >= CONFERMA_QUOTA: un messaggio corto non conferma un ricordo lungo con
   due parole in comune.
8. Task 2, `_lega_siti`: salta i ricordi senza archi vivi (`_primo` su array vuoto alza: oggi il ricordo entrerebbe).
9. Task 4, servizio: `siti` accettato solo come lista di stringhe (una stringa farebbe un engramma per lettera).
10. Task 5: `import collections` in riflesso_memoria.py; rotta `/correggicordo` in `do_POST` PRIMA dell'inoltro (oggi un
   path sconosciuto va a :8090). Noto e accettato: registro D10 vuoto al riavvio del riflesso (le pagine ancora nella
   storia rientrano con l'ora del riavvio: piu' prudente); una correggicordo nello stesso giro della web_extract passa
   prima che la pagina sia registrata (raro).
11. Task 2: anche i ricordi di `+lux` (`_accoda_forzato`) prendono i siti delle letture recenti (`_recenti()` di D10):
   un ricordo voluto dall'agente dopo una pagina viene da quella pagina. Valore provvisorio di CC.
12. Rollback: la 1.23.0 riscrive lo stato senza FO_* (fiducia persa) e `profz` torna a diluirsi coi ricordi con siti:
   accettato (la fiducia rinasce dalle conferme). `costruisci` riparte senza stato (come per i ponti).

## Revisione del codice (agente, 13/11 notte) - applicata
Corretti: chi corregge si riscrive a OGNI richiesta del modello (pensatoio e cron = non l'utente); una conferma da' credito a
TUTTI i siti del ricordo confermato; `lux_engrammi.py correggi` da riga di comando smentisce i siti come il servizio
(fonte ignota: niente conferme); siti con la stessa chiave = uno solo; registro delle letture con gli id visti senza
tetto; test di conferma resi veri (frase corta, un sito non si conferma da se', ricordo con due siti).
Limiti accettati (provvisori di CC): un ricordo DOPPIONE (testo identico al carattere) torna col nid che c'era e i siti
del secondo arrivo non si legano; `letture` prende come pagina qualunque comando con un URL e >= 400 caratteri di uscita
(anche git clone, pip install, un indirizzo locale) e solo il primo URL della chiamata. Lo scenario del Task 6 (siti che
diventano certi e ricadono) e' coperto da engrammi/test_fonti_lux_124.py (parti 3, 4, 6); la prova del Task 6 misura
l'effetto zero sui 668 ricordi.

## Rollback
A servizi fermi: dati 1.24.0 copiati sulla 1.23.0 (gli archi dei siti restano ma la 1.23.0 li vede come archi -1 di
parametro sconosciuto: `_apri` della 1.23.0 cerca solo `corregge` con n == 2, quindi li ignora; gli `FO_*` nello stato
li ignora), `git revert -m 1 <merge>`, restart; plugin: togliere `correggicordo` dal container (lo fa l'utente al riavvio).

## Stato
13/11 notte: IN PRODUZIONE (col via dell'utente). Backup in engrammi/backup/2, merge 42b8162, 107faf1 (VERSIONE 1.24.0,
PRECEDENTE 1.23.0, da_precedente = copia identica). /salute = 1.24.0, 668 ricordi, 0 siti; servizi attivi, riflesso
riavviato; /correggicordo del riflesso risponde (codice inesistente -> R_CODICE); verifica_post_versioning: solo
l'errore gia' noto sul 809. Plugin copiato (docker cp -a, uid 1000) nel container SPENTO: si carica quando l'utente
riaccende l'agente. Da guardare dal vivo: prima pagina letta (coda-firma con "siti"), Hermes che carica correggicordo.
13/11 notte: Task 1-7 fatti nel ramo `fonti`: riflesso, Lux, servizio, plugin; test nuovi
verdi (test_fonti_124.py, engrammi/test_fonti_lux_124.py), test di prima con la stessa uscita (test_forza rosso gia'
prima), ruff pulito, conservazione 50/50 richiami, 668/668 ricomposizioni, profilo uguale. Revisione del codice applicata.
Prossimo: Task 8, produzione col via dell'utente.
13/11 sera: decisioni D1-D10 prese, piano scritto, revisione del piano fatta (12 correzioni sopra). Testi approvati.
