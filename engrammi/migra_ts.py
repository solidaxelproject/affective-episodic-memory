#!/usr/bin/env python3
"""qlux (l'utente 09/11, PIANO-MEMORINVOLONTARIA-LUX.md): una tantum, il momento (ts) di ogni ricordo da memoria.db
dentro lux-meta.json della versione in servizio (primo pezzo della fase 2 "memoria.db superfluo"). Il codice del
ricordo deve tornare (codice(ts)); le correzioni hanno gia' il loro ts. Scrittura atomica sotto il lucchetto: il
servizio ricarica da solo. Idempotente. Uso: venv-spacy/bin/python migra_ts.py [--dry] [cartella]"""
import json
import os
import sqlite3
import sys

import lux_engrammi as X

dry = "--dry" in sys.argv
cartella = next((a for a in sys.argv[1:] if a != "--dry"), X.DIR)
meta = f"{cartella}/lux-meta.json"
with X.lucchetto():
    m = json.load(open(meta))
    c = sqlite3.connect(f"file:{X.T.DB}?mode=ro", uri=True)
    db = dict(c.execute("select id, ts from nodi"))
    messi = gia = 0
    for k, r in m["ricordi"].items():
        if "ts" in r:
            gia += 1
            continue
        ts = db[int(k)]
        assert X.codice(ts) == r["codice"], (k, ts, r["codice"])
        r["ts"] = ts
        messi += 1
    assert all("ts" in r for r in m["ricordi"].values())
    if not dry and messi:
        json.dump(m, open(meta + ".tmp", "w"), ensure_ascii=False)
        os.replace(meta + ".tmp", meta)
print(f"{meta}: ts messi {messi}, gia' presenti {gia}{' (prova, niente scritto)' if dry else ''}")
