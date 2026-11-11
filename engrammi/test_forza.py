#!/usr/bin/env python3
"""test di Lux.forza (PIANO-STEERING-RIFLESSO.md punto 7a, 11/11): dominante e S_e del punto 7 di PIANO-LUX-FASI, sola
lettura; la dominante e' emo_tag di memoria.db (memoria.dominante dal 09/11, memoria vuole torch e il Lux no). Uso: cd engrammi && /data/venv-spacy/bin/python test_forza.py"""
import sqlite3

import numpy as np

import lux_engrammi as X

L = X.Lux.struttura(X.DIR)
c = sqlite3.connect(f"file:{X.T.DB}?mode=ro", uri=True)
dom = {n: e for n, e in c.execute("select id, emo_tag from nodi") if n in L.ricordi}
S, nessuno = [], 0
for nid, emo in dom.items():
    s = L.forza(nid, emo)
    if s is None:
        nessuno += 1
        continue
    S.append(s)
# la misura del punto 5 (633 ricordi del Lux 1.13.0: mediana 1.13) valeva sulla firma grezza; dalla 1.15.0 la carica
# e' firma x fattore e S_e scende col fattore della dominante (test_tabella_115.py)
assert len(S) >= 633, len(S)

# a mano su un ricordo: S_e = media delle F_i,e pesata con w_i (w0 = w finche' C0 non esiste)
nid = next(n for n in sorted(dom) if L.forza(n, dom[n]) is not None)
js = [j for j in L.per_ricordo[nid] if L.C[j].any()]
e = X.EMOZIONI.index(dom[nid])
w = {}
for j in js:
    a, b = (int(v) for v in L.A[j, 2:4])
    for i in {a, b}:
        w[i] = w.get(i, 0.0) + float(L.C[j, e])
atteso = sum(wi * float(L.F[i, e]) for i, wi in w.items()) / sum(w.values())
assert abs(L.forza(nid, dom[nid]) - atteso) < 1e-6
assert L.forza(-5, "joy") is None and L.forza(nid, "nessuna") is None, "ricordo o emozione sconosciuti"
print(f"test_forza: ok ({len(S)} ricordi, {nessuno} senza forza)")
