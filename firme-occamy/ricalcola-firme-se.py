# B3 di PIANO-FIRMA-ENGRAMMI.md (l'utente 31/10-01/11): rifirma di tutti i ricordi coi vettori se' sui 24 assi della
# ruota (firma_se.firma_server, lettura dal server col GGUF dell'agente), statistiche di popolazione nuove e soglia nuova
# con la STESSA QUOTA di messaggi che passava con la firma vecchia (D5). Schema di ricalcola-firme.py (29-30/09).
# Contesto dalla chat vera, rietratta il 01/11 (chat-completa-0111.jsonl, estrai-chat-ro.py: la vecchia finiva al 26/07).
#
#   --leggi   server di prova 8098 (GPU libera): per ogni voce (tutti i nodi + tutti gli altri messaggi della chat) la
#             firma a 24 assi; il messaggio da solo per mu (media di popolazione per strato, serve ai messaggi senza
#             contesto). Salvate in letture-se.pt con ripresa.
#   --scrivi  CPU: z sulla popolazione, soglia, riscrive firma/emo_tag/salienza in memoria.db e addr_emo in vettori.pt
#             (emo_alpha non si calcola piu', P2); stats-firma-se.pt coi metadati. Backup .bak-pre-firme-se-<ts>.
#   --dry     con --scrivi: solo il resoconto.
# 09/11 (PIANO-FIRMA-44-ASSI.md, l'utente): --leggi salva le DIFFERENZE per strato (letture-diff.pt, float32), non la
#   proiezione: --scrivi proietta coi vettori di VETTORI_FIRMA (default vettori-lettura-firma.pt, 44 assi, variante C)
#   e li scrive nelle statistiche ("vettori"); dominante con memoria.dominante; db e vettori.pt sotto il lucchetto.
# Uso: cd /data/jspace && venv/bin/python /data/memoria-episodica-affettiva/firme-occamy/ricalcola-firme-se.py --leggi
import argparse
import fcntl
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva")
sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
import firma_se as F  # noqa: E402
import tagging35b as T  # noqa: E402  (pulisci, contesto_di: gli stessi del tagging)

QUI = "/data/memoria-episodica-affettiva/firme-occamy"
CHAT = f"{QUI}/chat-completa-0111.jsonl"
LETTURE = os.environ.get("LETTURE_SE", f"{QUI}/letture-diff.pt")   # LETTURE_SE, STATS_SE: copie per i test
VETTORI = os.environ.get("VETTORI_FIRMA", "/data/jspace/out-occamy/vettori-lettura-firma.pt")
VECCHIE = f"{QUI}/letture-v3.pt"          # firma vecchia (51 assi) dei 600 messaggi non nodo di settembre
STATS_VECCHIE = "/data/memoria-episodica-affettiva/stats-emo-v2.pt"
STATS = os.environ.get("STATS_SE", "/data/memoria-episodica-affettiva/stats-firma-se.pt")
MEM = os.environ.get("MEM_SAM", "/data/workspace/memoria")   # MEM_SAM: copia per i test
DB = f"{MEM}/memoria.db"
VEC = f"{MEM}/vettori.pt"
URL = os.environ.get("URL_FIRMA", "http://127.0.0.1:8098")
FINESTRA = 86400          # contesto = messaggi delle 24 h prima, come il 29/09
SOGLIA_VECCHIA = 1.8
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
    return T.contesto_di([t for (u, t) in chat if ts - FINESTRA <= u < ts - 0.5])


def voci():
    """tutti i nodi + tutti i messaggi della chat che non sono nodi (il campione della quota)"""
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    nodi = db.execute("SELECT id, ts, testo FROM nodi ORDER BY id").fetchall()
    db.close()
    chat = carica_chat()
    testi_nodi = {t.strip() for _, _, t in nodi}
    v = [("nodo", nid, ts, t) for nid, ts, t in nodi]
    v += [("campione", -1, u, t) for u, t in chat if t not in testi_nodi]
    return v, chat


def chiave(tipo, nid, ts):
    return f"{tipo}:{nid if tipo == 'nodo' else ts}"


def modello_server():
    with urllib.request.urlopen(URL + "/props", timeout=10) as f:
        return json.load(f)["model_path"]


def salva(fatto):
    torch.save(fatto, LETTURE + ".tmp")
    os.replace(LETTURE + ".tmp", LETTURE)   # mai un file a meta': la ripresa trova sempre letture intere


