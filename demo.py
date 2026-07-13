# Self-contained demo of the growing memory organ (Lux, a GWR network).
# No GPU, no model, no personal data: a synthetic "life" of experiences shows
# the organ growing with novelty, consolidating during sleep, and recalling
# by emotion and by meaning.  Requires only numpy.
#
#   python3 demo.py
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
print("== a life of 48 experiences, 4 recurring themes ==")
for day in range(4):
    for _ in range(12):
        k = rng.integers(len(EMOTIONS))
        state = themes[k] + 0.06 * rng.normal(size=D).astype(np.float32)
        signature = np.zeros(E, np.float32)
        signature[k] = 2.5 + rng.normal() * 0.2      # dominant emotion
        _, outcome = organ.esperisci(state, signature, nodo_id=int(k))
        born += outcome == "nato"
        reinforced += outcome == "rinforzato"
    fused = organ.consolida()                        # sleep: similar traces merge
    print(f"day {day + 1}: {len(organ.tracce)} neurons "
          f"({born} born, {reinforced} reinforced, {fused} fused in sleep)")

assert len(organ.tracce) <= 12, "the organ should stay lean: it grows on novelty, not on volume"

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

print("\n== birth registry (who was nearest when each neuron was born) ==")
print("nato_da:", ["first" if v == -1 else "recorded" for v in organ.nato_da])

print("\nAll checks passed: the organ grew with novelty, slept, and recalled "
      "by emotion and by meaning. This is the same code that runs in production.")
