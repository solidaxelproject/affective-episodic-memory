#!/usr/bin/env python3
"""Via emotiva del richiamo, 1.19.0 (PIANO-1.19-VIA-EMOTIVA.md, decisioni dell'utente dell'11/11).
Due tempi: ogni testo che arriva (messaggio dell'utente, risposta dell'agente, risultato di uno strumento) passa dalla J-lens
su L29 (traduzione appresa ai 44 assi della firma, accordo 0.69) = emozione suscitata; ogni lettura imprime l'umore
(omeostato, impronta 0.12). L'indizio emotivo del richiamo = meta' emozione del messaggio e meta' umore di prima;
peso k = 0.2 x D / 1.1 fra 0.1 e 0.4 (D = distanza dell'umore dalla calma); riparazione dell'umore dopo 3 letture
negative di fila (valori provvisori di CC). Tutto finisce nel diario delle letture: !verifica emotiva!
(VERIFICA-VIA-EMOTIVA.md, verifica_via_emotiva.py) rigioca le scelte con altri numeri.
Lo importa il riflesso (/usr/bin/python3): solo numpy e libreria standard.
  python via_emotiva.py addestra   (venv-spacy) -> via-emotiva/traduzione-l29.npz"""
import json
import os
import sys
import threading
import time

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))
sys.path.append("/data/workspace/memoria")   # in coda: la cartella la scrive anche il container
sys.path.append(os.path.join(os.path.dirname(QUI), "runtime"))   # nel repo pubblico stato.py sta in runtime/
import ponte  # noqa: E402
import stato as omeostato  # noqa: E402

TRADUZIONE = os.environ.get("VIA_EMOTIVA_TRADUZIONE", f"{QUI}/via-emotiva/traduzione-l29.npz")
STATO = os.environ.get("VIA_EMOTIVA_STATO", "/data/workspace/memoria/via-emotiva-stato.json")
DIARIO = os.environ.get("VIA_EMOTIVA_DIARIO", "/data/workspace/memoria/diario-via-emotiva.jsonl")
IMPRONTA = 0.12      # l'utente 11/11 18:35
META_MESSAGGIO = 0.5  # l'utente 11/11 18:33: a, il resto e' l'umore
K_NORMALE, K_MIN, K_MAX = 0.2, 0.1, 0.4   # l'utente 11/11 17:08 e 18:45; il valore normale di D sta nella traduzione
# (taratura: era 1.1 nella simulazione T1f senza consegne; da ritarare coi dati veri del diario)
RIPARA_DI_FILA = 3   # provvisorio di CC (11/11 19:15): la mediana dei periodi negativi simulati
RIPARA_PERCENTILE = 75   # provvisorio di CC: la soglia della negativita' e' questo percentile della simulazione
TESTO_MAX = 4000   # CC: circa i primi 1024 token, come l'addestramento (stati dei ricordi)
LETTE_MAX = 200
TIMEOUT = 20   # CC: oltre, consegna senza emozione (mai bloccare la parola dell'agente)
_lock = threading.Lock()
_tr = {}


def _un(v):
    return v / (np.linalg.norm(v) + 1e-9)


def traduzione():
    if not _tr:
        z = np.load(TRADUZIONE)
        _tr.update({k: z[k] for k in z.files})
        _tr["assi"] = [str(a) for a in _tr["assi"]]
    return _tr


def negativita(u):
    """media degli assi negativi meno media dei positivi di u (= umore - calma)"""
    t = traduzione()
    return float(u[t["neg"]].mean() - u[t["pos"]].mean())


def leggi(testo):
    """(z sui 44 assi, token letti): lo stato medio di L29 del testo intero (fino a TESTO_MAX) tradotto"""
    t = traduzione()
    r = ponte._post("/lux-read", {"content": testo[:TESTO_MAX], "layer": ponte.LAYER_SONDA}, timeout=TIMEOUT)
    return np.asarray(r["mean"], np.float64) @ t["M"] + t["b"], int(r.get("n_tokens", 0))


def _stato_rip():
    try:
        return json.load(open(STATO))
    except (OSError, ValueError):
        return {"di_fila": 0}


def _salva_rip(st):
    with open(STATO + ".tmp", "w") as f:
        json.dump(st, f)
    os.replace(STATO + ".tmp", STATO)


def gia_letta(chiave):
    """revisione 11/11: Hermes rimanda la stessa richiesta (pensatoio rimandato, ritentativi, riavvio del riflesso):
    True se la chiave e' fra le ultime LETTE_MAX lette (stato su disco), e allora non si rilegge"""
    with _lock:
        return chiave in _stato_rip().get("lette", [])


