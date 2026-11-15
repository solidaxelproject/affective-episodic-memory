#!/usr/bin/env python3
"""Fotografia del comportamento del Lux degli engrammi (interfase 3-4, PIANO-INTERFASE-34-DIVISIONE-LUX.md).

Gira il codice di CARTELLA_CODICE (es. /data/memoria-episodica-affettiva/engrammi o il worktree) su COPIE dei dati: Lux 1.24.0,
precedente 1.23.0, diario dei riflessi, giornata delle firme, omeostato, tempo vissuto. Orologio fermo e semi fissi.
I dati si congelano UNA volta (ISTANTANEA, presa sotto il lucchetto del Lux come fa notte-memoria.sh); ogni giro parte
da una copia fresca dell'istantanea. Uscita: json {voce: sha256}; stesso comportamento = stesso file al byte.
Uso: /data/venv-spacy/bin/python foto_lux.py CARTELLA_CODICE USCITA.json [--nuova-istantanea]
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

ENG = "/data/memoria-episodica-affettiva/engrammi"
MEM = "/data/workspace/memoria"
TMP = "/data/tmp-foto-lux"
ISTANTANEA = "/data/tmp-foto-lux-istantanea"
T0 = 1794700000.0   # orologio fermo (14/11/2026 sera circa)

FIGLIO = r'''
import hashlib, json, os, random, sys, time
import numpy as np
T0 = float(os.environ["FOTO_T0"])
time.time = lambda: T0
from pathlib import Path
import lux_engrammi as X
X.PRECEDENTE = os.environ["FOTO_PREC"]
X.LUX.FILE = Path(os.environ["FOTO_OROLOGIO"]) / "lux.npz"   # tempo-vissuto.json congelato
out = {}

def h(o):
    return hashlib.sha256(repr(o).encode()).hexdigest()

def hf(p):
    if p.endswith(".npy"):   # blocchi di V e sal_F (1.25.0): stanno nel contenuto di lux.npz rimontato
        return None
    if p.endswith(".npz"):
        z = X.carica_npz(p) if p.endswith("/lux.npz") and hasattr(X, "carica_npz") else np.load(p)
        return hashlib.sha256(b"".join(k.encode() + np.ascontiguousarray(z[k]).tobytes() for k in sorted(z))).hexdigest()
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def cartella(d):
    return {os.path.relpath(os.path.join(r, f), d): hf(os.path.join(r, f))
            for r, _, fs in os.walk(d) for f in sorted(fs) if not f.startswith(".lucchetto") and not f.endswith(".npy")}

if sys.argv[1] == "lux":
    oggi = X.giorno_di(T0)
    L = X.Lux()
    L.salva_stato = lambda: None
    random.seed(0)
    nids = sorted(n for n in L.ricordi if L.ricordi[n]["n"] >= 6)
    indizi = []
    for nid in random.sample(nids, 50):
        idx = sorted(L.per_ricordo[nid], key=lambda j: L.A[j, 1])
        e = [int(L.A[j, 3]) for j in idx]
        indizi.append(L.testi[e[1]] + ". " + L.testi[e[len(e) // 2 + 1]])
    out["indizi"] = h(indizi)
    out["richiama"] = h([L.richiama(t, 5, 0, oggi=oggi, ora=T0) for t in indizi])
    out["ricomponi"] = h({n: L.ricomponi(n) for n in sorted(L.ricordi)})
    out["frasi"] = h({n: L.frasi(n) for n in sorted(L.ricordi)})
    c = [L.consegna(t, oggi=oggi, ora=T0) for t in indizi[:10]]
    out["consegna"] = h(c)
    out["risposta_tool"] = h([L.risposta_tool([n for n, _, _ in x]) for x in c])
    out["ricombina"] = h([L.ricombina(t, numero=i + 1, oggi=oggi, ora=T0) for i, t in enumerate(indizi[10:20])])
    out["forza"] = h([L.forza(n, e) for n in nids[:30] for e in X.EMOZIONI[:5]])
    out["stato_memoria"] = h({k: (np.asarray(v).tobytes() if isinstance(v, np.ndarray) else repr(v))
                              for k, v in sorted(vars(L).items()) if not callable(v) and k not in ("L29", "ha_l29")})   # tolti col punto 4
    out["riaccendi"] = h(X.riaccendi())
    out["riconsolida"] = h(X.riconsolida(oggi=oggi))
    out["avvicina"] = h(X.avvicina(oggi=oggi))
    out["sbiadisci"] = h(X.sbiadisci(oggi=oggi))
    out["pota_ponti"] = h(X.pota_ponti())
    cod = L.ricordi[nids[0]]["codice"]
    out["correggi"] = h(X.correggi(cod, "Correzione di prova della fotografia.", ts=T0))
    out["file_lux"] = cartella(X.DIR)
elif sys.argv[1] == "precedente":
    X.da_precedente()
    out["file_da_precedente"] = cartella(X.DIR)
print(json.dumps(out))
'''


def copia(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def istantanea():
    import fcntl
    shutil.rmtree(ISTANTANEA, ignore_errors=True)
    os.makedirs(f"{ISTANTANEA}/orologio")
    with open(f"{ENG}/lux-1.24.0/.lucchetto", "a") as lp:
        fcntl.flock(lp, fcntl.LOCK_EX)
        shutil.copytree(f"{ENG}/lux-1.24.0", f"{ISTANTANEA}/lux", ignore=shutil.ignore_patterns(".lucchetto", "notti"))
    shutil.copytree(f"{ENG}/lux-1.23.0", f"{ISTANTANEA}/prec", ignore=shutil.ignore_patterns(".lucchetto"))
    for f in ("diario-riflessi.jsonl", "giornata-firma.jsonl", "stato-emotivo.json"):
        copia(f"{MEM}/{f}", f"{ISTANTANEA}/{f}")
    copia(f"{MEM}/tempo-vissuto.json", f"{ISTANTANEA}/orologio/tempo-vissuto.json")


def main():
    codice, uscita = os.path.abspath(sys.argv[1]), sys.argv[2]
    if "--nuova-istantanea" in sys.argv or not os.path.isdir(ISTANTANEA):
        istantanea()
    shutil.rmtree(TMP, ignore_errors=True)
    shutil.copytree(ISTANTANEA, TMP)
    base = {**os.environ, "FOTO_T0": str(T0), "FOTO_PREC": f"{TMP}/prec", "PYTHONHASHSEED": "0",
            "FOTO_OROLOGIO": f"{TMP}/orologio",
            "DIARIO_RIFLESSO": f"{TMP}/diario-riflessi.jsonl", "GIORNATA_FIRMA": f"{TMP}/giornata-firma.jsonl",
            "OMEOSTATO": f"{TMP}/stato-emotivo.json"}
    foto = {}
    for modo, lux_dir in (("lux", f"{TMP}/lux"), ("precedente", f"{TMP}/dp")):
        r = subprocess.run([sys.executable, "-c", FIGLIO, modo], cwd=codice, env={**base, "LUX_DIR": lux_dir},
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"{modo}: errore\n{r.stderr[-3000:]}")
        foto.update(json.loads(r.stdout.strip().splitlines()[-1]))
    foto["altri_file"] = {f: hashlib.sha256(open(f"{TMP}/{f}", "rb").read()).hexdigest()
                          for f in ("diario-riflessi.jsonl", "giornata-firma.jsonl", "stato-emotivo.json")}
    json.dump(foto, open(uscita, "w"), indent=1, sort_keys=True)
    print(f"{uscita}: {len(foto)} voci")


if __name__ == "__main__":
    main()
