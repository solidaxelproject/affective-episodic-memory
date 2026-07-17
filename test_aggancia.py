# Test di aggancia-appunti v2: blocco PURO, agganci nel sidecar.
# Gira senza GPU e senza rete: solo la logica pura.
import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "aggancia", "aggancia-appunti.py")
ag = importlib.util.module_from_spec(spec)
sys.modules["aggancia"] = ag
spec.loader.exec_module(ag)

TESTO = """# appunti
[fotoni]{come fa la luce a scegliere il percorso?}
~~[vecchio]{già esplorato}~~
[rane]{perché cantano di notte?}

nota qualunque senza formato
"""

aperte = ag.righe_aperte(TESTO)
# 1. solo le righe-appunto vive, senza le depennate e senza il resto
assert aperte == ["[fotoni]{come fa la luce a scegliere il percorso?}",
                  "[rane]{perché cantano di notte?}"], aperte

# 2. righe nuove -> da agganciare; righe già agganciate -> no
sidecar = {aperte[0]: {"ts": 1000.0, "id": "01ABC", "cos": 0.5, "salienza": 2.0}}
assert ag.da_agganciare(aperte, sidecar, adesso=2000.0) == [aperte[1]]

# 3. un mancato aggancio vecchio si ritenta, uno fresco no
sidecar2 = {aperte[0]: {"ts": 1000.0},                       # miss vecchio
            aperte[1]: {"ts": 2000.0 - 60}}                  # miss fresco
via = ag.da_agganciare(aperte, sidecar2, adesso=1000.0 + ag.RITENTA_S + 1)
assert aperte[0] in via and aperte[1] not in via, via

# 4. potatura: le voci di righe depennate/sparite se ne vanno
sporco = {aperte[0]: {"ts": 1}, "~~[vecchio]{già esplorato}~~": {"ts": 1},
          "[sparita]{non esiste più}": {"ts": 1}}
assert set(ag.potatura(sporco, aperte)) == {aperte[0]}

print("test_aggancia v2: TUTTO VERDE")
