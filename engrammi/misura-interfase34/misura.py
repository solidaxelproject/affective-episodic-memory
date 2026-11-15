#!/usr/bin/env python3
"""Interfase 3-4 punto 5, parte A (14/11/2026): il richiamo del Lux contro un RAG semplice e bm25, e le ablazioni
dei meccanismi del richiamo (un meccanismo spento alla volta). Solo il recupero (il ricordo giusto); qualita' delle
risposte, coerenza nel tempo ed effetto dello steering sul ragionamento vogliono il 35B (parte B).
Dati: COPIA congelata del Lux (/data/tmp-foto-lux-istantanea, vedi manutenzione/foto_lux.py), mai il Lux vero.
Indizi: (1) le frasi libere di taratura_soglia.py (scritte da CC, parole diverse dal ricordo), (2) 40 indizi da due
engrammi del ricordo, non vicini (come prova()), (3) 40 frasi copiate dal ricordo; negativi: le frasi senza ricordo
di taratura_soglia.py. Metriche: primo posto, fra i primi 3, MRR sui primi 3; per i negativi, quanti passano la
soglia del Lux. Serve l'embedder :8094.
Uso: cd engrammi && /data/venv-spacy/bin/python misura-interfase34/misura.py"""
import ast
import json
import os
import random
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.dirname(QUI)
ISTANTANEA = "/data/tmp-foto-lux-istantanea"
COPIA = "/data/tmp-misura-lux"
shutil.rmtree(COPIA, ignore_errors=True)
shutil.copytree(ISTANTANEA, COPIA)
os.environ["LUX_DIR"] = f"{COPIA}/lux"
sys.path.insert(0, ENG)
import lux_engrammi as X  # noqa: E402

X.LUX.FILE = Path(f"{COPIA}/orologio/lux.npz")   # tempo vissuto congelato
L = X.Lux()
L.salva_stato = lambda: None
ORA = 1794700000.0
OGGI = X.giorno_di(ORA)

# --- indizi
albero = ast.parse(open(f"{ENG}/taratura_soglia.py").read())
lett = {t.targets[0].id: ast.literal_eval(t.value) for t in albero.body
        if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name) and t.targets[0].id in ("POSITIVI", "NEGATIVI")}
