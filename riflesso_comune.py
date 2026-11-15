# riflesso_comune.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import hashlib
import json
import os
import re
import time
from pathlib import Path
import ponte


# 14/11 (l'utente, interfase 3-4 punto 6): patto e consenso tolti; i vettori li spegne solo l'utente dalla dashboard (:8095,
# pulsante "vettori"), che crea questo file. Sta fuori da workspace: l'agente non lo vede e non lo cambia.
VETTORI_SPENTI = Path(os.environ.get("RIFLESSO_VETTORI_SPENTI", "/data/memoria-episodica-affettiva/vettori-spenti"))
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"


_HANDLE = re.compile(r"^\[([a-z0-9_]+)\]\s?(.*)$", re.DOTALL)   # come estrai-matrix: solo handle veri (minuscoli)


_ORA = re.compile(r"^\[\d{1,2}/\d{1,2}/\d{4}\|\d{1,2}:\d{2}\] ")


def _chiedi(path, payload):
    st, r = ponte.post(path, payload, timeout=600)
    if st != 200:
        raise RuntimeError(f"{path}: HTTP {st}")
    return r


def vettori_attivi():
    """vettori ammessi finche' l'utente non li spegne dalla dashboard (14/11: niente piu' consenso nel file dell'agente)"""
    return not VETTORI_SPENTI.exists()


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
_EMOZIONI_IT = [e["it"] for e in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "emozioni.json"),
                                                 encoding="utf-8"))]   # 14/11: le righe [emozione] del blocco
_IMITATI = re.compile(r"(?:\s*\[(?:/?pensatoio|\d\d:\d\d\|\d\d/\d\d/\d{4}|"
                      + "|".join(map(re.escape, sorted(_EMOZIONI_IT, key=len, reverse=True))) + r")\])+\s*\Z")


def _senza_imitati(testo):
    return _IMITATI.sub("", testo) if isinstance(testo, str) else testo


def _ha_testo(m):
    c = m.get("content")
    if isinstance(c, list):
        return any((p.get("text") or "").strip() for p in c if isinstance(p, dict))
    return bool((c or "").strip())


def _diario(voce):
    with open(DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **voce}, ensure_ascii=False) + "\n")
