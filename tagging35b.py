# Tagger notturno: messaggi JSONL -> nodi del grafo memoria.
# Per ogni messaggio: stato a L34 -> firma 51-dim -> salienza (z-max).
# Sopra soglia: nodo con indirizzo semantico, tag emozione dominante, alpha.
# Uso: venv/bin/python tagging35b.py messaggi.jsonl [--soglia 1.8] [--dry]
# GPU: da lanciare con l'agente spento (usa il loader misto).
import argparse
import json
import logging
import os
import sys

import torch

sys.path.insert(0, "/data/jspace")
import mixed35b as M  # noqa: E402

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import memoria  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("tagger")

READ_L = 34

p = argparse.ArgumentParser()
p.add_argument("jsonl")
p.add_argument("--soglia", type=float, default=1.8)
p.add_argument("--dry", action="store_true", help="mostra senza salvare")
args = p.parse_args()

import re

ARTEFATTI = ("Cronjob Response:", "⚡ Interrupting", "📚 Reading skill",
             "* 📚", "⚠", "```")


def pulisci(testo):
    """Via i blocchi di reasoning e gli artefatti di sistema; None = scarta."""
    testo = re.sub(r"💭 \*\*Reasoning:\*\*\s*```.*?```", "", testo,
                   flags=re.DOTALL).strip()
    if not testo or any(testo.startswith(a) for a in ARTEFATTI):
        return None
    return testo


msgs = []
for l in open(args.jsonl):
    if not l.strip():
        continue
    m = json.loads(l)
    t = pulisci(m["testo"])
    if t:
        m["testo"] = t
        msgs.append(m)

# dedup (scelta del 12/07, dopo il loop consolidato 5 volte): messaggi
# con lo stesso incipit nella finestra = una sola esperienza (spam/loop/retry).
visti, uniq = set(), []
for m in msgs:
    k = (m.get("autore", ""), m["testo"][:200])
    if k in visti:
        continue
    visti.add(k)
    uniq.append(m)
if len(uniq) < len(msgs):
    log.info("dedup: %d messaggi ripetuti collassati", len(msgs) - len(uniq))
msgs = uniq

# coda "ricorda-ora": voci FORZATE (bypassano la soglia di salienza)
CODA = "/data/workspace/memoria/da-ricordare.jsonl"
if not args.dry and os.path.exists(CODA):
    forzati = [json.loads(l) for l in open(CODA, encoding="utf-8") if l.strip()]
    msgs.extend(forzati)
    log.info("%d voci forzate dalla coda ricorda-ora", len(forzati))

log.info("%d messaggi da valutare (dopo il filtro artefatti)", len(msgs))

s = M.load()
calib = json.load(open(f"{M.OUT}/alpha-calib-L26-28.json"))
ok_emos = {e for e in s["emos"] if calib.get(e, {}).get("reached_target")}
from jlens.hooks import ActivationRecorder  # noqa: E402

# BASE è una COSTANTE (media L34 su 6 prompt wikitext fissi): si calcola una
# volta e si cachea. Il 14/07 alle 00:00 il CDN di HF ha risposto 403 e il
# tagging è morto per un download che non serviva: mai più rete nel rito.
BASE_CACHE = "/data/memoria-episodica-affettiva/base-L34.pt"


def _sano(t, nome):
    """14/07: la GPU corrotta ha prodotto stati a norma ~1e35 che hanno
    avvelenato grafo, Lux, statistiche e omeostato in un colpo solo.
    Norme sane osservate: 3-7. Tutto ciò che non è finito e umano si ferma."""
    n = float(t.double().norm())
    if torch.isfinite(t).all() and 0.1 < n < 1e3:
        return True
    log.error("%s corrotto (norma %.3e): GPU sporca? Mi fermo.", nome, n)
    return False


BASE = None
if os.path.exists(BASE_CACHE):
    BASE = torch.load(BASE_CACHE, weights_only=True)
    if not _sano(BASE, "base-L34.pt (cache)"):
        os.remove(BASE_CACHE)
        BASE = None
if BASE is None:
    from jlens.examples import load_wikitext_prompts  # noqa: E402
    _bases = []
    for pr in load_wikitext_prompts(6):
        with torch.no_grad():
            ids = s["model"].encode(pr, max_length=96)
            with ActivationRecorder(s["model"].layers, at=[READ_L]) as rec:
                s["model"].forward(ids)
            _bases.append(rec.activations[READ_L][0].float().cpu().mean(0))
    BASE = torch.stack(_bases).mean(0)
    if not _sano(BASE, "base-L34 appena calcolata"):
        sys.exit(1)
    torch.save(BASE, BASE_CACHE)
V34 = s["V"][list(s["BAND"]).index(READ_L)]

