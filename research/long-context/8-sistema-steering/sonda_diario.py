#!/usr/bin/env python3
"""Sistema di steering (21/10, l'utente "trova il sistema"): passo 1, sul solo processore.
Su quali layer L15-L32 l'emozione si legge dallo stato interno quando la parola NON c'e' (testi del diario,
5-vettori-italiani/stati-diario.npy, gia' calcolati il 12/10)? Sonda lineare a 51 classi (LDA con shrinkage),
5 fold per registro alternato. Uscita: sonda-diario.json (accuratezza e rango medio per layer)."""
import json

import numpy as np

D = "/data/memoria-episodica-affettiva/research/long-context"
S = np.load(f"{D}/5-vettori-italiani/stati-diario.npy", mmap_mode="r")
idx = json.load(open(f"{D}/5-vettori-italiani/indice-diario.json"))
NOMI = sorted({x["emozione"] for x in idx})
y = np.array([NOMI.index(x["emozione"]) for x in idx])
rng = np.random.default_rng(0)
fold = rng.integers(0, 5, len(y))
out = {}
for li, l in enumerate(range(15, 33)):
    X = np.asarray(S[:, li, :], np.float32)
    X = X - X.mean(0)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    acc, rango = [], []
    for f in range(5):
        tr, te = fold != f, fold == f
        mu = np.stack([X[tr & (y == c)].mean(0) for c in range(len(NOMI))])
        R = X[tr] - mu[y[tr]]
        C = R.T @ R / len(R)
        C = 0.9 * C + 0.1 * np.trace(C) / C.shape[0] * np.eye(C.shape[0])
        W = np.linalg.solve(C, mu.T)                     # 2048 x 51
        b = -0.5 * np.einsum("cd,dc->c", mu, W)
        s = X[te] @ W + b
        acc.append((s.argmax(1) == y[te]).mean())
        rango.append(((s > s[np.arange(len(s)), y[te]][:, None]).sum(1) + 1).mean())
    out[l] = {"acc": float(np.mean(acc)), "rango": float(np.mean(rango))}
    print(f"L{l}: accuratezza {out[l]['acc']:.3f} (a caso {1 / len(NOMI):.3f}), rango medio {out[l]['rango']:.1f}", flush=True)
json.dump(out, open("sonda-diario.json", "w"), indent=1)
