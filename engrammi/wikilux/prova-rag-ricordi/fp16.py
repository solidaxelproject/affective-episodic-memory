"""float16 contro float32 sui vettori del Lux dell'agente (15/10): scarto dei coseni e richiamo sugli stessi indizi."""
import sys, numpy as np
sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi"); sys.path.insert(0, ".")
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import prova as P
L, V32 = P.L, P.L.V.copy()
V16 = V32.astype(np.float16).astype(np.float32)
rng = np.random.default_rng(0); q = V32[rng.choice(len(V32), 2000, replace=False)]
S32, S16 = q @ V32.T, q.astype(np.float16).astype(np.float32) @ V16.T
d = np.abs(S32 - S16)
print(f"coseni confrontati {d.size:,}: scarto medio {d.mean():.1e}, massimo {d.max():.1e}")
print(f"coppie che cambiano lato della soglia 0.8: {((S32 >= .8) != (S16 >= .8)).sum()} su {(S32 >= .8).sum()} sopra soglia")
uguali = tot = 0
for g, qs in P.gruppi.items():
    for testo, _ in qs:
        L.V = V32; a = L.richiama(testo, 3, 0)
        L.V = V16; b = L.richiama(testo, 3, 0)
        tot += 1; uguali += [n for n, _ in a] == [n for n, _ in b]
print(f"richiami con gli stessi primi 3 ricordi nello stesso ordine: {uguali}/{tot}")
