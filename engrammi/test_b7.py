#!/usr/bin/env python3
"""Stress-test di B7 (PIANO-FIRMA-ENGRAMMI.md, pulizia): P4 codice(ts) in un posto solo, potatura del registro del
giorno. La produzione si legge. Lux 1.20.0: tolte le prove di ricorda.py, del riflesso (non calcola piu' codici) e di
addr_emo in vettori.pt (P3), codice in archivio-20261111.
Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/jspace/venv/bin/python test_b7.py"""
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

QUI = os.path.dirname(os.path.abspath(__file__))
SPACY = "/data/venv-spacy/bin/python"
TMP = tempfile.mkdtemp(prefix="test-b7-")
os.makedirs(f"{TMP}/mem")
os.environ.update(MEM_SAM=f"{TMP}/mem", MARKER_NOTTE=f"{TMP}/marker")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import codice_ricordo  # noqa: E402
import firma_subito as FS  # noqa: E402

# ---------- 1. P4: codice(ts) ----------
print("1. codice(ts): modulo, Lux, codici del Lux in servizio", flush=True)
db = sqlite3.connect("file:/data/workspace/memoria/memoria.db?mode=ro", uri=True)
veri = [ts for (ts,) in db.execute("select ts from nodi")]
db.close()
rng = random.Random(7)
tss = veri + [rng.uniform(0, 2e9) for _ in range(5000)] + [rng.randint(0, 2 ** 40) for _ in range(4000)] + [0.0, 1, -1.5]
json.dump(tss, open(f"{TMP}/ts.json", "w"))
attesi = [codice_ricordo.codice(t) for t in json.load(open(f"{TMP}/ts.json"))]
leggi = f"import json; T = json.load(open({TMP + '/ts.json'!r}))"
lux = subprocess.run([SPACY, "-c", f"import lux_engrammi as X; {leggi}; print(json.dumps([X.codice(t) for t in T]))"],
                     cwd=QUI, capture_output=True, text=True, check=True)
assert json.loads(lux.stdout) == attesi, "lux_engrammi diverso"
assert len(set(attesi)) == len(set(map(repr, json.load(open(f"{TMP}/ts.json")))))   # nessuna collisione
meta = json.load(open("/data/memoria-episodica-affettiva/engrammi/lux-1.13.0/lux-meta.json"))["ricordi"]   # dati fuori da git
db = sqlite3.connect("file:/data/workspace/memoria/memoria.db?mode=ro", uri=True)
for nid, ts in db.execute("select id, ts from nodi"):
    assert meta[str(nid)]["codice"] == codice_ricordo.codice(ts), nid
db.close()

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
