#!/usr/bin/env python3
"""GIF della formazione del Lux degli engrammi per il README (17/10/2026). Solo lettura di lux-<versione>/.
I ricordi entrano in ordine cronologico (data del nodo in memoria.db): ogni engramma nasce col primo ricordo che lo
contiene, gli archi compaiono col loro ricordo. Poi un giro completo sul Lux finito.
Stessa geometria di lux3d.py (PCA 3D dei vettori bge-m3, colore = emozione principale della firma). Nessun testo:
solo sfere, archi, data e conteggi, quindi pubblicabile.
  /data/jspace/venv/bin/python lux3d-gif.py [out.gif]"""
import json
import re
import sqlite3
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSIONE = "1.12.0"
DIR = f"/data/memoria-episodica-affettiva/engrammi/lux-{VERSIONE}"
DB = "/data/workspace/memoria/memoria.db"
W, H, MS = 640, 480, 90
F_NASCITA, F_PAUSA, F_GIRO = 90, 8, 48
BG = (11, 14, 26)
COL = json.loads(re.search(r"COL=(\{.*?\});", open("/data/memoria-episodica-affettiva/grafo3d.py").read()).group(1))
EMOZIONI = [e["en"] for e in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))]

z = np.load(f"{DIR}/lux.npz")
V, F, A = z["V"].astype(np.float32), z["F"], z["A"]
ts = dict(sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute("select id, ts from nodi"))
quando = {int(r): ts.get(int(r), np.nan) for r in np.unique(A[:, 0])}
t_arco = np.array([quando[int(r)] for r in A[:, 0]])
t_arco[np.isnan(t_arco)] = np.nanmax(t_arco)   # correzioni (fuori da memoria.db): entrano alla fine

nascita = np.full(len(V), np.inf)
for col in (2, 3):
    np.minimum.at(nascita, A[:, col], t_arco)
nascita[np.isinf(nascita)] = np.nanmax(t_arco)
archi = A[:, 2] != A[:, 3]
ea, eb, et = A[archi, 2], A[archi, 3], t_arco[archi]

X = V - V.mean(0)
_, _, Vt = np.linalg.svd(X[::7], full_matrices=False)   # come lux3d.py: PCA su un campione
P3 = X @ Vt[:3].T
P3 /= np.percentile(np.abs(P3), 99.5)
emo = [EMOZIONI[int(np.argmax(f))] if f.any() else "" for f in F]
gradi = np.bincount(np.concatenate([ea, eb]), minlength=len(V))
t0, t1 = nascita.min(), nascita.max()
try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
except OSError:
    FONT = ImageFont.load_default()


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


CR = np.array([hexrgb(COL.get(e, "#8ea0c9")) for e in emo])


def proietta(ry, rx=-0.4):
    cy, sy, cx, sx = np.cos(ry), np.sin(ry), np.cos(rx), np.sin(rx)
    x = P3[:, 0] * cy + P3[:, 2] * sy
    z1 = -P3[:, 0] * sy + P3[:, 2] * cy
    y = P3[:, 1] * cx - z1 * sx
    zz = P3[:, 1] * sx + z1 * cx
    p = 1 / (2.4 + zz)
    zoom = min(W, H) * 0.33 * 2.4
    SX, SY = x * zoom * p, y * zoom * p
    cx, cy = (np.percentile(SX, 1) + np.percentile(SX, 99)) / 2, (np.percentile(SY, 1) + np.percentile(SY, 99)) / 2
    return SX - cx + W / 2, SY - cy + H / 2 - 12, zz, p


def disegna(adesso, ry, data=None):
    lampo = 2.5 * (t1 - t0) / F_NASCITA
    SX, SY, zz, p = proietta(ry)
    vivi = nascita <= adesso
    im = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(im, "RGBA")
    va = et <= adesso
    for a, b, t in zip(ea[va], eb[va], et[va]):
        fresco = adesso - t < lampo
        dr.line([SX[a], SY[a], SX[b], SY[b]], fill=(150, 170, 230, 90 if fresco else 10))
    for i in np.argsort(-zz):
        if not vivi[i]:
            continue
        r = max(0.7, (0.6 + np.log1p(gradi[i]) * 0.45) * p[i] * 2.4)
        if adesso - nascita[i] < lampo:
            alone = r * 2.2
            dr.ellipse([SX[i] - alone, SY[i] - alone, SX[i] + alone, SY[i] + alone], fill=(255, 255, 255, 45))
        dr.ellipse([SX[i] - r, SY[i] - r, SX[i] + r, SY[i] + r], fill=tuple(CR[i]))
    testo = (f"{time.strftime('%d/%m/%Y', time.localtime(data or adesso))}   engrammi {int(vivi.sum())}   "
             f"archi {int(va.sum())}")
    dr.text((14, H - 26), testo, fill=(200, 210, 235), font=FONT)
    return im.quantize(colors=64, dither=Image.Dither.NONE)


out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/lux-engrammi-3d.gif"
frames = []
for f in range(F_NASCITA):
    frames.append(disegna(t0 + (t1 - t0) * (f + 1) / F_NASCITA, 0.6 + 0.6 * f / F_NASCITA))
frames += [frames[-1]] * F_PAUSA
for f in range(F_GIRO):
    frames.append(disegna(t1 + 1e9, 1.2 + 2 * np.pi * f / F_GIRO, t1))
frames[0].save(out, save_all=True, append_images=frames[1:], loop=0, duration=MS, optimize=True)
print(f"{out}: {len(V)} engrammi, {len(ea)} archi, {len(quando)} ricordi, "
      f"{time.strftime('%d/%m/%Y', time.localtime(t0))}-{time.strftime('%d/%m/%Y', time.localtime(t1))}")