def segna_letta(chiave):
    """dopo una lettura riuscita: una lente rotta lascia rileggere il messaggio al rinvio di Hermes"""
    with _lock:
        st = _stato_rip()
        st["lette"] = (st.get("lette", []) + [chiave])[-LETTE_MAX:]
        _salva_rip(st)


def imprimi(z):
    """la lettura imprime l'umore (solo i 44 assi); -> (umore prima, umore dopo, negativita', riparazione)
    riparazione = {"accesa", "di_fila"} dopo questa lettura"""
    t = traduzione()
    with _lock:
        prima, dopo = omeostato.imprimi_lettura(dict(zip(t["assi"], map(float, z))), IMPRONTA)
        up = np.array([float(prima.get(a, 0.0)) for a in t["assi"]])
        ud = np.array([float(dopo.get(a, 0.0)) for a in t["assi"]])
        neg = negativita(ud - t["calma"])
        st = _stato_rip()
        st["di_fila"] = st.get("di_fila", 0) + 1 if neg > float(t["ripara_soglia"]) else 0
        _salva_rip(st)
    return up, ud, neg, {"accesa": st["di_fila"] >= RIPARA_DI_FILA, "di_fila": st["di_fila"]}


def indizio(z_msg, umore_prima, riparazione=False):
    """(q sui 44 assi, k, D): q = meta' emozione del messaggio e meta' umore di prima (lunghezza 1 ciascuno);
    con la riparazione la meta' dell'umore va sulle emozioni positive"""
    t = traduzione()
    u = umore_prima - t["calma"]
    D = float(np.linalg.norm(u))
    if riparazione:
        u = np.zeros_like(u)
        u[t["pos"]] = 1.0
    q = _un(META_MESSAGGIO * _un(z_msg) + (1 - META_MESSAGGIO) * _un(u))
    return q, float(np.clip(K_NORMALE * D / float(t["D_normale"]), K_MIN, K_MAX)), D


