#!/usr/bin/env python3
"""Controllo delle scene di un giro di Plutchik (22/10). Uso: valida_giro.py <giro> <gruppo 1-6>
Legge scene/giro-<giro>-<gruppo>.jsonl e lo confronta con scene/gruppo-<gruppo>.jsonl: stesse scene nello stesso
ordine, una versione per ogni emozione nuova del giro, nessuna radice delle emozioni del giro (nemmeno di quelle
originali: la scena non deve nominare nessuna emozione), lunghezza fra 0.85 e 1.4 volte la neutra."""
import json
import re
import sys

sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering")
from sistema import D, EMO_IT, GIRI, RADICI  # noqa: E402

giro, g = sys.argv[1], sys.argv[2]
base = [json.loads(r) for r in open(f"{D}/scene/gruppo-{g}.jsonl") if r.strip()]
nuovo = [json.loads(r) for r in open(f"{D}/scene/giro-{giro}-{g}.jsonl") if r.strip()]
nuove = [e for e in GIRI[giro] if e not in EMO_IT]
errori = []
if [x["scena"] for x in nuovo] != [x["scena"] for x in base]:
    errori.append(f"scene diverse o in ordine diverso: {[x['scena'] for x in nuovo]}")
for b, x in zip(base, nuovo):
    n = len(b["versioni"]["neutra"])
    for e in nuove:
        t = x.get("versioni", {}).get(e)
        if not t:
            errori.append(f"{x['scena']} {e}: manca")
            continue
        for f in GIRI[giro]:
            m = re.search(RADICI[f], t, re.I)
            if m:
                errori.append(f"{x['scena']} {e}: contiene {m.group(0)!r} (radice di {f})")
        if not 0.85 <= len(t) / n <= 1.4:
            errori.append(f"{x['scena']} {e}: lunghezza {len(t)} contro {n} della neutra")
print("\n".join(errori) or f"giro {giro} gruppo {g}: ok ({len(nuovo)} scene x {len(nuove)} emozioni)")
sys.exit(1 if errori else 0)
