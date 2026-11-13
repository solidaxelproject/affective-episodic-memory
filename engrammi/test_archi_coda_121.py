#!/usr/bin/env python3
"""test della 1.21.0 (PIANO-FASE2-C-ARCHI-E-CODA.md): coda, archi fra ricordi, predisposizione dall'arco, avvicina,
dominante ricalcolata, da_precedente. Su una COPIA della 1.20.0 (LUX_DIR temporanea).
Uso: cd engrammi && /data/venv-spacy/bin/python test_archi_coda_121.py"""
import copy
import json
import os
import tempfile

T = tempfile.mkdtemp(prefix="ac121-", dir=os.environ.get("TMPDIR"))
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

# in_coda (D4): i nuovi passano avanti ai vecchi che battono, non fra loro
batte = {(3, 2), (4, 2), (4, 1), (4, 3)}
b = lambda n, v: (n, v) in batte  # noqa: E731
assert X.in_coda([1, 2], [3], b) == [1, 3, 2]
assert X.in_coda([1, 2], [3, 4], b) == [1, 3, 4, 2], "4 ha scavalcato 3, della sua stessa selezione"
assert X.in_coda([], [5, 6], b) == [5, 6]

# da_precedente: copia identica della 1.20.0; avvicina_da, che la migrazione della 1.21.0 metteva a oggi vissuto, qui a
# mano (dalla 1.22.0 da_precedente copia e basta)
X.PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.20.0"
X.da_precedente()
z0, zp = np.load(X.NPZ), np.load(f"{X.PRECEDENTE}/lux.npz")
assert set(z0.files) == set(zp.files)
assert all(np.array_equal(z0[k], zp[k], equal_nan=zp[k].dtype.kind == "f") for k in zp.files)
assert json.load(open(X.META)) == json.load(open(f"{X.PRECEDENTE}/lux-meta.json"))
z = dict(z0)
z["avvicina_da"] = np.float64(X.LUX.orologio())
np.savez(X.NPZ, **z)
oggi = float(z["avvicina_da"])

L = X.Lux()
dom = lambda n: L.ricordi[n].get("dominante")  # noqa: E731

# un indizio vero con firme miste nelle prime 4 catene
testi = [v["testo"] for v in map(json.loads, open(X.GIORNATA)) if isinstance(v.get("testo"), str) and len(v["testo"]) > 20]
for t in reversed(testi):
    scelta = [n for n, _ in L.richiama(t, len(L.ricordi), oggi=oggi, ora=1.8e9)]
    sel = [k[0] for k in L._catene(scelta, set(), 4, stessa=False)]
    if len(sel) >= 3 and len({dom(n) for n in sel}) >= 2:
        break
else:
    raise SystemExit("nessun indizio con firme miste")

# coda vuota = step b; la selezione diversa resta in coda; archi fra tutte le coppie della selezione
L2 = X.Lux()
L2.salva_stato = lambda: None
attesi = [n for n, _, _ in L2.consegna(t, 4, oggi=oggi, ora=1.8e9)]
coda = []
c = L.consegna(t, 4, oggi=oggi, ora=1.8e9, coda=coda)
dati = [n for n, _, _ in c]
assert dati == attesi, (dati, attesi)
assert coda == [L.ricordi[n]["codice"] for n in sel if n not in dati], (coda, sel, dati)
coppie = {(min(a, b), max(a, b)) for i, a in enumerate(sel) for b in sel[i + 1:]}
assert coppie <= set(L.archi_ric) and all(L.archi_ric[k][2:] == [1, 1] for k in coppie), L.archi_ric
assert X.Lux().archi_ric == L.archi_ric, "archi fra ricordi non salvati su disco"

# messaggio che non richiama niente: esce la testa della coda (con quelli della sua dominante), nessun arco nuovo
prima = copy.deepcopy(L.archi_ric)
testa = L.da_codice[coda[0]]
c2 = L.consegna("zqxw vbnm", 4, oggi=oggi, ora=1.8e9 + 60, coda=coda)
d2 = [n for n, _, _ in c2]
assert d2[0] == testa and all(dom(n) == dom(testa) for n in d2), d2
assert L.archi_ric == prima, "la testa della coda si e' legata a una selezione che non era la sua"
assert all(L.ricordi[n]["codice"] not in coda for n in d2)
# un codice in coda gia' dato da qlux (esclusi) esce dalla coda e non si consegna
coda = [L.ricordi[n]["codice"] for n in sel]
k = coda[0]
c3 = L.consegna("zqxw vbnm", 4, oggi=oggi, ora=1.8e9 + 120, coda=coda, esclusi=[k])
assert c3 and k not in coda and L.da_codice[k] not in [n for n, _, _ in c3], (k, coda, c3)

# predisposizione dall'arco (D1): consegnato a, b riceve la spinta della forza dell'arco
a, bb = sorted(coppie)[0]
L3 = X.Lux()
L3.salva_stato = lambda: None
L3.pronti = {}
L3.predisponi([a], 1.8e9, oggi)
con = L3.spinta(bb, 1.8e9)
L3.pronti, L3.archi_ric = {}, {}
L3.predisponi([a], 1.8e9, oggi)
senza = L3.spinta(bb, 1.8e9)
assert abs(con - senza - X.PESO_ARCO_RICORDI / np.sqrt(L3.ricordi[bb]["n"])) < 1e-9, (con, senza)

