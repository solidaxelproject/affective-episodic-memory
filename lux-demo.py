# Battesimo della GWR: le memorie REALI di Agente entrano nell'organo
# in ordine cronologico. Mostra: curva di crescita, fusioni, richiami.
import json
import sqlite3
import sys

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva")
from lux import Lux

DB = "/data/workspace/memoria/memoria.db"
VEC = "/data/workspace/memoria/vettori.pt"

v = torch.load(VEC, weights_only=True)
c = sqlite3.connect(DB)
righe = c.execute("SELECT id, ts, firma, emo_tag, testo, classe FROM nodi "
                  "ORDER BY ts").fetchall()
righe = [r for r in righe if r[0] in v]
print(f"{len(righe)} memorie da vivere")

stati = np.stack([v[r[0]]["addr_sem"].numpy() for r in righe])
g = Lux()
g.fit_encoder(stati)

nati = rinforzati = 0
curva = []
for i, r in enumerate(righe):
    firma = json.loads(r[2])
    f51 = np.array([firma[e] for e in sorted(firma)], np.float32)
    _, esito = g.esperisci(stati[i], f51, nodo_id=r[0])
    nati += esito == "nato"
    rinforzati += esito == "rinforzato"
    curva.append(len(g.tracce))

print(f"\nCURVA DI CRESCITA (esperienze -> neuroni):")
for x in range(9, len(curva), 10):
    print(f"  dopo {x+1:3d} esperienze: {curva[x]:3d} neuroni")
print(f"\nnati: {nati}, rinforzati (esperienze familiari fuse): {rinforzati}")
print(f"stats: {g.stats()}")

emos = sorted(json.loads(righe[0][2]))
def testo_di(nid):
    r = c.execute("SELECT testo, emo_tag FROM nodi WHERE id=?", (nid,)).fetchone()
    return (r[0][:90].replace("\n", " "), r[1]) if r else ("?", "?")

for emo in ("love", "fear", "curiosity"):
    q = np.zeros(len(emos), np.float32)
    q[emos.index(emo)] = 1.0
    print(f"\nRICHIAMO via emotiva [{emo}]:")
    for hit in g.richiama(q, via="emotiva", k=2):
        t, tag = testo_di(hit["nodo_id"])
        print(f"  n{hit['neurone']} (sim {hit['sim']}, tag {tag}): {t}")

g.salva()
print(f"\norgano salvato: {g.stats()['neuroni']} neuroni")
