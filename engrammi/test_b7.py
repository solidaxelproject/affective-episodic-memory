#!/usr/bin/env python3
"""Stress-test di B7 (PIANO-FIRMA-ENGRAMMI.md, pulizia): P4 codice(ts) in un posto solo, P3 addr_emo nell'ordine di
emozioni.json (migrazione su COPIA di memoria.db e vettori.pt), potatura del registro del giorno. La produzione si legge.
Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/jspace/venv/bin/python test_b7.py"""
import ast
import importlib.machinery
import importlib.util
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import torch

QUI = os.path.dirname(os.path.abspath(__file__))
SPACY = "/data/venv-spacy/bin/python"
TMP = tempfile.mkdtemp(prefix="test-b7-")
os.makedirs(f"{TMP}/mem")
os.environ.update(MEM_SAM=f"{TMP}/mem", MARKER_NOTTE=f"{TMP}/marker")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import codice_ricordo  # noqa: E402
import firma_subito as FS  # noqa: E402
import memoria  # noqa: E402

# ---------- 1. P4: codice(ts) ----------
print("1. codice(ts): modulo, riflesso, Lux, copia di ricorda.py, codici del Lux in servizio", flush=True)
db = sqlite3.connect("file:/data/workspace/memoria/memoria.db?mode=ro", uri=True)
veri = [ts for (ts,) in db.execute("select ts from nodi")]
db.close()
rng = random.Random(7)
tss = veri + [rng.uniform(0, 2e9) for _ in range(5000)] + [rng.randint(0, 2 ** 40) for _ in range(4000)] + [0.0, 1, -1.5]
json.dump(tss, open(f"{TMP}/ts.json", "w"))
attesi = [codice_ricordo.codice(t) for t in json.load(open(f"{TMP}/ts.json"))]
leggi = f"import json; T = json.load(open({TMP + '/ts.json'!r}))"
rifl = subprocess.run(["python3", "-c", f"import sys; sys.path.insert(0, '/data/memoria-episodica-affettiva'); import riflesso as R; {leggi}; "
                       "print(json.dumps([R._codice(t) for t in T]))"], capture_output=True, text=True, check=True)
lux = subprocess.run([SPACY, "-c", f"import lux_engrammi as X; {leggi}; print(json.dumps([X.codice(t) for t in T]))"],
                     cwd=QUI, capture_output=True, text=True, check=True)
src = open("/data/workspace/memoria/ricorda.py").read()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "codice")
spazio = {}
exec("import hashlib\n" + ast.get_source_segment(src, fn), spazio)
assert json.loads(rifl.stdout) == attesi, "riflesso diverso"
assert json.loads(lux.stdout) == attesi, "lux_engrammi diverso"
assert [spazio["codice"](t) for t in json.load(open(f"{TMP}/ts.json"))] == attesi, "copia di ricorda.py diversa"
assert len(set(attesi)) == len(set(map(repr, json.load(open(f"{TMP}/ts.json")))))   # nessuna collisione
meta = json.load(open(f"{QUI}/lux-1.13.0/lux-meta.json"))["ricordi"]
db = sqlite3.connect("file:/data/workspace/memoria/memoria.db?mode=ro", uri=True)
for nid, ts in db.execute("select id, ts from nodi"):
    assert meta[str(nid)]["codice"] == codice_ricordo.codice(ts), nid
db.close()

# ---------- 2. P3: addr_emo ----------
print("2. addr_emo nell'ordine di emozioni.json: migrazione su copia, richiamo uguale", flush=True)
DB_VECCHIO = "/data/workspace/memoria/memoria.db.bak-pre-pulizia-0111"   # coerente coi vettori di prima di B7
shutil.copy2(DB_VECCHIO if os.path.exists(DB_VECCHIO) else "/data/workspace/memoria/memoria.db",
             f"{TMP}/mem/memoria.db")
VEC_VECCHIO = "/data/workspace/memoria/vettori.pt.bak-pre-B7-0111"   # formato di prima della migrazione
shutil.copy2(VEC_VECCHIO if os.path.exists(VEC_VECCHIO) else "/data/workspace/memoria/vettori.pt",
             f"{TMP}/mem/vettori.pt")