def leggi():
    v, chat = voci()
    mod = modello_server()
    if os.path.exists(LETTURE):
        fatto = torch.load(LETTURE, weights_only=False)
        assert fatto["modello"] == mod and fatto["strati"] == F.STRATI and "D" in fatto, \
            f"{LETTURE}: di un altro lettore o di prima delle differenze"
    else:
        fatto = {"modello": mod, "strati": F.STRATI, "D": {}, "soli": {},
                 "mu_somma": np.zeros((len(F.STRATI), 2048)), "mu_n": 0}
    log.info("lettore %s (%s), %d voci (%d nodi), gia' lette %d", URL, mod, len(v),
             sum(1 for x in v if x[0] == "nodo"), len(fatto["D"]) + len(fatto["soli"]))
    t0, nuovi = time.time(), 0
    for k, (tipo, nid, ts, testo) in enumerate(v):
        c = chiave(tipo, nid, ts)
        if c in fatto["D"] or c in fatto["soli"]:
            continue
        msg = F._taglia(URL, testo, F.MSG_TOK, coda=False)
        s, n = F._somme(URL, msg, None)
        solo = np.stack([s[l] / n for l in F.STRATI])
        if not np.isfinite(solo).all():
            raise ValueError(f"voce {c}: lettura del messaggio da solo non finita")
        ctx = contesto(chat, ts)
        if ctx:
            dd = F.diff_server(ctx, testo, URL)   # una volta per voce (revisione 09/11)
            d = np.stack([dd[l] for l in F.STRATI]).astype(np.float32)
            if not np.isfinite(d).all() or (np.linalg.norm(d, axis=-1) < 1e-6).any():
                raise ValueError(f"voce {c}: differenza non finita o nulla")
            fatto["D"][c] = d
        else:
            fatto["soli"][c] = solo.astype(np.float32)   # la firma la fa --scrivi, quando mu e' completa
        fatto["mu_somma"] += solo
        fatto["mu_n"] += 1
        nuovi += 1
        if nuovi % 100 == 0:
            salva(fatto)
            log.info("letture %d/%d (%.1f s/voce)", k + 1, len(v), (time.time() - t0) / nuovi)
    salva(fatto)
    log.info("LETTURE-COMPLETE: %d voci (%d nuove; %d senza contesto)", len(fatto["D"]) + len(fatto["soli"]), nuovi,
             len(fatto["soli"]))


def quota_vecchia():
    """quota dei 600 messaggi non nodo di settembre con salienza vecchia (max z sui 51 assi) >= 1.8"""
    f = torch.load(VECCHIE, weights_only=False)
    s = torch.load(STATS_VECCHIE, weights_only=False)
    R = torch.stack([x for c, x in f["R"].items() if c.startswith("campione:")]).double()
    sd = torch.sqrt(s["M2"].double() / max(s["n"] - 1, 1))
    z = (R - s["mean"].double()) / (sd + 1e-6)
    return float((z.max(1).values >= SOGLIA_VECCHIA).double().mean()), len(R)


def calcola():
    """-> (nuove {nid: (firma, dominante, salienza)}, statistiche, resoconto). Puro: stesse letture, stessi numeri."""
    f = torch.load(LETTURE, weights_only=False)
    F.usa(VETTORI)
    assi, _ = F.vettori()
    v, _ = voci()
    mancano = [x for x in v if chiave(*x[:3]) not in f["D"] and chiave(*x[:3]) not in f["soli"]]
    assert not mancano, f"{len(mancano)} voci senza lettura: rilanciare --leggi"
    mu = f["mu_somma"] / f["mu_n"]
    R = {c: F.proietta({l: d[i].astype(np.float64) for i, l in enumerate(F.STRATI)}) for c, d in f["D"].items()}
    for c, solo in f["soli"].items():
        R[c] = F.proietta({l: solo[i].astype(np.float64) - mu[i] for i, l in enumerate(F.STRATI)})
    chiavi = [chiave(*x[:3]) for x in v]
    X = np.stack([R[c] for c in chiavi])
    mean = X.mean(0)
    M2 = ((X - mean) ** 2).sum(0)
    sd = np.sqrt(M2 / max(len(X) - 1, 1))
    Z = (X - mean) / (sd + 1e-6)
    sal = Z.max(1)
    campione = np.array([x[0] == "campione" for x in v])
    quota, n_vecchio = quota_vecchia()
    soglia = float(np.quantile(sal[campione], 1 - quota))
    nuove = {}
    for (tipo, nid, _, _), z, s in zip(v, Z, sal):
        if tipo == "nodo":
            firma = {a: round(float(z[j]), 3) for j, a in enumerate(assi)}
            nuove[nid] = (firma, T.memoria.dominante(firma), float(s))   # 09/11: come firma_subito
    stats = {"versione": 2, "assi": assi, "strati": F.STRATI, "vettori": VETTORI,
             "fonti": torch.load(VETTORI, weights_only=False)["fonte"],
             "lettore": f["modello"], "n": len(X), "mean": torch.tensor(mean), "M2": torch.tensor(M2),
             "mu": {l: torch.tensor(mu[i]) for i, l in enumerate(F.STRATI)}, "soglia": soglia,
             "quota": quota, "soglia_vecchia": SOGLIA_VECCHIA, "chat": os.path.basename(CHAT)}
    res = {"n": len(X), "n_campione": int(campione.sum()), "senza_contesto": len(f["soli"]), "quota": quota,
           "n_vecchio": n_vecchio, "soglia": soglia, "quota_nuova": float((sal[campione] >= soglia).mean()),
           "nodi_sotto": int(sum(1 for x in nuove.values() if x[2] < soglia)),
           "quota_forte": float((sal[campione] >= soglia + 1.0).mean()),   # FORTE_DELTA di firma_subito
           "sal_su_soglia": np.percentile(sal[campione] / soglia, [50, 90, 99]).tolist()}
    return nuove, stats, res


