# Self-contained demo of the growing memory organ (Lux, a GWR network).
# No GPU, no model, no personal data: a synthetic "life" of experiences shows
# the organ growing with novelty, connecting what is similar, and recalling
# by emotion and by meaning.  Requires only numpy.
#
#   python3 demo.py
#
# The organ used to merge similar traces during sleep, and this demo used to
# assert that it stayed lean. It no longer does either. Merging two distinct
# experiences does not abstract them, it makes them one thing lived twice: a
# deja vu. Structure is not lost by refusing to merge, it moves into the arcs,
# and this demo shows exactly that: 48 experiences stay 48 neurons, yet the
# four themes come back out of the topology on their own.
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lux

# keep the demo hermetic: the organ lives (and dies) in a temp directory
_td = tempfile.TemporaryDirectory()
lux.FILE = Path(_td.name) / "lux.npz"
lux.META = Path(_td.name) / "lux-meta.json"

rng = np.random.default_rng(42)
EMOTIONS = ["joy", "fear", "curiosity", "sadness"]
D, E = 2048, 51

# a synthetic life: four recurring emotional themes, each a region of the
# semantic space, lived many times with small variations
themes = rng.normal(size=(len(EMOTIONS), D)).astype(np.float32)
organ = lux.Lux()
born = reinforced = 0
whose_theme = {}                                     # neuron id -> theme it lived
print("== a life of 48 experiences, 4 recurring themes ==")
for day in range(4):
    for _ in range(12):
        k = rng.integers(len(EMOTIONS))
        state = themes[k] + 0.06 * rng.normal(size=D).astype(np.float32)
        signature = np.zeros(E, np.float32)
        signature[k] = 2.5 + rng.normal() * 0.2      # dominant emotion
        i, outcome = organ.esperisci(state, signature, nodo_id=int(k))
        born += outcome == "nato"
        reinforced += outcome == "rinforzato"
        whose_theme[str(organ.ids[i])] = int(k)
    fused = organ.consolida()                        # sleep: only true duplicates merge
    print(f"day {day + 1}: {len(organ.tracce)} neurons, {len(organ.archi)} arcs "
          f"({born} born, {reinforced} reinforced, {fused} fused in sleep)")

# every experience stayed itself: nothing was averaged away
assert born == 48 and len(organ.tracce) == 48, f"something merged: {len(organ.tracce)} neurons"

print("\n== the themes are still there, in the topology ==")
inside = sum(1 for k in organ.archi
             if whose_theme[k.split("|")[0]] == whose_theme[k.split("|")[1]])
bridges = len(organ.archi) - inside
print(f"{len(organ.archi)} arcs: {inside} inside a theme, {bridges} bridging two")
print(f"(a bridge is a theme being lived for the first time: {len(EMOTIONS)} themes, "
      f"{len(EMOTIONS) - 1} bridges)")
# nothing merged, yet the four themes fall out of the arcs on their own
assert inside >= 44, f"the topology lost the themes: only {inside} arcs inside one"
assert bridges <= len(EMOTIONS) - 1, f"too many bridges: {bridges}"

print("\n== recall by emotion ==")
for k, emo in enumerate(EMOTIONS):
    query = np.zeros(E, np.float32)
    query[k] = 1.0
    hit = organ.richiama(query, via="emotiva", k=1)[0]
    ok = hit["nodo_id"] == k
    print(f"feeling '{emo}' -> memory of theme {hit['nodo_id']} "
          f"(sim {hit['sim']}) {'OK' if ok else 'WRONG'}")
    assert ok

print("\n== recall by meaning (a noisy echo of a lived state) ==")
echo = themes[1] + 0.15 * rng.normal(size=D).astype(np.float32)
hit = organ.richiama(echo, via="semantica", k=1)[0]
print(f"echo of theme 1 -> neuron {hit['neurone']}, theme {hit['nodo_id']} "
      f"{'OK' if hit['nodo_id'] == 1 else 'WRONG'}")
assert hit["nodo_id"] == 1

print("\n== every neuron knows what it absorbed ==")
print(f"{len(organ.nodi)} neurons carry the list of the experiences they hold "
      f"(not just how many times they were touched)")

print("\nAll checks passed: the organ grew with novelty, kept every experience "
      "distinct, connected the similar ones, and recalled by emotion and by "
      "meaning. This is the same code that runs in production.")
