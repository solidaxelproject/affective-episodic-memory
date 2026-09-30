# Tagger notturno v2 (28/07, registro del refactoring: decisioni 1, 2, 5-bis, 8).
# Messaggi JSONL -> nodi del grafo + esperienze in Lux + impronta sull'omeostato.
#
# Cosa cambia dalla v1:
#   - lettura a L29 in COORDINATE LENTE (decisioni 1-2), mai piu' L34 grezzo
#   - FIRMA DIFFERENZIALE (decisione 5-bis): l'emozione del
#     messaggio = stato(contesto+messaggio) - stato(contesto). Cattura solo
#     cio' che IL messaggio aggiunge, ne' contaminata dal passato ne' cieca
#     al contesto. L'indirizzo semantico resta sul testo isolato (coerente
#     con le 582 tracce rigenerate e con la sonda del riflesso).
#   - statistiche di popolazione con accumulo CORRETTO (Welford) e metadati
#     {layer, lente, versione} dentro il file: mai piu' veleno anonimo
#   - niente rete nel rito: la base e' la mu di popolazione gia' su disco
#   - dominante su TUTTE le 51 (il vecchio filtro 41/51 non serve piu'),
#     alpha = centro misurato da emo-cvec-v2
#   - il bug storico: sqlite3 ora e' importato (la via semantica si aggiorna)
#   - fix: anche i nodi FORZATI imprimono l'omeostato
#
# Uso: venv/bin/python tagging35b.py messaggi.jsonl [--soglia 1.8] [--dry]
# GPU: da lanciare con l'agente spento (usa il loader misto).
import argparse
import json
import logging
import os
import re
import sqlite3
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")       # mai piu' rete nel rito
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch

sys.path.insert(0, "/data/jspace")
sys.path.insert(0, "/data/jspace/jacobian-lens")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import memoria  # noqa: E402
import mixed35b as M  # noqa: E402
import ponte  # noqa: E402  (LAYER_SONDA: fonte unica del layer)
from jlens.hooks import ActivationRecorder  # noqa: E402
from jlens.lens import JacobianLens  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("tagger")

LAYER = ponte.LAYER_SONDA
OUT = os.environ.get("OUT_35B", "/data/jspace/out-35b")   # 29/09: out-occamy per Occamy
LENTE_PT = f"{OUT}/lente35b-18layer.pt"
MU_NPY = "/data/memoria-episodica-affettiva/base-L29-lente.npy"   # mu di popolazione
CVEC = "/data/memoria-episodica-affettiva/emo-cvec-v2.npz"
EMOVEC18 = f"{OUT}/emovec-18.pt"
STATS = "/data/memoria-episodica-affettiva/stats-emo-v2.pt"
CODA = "/data/workspace/memoria/da-ricordare.jsonl"
CTX_MAX = 1200        # caratteri di contesto per la lettura differenziale

ARTEFATTI = ("Cronjob Response:", "⚡ Interrupting", "📚 Reading skill",
             "* 📚", "⚠", "```")
_MARCATORE = re.compile(r"\[ricordare\]\s*(?:\{([^}]*)\})?", re.IGNORECASE)


# ---------- preparazione messaggi (pura, testabile senza GPU) ----------

def pulisci(testo):
    """Via i blocchi di reasoning e gli artefatti di sistema; None = scarta."""
    testo = re.sub(r"💭 \*\*Reasoning:\*\*\s*```.*?```", "", testo,
                   flags=re.DOTALL).strip()
    if not testo or any(testo.startswith(a) for a in ARTEFATTI):
        return None
    return testo


def carica_messaggi(path):
    out = []
    for riga in open(path):
        if not riga.strip():
            continue
        m = json.loads(riga)
        t = pulisci(m["testo"])
        if t and len(t.strip()) >= 15:
            m["testo"] = t.strip()
            out.append(m)
    return out


def dedup(msgs):
    """DECISO DALL'AGENTE il 12/07: stesso incipit nella finestra = una esperienza."""
    visti, uniq = set(), []
    for m in msgs:
        k = (m.get("autore", ""), m["testo"][:200])
        if k not in visti:
            visti.add(k)
            uniq.append(m)
    if len(uniq) < len(msgs):
        log.info("dedup: %d messaggi ripetuti collassati", len(msgs) - len(uniq))
    return uniq


