#!/usr/bin/env python3
"""PIANO-FIRMA-44-ASSI.md, task 6 (09/11): dopo la rifirma di memoria.db a 44 assi, l'emozione sugli archi del Lux
(C, 51 colonne nell'ordine di emozioni.json) si rifa' dalla firma nuova del ricordo dell'arco, come da_precedente
(1.13.0): solo gli archi con posizione >= 0 di un ricordo di memoria.db; le altre righe restano come sono. F degli
engrammi = firme_engrammi. A, P, V, salienza, stato dei rinforzi (S, S0, U) intatti: le S0 restano quelle nate con la
firma a 24 assi (sono la storia del ricordo). lux-meta.json riscritta per ultima: il servizio ricarica.
MEM_SAM e LUX_DIR puntano una copia per la prova. Uso: /data/venv-spacy/bin/python aggiorna_c_0911.py"""
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lux_engrammi as X  # noqa: E402

DB = f"{os.environ.get('MEM_SAM', '/data/workspace/memoria')}/memoria.db"

with X.lucchetto():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    firme = dict(c.execute("select id, firma from nodi"))
    c.close()
    z = dict(np.load(X.NPZ))
    if "fattore" in z:   # 1.15.0: rifarebbe C dalla firma grezza senza fattore, con C0 nell'altra scala
        sys.exit("script da una volta del 09/11: non si rilancia dalla 1.15.0")
    A, C = z["A"], z["C"].copy()
    k = np.array([p >= 0 and int(r) in firme for r, p in A[:, :2].tolist()])
    C[k] = np.stack([X.carica(firme[int(r)]) for r in A[k, 0].tolist()])
    z.update(C=C, F=X.firme_engrammi(A, C, len(z["V"])))
    np.savez(X.NPZ + ".tmp.npz", **z)
    m = json.load(open(X.META))
    json.dump(m, open(X.META + ".tmp", "w"), ensure_ascii=False)
    os.replace(X.NPZ + ".tmp.npz", X.NPZ)
    os.replace(X.META + ".tmp", X.META)   # per ultimo: e' il segnale di ricarica del servizio
print(f"Lux: C rifatta su {int(k.sum())} archi di {len(A)}, F di {len(z['V'])} engrammi")
