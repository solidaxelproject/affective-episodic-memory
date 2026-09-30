# Ricostruzione di Lux dal grafo (v2, 28/07: IDEMPOTENTE, registro dec. 9).
# La v1 riversava le memorie SOPRA l'organo vivo: lanciata due volte
# raddoppiava i neuroni (trappola armata, censimento fase 0). Ora:
#   1. backup di lux.npz + lux-meta.json (con timestamp)
#   2. organo AZZERATO e ricostruito dal grafo in ordine cronologico
#   3. se qualcosa fallisce, i backup tornano al loro posto da soli
# Resta lo strumento di emergenza della sentinella anti-amnesia.
import json
import shutil
import sqlite3
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import lux as lux_mod
from lux import Lux

DB = "/data/workspace/memoria/memoria.db"
VEC = "/data/workspace/memoria/vettori.pt"


def carica_memorie():
    v = torch.load(VEC, weights_only=True)
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    righe = c.execute("SELECT id, ts, firma, emo_tag, testo, classe FROM nodi "
                      "WHERE classe='vissuto' ORDER BY ts").fetchall()
    c.close()
    return [(r, v[r[0]]["addr_sem"].float().numpy()) for r in righe if r[0] in v]


def backup():
    ts = time.strftime("%Y%m%d-%H%M")
    salvati = []
    for f in (str(lux_mod.FILE), str(lux_mod.META)):
        try:
            shutil.move(f, f + f".bak-rebuild-{ts}")
            salvati.append((f + f".bak-rebuild-{ts}", f))
        except FileNotFoundError:
            pass
    return salvati


def ripristina(salvati):
    for bak, orig in salvati:
        shutil.move(bak, orig)


def ricostruisci(memorie):
    g = Lux()                      # file assenti = organo nuovo, vuoto
    if g.pca_mu is None:
        g.fit_encoder(np.stack([st for _, st in memorie]))
    nati = rinforzati = 0
    for (r, st) in memorie:
        firma = json.loads(r[2])
        f51 = np.array([firma[e] for e in sorted(firma)], np.float32)
        _, esito = g.esperisci(st, f51, nodo_id=r[0])
        nati += esito == "nato"
        rinforzati += esito == "rinforzato"
    g.salva()
    return g, nati, rinforzati


def main():
    memorie = carica_memorie()
    print(f"{len(memorie)} memorie vissute da rivivere")
    salvati = backup()
    print("backup:", [b for b, _ in salvati] or "nessun organo precedente")
    try:
        g, nati, rinforzati = ricostruisci(memorie)
    except Exception:
        ripristina(salvati)
        print("FALLITO: organo precedente RIPRISTINATO dai backup")
        raise
    print(f"organo ricostruito: {g.stats()} (nati {nati}, "
          f"rinforzati {rinforzati}); i backup restano su disco")


if __name__ == "__main__":
    main()
