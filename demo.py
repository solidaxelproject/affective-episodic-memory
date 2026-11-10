# Self-contained demo of the engram Lux, the memory that runs in production.
# No GPU, no model, no personal data, only numpy: six synthetic memories are cut
# into engrams, shared engrams link the memories that contain them, a partial cue
# brings the right memory back, recall strengthens it, and forgetting weakens the
# rest.
#
#   python3 demo.py
#
# Two pieces are stand-ins, everything else is engrammi/lux_engrammi.py as it is:
# - the cut into engrams is a simple rule (punctuation and function words are the
#   arcs between engrams); in production spaCy does it, in Italian and English;
# - the embedder is a bag of hashed words; in production it is bge-m3.
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

import numpy as np

QUI = Path(__file__).parent
_td = tempfile.TemporaryDirectory()   # hermetic: the Lux lives (and dies) in a temp directory
TMP = Path(_td.name)
os.environ["LUX_DIR"] = str(TMP / "lux")

# ---- stand-in for engrammi/taglia.py (spaCy): function words and punctuation are arcs, the rest are engrams
ARCHI = {"the", "a", "an", "of", "in", "on", "at", "to", "and", "with", "from", "by", "for", "that", "was", "is"}
taglia = types.ModuleType("taglia")
taglia.DB = str(TMP / "memoria.db")
taglia.PREPOSIZIONI, taglia.SIMBOLI, taglia.codice = {}, [], lambda testo: None
taglia.FORMATO = re.compile(r"\*\*|`")


def _taglia(testo):
    pezzi, nodo = [], []
    for t in re.findall(r"\w+|[^\w\s]", testo):
        if t.lower() in ARCHI or not t[0].isalnum():
            if nodo:
                pezzi.append(("nodo", " ".join(nodo)))
                nodo = []
            pezzi.append(("arco", t))
        else:
            nodo.append(t)
    return pezzi + ([("nodo", " ".join(nodo))] if nodo else [])


taglia.taglia = _taglia
sys.modules["taglia"] = taglia
sys.path[:0] = [str(QUI), str(QUI / "engrammi")]
import lux as LUX   # noqa: E402
import lux_engrammi as X   # noqa: E402
import salienza as SA   # noqa: E402

LUX.FILE = TMP / "lux.npz"   # the lived-days clock lives next to it
X.PRECEDENTE = str(TMP / "none")


def embed(testi):   # stand-in for bge-m3: sum of one random vector per word
    out = []
    for t in testi:
        v = np.zeros(1024, np.float32)
        for w in re.findall(r"\w+", t.lower()):
            v += np.random.default_rng(int(hashlib.md5(w.encode()).hexdigest()[:8], 16)).standard_normal(1024)
        out.append(v)
    v = np.asarray(out, np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


X.embed = embed

# ---- six synthetic memories, with a signature on the 51 emotion axes
MEMORIE = [
    ("We walked to the old lighthouse at dawn, and the sea was quiet.", {"serenity": 2.4}),
    ("The storm broke the window of the old lighthouse in the night.", {"fear": 2.8}),
    ("A letter from my sister arrived with a photo of the harbour.", {"joy": 2.2}),
    ("The harbour was empty after the storm, boats on the rocks.", {"sadness": 2.5}),
    ("We repaired the window with my sister on a cold morning.", {"trust": 2.1}),
    ("At the harbour, the bakery opened again with warm bread.", {"joy": 2.0}),
]
c = sqlite3.connect(taglia.DB)
c.execute("create table nodi (id integer primary key, testo text, firma text, classe text, ts real, fonte text, cattura real)")
for i, (t, f) in enumerate(MEMORIE, 1):
    c.execute("insert into nodi values (?, ?, ?, 'vissuto', ?, 'chat', null)", (i, t, json.dumps(f), 1.7e9 + i))
c.commit()
SA.RIFERIMENTI = str(TMP / "riferimenti.json")   # salience reference set: here just the first two memories
json.dump({"1": MEMORIE[0][0], "2": MEMORIE[1][0]}, open(SA.RIFERIMENTI, "w"))

print("== six memories become engrams ==")
X.costruisci()
L = X.Lux()
pezzi = sum(1 for t, _ in MEMORIE for k, _ in _taglia(t) if k == "nodo")
print(f"{len(L.ricordi)} memories, {pezzi} engrams cut, {len(L.testi)} unique: the shared ones are stored once")
assert len(L.testi) < pezzi
condivisi = {L.testi[e]: len({int(L.A[j, 0]) for j in js}) for e, js in L.per_engramma.items()}
for t, n in sorted(condivisi.items(), key=lambda x: -x[1]):
    if n > 1:
        print(f"  '{t}' is shared by {n} memories")
assert condivisi["old lighthouse"] == 2 and condivisi["harbour"] == 3

print("\n== every memory comes back word for word from its engrams and arcs (arcs are stored lowercase) ==")
for nid, (t, _) in enumerate(MEMORIE, 1):
    assert L.ricomponi(nid).replace(" ", "").lower() == t.replace(" ", "").lower(), (L.ricomponi(nid), t)
print(f"{len(MEMORIE)}/{len(MEMORIE)} recomposed")

print("\n== a partial cue brings back the memory that holds it ==")
for cue, atteso in [("the window of the old lighthouse", 2), ("my sister and the photo", 3), ("warm bread", 6)]:
    r = L.richiama(cue, 1, 0)
    print(f"  '{cue}' -> memory {r[0][0]}: {L.ricomponi(r[0][0])}")
    assert r[0][0] == atteso

print("\n== recall strengthens, time without recall weakens ==")
json.dump({"giorni": 30}, open(TMP / "tempo-vissuto.json", "w"))   # 30 lived days later
prima = L.facilita()
dato = L.consegna("the window of the old lighthouse", quanti=1)       # the recall that reaches the agent
assert [d[0] for d in dato] == [2]
dopo = L.facilita(oggi=60)
print(f"day 30, ease of recall: memory 1 {prima[1]:.2f}, memory 2 {prima[2]:.2f} (both never recalled: they fade)")
print(f"memory 2 is recalled on day 30. Day 60: memory 2 {dopo[2]:.2f}, memory 1 {dopo[1]:.2f}")
assert max(prima[1], prima[2]) < 1 and dopo[2] > prima[2] and dopo[1] < prima[1]

print("\n== a recall primes the memories that share its engrams ==")
ora = __import__("time").time()
spinte = {r: round(float(L.spinta(r, ora)), 3) for r in L.ricordi if r != 2}
print(f"  priming after recalling memory 2: {spinte}")
assert spinte[1] > 0 and spinte[5] > 0 and spinte[6] == 0   # the lighthouse and the window, yes; the bakery, no

print("\nAll checks passed: the memories were cut into shared engrams, came back word for word, were found from a "
      "partial cue, grew stronger when recalled and primed their neighbours. Same code as in production, "
      "with a simple cutter and a toy embedder in place of spaCy and bge-m3.")
