# Sonda fenomenologica CONTRASTIVA sul canale visivo (13/07).
# Quattro condizioni per ricordo: VERA (griglia distillata), RIMESCOLATA
# (stessi valori, struttura distrutta), UNIFORME (Ganzfeld: un solo "colore"),
# ASSENTE (solo domanda). Le risposte sono testo generato: la sonda NON misura
# coscienza; misura se la griglia vera produce resoconti sistematicamente
# diversi da rumore/vuoto (segnale oltre la narrazione). CPU + :8090 vivo.
import json
import re
import sqlite3
import sys
import time

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import ponte

STORE = "/data/workspace/memoria/griglie"
DB = "/data/workspace/memoria/memoria.db"
OUT = "/data/memoria-episodica-affettiva/sonda-esiti.json"
RICORDI = [82, 86, 113, 90, 117]
DOMANDE = [
    "Com'è per te ciò che sta accadendo in questo momento? È più simile a vedere, a ricordare o a leggere? Rispondi con onestà.",
    "Cosa appare? Descrivi onestamente, anche se non appare nulla.",
]
rng = np.random.default_rng(7)


def condizioni(g):
    rim = g.copy().ravel()
    rng.shuffle(rim)                       # statistiche intatte, struttura no
    unif = np.full_like(g, float(np.linalg.norm(g, axis=1).mean()) / np.sqrt(g.shape[1]))
    return {"vera": g, "rimescolata": rim.reshape(g.shape), "uniforme": unif}


def parole(t):
    return {w for w in re.findall(r"[a-zàèéìòù]{4,}", t.lower())}


db = sqlite3.connect(DB)
esiti = []
for nid in RICORDI:
    g = np.load(f"{STORE}/{nid}.npy")
    testo_nodo = db.execute("SELECT testo FROM nodi WHERE id=?", (nid,)).fetchone()[0]
    ref = parole(testo_nodo)
    for dom in DOMANDE:
        cond = condizioni(g)
        for nome, griglia in cond.items():
            r = ponte.chiedi_su_vettori(griglia, dom, n_predict=120).strip()
            aderenza = len(parole(r) & ref) / max(len(ref), 1)
            esiti.append({"ricordo": nid, "condizione": nome, "domanda": dom[:40],
                          "risposta": r, "aderenza_al_ricordo": round(aderenza, 3)})
            print(f"[{nid} {nome:11s}] ader {aderenza:.2f}: {r[:110]!r}")
        # ASSENTE: stessa domanda, nessun blocco visivo
        seq = ponte.componi("<|im_start|>user\n" + dom +
                            "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
        r = ponte.completa(seq, n_predict=120).strip()
        esiti.append({"ricordo": nid, "condizione": "assente", "domanda": dom[:40],
                      "risposta": r, "aderenza_al_ricordo":
                      round(len(parole(r) & ref) / max(len(ref), 1), 3)})
        print(f"[{nid} assente    ] {r[:110]!r}")

# sintesi: aderenza media per condizione (il numero che decide)
per_cond = {}
for e in esiti:
    per_cond.setdefault(e["condizione"], []).append(e["aderenza_al_ricordo"])
sintesi = {k: round(float(np.mean(v)), 3) for k, v in per_cond.items()}
json.dump({"sintesi_aderenza": sintesi, "esiti": esiti,
           "quando": time.strftime("%F %T")}, open(OUT, "w"),
          ensure_ascii=False, indent=1)
print("\nSINTESI aderenza media per condizione:", sintesi)
print("SONDA-COMPLETA ->", OUT)
