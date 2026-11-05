#!/usr/bin/env python3
"""Fedelta' di B2 (PIANO-FIRMA-ENGRAMMI.md): le firme dei 10 messaggi veri lette dal server (fedelta-server.json, da
test_firma_se.py) contro le stesse lette col modello HF. GPU: solo con llama-35b e il server di prova spenti.
Uso: cd /data/jspace && HF_HOME=/data/jspace/hf MODELLO_35B=Accio-Lab/occamy-1.0 OUT_35B=/data/jspace/out-occamy \
     PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True venv/bin/python /data/memoria-episodica-affettiva/engrammi/test_fedelta_hf.py"""
import json
import sys

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import tagging35b as T  # noqa: E402,F401  (percorsi di jspace e jlens, ambiente offline)
import firma_se as F    # noqa: E402
import mixed35b as M    # noqa: E402

voci = json.load(open("/data/memoria-episodica-affettiva/engrammi/fedelta-server.json"))
assert len(voci) == 10
s = M.load()
cosi, pearson, stesso = [], [], 0
for v in voci:
    fs = np.asarray(v["firma"])
    fh = F.firma_hf(s, v["contesto"], v["messaggio"])
    cosi.append(float(fs @ fh / (np.linalg.norm(fs) * np.linalg.norm(fh))))
    pearson.append(float(np.corrcoef(fs, fh)[0, 1]))
    stesso += int(np.argmax(fs) == np.argmax(fh))
    v["firma_hf"] = fh.tolist()
json.dump(voci, open("/data/memoria-episodica-affettiva/engrammi/fedelta-hf.json", "w"), ensure_ascii=False)
print(f"coseno server/HF min {min(cosi):.4f} medio {np.mean(cosi):.4f}; Pearson min {min(pearson):.4f}; "
      f"stesso asse massimo {stesso}/10")
verde = min(cosi) >= 0.99 and min(pearson) >= 0.97 and stesso >= 9
print("TUTTO VERDE" if verde else "ROSSO")
sys.exit(0 if verde else 1)
