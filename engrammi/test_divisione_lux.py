"""Divisione di lux_engrammi.py (interfase 3-4 punto 1, PIANO-INTERFASE-34-DIVISIONE-LUX.md, 14/11/2026).
Gira su una copia: LUX_DIR punta a una cartella temporanea, nessun file del Lux vero si apre.
1. ogni nome del modulo di prima (manutenzione/nomi-lux-1.24.0.txt, privati compresi) c'e' sulla facciata ed e' lo
   stesso oggetto del modulo che lo possiede;
2. gli 11 nomi che test e script sostituiscono da fuori (X.STATO = ...) arrivano al proprietario e le funzioni dei
   moduli leggono il valore nuovo (altrimenti un test scriverebbe in produzione)."""
import os
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
os.environ["LUX_DIR"] = tempfile.mkdtemp(prefix="test-divisione-lux-")
sys.path.insert(0, QUI)
import lux_engrammi as X  # noqa: E402

# 1. nomi di prima
nomi = open(os.path.join(QUI, "..", "manutenzione", "nomi-lux-1.24.0.txt")).read().split()
assert len(nomi) == 131
for n in nomi:
    assert hasattr(X, n), f"manca {n}"
    for m in X.MODULI:
        if n in vars(m) and not isinstance(getattr(X, n), type(sys)):
            assert vars(m)[n] is getattr(X, n) or n in ("_k", "_v"), f"{n}: oggetto diverso in {m.__name__}"
assert X.Lux.__mro__[1:3] == (X.Ricombina, X.Fonti)

# 2. inoltro delle sostituzioni
SOSTITUITI = ["PRECEDENTE", "STATO", "DIR", "NPZ", "META", "GIORNATA", "DIARIO_RIFLESSO", "OMEOSTATO",
              "SOGLIA_SORPRESA", "PONTE_CALO", "PONTI_PER_RICHIAMO"]
for n in SOSTITUITI:
    prima = getattr(X, n)
    setattr(X, n, f"prova-{n}")
    assert getattr(X.lux_base, n) == f"prova-{n}", f"{n} non inoltrato a lux_base"
    assert getattr(X, n) == f"prova-{n}"
    setattr(X, n, prima)
    assert getattr(X.lux_base, n) == prima

# una funzione di un altro modulo legge il valore sostituito: da_precedente si ferma se NPZ esiste gia'
d = tempfile.mkdtemp(prefix="test-divisione-lux-npz-")
open(f"{d}/lux.npz", "w").close()
npz, X.NPZ = X.NPZ, f"{d}/lux.npz"
try:
    X.da_precedente()
    raise AssertionError("da_precedente non ha visto NPZ sostituito")
except SystemExit as e:
    assert f"{d}/lux.npz" in str(e), e
X.NPZ = npz
print("test_divisione_lux: OK")
