#!/usr/bin/env python3
"""Prova della selezione dei ricordi di B6 senzall'agente (l'utente 01/11 sera): la chat vera (chat-completa-0111.jsonl, fino al
24/10) rigiocata in ordine attraverso firma_subito, firma vera dal server di prova 8098 (stesso GGUF dell'agente), su COPIE
di memoria.db, vettori.pt e del Lux. Alla fine: quanti nodi, trascinati, scartati, corti, doppioni, per giorno.
Uso: cd /data/memoria-episodica-affettiva/engrammi && nice -n 10 /data/jspace/venv/bin/python prova_selezione.py"""
import collections
import json
import os
import shutil
import sys
import time
from pathlib import Path

QUI = os.path.dirname(os.path.abspath(__file__))
OUT = f"{QUI}/prova-selezione"
TMP = f"{OUT}/copia"
if os.path.exists(TMP):
    shutil.rmtree(TMP)
os.makedirs(f"{TMP}/mem")
shutil.copy2("/data/workspace/memoria/memoria.db", f"{TMP}/mem/memoria.db")
shutil.copy2("/data/workspace/memoria/vettori.pt", f"{TMP}/mem/vettori.pt")
shutil.copytree(f"{QUI}/lux-1.13.0", f"{TMP}/lux")
os.environ.update(MEM_SAM=f"{TMP}/mem", LUX_DIR=f"{TMP}/lux", URL_FIRMA="http://127.0.0.1:8098",
                  MARKER_NOTTE=f"{TMP}/nessun-marker")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import firma_subito as FS  # noqa: E402
import memoria  # noqa: E402

memoria.DB, memoria.VEC = Path(f"{TMP}/mem/memoria.db"), Path(f"{TMP}/mem/vettori.pt")
chat = sorted((json.loads(r) for r in open("/data/memoria-episodica-affettiva/firme-occamy/chat-completa-0111.jsonl", encoding="utf-8")
               if r.strip()), key=lambda m: m["ts"])
FS.accoda([{"ts": m["ts"], "autore": m.get("autore", ""), "testo": m["testo"]} for m in chat])
FS.log.info("PROVA: %d messaggi in coda, soglia %.3f", len(chat), FS.stats()["s"]["soglia"])
t0 = time.time()
while FS._pos() < os.path.getsize(FS.CODA):
    st = FS.passo()
    if st != "pronto":
        FS.log.info("STATO %s", st)
        time.sleep(10)
FS.passo()   # l'ultimo giro mette nel Lux i nodi rimasti
durata = time.time() - t0
reg = list(FS.registro().values())
giorni = collections.defaultdict(collections.Counter)
for v in reg:
    giorni[time.strftime("%Y-%m-%d", time.localtime(v["ts"]))][v["esito"]] += 1
tot = collections.Counter(v["esito"] for v in reg)
firmati = tot["nodo"] + tot["trascinato"] + tot["scartato"]
res = {"messaggi": len(chat), "esiti": dict(tot), "firmati": firmati,
       "quota_nodi": tot["nodo"] / max(firmati, 1), "quota_ricordi": (tot["nodo"] + tot["trascinato"]) / max(firmati, 1),
       "forzati": sum(1 for v in reg if v.get("forzato")), "durata_s": durata, "s_a_firma": durata / max(firmati, 1),
       "per_giorno": {g: dict(c) for g, c in sorted(giorni.items())}}
json.dump(res, open(f"{OUT}/risultato.json", "w"), ensure_ascii=False, indent=1)
FS.log.info("PROVA-COMPLETA: %s", json.dumps({k: v for k, v in res.items() if k != "per_giorno"}, ensure_ascii=False))
