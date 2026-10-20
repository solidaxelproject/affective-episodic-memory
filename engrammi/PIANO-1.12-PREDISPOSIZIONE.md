# Lux 1.12.0: predisposizione dopo il richiamo + apostrofi (piano di implementazione)

> Per chi esegue: superpowers:executing-plans, un task alla volta, caselle `- [ ]`.

**Obiettivo (l'utente 20/10/2026, "seconda strada"):** i ricordi che condividono engrammi, e ancor di piu' archi, con un
ricordo appena consegnato all'agente restano PREDISPOSTI per un po': se il prossimo indizio li tocca anche debolmente,
salgono prima dei concorrenti. La predisposizione da sola NON consegna mai niente (niente richiamo a cascata).

**Architettura:** tutto dentro `lux_engrammi.py`, classe `Lux`.
- `predisponi(nids)`, chiamata da `consegna` dopo i rinforzi: per ogni ricordo y la spinta = somma, sugli engrammi che
  y condivide con i ricordi consegnati, di `1/(ricordi che usano l'engramma - 1)`, piu' `PESO_COPPIA/(ricordi con la
  coppia - 1)` per ogni arco condiviso (stessa coppia di engrammi), divisa per `sqrt(engrammi di y)`. Peso = effetto
  ventaglio (fan effect, Anderson 1974; ACT-R): l'attivazione di un elemento si divide fra tutti i ricordi a cui e'
  legato. Misura del 20/10 sulle 27 consegne di ieri sera: col peso di `richiama` (1/log(1+n)) una consegna
  predisponeva in mediana 212 ricordi (fino a 116 con spinta >= 0.5: "È", "l'utente", "Io" spargono la spinta ovunque);
  col ventaglio 57 appena sfiorati, 6 con spinta >= 0.1, in mediana nessuno >= 0.5. Convergenza: le spinte di piu' ricordi consegnati si sommano.
- La spinta cala col tempo dell'orologio di parete (`time.time()`), emivita `PREDISPOSIZIONE_EMIVITA`.
- `richiama` moltiplica il punteggio dei ricordi GIA' accesi dall'indizio per `min(PREDISPOSIZIONE_MAX, 1 + spinta)`.
  Un ricordo che l'indizio non tocca resta fuori: la predisposizione non crea richiami da sola.
- Stato SOLO in RAM (`self.pronti`): e' un effetto di minuti/ore. `servizio_lux.py` lo porta da un Lux al successivo
  quando la notturna lo ricarica.
- Senza predisposizione (Lux appena aperto) `richiama` da' risultati IDENTICI alla 1.11.0: la soglia tarata l'11/10 resta
  valida, `lux3d.py`, `taratura_soglia.py` e le prove (che aprono un Lux nuovo e non consegnano) non cambiano.

**Niente stringhe nuove che il modello vede.** La risposta del tool resta quella della 1.10/1.11.

## Dipendenze controllate (20/10)

| Chi | Cosa usa | Effetto della 1.12.0 |
|---|---|---|
| `servizio_lux.py` (unit `lux-engrammi.service`, :8132) | `Lux()`, `consegna`, `risposta_tool`, `correggi`, ricarica su `META` | consegna predispone; nella ricarica si porta `pronti` (Task 4) |
| `riflesso.py:392,908` | POST /consegna `{testo, esclusi}` | nessun cambiamento di interfaccia |
| `notte-memoria.sh` | `lux_engrammi.py aggiungi` (usa `DIR`) | scrive in `lux-1.12.0/` |
| `lux3d.py`, `taratura_soglia.py`, `test_archi_vivi.py`, `verifica_post_versioning.py`, `salienza/*.py`, `7-codici/richiamo_json.py` | `Lux()`, `richiama` su un Lux nuovo | identici (pronti vuoto) |
| `lux3d-gif.py:17` | `VERSIONE = "1.11.0"` scritta a mano | portata a 1.12.0 (Task 5) |
| `wikilux/*`, `ricorda.py`, `test-riflesso-query.py` | non usano la classe `Lux` (solo regole di taglio o `codice`) | nessuno |

Versione: MINOR (funzione nuova, dati identici), cartella nuova `lux-1.12.0/` = copia di `lux-1.11.0/` (precedente:
la 1.10.0 aveva fatto lo stesso). `PRECEDENTE` passa a `lux-1.11.0`.

## Decisioni (20/10: regolate su come funziona la mente umana)

- D1 `PREDISPOSIZIONE_EMIVITA` = 21600 s (6 ore). Dopo un richiamo i neuroni del ricordo restano piu' eccitabili per
  alcune ore e i ricordi formati in quella finestra si legano (Cai 2016: 5 ore si', 7 giorni no; Rashid 2016: 6 ore),
  la stessa finestra del riconsolidamento della fase 2 (Nader 2000). Il richiamo volontario predispone quelli
  involontari dello stesso tema fino al giorno dopo (Mace 2005): con 6 ore dopo un giorno resta 1/16.
- D2 `PREDISPOSIZIONE_MAX` = 2.0. Il priming abbassa la soglia ma non sostituisce l'indizio: un indizio debole basta,
  nessun indizio no (gia' nella regola: solo i ricordi accesi dall'indizio). Nessun dato umano da' il valore: tetto
  uguale a `FACILITA_MAX`, da verificare con la misura del Task 2.
- D3 `PESO_COPPIA` = 1.0. La codifica relazionale (Cohen ed Eichenbaum 1993) lega due ricordi molto piu' per una
  combinazione condivisa che per gli elementi sparsi: un arco condiviso porta i suoi due engrammi piu' la relazione,
  cioe' tre volte un engramma raro da solo.
- D4 una predisposizione sola per chat e pensatoio: la memoria umana e' una, pensare a una cosa la predispone anche
  nella conversazione.

---

## Parte B (20/10): apostrofi veri, apici delle citazioni

Problema (misurato su 584 ricordi): 47 ricordi perdono apostrofi veri, 2 hanno spazi sbagliati. Cause: `taglia.py`
tratta ogni apostrofo isolato come apice (lo toglie e apre una "citazione" che ingoia le parole dopo: «perche' non so
piu'» -> [perche][non so piu]); «d'» diventa il parametro "di» («d'accordo» -> «di accordo»); `ricomponi` incolla la
parola dopo QUALUNQUE apostrofo («un po'di») e stacca i pezzi inglesi che iniziano con l'apostrofo («it 's»).

Regole (prototipo nello scratchpad: 47 -> 0 e 2 -> 0, nessun ricordo peggiorato; restano solo gli apici delle
citazioni, tolti per scelta):
1. `taglia.apostrofo(t)`: un segno ' o ’ ATTACCATO alla parola prima (nessuno spazio) e' un apostrofo vero e resta
   nell'engramma di quella parola (po', perche', be', students'); fuori da una citazione aperta. Un apice dopo uno spazio
   apre la citazione, il segno dopo la chiude (come oggi).
2. `legame`: «d'» non e' un parametro, resta nell'engramma (d'accordo, d'altronde).
3. `ricomponi`: si incolla dopo un apostrofo solo se prima c'e' una consonante (elisione: l', dell', c', quest'); i nodi
   che iniziano con ', ’, n't si attaccano alla parola prima (inglese: it's, I've, aren't).
Limiti noti (ponytail): «Di' la verita'» esce minuscolo (0 ricordi), genitivo inglese davanti a parola
(«students' books») esce attaccato.

Dati: il taglio cambia i testi degli engrammi -> la 1.12.0 si RICOSTRUISCE (costruisci, vettori ripresi da 1.11.0 per i
testi uguali). Rinforzi della 1.11.0: zero archi con S != S0 (20/10), non si perde niente. Chi importa taglia.py:
lux_engrammi, salienza/misura.py, wikilux/wikilux.py e prova-rag/valuta.py (i dati di wikilux restano quelli costruiti;
la ricomposizione nuova vale anche per loro).

### Task B1: test (in test_engrammi.py, dopo gli assert esistenti)
### Task B2: taglia.py (apostrofo, legame) e lux_engrammi.ricomponi
### Task B3: ricostruzione in lux-1.12.0 SENZA cambiare VERSIONE nel file (script con X.DIR/NPZ/META/STATO puntati
  alla cartella nuova; il servizio e la notturna restano su 1.11.0)
### Task B4: verifiche: verifica_post_versioning sulla 1.12.0 (errori attesi: solo apici), apostrofi 0 persi,
  richiama dei 56 indizi confrontato con la 1.11.0 (cambia solo dove cambiano gli engrammi), test esistenti.

### Task 0: backup a rotazione (il piu' vecchio viene sovrascritto)

**File:** nessuno nuovo. Tre posti fissi in `/data/memoria-episodica-affettiva/engrammi/backup/1..3`.

- [ ] **Passo 1:** copiare nel posto vuoto o, se sono pieni tutti e tre, in quello modificato meno di recente:

```bash
cd /data/memoria-episodica-affettiva/engrammi && mkdir -p backup/1 backup/2 backup/3 && \
B=$(ls -dtr backup/1 backup/2 backup/3 | head -1); \
for b in backup/1 backup/2 backup/3; do if [ -z "$(ls -A "$b")" ]; then B=$b; break; fi; done; \
rm -rf "${B:?}"/* && cp -a lux_engrammi.py servizio_lux.py lux3d-gif.py taglia.py lux-1.11.0 "$B"/ && touch "$B" && \
echo "backup in $B" && ls "$B"
```
Atteso: `backup in backup/1` e i quattro elementi.

### Task 1: fotografia del comportamento attuale (per la conservazione delle funzioni)

**File:** crea `/data/memoria-episodica-affettiva/engrammi/test_predisposizione.py` (Task 3) e la fotografia
`/tmp/foto-1.11.json`.

- [ ] **Passo 1:** con il codice 1.11.0 salvare `richiama` (tutti i punteggi, soglia 0) su 30 indizi: i messaggi di
  ieri sera, le domande di `taratura_soglia.py`, gli indizi di `test_archi_vivi.py`, scritti a mano in `scratchpad/indizi.json`;
  piu' `ricomponi` di tutti i ricordi. `richiama` con `quanti = len(L.ricordi)` e soglia 0: tutti i punteggi.

```bash
cd /data/memoria-episodica-affettiva/engrammi && /data/venv-spacy/bin/python - <<'P'
import json, lux_engrammi as X
L = X.Lux(); L.salva_stato = lambda: None
g = X.LUX.orologio()   # giorno vissuto fissato: la notturna lo avanza, il Task 6 riusa questo
q = json.load(open("/tmp/indizi.json"))
foto = {"giorno": g, "richiama": {t: L.richiama(t, len(L.ricordi), 0, g) for t in q}, "ricomponi": {n: L.ricomponi(n) for n in L.ricordi}}
json.dump(foto, open("/tmp/foto-1.11.json", "w"))
print(len(q), "indizi,", len(foto["ricomponi"]), "ricordi")
P
```
- [ ] **Passo 2:** girare `test_archi_vivi.py` e `verifica_post_versioning.py`, salvare l'uscita come riferimento.

### Task 2: misura della spinta sulle consegne vere (base delle decisioni D1-D3)

- [x] Peso del ventaglio misurato il 20/10 (vedi Architettura).
- [ ] Script usa e getta nello scratchpad: per le 27 consegne di ieri sera (`diario-riflessi.jsonl`, campo `nid`)
  calcola la spinta che riceverebbero gli altri ricordi, la distribuzione (mediana, 90°, massimo), quanti ricordi
  superano spinta 0.1/0.3/1.0, e per gli indizi successivi quante consegne cambierebbero. Il risultato va a l'utente
  prima del Task 6.

### Task 3: test che fallisce

**File:** crea `/data/memoria-episodica-affettiva/engrammi/test_predisposizione.py`

```python
#!/usr/bin/env python3
"""test della predisposizione (Lux 1.12.0): niente scritture sullo stato vero (salva_stato disattivato)"""
import numpy as np
import lux_engrammi as X

L = X.Lux()
L.salva_stato = lambda: None
assert L.pronti == {}
# x e y condividono un engramma raro (usato solo da loro due); z non condivide niente con x
coppie = [(e, sorted({int(L.A[j, 0]) for j in js})) for e, js in L.per_engramma.items()]
e, (x, y) = next((e, r) for e, r in coppie if len(r) == 2)
eng_x = {int(v) for j in L.per_ricordo[x] for v in L.A[j, 2:4]}
z = next(r for r in L.ricordi if r not in (x, y) and not eng_x & {int(v) for j in L.per_ricordo[r] for v in L.A[j, 2:4]})
L.predisponi([x], ora=1000.0)
assert L.spinta(y, 1000.0) > 0                                     # condivide un engramma: predisposto
assert L.spinta(z, 1000.0) == 0 and L.spinta(x, 1000.0) == 0      # niente in comune / il consegnato stesso
s = L.spinta(y, 1000.0)
assert abs(L.spinta(y, 1000.0 + X.PREDISPOSIZIONE_EMIVITA) - s / 2) < 1e-9   # emivita
L.predisponi([x], ora=1000.0)
assert abs(L.spinta(y, 1000.0) - 2 * s) < 1e-9                    # convergenza: le spinte si sommano
# richiama: moltiplica solo i ricordi accesi dall'indizio, col tetto
testo = L.testi[e]
fresco = X.Lux()
tutti = len(L.ricordi)
base = dict(fresco.richiama(testo, tutti, 0))
ora = dict(L.richiama(testo, tutti, 0, ora=1000.0))
assert y in base and abs(ora[y] - base[y] * min(X.PREDISPOSIZIONE_MAX, 1 + 2 * s)) < 1e-9
assert set(ora) == set(base)                                       # nessun ricordo nuovo dalla sola predisposizione
for r in base:
    if r != y and L.spinta(r, 1000.0) == 0:
        assert ora[r] == base[r]                                   # gli altri identici
# consegna predispone
L2 = X.Lux(); L2.salva_stato = lambda: None
L2.U[:] = 1000.0                                                   # archi freschi, come test_archi_vivi
c = L2.consegna("Ci vuole un UPS", oggi=1000.0)
assert c and L2.pronti                                             # ha lasciato una predisposizione
print("test_predisposizione: ok")
```
- [ ] Girarlo: `cd /data/memoria-episodica-affettiva/engrammi && /data/venv-spacy/bin/python test_predisposizione.py`
  Atteso: `AttributeError: 'Lux' object has no attribute 'pronti'`.

### Task 4: implementazione

**File:** `lux_engrammi.py` (costanti dopo `SOGLIA_SEM`, `_apri`, `richiama`, `consegna`, VERSIONE), `servizio_lux.py:22-28`.

- [ ] Costanti (VERSIONE e PRECEDENTE restano 1.11.0 / 1.10.0 fino al Task 7: il test gira su lux-1.11.0 col
  salvataggio disattivato, e la notturna di mezzanotte continua a scrivere nella cartella che il servizio sorveglia):
```python
# 1.12.0 (20/10): predisposizione dopo il richiamo (predisponi): i ricordi che condividono engrammi e archi coi
# ricordi consegnati salgono prima col prossimo indizio. Piano: PIANO-1.12-PREDISPOSIZIONE.md
PREDISPOSIZIONE_EMIVITA = 21600.0   # 1.12.0 (6 ore, Cai 2016, Rashid 2016): secondi di parete, dopo i quali la spinta e' a meta'
PREDISPOSIZIONE_MAX = 2.0   # 1.12.0: tetto del moltiplicatore del richiamo
PESO_COPPIA = 1.0   # 1.12.0: un arco condiviso (stessa coppia di engrammi) vale quanto un engramma in piu'
```
- [ ] In `_apri`, nel ciclo degli archi vivi e dopo:
```python
            self.coppie.setdefault((min(a, b), max(a, b)), set()).add(r)   # (prima del ciclo: self.coppie = {})
        ...
        self.pronti = {}   # 1.12.0: ricordo -> (spinta, ora) lasciata dalle consegne. ponytail: solo RAM, si perde al
        # riavvio del servizio (effetto di minuti); su disco se servira' sopravvivere ai riavvii
```
- [ ] Metodi nuovi (dopo `rinforza`):
```python
    def spinta(self, r, ora):
        """1.12.0: predisposizione del ricordo r all'ora (secondi di parete), dimezzata ogni PREDISPOSIZIONE_EMIVITA"""
        s, t = self.pronti.get(r, (0.0, ora))
        return s * 0.5 ** ((ora - t) / PREDISPOSIZIONE_EMIVITA)

    def predisponi(self, nids, ora=None):
        """1.12.0: dopo una consegna, ogni ricordo che condivide engrammi (peso 1/(altri ricordi che li usano), effetto
        ventaglio di Anderson 1974) o archi
        (stessa coppia di engrammi, x PESO_COPPIA) coi ricordi consegnati riceve una spinta, divisa per
        sqrt(engrammi del ricordo) come in richiama; si somma a quella residua"""
        ora = time.time() if ora is None else ora
        spinte = {}
        for x in nids:
            js = self.per_ricordo.get(x, [])
            for e in {int(v) for j in js for v in self.A[j, 2:4]}:
                ric = {int(self.A[j, 0]) for j in self.per_engramma[e]}
                for r in ric:   # effetto ventaglio: l'attivazione si divide fra gli altri ricordi dell'engramma
                    spinte[r] = spinte.get(r, 0) + 1 / max(1, len(ric) - 1)
            for a, b in {tuple(sorted(int(v) for v in self.A[j, 2:4])) for j in js}:
                ric = self.coppie[(a, b)]
                if a != b:   # l'arco su se stesso dei ricordi di un engramma solo non e' una relazione
                    for r in ric:
                        spinte[r] = spinte.get(r, 0) + PESO_COPPIA / max(1, len(ric) - 1)
        for r, s in spinte.items():
            if r not in nids:
                self.pronti[r] = (self.spinta(r, ora) + s / np.sqrt(self.ricordi[r]["n"]), ora)
```
- [ ] `richiama(self, testo, quanti=3, soglia=SOGLIA_RICHIAMO, oggi=None, ora=None)`: nel ciclo finale
```python
        ora = time.time() if ora is None else ora
        for r in punti:
            punti[r] *= fac[r] / np.sqrt(self.ricordi[r]["n"]) * min(PREDISPOSIZIONE_MAX, 1 + self.spinta(r, ora))
```
  e una riga nella docstring (1.12.0: moltiplicato per la predisposizione).
- [ ] `consegna`: dopo il ciclo dei rinforzi `self.predisponi(scelti)`.
- [ ] `servizio_lux.py`, in `lux()`: `nuovo = X.Lux(); nuovo.pronti = L.pronti; L, _meta[0] = nuovo, t`.
- [ ] Docstring del modulo: la riga "ponytail: ... propagazione non ancora usati" diventa "propagazione: solo
  predisposizione (1.12.0)".
- [ ] `test_predisposizione.py` passa.

### Task 5: (spostato nel Task 7) cambio di versione e cartella

Revisione 20/10: cambiare VERSIONE prima della messa in produzione spezza la notturna (cartella mancante, poi ricordi
nuovi in 1.12.0 che il servizio vecchio non vede e rinforzi persi). Si fa tutto insieme nel Task 7.

### Task 6: conservazione delle funzioni

- [ ] La fotografia del Task 1 rifatta col codice nuovo su un Lux appena aperto, con `foto["giorno"]` come `oggi`: `richiama` identico su tutti gli
  indizi (stessi ricordi, stessi punteggi), `ricomponi` identico su tutti i ricordi.
- [ ] `test_archi_vivi.py`, `test_engrammi.py`, `verifica_post_versioning.py`: stessa uscita del Task 1.
- [ ] `python -m py_compile` di `lux_engrammi.py`, `servizio_lux.py`, `lux3d.py`.
- [ ] Revisione del codice (superpowers:requesting-code-review), poi deslop e ponytail sul diff, poi di nuovo questo task.

### Task 7: messa in produzione (SOLO col via dell'utente)

- [ ] A servizio fermo e lontano dalla mezzanotte (lux-1.12.0 costruita al Task B3; rifarla se nel frattempo la
  notturna ha aggiunto ricordi alla 1.11.0):
```bash
cd /data/memoria-episodica-affettiva/engrammi && systemctl --user stop lux-engrammi.service lux3d.service && \
test -f lux-1.12.0/lux.npz && \
sed -i 's|^VERSIONE = "1.11.0"|VERSIONE = "1.12.0"|; s|^PRECEDENTE = .*lux-1.10.0"|PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.11.0"|' lux_engrammi.py && \
sed -i 's|^VERSIONE = "1.11.0"|VERSIONE = "1.12.0"|' lux3d-gif.py && \
systemctl --user start lux-engrammi.service lux3d.service
```
- [ ] Poi `curl -s 127.0.0.1:8132/salute` -> versione
  1.12.0, stesso numero di ricordi (gli engrammi cambiano: Parte B).
- [ ] Commit nel locale (`/data/memoria-episodica-affettiva`): `lux_engrammi.py servizio_lux.py lux3d-gif.py
  taglia.py test_engrammi.py test_predisposizione.py PIANO-1.12-PREDISPOSIZIONE.md`. Il pubblico solo su richiesta, con la skill.
- [ ] Rollback (N = posto del backup 2 = Parte B). La 1.12.0 e' ricostruita, i suoi archi non corrispondono a quelli
  della 1.11.0: lo stato NON si riporta (i rinforzi presi in 1.12.0 si perdono); i ricordi aggiunti dalla notturna
  in 1.12.0 rientrano in 1.11.0 con `aggiungi` (prende i ricordi di memoria.db che mancano):
```bash
cd /data/memoria-episodica-affettiva/engrammi && systemctl --user stop lux-engrammi.service lux3d.service && \
cp -a backup/N/lux_engrammi.py backup/N/servizio_lux.py backup/N/lux3d-gif.py backup/N/taglia.py . && \
/data/venv-spacy/bin/python lux_engrammi.py aggiungi && \
systemctl --user start lux-engrammi.service lux3d.service
```
