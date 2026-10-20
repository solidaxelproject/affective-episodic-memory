#!/usr/bin/env python3
"""Grafo 3D interattivo del Lux degli engrammi nel browser (11/10/2026). Solo lettura di lux-<versione>/, niente scritture.
  /data/venv-spacy/bin/python lux3d.py      poi apri http://127.0.0.1:8131
Posizioni = PCA 3D dei vettori bge-m3 degli engrammi (vicini = senso simile); colore = emozione principale della firma.
/cerca?q=parola -> gli engrammi piu' vicini (stesso testo + coseno bge-m3 da :8094).
/richiama?q=frase -> i 3 ricordi vincenti ricomposti (Lux.richiama); /ricordo?id=N -> il ricordo N ricomposto.
ponytail: server della libreria standard, solo 127.0.0.1 (dentro ci sono i ricordi dell'agente); da fuori passa dalla
pagina della notturna (:8095/lux3d/, pulsante Lux in 3D). Unit: lux3d.service"""
import gzip
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import lux_engrammi as X

PORTA = 8131
L = X.Lux()
_firma = [None]
COL = {e["en"]: e["colore"] for e in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))}   # palette emozione -> colore


def dati():
    V = L.V.astype(np.float32)   # 1.7.0: i vettori del Lux sono float16, linalg vuole float32
    V = V - V.mean(0)
    _, _, Vt = np.linalg.svd(V[::7], full_matrices=False)   # ponytail: PCA su un campione, basta per 3 assi
    P = V @ Vt[:3].T
    P = P / P.std(0) * 120
    emo = [X.EMOZIONI[int(np.argmax(f))] if f.any() else "" for f in L.F]
    ricordi_di = {}
    for a, b, r in L.A[:, [2, 3, 0]]:
        for v in (a, b):
            ricordi_di.setdefault(int(v), set()).add(int(r))
    archi, fa = [], L.facilita_archi()
    for j, (r, pos, a, b, p0, n) in enumerate(L.A.tolist()):
        if a == b:
            continue
        par = "".join("{%s}" % mostra_par(int(p)) for p in L.P[p0:p0 + n])
        archi.append([a, b, r, pos, par, round(float(fa[j]), 3)])
    return {"pos": np.round(P, 1).tolist(), "testi": L.testi, "emo": emo, "col": COL,
            "ricordi": [sorted(ricordi_di.get(i, ())) for i in range(len(L.testi))], "archi": archi}


def mostra_par(pid):
    t = X.param_testo(pid, L.altri)
    p = X.T.parametro(t)
    return f"{p[0]}{p[1] or ''}" if p else t


def cerca(q, quanti=20):
    q = q.strip()
    if not q:
        return []
    s = X.coseni(X.embed([q]), L.V)[0]
    k = X.chiave(q)
    for i, t in enumerate(L.testi):   # stesso testo o parola contenuta: in cima
        if X.chiave(t) == k:
            s[i] = 2.0
        elif re.search(r"\b" + re.escape(k) + r"\b", X.chiave(t)):
            s[i] = max(s[i], 1.0 + s[i] / 10)
    top = np.argsort(-s)[:quanti]
    return [[int(i), round(float(s[i]), 3)] for i in top]


def aggiorna():
    """12/10: si ricarica quando la notturna aggiunge ricordi (lux-meta.json) o il riflesso rinforza archi
    (lux-stato.npz): la pagina mostra sempre il Lux vivo"""
    global L, DATI, DATI_GZ
    f = tuple(os.path.getmtime(p) if os.path.exists(p) else 0 for p in (X.META, X.STATO))
    if f != _firma[0]:
        if _firma[0] is not None:
            L = X.Lux()
        DATI, _firma[0] = json.dumps(dati(), ensure_ascii=False).encode(), f
        DATI_GZ = gzip.compress(DATI, 6)   # 20/10: dal cellulare 2,8 MB -> ~0,6 MB, la pagina lo scompatta


aggiorna()
PAGINA = open(__file__.replace(".py", ".html"), "rb").read()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        aggiorna()
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            corpo, tipo = PAGINA.replace(b"__SOGLIA__", str(X.SOGLIA_RICHIAMO).encode()).replace(b"__VERSIONE__", X.VERSIONE.encode()), "text/html; charset=utf-8"
        elif u.path == "/dati.json":
            corpo, tipo = DATI, "application/json"
        elif u.path == "/dati.json.gz":   # niente Content-Encoding: il proxy della notturna non lo inoltrerebbe
            corpo, tipo = DATI_GZ, "application/octet-stream"
        elif u.path == "/richiama":   # come il richiamo vero: frase -> i 3 ricordi vincenti, ricomposti
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0]
            r = [{"id": n, "punti": round(float(p), 3), "testo": L.ricomponi(n)} for n, p in L.richiama(q, 3, 0)] if q.strip() else []   # la pagina esplora: mostra anche sotto soglia
            corpo, tipo = json.dumps(r, ensure_ascii=False).encode(), "application/json"
        elif u.path == "/ricordo":
            n = int(urllib.parse.parse_qs(u.query).get("id", ["0"])[0])
            r = {"id": n, "testo": L.ricomponi(n)} if n in L.ricordi else {}
            corpo, tipo = json.dumps(r, ensure_ascii=False).encode(), "application/json"
        elif u.path == "/cerca":
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0]
            corpo, tipo = json.dumps(cerca(q)).encode(), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Lux {X.VERSIONE} in 3D: http://127.0.0.1:{PORTA}  ({len(L.testi)} engrammi)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORTA), H).serve_forever()