def diario(voce):
    voce = {"ts": round(time.time(), 3), **voce}
    with _lock, open(DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")


def tondo(v, n=3):
    return [round(float(x), n) for x in v]


# ---------- addestramento (una volta: i vettori se' non cambiano finche' si usa Occamy, l'utente 11/11) ----------
def _ridge(X, T, lam):
    mx, sx, my = X.mean(0), X.std(0) + 1e-9, T.mean(0)
    A = (X - mx) / sx
    Wd = A.T @ np.linalg.solve(A @ A.T + lam * np.eye(len(A)), T - my)
    return mx, sx, my, Wd


def _corr(P, T):
    P, T = P - P.mean(0), T - T.mean(0)
    return float(np.nanmean((P * T).sum(0) / (np.sqrt((P * P).sum(0) * (T * T).sum(0)) + 1e-12)))


def _scegli(X, T, lams=tuple(10.0 ** k for k in range(1, 6))):
    """la forza scelta a 4 parti dentro i dati, come T1d"""
    sub = np.arange(len(X)) % 4
    punti = []
    for lam in lams:
        Q = np.zeros_like(T)
        for g in range(4):
            mx, sx, my, Wd = _ridge(X[sub != g], T[sub != g], lam)
            Q[sub == g] = ((X[sub == g] - mx) / sx) @ Wd + my
        punti.append(_corr(Q, T))
    return lams[int(np.argmax(punti))]


def addestra(uscita=TRADUZIONE):
    d = np.load(f"{QUI}/misura-t1a-stati.npz")
    emo = [e["en"] for e in json.load(open(os.path.join(os.path.dirname(QUI), "emozioni.json")))]
    CA = d["CA"]
    assi = [i for i in range(51) if CA[:, i].std() > 0]
    J = np.load(ponte.LENTE_NPY).astype(np.float64)
    G = d["H"][:, 29 - 15].astype(np.float64)   # il "mean" grezzo di /lux-read su L29, la strada della produzione
    X, Y = G @ J.T, CA[:, assi].astype(np.float64)
    mu_y, sd_y = Y.mean(0), Y.std(0) + 1e-9
    # controllo: accordo a 5 parti con le stesse parti di T1a (deve tornare circa 0.68)
    parti = np.random.default_rng(0).permutation(len(Y)) % 5
    P = np.zeros_like(Y)
    for f in range(5):
        tr, te = parti != f, parti == f
        mx, sx, my, Wd = _ridge(X[tr], Y[tr], _scegli(X[tr], Y[tr]))
        P[te] = ((X[te] - mx) / sx) @ Wd + my
    accordo = _corr(P, Y)
    lam = _scegli(X, Y)
    mx, sx, my, Wd = _ridge(X, Y, lam)
    # z = ((G J^T - mx) / sx Wd + my - mu_y) / sd_y = G M + b
    M = (J.T @ (Wd / sx[:, None])) / sd_y
    b = (my - (mx / sx) @ Wd - mu_y) / sd_y
    nomi = [emo[i] for i in assi]
    calma = np.array([omeostato.DEFAULT_BASELINE.get(e, 0.0) for e in nomi])
    sys.path.insert(0, QUI)
    import lux_engrammi as LE
    pos = np.array([i for i, e in enumerate(nomi) if e in LE.POSITIVE])
    neg = np.array([i for i, e in enumerate(nomi) if e not in LE.POSITIVE and e not in LE.NEUTRE])
    Zp = (P - mu_y) / sd_y
    tar = taratura(d["nid"], Zp, nomi, calma, pos, neg)
    soglia, d_normale = tar["ripara_soglia"], tar["D_normale"]
    os.makedirs(os.path.dirname(uscita), exist_ok=True)
    np.savez(uscita, M=M.astype(np.float32), b=b, assi=np.array(nomi), forza=lam, accordo=accordo, calma=calma,
             pos=pos, neg=neg, ripara_soglia=soglia, D_normale=d_normale, ricordi=d["nid"])
    print(json.dumps({"assi": len(nomi), "forza": lam, "accordo_5_parti": round(accordo, 3),
                      "positivi": len(pos), "negativi": len(neg), **tar}))


def taratura(nid, Zp, nomi, calma, pos, neg, theta=0.35, impronta_consegna=0.25):
    """valore normale di D e soglia della riparazione (CC, revisione 11/11: l'omeostato vero lo muovono anche le
    consegne e la notte, non solo le letture). Simulazione sulla storia vera: ogni messaggio-ricordo letto (lettura
    prevista senza averlo visto) imprime IMPRONTA; ogni ricordo consegnato (diario-riflessi.jsonl) imprime la sua firma
    a 0.25 come barra-prefill; ogni mezzanotte la media delle firme dei ricordi del giorno a 0.25 come la notturna.
    D e negativita' si misurano a ogni lettura: D_normale = mediana, soglia = RIPARA_PERCENTILE-esimo percentile"""
    import datetime
    import meta_lux   # 1.20.0: dal meta del Lux (prima memoria.db); le correzioni restano fuori come prima
    meta = json.load(open(meta_lux.percorso()))["ricordi"]
    ts, firma = {}, {}
    for r, m in meta.items():
        if m["classe"] == "correzione":
            continue
        ts[int(r)] = float(m["ts"])
        if m.get("firma"):
            firma[int(r)] = np.array([float(m["firma"].get(e, 0.0)) for e in nomi])
    ev = [(ts[int(r)], 0, Zp[k]) for k, r in enumerate(nid) if int(r) in ts]
    for riga in open("/data/workspace/memoria/diario-riflessi.jsonl", encoding="utf-8"):
        try:
            v = json.loads(riga)
        except ValueError:
            continue
        ev += [(float(v["ts"]), 1, firma[n]) for n in v.get("nid") or [] if n in firma]
    giorni = {}
    for r, t in ts.items():
        if r in firma:
            giorni.setdefault(datetime.date.fromtimestamp(t), []).append(firma[r])
    ev += [(datetime.datetime.combine(g + datetime.timedelta(days=1), datetime.time()).timestamp(), 2, np.mean(f, 0))
           for g, f in giorni.items()]
    ev.sort(key=lambda x: (x[0], x[1]))
    umore, t_prec, D, negs, di_fila, periodi = calma.copy(), None, [], [], 0, []
    for t, tipo, v in ev:
        if t_prec is not None:
            umore = umore + (1 - np.exp(-theta * max(0.0, t - t_prec) / 3600)) * (calma - umore)
        t_prec = t
        if tipo == 0:   # D sull'umore di prima, come nell'indizio (revisione del codice 11/11)
            D.append(float(np.linalg.norm(umore - calma)))
        umore = np.clip(umore + (IMPRONTA if tipo == 0 else impronta_consegna) * (v - umore), -3.5, 3.5)
        if tipo == 0:   # la negativita' dopo, come in imprimi
            u = umore - calma
            negs.append(float(u[neg].mean() - u[pos].mean()))
    soglia = float(np.percentile(negs, RIPARA_PERCENTILE))
    for x in negs:
        if x > soglia:
            di_fila += 1
        elif di_fila:
            periodi.append(di_fila)
            di_fila = 0
    return {"D_normale": round(float(np.median(D)), 4), "D_percentili_10_90": [round(float(x), 3) for x in np.percentile(D, [10, 90])],
            "ripara_soglia": round(soglia, 4), "periodi_negativi": len(periodi),
            "periodo_mediana_letture": float(np.median(periodi)) if periodi else 0.0,
            "letture": len(D), "consegne": sum(1 for e in ev if e[1] == 1), "notti": sum(1 for e in ev if e[1] == 2)}


if __name__ == "__main__":
    if sys.argv[1:] == ["addestra"]:
        addestra()
