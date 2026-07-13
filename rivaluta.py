#!/usr/bin/env python3
# Rivalutazione retroattiva (riconsolidamento) — issue #1 del repo.
# Quando una decisione si rivela sbagliata (revert, fallimento), il ricordo
# della decisione viene ri-etichettato con l'affetto dell'esito e collegato
# ad esso da un arco CAUSALE (direzionale, tipo='causale').
# SOLO stdlib: gira anche nel container di Sam.
#
# Uso: rivaluta.py --decisione ID --esito ID          (l'esito ri-tinge la decisione)
#      rivaluta.py --decisione ID --perche "testo"    (senza nodo esito: solo nota)
#      rivaluta.py --lista                             (rivalutazioni fatte)
import argparse
import json
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent / "memoria.db"
DIARIO = Path(__file__).parent / "diario-rivalutazioni.jsonl"
PESO_ESITO = 0.6        # quanto l'affetto dell'esito ri-tinge la decisione
BONUS_SALIENZA = 1.5    # una scottatura DEVE pesare di più nel richiamo

p = argparse.ArgumentParser()
p.add_argument("--decisione", type=int)
p.add_argument("--esito", type=int)
p.add_argument("--perche", help="motivo testuale se non c'è un nodo esito")
p.add_argument("--lista", action="store_true")
args = p.parse_args()

c = sqlite3.connect(DB)
c.execute("PRAGMA busy_timeout=5000")

if args.lista:
    if DIARIO.exists():
        for r in open(DIARIO, encoding="utf-8"):
            e = json.loads(r)
            print(f"{time.strftime('%d/%m %H:%M', time.localtime(e['ts']))} "
                  f"decisione {e['decisione']} <- esito {e.get('esito', '-')} "
                  f"({(e.get('perche') or '')[:60]})")
    else:
        print("nessuna rivalutazione ancora")
    raise SystemExit

if not args.decisione:
    p.error("serve --decisione (con --esito o --perche)")

dec = c.execute("SELECT firma, salienza, emo_tag FROM nodi WHERE id=?",
                (args.decisione,)).fetchone()
if not dec:
    raise SystemExit(f"nessun nodo {args.decisione}")
firma_dec = json.loads(dec[0])

if args.esito:
    es = c.execute("SELECT firma, emo_tag FROM nodi WHERE id=?", (args.esito,)).fetchone()
    if not es:
        raise SystemExit(f"nessun nodo esito {args.esito}")
    firma_es = json.loads(es[0])
    # riconsolidamento: la firma della decisione si sposta verso quella dell'esito
    nuova = {k: round((1 - PESO_ESITO) * firma_dec[k] + PESO_ESITO * firma_es.get(k, 0), 4)
             for k in firma_dec}
    nuovo_tag = max(nuova, key=lambda k: abs(nuova[k]))
    c.execute("UPDATE nodi SET firma=?, emo_tag=?, salienza=salienza+? WHERE id=?",
              (json.dumps(nuova), nuovo_tag, BONUS_SALIENZA, args.decisione))
    # arco CAUSALE direzionale: la decisione ha prodotto l'esito
    c.execute("INSERT INTO archi (a,b,w,tipo) VALUES (?,?,1.0,'causale') "
              "ON CONFLICT(a,b) DO UPDATE SET w=w+1.0, tipo='causale'",
              (args.decisione, args.esito))
    print(f"decisione {args.decisione}: firma ri-tinta dall'esito {args.esito} "
          f"(emo {dec[2]} -> {nuovo_tag}), salienza +{BONUS_SALIENZA}, arco causale creato")
else:
    # niente nodo esito: solo il bonus di salienza e la nota a diario
    c.execute("UPDATE nodi SET salienza=salienza+? WHERE id=?",
              (BONUS_SALIENZA, args.decisione))
    print(f"decisione {args.decisione}: salienza +{BONUS_SALIENZA} ({args.perche or 'senza motivo'})")

c.commit()
with open(DIARIO, "a", encoding="utf-8") as d:
    d.write(json.dumps({"ts": time.time(), "decisione": args.decisione,
                        "esito": args.esito, "perche": args.perche},
                       ensure_ascii=False) + "\n")
