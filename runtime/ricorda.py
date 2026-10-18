#!/usr/bin/env python3
# Richiamo dalla memoria affettiva: SOLO libreria standard (gira nel container).
# Uso: ricorda.py --emo gioia [-k 3] | ricorda.py --testo "parole" [-k 3]
#      ricorda.py --id <codice>   richiamo diretto di un ricordo (codice di 16 caratteri, 18/10;
#                                 vale anche il numero del nodo)
#      ricorda.py --richiamati   i ricordi che il riflesso mi ha consegnato dall'ultima notturna (18/10)
#      ricorda.py --stats
# Emozioni in inglese (lessico Plutchik): joy, fear, sadness, love, curiosity...
import argparse
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent / "memoria.db"
HEBB_GAIN = 0.1
HEBB_BLEND = 0.25

import stato as omeostato

p = argparse.ArgumentParser()
p.add_argument("--emo")
p.add_argument("--testo")
p.add_argument("--id", help="richiama un ricordo preciso: il suo codice (o il numero del nodo)")
p.add_argument("--congruente", action="store_true",
               help="richiamo guidato dallo stato emotivo attuale")
p.add_argument("-k", type=int, default=3)
p.add_argument("--stats", action="store_true")
p.add_argument("--richiamati", action="store_true",
               help="i ricordi consegnati dal riflesso dall'ultima notturna, col loro codice")
p.add_argument("--stato", action="store_true",
               help="mostra lo stato emotivo attuale")
args = p.parse_args()


def codice(ts):
    """il codice del ricordo, come lux_engrammi.codice e il riflesso: SHA-256 del timestamp, 16 caratteri [0-9a-z]"""
    n, s = int(hashlib.sha256(repr(ts).encode()).hexdigest(), 16), ""
    for _ in range(16):
        n, r = divmod(n, 36)
        s += "0123456789abcdefghijklmnopqrstuvwxyz"[r]
    return s

if args.stato:
    print("stato attuale:", omeostato.descrivi())
    sys.exit(0)

c = sqlite3.connect(DB)
c.execute("PRAGMA busy_timeout=5000")

if args.stats:
    n = c.execute("SELECT COUNT(*) FROM nodi").fetchone()[0]
    per = c.execute("SELECT emo_tag, COUNT(*) FROM nodi GROUP BY emo_tag "
                    "ORDER BY 2 DESC LIMIT 10").fetchall()
    print(f"{n} ricordi. Emozioni più frequenti: "
          + ", ".join(f"{e} ({q})" for e, q in per))
    sys.exit(0)

