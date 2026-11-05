# Firme dei ricordi rifatte su Occamy (ordine l'utente 29/09): firma v2 DIFFERENZIALE come tagging35b
# (st(ctx+msg) - st(ctx), primo messaggio st(msg) - mu), contesto dalla chat vera (chat-completa.jsonl,
# estratta in sola lettura da state.db di Hermes con estrai-chat-ro.py).
# Le firme di oggi sono ancora del tagger v1 (L34 grezzo, Qwen): tutti i 584 nodi sono anteriori al 28/07.
#
#   --leggi   GPU: letture per i nodi + un campione di messaggi non-nodo (statistiche di popolazione),
#             salvate in letture.pt con ripresa. Va lanciato DOPO swap-l29 (usa la mu di Occamy).
#   --scrivi  CPU: statistiche nuove (stats-emo-v2.pt), z, e riscrive IN PLACE firma/emo_tag/emo_alpha/salienza
#             in memoria.db, addr_emo in vettori.pt, firme dei neuroni in lux.npz (media dei loro nodi).
#             ID, archi, attivazioni, date di Lux intatti. Backup .bak-pre-firme-occamy-<ts> di tutto.
#   --dry     con --scrivi: solo il resoconto, nessuna scrittura.
# Uso: cd /data/jspace && OUT_35B=/data/jspace/out-occamy MODELLO_35B=Accio-Lab/occamy-1.0 \
#      venv/bin/python /data/memoria-episodica-affettiva/firme-occamy/ricalcola-firme.py --leggi
import argparse
import json
import os
import random
import shutil
import sqlite3
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import tagging35b as T  # noqa: E402  (stesse funzioni di lettura, stessa lente, stessi vettori emotivi)

QUI = "/data/memoria-episodica-affettiva/firme-occamy"
CHAT = f"{QUI}/chat-completa.jsonl"
LETTURE = f"{QUI}/letture-v3.pt"   # letture.pt = prima corsa col bug del troncamento
MEM = "/data/workspace/memoria"
DB = f"{MEM}/memoria.db"
VEC = f"{MEM}/vettori.pt"
LUX = f"{MEM}/lux.npz"
LUX_META = f"{MEM}/lux-meta.json"
N_CAMPIONE = 600          # messaggi non-nodo per le statistiche di popolazione
FINESTRA = 86400          # contesto = messaggi delle 24 h prima (la notturna leggeva la giornata)
log = T.log


def carica_chat():
    out = []
    for r in open(CHAT, encoding="utf-8"):
        m = json.loads(r)
        t = T.pulisci(m["testo"])
        if t and len(t.strip()) >= 15:
            out.append((float(m["ts"]), t.strip()))
    return sorted(out)


def contesto(chat, ts):
    prec = [t for (u, t) in chat if ts - FINESTRA <= u < ts - 0.5]
    return T.contesto_di(prec)


def voci():
    """nodi (tutti) + campione fisso di messaggi che non sono nodi"""
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    nodi = db.execute("SELECT id, ts, testo FROM nodi ORDER BY id").fetchall()
    db.close()
    chat = carica_chat()
    testi_nodi = {t for _, _, t in nodi}
    altri = [(u, t) for u, t in chat if t not in testi_nodi]
    random.Random(0).shuffle(altri)
    v = [("nodo", nid, ts, t) for nid, ts, t in nodi]
    v += [("campione", -1, u, t) for u, t in altri[:N_CAMPIONE]]
    return v, chat


def leggi():
    import mixed35b as M
    from jlens.lens import JacobianLens
    log.info("modello %s, lente %s, emovec %s, mu %s", M.MODEL_ID, T.LENTE_PT, T.EMOVEC18, T.MU_NPY)
    v, chat = voci()
    fatto = torch.load(LETTURE, weights_only=False) if os.path.exists(LETTURE) else {"modello": M.MODEL_ID, "R": {}}
    assert fatto["modello"] == M.MODEL_ID, f"letture.pt di un altro modello: {fatto['modello']}"
    mu = torch.tensor(np.load(T.MU_NPY), dtype=torch.float32)
    if not T._sano(mu, "mu di popolazione"):
        sys.exit(1)
    s = M.load()
    lente = JacobianLens.load(T.LENTE_PT)
    emos, V = T.direzioni_emotive()
    fatto["emos"] = emos
    t0, nuovi = time.time(), 0
    for k, (tipo, nid, ts, testo) in enumerate(v):
        chiave = f"{tipo}:{nid if tipo == 'nodo' else ts}"
        if chiave in fatto["R"]:
            continue
        ctx = contesto(chat, ts)
        if ctx:
            diff = T.leggi_differenziale(s, lente, ctx, testo)   # 30/09: fix troncamento
            if not T._sano(diff, "firma differenziale"):
                # 30/09: una lettura isolata e' esplosa (5e15) e ripetuta era normale: un secondo tentativo
                diff = T.leggi_differenziale(s, lente, ctx, testo)
                if not T._sano(diff, "firma differenziale (2o tentativo)"):
                    sys.exit(1)
                log.info("voce %s: 2o tentativo sano", chiave)
        else:
            st = T.leggi_stato(s, lente, testo)
            if not T._sano(st, "stato"):
                sys.exit(1)
            diff = st - mu
        fatto["R"][chiave] = (V @ diff).float()
        nuovi += 1
        if nuovi % 25 == 0:
            torch.save(fatto, LETTURE)
            log.info("letture %d/%d (%.1f s/voce)", k + 1, len(v), (time.time() - t0) / nuovi)
    torch.save(fatto, LETTURE)
    log.info("LETTURE-COMPLETE: %d voci (%d nuove)", len(fatto["R"]), nuovi)


