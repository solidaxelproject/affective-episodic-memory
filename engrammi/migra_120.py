#!/usr/bin/env python3
"""Rollback del Lux 1.20.0 (PIANO-1.20-MEMORIADB-SUPERFLUO.md): i ricordi nati nella 1.20.0 stanno solo nel suo meta;
"indietro" li riporta in memoria.db con id = nid (gli stessi numeri stanno in diario-riflessi, giornata-firma, M e
lux-stato). Prima: `chmod u+w memoria.db` e servizi fermi. Idempotente: un nid gia' nel db non si tocca. vettori.pt no
(nessun lettore dal 1.20.0).
Uso: python3 migra_120.py indietro [cartella del Lux 1.20.0] [memoria.db]"""
import json
import sqlite3
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "indietro":
        sys.exit(__doc__)
    lux = sys.argv[2] if len(sys.argv) > 2 else "/data/memoria-episodica-affettiva/engrammi/lux-1.20.0"
    db = sys.argv[3] if len(sys.argv) > 3 else "/data/workspace/memoria/memoria.db"
    ricordi = json.load(open(f"{lux}/lux-meta.json"))["ricordi"]
    c = sqlite3.connect(db)
    ci = {n for (n,) in c.execute("select id from nodi")}
    nuovi = sorted(int(k) for k, r in ricordi.items() if r["classe"] != "correzione" and int(k) not in ci)
    for n in nuovi:
        r = ricordi[str(n)]
        c.execute("INSERT INTO nodi (id, ts, testo, fonte, emo_tag, emo_alpha, firma, salienza, classe, voluto, cattura)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (n, r["ts"], r["testo"], r.get("fonte"), r.get("dominante"), None,
                   json.dumps(r["firma"], ensure_ascii=False) if r.get("firma") is not None else None,
                   r.get("salienza"), r["classe"], int(r.get("voluto") or 0), r.get("cattura")))
    c.commit()
    print(f"{len(nuovi)} ricordi riportati in {db}: {nuovi[:20]}")
