#!/usr/bin/env python3
"""Sentinella anti-amnesia della notturna (B5 01/11, PIANO-FIRMA-ENGRAMMI.md, P6): ogni ricordo di memoria.db sta nel
Lux degli engrammi in servizio. Esce con 1 e li elenca se ne manca qualcuno. Sola lettura, senza spacy."""
import json
import os
import re
import sqlite3
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
VERSIONE = re.search(r'^VERSIONE = "([^"]+)"', open(f"{QUI}/lux_engrammi.py").read(), re.M).group(1)
META = f"{os.environ.get('LUX_DIR', f'{QUI}/lux-{VERSIONE}')}/lux-meta.json"
DB = os.environ.get("MEMORIA_DB", "/data/workspace/memoria/memoria.db")

dentro = {int(k) for k in json.load(open(META))["ricordi"]}
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
fuori = [n for (n,) in c.execute("select id from nodi where testo != '' order by id") if n not in dentro]
if fuori:
    print(f"CRITICO: {len(fuori)} ricordi fuori dal Lux {VERSIONE}: {fuori[:20]}")
    sys.exit(1)
print(f"sentinella: tutti i ricordi nel Lux {VERSIONE} ({len(dentro)})")
