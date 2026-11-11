#!/usr/bin/env python3
# Vista d'insieme del cervello di Agente: grafo, Lux, stato emotivo, ultimi richiami.
# CPU, host-side (usa numpy per Lux). Uno sguardo solo su tutto l'organismo.
import json
import sys
import time
from pathlib import Path

MEM = Path("/data/workspace/memoria")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
sys.path.insert(0, str(MEM))

print("=" * 56)
print("  CERVELLO DELL'AGENTE")
print("=" * 56)

# --- ricordi: 1.20.0: dal meta del Lux (prima memoria.db; gli archi hebbiani restano li', in archivio)
sys.path.insert(0, str(Path(__file__).resolve().parent / "engrammi"))
import meta_lux  # noqa: E402

META = Path(meta_lux.percorso())
if META.exists():
    ric = [r for r in json.loads(META.read_text(encoding="utf-8"))["ricordi"].values() if r["classe"] != "correzione"]
    vis = sum(1 for r in ric if r["classe"] == "vissuto")
    let = sum(1 for r in ric if r["classe"] == "letto")
    conta = {}
    for r in ric:
        if r["classe"] == "vissuto":
            conta[r.get("dominante")] = conta.get(r.get("dominante"), 0) + 1
    top = sorted(conta.items(), key=lambda x: -x[1])[:5]
    print(f"\nGRAFO (memoria episodica testuale)")
    print(f"  {len(ric)} nodi: {vis} vissuti, {let} letti")
    print(f"  emozioni: " + ", ".join(f"{e} {q}" for e, q in top))

# --- Lux v0: sezione tolta il 10/11 (il vecchio Lux e' archiviato dal 31/10, la classe in archivio-20261110/lux.py)

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
