# riflesso_firma.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import json
import os
import time
import riflesso_comune as C


# B6 (31/10, engrammi/PIANO-FIRMA-ENGRAMMI.md): i messaggi del turno chiuso vanno a firma-subito, il ricordo
# nasce subito e non piu' nella notturna
CODA_FIRMA = os.environ.get("CODA_FIRMA", "/data/workspace/memoria/coda-firma.jsonl")


def _accoda_forzato(testo, siti=()):
    fd = os.open(CODA_FIRMA, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:   # una sola write: righe intere anche con la chat che accoda
        os.write(fd, (json.dumps({"ts": time.time(), "autore": "@agente:localhost", "testo": testo,
                                  "forzato": True, **({"siti": list(siti)} if siti else {})},
                                 ensure_ascii=False) + "\n").encode())
    finally:
        os.close(fd)


def _accoda_firma(flusso, ultimo, arrivo, esito, siti=()):
    """B6: solo le risposte finali. Chat: il messaggio dell'utente com'era prima delle aggiunte del riflesso (ora, coda)
    e la risposta dell'agente; un ultimo user senza "[handle] " e' Hermes (background review, memory flush): niente.
    Pensatoio: la risposta dell'agente. Una sola write in append: righe intere anche con la notturna che accoda"""
    if not esito or esito.get("finish") != "stop" or esito.get("tool_calls"):
        return
    risposta = C._senza_imitati(esito.get("testo") or "").strip()
    righe = []
    if flusso == "chat":
        m = C._HANDLE.match(ultimo.strip()) if isinstance(ultimo, str) else None
        if not m or not m.group(2).strip():
            return
        righe.append({"ts": arrivo, "autore": f"@{m.group(1)}:localhost", "testo": m.group(2).strip(), "flusso": flusso})
    elif flusso != "pensatoio":
        return
    if risposta and not risposta.startswith("[OUT-OF-BAND]"):   # orchestrazione, non esperienza (estrai-matrix)
        righe.append({"ts": time.time(), "autore": "@agente:localhost", "testo": risposta, "flusso": flusso,
                      **({"siti": list(siti)} if siti else {})})   # 1.24.0: i siti delle pagine lette nel turno
    if righe:
        fd = os.open(CODA_FIRMA, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in righe).encode())
        finally:
            os.close(fd)