def scrivi(dry):
    import mixed35b as M
    f = torch.load(LETTURE, weights_only=False)
    assert f["modello"] == M.MODEL_ID, f"letture di {f['modello']}, lancio con {M.MODEL_ID}"
    emos = f["emos"]
    v, _ = voci()
    mancano = [x for x in v if f"{x[0]}:{x[1] if x[0] == 'nodo' else x[2]}" not in f["R"]]
    assert not mancano, f"{len(mancano)} voci senza lettura: rilanciare --leggi"
    R = torch.stack(list(f["R"].values()))
    n = len(R)
    mean = R.mean(0)
    M2 = ((R - mean) ** 2).sum(0)
    sd = torch.sqrt(M2 / max(n - 1, 1))
    cvec = np.load("/data/memoria-episodica-affettiva/emo-cvec-v2.npz")   # B7: tagging35b non lo usa piu'
    nomi_cv = [str(x) for x in cvec["nomi"]]

    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    vecchi = {r[0]: r[1:] for r in db.execute("SELECT id, emo_tag, salienza, classe FROM nodi")}
    db.close()
    nuove = {}
    for tipo, nid, _, _ in v:
        if tipo != "nodo":
            continue
        z = (f["R"][f"nodo:{nid}"] - mean) / (sd + 1e-6)
        firma = {e: round(z[j].item(), 3) for j, e in enumerate(emos)}
        dom = max(firma, key=firma.get)
        nuove[nid] = (firma, dom, float(cvec["centro"][nomi_cv.index(dom)]), max(firma.values()))

    cambiati = sum(1 for nid, x in nuove.items() if x[1] != vecchi[nid][0])
    sal = np.array([x[3] for x in nuove.values()])
    log.info("RESOCONTO: %d nodi, popolazione %d (nodi + %d campione)", len(nuove), n, n - len(nuove))
    log.info("  emozione dominante cambiata: %d/%d", cambiati, len(nuove))
    log.info("  salienza nuova: p5 %.2f p50 %.2f p95 %.2f, sotto 1.8: %d (restano tutti)",
             *np.percentile(sal, [5, 50, 95]), int((sal < 1.8).sum()))
    conta = {}
    for x in nuove.values():
        conta[x[1]] = conta.get(x[1], 0) + 1
    log.info("  dominanti nuove: %s", sorted(conta.items(), key=lambda kv: -kv[1])[:12])
    if dry:
        return

    ts = time.strftime("%Y%m%d-%H%M")
    bak = f".bak-pre-firme-occamy-{ts}"
    src = sqlite3.connect(DB)
    dst = sqlite3.connect(DB + bak)
    src.backup(dst)
    dst.close()
    for p in (VEC, LUX, LUX_META, T.STATS):
        if os.path.exists(p):
            shutil.copy2(p, p + bak)
    log.info("backup %s fatti", bak)

    src.execute("PRAGMA busy_timeout=5000")
    with src:
        for nid, (firma, dom, alpha, salienza) in nuove.items():
            src.execute("UPDATE nodi SET firma=?, emo_tag=?, emo_alpha=?, salienza=? WHERE id=?",
                        (json.dumps(firma, ensure_ascii=False), dom, alpha, salienza, nid))
    src.close()

    vec = torch.load(VEC, weights_only=True)
    for nid, (firma, *_rest) in nuove.items():
        if nid in vec:
            vec[nid]["addr_emo"] = T.memoria.addr_emo(firma)   # B7: ordine di emozioni.json
    torch.save(vec, VEC)

    f51 = {nid: np.array([x[0][e] for e in sorted(x[0])], np.float32) for nid, x in nuove.items()}
    z = dict(np.load(LUX, allow_pickle=False))
    nodi_di = json.load(open(LUX_META)).get("nodi", {})
    firme = z["firme"].copy()
    senza = 0
    for i, uid in enumerate(z["ids"].tolist()):
        suoi = [f51[int(nd)] for nd in nodi_di.get(str(uid), [int(z["nodo_id"][i])]) if int(nd) in f51]
        if suoi:
            firme[i] = np.mean(suoi, axis=0)
        else:
            senza += 1
    z["firme"] = firme.astype(np.float32)
    np.savez_compressed(LUX, **z)

    torch.save({"n": n, "mean": mean, "M2": M2, "layer": T.LAYER, "lente": os.path.basename(T.LENTE_PT),
                "versione": 3, "modello": M.MODEL_ID}, T.STATS)
    log.info("FIRME-SCRITTE: memoria.db %d nodi, vettori.pt addr_emo, lux.npz %d neuroni (%d senza nodi: invariati), "
             "stats-emo-v2.pt n=%d", len(nuove), len(firme) - senza, senza, n)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--leggi", action="store_true")
    p.add_argument("--scrivi", action="store_true")
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    if a.leggi:
        leggi()
    if a.scrivi:
        scrivi(a.dry)
