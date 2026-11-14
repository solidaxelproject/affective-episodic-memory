#!/usr/bin/env python3
"""Prova 1.24.0 (PIANO-1.24-FONTI.md, Task 6): sul Lux 1.23.0 senza siti il codice nuovo richiama, ricompone e da' il
profilo emotivo come il vecchio (master), su una COPIA. Uso: cd engrammi && /data/venv-spacy/bin/python
prova-fonti-124/prova_fonti_124.py"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

import numpy as np

T = tempfile.mkdtemp(prefix="pf124-")
shutil.copytree("/data/memoria-episodica-affettiva/engrammi/lux-1.23.0", f"{T}/lux")
os.environ["LUX_DIR"] = f"{T}/lux"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def carica(nome, percorso):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


N = carica("nuovo", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lux_engrammi.py"))
V = carica("vecchio", "/data/memoria-episodica-affettiva/engrammi/lux_engrammi.py")
Ln, Lv = N.Lux(), V.Lux()
Ln.salva_stato = Lv.salva_stato = lambda: None
nids = sorted(Lv.ricordi)[::max(1, len(Lv.ricordi) // 50)][:50]
indizi = [" ".join(Lv.ricordi[n]["testo"].split()[:8]) for n in nids]
uguali_r = sum(Ln.richiama(t, 4, oggi=100.0, ora=1.8e9) == Lv.richiama(t, 4, oggi=100.0, ora=1.8e9) for t in indizi)
uguali_c = sum(Ln.ricomponi(n) == Lv.ricomponi(n) for n in Lv.ricordi)
prof = np.array_equal(Ln.prof_nid, Lv.prof_nid) and np.allclose(Ln.profz, Lv.profz)
r = {"indizi": len(indizi), "richiama_uguali": int(uguali_r), "ricordi": len(Lv.ricordi),
     "ricomposizioni_uguali": int(uguali_c), "profilo_uguale": bool(prof), "siti": len(Ln.ricordi_di_sito)}
print(json.dumps(r, indent=1))
json.dump(r, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "risultati.json"), "w"), indent=1)
assert r["richiama_uguali"] == r["indizi"] and r["ricomposizioni_uguali"] == r["ricordi"] and prof
