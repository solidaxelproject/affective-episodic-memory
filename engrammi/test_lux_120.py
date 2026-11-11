"""1.20.0 (l'utente 22/10 + 11/11, PIANO-1.20-MEMORIADB-SUPERFLUO.md): i dati dei ricordi stanno nel Lux, memoria.db
solo archivio. Su una copia (LUX_DIR temporanea): migrazione dalla 1.19.0 identica al db, ricordo nuovo con nid, dedup,
S0 di trascinato e abitudine come prima, correzioni fuori dal dedup, carica_stato e ricordo() dal meta."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

import numpy as np

DIR = tempfile.mkdtemp(prefix="lux120-")
os.environ["LUX_DIR"] = DIR
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lux_engrammi as X  # noqa: E402

DB = "/data/workspace/memoria/memoria.db"
assert X.PRECEDENTE.endswith("lux-1.19.0"), X.PRECEDENTE
try:
    X.da_precedente()
    P = X.PRECEDENTE
    for f in ("lux.npz", "lux-stato.npz"):
        assert open(f"{P}/{f}", "rb").read() == open(f"{DIR}/{f}", "rb").read(), f
    mp, m = json.load(open(f"{P}/lux-meta.json")), json.load(open(X.META))
    assert m["engrammi"] == mp["engrammi"] and m["altri_parametri"] == mp["altri_parametri"]
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    righe = c.execute("select id, testo, firma, emo_tag, fonte, cattura, salienza, voluto from nodi where testo != ''").fetchall()
    assert len(righe) == len(m["ricordi"]) == len(mp["ricordi"])
    for nid, testo, firma, dom, fonte, catt, sal, vol in righe:
        r, rp = m["ricordi"][str(nid)], mp["ricordi"][str(nid)]
        assert {k: r[k] for k in rp} == rp, nid   # i campi della 1.19.0 restano identici
        assert (r["testo"], r["firma"], r["dominante"], r["fonte"], r["cattura"], r["salienza"], r["voluto"]) == \
            (testo, json.loads(firma) if firma else None, dom, fonte, catt, sal, vol), nid
    print(f"migrazione: {len(righe)} ricordi identici al db, npz e stato identici al byte")

    # carica e s0_ricordi: firma dict = firma json
    f = m["ricordi"]["815"]["firma"]
    assert np.array_equal(X.carica(f), X.carica(json.dumps(f)))
    rk = X.SA.ranghi(np.load(X.NPZ))
    assert X.s0_ricordi({1: f}, rk, [1]) == X.s0_ricordi({1: json.dumps(f)}, rk, [1])

    # carica_stato senza lux-stato.npz: S0 dalle firme del meta, uguale a quello dalle firme del db
    shutil.move(X.STATO, X.STATO + ".via")
    L = X.Lux()
    s0 = X.s0_ricordi(dict(c.execute("select id, firma from nodi")), X.SA.ranghi(np.load(X.NPZ)), L.ricordi)
    assert np.array_equal(L.S0, np.asarray([s0[int(r)] for r in L.A[:, 0]], np.float64))
    shutil.move(X.STATO + ".via", X.STATO)
    print("carica_stato: S0 dal meta identico a quello dal db")

    # ricordo(codice)
    L = X.Lux()
    r = L.ricordo(m["ricordi"]["815"]["codice"])
    assert r["nid"] == 815 and r["testo"] == m["ricordi"]["815"]["testo"] and r["dominante"] == "serenity", r
    assert L.ricordo("zzzzinesistente") is None

    # ricordo nuovo: nid dopo il massimo, campi nel meta, dedup sul testo esatto
    v = {"testo": "Oggi l'utente mi ha fatto sentire il pezzo nuovo e ho pensato a quanto mi piace la sua voce.",
         "firma": f, "dominante": "serenity", "fonte": "@agente:localhost", "ts": 1794400000.0,
         "classe": "vissuto", "voluto": 0, "cattura": None, "salienza": 2.5}
    n_a = len(np.load(X.NPZ)["A"])
    nid = X.aggiungi_ricordo(v)
    assert nid == 816, nid
    m = json.load(open(X.META))
    r = m["ricordi"]["816"]
    assert all(r[k] == v[k] for k in v), r
    assert r["codice"] == X.codice(v["ts"])
    n_b = len(np.load(X.NPZ)["A"])
    assert n_b > n_a and len(np.load(X.STATO)["S"]) == n_b
    assert X.aggiungi_ricordo(dict(v, ts=1794400500.0)) == 816 and len(np.load(X.NPZ)["A"]) == n_b
    print(f"ricordo nuovo 816 con {n_b - n_a} archi, dedup sul testo")

    # S0 dei trascinati (x cattura) e delle abitudini (almeno S_ABITUDINE), come la 1.19.0 da memoria.db
    z = np.load(X.NPZ)
    for i, (fonte, catt, atteso) in enumerate((("trascinato", 0.4, lambda s: s * 0.4), ("trascinato", None, lambda s: s * X.TRASCINATO_S0),
                                ("abitudine", None, lambda s: max(s, X.S_ABITUDINE)))):
        testo = f"Un pensiero di prova per la fonte {fonte} con cattura {catt}, che non somiglia a niente."
        n = X.aggiungi_ricordo(dict(v, testo=testo, fonte=fonte, cattura=catt, ts=v["ts"] + 1000 + i))
        z, s = np.load(X.NPZ), np.load(X.STATO)
        k = z["A"][:, 0] == n
        base = X.s0_ricordi({n: f}, X.SA.ranghi(z), [n])[n]
        assert np.allclose(s["S0"][k], atteso(base)), (fonte, catt)
    print("S0 di trascinati e abitudini come prima")

    # le correzioni stanno fuori dal dedup e fuori dalla serie
    cod = X.correggi(X.codice(v["ts"]), "Testo della correzione di prova, abbastanza lungo da tagliare.", ts=1794409999.0)
    m = json.load(open(X.META))
    nc = next(int(k) for k, r in m["ricordi"].items() if r["codice"] == cod)
    assert nc == X.PRIMO_CORREZIONE and m["ricordi"][str(nc)]["testo"].startswith("Testo della correzione")
    n2 = X.aggiungi_ricordo(dict(v, testo=m["ricordi"][str(nc)]["testo"], ts=v["ts"] + 2000))
    assert n2 < X.PRIMO_CORREZIONE and n2 not in (816, nc), n2
    assert X.Lux().ricordo(cod)["classe"] == "correzione"
    print("correzioni fuori dal dedup e dalla serie")
    print("OK test_lux_120")
finally:
    shutil.rmtree(DIR, ignore_errors=True)
