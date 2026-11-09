"""09/11: una volta. Nei ricordi di memoria.db con dominante (emo_tag) senza vettore di steering, la dominante
diventa la piu' forte fra le emozioni con vettore (memoria.dominante). Firma e salienza restano. Copia del db prima.
Uso: python migra_dominante.py [percorso di memoria.db]"""
import json
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # la cartella di memoria.py
import memoria  # noqa: E402

db = sys.argv[1] if len(sys.argv) > 1 else str(memoria.DB)
c = sqlite3.connect(db)
cambi = [(memoria.dominante(json.loads(f)), i, t) for i, t, f in c.execute("SELECT id, emo_tag, firma FROM nodi")
         if f and t not in memoria.CON_VETTORE]
cambi = [x for x in cambi if x[0] != x[2]]
if cambi:
    c.close()
    shutil.copy2(db, db + ".bak-pre-dominante")
    c = sqlite3.connect(db)
    with c:
        c.executemany("UPDATE nodi SET emo_tag = ? WHERE id = ?", [(d, i) for d, i, _ in cambi])
for d, i, t in cambi:
    print(f"{i}: {t} -> {d}")
print(f"{len(cambi)} ricordi cambiati")
