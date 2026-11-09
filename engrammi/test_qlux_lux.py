#!/usr/bin/env python3
"""test di consegna con quanti, soglia e finestra di tempo (PIANO-MEMORINVOLONTARIA-LUX.md, l'utente 09/11): niente
scritture sullo stato vero (salva_stato disattivato). I ts si prendono da memoria.db solo in RAM, come fara' la
migrazione. Uso: cd engrammi && /data/venv-spacy/bin/python test_qlux_lux.py"""
import sqlite3

import lux_engrammi as X

T = X.T   # taglia: DB = memoria.db

L = X.Lux()
L.salva_stato = lambda: None
c = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
for nid, ts in c.execute("select id, ts from nodi"):
    if nid in L.ricordi:
        assert L.ricordi[nid]["codice"] == X.codice(ts)
        L.ricordi[nid]["ts"] = ts
indizio = L.ricomponi(sorted(L.ricordi)[len(L.ricordi) // 3])[:120]   # un pezzo di un ricordo vero
# un ricordo per volta
uno = L.consegna(indizio, quanti=1)
assert len(L.catena(uno[0][0])) == len(uno), uno
# soglia 0: anche sotto la soglia di sempre, il piu' vicino
basso = "parola"
assert L.consegna(basso, quanti=1, soglia=0, ora=float("inf"))
# finestra di tempo: solo ricordi nati li'
ts = sorted(r["ts"] for r in L.ricordi.values() if "ts" in r)
da, a = ts[len(ts) // 2], ts[len(ts) // 2] + 86400
dentro = {n for n, r in L.ricordi.items() if da <= r.get("ts", -1) < a}
assert dentro
for testo in (indizio, ""):   # testo vuoto: il ricordo della finestra coi punti (facilita') piu' alti
    r = L.consegna(testo, quanti=1, soglia=0, da=da, a=a, ora=float("inf"))
    assert r and r[0][0] in dentro, (testo, r)
# finestra: il testo accende solo ricordi gia' esclusi -> il resto della finestra
x = L.consegna(indizio, quanti=1, soglia=0, da=da, a=a, ora=float("inf"))
y = L.consegna(indizio, quanti=1, soglia=0, da=da, a=a, esclusi=[x[0][1]], ora=float("inf"))
assert len(dentro) == 1 or (y and y[0][0] != x[0][0] and y[0][0] in dentro), (x, y)
# finestra vuota = nessun ricordo
assert L.consegna(indizio, quanti=1, soglia=0, da=1.0, a=2.0) == []
# esclusi: la seconda volta il successivo
primo = L.consegna(testo := "", quanti=1, soglia=0, da=da, a=a, ora=float("inf"))
secondo = L.consegna("", quanti=1, soglia=0, da=da, a=a, esclusi=[primo[0][1]], ora=float("inf"))
assert len(dentro) == 1 or (secondo and secondo[0][0] != primo[0][0])
# default invariato: fino a CONSEGNA_MAX, soglia di sempre
assert len({L.catena(n)[0] for n, _, _ in L.consegna(indizio)}) <= X.CONSEGNA_MAX
# _inserisci scrive il ts per tutti i ricordi
ricordi = {}
X._inserisci([(1, "un ricordo di prova per il ts", None, "vissuto", 123.0)], {}, [], [], {}, [], [], ricordi)
assert ricordi[1]["ts"] == 123.0 and ricordi[1]["codice"] == X.codice(123.0)
print("TUTTO VERDE")
