"""Il Lux degli engrammi da capo a fondo su un Lux minuscolo (interfase 3-4 punto 2, l'utente 14/11/2026): costruzione,
richiamo, consegna, ricombinazione, forza, ricordi nuovi, correzione, fonti, lavori della notte, versione dalla
precedente. Niente dati veri, niente embedder (lux_minuscolo.py). Orologio fermo.
Il confronto e' con dati-prova/attesi-minuscolo.json (sha256 per voce): un cambio di comportamento lo fa fallire.
Uso: cd engrammi && /data/venv-spacy/bin/python test_lux_minuscolo.py [--registra]   (--registra = nuovi attesi,
solo dopo un cambio VOLUTO)"""
import hashlib
import json
import os
import sys
import time

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
import lux_minuscolo  # noqa: E402

T0 = lux_minuscolo.T0 + 86400 * 3
time.time = lambda: T0
X = lux_minuscolo.prepara()
ATTESI = os.path.join(QUI, "dati-prova", "attesi-minuscolo.json")
out = {}


def h(o):
    return hashlib.sha256(repr(o).encode()).hexdigest()


def contenuto(d):
    r = {}
    for f in sorted(os.listdir(d)):
        p = f"{d}/{f}"
        if f.endswith(".npz"):   # lux.npz col formato a blocchi: il contenuto rimontato (1.25.0)
            z = X.carica_npz(p) if f == "lux.npz" and hasattr(X, "carica_npz") else np.load(p)
            r[f] = hashlib.sha256(b"".join(k.encode() + np.ascontiguousarray(z[k]).tobytes()
                                           for k in sorted(z))).hexdigest()
        elif f.endswith(".json"):
            r[f] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return r


oggi = X.giorno_di(T0)
out["costruzione"] = contenuto(X.DIR)
L = X.Lux()
assert len(L.ricordi) == 12 and len(L.testi) > 12
indizi = [L.testi[i] + ". " + L.testi[i + 3] for i in range(0, len(L.testi) - 3, 5)]
r = [L.richiama(t, 3, 0, oggi=oggi, ora=T0) for t in indizi]
assert sum(bool(x) for x in r) >= len(indizi) // 2, "il richiamo non trova quasi niente"
out["richiama"] = h(r)
out["ricomponi"] = h({n: L.ricomponi(n) for n in sorted(L.ricordi)})
assert L.ricomponi(1) == lux_minuscolo.FRASI[0], L.ricomponi(1)
out["frasi"] = h({n: L.frasi(n) for n in sorted(L.ricordi)})
c = [L.consegna(t, oggi=oggi, ora=T0) for t in indizi[:4]]
out["consegna"] = h(c)
out["risposta_tool"] = h([L.risposta_tool([n for n, _, _ in x]) for x in c])
out["ricombina"] = h([L.ricombina(t, numero=i + 1, oggi=oggi, ora=T0) for i, t in enumerate(indizi[4:8])])
out["forza"] = h([L.forza(n, e) for n in sorted(L.ricordi) for e in X.EMOZIONI[:6]])
L.salva_stato()
out["dopo_consegne"] = contenuto(X.DIR)

nuovo = {"testo": "La lampada del soggiorno adesso fa una luce calda.", "firma": L.ricordi[11]["firma"],
         "classe": "vissuto", "ts": T0, "fonte": X.FONTE_CERTA, "salienza": 0.5, "voluto": 0, "cattura": None,
         "dominante": L.ricordi[11]["dominante"]}
out["aggiungi_ricordo"] = h(X.aggiungi_ricordo(nuovo))
cod = X.correggi(L.ricordi[3]["codice"], "Abbiamo cucinato la pasta al forno con le zucchine.", ts=T0)
out["correggi"] = h(cod)
L = X.Lux()
assert len(L.ricordi) == 14, len(L.ricordi)
out["fonti"] = h([L.conferma(n) for n in sorted(L.ricordi)])
out["dopo_aggiunte"] = contenuto(X.DIR)