gruppi = {"libere": [(f, n) for f, n in lett["POSITIVI"] if n in L.ricordi]}
random.seed(0)
lunghi = [n for n in sorted(L.ricordi) if L.ricordi[n]["n"] >= 6]
due = []
for nid in random.sample(lunghi, 40):
    idx = sorted(L.per_ricordo[nid], key=lambda j: L.A[j, 1])
    e = [int(L.A[j, 3]) for j in idx]
    due.append((L.testi[e[1]] + ". " + L.testi[e[len(e) // 2 + 1]], nid))
gruppi["due_engrammi"] = due
esatte = []
for nid in random.sample(lunghi, 40):
    frasi = [s for s in re.split(r"(?<=[.!?])\s+", L.ricordi[nid]["testo"]) if len(s.split()) >= 5]
    if frasi:
        esatte.append((random.choice(frasi), nid))
gruppi["frasi_esatte"] = esatte
negativi = [f for f in lett["NEGATIVI"]]

# --- il richiamo del Lux con interruttori (stessa formula di Lux.richiama, emozione a parte)
TUTTO = {"facilita": True, "predisposizione": True, "peso_comuni": True, "lunghezza": True}


def lux(q, sw=TUTTO, quanti=3, soglia=0.0):
    punti = {}
    for i, a in L.accendi(q).items():
        ric = {int(L.A[j, 0]) for j in L.per_engramma.get(i, ())}
        for r in ric:
            punti[r] = punti.get(r, 0) + a / (np.log(1 + len(ric)) if sw["peso_comuni"] else 1.0)
    fac = L.facilita(OGGI)
    for r in punti:
        punti[r] *= (fac[r] if sw["facilita"] else 1.0) / (np.sqrt(L.ricordi[r]["n"]) if sw["lunghezza"] else 1.0) * \
            (min(X.PREDISPOSIZIONE_MAX, 1 + L.spinta(r, ORA)) if sw["predisposizione"] else 1.0)
    return [n for n, p in sorted(punti.items(), key=lambda x: -x[1])[:quanti] if p >= soglia]


# fedelta': a interruttori accesi coincide con Lux.richiama
for q, _ in gruppi["due_engrammi"][:10] + gruppi["libere"][:5]:
    assert lux(q) == [n for n, _ in L.richiama(q, 3, 0, oggi=OGGI, ora=ORA)], q

# --- RAG: blocchi di circa 150 parole per ricordo, frasi intere, bge-m3; bm25: fts5 sui ricordi interi
blocchi = []
for n in sorted(L.ricordi):
    cur = []
    for s in re.split(r"(?<=[.!?])\s+", L.ricordi[n]["testo"]):
        cur.append(s)
        if sum(len(x.split()) for x in cur) >= 150:
            blocchi.append((n, " ".join(cur)))
            cur = []
    if cur:
        blocchi.append((n, " ".join(cur)))
fv = f"{QUI}/rag-V.npy"
R = np.load(fv) if os.path.exists(fv) and len(np.load(fv)) == len(blocchi) else None
if R is None:
    R = X.embed([b[1] for b in blocchi]).astype(np.float32)
    np.save(fv, R)
db = sqlite3.connect(":memory:")
db.execute("create virtual table r using fts5(id unindexed, testo)")
db.executemany("insert into r values(?, ?)", [(n, r["testo"]) for n, r in L.ricordi.items()])


def rag(q):
    s, out = R @ X.embed([q])[0].astype(np.float32), []
    for j in np.argsort(-s):
        if blocchi[j][0] not in out:
            out.append(blocchi[j][0])
        if len(out) == 3:
            return out
    return out


def bm25(q):
    parole = " OR ".join(f'"{w}"' for w in re.findall(r"\w{3,}", q.lower()))
    if not parole:
        return []
    return [int(i) for i, in db.execute("select id from r where r match ? order by bm25(r) limit 3", (parole,))]


sistemi = {"lux": lux, "rag": rag, "bm25": bm25}
for k in TUTTO:
    sistemi[f"lux_senza_{k}"] = (lambda kk: lambda q: lux(q, {**TUTTO, kk: False}))(k)


def misura(f, indizi):
    p1 = p3 = rr = 0
    for q, n in indizi:
        r = f(q)
        p1 += bool(r) and r[0] == n
        p3 += n in r
        rr += 1 / (r.index(n) + 1) if n in r else 0
    k = len(indizi)
    return {"primo": round(p1 / k, 3), "primi3": round(p3 / k, 3), "mrr3": round(rr / k, 3), "n": k}


risultati = {g: {s: misura(f, ind) for s, f in sistemi.items()} for g, ind in gruppi.items()}
risultati["negativi_sopra_soglia_lux"] = {"passano": sum(bool(lux(q, soglia=X.SOGLIA_RICHIAMO)) for q in negativi),
                                          "n": len(negativi)}
risultati["positivi_sopra_soglia_lux"] = {
    g: {"passano": sum(bool(lux(q, soglia=X.SOGLIA_RICHIAMO)) for q, _ in ind), "n": len(ind)} for g, ind in gruppi.items()}
json.dump(risultati, open(f"{QUI}/risultati-A.json", "w"), indent=1)
for g in gruppi:
    print(f"\n{g} (n={len(gruppi[g])})")
    for s, v in risultati[g].items():
        print(f"  {s:28} primo {v['primo']:.2f}  primi3 {v['primi3']:.2f}  mrr {v['mrr3']:.2f}")
print("\nsoglia del Lux:", risultati["negativi_sopra_soglia_lux"], risultati["positivi_sopra_soglia_lux"])
shutil.rmtree(COPIA, ignore_errors=True)