# avvicina: rodaggio 10% il primo giorno, i profili dei due si avvicinano, P azzerato, la seconda volta niente
diversi = [k for k in coppie if dom(k[0]) != dom(k[1])]
assert diversi
x, y = diversi[0]


def profilo(Lx, n):
    js = [j for j in Lx.per_ricordo[n] if Lx.C0[j].any()]
    return np.mean(Lx.C[js] / Lx.W[js, None], 0)


Lp = X.Lux.struttura(X.DIR)
d_prima = np.abs(profilo(Lp, x) - profilo(Lp, y)).sum()
S_prima = np.load(X.STATO)["S"].copy()
r = X.avvicina(oggi + 1)
assert r["rodaggio"] == 0.1 and r["archi"] == len(L.archi_ric) and r["spostati"] > 0, r
Ld = X.Lux.struttura(X.DIR)
assert np.abs(profilo(Ld, x) - profilo(Ld, y)).sum() < d_prima, "le firme non si sono avvicinate"
s = np.load(X.STATO)
assert (s["RA_P"] == 0).all() and not np.array_equal(s["S"], S_prima)
assert X.avvicina(oggi + 2)["archi"] == 0, "co-selezioni lavorate due volte"
# D5: la dominante si ricalcola dalla carica e la nascita resta. Se il primo giorno nessuna e' cambiata, tante
# co-selezioni a rodaggio pieno su una coppia ancora diversa
if not any("dominante_nascita" in v for v in json.load(open(X.META))["ricordi"].values()):
    mm = json.load(open(X.META))["ricordi"]
    x, y = next(k for k in diversi if mm[str(k[0])]["dominante"] != mm[str(k[1])]["dominante"])
    s = dict(np.load(X.STATO))
    i = [tuple(v) for v in s["RA"].tolist()].index((x, y))
    s["RA_P"][i] = 400
    np.savez(X.STATO + ".tmp.npz", **s)
    os.replace(X.STATO + ".tmp.npz", X.STATO)
    r = X.avvicina(oggi + 40)
    assert r["rodaggio"] == 1.0 and r["dominanti"] >= 1, r
m = json.load(open(X.META))["ricordi"]
cambiato = next(int(n) for n, v in m.items() if "dominante_nascita" in v)
Ln = X.Lux()
assert m[str(cambiato)]["dominante"] != m[str(cambiato)]["dominante_nascita"]


def pesi(Lx, n, e, C):
    w = {}
    for j in Lx.per_ricordo[n]:
        if Lx.C0[j].any():
            for i in {int(Lx.A[j, 2]), int(Lx.A[j, 3])}:
                w[i] = w.get(i, 0.0) + float(C[j, e])
    return w


nuova, nasc = (X.EMOZIONI.index(m[str(cambiato)][k]) for k in ("dominante", "dominante_nascita"))
w = pesi(Ln, cambiato, nuova, Ln.C)
atteso = sum(v * float(Ln.F[i, nuova]) for i, v in w.items()) / sum(w.values())
assert abs(Ln.forza(cambiato, m[str(cambiato)]["dominante"]) - atteso) < 1e-9, "forza della dominante presa dopo"
w, w0 = pesi(Ln, cambiato, nasc, Ln.C), sum(pesi(Ln, cambiato, nasc, Ln.C0).values())
atteso = sum(v * float(Ln.F0[i, nasc]) for i, v in w.items()) / w0
assert abs(Ln.forza(cambiato, m[str(cambiato)]["dominante_nascita"]) - atteso) < 1e-9, "formula della nascita cambiata"

# stessa dominante: un arco con co-selezioni nuove non sposta niente (e P si consuma)
per_dom = {}
for n, v in Ln.ricordi.items():
    if n < X.PRIMO_CORREZIONE and v.get("dominante"):
        per_dom.setdefault(v["dominante"], []).append(n)
u, v = next(sorted(g[:2]) for g in per_dom.values() if len(g) >= 2)
s = dict(np.load(X.STATO))
s["RA"] = np.concatenate([s["RA"], [[u, v]]])
for c, val in (("S", X.LUX.S_BASE), ("U", oggi + 40), ("N", 1), ("P", 1)):
    s[f"RA_{c}"] = np.concatenate([s[f"RA_{c}"], np.asarray([val], s[f"RA_{c}"].dtype)])
np.savez(X.STATO + ".tmp.npz", **s)
os.replace(X.STATO + ".tmp.npz", X.STATO)
Cp = np.load(X.NPZ)["C"].copy()
r = X.avvicina(oggi + 41)
assert r["archi"] == 1 and r["spostati"] == 0 and np.array_equal(np.load(X.NPZ)["C"], Cp), r
assert (np.load(X.STATO)["RA_P"] == 0).all()

# aggiungi dopo avvicina: avvicina_da resta (revisione 1)
nid = max(L.ricordi) + 1
X._aggiungi([(nid, "Il gatto rosso dorme sul davanzale della cucina.", L.ricordi[x]["firma"], "vissuto", 1.8e9,
              {"dominante": dom(x), "fonte": "prova", "cattura": None, "salienza": None, "voluto": False})])
assert "avvicina_da" in np.load(X.NPZ).files, "aggiungi ha perso avvicina_da"
assert X.Lux().archi_ric, "aggiungi ha perso gli archi fra ricordi"
print(f"selezione {sel}, dati {dati}, coda dopo {len(coda)}, archi {len(L.archi_ric)}, cambiato {cambiato}")
print("TUTTI I TEST DELLA 1.21.0 VERDI")
