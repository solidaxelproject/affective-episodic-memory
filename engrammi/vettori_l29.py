#!/usr/bin/env python3
"""Vettori L29 degli engrammi (11/10/2026), su CPU, dagli stati gia' letti (engrammi/stati/<nid>.npz).
Per ogni ricordo: la catena dei suoi engrammi (dagli archi del Lux), ogni engramma ritrovato nel testo
originale in ordine, i token che ci cadono dentro (meno il token 0, pozzo dell'attenzione) mediati, portati
in coordinate lente (ponte.trasporta), meno la base, normalizzati: lo stesso spazio di addr-sem del riflesso.
Un engramma condiviso = media delle sue occorrenze. Uscita: lux-<VERSIONE>/lux-l29.npz (L, presente).
Gira nel venv jspace (ponte): /data/jspace/venv/bin/python vettori_l29.py <cartella della versione>
ponytail: ricerca del testo in ordine; un engramma non ritrovato (formattazione tolta, testo oltre i 1024 token
letti) resta senza vettore L29 e conta solo la via bge-m3"""
import json
import os
import re
import sys

import numpy as np

sys.path[:0] = ["/data/memoria-episodica-affettiva", "/data/jspace", "/data/jspace/jacobian-lens"]
import ponte  # noqa: E402

DIR = sys.argv[1]
STATI = "/data/memoria-episodica-affettiva/engrammi/stati"

z = np.load(f"{DIR}/lux.npz")
A = z["A"]
meta = json.load(open(f"{DIR}/lux-meta.json"))
testi = meta["engrammi"]
orig = {int(k): r["testo"] for k, r in meta["ricordi"].items()
        if r["classe"] != "correzione"}   # 1.20.0: dal meta del Lux (prima memoria.db)
base = ponte.base_lente()

def cerca(engramma, testo, da):
    """l'engramma nel testo originale da 'da' in poi: maiuscole libere (gli engrammi condivisi tengono la forma
    della prima occorrenza), spazi e formattazione tolta dal taglio (* _ ` virgolette) liberi fra le parole"""
    parole = [re.escape(p) for p in engramma.split()]
    return re.compile(r"[\s*_`\"'«»“”]+".join(parole), re.I).search(testo, da) if parole else None


catene = {}
for r, pos, a, b in A[:, :4].tolist():
    catene.setdefault(r, []).append((pos, a, b))
somma = np.zeros((len(testi), 2048), np.float64)
quante = np.zeros(len(testi), np.int64)
trovati = mancati = 0
for r, archi in catene.items():
    f = f"{STATI}/{r}.npz"
    if not os.path.exists(f):
        continue
    s = np.load(f)
    h, offs = s["h"].astype(np.float32), s["offs"]
    archi.sort()
    seq = [archi[0][1]] + [b for pos, a, b in archi if pos > 0]
    t, cur, M = orig[r], 0, []
    for e in seq:
        m = cerca(testi[e], t, cur)
        if not m:
            mancati += 1
            continue
        i, j = m.span()
        cur = j
        tok = [k for k in range(1, len(offs)) if offs[k][1] > i and offs[k][0] < j]
        if not tok:
            mancati += 1
            continue
        M.append((e, h[tok].mean(0)))
        trovati += 1
    if M:
        V = ponte.trasporta(np.stack([m for _, m in M])) - base
        V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
        for (e, _), v in zip(M, V):
            somma[e] += v
            quante[e] += 1
L = somma / np.maximum(quante, 1)[:, None]
L /= np.linalg.norm(L, axis=1, keepdims=True) + 1e-9
np.savez(f"{DIR}/lux-l29.npz", L=L.astype(np.float16), presente=quante > 0)
print(f"occorrenze ritrovate {trovati}, mancate {mancati}; engrammi con vettore L29 {int((quante > 0).sum())}/{len(testi)}")
