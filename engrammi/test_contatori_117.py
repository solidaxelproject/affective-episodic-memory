#!/usr/bin/env python3
"""test della 1.17.0 (PIANO-1.17-CONTATORI.md): contatori degli engrammi (nascita, ultima accensione, accensioni),
riaccendi dai messaggi del registro, archi nuovi, ultimo richiamo per ricordo. Su una COPIA (LUX_DIR temporanea),
registro finto, orologio vero (sola lettura); embedder :8094. Uso: cd engrammi && /data/venv-spacy/bin/python test_contatori_117.py"""
import json
import os
import shutil
import tempfile
import time

T = tempfile.mkdtemp(prefix="con117-", dir=os.environ.get("TMPDIR"))
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

# _accendi_contatori: nascita, una accensione per giorno, mai all'indietro
E = (np.array([-1, 3]), np.array([-1, 3]), np.array([0, 0]))
X._accendi_contatori(E, {0: 5, 1: 3})
X._accendi_contatori(E, {0: 5, 1: 7})
X._accendi_contatori(E, {0: 4, 1: 8})
assert E[0].tolist() == [5, 3] and E[1].tolist() == [5, 8] and E[2].tolist() == [0, 2], E
st = json.load(open(X.LUX._file_orologio()))
g, u = int(st["giorni"]), float(st["ultimo_avanzamento"])
assert X.giorno_di(u + 1) == g and X.giorno_di(u - 1) == max(0, g - 1) and X.giorno_di(0) == max(0, g - 1)
assert X.giorno_di(0, indietro=True) == 0 and X.giorno_di(u - 86400 * 1.5, indietro=True) == max(0, g - 2)

X.PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.18.0"   # 1.19.0: copia identica, coi contatori veri
X.GIORNATA = f"{T}/giornata.jsonl"
t0 = time.time()
X.da_precedente()
p, z = np.load(f"{X.PRECEDENTE}/lux.npz"), np.load(X.NPZ)
for k in p.files:
    assert np.array_equal(p[k], z[k], equal_nan=True) if p[k].dtype.kind == "f" else np.array_equal(p[k], z[k]), k
n = len(z["V"])
assert all(len(z[k]) == n for k in ("E_nato", "E_acceso", "E_accensioni")) and 0 < float(z["riacceso_fino"]) <= t0
assert (z["E_nato"] >= 0).all() and (z["E_acceso"] >= z["E_nato"]).all() and (z["E_accensioni"] >= 0).all()
L = X.Lux.struttura(X.DIR)
condivisi = [i for i in range(n) if len({int(L.A[j, 0]) for j in L.per_engramma.get(i, ())}) > 1]
assert condivisi, "nessun engramma in piu' ricordi"

# riaccendi: solo i messaggi dopo riacceso_fino, una accensione per giorno, gli altri engrammi fermi
eng = L.testi[condivisi[0]]
dopo = float(z["riacceso_fino"]) + 10
with open(X.GIORNATA, "w") as f:
    for v in ({"ts": dopo - 100, "autore": "@utente:localhost", "testo": f"vecchio {eng}"},
              {"ts": dopo, "autore": "@utente:localhost", "testo": f"Oggi pensavo a {eng}."},
              {"ts": dopo + 1, "autore": "@agente:localhost", "testo": f"Anche io, {eng}."},
              {"ts": dopo + 2, "autore": "@utente:localhost", "testo": ""}):
        f.write(json.dumps(v) + "\n")
prima = {k: z[k].copy() for k in ("E_nato", "E_acceso", "E_accensioni")}
r = X.riaccendi()
z = np.load(X.NPZ)
i = condivisi[0]
d = X.giorno_di(dopo)
assert r["messaggi"] == 2, r
assert z["E_acceso"][i] == max(prima["E_acceso"][i], d)
assert z["E_accensioni"][i] == prima["E_accensioni"][i] + (1 if d > prima["E_acceso"][i] else 0), "due messaggi, un giorno"
cambiati = np.nonzero(z["E_accensioni"] != prima["E_accensioni"])[0].tolist()
assert len(cambiati) <= 200, len(cambiati)   # solo gli engrammi dei due messaggi
assert float(z["riacceso_fino"]) == dopo + 1 and X.riaccendi()["messaggi"] == 0, "rifatto"

# un ricordo nuovo: i suoi engrammi nuovi nascono oggi, i contatori si allungano, il resto della 1.16 resta
n_a = len(z["A"])
X._aggiungi([(999999, "Oggi al mare con l'utente abbiamo visto un delfino saltare vicino alla barca.",
              json.dumps({"joy": 2.5}), "vissuto", time.time())])
z = np.load(X.NPZ)
assert all(len(z[k]) == len(z["V"]) for k in ("E_nato", "E_acceso", "E_accensioni")) and len(z["V"]) > n
assert (z["E_nato"][n:] == X.giorno_di(time.time())).all() and "W" in z.files and "riacceso_fino" in z.files

# ultimo richiamo alla consegna, salvato nello stato e riletto; aggiungi non lo cancella
L = X.Lux()
c = L.consegna(L.ricomponi(sorted(L.ricordi)[3])[:120], quanti=1)
assert c and c[0][0] in L.R and abs(L.R[c[0][0]] - time.time()) < 60
s = np.load(X.STATO)
assert c[0][0] in s["R_nid"].tolist()
X._aggiungi([(999998, "Il gatto dorme sul divano rosso del soggiorno.", json.dumps({"serenity": 2.0}), "vissuto", time.time())])
assert c[0][0] in np.load(X.STATO)["R_nid"].tolist(), "aggiungi ha cancellato l'ultimo richiamo"
assert c[0][0] in X.Lux().R
shutil.rmtree(T)
print(f"test_contatori_117: TUTTO VERDE ({int((p['A'][:, 1] >= 0).sum())} archi vivi, {len(condivisi)} engrammi in piu' ricordi)")
