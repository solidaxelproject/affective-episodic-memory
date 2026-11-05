#!/usr/bin/env python3
"""Stress-test di B4 (PIANO-FIRMA-ENGRAMMI.md): Lux 1.13.0, l'emozione sull'arco.
  dati:    A, P, V, salienza, lux-meta.json uguali alla 1.12.0, stato dei rinforzi identico; C una riga per arco = firma
           del suo ricordo; F = media delle C dei suoi archi vivi (contata qui a mano, in un altro modo)
  stress:  1000 indizi dai ricordi veri = stessi ricordi della 1.12.0; aggiungi di un ricordo nuovo (su una copia)
           aggiunge le sue righe di C e ricalcola F; correggi: l'arco a posizione -1 ha la sua C; aggiungi mentre un
           servizio rinforza e salva lo stato: nessun arco e nessun rinforzo perso.
Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/venv-spacy/bin/python test_lux_113.py"""
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading

import numpy as np

import lux_engrammi as X
import taglia as T

VECCHIO = "/data/memoria-episodica-affettiva/engrammi/lux_engrammi.py.bak-pre-1.13.0"   # il codice della 1.12.0
fallimenti = []


def ok(cond, cosa):
    if not cond:
        fallimenti.append(cosa)
        print("  ROSSO:", cosa, flush=True)


print("1. dati uguali alla 1.12.0", flush=True)
z12, z13 = np.load(f"{X.PRECEDENTE}/lux.npz"), np.load(X.NPZ)
for k in z12.files:
    if k != "F":
        ok(np.array_equal(z12[k], z13[k]), f"{k} diverso dalla 1.12.0")
ok(set(z13.files) == set(z12.files) | {"C"}, f"chiavi di lux.npz {sorted(z13.files)}")
for f in ("lux-meta.json", "lux-stato.npz"):
    ok(open(f"{X.PRECEDENTE}/{f}", "rb").read() == open(f"{X.DIR}/{f}", "rb").read(), f"{f} non identico alla 1.12.0")

print("2. C = firma del ricordo per ogni arco", flush=True)
A, C, F = z13["A"], z13["C"], z13["F"]
ok(C.shape == (len(A), 51) and len(A) >= 34043, f"forma di C {C.shape}")
db = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
firme = {i: json.loads(f) for i, f in db.execute("select id, firma from nodi")}
db.close()
assi24 = [e for e in X.EMOZIONI if e in next(iter(firme.values()))]
ok(len(assi24) == 24, f"assi della firma fra i 51: {len(assi24)}")
for j, (r, p) in enumerate(A[:, :2].tolist()):
    atteso = np.zeros(51, np.float32) if p < 0 or r not in firme else \
        np.asarray([firme[r].get(e, 0.0) for e in X.EMOZIONI], np.float32)
    if not np.array_equal(C[j], atteso):
        ok(False, f"arco {j} (ricordo {r}): C diversa dalla firma")
        break
fuori = [i for i, e in enumerate(X.EMOZIONI) if e not in assi24]
ok(not C[:, fuori].any(), "C non zero fuori dai 24 assi")

print("3. F = media delle C dei suoi archi vivi (conteggio indipendente)", flush=True)
archi_di = {}
for j, (r, p, a, b) in enumerate(A[:, :4].tolist()):
    if p >= 0 and C[j].any():
        for e in {a, b}:
            archi_di.setdefault(e, []).append(j)
random.seed(1)
for e in random.sample(range(len(F)), 2000) + [e for e in range(len(F)) if e not in archi_di][:50]:
    atteso = C[archi_di[e]].mean(0) if e in archi_di else np.zeros(51)
    if not np.allclose(F[e], atteso, atol=1e-5):
        ok(False, f"engramma {e}: F diversa dalla media delle C")
        break

print("4. 1000 indizi dai ricordi veri: stessi ricordi della 1.12.0", flush=True)
L = X.Lux()
L.salva_stato = lambda: None
ok(L.C.shape == C.shape, "Lux() non carica C")
random.seed(2)
indizi = []
for nid in random.choices([n for n in L.ricordi if L.ricordi[n]["n"] >= 3], k=1000):
    e = [int(L.A[j, 3]) for j in sorted(L.per_ricordo[nid], key=lambda j: L.A[j, 1])]
    indizi.append(". ".join(L.testi[x] for x in random.sample(e, 2)))