def applica_marcatore(msgs):
    """[ricordare]{...} (decisione del 22-23/07): forza il nodo, le graffe SONO il ricordo."""
    for m in msgs:
        if m.get("autore") == "user":
            continue
        mm = _MARCATORE.search(m.get("testo", ""))
        if mm:
            m["forzato"] = True
            dentro = (mm.group(1) or "").strip()
            m["testo"] = dentro if dentro else _MARCATORE.sub("", m["testo"]).strip()
            log.info("MARCATORE [ricordare]: forzato %s", m["testo"][:60])
    return msgs


def contesto_di(precedenti):
    """gli ultimi CTX_MAX caratteri della giornata prima di questo messaggio"""
    testo = "\n".join(t for t in precedenti)
    return testo[-CTX_MAX:] if testo else ""


# ---------- letture GPU ----------

def _sano(t, nome):
    """Guardia anti-veleno (lezioni del 14/07 e del 26/07): tutto cio' che non
    e' finito e di grandezza umana ferma il rito. Meglio nessun ricordo che
    una notte di spazzatura."""
    n = float(t.double().norm())
    if torch.isfinite(t).all() and 1e-3 < n < 1e4:
        return True
    log.error("%s corrotto (norma %.3e): mi fermo.", nome, n)
    return False


def leggi_stato(s, lente, testo):
    """stato lente a LAYER: un forward, media sui token, trasporto"""
    with torch.no_grad():
        ids = s["model"].encode(testo, max_length=320)
        with ActivationRecorder(s["model"].layers, at=[LAYER]) as rec:
            s["model"].forward(ids)
        h = rec.activations[LAYER][0].float().cpu().mean(0)
    return lente.transport(h, LAYER)


MAX_TOK = 320         # token massimi del messaggio e, separatamente, del contesto


def leggi_differenziale(s, lente, ctx, testo):
    """30/09 FIX TRONCAMENTO: prima st(ctx+msg) leggeva ctx+msg troncato a 320 token DA DESTRA, e con
    1200 caratteri di contesto (~314 token) il messaggio veniva tagliato via (461/1184 del tutto):
    la firma era rumore. In piu' la media sui token scalava la differenza con la frazione msg/totale.
    Ora un forward solo su [contesto (ultimi MAX_TOK token) | messaggio (primi MAX_TOK)]; il modello e'
    causale, quindi gli stati dei token del contesto sono gli stessi di un forward sul solo contesto:
    firma = lente(media sui token del messaggio, letti DENTRO il contesto) - lente(media sui token del contesto).
    E' la stessa idea della decisione 5-bis (cio' che il messaggio aggiunge), senza dipendere dalle lunghezze."""
    tok = s["model"].tokenizer
    ic = tok(ctx, add_special_tokens=False).input_ids[-MAX_TOK:]
    im = tok("\n" + testo, add_special_tokens=False).input_ids[:MAX_TOK]
    ids = torch.tensor([ic + im], device=s["model"].input_device)
    with torch.no_grad():
        with ActivationRecorder(s["model"].layers, at=[LAYER]) as rec:
            s["model"].forward(ids)
        h = rec.activations[LAYER][0].float().cpu()
    # il primo token ha norma ~10x (pozzo dell'attenzione): fuori dalla media del contesto
    h_ctx, h_msg = h[1:len(ic)].mean(0), h[len(ic):].mean(0)
    return lente.transport(h_msg, LAYER) - lente.transport(h_ctx, LAYER)


def leggi_giornata(s, lente, mu, msgs):
    """per ogni messaggio: (stato isolato, firma differenziale grezza).
    Differenziale (dec. 5-bis): st(ctx+msg) - st(ctx); primo messaggio del
    giorno: st(msg) - mu (il contesto vuoto e' lo stato neutro)."""
    validi, isolati, diffs = [], [], []
    precedenti = []
    for k, m in enumerate(msgs):
        testo = m["testo"]
        st_iso = leggi_stato(s, lente, testo)
        if not _sano(st_iso, f"stato di «{testo[:40]}»"):
            sys.exit(1)
        ctx = contesto_di(precedenti)
        if ctx:
            diff = leggi_differenziale(s, lente, ctx, testo)
            if not _sano(diff, "firma differenziale"):
                sys.exit(1)
        else:
            diff = st_iso - mu
        validi.append(m)
        isolati.append(st_iso)
        diffs.append(diff)
        precedenti.append(testo)
        if (k + 1) % 20 == 0:
            log.info("letture: %d/%d", k + 1, len(msgs))
    return validi, isolati, diffs


