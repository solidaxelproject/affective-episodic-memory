#!/usr/bin/env python3
"""Fase 1 del piano di refactoring Lux + richiamo (10/10/2026): quanti token mettere in un engramma.
  stati   GPU, con l'agente e llama-35b spenti (lancio manuale): un forward per ricordo vissuto, stati L29 per token
          -> engrammi-stati/<nid>.npz (h float16 [n_tok, 2048], offs [n_tok, 2]); riprende da dove era rimasto
  misura  CPU: per ogni granularita' spezza i ricordi in frammenti e misura
          autoriconoscimento (il frammento ritrova il suo ricordo, come la via semantica del riflesso),
          con_arco (frammenti legati a quelli di un altro ricordo = possibili ramificazioni),
          grado_max (il frammento con piu' archi: un calderone se esplode), bivi (frammenti con archi in un ricordo)
"""
import argparse
import json
import os
import re
import sqlite3
import sys

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva")
DB = "/data/workspace/memoria/memoria.db"
SIDECAR = "/data/workspace/memoria/addr-sem.npz"
DIR = "/data/memoria-episodica-affettiva/engrammi/stati"
OUT = "/data/memoria-episodica-affettiva/engrammi/misura-archi.json"
MAX_TOK = 1024   # ponytail: dei ricordi oltre ~4000 caratteri si legge solo la testa; alzare se servono interi
GRANULARITA = ["frase", "frase60", "tok16", "tok32", "tok64", "intero"]
TAGLIO = re.compile(r"[.!?\n]+\s*")


def spezza(testo, offs, g):
    """frammenti come intervalli di token [a, b); il token 0 (pozzo dell'attenzione) resta fuori, come in tagging35b"""
    n = len(offs)
    if n < 2:
        return []
    if g == "intero":
        return [(1, n)]
    if g.startswith("tok"):
        k = int(g[3:])
        return [(a, min(a + k, n)) for a in range(1, n, k)]
    tagli, cur = [], 0
    for m in TAGLIO.finditer(testo):
        if g == "frase" or m.end() - cur >= 60:   # frase60 = come _segmenta del riflesso, senza tetto
            tagli.append(m.end())
            cur = m.end()
    tagli.append(len(testo))
    spans, a = [], 1
    for t in tagli:
        b = a
        while b < n and offs[b][1] <= t:          # il token appartiene al pezzo in cui finisce
            b += 1
        if b > a:
            spans.append((a, b))
        a = b
    if a < n:
        spans.append((a, n))
    return spans


def archi(V, mem, soglia, k):
    """niente fusione (regola del 15/07: simili ma distinti si collegano, non si fondono): ogni frammento
    si lega ai suoi k piu' simili di ricordi DIVERSI con coseno >= soglia -> {(i, j)} con i < j.
    ponytail: matrice piena N x N, regge fino a ~20k frammenti; oltre, ricerca per vicini (hnswlib)"""
    S = V @ V.T
    S[mem[:, None] == mem[None, :]] = -1
    out = set()
    for i, row in enumerate(S):
        for j in np.argsort(-row)[:k]:
            if row[j] >= soglia:
                out.add((min(i, j), max(i, j)))
    return out


def ricordi():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    return c.execute("SELECT id, testo FROM nodi WHERE classe='vissuto' ORDER BY id").fetchall()


def cmd_stati(_):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    sys.path[:0] = ["/data/jspace", "/data/jspace/jacobian-lens"]
    import torch
    import mixed35b as M
    import ponte
    from jlens.hooks import ActivationRecorder
    os.makedirs(DIR, exist_ok=True)
    s = M.load()
    tok = s["model"].tokenizer
    for nid, testo in ricordi():
        f = f"{DIR}/{nid}.npz"
        if os.path.exists(f):
            continue
        e = tok(testo, add_special_tokens=False, return_offsets_mapping=True, truncation=True, max_length=MAX_TOK)
        ids = torch.tensor([e.input_ids], device=s["model"].input_device)
        with torch.no_grad(), ActivationRecorder(s["model"].layers, at=[ponte.LAYER_SONDA]) as rec:
            s["model"].forward(ids)
        h = rec.activations[ponte.LAYER_SONDA][0].float().cpu().numpy().astype(np.float16)
        np.savez(f + ".tmp.npz", h=h, offs=np.array(e.offset_mapping, np.int32))
        os.replace(f + ".tmp.npz", f)
        print(nid, len(e.input_ids), flush=True)


def cmd_misura(a):
    import ponte
    base = ponte.base_lente()
    sc = np.load(SIDECAR)
    M, ids_M = sc["M"], sc["ids"]
    testi = dict(ricordi())
    dati = {}
    for nid in testi:
        f = f"{DIR}/{nid}.npz"
        if os.path.exists(f):
            z = np.load(f)
            dati[nid] = (z["h"], z["offs"])
    print(f"{len(dati)}/{len(testi)} ricordi con gli stati", flush=True)
    esiti = {}
    for g in GRANULARITA:
        V, mem, lung, seqi = [], [], [], {}
        for nid, (h, offs) in dati.items():
            spans = spezza(testi[nid], offs, g)
            if not spans:
                continue
            v = ponte.trasporta(np.stack([h[x:y].astype(np.float32).mean(0) for x, y in spans])) - base
            v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
            seqi[nid] = list(range(len(mem), len(mem) + len(spans)))
            V.append(v)
            mem += [nid] * len(spans)
            lung += [y - x for x, y in spans]
        V, mem = np.concatenate(V), np.array(mem)
        A = archi(V, mem, a.soglia, a.k)
        grado = np.zeros(len(V), int)
        for i, j in A:
            grado[i] += 1
            grado[j] += 1
        bivi = [int((grado[s] > 0).sum()) for s in seqi.values()]
        esiti[g] = {"frammenti": len(V), "token_medi": round(float(np.mean(lung)), 1),
                    "autoriconoscimento": round(float((ids_M[(V @ M.T).argmax(1)] == mem).mean()), 3),
                    "con_arco": round(float((grado > 0).mean()), 3),
                    "grado_max": int(grado.max()),
                    "bivi_mediana": float(np.median(bivi)),
                    "ricordi_senza_bivi": round(float(np.mean([b == 0 for b in bivi])), 3)}
        print(g, json.dumps(esiti[g]), flush=True)
    json.dump({"soglia_arco": a.soglia, "k": a.k, "ricordi": len(dati), "esiti": esiti}, open(OUT, "w"), indent=1)
    print(f"| granularita' | frammenti | token medi | autoriconoscimento | con arco | grado max | bivi (mediana) | ricordi senza bivi |\n|---|---|---|---|---|---|---|---|")
    for g, e in esiti.items():
        print(f"| {g} | " + " | ".join(str(x) for x in e.values()) + " |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stati")
    m = sub.add_parser("misura")
    m.add_argument("--soglia", type=float, default=0.65, help="coseno minimo per un arco di somiglianza")
    m.add_argument("--k", type=int, default=3, help="archi al massimo per frammento, verso altri ricordi")
    a = ap.parse_args()
    {"stati": cmd_stati, "misura": cmd_misura}[a.cmd](a)
