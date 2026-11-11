#!/usr/bin/env python3
"""test della 1.14.0 (PIANO-1.14-RICONSOLIDAMENTO.md): migrazione, M, effetto zero, effetto acceso, chiavi nuove tenute
da correggi/aggiungi. Su una COPIA del Lux in una cartella temporanea (LUX_DIR), diario e registro finti; embedder :8094
acceso (correggi). Uso: cd engrammi && /data/venv-spacy/bin/python test_riconsolida.py"""
import json
import os
import shutil
import tempfile

T = tempfile.mkdtemp(prefix="ric114-", dir=os.environ.get("TMPDIR"))
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

X.PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.18.0"   # 1.19.0: da_precedente = copia identica; la migrazione 1.17.0 e la prova test_contatori_117.py
X.DIARIO_RIFLESSO, X.GIORNATA = f"{T}/diario.jsonl", f"{T}/giornata.jsonl"
X.da_precedente()
z = np.load(X.NPZ)
assert np.isnan(z["rodaggio_da"])
zz = dict(z)
zz["M"] = np.zeros((0, 4 + len(X.EMOZIONI)))   # la copia parte senza momenti (quelli veri della 1.14.0 restano li')
np.savez(X.NPZ + ".tmp.npz", **zz)
os.replace(X.NPZ + ".tmp.npz", X.NPZ)
FATT = z["fattore"].astype(np.float64)

L = X.Lux.struttura(X.DIR)
n1, n2 = [n for n in sorted(L.ricordi) if any(L.C[j].any() for j in L.per_ricordo.get(n, ()))][:2]
F1 = {e: 0.5 for e in X.EMOZIONI[:44]}
F2 = {e: -1.0 for e in X.EMOZIONI[:44]}


def scrivi(f, voci):
    with open(f, "a") as h:
        for v in voci:
            h.write(json.dumps(v) + "\n")


scrivi(X.DIARIO_RIFLESSO, [{"ts": 1000.0, "memorinvolontaria": ["a"], "nid": [n1], "flusso": "chat"},
                           {"ts": 2000.0, "memorinvolontaria": ["b"], "nid": [n2], "flusso": "chat"},
                           {"ts": 3000.0, "memorinvolontaria": ["c"], "nid": [n1], "flusso": "pensatoio"},
                           {"ts": 5000.0, "memorinvolontaria": ["d"], "nid": [n1], "flusso": "chat"},
                           {"ts": 9000.0, "memorinvolontaria": ["e"], "nid": [n1]},   # voce di prima: senza flusso
                           {"ts": 4000.0, "kill": "altro"}])
