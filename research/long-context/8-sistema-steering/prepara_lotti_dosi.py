#!/usr/bin/env python3
"""Lotti ciechi per il giudice Opus della taratura delle dosi (24/10), come giudizio-opus/ del 24/10.
Uso: prepara_lotti_dosi.py emozione [emozione...]  -> giudizio-dosi/lotti/lotto-<emo>-NNN.json per i testi cambiati
di quelle emozioni non ancora in mappa.json (n continua da dove era). Stampa i nomi dei lotti nuovi."""
import json
import os
import random
import sys

D = os.path.dirname(os.path.abspath(__file__))
G = f"{D}/giudizio-dosi"
PROVE = [f"{D}/prova-dosi-medio.jsonl", f"{D}/prova-dosi-fini.jsonl", f"{D}/prova-dosi-giri.jsonl"]


def chiave(r):
    return "|".join(map(str, (r["k"], r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"])))


def main(emozioni):
    os.makedirs(f"{G}/lotti", exist_ok=True)
    os.makedirs(f"{G}/uscite", exist_ok=True)
    mappa = json.load(open(f"{G}/mappa.json")) if os.path.exists(f"{G}/mappa.json") else {}
    fatte = set(mappa.values())
    n = max(map(int, mappa), default=0)
    basi, per_k = {}, {}
    for f in PROVE:
        if not os.path.exists(f):
            continue
        for x in open(f):
            if not x.endswith("\n"):
                continue
            r = json.loads(x)
            if r.get("base"):
                basi.setdefault(r["k"], r)
            elif r["emo"] in emozioni and r["cambiato"] and chiave(r) not in fatte:
                fatte.add(chiave(r))
                per_k.setdefault(r["k"], []).append(r)
    tc = lambda s: "<tool_call>" in s or "<function" in s
    random.seed(n)
    nuovi = []
    for k, lst in sorted(per_k.items()):
        random.shuffle(lst)
        for i in range(0, len(lst), 100):
            n_lotto = sum(1 for x in os.listdir(f"{G}/lotti"))
            nome = f"{n_lotto:03d}"
            testi = []
            for r in lst[i:i + 100]:
                n += 1
                mappa[str(n)] = chiave(r)
                testi.append({"n": n, "emozione_bersaglio": r["emo"], "ragionamento": r["pensiero"],
                              "inizio_risposta": r["coda"]})
            b = basi[k]
            json.dump({"contesto": k, "base": {"ragionamento": b["pensiero"], "inizio_risposta": b["coda"],
                                               "chiama_tool": tc(b["pensiero"] + b["coda"])}, "testi": testi},
                      open(f"{G}/lotti/lotto-{nome}.json", "w"), ensure_ascii=False, indent=0)
            nuovi.append(nome)
    json.dump(mappa, open(f"{G}/mappa.json.tmp", "w"))
    os.replace(f"{G}/mappa.json.tmp", f"{G}/mappa.json")
    print(json.dumps(nuovi))


if __name__ == "__main__":
    main(sys.argv[1:])
