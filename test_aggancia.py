# Test di aggancia-appunti (passo 2 del motore): righe nude -> arricchite.
# Gira senza GPU e senza rete: l'aggancio vero è iniettato come funzione finta.
import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "aggancia", "aggancia-appunti.py")
ag = importlib.util.module_from_spec(spec)
sys.modules["aggancia"] = ag
spec.loader.exec_module(ag)

ID = "01K0AFYBGWJ5M2QZ8XN4V7RTCE9DHSPB"     # stile ULID, 32+ char


def falso_aggancio(testo):
    return {"id": ID, "cos": 0.71, "salienza": 2.34}


def nessun_aggancio(testo):
    return None                              # sotto soglia / Lux vuota


righe = [
    "# appunti dell'agente",                       # riga qualunque: intoccabile
    "[fotoni]{come fa la luce a sapere il percorso più breve?}",
    "[01ABC|0.55|1.20] [rane]{perché cantano di notte?}",   # già arricchita
    "~~[vecchio]{già indagato}~~",            # depennata: intoccabile
    "",
]

fuori = ag.arricchisci(righe, falso_aggancio)

# 1. la riga nuda viene arricchita nel formato del motore
assert fuori[1] == f"[{ID}|0.71|2.34] [fotoni]{{come fa la luce a sapere il percorso più breve?}}", fuori[1]
# 2. idempotenza: la riga già arricchita non si tocca
assert fuori[2] == righe[2]
# 3. depennate e righe qualunque non si toccano
assert fuori[0] == righe[0] and fuori[3] == righe[3] and fuori[4] == righe[4]
# 4. sotto soglia: la riga resta nuda (fallback di il progetto: in fondo alla coda)
assert ag.arricchisci(righe, nessun_aggancio)[1] == righe[1]
# 5. il risultato è leggibile dal motore: regex RIGA con meta valorizzato
import re
RIGA = re.compile(r"^\s*(?:\[(?P<meta>[^\]]*)\])?\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")
m = RIGA.match(fuori[1])
assert m and m["meta"] == f"{ID}|0.71|2.34" and m["tema"] == "fotoni"
# 6. la salienza è nel campo che priorità() legge (terzo, split su |)
assert float(m["meta"].split("|")[2]) == 2.34

print("test_aggancia: TUTTO VERDE")
