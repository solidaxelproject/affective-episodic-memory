"""controllo della sonda: allena su un registro del diario (io-io) e prova sull'altro (io-tu)"""
import json
import numpy as np
D = "/data/memoria-episodica-affettiva/research/long-context"
S = np.load(f"{D}/5-vettori-italiani/stati-diario.npy", mmap_mode="r")
idx = json.load(open(f"{D}/5-vettori-italiani/indice-diario.json"))
NOMI = sorted({x["emozione"] for x in idx})
y = np.array([NOMI.index(x["emozione"]) for x in idx])
reg = np.array([x["registro"] for x in idx])
print({r: int((reg == r).sum()) for r in set(reg)})
a, b = sorted(set(reg))
for li, l in [(0, 15), (6, 21), (9, 24), (14, 29), (17, 32)]:
    X = np.asarray(S[:, li, :], np.float32); X -= X.mean(0); X /= np.linalg.norm(X, axis=1, keepdims=True)
    for tr, te in ((reg == a, reg == b), (reg == b, reg == a)):
        mu = np.stack([X[tr & (y == c)].mean(0) for c in range(len(NOMI))])
        R = X[tr] - mu[y[tr]]; C = R.T @ R / len(R); C = 0.9 * C + 0.1 * np.trace(C) / len(C) * np.eye(len(C))
        W = np.linalg.solve(C, mu.T); s = X[te] @ W - 0.5 * np.einsum("cd,dc->c", mu, W)
        r = (s > s[np.arange(len(s)), y[te]][:, None]).sum(1) + 1
        print(f"L{l} {'io-io->io-tu' if tr[0] == (reg[0] == a) else 'inverso'}: acc {(r == 1).mean():.3f} top5 {(r <= 5).mean():.3f} rango {r.mean():.1f}", flush=True)
