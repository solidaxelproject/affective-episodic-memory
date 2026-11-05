#!/usr/bin/env python3
"""Taratura delle due soglie della persistenza sul Lux degli engrammi (PIANO-FIRMA-ENGRAMMI.md, B5).
Criterio del 30/09 (persistenza.py): eco falsa sotto il 5% per messaggio. Per ogni ricordo vero il punteggio massimo
contro gli ALTRI ricordi (lui e la sua catena di correzioni esclusi); soglia = 95 percentile.
  eco:  Lux.richiama del testo del ricordo (senza predisposizione, come il /richiama del servizio)
  temi: coseno bge-m3 del messaggio intero
Sola lettura. Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/venv-spacy/bin/python taratura_persistenza.py"""
import json
import sqlite3

import numpy as np

import lux_engrammi as X
import taglia as T

MAX_CAR = 6000   # come persistenza.MAX_CAR: bge-m3 (:8094) legge al massimo 2048 token
L = X.Lux()
c = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
testi = dict(c.execute("select id, testo from nodi where testo != ''"))
nids = sorted(n for n in L.ricordi if n in testi)
eco = []
for n in nids:
    fuori = set(L.catena(n))
    r = [p for m, p in L.richiama(testi[n], len(L.ricordi), soglia=0, ora=float("inf")) if m not in fuori]
    eco.append(r[0] if r else 0.0)
eco = np.asarray(eco)
E = X.embed([testi[n][:MAX_CAR] for n in nids])
S = E @ E.T
np.fill_diagonal(S, -1)
temi = S.max(1)
out = {"ricordi": len(nids),
       "eco": {"p95": float(np.percentile(eco, 95)), "p50": float(np.median(eco)), "max": float(eco.max())},
       "temi": {"p95": float(np.percentile(temi, 95)), "p50": float(np.median(temi)), "max": float(temi.max())}}
json.dump(out, open("taratura-persistenza.json", "w"), indent=1)
print(json.dumps(out, indent=1))
for nome, v in (("eco", eco), ("temi", temi)):   # le coppie sopra soglia, per leggerle
    for i in np.argsort(-v)[:5]:
        print(nome, round(float(v[i]), 3), testi[nids[i]][:80].replace("\n", " "))
