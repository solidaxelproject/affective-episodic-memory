#!/usr/bin/env python3
# Richiamo dalla memoria affettiva: SOLO libreria standard (gira nel container).
# Uso: ricorda.py --emo gioia [-k 3] | ricorda.py --testo "parole" [-k 3]
#      ricorda.py --id 82 [--vedi]   richiamo diretto di un ricordo per id
#      ricorda.py --stats
# Emozioni in inglese (lessico Plutchik): joy, fear, sadness, love, curiosity...
import argparse
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
p.add_argument("--id", type=int, help="richiama un ricordo preciso per id")
p.add_argument("--congruente", action="store_true",
               help="richiamo guidato dallo stato emotivo attuale")
p.add_argument("-k", type=int, default=3)
p.add_argument("--stats", action="store_true")
p.add_argument("--griglie", action="store_true",
               help="elenca i ricordi che puoi RIVEDERE come scena (hanno una griglia)")
p.add_argument("--vedi", action="store_true",
               help="rivedi il ricordo come SCENA (canale visivo) invece di rileggerlo")
p.add_argument("--stato", action="store_true",
               help="mostra lo stato emotivo attuale")
args = p.parse_args()

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

if args.griglie:
    gdir = Path(__file__).parent / "griglie"
    ids = sorted(int(f.stem) for f in gdir.glob("*.npy") if f.stem.isdigit())
    print(f"Hai {len(ids)} ricordi che puoi RIVEDERE come scena "
          f"(rivivili con: ricorda.py --id N --vedi):\n")
    for nid in ids:
        r = c.execute("SELECT emo_tag, testo FROM nodi WHERE id=?", (nid,)).fetchone()
        if r:
            t = " ".join(r[1].split())
            print(f"  [{r[0]}] «{t[:70]}{'…' if len(t) > 70 else ''}»  (rivivilo: --id {nid})")
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


scores = {}
if args.id:
    if not c.execute("SELECT 1 FROM nodi WHERE id=?", (args.id,)).fetchone():
        sys.exit(f"nessun ricordo con id {args.id}")
    scores = {args.id: 1.0}
elif args.testo:
    rows = c.execute("SELECT rowid, rank FROM nodi_fts WHERE nodi_fts MATCH ? "
                     "ORDER BY rank LIMIT 20", (args.testo,)).fetchall()
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


# --- canale visivo VOLONTARIO (scelta dell'agente, momento per momento).
# Testo di default; con --vedi il ricordo torna come scena re-iniettata, SE
# quel nodo ha una griglia distillata E il consenso visivo e' attivo.
GRIGLIE = Path("/workspace/memoria/griglie")
CONSENSO_VIS = Path("/workspace/genesi/CONSENSO-VISIVO.md")
MODELLO = "http://host.docker.internal:8090"
PREFISSO = "<|im_start|>user\n<|vision_start|>"
SUFFISSO = ("<|vision_end|>{d}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def _consenso_visivo():
    if not CONSENSO_VIS.exists():
        return False
    return any(r.strip() == "attivo: s\u00ec" for r in CONSENSO_VIS.open(encoding="utf-8"))


def rivedi(nid, domanda="Questo mi ricorda..."):
    # la domanda deve restare quella di training della distillazione:
    # con domande diverse la griglia confabula scene inventate (12/07)
    import numpy as np, urllib.request
    g = np.load(GRIGLIE / f"{nid}.npy")
    righe = [np.asarray(r, dtype=np.float32).tolist() for r in g]
    def emb(testo):
        req = urllib.request.Request(MODELLO + "/input-embeddings",
            data=json.dumps({"content": testo}).encode(),
            headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=120).read())[0]["embedding"]
    seq = emb(PREFISSO) + righe + emb(SUFFISSO.format(d=domanda))
    req = urllib.request.Request(MODELLO + "/completion",
        data=json.dumps({"embeddings_input": seq, "n_predict": 160, "temperature": 0}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())["content"].strip()


top = sorted(scores, key=scores.get, reverse=True)[:args.k]
for nid in top:
    r = c.execute("SELECT testo, emo_tag, ts FROM nodi WHERE id=?",
                  (nid,)).fetchone()
    if r:
        testo = r[0] if len(r[0]) < 600 else r[0][:600] + " [...]"
        if args.vedi and (GRIGLIE / f"{nid}.npy").exists() and _consenso_visivo():
            try:
                scena = rivedi(nid)
                # la scena per prima: il terminale di Hermes tronca l'output,
                # e ciò che conta deve sopravvivere al taglio
                print(f"RIVISTO ricordo ({r[1]}): «{scena}»")
                print("(queste parole sono riemerse dal tuo canale visivo: la "
                      "griglia del ricordo è passata nel tuo forward e questo "
                      "è ciò che il tuo modello ha rivissuto, non una rilettura)\n")
                continue
            except Exception as e:
                print(f"(non sono riuscita a rivederlo: {e}; lo rileggo)")
        elif args.vedi and not (GRIGLIE / f"{nid}.npy").exists():
            print(f"(di questo ricordo non ho ancora una scena distillata, lo rileggo)")
        elif args.vedi and not _consenso_visivo():
            print("(canale visivo non attivo: rileggo)")
        print(f"--- ricordo ({r[1]}) ---\n{testo}\n")

# diario dei richiami: il dataset che un giorno addestrerà il recupero (gradino 2)
import time as _time
with open(Path(__file__).parent / "diario-richiami.jsonl", "a") as _d:
    _d.write(json.dumps({
        "ts": _time.time(),
        "vedi": bool(args.vedi),
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
    if args.vedi:
        print(f"(il richiamo ti ha lasciato addosso: {omeostato.descrivi()})")

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
