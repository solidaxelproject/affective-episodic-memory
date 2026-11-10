# Persistenza dei ricordi: curva FSRS e orologio dei giorni vissuti (30/09).
# Manutenzione 10/11: di lux.py restano solo queste funzioni (le usano persistenza.py, engrammi/lux_engrammi.py, la
# notturna); la classe Lux v0 (Grow-When-Required, vecchio Lux archiviato il 31/10) resta nella storia di git.
import json
import time
from pathlib import Path

import numpy as np

DIR = Path("/data/workspace/memoria")
FILE = DIR / "lux.npz"   # non esiste piu': serve solo come cartella dell'orologio (anche nei test, che cambiano FILE)

# ---------- persistenza (30/09, PIANO-PERSISTENZA-LUX.md, fase 1) ----------
#   - l'orologio e' il TEMPO VISSUTO (notturne riuscite, tempo-vissuto.json):
#     da spenta non si dimentica
#   - ogni ricordo ha una stabilita' S e una ritenzione R. Curva dell'oblio a
#     LEGGE DI POTENZA, come quella umana (Wixted & Ebbesen 1991; forma di FSRS,
#     modello addestrato su milioni di ripetizioni umane):
#         R(t) = (1 + F * t / S) ** DECAY,  F = 19/81, DECAY = -0.5
#     S = giorni vissuti dopo cui R scende a 0.9. La coda e' lunga: un ricordo
#     sbiadisce ma non si azzera in fretta (il "permastore" di Bahrick, 1984)
#   - a ogni riattivazione S cresce con la formula di FSRS (richiamo riuscito, difficolta' di un 'good'):
#         S <- S * (1 + K * S**(-B) * (exp(C * (1 - R)) - 1) * peso)
#     R = 1 (stesso giorno) -> crescita zero: dieci richiami ammassati valgono uno;
#     R basso (stava svanendo) -> crescita forte: effetto spaziatura (Ebbinghaus,
#     Cepeda 2006); S**(-B): rendimenti decrescenti sui ricordi gia' stabili
#   - un ricordo nasce piu' stabile se e' emotivamente forte: l'arousal potenzia
#     il consolidamento (McGaugh 2004). S0 = S_BASE * fattore(salienza)
#   - si pota quando R < R_MIN
# Valori scelti su criterio di memoria umana (scelta di progetto, 30/09).
S_BASE = 3.173     # FSRS (pesi di default a 19, w2): stabilita' iniziale di un ricordo appreso una volta ("good")
AROUSAL_MAX = 3.0  # un ricordo emotivamente fortissimo nasce fino a 3x piu' stabile
F_CURVA, DECAY = 19 / 81, -0.5
# pesi di default di FSRS (19 parametri): w8 = 1.54575, w9 = 0.1192, w10 = 1.01925; difficolta' iniziale di un
# "good" D0 = w4 - e^(2 w5) + 1 = 5.28 (w4 = 7.1949, w5 = 0.5345). Fonte: borretti.me/article/implementing-fsrs-in-100-lines
_D0 = 7.1949 - np.exp(2 * 0.5345) + 1
K_FSRS, B_FSRS, C_FSRS = float(np.exp(1.54575) * (11 - _D0)), 0.1192, 1.01925
R_MIN = 0.10       # sotto: potato. Con S = 3 vuol dire ~3.5 anni vissuti senza mai tornare
S_MAX = 36500.0    # 100 anni vissuti: di fatto nessun tetto, come in FSRS
def curva(delta, s):
    """ritenzione dopo delta giorni vissuti con stabilita' s (legge di potenza)"""
    return (1 + F_CURVA * delta / s) ** DECAY


def cresci(s, r, peso=1.0):
    """stabilita' dopo una riattivazione avvenuta a ritenzione r (formula FSRS)"""
    return min(S_MAX, s * (1 + K_FSRS * s ** (-B_FSRS) * (np.exp(C_FSRS * (1 - r)) - 1) * peso))


def _file_orologio():
    return FILE.parent / "tempo-vissuto.json"   # accanto a lux.npz (anche nei test)


def orologio():
    """giorni vissuti finora (0 se l'orologio non e' mai partito)"""
    try:
        return int(json.load(open(_file_orologio()))["giorni"])
    except (OSError, ValueError, KeyError):
        return 0


def avanza_orologio():
    """+1 giorno vissuto: la chiama la notturna a lavoro riuscito, e solo lei."""
    g = orologio() + 1
    tmp = _file_orologio().with_suffix(".tmp")
    json.dump({"giorni": g, "ultimo_avanzamento": time.time()}, open(tmp, "w"))
    tmp.replace(_file_orologio())
    return g
