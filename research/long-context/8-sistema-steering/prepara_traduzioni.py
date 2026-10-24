#!/usr/bin/env python3
"""Lotti dei testi delle prove ancora da tradurre (22/10: ogni risultato di steering col testo in italiano).
Scrive traduzioni/lotto-<n>.json = [{"id", "testo"}] coi testi inglesi (primi 600 caratteri, come la pagina) che non
hanno ancora un traduzioni/*-it.json; i testi gia' in italiano si saltano. Li traducono agenti Haiku, che scrivono
traduzioni/lotto-<n>-it.json = [{"id", "it"}]; pagina_protocollo.py li legge.
Uso: prepara_traduzioni.py [testi per lotto, default 100]"""
import json
import os
import re
import sys

from pagina_protocollo import D, chiave, righe

T = f"{D}/traduzioni"
ITALIANO = re.compile(r"\b(che|non|sono|della|perché|questo|per|il|di|una|mi|ho)\b", re.I)

os.makedirs(T, exist_ok=True)
fatti = {t["id"] for f in os.listdir(T) if f.endswith("-it.json") for t in json.load(open(f"{T}/{f}"))}
in_coda = {t["id"] for f in os.listdir(T) if f.startswith("lotto-") and not f.endswith("-it.json")
           and not os.path.exists(f"{T}/{f[:-5]}-it.json") for t in json.load(open(f"{T}/{f}"))}
da_fare, visti = [], set()
for r in righe(f"{D}/prova-frase.jsonl"):
    if r.get("base"):
        continue
    k, testo = chiave(r), r["pensiero"][:600]
    if k in fatti or k in in_coda or k in visti or not testo.strip():
        continue
    if len(ITALIANO.findall(testo)) / len(testo.split()) > 0.08:
        continue
    visti.add(k)
    da_fare.append({"id": k, "testo": testo})
n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
primo = 1 + max([int(f.split("-")[1].split(".")[0]) for f in os.listdir(T) if f.startswith("lotto-")] or [0])
for i in range(0, len(da_fare), n):
    with open(f"{T}/lotto-{primo + i // n:03d}.json", "w") as f:
        json.dump(da_fare[i:i + n], f, ensure_ascii=False)
print(f"{len(da_fare)} testi in {(len(da_fare) + n - 1) // n} lotti da lotto-{primo:03d}")