spec = importlib.util.spec_from_loader("memoria_vecchia", importlib.machinery.SourceFileLoader(
    "memoria_vecchia", "/data/memoria-episodica-affettiva/memoria.py.bak-pre-B7-0111"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
for M in (V, memoria):
    M.DB, M.VEC = Path(f"{TMP}/mem/memoria.db"), Path(f"{TMP}/mem/vettori.pt")
assi = ["joy", "fear", "sadness", "trust", "anger", "surprise", "disgust", "anticipation", "serenity", "grief"]
prima = {e: V.recall(e, mode="emotiva", k=10, update_hebb=False) for e in assi}
n = memoria.migra_addr_emo()
v1 = torch.load(memoria.VEC, weights_only=True)
assert n == len(v1)
db = sqlite3.connect(f"file:{memoria.DB}?mode=ro", uri=True)
firme = dict(db.execute("select id, firma from nodi"))
db.close()
nomi = [e["en"] for e in memoria.EMOZIONI]
for nid, x in v1.items():
    if nid not in firme:   # tolto dopo B7 (pulizia dei ricordi del 01/11 sera): resta nei vettori di prima
        continue
    f = json.loads(firme[nid])
    a = x["addr_emo"]
    assert len(a) == 51 and all(float(a[nomi.index(k)]) == float(torch.tensor(val)) for k, val in f.items()), nid
    assert sum(1 for i, e in enumerate(nomi) if e not in f and float(a[i]) != 0) == 0, nid
for e in assi:
    dopo = memoria.recall(e, mode="emotiva", k=10, update_hebb=False)
    assert [r["id"] for r in dopo] == [r["id"] for r in prima[e]], e
    assert all(abs(r["score"] - s["score"]) < 1e-4 for r, s in zip(dopo, prima[e])), e
    it = next(x["it"] for x in memoria.EMOZIONI if x["en"] == e)
    assert [r["id"] for r in memoria.recall(it, mode="emotiva", k=10, update_hebb=False)] == [r["id"] for r in dopo]
memoria.migra_addr_emo()
v2 = torch.load(memoria.VEC, weights_only=True)
assert all(torch.equal(v1[k]["addr_emo"], v2[k]["addr_emo"]) and torch.equal(v1[k]["addr_sem"], v2[k]["addr_sem"])
           for k in v1)   # ripetuta = uguale, addr_sem intatta
nid = memoria.add_node("B7 un ricordo nuovo per il formato", {"joy": 2.0, "fear": -0.5}, torch.zeros(1024), "joy", None, 2.0)
a = torch.load(memoria.VEC, weights_only=True)[nid]["addr_emo"]
assert len(a) == 51 and float(a[nomi.index("joy")]) == 2.0 and float(a[nomi.index("fear")]) == -0.5 and float(a.abs().sum()) == 2.5

# ---------- 3. potatura del registro ----------
print("3. potatura: vecchie fuori, dal marker dentro, ultima riga vince, riga rotta, contesto uguale", flush=True)
ora = time.time()
voci = [dict(ts=ora - g * 86400 - k - 1, autore="a", testo=f"B7 voce {g} {k}", esito="scartato", firma={}, salienza=0.0)
        for g in range(8) for k in range(3)]
with open(FS.GIORNATA, "w", encoding="utf-8") as f:
    for v in voci:
        f.write(json.dumps(v) + "\n")
    f.write(json.dumps(dict(voci[0], esito="trascinato", nid=5)) + "\n")   # riscrittura: vince l'ultima
    f.write('{"ts": 12, "autore": "a", "tes')                              # riga a meta' di un crash
contesto_prima = FS.T.contesto_di([x["testo"] for x in FS._vivi(FS.registro(), ora + 1)])
open(FS.MARKER, "w").close()
os.utime(FS.MARKER, (ora - 5 * 86400, ora - 5 * 86400))   # notturne fallite da 5 giorni
FS.pota(ora)
reg = FS.registro()
giorni = sorted({int(v["testo"].split()[2]) for v in reg.values()})
assert giorni == [0, 1, 2, 3, 4, 5], giorni   # dal marker meno un giorno, oltre i 3 giorni
righe = open(FS.GIORNATA).read().splitlines()
assert len(righe) == len(reg) == 18 and all(json.loads(r) for r in righe)   # una riga per voce, niente riga rotta
assert reg[FS._chiave(voci[0])]["esito"] == "trascinato"
assert FS.T.contesto_di([x["testo"] for x in FS._vivi(FS.registro(), ora + 1)]) == contesto_prima
os.utime(FS.MARKER, (ora - 60, ora - 60))   # notturna di stanotte riuscita: tre giorni
FS.pota(ora)
assert sorted({int(v["testo"].split()[2]) for v in FS.registro().values()}) == [0, 1, 2]
os.remove(FS.MARKER)   # nessun marker: si tiene tutto
FS.pota(ora)
assert len(FS.registro()) == 9
FS._potato[0] = 0.0   # il servizio pota da solo al primo passo
FS.firma = lambda c, t: (_ for _ in ()).throw(AssertionError("niente da firmare"))
FS.controlla_lettore = lambda: None
FS.lux_aggiungi = lambda: None
assert FS.passo() == "pronto" and FS._potato[0] > 0
os.utime(FS.MARKER if os.path.exists(FS.MARKER) else open(FS.MARKER, "w").name, (ora - 60, ora - 60))
n = len(FS.registro())
FS.accoda([dict(ts=ora - 10 * 86400, autore="a", testo="B7 voce di dieci giorni fa, segnalibro perso")])
assert FS.passo() == "pronto" and len(FS.registro()) == n   # piu' vecchia del registro potato: saltata, niente firma
FS._potato[0] = 0.0
pota_vera = FS.pota
FS.pota = lambda: (_ for _ in ()).throw(OSError("disco pieno"))   # potatura impossibile: il giro va avanti lo stesso
FS.accoda([dict(ts=ora - 5, autore="a", testo="B7 voce con la potatura rotta")])
FS.firma = lambda c, t: ({"joy": 0.1}, 0.1, "joy")
assert FS.passo() == "pronto"
FS.pota = pota_vera
assert FS._potato[0] > 0 and FS.registro()[FS._chiave(dict(ts=ora - 5, testo="B7 voce con la potatura rotta"))]["esito"] == "scartato"

shutil.rmtree(TMP)
print("TUTTO VERDE")