if args.richiamati:
    # il file lo scrive il riflesso a ogni consegna e lo svuota la notturna; solo lettura, non e' un richiamo
    try:
        conv = json.loads((Path(__file__).parent / "consegne-memorinvolontaria.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        conv = {}
    codici = list(dict.fromkeys(cod for v in sorted(conv.values(), key=lambda v: v.get("ts", 0))
                                for voce in v.get("voci", []) for cod in voce.get("codici") or [voce.get("codice")]))
    nodi = {codice(ts): (emo, testo) for ts, emo, testo in c.execute("SELECT ts, emo_tag, testo FROM nodi")}
    if not codici:
        print("nessun ricordo richiamato dall'ultima notturna")
    for cod in codici:
        emo, testo = nodi.get(cod, ("?", "(non piu' nel grafo)"))
        print(f"{cod} ({emo}) {testo.splitlines()[0][:120] if testo else ''}")
    sys.exit(0)

def _cosine_su_firma(query):
    """query: dict {emo: peso}. Cosine con le firme dei soli nodi VISSUTI:
    regola 2 del contratto: il 'letto' non partecipa al richiamo emotivo."""
    qn = math.sqrt(sum(v * v for v in query.values())) or 1.0
    out = {}
    for nid, firma_json in c.execute(
            "SELECT id, firma FROM nodi WHERE classe='vissuto'"):
        firma = json.loads(firma_json)
        norm = math.sqrt(sum(v * v for v in firma.values())) or 1.0
        out[nid] = sum(firma.get(e, 0) * w for e, w in query.items()) / (norm * qn)
    return out


def _cerca_testo(q):
    """FTS5 sul testo libero. La query passa com'e' (OR, NOT, prefisso* restano
    operatori); se FTS5 la rifiuta (com'era, "casa, mare", e-mail, paura: tanta)
    si riprova con ogni parola tra virgolette, cioe' come testo e non sintassi."""
    sql = ("SELECT rowid, rank FROM nodi_fts WHERE nodi_fts MATCH ? "
           "ORDER BY rank LIMIT 20")
    try:
        return c.execute(sql, (q,)).fetchall()
    except sqlite3.OperationalError:
        q = " ".join('"' + p.replace('"', '""') + '"' for p in q.split())
        return c.execute(sql, (q,)).fetchall() if q else []


scores = {}
if args.id:
    q = args.id.strip().lower()
    nid = int(q) if q.isdigit() else next(
        (i for i, ts in c.execute("SELECT id, ts FROM nodi") if codice(ts) == q), None)
    if nid is None or not c.execute("SELECT 1 FROM nodi WHERE id=?", (nid,)).fetchone():
        sys.exit(f"nessun ricordo con codice {args.id}")
    scores = {nid: 1.0}
elif args.testo:
    rows = _cerca_testo(args.testo)
    scores = {r[0]: 1.0 / (1 + i) for i, r in enumerate(rows)}
elif args.congruente:
    st = omeostato.carica()
    if st is None:
        sys.exit("stato non inizializzato: fai prima un richiamo --emo")
    scores = _cosine_su_firma(st)
    print(f"(stato attuale: {omeostato.descrivi()})\n")
elif args.emo:
    esempio = c.execute("SELECT firma FROM nodi LIMIT 1").fetchone()
    if esempio and args.emo not in json.loads(esempio[0]):
        sys.exit(f"emozione sconosciuta: {args.emo}. Usa i nomi Plutchik in "
                 f"inglese, es: joy, sadness, fear, love, curiosity, hope...")
    scores = _cosine_su_firma({args.emo: 1.0})
else:
    p.error("serve --emo, --testo, --congruente, --stato o --stats")

# spinta hebbiana dagli archi dei nodi più forti
top3 = sorted(scores, key=scores.get, reverse=True)[:3]
for a in top3:
    for b, w in c.execute("SELECT b, w FROM archi WHERE a=?", (a,)):
        if b in scores:
            scores[b] += HEBB_BLEND * w * scores[a]


top = sorted(scores, key=scores.get, reverse=True)[:args.k]
for nid in top:
    r = c.execute("SELECT testo, emo_tag, ts FROM nodi WHERE id=?",
                  (nid,)).fetchone()
    if r:
        testo = r[0] if len(r[0]) < 600 else r[0][:600] + " [...]"
        print(f"--- ricordo {codice(r[2])} ({r[1]}) ---\n{testo}\n")

# diario dei richiami: il dataset che un giorno addestrerà il recupero (gradino 2)
import time as _time
with open(Path(__file__).parent / "diario-richiami.jsonl", "a") as _d:
    _d.write(json.dumps({
        "ts": _time.time(),
        "modo": "id" if args.id else (
            "testo" if args.testo else ("congruente" if args.congruente else "emo")),
        "query": str(args.id) if args.id else (args.testo or args.emo or "stato"),
        "risultati": top,
    }, ensure_ascii=False) + "\n")

# il richiamo imprime lo stato emotivo (i ricordi richiamati lo spostano)
firme_top = [json.loads(c.execute("SELECT firma FROM nodi WHERE id=?",
                                  (nid,)).fetchone()[0]) for nid in top]
if firme_top:
    # via semantica (--testo) = vicinanza di significato, non risonanza
    # emotiva: l'impronta sullo stato è depotenziata (progetto 22/07)
    omeostato.imprimi(firme_top, semantico=bool(args.testo))

# rinforzo hebbiano del co-richiamo
if len(top) >= 2:
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            for x, y in ((a, b), (b, a)):
                c.execute("INSERT INTO archi (a,b,w) VALUES (?,?,?) "
                          "ON CONFLICT(a,b) DO UPDATE SET w=w+?",
                          (x, y, HEBB_GAIN, HEBB_GAIN))
    c.executemany("UPDATE nodi SET n_richiami=n_richiami+1 WHERE id=?",
                  [(n,) for n in top])
    c.commit()
c.close()
