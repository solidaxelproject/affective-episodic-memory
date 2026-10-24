"""salienza (15/10): riferimento a se' e novita' per ogni ricordo dell'agente, fra 0 e 1. Sola lettura.
se' = coseno massimo fra le frasi del ricordo e le 12 frasi di riferimento (dai ricordi dell'agente, approvate da l'utente);
novita' = 1 - somiglianza col ricordo piu' simile fra quelli arrivati prima (media sulle frasi del coseno migliore).
Entrambe riportate fra 0 e 1 come rango sulla distribuzione (i 12 ricordi delle frasi fuori dalla taratura del se')."""
import json, os, re, sqlite3, sys, numpy as np
sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
import lux_engrammi as X
# le 12 frasi stanno in riferimenti.json (testi di ricordi: privati, fuori dal repo pubblico)
RIF = {int(k): v for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "riferimenti.json"))).items()}
c = sqlite3.connect(f"file:{X.T.DB}?mode=ro", uri=True)
righe = c.execute("select id, ts, testo from nodi where testo != '' order by ts").fetchall()
frasi, di = [], []
for k, (i, ts, t) in enumerate(righe):
    fr = [s.strip(" *-#>|") for s in re.split(r"(?<=[.!?])\s+|\n+", t)]
    fr = [s for s in fr if len(s) >= 15] or [t.strip()[:500]]
    frasi += fr; di += [k] * len(fr)
di = np.array(di)
print(f"{len(righe)} ricordi, {len(frasi)} frasi", flush=True)
import os
if os.path.exists("frasi-V.npy"):
    F = np.load("frasi-V.npy")
else:
    F = X.embed(frasi); np.save("frasi-V.npy", F)
R = X.embed(list(RIF.values()))
rango = lambda v, base: np.array([(base < x).mean() + 0.5 * (base == x).mean() for x in v])
# se'
cs = F @ R.T
se_raw = np.array([cs[di == k].max() for k in range(len(righe))])
ids = np.array([r[0] for r in righe]); fuori = np.isin(ids, list(RIF))
se = rango(se_raw, se_raw[~fuori])
# novita' come distintivita' (15/10): somiglianza col ricordo piu' simile fra TUTTI gli altri, non solo quelli
# arrivati prima (i primi arrivati sembravano nuovi per forza); rango dentro la stessa classe di lunghezza in frasi
# (1, 2-3, 4-8, 9+), cosi' un messaggio di una riga non risulta distintivo solo perche' corto
n = len(righe)
nf = np.bincount(di, minlength=n)
nov_raw = np.ones(n)
for k in range(n):
    S = F[di == k] @ F.T
    best = np.full((S.shape[0], n), -1.0)
    np.maximum.at(best.T, di, S.T)
    best[:, k] = -1.0
    nov_raw[k] = 1 - best.mean(0).max()
classe = np.digitize(nf, [2, 4, 9])
nov = np.zeros(n)
for c in range(4):
    sel = classe == c
    nov[sel] = rango(nov_raw[sel], nov_raw[sel])
out = {int(i): {"se": round(float(a), 3), "se_cos": round(float(b), 3), "novita": round(float(n), 3), "novita_raw": round(float(m), 3), "frasi": int(f),
               "inizio": t[:110].replace("\n", " ")} for (i, ts, t), a, b, n, m, f in zip(righe, se, se_raw, nov, nov_raw, nf)}
json.dump(out, open("passi.json", "w"), ensure_ascii=False, indent=1)
print(f"correlazione se'-novita': {np.corrcoef(se, nov)[0, 1]:.2f}")
for k, raw in (("se", "se_cos"), ("novita", "novita")):
    o = sorted(((i, v) for i, v in out.items() if not (k == "se" and i in RIF)), key=lambda x: (-x[1][raw], -x[1]["novita_raw"]))
    print(f"\n== {k}: i 5 piu' alti"); [print(f"  {i:4} {v[raw]:.3f} ({v['frasi']} frasi)  {v['inizio']!r}") for i, v in o[:5]]
    print(f"== {k}: i 5 piu' bassi"); [print(f"  {i:4} {v[raw]:.3f} ({v['frasi']} frasi)  {v['inizio']!r}") for i, v in o[-5:]]
