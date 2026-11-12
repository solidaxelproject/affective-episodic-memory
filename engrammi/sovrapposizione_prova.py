#!/usr/bin/env python3
"""Sovrapposizione parziale degli engrammi sui dati della prova della selezione (l'utente 01/11 sera): per ogni messaggio
debole (scartato o trascinato nella prova) vicino nel tempo a un ricordo forte (salienza >= soglia + 1), quanti dei suoi
engrammi coincidono con quelli del forte (stessa chiave o coseno bge-m3 >= SOGLIA_SEM, la regola di accendi) e quanti
sono nuovi. Poi quanti verrebbero catturati con varie regole. Solo lettura sulla copia della prova.
Uso: cd /data/memoria-episodica-affettiva/engrammi && LUX_DIR=prova-selezione/copia/lux /data/venv-spacy/bin/python sovrapposizione_prova.py"""
import collections
import json

import numpy as np

import lux_engrammi as X
import taglia as T

OUT = "prova-selezione"
reg = {}
for r in open(f"{OUT}/copia/mem/giornata-firma.jsonl", encoding="utf-8"):
    v = json.loads(r)
    reg[f"{v['ts']!r}|{v['testo']}"] = v
reg = sorted(reg.values(), key=lambda v: v["ts"])
SOGLIA = 1.532
forti = [v for v in reg if v["esito"] == "nodo" and v["salienza"] >= SOGLIA + 1]
deboli = [v for v in reg if v["esito"] in ("scartato", "trascinato")]
L = X.Lux()


def engrammi_di(nid):
    js = L.per_ricordo.get(nid, [])
    return {int(e) for j in js for e in L.A[j, 2:4] if e >= 0}


E_forte = {v["nid"]: engrammi_di(v["nid"]) for v in forti}
nodi_deb = {id(v): [t for k, t in T.taglia(v["testo"]) if k == "nodo"] for v in deboli}
tutti = [t for ts in nodi_deb.values() for t in ts]
Vd = X.embed(tutti) if tutti else np.zeros((0, L.V.shape[1]), np.float32)
pos, k = {}, 0
for v in deboli:
    n = len(nodi_deb[id(v)])
    pos[id(v)] = (k, k + n)
    k += n

righe = []
for v in deboli:
    a, b = pos[id(v)]
    nodi = nodi_deb[id(v)]
    for f in forti:
        dt = v["ts"] - f["ts"]
        if abs(dt) > 3600 or not nodi:
            continue
        ef = sorted(E_forte[f["nid"]])
        if not ef:
            continue
        S = X.coseni(Vd[a:b], L.V[ef])
        presi = 0
        for t, row in zip(nodi, S):
            i = L.chiavi.get(X.chiave(t))
            presi += (i is not None and i in E_forte[f["nid"]]) or bool((row >= X.SOGLIA_SEM).any())
        righe.append({"dt": dt, "n": len(nodi), "presi": presi, "nuovi": len(nodi) - presi,
                      "quota": presi / len(nodi), "esito_prova": v["esito"], "debole": v["testo"][:80],
                      "z_forte": f["salienza"], "z_debole": v["salienza"]})

# il miglior forte per ogni debole (la cattura ne vuole uno solo)
migliore = {}
for r in righe:
    k = r["debole"] + repr(r["z_debole"])
    if k not in migliore or (r["quota"], -abs(r["dt"])) > (migliore[k]["quota"], -abs(migliore[k]["dt"])):
        migliore[k] = r
best = list(migliore.values())
vicini = len(best)
res = {"deboli": len(deboli), "forti": len(forti), "deboli_vicini_a_un_forte_60min": vicini,
       "trascinati_nella_prova": sum(v["esito"] == "trascinato" for v in deboli),
       "engrammi_presi": dict(sorted(collections.Counter(min(r["presi"], 5) for r in best).items())),
       "quota_presa": {f"{lo:.2f}-{lo + 0.25:.2f}": sum(lo <= r["quota"] < lo + 0.25 or (lo == 0.75 and r["quota"] == 1)
                                                        for r in best) for lo in (0, 0.25, 0.5, 0.75)},
       "tutto_gia_nel_forte": sum(r["nuovi"] == 0 for r in best),
       "regole": {}}
for finestra in (3600, 1800, 900):
    for minimo in (1, 2):
        for quota_min in (0.0, 0.25):
            nome = f"finestra {finestra // 60} min, >= {minimo} engrammi presi, quota >= {quota_min}, >= 1 nuovo"
            res["regole"][nome] = sum(abs(r["dt"]) <= finestra and r["presi"] >= minimo and r["quota"] >= quota_min
                                      and r["nuovi"] >= 1 for r in best)
json.dump({"riassunto": res, "coppie": best}, open(f"{OUT}/sovrapposizione.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