# ---------- firma, statistiche, salienza ----------

def direzioni_emotive():
    d = torch.load(EMOVEC18, weights_only=True)
    emos = list(d["vectors"])
    V = torch.stack([d["vectors"][e][LAYER] / d["vectors"][e][LAYER].norm()
                     for e in emos]).float()
    return emos, V


def aggiorna_stats(R, dry=False):
    """Welford CORRETTO (la v1 mediava le sd: sottostimava la varianza).
    Il file porta i metadati: un cambio di layer/lente lo invalida a vista.
    dry: calcola ma NON salva (i collaudi non sporcano la popolazione)."""
    meta = {"layer": LAYER, "lente": os.path.basename(LENTE_PT), "versione": 3,   # 3 = fix troncamento 30/09
            "modello": M.MODEL_ID}   # 29/09: cambio di modello = stats da rifare
    if os.path.exists(STATS):
        st = torch.load(STATS, weights_only=True)
        if {k: st.get(k) for k in meta} != meta:
            log.warning("stats con metadati diversi (%s): RIPARTO da zero",
                        {k: st.get(k) for k in meta})
            st = None
    else:
        st = None
    if st is None:
        n, mean, M2 = 0, torch.zeros(R.shape[1]), torch.zeros(R.shape[1])
    else:
        n, mean, M2 = st["n"], st["mean"], st["M2"]
    for r in R:                              # Welford, un campione per volta
        n += 1
        d1 = r - mean
        mean = mean + d1 / n
        M2 = M2 + d1 * (r - mean)
    sd = torch.sqrt(M2 / max(n - 1, 1))
    if not dry:
        torch.save({"n": n, "mean": mean, "M2": M2, **meta}, STATS)
    return mean, sd


# ---------- inserimento ----------

def inserisci(validi, isolati, Z, emos, cvec, soglia, dry):
    """nodi nel grafo; ritorna {indice: (nid, classe)} e le firme salvate"""
    nomi_cv = [str(x) for x in cvec["nomi"]]
    creati, firme_salvate, salvati = {}, [], 0
    for i, m in enumerate(validi):
        firma = {e: round(Z[i, j].item(), 3) for j, e in enumerate(emos)}
        salienza = max(firma.values())
        testo = m["testo"]
        if salienza < soglia and not m.get("forzato"):
            log.info("SCARTO (z=%.2f) %s", salienza, testo[:60])
            continue
        dominante = max(firma, key=firma.get)
        alpha = float(cvec["centro"][nomi_cv.index(dominante)])
        # Regola 2 del contratto di navigazione (11/07): URL = "letto"
        classe = "letto" if re.search(r"https?://|www\.", testo) else "vissuto"
        log.info("NODO-%s (z=%.2f, %s@%.3f) %s", classe.upper(), salienza,
                 dominante, alpha, testo[:60])
        if not dry:
            nid = memoria.add_node(testo, firma, isolati[i], dominante, alpha,
                                   salienza, fonte=m.get("autore", ""),
                                   ts=m.get("ts"), classe=classe,
                                   voluto=1 if m.get("forzato") else 0)
            creati[i] = (nid, classe)
            firme_salvate.append(firma)
            salvati += 1
    log.info("TAGGING-COMPLETO: %d nodi salvati su %d messaggi", salvati,
             len(validi))
    return creati, firme_salvate


