# Passo 2 del motore di autonomia: righe nude del blocco appunti -> arricchite.
#
#   [tema]{query}                       -> [id-neurone|cos|salienza] [tema]{query}
#
# L'aggancio usa la route /lux-read (16/07): stato L34 dal server VIVO, 0.4s,
# l'agente non si ferma. Ricetta identica a tagging35b: media L34 - BASE, poi
# confronta() per il ricordo più vicino (id STABILE, C1) e V34@st -> z per la
# salienza dell'appunto (presa alla formazione, dottrina D3).
# Sotto soglia la riga resta nuda: fallback di il progetto, in fondo alla coda.
import json
import re
import sys
import urllib.request
from pathlib import Path

APPUNTI = Path("/data/workspace/memoria/appunti.md")
BASE_PT = "/data/workspace/memoria/base-L34.pt"
EMOVEC = "/data/models/emovec.pt"
STATS = "/data/workspace/memoria/stats-popolazione.pt"
LUX_READ = "http://127.0.0.1:8090/lux-read"
LAYER = 34
# Tarata il 16/07 su 25 sonde (12 substringhe vere, 5 parafrasi, 8 estranei):
# parafrasi 0.369-0.398, estranei max 0.354. NON è la scala di SOGLIA_ARCO (0.5):
# un appunto corto contro un ricordo lungo vive più in basso (media su pochi
# token). ponytail: margine sottile (~0.015), errori borderline possibili e
# tollerati: falso aggancio = ricordo parente alla lontana, falso scarto =
# riga nuda in coda. Ritarare quando gli appunti veri dell'agente saranno decine.
SOGLIA = 0.36

RIGA = re.compile(r"^\s*(?:\[(?P<meta>[^\]]*)\])?\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")


def arricchisci(righe, aggancia):
    """Righe nude -> arricchite. Pura: l'aggancio arriva da fuori."""
    fuori = []
    for r in righe:
        m = RIGA.match(r)
        if not m or m["meta"] is not None or r.strip().startswith("~~"):
            fuori.append(r)          # non-appunto, già arricchita, o depennata
            continue
        a = aggancia(r.strip())
        if a is None:
            fuori.append(r)          # sotto soglia: resta nuda, andrà in fondo
            continue
        fuori.append(f"[{a['id']}|{a['cos']}|{a['salienza']}] {r.strip()}")
    return fuori


def aggancio_vero(testo):
    import numpy as np
    import torch
    sys.path.insert(0, ".")
    from lux import Lux

    req = urllib.request.Request(
        LUX_READ, data=json.dumps({"content": testo, "layer": LAYER}).encode(),
        headers={"Content-Type": "application/json"})
    st = np.array(json.loads(urllib.request.urlopen(req, timeout=120).read())["mean"],
                  np.float32)
    st -= torch.load(BASE_PT, weights_only=True).float().numpy()

    hit = (Lux().confronta(st, via="semantica", k=1) or [None])[0]
    if hit is None or hit["sim"] < SOGLIA:
        return None

    d = torch.load(EMOVEC, weights_only=True)
    V34 = np.stack([(v := d["vectors"][e][LAYER].float().numpy()) / np.linalg.norm(v)
                    for e in d["vectors"]])
    z = torch.load(STATS, weights_only=True)
    salienza = float(((V34 @ st - z["mu"].numpy()) / (z["sd"].numpy() + 1e-6)).max())
    return {"id": hit["id"], "cos": hit["sim"], "salienza": round(salienza, 2)}


if __name__ == "__main__":
    if not APPUNTI.exists():
        print("nessun blocco appunti: niente da fare")
        sys.exit(0)
    righe = APPUNTI.read_text(encoding="utf-8").splitlines()
    fuori = arricchisci(righe, aggancio_vero)
    if fuori != righe:
        tmp = APPUNTI.with_suffix(".tmp")
        tmp.write_text("\n".join(fuori) + "\n", encoding="utf-8")
        tmp.replace(APPUNTI)
    print(f"{sum(1 for a, b in zip(righe, fuori) if a != b)} appunti agganciati")
