#!/usr/bin/env python3
"""test della 1.15.0 (PIANO-1.15-TABELLA-EMOZIONI.md): tabella delle emozioni in lux.npz, carica = firma x fattore
alla migrazione e per gli archi nuovi, forza scalata col fattore. Su una COPIA (LUX_DIR temporanea); embedder :8094.
Uso: cd engrammi && /data/venv-spacy/bin/python test_tabella_115.py"""
import json
import os
import shutil
import tempfile

T = tempfile.mkdtemp(prefix="tab115-", dir=os.environ.get("TMPDIR"))
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

f, sb = X.tabella_emozioni()
it = {x["en"]: x["it"] for x in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "emozioni.json")))}
F = dict(zip((it[e] for e in X.EMOZIONI), f))
assert (F["estasi"], F["gioia"], F["serenità"], F["diletto"], F["cinismo"]) == (1.0, 0.8, np.float32(0.4), np.float32(0.6), np.float32(0.6))
S = dict(zip((it[e] for e in X.EMOZIONI), sb))
assert abs(S["sorpresa"] - 0.02284) < 1e-6 and abs(S["colpa"] - 0.00019) < 1e-6 and abs(S["gioia"] - 0.0019) < 1e-6

print("test_tabella_115: TUTTO VERDE (migrazione e aggiungi col fattore: test_carica_116.py)")
shutil.rmtree(T)