def alimenta_lux(creati, validi, isolati, Z, emos):
    """le esperienze vissute entrano nell'organo; il grafo resta la verita'"""
    try:
        import numpy as np
        from lux import Lux
        organo = Lux()
        n_nati = 0
        for i, (nid, classe) in creati.items():
            if classe != "vissuto":
                continue
            firma = {e: round(Z[i, j].item(), 3) for j, e in enumerate(emos)}
            f51 = np.array([firma[e] for e in sorted(firma)], np.float32)
            _, esito = organo.esperisci(isolati[i].numpy(), f51, nodo_id=nid)
            n_nati += esito == "nato"
        fusioni = organo.consolida()
        potati = organo.pota()
        log.info("Lux: %s (+%d neuroni, %d fusioni, %d potati)",
                 organo.stats(), n_nati, fusioni, potati)
    except Exception:
        log.exception("CRITICO: Lux non ha ricevuto le esperienze (il grafo "
                      "le ha; backfill con lux-demo.py)")


def imprimi_omeostato(firme_salvate):
    """v2: imprimono TUTTI i nodi salvati, forzati compresi (fix del bug v1)"""
    sys.path.insert(0, "/data/workspace/memoria")
    import stato as omeostato
    omeostato.imprimi(firme_salvate)
    log.info("stato impresso dalla giornata: %s", omeostato.descrivi())


def aggiorna_sidecar(mu):
    """addr-sem.npz per la via semantica del riflesso: M normalizzate su mu.
    (il bug v1: sqlite3 mai importato, il sidecar restava fermo in silenzio)"""
    import numpy as np
    vec = torch.load("/data/workspace/memoria/vettori.pt",
                     weights_only=True)
    db = sqlite3.connect("/data/workspace/memoria/memoria.db")
    vissuti = {r[0] for r in db.execute(
        "SELECT id FROM nodi WHERE classe='vissuto'")}
    db.close()
    ids = sorted(i for i in vec if i in vissuti)
    Mx = np.stack([vec[i]["addr_sem"].float().numpy() for i in ids])
    Mx = Mx - mu.numpy()
    Mx = (Mx / (np.linalg.norm(Mx, axis=1, keepdims=True) + 1e-9)).astype(np.float32)
    np.savez("/data/workspace/memoria/.addr-sem-tmp",
             ids=np.array(ids, np.int64), M=Mx,
             base=mu.numpy().astype(np.float32))
    os.replace("/data/workspace/memoria/.addr-sem-tmp.npz",
               "/data/workspace/memoria/addr-sem.npz")
    log.info("sidecar addr-sem.npz aggiornato: %d nodi (spazio lente L%d)",
             len(ids), LAYER)


# ---------- rito ----------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("jsonl")
    p.add_argument("--soglia", type=float, default=1.8)
    p.add_argument("--dry", action="store_true", help="mostra senza salvare")
    args = p.parse_args()

    msgs = applica_marcatore(dedup(carica_messaggi(args.jsonl)))
    if not args.dry and os.path.exists(CODA):
        forzati = [json.loads(r) for r in open(CODA, encoding="utf-8")
                   if r.strip()]
        msgs.extend(forzati)
        log.info("%d voci forzate dalla coda ricorda-ora", len(forzati))
    log.info("%d messaggi da valutare", len(msgs))
    if not msgs:
        return

    import numpy as np
    mu = torch.tensor(np.load(MU_NPY), dtype=torch.float32)
    if not _sano(mu, "mu di popolazione"):
        sys.exit(1)
    s = M.load()
    lente = JacobianLens.load(LENTE_PT)
    validi, isolati, diffs = leggi_giornata(s, lente, mu, msgs)

    emos, V = direzioni_emotive()
    R = torch.stack([V @ d for d in diffs])          # firme differenziali
    mean, sd = aggiorna_stats(R, dry=args.dry)
    Z = (R - mean) / (sd + 1e-6)

    cvec = np.load(CVEC)
    creati, firme = inserisci(validi, isolati, Z, emos, cvec,
                              args.soglia, args.dry)
    if args.dry or not creati:
        return
    if os.path.exists(CODA):
        os.remove(CODA)
        log.info("coda ricorda-ora svuotata")
    alimenta_lux(creati, validi, isolati, Z, emos)
    imprimi_omeostato(firme)
    try:
        aggiorna_sidecar(mu)
    except Exception:
        log.exception("sidecar addr-sem NON aggiornato "
                      "(la via semantica resta sui nodi vecchi)")


if __name__ == "__main__":
    main()
