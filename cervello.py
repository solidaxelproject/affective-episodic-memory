#!/usr/bin/env python3
# Vista d'insieme del cervello di Agente: grafo, Lux, stato emotivo, ultimi richiami.
# CPU, host-side (usa numpy per Lux). Uno sguardo solo su tutto l'organismo.
import json
import sqlite3
import sys
import time
from pathlib import Path

MEM = Path("/data/workspace/memoria")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
sys.path.insert(0, str(MEM))

print("=" * 56)
print("  CERVELLO DELL'AGENTE")
print("=" * 56)

# --- grafo
db = MEM / "memoria.db"
if db.exists():
    c = sqlite3.connect(db)
    n = c.execute("SELECT COUNT(*) FROM nodi").fetchone()[0]
    vis = c.execute("SELECT COUNT(*) FROM nodi WHERE classe='vissuto'").fetchone()[0]
    let = c.execute("SELECT COUNT(*) FROM nodi WHERE classe='letto'").fetchone()[0]
    arc = c.execute("SELECT COUNT(*) FROM archi").fetchone()[0]
    top = c.execute("SELECT emo_tag, COUNT(*) FROM nodi WHERE classe='vissuto' "
                    "GROUP BY emo_tag ORDER BY 2 DESC LIMIT 5").fetchall()
    print(f"\nGRAFO (memoria episodica testuale)")
    print(f"  {n} nodi: {vis} vissuti, {let} letti | {arc} archi hebbiani")
    print(f"  emozioni: " + ", ".join(f"{e} {q}" for e, q in top))
    c.close()

# --- Lux
try:
    from lux import Lux
    lux = Lux()
    st = lux.stats()
    print(f"\nLUX (organo di memoria crescente)")
    print(f"  {st['neuroni']} neuroni | {st['archi']} archi | "
          f"{st['attivazioni_totali']} attivazioni totali")
    if st["neuroni"]:
        import numpy as np
        eta_g = (time.time() - lux.nati) / 86400
        print(f"  più antico: {eta_g.max():.1f} giorni | "
              f"più attivo: neurone {int(lux.attivazioni.argmax())} "
              f"({int(lux.attivazioni.max())} attivazioni)")
except Exception as e:
    print(f"\nLUX: non disponibile ({e})")

# --- stato emotivo
try:
    import stato as omeostato
    print(f"\nSTATO EMOTIVO (omeostato)")
    print(f"  {omeostato.descrivi(6)}")
    esito, motivo = omeostato.gate()
    print(f"  gate: {esito} — {motivo}")
except Exception as e:
    print(f"\nSTATO: non disponibile ({e})")

# --- ultimi richiami
diario = MEM / "diario-richiami.jsonl"
if diario.exists():
    righe = diario.read_text(encoding="utf-8").strip().splitlines()
    print(f"\nULTIMI RICHIAMI ({len(righe)} totali nel diario)")
    for l in righe[-3:]:
        r = json.loads(l)
        print(f"  [{r['modo']}] {r['query']} -> {r['risultati']}")

# --- coda ricorda-ora
coda = MEM / "da-ricordare.jsonl"
if coda.exists():
    n = sum(1 for _ in open(coda, encoding="utf-8"))
    print(f"\nIN ATTESA DI CONSOLIDAMENTO: {n} cose da ricordare (coda ricorda-ora)")

print("=" * 56)