out["riaccendi"] = h(X.riaccendi())
out["riconsolida"] = h(X.riconsolida(oggi=oggi))
out["avvicina"] = h(X.avvicina(oggi=oggi))
out["sbiadisci"] = h(X.sbiadisci(oggi=oggi))
out["pota_ponti"] = h(X.pota_ponti())
out["dopo_notte"] = contenuto(X.DIR)

base = os.path.dirname(X.DIR)
X.PRECEDENTE, nuova = X.DIR, f"{base}/lux-nuova"
X.DIR, X.NPZ, X.META, X.STATO = nuova, f"{nuova}/lux.npz", f"{nuova}/lux-meta.json", f"{nuova}/lux-stato.npz"
X.da_precedente()
out["da_precedente"] = contenuto(nuova)

# 1.25.0 (punto 3): formato a blocchi. Un lux.npz di prima (V e sal_F dentro) si legge, una notte lo riscrive nel
# formato nuovo senza perdere righe; un blocco avanzato da una scrittura interrotta si ignora e si toglie.
import shutil  # noqa: E402
z = X.carica_npz()
assert sorted(f for f in os.listdir(nuova) if f[0] != ".") == ["lux-C0-0000000000.npy", "lux-V-0000000000.npy", "lux-meta.json",
                                                                 "lux-salF-0000000000.npy", "lux-stato.npz", "lux.npz"], os.listdir(nuova)
assert "V" not in np.load(X.NPZ).files and np.load(X.NPZ)["A"].dtype == np.int32
vecchia = f"{base}/lux-vecchia"
os.makedirs(vecchia)
np.savez(f"{vecchia}/lux.npz", **z)
for f in ("lux-meta.json", "lux-stato.npz"):
    shutil.copy2(f"{nuova}/{f}", f"{vecchia}/{f}")
X.DIR, X.NPZ, X.META, X.STATO = vecchia, f"{vecchia}/lux.npz", f"{vecchia}/lux-meta.json", f"{vecchia}/lux-stato.npz"
assert all(np.array_equal(X.carica_npz()[k], z[k], equal_nan=True) for k in z), "formato di prima letto male"
X.pota_ponti()
X.salva_npz(X.carica_npz())
assert "V" not in np.load(X.NPZ).files and all(np.array_equal(X.carica_npz()[k], z[k], equal_nan=True) for k in z), "righe perse"
np.save(f"{vecchia}/lux-V-{len(z['V']):010d}.npy", z["V"][:3])   # avanzo: lux.npz non lo conta
assert len(X.carica_npz()["V"]) == len(z["V"])
X.salva_npz(X.carica_npz())
assert not os.path.exists(f"{vecchia}/lux-V-{len(z['V']):010d}.npy"), "avanzo non tolto"

# costruisci riprende i vettori da una precedente nel formato a blocchi (bug trovato dai test il 14/11)
X.PRECEDENTE, rifatta = nuova, f"{base}/lux-rifatta"
X.DIR, X.NPZ, X.META, X.STATO = rifatta, f"{rifatta}/lux.npz", f"{rifatta}/lux-meta.json", f"{rifatta}/lux-stato.npz"
X.costruisci()
assert np.array_equal(X.carica_npz()["V"], X.carica_npz(f"{nuova}/lux.npz")["V"]), "vettori non ripresi dalla precedente"

if "--registra" in sys.argv:
    os.makedirs(os.path.dirname(ATTESI), exist_ok=True)
    json.dump(out, open(ATTESI, "w"), indent=1, sort_keys=True)
    print(f"test_lux_minuscolo: registrati {len(out)} attesi in {ATTESI}")
else:
    attesi = json.load(open(ATTESI))
    diversi = [k for k in sorted(set(out) | set(attesi)) if out.get(k) != attesi.get(k)]
    assert not diversi, f"comportamento cambiato: {diversi}"
    print(f"test_lux_minuscolo: OK ({len(out)} voci identiche)")
