#!/usr/bin/env python3
"""Pulizia dei ricordi (l'utente 01/11 sera, "puliscili e togli i 3 di spazzatura").
  VIA: 699 (riassunto di Hermes "[CONTEXT COMPACTION]"), 81 (errore di un cron), 7 (ragionamento + solo "✅").
  PULITI: 20 ricordi di luglio col blocco "💭 **Reasoning:** ```...```" davanti alla risposta dell'agente (prima che pulisci
  lo togliesse): il testo diventa la sola risposta, firma rifatta (firma_se.firma_server, contesto delle 24 ore prima
  dalla chat come in B3, stats di B3), addr_sem = bge-m3 del testo nuovo (come i nodi nuovi), addr_emo dalla firma.
  Nel Lux i 23 escono (archi, cariche, stato, salienza) e i 20 rientrano col testo nuovo (aggiungi): stesso nid e
  stesso ts, quindi stesso codice; i rinforzi dei loro archi si perdono (accettato dall'utente). Gli altri ricordi non si
  toccano: archi, stato e rinforzi identici.
Passi (MEM_SAM e LUX_DIR puntano una copia per la prova):
  jspace venv:  pulisci_ricordi_0111.py firme   -> firme-pulizia.json (legge il server URL_FIRMA, default 8098)
  venv-spacy:   pulisci_ricordi_0111.py lux-togli
  jspace venv:  pulisci_ricordi_0111.py db
  venv-spacy:   pulisci_ricordi_0111.py lux-rimetti"""
import json
import os
import re
import sys

VIA = [699, 81, 7]
PULITI = [8, 21, 23, 41, 42, 45, 49, 50, 51, 55, 61, 63, 66, 67, 69, 71, 73, 75, 78, 80]
MEM = os.environ.get("MEM_SAM", "/data/workspace/memoria")
DB = f"{MEM}/memoria.db"
QUI = os.path.dirname(os.path.abspath(__file__))
FIRME = os.environ.get("FIRME_PULIZIA", f"{QUI}/firme-pulizia.json")
RAGIONAMENTO = re.compile(r"\s*💭 \*\*Reasoning:\*\*\s*```.*?```\s*", re.S)


def testi_nuovi(db):
    out = {}
    for nid in PULITI:
        t = db.execute("select testo from nodi where id = ?", (nid,)).fetchone()[0]
        m = RAGIONAMENTO.match(t)
        assert m, f"{nid}: niente ragionamento in testa"
        out[nid] = t[m.end():].strip()
        assert len(out[nid]) >= 15 and "💭" not in out[nid], nid
    return out