def scrivi(dry):
    nuove, stats, res = calcola()
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    vecchi = dict(db.execute("SELECT id, emo_tag FROM nodi"))
    db.close()
    log.info("RESOCONTO: %d nodi, popolazione %d (%d non nodo, %d senza contesto)", len(nuove), res["n"],
             res["n_campione"], res["senza_contesto"])
    log.info("  quota vecchia %.4f (salienza >= %.1f su %d messaggi di settembre) -> soglia nuova %.3f, quota "
             "nuova %.4f sul campione", res["quota"], SOGLIA_VECCHIA, res["n_vecchio"], res["soglia"], res["quota_nuova"])
    sal = np.array([x[2] for x in nuove.values()])
    log.info("  salienza dei nodi: p5 %.2f p50 %.2f p95 %.2f; sotto la soglia nuova %d (restano tutti)",
             *np.percentile(sal, [5, 50, 95]), res["nodi_sotto"])
    conta = {}
    for x in nuove.values():
        conta[x[1]] = conta.get(x[1], 0) + 1
    log.info("  dominanti nuove: %s", sorted(conta.items(), key=lambda kv: -kv[1]))
    log.info("  emozione dominante cambiata: %d/%d", sum(1 for n, x in nuove.items() if x[1] != vecchi[n]), len(nuove))
    log.info("  quota del campione forte (salienza >= soglia + 1): %.4f; salienza/soglia p50 p90 p99: %s",
             res["quota_forte"], " ".join(f"{x:.2f}" for x in res["sal_su_soglia"]))
    if dry:
        return res

    bak = f".bak-pre-firme-se-{time.strftime('%Y%m%d-%H%M%S')}"
    M = T.memoria
    M.DB, M.VEC = M.Path(DB), M.Path(VEC)
    with open(f"{DB}.lock", "w") as lk:   # 09/11: lo stesso lucchetto di memoria.add_node, backup compreso
        fcntl.flock(lk, fcntl.LOCK_EX)
        src = sqlite3.connect(DB)
        src.execute("PRAGMA busy_timeout=5000")
        assert {r[0] for r in src.execute("SELECT id FROM nodi")} == set(nuove), "nodi cambiati dopo la lettura: rilanciare"
        dst = sqlite3.connect(DB + bak)
        src.backup(dst)
        dst.close()
        for p in (VEC, STATS):
            if os.path.exists(p):
                shutil.copy2(p, p + bak)
        log.info("backup %s fatti", bak)
        with src:
            for nid, (firma, dom, salienza) in nuove.items():
                src.execute("UPDATE nodi SET firma=?, emo_tag=?, salienza=? WHERE id=?",
                            (json.dumps(firma, ensure_ascii=False), dom, salienza, nid))
        src.close()
        vec = M._load_vec()
        for nid, (firma, _, _) in nuove.items():
            if nid in vec:
                vec[nid]["addr_emo"] = M.addr_emo(firma)   # B7: come memoria.add_node (ordine di emozioni.json)
        M._save_vec(vec)   # file temporaneo e os.replace
        torch.save(stats, STATS + ".tmp")
        os.replace(STATS + ".tmp", STATS)
    log.info("FIRME-SCRITTE: memoria.db %d nodi, vettori.pt addr_emo, %s n=%d soglia %.3f", len(nuove), STATS,
             stats["n"], stats["soglia"])
    return res


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
