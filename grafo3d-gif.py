#!/usr/bin/env python3
# GIF animata del grafo 3D della memoria per il repo pubblico (README).
# Reso STABILE il 23/07: l'originale del 13/07 era un one-off perso.
# Stessa geometria di grafo3d.py (PCA 3D degli addr_sem, colore = emozione,
# anello = scena distillata, archi hebbiani), rotazione completa.
# Contenuto sicuro per il repo: solo sfere/archi/colori, nessun testo.
# Uso: python grafo3d-gif.py [out.gif]
import json
import os
import re
import sqlite3
import sys

import numpy as np
import torch
from PIL import Image, ImageDraw

W, H, FRAMES, MS = 640, 480, 60, 90
BG = (11, 14, 26)

db = sqlite3.connect('/data/workspace/memoria/memoria.db')
v = torch.load('/data/workspace/memoria/vettori.pt', weights_only=True)
GR = '/data/workspace/memoria/griglie'
griglie = {int(f.split('.')[0]) for f in os.listdir(GR)
           if f.endswith('.npy') and f.split('.')[0].isdigit()}
# la palette emozione->colore vive in grafo3d.py (unica fonte): la estraggo da lì
src = open('/data/memoria-episodica-affettiva/grafo3d.py').read()
COL = json.loads(re.search(r'COL=(\{.*?\})', src).group(1))

rows = [r for r in db.execute('select id,emo_tag,salienza from nodi') if r[0] in v]
X = np.stack([v[r[0]]['addr_sem'].numpy() for r in rows]).astype(np.float32)
X -= X.mean(0)
_, _, Vt = np.linalg.svd(X, full_matrices=False)
P3 = X @ Vt[:3].T
P3 /= np.abs(P3).max()
ids = {r[0]: i for i, r in enumerate(rows)}
edges = [(ids[a], ids[b], w) for a, b, w in db.execute('select a,b,w from archi')
         if a in ids and b in ids and a < b]


def hexrgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/memory-graph-3d.gif'
frames = []
rx = -0.4
for f in range(FRAMES):
    ry = 0.6 + 2 * np.pi * f / FRAMES
    cy, sy, cx, sx = np.cos(ry), np.sin(ry), np.cos(rx), np.sin(rx)
    x = P3[:, 0] * cy + P3[:, 2] * sy
    z1 = -P3[:, 0] * sy + P3[:, 2] * cy
    y = P3[:, 1] * cx - z1 * sx
    z = P3[:, 1] * sx + z1 * cx
    p = 1 / (1.9 + z)
    zoom = min(W, H) * 0.58
    SX, SY = x * zoom * p * 1.9, y * zoom * p * 1.9
    SX = SX - SX.mean() + W / 2      # centrato sul baricentro proiettato
    SY = SY - SY.mean() + H / 2

    im = Image.new('RGB', (W, H), BG)
    dr = ImageDraw.Draw(im, 'RGBA')
    for a, b, w in edges:
        alpha = int(255 * min(0.35, 0.06 + w * 0.05))
        dr.line([SX[a], SY[a], SX[b], SY[b]], fill=(120, 140, 200, alpha))
    for i in np.argsort(-z):          # prima i lontani
        nid, emo, sal = rows[i]
        r = max(1.5, (2 + (sal or 0) * 1.6) * p[i] * 1.9)
        c = hexrgb(COL.get(emo, '#8ea0c9'))
        dr.ellipse([SX[i] - r, SY[i] - r, SX[i] + r, SY[i] + r], fill=c)
        dr.ellipse([SX[i] - r / 2.2, SY[i] - r / 2.2, SX[i], SY[i]],
                   fill=(255, 255, 255, 90))          # riflesso in alto a sx
        if nid in griglie:
            dr.ellipse([SX[i] - r - 2, SY[i] - r - 2, SX[i] + r + 2, SY[i] + r + 2],
                       outline=(255, 255, 255, 170), width=1)
    frames.append(im.quantize(colors=128, dither=Image.Dither.NONE))

frames[0].save(out, save_all=True, append_images=frames[1:], loop=0,
               duration=MS, optimize=True)
print(f'{out}: {len(rows)} nodi, {len(edges)} archi, '
      f'{len(griglie)} scene, {os.path.getsize(out) // 1024} KB')
