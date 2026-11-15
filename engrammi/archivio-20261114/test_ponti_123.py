#!/usr/bin/env python3
"""Lux 1.23.0 (PIANO-PONTI-123.md): ponti fra engrammi di ricordi diversi. Stato su una COPIA (LUX_DIR temporanea), il
resto sul Lux vero in sola lettura. Uso: cd engrammi && /data/venv-spacy/bin/python test_ponti_123.py"""
import os
import shutil
import tempfile

T = tempfile.mkdtemp(prefix="po123-")
shutil.copytree("/data/memoria-episodica-affettiva/engrammi/lux-1.22.0", f"{T}/lux")
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

# 1. stato: i ponti si salvano e si rileggono; un Lux senza PO parte senza ponti
L = X.Lux()
assert L.ponti == {}
L.ponti = {(3, 7): [0.1, 0, 1, 10, 11], (2, 9): [0.4, 1, 0, 12, 13]}
L.salva_stato()
assert X.Lux().ponti == {(3, 7): [0.1, 0, 1, 10, 11], (2, 9): [0.4, 1, 0, 12, 13]}
print("1 stato: ok", flush=True)

# 2. senza ponti ricombina e' identica alla 1.22.0; un ponte porta il ricordo dall'altra parte fra i candidati
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("lux122", "/data/memoria-episodica-affettiva/engrammi/lux_engrammi.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
L, L0 = X.Lux(), V.Lux()
L.salva_stato = L0.salva_stato = lambda: None
L.ponti = {}
t = "Ciao l'agente, oggi ho pensato alla casa al mare"
r, r0 = L.ricombina(t, oggi=100.0, ora=1.8e9), L0.ricombina(t, oggi=100.0, ora=1.8e9)
assert {k: r[k] for k in r0} == r0, (r, r0)
att = L.accendi(t)
x = max(att, key=att.get)
fuori = {n for n, _ in L.richiama(t, 30, soglia=0.0, oggi=100.0, ora=1.8e9)}
m = next(n for n in sorted(L.ricordi) if n not in fuori and n not in L.errati and L.per_ricordo.get(n))
e = next(int(v) for j in L.per_ricordo[m] for v in L.A[j, 2:4] if len(L.per_engramma[int(v)]) <= 2 and int(v) not in att)
L.ponti = {(min(x, e), max(x, e)): [1.0, 1, 0, *((L.A[next(iter(L.per_engramma[x])), 0], m) if x < e else (m, L.A[next(iter(L.per_engramma[x])), 0]))]}
pa, dal = L._dai_ponti(att)
assert pa == {e: min(1.0, att[x])} and dal == {m: min(1.0, att[x])} and L._dai_ponti({}) == ({}, {})
visti = []
frasi = L.frasi
L.frasi = lambda n: visti.append(n) or frasi(n)
L.ricombina(t, oggi=100.0, ora=1.8e9)
assert m in visti, "il ricordo raggiunto dal ponte non e' fra i candidati"
L.frasi = frasi
print("2 diffusione dai ponti: ok", flush=True)

# 3. nascita (B1, B2), cattura e rinforzo (B3), ramo discendente (B6)
L.ponti = {}
nati = None
for t in ["Ti ricordi la canzone che ti ho fatto sentire?", "Ciao l'agente, oggi ho pensato alla casa al mare",
          "Sono stanca, oggi al lavoro è stato un disastro"]:
    r = L.ricombina(t, oggi=100.0, ora=1.8e9)
    if r and L.ponti:
        nati = (t, r)
        break
assert nati, "nessun ponte nato su tre messaggi veri"
t, r = nati
att = L.accendi(t)
assert 1 <= len(L.ponti) <= X.PONTI_PER_RICHIAMO
coppie_ric = set()
for (a, b), (w, st, us, ra, rb) in L.ponti.items():
    assert w == X.PONTE_W0 and st == 0 and us == 1 and a < b
    assert (a, b) not in L.coppie and ra != rb and {ra, rb} <= set(r["nid"])
    assert min(1.0, att[a]) >= X.PONTE_A1 and min(1.0, att[b]) >= X.PONTE_A1
    assert np.log(L.fan[a]) < X.S_MAX and np.log(L.fan[b]) < X.S_MAX
    coppie_ric.add(frozenset((ra, rb)))
assert len(coppie_ric) == len(L.ponti), "piu' di un ponte per coppia di ricordi"
k = next(iter(L.ponti))
L.ponti[k][2] = 0
assert L._aggiorna_ponti(att)                                         # di nuovo forte-forte: cattura
w, st, us = L.ponti[k][:3]
assert st == 1 and us == 1 and abs(w - max(X.PONTE_W0 + X.PONTE_G * (1 - X.PONTE_W0), X.PONTE_W_CATTURA)) < 1e-12
a, b = k
prima = L.ponti[k][0]
assert L._aggiorna_ponti({a: 1.0, b: 0.35})                           # un capo forte, l'altro moderato
assert abs(L.ponti[k][0] - (prima - X.PONTE_D)) < 1e-9, L.ponti[k][0]
assert not L._aggiorna_ponti({a: 1.0}) and not L._aggiorna_ponti({})   # l'altro capo spento: niente
print("3 nascita, cattura, rinforzo, calo: ok", flush=True)

# 4. notte (B4): provvisori via, calo dei non usati tranne il 20% piu' forte, taglio, nessun tetto per engramma, segno
# azzerato
P = {(1, 2): [0.1, 0, 1, 5, 6], (1, 3): [0.9, 1, 0, 5, 7], (1, 4): [0.3, 1, 1, 5, 8], (1, 5): [0.3, 1, 0, 5, 9],
     (1, 6): [0.055, 1, 0, 5, 10]}
P.update({(100, 200 + i): [0.5, 1, 1, 11, 12] for i in range(10)})
L.ponti = {k: list(v) for k, v in P.items()}
X.Lux.salva_stato(L)
r = X.pota_ponti()
po = X.Lux().ponti
assert (1, 2) not in po and (1, 6) not in po, po                     # provvisorio; 0.055 x 0.82 sotto 0.05
assert po[(1, 3)][0] == 0.9 and po[(1, 4)][0] == 0.3                  # il piu' forte e l'usato non calano
assert abs(po[(1, 5)][0] - 0.3 * X.PONTE_CALO) < 1e-12
assert sum(a == 100 for a, _ in po) == 10                          # l'utente 13/11 notte: niente tetto per engramma
assert all(v[2] == 0 for v in po.values())
assert r == {"ponti": len(po), "provvisori": 1, "calati": 2, "tagliati": 1}, r
assert X.pota_ponti()["provvisori"] == 0
# revisione 13/11: pesi tutti uguali, mai usati: calano lo stesso (protetto solo il 20% per rango)
L.ponti = {(300, 400 + i): [0.28, 1, 0, 1, 2] for i in range(10)}
X.Lux.salva_stato(L)
assert X.pota_ponti()["calati"] == 8
print("4 notte: ok", flush=True)
shutil.rmtree(T)
