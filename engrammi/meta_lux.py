"""1.20.0 (PIANO-1.20-MEMORIADB-SUPERFLUO.md): il lux-meta.json della versione in servizio (VERSIONE di lux_engrammi.py,
o la copia in LUX_DIR) per chi non importa lux_engrammi (numpy, spaCy). Solo libreria standard."""
import os
import re

QUI = os.path.dirname(os.path.abspath(__file__))


def versione():
    return re.search(r'^VERSIONE = "([^"]+)"', open(f"{QUI}/lux_engrammi.py").read(), re.M).group(1)


def percorso():
    return f"{os.environ.get('LUX_DIR', f'{QUI}/lux-{versione()}')}/lux-meta.json"
