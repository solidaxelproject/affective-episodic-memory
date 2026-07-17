# Passo 2 del motore di autonomia, v2 (17/07 sera, scelta di progetto):
# il blocco appunti resta PURO (solo le righe dell'agente, mai metadati in vista).
# Gli agganci [id-neurone, cos, salienza] vivono in un sidecar host-only che
# legge soltanto il motore. La tubatura non deve vedersi.
#
# Ricetta invariata: /lux-read (server vivo) -> -BASE -> confronta() per il
# ricordo più vicino; V34@st -> z-max per la salienza (dottrina D3).
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

APPUNTI = Path("/data/workspace/memoria/appunti.md")
SIDECAR = Path("/data/workspace/memoria/.appunti-agganci.json")
BASE_PT = "/data/workspace/memoria/base-L34.pt"
EMOVEC = "/data/models/emovec.pt"
STATS = "/data/workspace/memoria/stats-popolazione.pt"
LUX_READ = "http://127.0.0.1:8090/lux-read"
LAYER = 34
SOGLIA = 0.36        # tarata 16/07 su 25 sonde: NON è la scala di SOGLIA_ARCO
RITENTA_S = 24 * 3600   # un mancato aggancio si ritenta quando Lux è cresciuta

RIGA = re.compile(r"^\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")


def righe_aperte(testo):
    """Le righe-appunto non depennate, così come le ha scritte l'agente."""
    return [r.strip() for r in testo.splitlines()
            if RIGA.match(r) and not r.strip().startswith("~~")]


def da_agganciare(aperte, sidecar, adesso=None):
    """Quali righe hanno bisogno di un (ri)tentativo di aggancio. Pura."""
    adesso = adesso or time.time()
    fuori = []
    for r in aperte:
        v = sidecar.get(r)
        if v is None:
            fuori.append(r)
        elif "id" not in v and adesso - v.get("ts", 0) > RITENTA_S:
            fuori.append(r)          # sotto soglia allora: Lux cresce, riprova
    return fuori


def potatura(sidecar, aperte):
    """Via le voci di righe depennate o sparite. Pura."""
    return {r: v for r, v in sidecar.items() if r in aperte}


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

    d = torch.load(EMOVEC, weights_only=True)
    V34 = np.stack([(v := d["vectors"][e][LAYER].float().numpy()) / np.linalg.norm(v)
                    for e in d["vectors"]])
    z = torch.load(STATS, weights_only=True)
    salienza = float(((V34 @ st - z["mu"].numpy()) / (z["sd"].numpy() + 1e-6)).max())

    hit = (Lux().confronta(st, via="semantica", k=1) or [None])[0]
    esito = {"ts": time.time(), "salienza": round(salienza, 2)}
    if hit is not None and hit["sim"] >= SOGLIA:
        esito.update(id=hit["id"], cos=hit["sim"], nodo=hit["nodo_id"])
    return esito


if __name__ == "__main__":
    if not APPUNTI.exists():
        print("nessun blocco appunti: niente da fare")
        sys.exit(0)
    aperte = righe_aperte(APPUNTI.read_text(encoding="utf-8"))
    sidecar = json.loads(SIDECAR.read_text()) if SIDECAR.exists() else {}
    sidecar = potatura(sidecar, aperte)
    nuovi = 0
    for r in da_agganciare(aperte, sidecar):
        sidecar[r] = aggancio_vero(r)
        nuovi += "id" in sidecar[r]
    tmp = SIDECAR.with_suffix(".tmp")
    tmp.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1))
    tmp.replace(SIDECAR)
    print(f"{nuovi} appunti agganciati ({len(aperte)} aperti)")
