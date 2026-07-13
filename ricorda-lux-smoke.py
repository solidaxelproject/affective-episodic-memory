# Smoke dell'anello 2->4: Lux.richiama -> griglia del nodo -> iniezione :8090.
# NON tocca i dati di Agente: Lux copiata in temp (write-through deviato) e store
# griglie finto (GRIGLIE_DIR) col sogno del gatto keyato su un neurone vero.
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

td = tempfile.mkdtemp(prefix="ricorda-lux-smoke-")
os.environ["GRIGLIE_DIR"] = td

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import lux                                              # noqa: E402
shutil.copy(lux.FILE, Path(td) / "lux.npz")
lux.FILE = Path(td) / "lux.npz"                         # richiama salva qui
lux.META = Path(td) / "lux-meta.json"
import json                                             # noqa: E402
json.dump({"archi": {}}, open(lux.META, "w"))
import ponte                                            # noqa: E402

g = lux.Lux()
neurone = int(g.attivazioni.argmax())                   # il più vissuto
nodo = int(g.nodo_id[neurone])
firma = g.firme[neurone].copy()
shutil.copy("/data/memoria-episodica-affettiva/sogno-gatto.npy", f"{td}/{nodo}.npy")

# 1) richiamo emotivo con la firma del neurone -> deve tornare LUI, con griglia
scena, hit = ponte.ricorda_lux(firma, via="emotiva")
assert hit and hit["nodo_id"] == nodo, hit
assert scena and "gatt" in scena.lower(), scena
print(f"richiamo+iniezione OK: neurone {neurone} -> nodo {nodo} -> scena:")
print("  " + scena.strip().replace("\n", " ")[:200])

# 2) nessuna griglia per i richiamati -> (None, hit migliore), niente iniezione
os.remove(f"{td}/{nodo}.npy")
scena2, hit2 = ponte.ricorda_lux(firma, via="emotiva")
assert scena2 is None and hit2 is not None, (scena2, hit2)
print("fallback senza griglia OK")

# 3) via semantica: uno stato che re-incarna la traccia deve ritrovarla
# (encode sottrae mu: si passa quindi traccia + mu, come uno stato vero)
stato = g.tracce[neurone] + g.mu
top = g.richiama(stato, via="semantica", k=1)
assert top[0]["neurone"] == neurone, top
print("via semantica OK (traccia decompressa ritrova il suo neurone)")

shutil.rmtree(td)
print("SMOKE-OK")
