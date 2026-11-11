#!/usr/bin/env python3
"""verifica_post_versioning.py (16/10/2026): dopo ogni versione nuova del Lux, controlla che TUTTI i ricordi
siano ricostruiti correttamente dal Lux (VERSIONE di lux_engrammi.py): 1.20.0, il testo esatto e' nel meta del Lux (prima
memoria.db), le correzioni restano fuori come prima. Sola lettura.
Un ricordo e' corretto se la ricomposizione e' uguale al testo originale a meno delle trasformazioni volute dal taglio:
  formattazione tolta (taglia.FORMATO), virgolette tolte, spazi, maiuscole degli engrammi condivisi,
  forma canonica delle preposizioni (ad -> a, d' -> di, fra -> tra).
Per ogni ricordo dice a quale livello e' uguale; quelli che non tornano nemmeno dopo le trasformazioni sono errori,
con il punto dove divergono. Uscita 1 se c'e' almeno un errore o un ricordo mancante.
Uso: /data/venv-spacy/bin/python verifica_post_versioning.py"""
import difflib
import json
import re
import sys

import lux_engrammi as X

T = X.T
ELISIONE = re.compile(r"(\w)'(?=\w)")


def senza_formato(s):
    return "".join(T.FORMATO.sub("", s).split())


def senza_virgolette(s):
    return "".join(ch for ch in senza_formato(s) if ch not in T.VIRGOLETTE)


def canonico(s):
    """virgolette e formattazione tolte, minuscole, preposizioni nella forma canonica, senza spazi"""
    s = T.FORMATO.sub("", s).lower().replace("’", "'")
    s = ELISIONE.sub("\\1\x00", s)   # l'apostrofo fra due lettere e' elisione (d'animo), non virgoletta
    s = "".join(" " if ch in T.VIRGOLETTE else ch for ch in s).replace("\x00", "'")
    out = []
    for w in re.findall(r"\w+'|\w+|[^\w\s]", s):
        p = T.PREPOSIZIONI.get(w)
        out.append(X.INVERSO[p] if p is not None else w)
    return "".join(out)


def dove(a, b):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [(op, a[max(0, i1 - 15):i2 + 15], b[max(0, j1 - 15):j2 + 15]) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"][:3]


def main():
    L = X.Lux()
    orig = {int(k): r["testo"] for k, r in json.load(open(X.META))["ricordi"].items()   # 1.20.0: dal meta del Lux
            if r["classe"] != "correzione" and r.get("testo")}                       # (prima memoria.db)
    mancanti = sorted(set(orig) - set(L.ricordi))
    livelli = {"identico": [], "senza formattazione": [], "senza virgolette": [], "trasformazioni del taglio": [], "ERRORE": []}
    for nid in sorted(set(orig) & set(L.ricordi)):
        o, r = orig[nid], L.ricomponi(nid)
        if r == o:
            livelli["identico"].append(nid)
        elif senza_formato(r) == senza_formato(o):
            livelli["senza formattazione"].append(nid)
        elif senza_virgolette(r) == senza_virgolette(o):
            livelli["senza virgolette"].append(nid)
        elif canonico(r) == canonico(o):
            livelli["trasformazioni del taglio"].append(nid)
        else:
            livelli["ERRORE"].append(nid)
    print(f"Lux {X.VERSIONE}: {len(orig)} ricordi col testo nel meta, {len(L.ricordi)} nel Lux")
    for k, v in livelli.items():
        print(f"  {k:28} {len(v)}")
    if mancanti:
        print(f"  MANCANTI nel Lux: {mancanti}")
    for nid in livelli["ERRORE"]:
        print(f"\n== ERRORE ricordo {nid}")
        for op, a, b in dove(canonico(orig[nid]), canonico(L.ricomponi(nid))):
            print(f"   {op}: originale {a!r}\n   {' ' * len(op)}  Lux       {b!r}")
    ok = not livelli["ERRORE"] and not mancanti
    print("\nTUTTI I RICORDI RICOSTRUITI CORRETTAMENTE" if ok else f"\n{len(livelli['ERRORE'])} errori, {len(mancanti)} mancanti")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
