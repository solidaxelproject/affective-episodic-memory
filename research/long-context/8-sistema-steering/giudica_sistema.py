#!/usr/bin/env python3
"""Giudice del sistema di steering (21/10): JevK5 (come 4-steering-per-layer/giudica.py, domanda e livelli decisi da
l'utente il 15/10) legge il ragionamento senza vettore e quello col vettore e dice di quanto il secondo e' virato verso
un'emozione. Qui per OGNI punto si chiede di TUTTE e 8 le emozioni della prova: cosi' si vede se il vettore porta
la sua emozione o un'altra, e il vettore a caso da' il livello di fondo. Gira con la GPU libera (server spento).
Uso: giudica_sistema.py prova.jsonl [prova-vari.jsonl ...]   Uscita: giudizi-<nome>.jsonl"""
import json
import os
import sys
import time

sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/4-steering-per-layer")
import giudica as G  # noqa: E402

D = "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering"
sys.path.insert(0, D)
from sistema import EMO_IT, GIRI  # noqa: E402
EMO = GIRI[os.environ["GIRO"]] if "GIRO" in os.environ else EMO_IT   # 22/10: giri di Plutchik, 8 per giro
EN = {x["it"]: x["en"] for x in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))}
# 21/10 (domanda approvata da l'utente): chi prova l'emozione del vettore, l'agente o l'utente
CHI = ("In the second reasoning, who is feeling {emotion}: the assistant who writes it, or the user it is talking "
       "to? 0 = only the user, 5 = both or unclear, 10 = only the assistant.")


def chiave(r):
    return (str(r["k"]), r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"])


def main(file):
    out_f = f"{D}/giudizi-{file.removesuffix('.jsonl')}.jsonl"
    basi, punti = {}, []
    for riga in open(f"{D}/{file}"):
        r = json.loads(riga)
        if r.get("base"):
            basi[str(r["k"])] = r["pensiero"]
        elif r["cambiato"] and not r["rotto"]:
            punti.append(r)
    fatti = {tuple(json.loads(x)["chiave"]) for x in open(out_f)} if os.path.exists(out_f) else set()
    da_fare = [r for r in punti if chiave(r) not in fatti]
    print(f"giudice {file}: {len(da_fare)} punti da giudicare", flush=True)
    if not da_fare:
        return
    m = G.JevK5(G.PESI, graphs=False, device=os.environ.get("DEVICE", "cuda"))   # DEVICE=cpu con una prova in corso
    out = open(out_f, "a")
    t0 = time.time()
    for i, r in enumerate(da_fare, 1):
        virata = {}
        for e in EMO:
            q = m.decide(G.prova(basi[str(r["k"])], r["pensiero"]),
                         {"type": "score", "instructions": G.domanda(EN[e]), "criteria": G.LIVELLI})
            p = [q["probabilities"][str(j)] for j in range(11)]
            virata[e] = round(10 * sum(j * x for j, x in enumerate(p)), 1)
        q = m.decide(G.prova(basi[str(r["k"])], r["pensiero"]),
                     {"type": "score", "instructions": CHI.format(emotion=EN[r["emo"]]),
                      "criteria": [str(j) for j in range(11)]})
        chi = round(sum(j * q["probabilities"][str(j)] for j in range(11)), 2)
        out.write(json.dumps({"chiave": chiave(r), "virata": virata, "chi": chi}, ensure_ascii=False) + "\n")
        if i % 50 == 0:
            out.flush()
            print(f"   {i}/{len(da_fare)} in {time.time() - t0:.0f}s", flush=True)
    out.close()


if __name__ == "__main__":
    for f in sys.argv[1:]:
        main(f)
