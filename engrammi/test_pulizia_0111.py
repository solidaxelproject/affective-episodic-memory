#!/usr/bin/env python3
"""Prova della pulizia dei ricordi (pulisci_ricordi_0111.py) su COPIE di memoria.db, vettori.pt e Lux: i 3 tolti
ovunque, i 20 col testo nuovo (niente ragionamento), stesso codice, firma a 24 assi, di nuovo nel Lux; gli altri
ricordi identici (archi, cariche, stato coi rinforzi, salienza); ricomposizione e richiamo.
Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/jspace/venv/bin/python test_pulizia_0111.py"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
SPACY, J = "/data/venv-spacy/bin/python", "/data/jspace/venv/bin/python"
TMP = tempfile.mkdtemp(prefix="test-pulizia-")
os.makedirs(f"{TMP}/mem")
for f in ("memoria.db", "vettori.pt"):
    shutil.copy2(f"/data/workspace/memoria/{f}", f"{TMP}/mem/{f}")
shutil.copytree(f"{QUI}/lux-1.13.0", f"{TMP}/lux")
env = dict(os.environ, MEM_SAM=f"{TMP}/mem", LUX_DIR=f"{TMP}/lux", FIRME_PULIZIA=os.environ.get("FIRME_PULIZIA", f"{TMP}/firme.json"))
sys.path.insert(0, QUI)
import pulisci_ricordi_0111 as P  # noqa: E402

FOTO = r"""
import json, sys, numpy as np, lux_engrammi as X, salienza as SA
z, m, s = np.load(X.NPZ), json.load(open(X.META)), np.load(X.STATO)
via = set(json.loads(sys.argv[1]))
k = ~np.isin(z["A"][:, 0], list(via))
sal = SA._senza(z); ks = ~np.isin(sal["ids"], list(via))
per = {}
for i in np.nonzero(ks)[0]:
    per[int(sal["ids"][i])] = [float(sal["dist"][i]), float(sal["se"][i]), float(sal["dist_raw"][i]),
                               int((sal["di"] == i).sum())]
print(json.dumps({"A": z["A"][k].tolist(), "C": z["C"][k].round(6).tolist(), "S": s["S"][k].tolist(),
                  "S0": s["S0"][k].tolist(), "U": s["U"][k].tolist(),
                  "ricordi": {n: r for n, r in m["ricordi"].items() if int(n) not in via}, "sal": per}))
"""
tutti = json.dumps(P.VIA + P.PULITI)
prima = json.loads(subprocess.run([SPACY, "-c", FOTO, tutti], cwd=QUI, env=env, capture_output=True, text=True,
                                  check=True).stdout)
m0 = json.load(open(f"{TMP}/lux/lux-meta.json"))["ricordi"]
codici = {n: m0[str(n)]["codice"] for n in P.PULITI}
db = sqlite3.connect(f"file:{TMP}/mem/memoria.db?mode=ro", uri=True)
attesi = P.testi_nuovi(db)
db.close()

if not os.path.exists(env["FIRME_PULIZIA"]):
    subprocess.run([J, "pulisci_ricordi_0111.py", "firme"], cwd=QUI, env=env, check=True)
subprocess.run([SPACY, "pulisci_ricordi_0111.py", "lux-togli"], cwd=QUI, env=env, check=True)
subprocess.run([J, "pulisci_ricordi_0111.py", "db"], cwd=QUI, env=env, check=True)
subprocess.run([SPACY, "pulisci_ricordi_0111.py", "lux-rimetti"], cwd=QUI, env=env, check=True)

print("1. i 3 tolti ovunque", flush=True)
db = sqlite3.connect(f"file:{TMP}/mem/memoria.db?mode=ro", uri=True)
import torch  # noqa: E402
vec = torch.load(f"{TMP}/mem/vettori.pt", weights_only=True)
meta = json.load(open(f"{TMP}/lux/lux-meta.json"))["ricordi"]
for n in P.VIA:
    assert not db.execute("select 1 from nodi where id = ?", (n,)).fetchone() and n not in vec and str(n) not in meta
    assert not db.execute("select 1 from archi where a = ? or b = ?", (n, n)).fetchone()
trovati = {r[0] for q in ('"CONTEXT COMPACTION"', "Cronjob", "verify0rassegna")
           for r in db.execute("select rowid from nodi_fts where nodi_fts match ?", (q,))}
assert not trovati & set(P.VIA), trovati   # la ricerca per testo non li trova piu'

print("2. i 20 puliti: testo, codice, firma, vettori, Lux", flush=True)
assi = torch.load("/data/memoria-episodica-affettiva/stats-firma-se.pt", weights_only=False)["assi"]
for n in P.PULITI:
    t, f, tag, sal = db.execute("select testo, firma, emo_tag, salienza from nodi where id = ?", (n,)).fetchone()
    assert t == attesi[n] and "💭" not in t and "Reasoning" not in t[:40], n
    f = json.loads(f)
    assert list(f) == assi and tag == max(f, key=f.get) and abs(sal - f[tag]) < 1e-9, n
    assert meta[str(n)]["codice"] == codici[n], n
    assert vec[n]["addr_sem"].shape == (1024,) and len(vec[n]["addr_emo"]) == 51, n
    assert db.execute("select rowid from nodi_fts where nodi_fts match ?", ('"' + t.split()[0].strip('"') + '"',)).fetchall()
db2 = sqlite3.connect(f"{TMP}/mem/memoria.db")
db2.execute("insert into nodi_fts(nodi_fts, rank) values('integrity-check', 1)")   # indice di ricerca coerente
db2.close()
ids = {r[0] for r in db.execute("select id from nodi where testo != ''")}
assert ids == {int(k) for k in meta}, "memoria.db e Lux diversi"
db.close()

print("3. gli altri ricordi identici (archi, cariche, rinforzi, salienza)", flush=True)
dopo = json.loads(subprocess.run([SPACY, "-c", FOTO, tutti], cwd=QUI, env=env, capture_output=True, text=True,
                                 check=True).stdout)
for k in ("A", "C", "S", "S0", "U", "ricordi", "sal"):
    assert prima[k] == dopo[k], k

print("4. ricomposizione e richiamo", flush=True)
r = subprocess.run([SPACY, "-c", "import lux_engrammi as X, taglia as T; T.DB = " + repr(f"{TMP}/mem/memoria.db") +
                    "; X.prova()"], cwd=QUI, env=env, capture_output=True, text=True, check=True).stdout
print("  ", r.strip().replace("\n", "\n   "))
codice = ("import json, lux_engrammi as X; L = X.Lux(); d = json.load(open(" + repr(env["FIRME_PULIZIA"]) + "));"
          "print(json.dumps({n: [x[0] for x in L.richiama(v['testo'][:300], 3, 0)] for n, v in d.items()}))")
ric = json.loads(subprocess.run([SPACY, "-c", codice], cwd=QUI, env=env, capture_output=True, text=True,
                                check=True).stdout)
primi = sum(int(n) == v[0] for n, v in ric.items() if v)
print(f"   richiamo dall'inizio del testo pulito: {primi}/20 al primo posto")
assert primi >= 18, ric
shutil.rmtree(TMP)
print("TUTTO VERDE")