OGGI, ORA = 500.0, 1.8e9
nuovi = [[[int(n), round(float(p), 9)] for n, p in L.richiama(t, 3, 0, OGGI, ORA)] for t in indizi]
tmp = tempfile.mkdtemp(prefix="test-b4-", dir="/data/memoria-episodica-affettiva/engrammi")
try:
    shutil.copy2(VECCHIO, f"{tmp}/lux_engrammi.py")
    json.dump(indizi, open(f"{tmp}/indizi.json", "w"), ensure_ascii=False)
    codice = (f"import sys, json; sys.path.insert(1, '/data/memoria-episodica-affettiva/engrammi'); import lux_engrammi as X\n"
              f"assert X.VERSIONE == '1.12.0'\nL = X.Lux()\n"
              f"r = [[[int(n), round(float(p), 9)] for n, p in L.richiama(t, 3, 0, {OGGI}, {ORA})] "
              f"for t in json.load(open('indizi.json'))]\njson.dump(r, open('vecchi.json', 'w'))")
    subprocess.run([sys.executable, "-c", codice], cwd=tmp, check=True)
    vecchi = json.load(open(f"{tmp}/vecchi.json"))
    diversi = sum(a != b for a, b in zip(vecchi, nuovi))
    ok(diversi == 0, f"richiamo diverso dalla 1.12.0 su {diversi}/1000 indizi")
    print(f"   {1000 - diversi}/1000 uguali", flush=True)

    print("5. aggiungi e correggi su una copia; aggiungi mentre un servizio rinforza e salva", flush=True)
    copia = f"{tmp}/lux"
    shutil.copytree(X.DIR, copia)
    sqlite3.connect(T.DB).backup(sqlite3.connect(f"{tmp}/memoria.db"))
    X.DIR, X.NPZ, X.META, X.STATO = copia, f"{copia}/lux.npz", f"{copia}/lux-meta.json", f"{copia}/lux-stato.npz"
    T.DB = f"{tmp}/memoria.db"
    m = sqlite3.connect(T.DB)
    with m:
        nid = m.execute("INSERT INTO nodi (ts, testo, fonte, emo_tag, emo_alpha, firma, salienza, classe, voluto) "
                        "SELECT ?, ?, fonte, emo_tag, emo_alpha, firma, salienza, classe, voluto FROM nodi WHERE id=294",
                        (1.9e9, "Oggi abbiamo messo le emozioni sugli archi del Lux, e il ricordo nuovo ha la sua carica.")
                        ).lastrowid
    m.close()
    S = X.Lux()   # il "servizio": rinforza un ricordo vecchio di continuo, ricaricando come servizio_lux.py
    vecchio_nid = 294
    giri, ferma, errori = [0], threading.Event(), []

    def servizio():
        global S
        meta = os.path.getmtime(X.META)
        try:
            while not ferma.is_set():
                if os.path.getmtime(X.META) != meta:
                    S, meta = X.Lux(), os.path.getmtime(X.META)
                S.rinforza(vecchio_nid, 600.0 + giri[0])
                giri[0] += 1
        except Exception as e:   # noqa: BLE001
            errori.append(repr(e))
    th = threading.Thread(target=servizio)
    th.start()
    n_a = len(np.load(X.NPZ)["A"])
    X.aggiungi()
    ferma.set()
    th.join()
    ok(not errori, f"servizio durante aggiungi: {errori}")
    z, s = np.load(X.NPZ), np.load(X.STATO)
    nuovi_archi = np.nonzero(z["A"][:, 0] == nid)[0]
    ok(len(nuovi_archi) > 0 and nuovi_archi.min() == n_a, "archi del ricordo nuovo non in coda")
    ok(len(z["C"]) == len(z["A"]) == len(s["S"]) == len(s["S0"]) == len(s["U"]),
       f"righe: A {len(z['A'])}, C {len(z['C'])}, S {len(s['S'])}: archi persi")
    ok(np.array_equal(z["C"][:n_a], C), "C degli archi vecchi cambiata")
    f294 = np.asarray([firme[294].get(e, 0.0) for e in X.EMOZIONI], np.float32)
    ok(all(np.array_equal(z["C"][j], f294) for j in nuovi_archi), "C degli archi nuovi diversa dalla firma")
    ok(np.allclose(z["F"], X.firme_engrammi(z["A"], z["C"], len(z["V"]))), "F non ricalcolata")
    js = np.nonzero(z["A"][:, 0] == vecchio_nid)[0]
    ok(giri[0] > 0 and (s["U"][js] == 600.0 + giri[0] - 1).all(), f"ultimo rinforzo del servizio perso ({giri[0]} giri)")
    print(f"   servizio: {giri[0]} rinforzi durante aggiungi", flush=True)

    prima = X.Lux()   # caricato prima della correzione, salva dopo: gli archi nuovi della correzione devono restare
    cod = X.correggi(prima.ricordi[294]["codice"], "Correzione di prova: la carica sta sugli archi.", ts=1.9e9 + 5)
    z = np.load(X.NPZ)
    prima.rinforza(294, 9999.0)
    s = np.load(X.STATO)
    ok(len(s["S"]) == len(s["S0"]) == len(s["U"]) == len(z["A"]), f"stato {len(s['S'])} archi, A {len(z['A'])}: persi")
    ok((s["U"][z["A"][:, 0] == 294] == 9999.0).all(), "rinforzo del Lux caricato prima non salvato")
    ok((s["U"][len(prima.S):] != 9999.0).all() and len(s["S"]) > len(prima.S), "archi nuovi toccati dal Lux vecchio")
    Lc = X.Lux()
    cn = Lc.da_codice[cod]
    j = np.nonzero((z["A"][:, 0] == cn) & (z["A"][:, 1] == -1))[0]
    ok(len(j) == 1 and len(z["C"]) == len(z["A"]) and not z["C"][j].any(), "arco -1 della correzione senza la sua C")
    ok(not z["C"][z["A"][:, 0] == cn].any(), "la correzione (senza firma) ha cariche non zero")
    ok(Lc.corregge.get(cn) == 294, "correzione non legata al ricordo")
finally:
    shutil.rmtree(tmp)

print("TUTTO VERDE" if not fallimenti else f"ROSSO: {len(fallimenti)} fallimenti")
sys.exit(1 if fallimenti else 0)
