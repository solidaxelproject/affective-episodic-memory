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
from pathlib import Path

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import ponte  # noqa: E402  (unica porta verso :8090, gradino zero 26/07)

APPUNTI = Path("/data/workspace/memoria/appunti.md")
SIDECAR = Path("/data/workspace/memoria/.appunti-agganci.json")
BASE_PT = "/data/memoria-episodica-affettiva/base-L34.pt"
EMOVEC = "/data/jspace/out-35b/emovec.pt"
STATS = "/data/memoria-episodica-affettiva/stats-popolazione.pt"
LAYER = ponte.LAYER_SONDA
SOGLIA = 0.56        # 28/07, spazio L29-lente: p99 del rumore (sonde-soglie.py,
                     # validata). Permissiva di proposito: ritenta ogni 24h.
                     # (la 0.36 era dello spazio L34 grezzo)
RITENTA_S = 24 * 3600   # un mancato aggancio si ritenta quando Lux è cresciuta

# il | iniziale è la notazione dell'agente per "aperto" (adottata il 19/07)
RIGA = re.compile(r"^\s*\|?\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")


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
    from lux import Lux

    grezzo = np.array(ponte.leggi_sonda(testo, lente=False)["mean"], np.float32)
    st = ponte.trasporta([grezzo])[0] - ponte.base_lente()   # spazio lente L29

    # 28/07: salienza z sulle statistiche NUOVE (stats-emo-v2, spazio lente,
    # Welford). Finche' la popolazione e' fredda (n<30) resta -1: meglio
    # dichiarare "non so" che inventare uno z su due campioni.
    salienza = -1.0
    try:
        stz = torch.load("/data/memoria-episodica-affettiva/stats-emo-v2.pt",
                         weights_only=True)
        if stz.get("n", 0) >= 30:
            d18 = torch.load("/data/jspace/out-35b/emovec-18.pt",
                             weights_only=True)
            V = torch.stack([d18["vectors"][e][LAYER] /
                             d18["vectors"][e][LAYER].norm()
                             for e in d18["vectors"]]).float()
            R = V @ torch.tensor(st, dtype=torch.float32)
            sd = torch.sqrt(stz["M2"] / max(stz["n"] - 1, 1))
            salienza = float(((R - stz["mean"]) / (sd + 1e-6)).max())
    except (OSError, KeyError, RuntimeError):
        pass

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
