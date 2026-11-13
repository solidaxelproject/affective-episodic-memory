#!/usr/bin/env python3
"""Lux 1.23.0, prova B8 di RICERCA-LEGAMI-NUOVI.md (PIANO-PONTI-123.md Task 5): la stessa sequenza di messaggi in tre
condizioni, ognuna su una copia fresca del Lux 1.22.0: N (senza ponti), P (con i ponti), S (sensibilita': calo notturno
spento e K = 6). Ogni messaggio = 2 engrammi di un ricordo R preso a caso (seme fisso) fra i 10 ricordi del giorno; 50 messaggi per
giorno vissuto, poi la notte (pota_ponti). Umore a calma (OMEOSTATO assente). Misure per condizione:
- accesso: frazione di messaggi in cui R e' fra i ricordi dei tratti;
- esche: frazione dei tratti di un ricordo M != R che non condivide engrammi con R ed e' legato a R solo da un ponte;
- ricordo intero: ricomponi identico in tutte le condizioni (intrusioni 0); archi interni con richiamabilita' >= 0.5
  alla fine, centrali (terzo piu' alto per W nel ricordo) e periferici, differenza appaiata per ricordo con intervallo
  bootstrap al 95% (margine provvisorio 2 punti);
- ponti: nati, vivi alla fine, stabili.
Uso: cd engrammi && /data/venv-spacy/bin/python prova-ponti-b8/prova_ponti_b8.py [messaggi]"""
import json
import os
import random
import shutil
import sys
import tempfile
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))
T = tempfile.mkdtemp(prefix="b8-")
os.environ["LUX_DIR"] = f"{T}/lux"
os.environ["OMEOSTATO"] = f"{T}/nessuno.json"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

N_MSG = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
PER_GIORNO = 50
TEMI_DEL_GIORNO = 10   # senza temi che tornano nello stesso giorno nessun ponte viene catturato (prima corsa: 220 nati, 0)
ORIGINE = "/data/memoria-episodica-affettiva/engrammi/lux-1.22.0"
K0, CALO0 = X.PONTI_PER_RICHIAMO, X.PONTE_CALO   # i valori del piano, prima che gira() li cambi


def sequenza(L):
    rng = random.Random(13)
    buoni = [n for n in sorted(L.ricordi) if n not in L.errati and len({int(e) for j in L.per_ricordo.get(n, ())
                                                                        for e in L.A[j, 2:4]}) >= 4]
    out = []
    for i in range(N_MSG):
        if i % PER_GIORNO == 0:   # una giornata torna sugli stessi temi: 10 ricordi del giorno
            giorno = rng.sample(buoni, TEMI_DEL_GIORNO)
        r = rng.choice(giorno)
        eng = sorted({int(e) for j in L.per_ricordo[r] for e in L.A[j, 2:4]})
        out.append((r, " ".join(L.testi[e] for e in rng.sample(eng, 2))))
    return out


def gira(nome, k, calo):
    shutil.rmtree(f"{T}/lux", ignore_errors=True)
    shutil.copytree(ORIGINE, f"{T}/lux")
    X.PONTI_PER_RICHIAMO, X.PONTE_CALO = k, calo
    L = X.Lux()
    seq = sequenza(L)
    giorno0 = float(X.LUX.orologio())
    acc, esche, tratti, nati = 0, 0, 0, 0
    t0 = time.time()
    for i, (r, msg) in enumerate(seq):
        oggi = giorno0 + i // PER_GIORNO
        if i and i % PER_GIORNO == 0:
            X.pota_ponti()
            L.carica_stato()
        prima = set(L.ponti)
        out = L.ricombina(msg, oggi=oggi, ora=1.8e9 + 60 * i)
        nati += len(set(L.ponti) - prima)
        if not out:
            continue
        acc += r in out["nid"]
        eng_r = {int(e) for j in L.per_ricordo[r] for e in L.A[j, 2:4]}
        for m in out["nid"]:
            if m == r:
                continue
            tratti += 1
            eng_m = {int(e) for j in L.per_ricordo[m] for e in L.A[j, 2:4]}
            esche += (not eng_r & eng_m) and any((a in eng_r and b in eng_m) or (b in eng_r and a in eng_m)
                                                 for a, b in prima)   # i ponti di prima: quelli nati ora sono effetto
        if i % 100 == 99:
            print(f"{nome}: {i + 1} messaggi, {len(L.ponti)} ponti, {time.time() - t0:.0f} s", flush=True)
    X.pota_ponti()
    L.carica_stato()
    fine = giorno0 + N_MSG // PER_GIORNO
    R = X.LUX.curva(np.maximum(fine - L.U, 0.0), L.S)
    vive = {}
    for n, js in L.per_ricordo.items():
        js = np.asarray(js)
        cen = js[L.W[js] >= np.quantile(L.W[js], 2 / 3)]
        per = js[L.W[js] < np.quantile(L.W[js], 2 / 3)]
        vive[n] = (float((R[cen] >= 0.5).mean()) if len(cen) else np.nan,
                   float((R[per] >= 0.5).mean()) if len(per) else np.nan)
    ric = {n: L.ricomponi(n) for n in L.ricordi}
    st = sum(v[1] for v in L.ponti.values())
    return {"accesso": acc / N_MSG, "esche": esche / max(1, tratti), "nati": nati, "ponti": len(L.ponti),
            "stabili": int(st), "vive": vive, "ricomposti": ric}


def ic(d, seme=13):
    d = np.asarray([x for x in d if np.isfinite(x)])
    rng = np.random.default_rng(seme)
    b = [rng.choice(d, len(d)).mean() for _ in range(2000)]
    return float(d.mean()), float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))


if __name__ == "__main__":
    res = {"N": gira("N", 0, CALO0), "P": gira("P", K0, CALO0),
           "S": gira("S", 6, 1.0)}
    out = {"messaggi": N_MSG, "per_giorno": PER_GIORNO}
    for c in ("N", "P", "S"):
        out[c] = {k: res[c][k] for k in ("accesso", "esche", "nati", "ponti", "stabili")}
    for c in ("P", "S"):
        assert res[c]["ricomposti"] == res["N"]["ricomposti"], f"{c}: ricomposizione cambiata (intrusione)"
        nid = sorted(res["N"]["vive"])
        for i, parte in enumerate(("centrali", "periferici")):
            out[c][f"{parte}_diff"] = ic([res[c]["vive"][n][i] - res["N"]["vive"][n][i] for n in nid])
    out["N"]["centrali"] = float(np.nanmean([v[0] for v in res["N"]["vive"].values()]))
    out["N"]["periferici"] = float(np.nanmean([v[1] for v in res["N"]["vive"].values()]))
    json.dump(out, open(f"{QUI}/risultati.json", "w"), indent=1)
    print(json.dumps(out, indent=1))
    shutil.rmtree(T)
