#!/usr/bin/env python3
"""Fase 2 step b (l'utente 09/11 + 11/11, PIANO-FASE2-B-STESSA-FIRMA.md): i ricordi consegnati insieme hanno la stessa
dominante del primo; gli altri non si consegnano e non si rinforzano. Lux vero in sola lettura (salva_stato spento)."""
import copy
import json

import lux_engrammi as X

# _catene da solo, con correzioni finte: la catena conta la dominante dell'originale
F = X.Lux.__new__(X.Lux)
F.ricordi = {1: {"dominante": "joy"}, 2: {"dominante": "fear"}, 3: {"dominante": "joy"}, 4: {"dominante": None},
             5: {"dominante": "joy"}, 6: {"dominante": "joy"}, 7: {"dominante": "joy"}}
F.corregge, F.corretto_da = {4: 3}, {3: [4]}   # 4 corregge 3
assert F._catene([1, 2, 3, 5, 6, 7], set(), 4) == [[1], [3, 4], [5], [6]]   # 2 escluso, 4 viaggia con 3
assert F._catene([4, 1, 2], set(), 4) == [[3, 4], [1]]                     # la correzione porta la dominante di 3
assert F._catene([2, 1, 3], set(), 4) == [[2]]                             # firme tutte diverse: uno solo
assert F._catene([1, 2, 3], {1}, 4) == [[2]]                              # gia' nel contesto: si salta, decide il dopo
F.ricordi[8] = {"dominante": None}
assert F._catene([8, 1], set(), 4) == [[8]]                                # senza dominante: esce da solo
assert F._catene([1, 2, 3], set(), 1) == [[1]]

# Lux vero: indizi della giornata
L = X.Lux()
L.salva_stato = lambda: None
testi = [v["testo"] for v in map(json.loads, open(X.GIORNATA)) if isinstance(v.get("testo"), str) and len(v["testo"]) > 20][-40:]
base = {k: copy.deepcopy(getattr(L, k)) for k in ("S", "U", "R", "pronti")}


def rimetti():
    for k, v in base.items():
        setattr(L, k, copy.deepcopy(v))


dom = lambda n: L.ricordi[L.catena(n)[0]].get("dominante")
misti = insieme = 0
for t in testi:
    rimetti()
    uno = L.consegna(t, 1, oggi=100.0, ora=1.8e9)
    rimetti()
    tutti = [n for n, _ in L.richiama(t, len(L.ricordi), oggi=100.0, ora=1.8e9)]
    c = L.consegna(t, 4, oggi=100.0, ora=1.8e9)
    nids = [n for n, _, _ in c]
    attesi = []   # le prime 4 catene di richiama con la dominante della prima (revisione del piano, T5)
    for n in tutti:
        r = L.catena(n)[0]
        if len(attesi) < 4 and r not in attesi and (not attesi or dom(r) is not None and dom(r) == dom(attesi[0])):
            attesi.append(r)
    assert [L.catena(n)[0] for n in nids] == attesi, (t, nids, attesi)
    assert [x[0] for x in uno] == nids[:len(uno)], t                       # il primo e' quello di quanti=1
    assert len({dom(n) for n in nids}) <= 1, (t, [dom(n) for n in nids])
    fuori = [n for n in tutti if n not in nids]
    if c and any(dom(n) != dom(nids[0]) for n in fuori):
        misti += 1
    for n in fuori:   # non consegnati: niente rinforzo, niente ultimo richiamo
        js = L.per_ricordo.get(n, [])
        assert (L.U[js] == base["U"][js]).all() and (L.S[js] == base["S"][js]).all(), n
        assert L.R.get(n) == base["R"].get(n), n
    insieme += len(nids) > 1
print(f"{len(testi)} indizi: {insieme} consegne con piu' ricordi della stessa firma, {misti} con ricordi di firma diversa lasciati fuori")
assert misti > 0 and insieme > 0
print("OK")
