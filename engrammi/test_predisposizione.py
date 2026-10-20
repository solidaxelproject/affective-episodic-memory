#!/usr/bin/env python3
"""test della predisposizione (Lux 1.12.0): niente scritture sullo stato vero (salva_stato disattivato)"""
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
L2 = X.Lux()
L2.salva_stato = lambda: None
L2.U[:] = 1000.0                                                   # archi freschi, come test_archi_vivi
c = L2.consegna("Ci vuole un UPS", oggi=1000.0)
assert c and L2.pronti                                             # ha lasciato una predisposizione
print("test_predisposizione: ok")