def firme():
    import sqlite3
    import numpy as np
    import torch
    sys.path.insert(0, "/data/memoria-episodica-affettiva/firme-occamy")
    import importlib.util
    spec = importlib.util.spec_from_file_location("R", "/data/memoria-episodica-affettiva/firme-occamy/ricalcola-firme-se.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    url = os.environ.get("URL_FIRMA", "http://127.0.0.1:8098")
    s = torch.load("/data/memoria-episodica-affettiva/stats-firma-se.pt", weights_only=False)
    with urllib_get(url + "/props") as f:
        assert json.load(f)["model_path"] == s["lettore"], "lettore diverso da quello delle statistiche"
    mean, sd = s["mean"].double().numpy(), np.sqrt(s["M2"].double().numpy() / max(s["n"] - 1, 1))
    mu = {l: s["mu"][l].double().numpy() for l in R.F.STRATI}
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    nuovi = testi_nuovi(db)
    chat = R.carica_chat()
    out = {}
    for nid, testo in nuovi.items():
        ts = db.execute("select ts from nodi where id = ?", (nid,)).fetchone()[0]
        r = R.F.firma_server(R.contesto(chat, ts), testo, url, mu)
        z = (r - mean) / (sd + 1e-6)
        f = {a: round(float(z[j]), 3) for j, a in enumerate(s["assi"])}
        dom = max(f, key=f.get)
        out[nid] = {"testo": testo, "firma": f, "emo_tag": dom, "salienza": f[dom]}
        print(f"{nid}: {dom} z={f[dom]:.2f} ({len(testo)} car)", flush=True)
    json.dump(out, open(FIRME, "w"), ensure_ascii=False, indent=1)


def urllib_get(url):
    import urllib.request
    return urllib.request.urlopen(url, timeout=10)


def db_aggiorna():
    import sqlite3
    import torch
    sys.path.insert(0, "/data/memoria-episodica-affettiva")
    import memoria
    import persistenza
    memoria.DB, memoria.VEC = memoria.Path(DB), memoria.Path(f"{MEM}/vettori.pt")
    nuovi = {int(k): v for k, v in json.load(open(FIRME, encoding="utf-8")).items()}
    assert sorted(nuovi) == sorted(PULITI)
    sem = dict(zip(PULITI, persistenza.vettore([nuovi[n]["testo"] for n in PULITI])))
    with open(f"{DB}.lock", "w") as lk:
        import fcntl
        fcntl.flock(lk, fcntl.LOCK_EX)
        c = sqlite3.connect(DB)
        with c:
            for nid in VIA:
                t = c.execute("select testo from nodi where id = ?", (nid,)).fetchone()
                if t:
                    c.execute("insert into nodi_fts(nodi_fts, rowid, testo) values('delete', ?, ?)", (nid, t[0]))
                    c.execute("delete from nodi where id = ?", (nid,))
                c.execute("delete from archi where a = ? or b = ?", (nid, nid))
            for nid, v in nuovi.items():
                vecchio = c.execute("select testo from nodi where id = ?", (nid,)).fetchone()[0]
                c.execute("insert into nodi_fts(nodi_fts, rowid, testo) values('delete', ?, ?)", (nid, vecchio))
                c.execute("update nodi set testo = ?, firma = ?, emo_tag = ?, salienza = ? where id = ?",
                          (v["testo"], json.dumps(v["firma"], ensure_ascii=False), v["emo_tag"], v["salienza"], nid))
                c.execute("insert into nodi_fts(rowid, testo) values (?, ?)", (nid, v["testo"]))
        c.close()
        vec = memoria._load_vec()
        for nid in VIA:
            vec.pop(nid, None)
        for nid, v in nuovi.items():
            vec[nid] = {"addr_sem": torch.tensor(sem[nid]), "addr_emo": memoria.addr_emo(v["firma"])}
        memoria._save_vec(vec)
    print(f"memoria.db: {len(VIA)} tolti, {len(nuovi)} puliti")


def lux_togli():
    import numpy as np
    import lux_engrammi as X
    import salienza as SA
    via = set(VIA) | set(PULITI)
    with X.lucchetto():
        z, m = dict(np.load(X.NPZ)), json.load(open(X.META))
        tieni = ~np.isin(z["A"][:, 0], list(via))
        A, C = z["A"][tieni], z["C"][tieni]
        sal = SA._senza(z)
        k = ~np.isin(sal["ids"], list(via))   # ricordi che restano, nell'ordine
        nuovo_k = np.cumsum(k) - 1
        f = k[sal["di"]]
        sal.update(ids=sal["ids"][k], dist_raw=sal["dist_raw"][k], se_raw=sal["se_raw"][k], nf=sal["nf"][k],
                   dist=sal["dist"][k], se=sal["se"][k], F=sal["F"][f], di=nuovo_k[sal["di"][f]])
        z = {kk: v for kk, v in z.items() if not kk.startswith("sal_")}
        z.update(A=A, C=C, F=X.firme_engrammi(A, C, len(m["engrammi"])), **SA._prefisso(sal))
        s = np.load(X.STATO)
        np.savez(X.STATO + ".tmp.npz", S=s["S"][tieni], S0=s["S0"][tieni], U=s["U"][tieni])
        np.savez(X.NPZ + ".tmp.npz", **z)
        for n in via:
            m["ricordi"].pop(str(n), None)
        json.dump(m, open(X.META + ".tmp", "w"), ensure_ascii=False)
        os.replace(X.NPZ + ".tmp.npz", X.NPZ)
        os.replace(X.STATO + ".tmp.npz", X.STATO)
        os.replace(X.META + ".tmp", X.META)
    print(f"Lux: {len(via)} ricordi tolti, {int((~tieni).sum())} archi tolti, {int(tieni.sum())} restano")


def lux_rimetti():
    import taglia as T
    T.DB = DB
    import lux_engrammi as X
    X.aggiungi()


if __name__ == "__main__":
    {"firme": firme, "db": db_aggiorna, "lux-togli": lux_togli, "lux-rimetti": lux_rimetti}[sys.argv[1]]()
