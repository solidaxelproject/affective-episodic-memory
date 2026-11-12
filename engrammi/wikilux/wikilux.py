#!/usr/bin/env python3
"""wikilux (15/10/2026): un Lux di prova costruito da Wikipedia italiana, tema medicina (ZIM Kiwix nopic),
per misurare quanto pesa. Ogni ricordo = un articolo. Si scompatta in engrammi e archi SOLO il testo degli articoli:
paragrafi ed elenchi del corpo, senza infobox, tabelle, note, bibliografia, voci correlate, collegamenti.
Stesse regole del Lux dell'agente: taglia.py (spaCy it) e la logica di _inserisci in lux_engrammi.py.
I vettori bge-m3 NON si calcolano (la GPU serve al test): il loro peso = engrammi x 1024 x 4 byte.
Due passi, perche' libzim/bs4 stanno nel python di sistema e spaCy in /data/venv-spacy (che non si tocca):
  python3 wikilux.py estrai                          ZIM -> articoli.jsonl (titolo, paragrafi)
  /data/venv-spacy/bin/python wikilux.py [quanti] articoli.jsonl -> wikilux (quanti = solo i primi N)"""
import json
import os
import re
import sqlite3
import sys
import time
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
D = os.path.dirname(os.path.abspath(__file__))
ZIM = f"{D}/wikipedia_it_medicine_nopic_2026-10.zim"
FUORI = {"Note", "Bibliografia", "Voci correlate", "Altri progetti", "Collegamenti esterni", "Fonti", "Riferimenti"}


def testo_articolo(html):
    import bs4
    s = bs4.BeautifulSoup(html, "lxml")
    corpo = s.find("div", class_="mw-parser-output") or s
    for x in corpo.find_all(["table", "sup", "style", "script", "math", "figure"]):
        x.decompose()
    for x in corpo.find_all(class_=["navbox", "noprint", "metadata", "mw-references-wrap", "reflist", "hatnote"]):
        x.decompose()
    pezzi, dentro = [], True
    for x in corpo.find_all(["h2", "p", "li"]):
        if x.name == "h2":
            dentro = x.get_text(" ", strip=True) not in FUORI
        elif dentro and not (x.name == "li" and x.find_parent(["li"])):
            t = re.sub(r"\s+", " ", x.get_text(" ", strip=True)).strip()
            t = re.sub(r" ([,.;:!?)])", r"\1", t).replace("( ", "(")
            if t:
                pezzi.append(t)
    return pezzi


def lavora(x):
    os.nice(19)
    import taglia as T
    titolo, paragrafi = x
    out = []
    for p in paragrafi:
        out += T.taglia(p)
    return titolo, out


def articoli(quanti):
    n = 0
    for riga in open(f"{D}/articoli.jsonl"):
        x = json.loads(riga)
        yield x["titolo"], x["paragrafi"]
        n += 1
        if quanti and n >= quanti:
            return


def estrai():
    import libzim
    a = libzim.Archive(ZIM)
    out = open(f"{D}/articoli.jsonl.tmp", "w")
    n = 0
    for i in range(a.entry_count):
        e = a._get_entry_by_id(i)
        if e.is_redirect or e.path == "mainPage":
            continue
        it = e.get_item()
        if not it.mimetype.startswith("text/html"):
            continue
        p = testo_articolo(bytes(it.content).decode("utf-8", "replace"))
        if p:
            out.write(json.dumps({"titolo": e.title, "paragrafi": p}, ensure_ascii=False) + "\n")
            n += 1
    out.close()
    os.replace(f"{D}/articoli.jsonl.tmp", f"{D}/articoli.jsonl")
    print(f"{n} articoli estratti", flush=True)


def main(quanti):
    import lux_engrammi as LE   # param_id, chiave (sola lettura: il Lux dell'agente non si tocca)
    eid, testi, tab, A, P, ricordi = {}, [], {}, [], [], {}
    t0 = time.time()
    with Pool(4) as pool:
        for nid, (titolo, pezzi) in enumerate(pool.imap(lavora, articoli(quanti), chunksize=4)):
            nodi, legami, attesa = [], [], []
            for k, t in pezzi:
                if k == "arco":
                    attesa.append(LE.param_id(t, tab))
                    continue
                kk = LE.chiave(t)
                if kk not in eid:
                    eid[kk] = len(testi)
                    testi.append(t)
                nodi.append(eid[kk])
                legami.append(attesa)
                attesa = []
            ricordi[nid] = {"titolo": titolo, "n": len(nodi), "testa": legami[0] if legami else [], "coda": attesa}
            for p in range(1, len(nodi)):
                A.append((nid, p, nodi[p - 1], nodi[p], len(P), len(legami[p])))
                P += legami[p]
            if len(nodi) == 1:
                A.append((nid, 0, nodi[0], nodi[0], len(P), 0))
            if (nid + 1) % 500 == 0:
                print(f"{nid + 1} articoli, {len(testi)} engrammi, {len(A)} archi, {time.time() - t0:.0f}s", flush=True)
    n = len(ricordi)
    print(f"{n} articoli -> {len(testi)} engrammi, {len(A)} archi, {len(P)} parametri in {time.time() - t0:.0f}s", flush=True)
    np.savez(f"{D}/wikilux.npz", A=np.asarray(A, np.int64).reshape(-1, 6), P=np.asarray(P, np.int32))
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(f"{D}/wikilux-meta.json", "w"), ensure_ascii=False)
    # confronto: lo stesso testo in SQLite con indice di ricerca testuale (FTS5)
    if os.path.exists(f"{D}/confronto-fts.db"):
        os.remove(f"{D}/confronto-fts.db")
    c = sqlite3.connect(f"{D}/confronto-fts.db")
    c.execute("create virtual table r using fts5(titolo, testo)")
    c.executemany("insert into r values(?, ?)", ((t, "\n".join(p)) for t, p in articoli(quanti)))
    c.commit()
    c.execute("vacuum")
    c.close()
    peso = lambda f: os.path.getsize(f"{D}/{f}")
    r = {"articoli": n, "engrammi": len(testi), "archi": len(A), "parametri": len(P),
         "wikilux.npz": peso("wikilux.npz"), "wikilux-meta.json": peso("wikilux-meta.json"),
         "vettori_bge_m3_float32": len(testi) * 1024 * 4, "sqlite_fts5": peso("confronto-fts.db"),
         "testo_utf8": sum(len("\n".join(p).encode()) for _, p in articoli(quanti))}
    json.dump(r, open(f"{D}/misura.json", "w"), indent=1)
    print(json.dumps(r, indent=1), flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["estrai"]:
        estrai()
    else:
        main(int(sys.argv[1]) if sys.argv[1:] else 0)
