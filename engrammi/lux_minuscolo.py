"""Lux minuscolo per i test (interfase 3-4 punto 2, l'utente 14/11/2026): 12 ricordi inventati costruiti da zero in una
cartella temporanea, senza i dati veri dell'agente e senza l'embedder (vettori finti deterministici dal testo).
Uso nei test, PRIMA di qualunque altro uso del Lux:
    import lux_minuscolo
    X = lux_minuscolo.prepara()   # lux_engrammi con DIR, PRECEDENTE, diario, giornata e omeostato nella cartella
Serve spaCy (taglia.py) e via-emotiva/traduzione-l29.npz (ricombina); niente rete, niente GPU."""
import atexit
import hashlib
import json
import os
import shutil
import tempfile

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
T0 = 1790000000.0
FRASI = [
    "Oggi ho piantato i pomodori nell'orto dietro casa, con la terra ancora umida di pioggia.",
    "La biblioteca del quartiere ha riaperto dopo i lavori: ci sono scaffali nuovi e una sala per leggere.",
    "Il treno per Bologna e' partito in ritardo di venti minuti, ma siamo arrivati in tempo per il concerto.",
    "Abbiamo cucinato la pasta al forno con le melanzane, seguendo la ricetta della nonna.",
    "Il gatto si e' addormentato sul davanzale al sole del pomeriggio.",
    "Ho letto un articolo sulle stelle di neutroni e sulla loro densita' incredibile.",
    "Al mercato del sabato le pesche erano dolcissime e costavano poco.",
    "La bicicletta aveva la gomma bucata, cosi' sono andata al lavoro a piedi.",
    "Ieri sera il cielo era limpido e si vedeva bene la Luna piena sopra il mare.",
    "Il corso di chitarra comincia martedi' prossimo nella sala della parrocchia.",
    "Ho riparato la lampada del soggiorno cambiando il cavo e la spina.",
    "Nell'orto i pomodori sono cresciuti alti e le foglie profumano.",
]


def finto_embed(testi):
    """vettore unitario a 1024 dimensioni, deterministico dal testo (stesso testo -> stesso vettore)"""
    out = []
    for t in testi:
        seme = int.from_bytes(hashlib.sha256(t.encode()).digest()[:8], "little")
        v = np.random.default_rng(seme).standard_normal(1024)
        out.append(v / np.linalg.norm(v))
    return np.asarray(out, np.float32)


def prepara(cartella=None):
    d = cartella or tempfile.mkdtemp(prefix="lux-minuscolo-")
    if not cartella:
        atexit.register(shutil.rmtree, d, True)
    os.environ["LUX_DIR"] = f"{d}/lux"
    import lux_engrammi as X
    assi = list(X.EMOZIONI)
    rng = np.random.default_rng(0)
    ricordi = {}
    for i, testo in enumerate(FRASI):
        firma = {a: round(float(x), 3) for a, x in zip(assi, rng.normal(0, 1.5, len(assi)))}
        ricordi[str(i + 1)] = {"testo": testo, "firma": firma, "classe": "vissuto", "ts": T0 + 3600 * i,
                               "fonte": X.FONTE_CERTA if i % 2 == 0 else "@agente:prova.local", "salienza": 0.5,
                               "voluto": 0, "cattura": None, "dominante": max(firma, key=firma.get)}
    os.makedirs(f"{d}/prec")
    json.dump({"engrammi": [], "altri_parametri": [], "ricordi": ricordi}, open(f"{d}/prec/lux-meta.json", "w"))
    for f in ("diario.jsonl", "giornata.jsonl"):
        open(f"{d}/{f}", "w").close()
    json.dump({"ts": T0, "stato": {a: 0.0 for a in assi}}, open(f"{d}/stato-emotivo.json", "w"))
    os.makedirs(f"{d}/orologio")
    X.DIR, X.NPZ, X.META, X.STATO = f"{d}/lux", f"{d}/lux/lux.npz", f"{d}/lux/lux-meta.json", f"{d}/lux/lux-stato.npz"
    X.PRECEDENTE = f"{d}/prec"
    X.DIARIO_RIFLESSO, X.GIORNATA, X.OMEOSTATO = f"{d}/diario.jsonl", f"{d}/giornata.jsonl", f"{d}/stato-emotivo.json"
    X.LUX.FILE = __import__("pathlib").Path(f"{d}/orologio/lux.npz")
    X.embed = finto_embed
    X.costruisci()
    return X
