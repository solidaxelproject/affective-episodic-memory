#!/usr/bin/env python3
"""Sentinella anti-amnesia della notturna (B5 01/11, PIANO-FIRMA-ENGRAMMI.md, P6). 1.20.0 (PIANO-1.20, punto 6; prima
controllava memoria.db): ogni nid con esito "nodo" o "trascinato" nel registro di firma-subito (giornata-firma.jsonl) sta
nel Lux degli engrammi in servizio; ogni ricordo (non correzione) del Lux ha testo e firma. Il diario dei riflessi no: i
suoi nid li da' il Lux stesso, e ha quelli dei ricordi tolti apposta (81 e 699, pulizia del 01/11). Esce con 1 e li elenca
se qualcosa manca. Sola lettura, senza spacy."""
import json
import os
import sys

import meta_lux  # noqa: E402

VERSIONE, META = meta_lux.versione(), meta_lux.percorso()
GIORNATA = os.environ.get("GIORNATA_FIRMA", "/data/workspace/memoria/giornata-firma.jsonl")


def voci(p):
    """righe json del file (righe rotte saltate; file assente = nessuna riga)"""
    if not os.path.exists(p):
        return
    for riga in open(p, encoding="utf-8"):
        try:
            v = json.loads(riga)
        except ValueError:
            continue
        if isinstance(v, dict):
            yield v


ricordi = {int(k): r for k, r in json.load(open(META))["ricordi"].items()}
attesi = {int(v["nid"]) for v in voci(GIORNATA) if v.get("esito") in ("nodo", "trascinato") and v.get("nid") is not None}
fuori = sorted(attesi - set(ricordi))
vuoti = sorted(n for n, r in ricordi.items()
               if r["classe"] != "correzione" and not ((r.get("testo") or "").strip() and r.get("firma")))
if fuori or vuoti:
    if fuori:
        print(f"CRITICO: {len(fuori)} ricordi fuori dal Lux {VERSIONE}: {fuori[:20]}")
    if vuoti:
        print(f"CRITICO: {len(vuoti)} ricordi del Lux {VERSIONE} senza testo o firma: {vuoti[:20]}")
    sys.exit(1)
print(f"sentinella: tutti i ricordi nel Lux {VERSIONE} ({len(ricordi)})")
