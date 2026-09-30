#!/usr/bin/env python3
# GIF della FORMAZIONE della memoria (30/09): i neuroni di Lux nascono in ordine cronologico
# (data del ricordo piu' antico che contengono, da memoria.db: i `nati` di Lux sono quasi tutti del
# rebuild dell'11/07), gli archi compaiono quando esistono entrambi i loro neuroni. Poi un giro completo
# sul grafo finito. Stessa geometria e palette di grafo3d-gif.py: PCA 3D delle tracce di Lux,
# colore = emozione dominante della firma, grandezza = attivazioni. Nessun testo dei ricordi.
# Uso: python grafo3d-formazione-gif.py [out.gif]
import json
import os
import re
import sqlite3
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, MS = 720, 540, 80
F_NASCITA, F_PAUSA, F_GIRO = 150, 10, 60
BG = (11, 14, 26)
MEM = '/data/workspace/memoria'

src = open('/data/memoria-episodica-affettiva/grafo3d.py').read()
COL = json.loads(re.search(r'COL=(\{.*?\})', src).group(1))

z = np.load(f'{MEM}/lux.npz')
meta = json.load(open(f'{MEM}/lux-meta.json'))
ids = [str(u) for u in z['ids']]
riga = {u: i for i, u in enumerate(ids)}
db = sqlite3.connect(f'file:{MEM}/memoria.db?mode=ro', uri=True)
ts_nodo = dict(db.execute('select id, ts from nodi'))
emos = sorted(json.loads(db.execute('select firma from nodi limit 1').fetchone()[0]))
nascita = np.array([min((ts_nodo[n] for n in meta['nodi'].get(u, [int(z['nodo_id'][i])]) if n in ts_nodo),
                        default=float(z['nati'][i])) for i, u in enumerate(ids)])
emo = [emos[int(j)] for j in z['firme'].argmax(1)]
att = z['attivazioni'].astype(float)
archi = []
for k, w in meta['archi'].items():
    a, b = k.split('|')
    if a in riga and b in riga:
        archi.append((riga[a], riga[b], w))

X = z['tracce'].astype(np.float32) - z['tracce'].mean(0)
_, _, Vt = np.linalg.svd(X, full_matrices=False)
P3 = X @ Vt[:3].T
P3 /= np.abs(P3).max()

ordine = np.argsort(nascita)
t0, t1 = nascita.min(), nascita.max()
try:
    FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 15)
except OSError:
    FONT = ImageFont.load_default()


def hexrgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def proietta(ry, rx=-0.4):
    cy, sy, cx, sx = np.cos(ry), np.sin(ry), np.cos(rx), np.sin(rx)
    x = P3[:, 0] * cy + P3[:, 2] * sy
    z1 = -P3[:, 0] * sy + P3[:, 2] * cy
    y = P3[:, 1] * cx - z1 * sx
    zz = P3[:, 1] * sx + z1 * cx
    p = 1 / (1.9 + zz)
    zoom = min(W, H) * 0.58
    SX, SY = x * zoom * p * 1.9, y * zoom * p * 1.9
    return SX - SX.mean() + W / 2, SY - SY.mean() + H / 2, zz, p


def disegna(vivi, eta, ry, adesso):
    SX, SY, zz, p = proietta(ry)
    im = Image.new('RGB', (W, H), BG)
    dr = ImageDraw.Draw(im, 'RGBA')
    n_archi = 0
    for a, b, w in archi:
        if vivi[a] and vivi[b]:
            n_archi += 1
            fresco = min(eta[a], eta[b]) < 6          # arco appena nato: piu' luminoso
            alpha = 200 if fresco else int(255 * min(0.35, 0.08 + w * 0.05))
            dr.line([SX[a], SY[a], SX[b], SY[b]], fill=(150, 170, 230, alpha), width=2 if fresco else 1)
    for i in np.argsort(-zz):
        if not vivi[i]:
            continue
        r = max(1.5, (2.2 + np.log1p(att[i]) * 1.6) * p[i] * 1.9)
        if eta[i] < 6:                                  # nascita: lampo che si restringe
            alone = r * (3.2 - eta[i] * 0.35)
            dr.ellipse([SX[i] - alone, SY[i] - alone, SX[i] + alone, SY[i] + alone],
                       fill=(255, 255, 255, int(110 - eta[i] * 18)))
        c = hexrgb(COL.get(emo[i], '#8ea0c9'))
        dr.ellipse([SX[i] - r, SY[i] - r, SX[i] + r, SY[i] + r], fill=c)
        dr.ellipse([SX[i] - r / 2.2, SY[i] - r / 2.2, SX[i], SY[i]], fill=(255, 255, 255, 90))
    testo = f"{time.strftime('%d/%m/%Y', time.localtime(adesso))}   neuroni {int(vivi.sum())}   archi {n_archi}"
    dr.text((14, H - 26), testo, fill=(200, 210, 235), font=FONT)
    return im.quantize(colors=128, dither=Image.Dither.NONE)


out = sys.argv[1] if len(sys.argv) > 1 else '/data/memoria-episodica-affettiva/memoria-formazione.gif'
frames = []
nati_frame = np.full(len(ids), 10 ** 6)
for k, i in enumerate(ordine):   # i neuroni si distribuiscono sui frame in ordine di nascita
    nati_frame[i] = int(k * F_NASCITA / len(ordine))
for f in range(F_NASCITA + F_PAUSA + F_GIRO):
    ry = 0.6 + 2 * np.pi * f / (F_NASCITA + F_PAUSA + F_GIRO)
    vivi = nati_frame <= f
    eta = f - nati_frame
    adesso = nascita[ordine[min(int(vivi.sum()), len(ordine)) - 1]] if vivi.any() else t0
    frames.append(disegna(vivi, eta, ry, adesso))
frames[0].save(out, save_all=True, append_images=frames[1:], loop=0, duration=MS, optimize=True)
print(f'{out}: {len(ids)} neuroni, {len(archi)} archi, dal {time.strftime("%d/%m", time.localtime(t0))} '
      f'al {time.strftime("%d/%m", time.localtime(t1))}, {len(frames)} frame, {os.path.getsize(out) // 1024} KB')