# PASSATA 1: firme grezze di tutto il corpus (la z entro-messaggio non
# discrimina: il max di 51 valori normalizzati è sempre ~2; serve la z
# TRA messaggi, come nella validazione).
validi, raws, states = [], [], []
for m in msgs:
    testo = m["testo"].strip()
    if len(testo) < 15:
        continue
    with torch.no_grad():
        ids = s["model"].encode(testo, max_length=160)
        with ActivationRecorder(s["model"].layers, at=[READ_L]) as rec:
            s["model"].forward(ids)
        st = rec.activations[READ_L][0].float().cpu().mean(0) - BASE
    if not _sano(st, f"stato L34 di «{testo[:40]}»"):
        sys.exit(1)  # meglio nessun ricordo stanotte che una notte di garbage
    validi.append(m)
    states.append(st)
    raws.append(V34 @ st)
R = torch.stack(raws)  # [n_msg, 51]

# statistiche di popolazione: nuove o accumulate da run precedenti
import os
STATS = "/data/memoria-episodica-affettiva/stats-popolazione.pt"
if os.path.exists(STATS):
    old = torch.load(STATS, weights_only=True)
    mu = (old["mu"] * old["n"] + R.mean(0) * len(R)) / (old["n"] + len(R))
    sd = (old["sd"] * old["n"] + R.std(0) * len(R)) / (old["n"] + len(R))
    n_tot = old["n"] + len(R)
else:
    mu, sd, n_tot = R.mean(0), R.std(0), len(R)
torch.save({"mu": mu, "sd": sd, "n": n_tot}, STATS)
Z = (R - mu) / (sd + 1e-6)  # z tra messaggi, per emozione

# PASSATA 2: filtro e inserimento
salvati = 0
nodi_creati = {}  # indice messaggio -> (id nodo grafo, classe)
for i, m in enumerate(validi):
    firma = {e: round(Z[i, j].item(), 3) for j, e in enumerate(s["emos"])}
    salienza = max(firma.values())
    testo = m["testo"].strip()
    if salienza < args.soglia and not m.get("forzato"):
        log.info("SCARTO (z=%.2f) %s", salienza, testo[:60])
        continue
    dominante = max((e for e in firma if e in ok_emos), key=firma.get)
    alpha = calib[dominante]["alpha"]
    # Regola 2 del contratto di navigazione dell'agente (11/07): contenuto con URL
    # o citazioni web = "letto", non "vissuto": entra nel grafo solo come
    # testo consultabile, MAI nei richiami emotivi/congruenti.
    classe = "letto" if re.search(r"https?://|www\.", testo) else "vissuto"
    log.info("NODO-%s (z=%.2f, %s@%.2f) %s", classe.upper(), salienza,
             dominante, alpha, testo[:60])
    if not args.dry:
        nid = memoria.add_node(testo, firma, states[i], dominante, alpha,
                               salienza, fonte=m.get("autore", ""),
                               ts=m.get("ts"), classe=classe)
        nodi_creati[i] = (nid, classe)
        salvati += 1

# la coda ricorda-ora è stata consumata: svuotala (i suoi item sono ora ricordi)
if not args.dry and os.path.exists(CODA):
    os.remove(CODA)
    log.info("coda ricorda-ora svuotata")

log.info("TAGGING-COMPLETO: %d nodi salvati su %d messaggi", salvati, len(validi))

# le esperienze nuove entrano in Lux (l'organo di memoria crescente).
# Se Lux fallisce, il grafo resta fonte di verità: niente amnesia, si
# ri-alimenta con lux-demo.py (backfill). Ma il fallimento urla nel log.
if salvati and not args.dry:
    try:
        import numpy as _np
        from lux import Lux
        lux = Lux()
        if lux.pca_mu is None:  # primo avvio in assoluto: fitta l'encoder
            lux.fit_encoder(_np.stack([st.numpy() for st in states]))
        n_nati = 0
        for i, (nid, classe) in nodi_creati.items():
            if classe != "vissuto":  # regola 2: il "letto" non entra in Lux
                continue
            firma = {e: round(Z[i, j].item(), 3) for j, e in enumerate(s["emos"])}
            f51 = _np.array([firma[e] for e in sorted(firma)], _np.float32)
            _, esito = lux.esperisci(states[i].numpy(), f51, nodo_id=nid)
            n_nati += esito == "nato"
        # sonno profondo: episodi ripetuti -> schemi; disuso -> oblio
        fusioni = lux.consolida()
        potati = lux.pota()
        log.info("Lux: %s (+%d neuroni, %d fusioni, %d potati)",
                 lux.stats(), n_nati, fusioni, potati)
    except Exception:
        log.exception("CRITICO: Lux non ha ricevuto le esperienze di stanotte "
                      "(il grafo le ha; backfill con lux-demo.py)")

# la giornata imprime lo stato emotivo (consolidamento notturno)
if salvati and not args.dry:
    sys.path.insert(0, "/data/workspace/memoria")
    import stato as omeostato
    firme_giorno = [
        {e: round(Z[i, j].item(), 3) for j, e in enumerate(s["emos"])}
        for i in range(len(validi))
        if max(Z[i]).item() >= args.soglia
    ]
    omeostato.imprimi(firme_giorno)
    log.info("stato impresso dalla giornata: %s", omeostato.descrivi())
