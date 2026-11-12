#!/usr/bin/env python3
"""test della 1.18.0 (PIANO-1.18-SBIADIMENTO.md): sbiadimento di notte col freno, rodaggio, una volta per giorno,
C0, S e S0 fermi. Su una COPIA (LUX_DIR temporanea), omeostato finto. Uso: cd engrammi && /data/venv-spacy/bin/python test_sbiadimento_118.py"""
import json
import os
import shutil
import tempfile

T = tempfile.mkdtemp(prefix="sb118-", dir=os.environ.get("TMPDIR"))
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402
import salienza as SA  # noqa: E402

X.PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.20.0"   # 1.21.0 (prima 1.18.0): da_precedente = copia identica
X.OMEOSTATO = f"{T}/stato.json"
json.dump({"ts": 0, "stato": {"anxiety": 3.0, "sadness": 0.5}}, open(X.OMEOSTATO, "w"))
assert X._umore() == 1.0
json.dump({"ts": 0, "stato": {"anxiety": 1.0, "sadness": -2.0}}, open(X.OMEOSTATO, "w"))
assert X._umore() == 0.5
X.da_precedente()
zz = dict(np.load(X.NPZ))   # 1.19.0: il rodaggio come lo metteva la migrazione della 1.18.0 (oggi vissuto)
zz.update(sbiadimento_da=np.float64(X.LUX.orologio()), sbiadito_fino=np.float64(X.LUX.orologio()))
np.savez(X.NPZ + ".tmp.npz", **zz)
os.replace(X.NPZ + ".tmp.npz", X.NPZ)
z0 = np.load(X.NPZ)
oggi = float(z0["sbiadito_fino"])
assert float(z0["sbiadimento_da"]) == oggi
assert X.sbiadisci(oggi)["sbiadito"] is False, "nello stesso giorno della produzione non sbiadisce"

s = np.load(X.STATO)
L = X.Lux.struttura(X.DIR)
r = X.sbiadisci(oggi + 1)
assert r["sbiadito"] and r["rodaggio"] == 0.1 and r["umore"] == 0.5, r
z = np.load(X.NPZ)
f = X.freno_archi(z0["A"], s["S"], s["S0"], (z0["E_nato"], z0["E_acceso"], z0["E_accensioni"]), SA.ranghi(z0), L.errati,
                  oggi + 1)
neg = np.asarray([e not in X.POSITIVE and e not in X.NEUTRE for e in X.EMOZIONI])
atteso = z0["C"] * (1 - 0.1 * z0["sbiadimento"][None, :] * f[:, None] * np.where(neg, 0.75, 1.0)[None, :])
assert np.allclose(z["C"], atteso, rtol=1e-6, atol=1e-7), "formula del punto 4"
assert np.array_equal(z["C0"], z0["C0"]) and np.allclose(z["F"], X.firme_engrammi(z["A"], z["C"], len(z["V"])))
assert all(np.array_equal(np.load(X.STATO)[k], s[k]) for k in ("S", "S0", "U")), "lo sbiadimento ha toccato S o S0"
assert (np.sign(z["C"]) == np.sign(z0["C"])).all() and (np.abs(z["C"]) <= np.abs(z0["C"])).all(), "segno o crescita"
assert ((f > 0) & (f <= 1)).all(), "freno fuori da (0, 1]"
assert X.sbiadisci(oggi + 1)["sbiadito"] is False, "due volte nello stesso giorno"
# la forza scende come la carica (l'utente 11/11, D3): con C x k su tutti gli archi del ricordo la forza fa x k
L2 = X.Lux.struttura(X.DIR)
nid = next(n for n in sorted(L2.ricordi) if L.forza(n, "joy"))
L2.C = L2.C0.copy()
js = L2.per_ricordo[nid]
L2.C[js] *= 0.5
assert abs(L2.forza(nid, "joy") - 0.5 * L.forza(nid, "joy")) < 1e-6, "la forza deve scendere come la carica"
assert np.array_equal(L2.F0, X.firme_engrammi(L2.A, L2.C0, len(L2.V)))

# colpa (emivita 3650) sbiadisce molto meno della sorpresa (30), a parita' di arco
ec, es = X.EMOZIONI.index("guilt"), X.EMOZIONI.index("surprise")
j = int(np.nonzero((z0["C"][:, ec] != 0) & (z0["C"][:, es] != 0))[0][0])
dc = 1 - z["C"][j, ec] / z0["C"][j, ec]
ds = 1 - z["C"][j, es] / z0["C"][j, es]
assert 0 < dc < ds / 50, (dc, ds)

# rodaggio pieno dopo 30 giorni; il freno abbassa lo sbiadimento (ripetizione, tema aperto, importanza)
r = X.sbiadisci(oggi + 40)
assert r["rodaggio"] == 1.0 and 0 < r["freno_medio"] < 1, r
# un ricordo corretto ha il tema chiuso: aperta = 0 (stesso freno di un arco senza riaccensioni, a parita' del resto)
E = (z0["E_nato"].copy(), z0["E_acceso"].copy(), z0["E_accensioni"].copy())
E[2][:] = 3
E[0][:] = 0
E[1][:] = int(oggi)
nid = int(z0["A"][0, 0])
fa = X.freno_archi(z0["A"], s["S"], s["S0"], E, SA.ranghi(z0), set(), oggi)
fe = X.freno_archi(z0["A"], s["S"], s["S0"], E, SA.ranghi(z0), {nid}, oggi)
k = z0["A"][:, 0] == nid
assert (fe[k] > fa[k]).all() and np.array_equal(fe[~k], fa[~k]), "il ricordo corretto deve sbiadire senza freno del tema"
shutil.rmtree(T)
print(f"test_sbiadimento_118: TUTTO VERDE (freno medio {float(f.mean()):.3f}, colpa {dc:.2e} contro sorpresa {ds:.2e} a notte)")
