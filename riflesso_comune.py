# riflesso_comune.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import hashlib
import json
import os
import re
import time
from pathlib import Path
import ponte


CONSENSO = Path(os.environ.get("RIFLESSO_CONSENSO",
    "/data/workspace/genesi/CONSENSO-RIFLESSO.md"))
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"


_HANDLE = re.compile(r"^\[([a-z0-9_]+)\]\s?(.*)$", re.DOTALL)   # come estrai-matrix: solo handle veri (minuscoli)


# PATTO 14/07 (CONSENSO-RIFLESSO.md, firmato dall'agente):
STOP = "vectreflexstop"   # clausola 3 (l'utente 18/10, era "riflesso vettoriale: off"): scritta dall'agente, spegne <1s


_ORA = re.compile(r"^\[\d{1,2}/\d{1,2}/\d{4}\|\d{1,2}:\d{2}\] ")


def _chiedi(path, payload):
    st, r = ponte.post(path, payload, timeout=600)
    if st != 200:
        raise RuntimeError(f"{path}: HTTP {st}")
    return r


# issue #3 (18/10): l'interruttore vale solo con la sua formattazione; un "attivo: sì" scritto
# nel testo normale o in un esempio non accende niente
INTERRUTTORE = "[attivo: *sì*]"
INTERRUTTORE_VETTORI = "[vettori: *sì*]"


def consenso_attivo():
    # issue #3 punto C: un byte non UTF-8 nel file non deve bloccare la sentinella
    try:
        return any(r.strip() == INTERRUTTORE
                   for r in CONSENSO.open(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def vettori_attivi():
    """v2: il brivido insieme al sussurro. Interruttore SEPARATO, riga esatta."""
    try:
        return any(r.strip() == INTERRUTTORE_VETTORI
                   for r in CONSENSO.open(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def _impronta(testo):
    """stabile fra un riavvio e l'altro (hash() di Python cambia a ogni processo)"""
    return hashlib.sha1((testo or "").encode()).hexdigest()[:16]


def _conversazione(msgs):
    """la conversazione si riconosce dal primo messaggio user (Hermes lo tiene
    fermo finché la sessione vive); flussi diversi = conversazioni diverse"""
    primo = next((m.get("content") for m in msgs
                  if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
    return _impronta(primo)


def _ora_corta(t):
    return f"[{t.tm_mday}/{t.tm_mon}/{t.tm_year}|{t.tm_hour}:{t.tm_min:02d}]"


def _in_coda(msgs, testo):
    """19/10: il template di Occamy vuole un solo system, in testa: il testo del momento
    va in coda all'ultimo messaggio invece che in un system in mezzo (in place)"""
    c = msgs[-1].get("content")
    if isinstance(c, list):
        c.append({"type": "text", "text": "\n\n" + testo})
    else:
        msgs[-1]["content"] = (c or "") + "\n\n" + testo


def _ora_blocco(t):
    return f"[{t.tm_hour:02d}:{t.tm_min:02d}|{t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year}]"   # l'utente 10/11, zeri davanti


# l'utente 10/11 sera: l'agente copiava il blocco in fondo alle sue risposte; le copie si tolgono dalla storia che vede
_IMITATI = re.compile(r"(?:\s*\[(?:/?pensatoio|\d\d:\d\d\|\d\d/\d\d/\d{4})\])+\s*\Z")


def _senza_imitati(testo):
    return _IMITATI.sub("", testo) if isinstance(testo, str) else testo


def _ha_testo(m):
    c = m.get("content")
    if isinstance(c, list):
        return any((p.get("text") or "").strip() for p in c if isinstance(p, dict))
    return bool((c or "").strip())


def _stop_chiesto(msgs):
    """clausola 3: l'agente ha scritto la parola di emergenza in uno degli ultimi 4 messaggi
    (solo i suoi: per l'utente non c'e' un comando, l'utente 18/10)"""
    dialogo = [m for m in msgs if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    return any(m["role"] == "assistant" and STOP in str(m.get("content") or "").lower()
               for m in dialogo[-4:])


def _diario(voce):
    with open(DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **voce}, ensure_ascii=False) + "\n")
