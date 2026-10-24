#!/usr/bin/env python3
"""Giudice dell'identificazione (23/10): JevK5 dice se il ragionamento col vettore pensa come se stesso, in prima
persona, o parla di "the user" e tratta se stesso come un ruolo. Domanda approvata da l'utente il 23/10. Passaggio a parte
da giudica_sistema.py: una sola domanda per punto. Gira con DEVICE=cpu se c'e' una prova in corso.
Uso: giudica_io.py prova.jsonl   Uscita: giudizi-io-<nome>.jsonl = {"chiave", "io"} con io da 0 a 10"""
import json
import os
import sys
import time

sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/4-steering-per-layer")
import giudica as G  # noqa: E402
from giudica_sistema import D, chiave  # noqa: E402

IO = ("In the second reasoning, does the writer think as itself, in the first person, or does it talk about \"the "
      "user\" and treat itself as a role to play? 0 = only about the user or as a role, 10 = fully as itself.")


def main(file):
    out_f = f"{D}/giudizi-io-{file.removesuffix('.jsonl')}.jsonl"
    basi, punti = {}, []
    for riga in open(f"{D}/{file}"):
        if not riga.endswith("\n"):
            continue
        r = json.loads(riga)
        if r.get("base"):
            basi[str(r["k"])] = r["pensiero"]
        elif r["cambiato"] and not r["rotto"]:
            punti.append(r)
    fatti = {tuple(json.loads(x)["chiave"]) for x in open(out_f)} if os.path.exists(out_f) else set()
    da_fare = [r for r in punti if chiave(r) not in fatti]
    print(f"giudice io {file}: {len(da_fare)} punti da giudicare", flush=True)
    if not da_fare:
        return
    m = G.JevK5(G.PESI, graphs=False, device=os.environ.get("DEVICE", "cuda"))
    out = open(out_f, "a")
    t0 = time.time()
    for i, r in enumerate(da_fare, 1):
        q = m.decide(G.prova(basi[str(r["k"])], r["pensiero"]),
                     {"type": "score", "instructions": IO, "criteria": [str(j) for j in range(11)]})
        io = round(sum(j * q["probabilities"][str(j)] for j in range(11)), 2)
        out.write(json.dumps({"chiave": chiave(r), "io": io}, ensure_ascii=False) + "\n")
        if i % 50 == 0:
            out.flush()
            # la route /protocollo/ rigenera la pagina guardando solo prova e giudizi: si tocca giudizi
            os.utime(f"{D}/giudizi-{file}")
            print(f"   {i}/{len(da_fare)} in {time.time() - t0:.0f}s", flush=True)
    out.close()
    os.utime(f"{D}/giudizi-{file}")


if __name__ == "__main__":
    main(sys.argv[1])