L'AGENTE = "@agente:localhost"
scrivi(X.GIORNATA, [{"ts": 1500.0, "autore": L'AGENTE, "testo": "r1", "firma": F1, "flusso": "chat"},
                    {"ts": 1500.0, "autore": "@utente:localhost", "testo": "l", "firma": F2},
                    {"ts": 2500.0, "autore": L'AGENTE, "testo": "r2p", "firma": F2, "flusso": "pensatoio"},
                    {"ts": 2600.0, "autore": L'AGENTE, "testo": "r2", "esito": "corto", "flusso": "chat"},
                    {"ts": 3100.0, "autore": L'AGENTE, "testo": "forzato", "firma": F2, "forzato": True, "flusso": "pensatoio"},
                    {"ts": 3200.0, "autore": L'AGENTE, "testo": "r3", "firma": F2, "flusso": "pensatoio"},
                    {"ts": 9000.0 + X.FINESTRA_MOMENTO + 1, "autore": L'AGENTE, "testo": "tardi", "firma": F1}])
prima = {k: np.load(X.NPZ)[k] for k in ("C", "C0", "F", "A")}
stato = {k: np.load(X.STATO)[k] for k in ("S", "S0", "U")}

# effetto zero (rodaggio_da NaN): solo M
r = X.riconsolida(oggi=100.0)
assert r["momenti"] == 3 and r["spostati"] == 0 and r["effetto"] == 0.0, r
z = np.load(X.NPZ)
assert all(np.array_equal(prima[k], z[k]) for k in prima), "effetto zero ha toccato C/C0/F/A"
assert all(np.array_equal(stato[k], np.load(X.STATO)[k]) for k in stato), "effetto zero ha toccato lo stato"
M = z["M"]
assert [(int(a), b) for a, b in M[:, :2]] == [(n1, 1000.0), (n2, 2000.0), (n1, 3000.0)], M[:, :3]
assert M[0, 2] == 1500.0 and M[1, 2] == 2600.0 and M[2, 2] == 3200.0, "risposta sbagliata (flusso, forzati, corti)"
assert np.isnan(M[1, 3:]).all(), "la prima risposta senza firma deve dare un momento vuoto"
L = X.Lux.struttura(X.DIR)
j = next(j for j in L.per_ricordo[n1] if L.C0[j].any())
m = np.array([F1.get(e, np.nan) for e in X.EMOZIONI]) * FATT   # 1.15.0: momento nella scala della carica
k = ~np.isnan(m)
assert abs(M[0, 3] - np.sqrt(np.mean((m[k] - L.C[j][k] / L.W[j]) ** 2))) < 1e-6, "sorpresa = RMS sugli assi del momento"
t = os.path.getmtime(X.NPZ)
assert X.riconsolida(oggi=100.0)["momenti"] == 0 and os.path.getmtime(X.NPZ) == t, "rifatto o riscritto senza novita'"

# la consegna delle 5000 senza risposta si riprende quando la risposta arriva, anche dopo una piu' nuova (9000, senza flusso)
scrivi(X.GIORNATA, [{"ts": 9500.0, "autore": L'AGENTE, "testo": "r9", "firma": F2, "flusso": "pensatoio"}])
assert X.riconsolida(oggi=100.0)["momenti"] == 1
scrivi(X.GIORNATA, [{"ts": 5100.0, "autore": L'AGENTE, "testo": "r5", "firma": F1, "flusso": "chat"}])
assert X.riconsolida(oggi=100.0)["momenti"] == 1 and len(np.load(X.NPZ)["M"]) == 5

# rodaggio (punto 9)
assert [X._rodaggio(g) for g in (0, 9.9, 10, 19, 25, 30, 400)] == [0.1, 0.1, 0.3, 0.3, 0.7, 1.0, 1.0]

# una correzione (embedder vero) tiene C0 allineata, M e rodaggio_da
cod = X.correggi(L.ricordi[n2]["codice"], "Il gatto si chiamava Neve, non Bianca.", ts=7777.0)
z = np.load(X.NPZ)
assert len(z["C0"]) == len(z["A"]) == len(z["C"]) and len(z["M"]) == 5 and np.isnan(z["rodaggio_da"]), "chiavi 1.14 perse"
assert np.array_equal(z["C0"][:len(prima["C0"])], prima["C0"])
L = X.Lux.struttura(X.DIR)
nc = L.da_codice[cod]
assert nc >= X.PRIMO_CORREZIONE and n2 in L.errati

# effetto acceso: soglia 0, rodaggio pieno
zz = dict(np.load(X.NPZ))
zz["rodaggio_da"] = np.float64(500.0)   # accensione nel futuro: ancora niente
np.savez(X.NPZ + ".tmp.npz", **zz)
os.replace(X.NPZ + ".tmp.npz", X.NPZ)
X.SOGLIA_SORPRESA = 0.0
scrivi(X.DIARIO_RIFLESSO, [{"ts": 15000.0, "memorinvolontaria": ["x"], "nid": [n1], "flusso": "chat"}])
scrivi(X.GIORNATA, [{"ts": 15100.0, "autore": L'AGENTE, "testo": "r15", "firma": F1, "flusso": "chat"}])
r = X.riconsolida(oggi=90.0)
assert r["momenti"] == 1 and r["spostati"] == 0, r
zz = dict(np.load(X.NPZ))
zz["rodaggio_da"] = np.float64(50.0)
np.savez(X.NPZ + ".tmp.npz", **zz)
os.replace(X.NPZ + ".tmp.npz", X.NPZ)
X.SOGLIA_SORPRESA = 0.0
prima = {k: np.load(X.NPZ)[k] for k in ("C", "C0")}
stato = {k: np.load(X.STATO)[k] for k in ("S", "S0")}
scrivi(X.DIARIO_RIFLESSO, [{"ts": 20000.0, "memorinvolontaria": ["f"], "nid": [n1], "flusso": "chat"},
                           {"ts": 20001.0, "memorinvolontaria": ["g"], "nid": [n2], "flusso": "chat"},
                           {"ts": 20002.0, "memorinvolontaria": ["h"], "nid": [nc], "flusso": "chat"}])
scrivi(X.GIORNATA, [{"ts": 20100.0, "autore": L'AGENTE, "testo": "r20", "firma": F1, "flusso": "chat"}])
r = X.riconsolida(oggi=90.0)
assert r["momenti"] == 3 and r["effetto"] == 1.0, r
z, s = np.load(X.NPZ), np.load(X.STATO)
js = [j for j in L.per_ricordo[n1] if L.C0[j].any()]
cambiati = np.nonzero((z["C"] != prima["C"]).any(1))[0].tolist()
assert cambiati and set(cambiati) <= set(js), "spostati archi di altri ricordi (o niente)"
for j in js:
    alfa = X.ALFA / (1 + max(0.0, np.log(stato["S"][j] / stato["S0"][j])))
    mw = m * L.W[j]   # 1.16.0: bersaglio dell'arco = momento x fattore x peso
    atteso = prima["C"][j] + np.where(k, np.clip(alfa * (np.nan_to_num(mw) - prima["C"][j]) / L.W[j], -X.PASSO_MAX,
                                                 X.PASSO_MAX) * L.W[j], 0)
    assert np.allclose(z["C"][j], atteso), j
    assert (np.abs(z["C"][j][k] - mw[k]) <= np.abs(prima["C"][j][k] - mw[k]) + 1e-6).all(), "la carica ha superato il momento"
    q = z["C"][j]
    assert abs(s["S0"][j] / stato["S0"][j] - s["S"][j] / stato["S"][j]) < 1e-9, "S e S0 non scalate insieme"
assert np.array_equal(z["C0"], prima["C0"]), "C0 deve restare quella della nascita"
assert np.allclose(z["F"], X.firme_engrammi(z["A"], z["C"], len(z["V"]))), "F non ricalcolata"
L2 = X.Lux.struttura(X.DIR)
dom = X.EMOZIONI[int(np.argmax(L2.C0[js[0]]))]   # w0 dalla nascita: la forza c'e' ancora e segue la carica nuova
assert L2.forza(n1, dom) is not None and L2.forza(n1, dom) != X.Lux.struttura(f"{X.PRECEDENTE}").forza(n1, dom)
shutil.rmtree(T)
print("test_riconsolida: TUTTO VERDE")
