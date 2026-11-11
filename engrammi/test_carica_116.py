#!/usr/bin/env python3
"""test della 1.16.0 (PIANO-1.16-CARICA-PER-ARCO.md): peso W per arco (centrali piu' carichi, media del ricordo 1),
migrazione dalla 1.15.0, archi nuovi con fattore e peso. Su una COPIA (LUX_DIR temporanea); embedder :8094.
Uso: cd engrammi && /data/venv-spacy/bin/python test_carica_116.py"""
import json
import os
import shutil
import tempfile

T = tempfile.mkdtemp(prefix="car116-", dir=os.environ.get("TMPDIR"))
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

# 1.17.0: la migrazione 1.15.0 -> 1.16.0 e' fatta; qui la 1.16.0 vera (sola lettura) contro la 1.15.0, poi aggiungi
# su una copia fatta con la migrazione di oggi (1.16.0 -> 1.17.0)
p = np.load("/data/memoria-episodica-affettiva/engrammi/lux-1.15.0/lux.npz")
z = np.load("/data/memoria-episodica-affettiva/engrammi/lux-1.16.0/lux.npz")
W = z["W"]
assert W.shape == (len(z["A"]),) and (W > 0).all()
assert np.allclose(z["C"], p["C"] * W[:, None]) and np.allclose(z["C0"], p["C0"] * W[:, None]), "carica non pesata"
assert np.allclose(z["F"], X.firme_engrammi(z["A"], z["C"], len(z["V"]))), "F non ricalcolata"
assert np.allclose(W, X.pesi_archi(p["A"], p["V"], p["C0"])), "W della 1.16.0 diversa da pesi_archi"

# media 1 per ricordo (la carica media del ricordo resta firma x fattore), 1 per archi soli, correzioni e legami
A, C0 = z["A"], z["C0"]
vivi = (A[:, 1] >= 0) & p["C0"].any(1)
per = {}
for j in np.nonzero(vivi)[0].tolist():
    per.setdefault(int(A[j, 0]), []).append(j)
assert all(abs(W[js].mean() - 1) < 1e-4 for js in per.values()), "media dei pesi del ricordo diversa da 1"
assert (W[~vivi] == 1).all() and all(W[js[0]] == 1 for js in per.values() if len(js) == 1)
lunghi = [js for js in per.values() if len(js) >= 4]
spread = np.median([W[js].max() / W[js].min() for js in lunghi])
assert 1.3 < spread < 4, spread   # contrasto 3: centrale circa il doppio del contorno

# l'arco centrale e' quello coi due engrammi piu' vicini al senso del ricordo
js = max(lunghi, key=len)
e = sorted({int(v) for j in js for v in A[j, 2:4]})
V = z["V"][e].astype(np.float32)
m = V.mean(0) / np.linalg.norm(V.mean(0))
c = dict(zip(e, np.clip(V @ m, 0, None)))
cj = [(c[int(A[j, 2])] + c[int(A[j, 3])]) / 2 for j in js]
assert int(np.argmax(cj)) == int(np.argmax(W[js])) and int(np.argmin(cj)) == int(np.argmin(W[js]))

# un ricordo nuovo: carica = firma x fattore x peso, pesi a media 1, W allungata
X.PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.18.0"   # 1.19.0: da_precedente = copia identica
X.da_precedente()
firma = {"joy": 2.5, "serenity": 2.0, "fear": -1.0}
n_a = len(np.load(X.NPZ)["A"])
X._aggiungi([(999999, "Oggi al mare con l'utente abbiamo visto un delfino saltare vicino alla barca, poi il vento e' "
                      "girato e siamo tornati al porto ridendo.", json.dumps(firma), "vissuto", 1794400000.0)])
z = np.load(X.NPZ)
Wn = z["W"][n_a:]
assert len(z["W"]) == len(z["A"]) == len(z["C"]) == len(z["C0"]) and len(Wn) >= 2 and abs(Wn.mean() - 1) < 1e-4
assert np.allclose(z["C"][n_a:], X.carica(json.dumps(firma)) * z["fattore"] * Wn[:, None])
assert np.array_equal(z["C0"][n_a:], z["C"][n_a:]) and Wn.max() > Wn.min()
L = X.Lux.struttura(X.DIR)
assert np.array_equal(L.W, z["W"]) and L.forza(999999, "joy") is not None
shutil.rmtree(T)
print(f"test_carica_116: TUTTO VERDE (rapporto centrale/contorno in mediana {spread:.2f})")
