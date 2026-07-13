#!/usr/bin/env python3
# "Ricordati questa cosa" a comando. Stdlib-only (gira nel container).
# NON scrive subito il vettore (serve la GPU): mette il testo in coda; il
# consolidamento notturno (o un flush manuale) lo trasforma in ricordo VERO,
# bypassando la soglia di salienza (il bypass è possibile per comodità:
# ciò che si chiede di ricordare entra comunque). Come per gli umani: si
# decide di ricordare adesso, si consolida nel sonno.
import json
import sys
import time
from pathlib import Path

CODA = Path(__file__).parent / "da-ricordare.jsonl"

if len(sys.argv) < 2 or not sys.argv[1].strip():
    print("uso: ricorda-ora.py \"cosa voglio ricordare\"")
    sys.exit(2)

testo = " ".join(sys.argv[1:]).strip()
with open(CODA, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": time.time(), "testo": testo,
                        "forzato": True}, ensure_ascii=False) + "\n")
n = sum(1 for _ in open(CODA, encoding="utf-8"))
print(f"Segnato da ricordare (#{n} in coda). Diventerà un ricordo pieno al "
      f"prossimo consolidamento notturno, con la sua firma emotiva.")
