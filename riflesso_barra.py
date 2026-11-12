# riflesso_barra.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import os
import threading
from pathlib import Path
import riflesso_stato as S


def _segna_volo():
    """20/10: quante richieste della chat sono in volo, per la barra del prefill
    (~/.local/bin/barra-prefill): i prefill partiti con la chat in volo sono della chat"""
    with _volo_lock:    # 10/11: lo legge anche dormi-esegui.sh, mai un file a meta'
        try:
            Path(VOLO + ".tmp").write_text(str(S._chat_in_volo[0]))
            os.replace(VOLO + ".tmp", VOLO)
        except OSError:
            pass


def _segna_fase(f):
    """24/10: cosa sta facendo l'agente (legge, pensa, scrive, tool; vuoto = ferma), per l'emoji nel suo nome
    in chat (~/.local/bin/barra-prefill). Si scrive solo quando cambia"""
    with _fase_lock:
        if f == _fase[0]:
            return
        try:
            Path(FASE + ".tmp").write_text(f)
            os.replace(FASE + ".tmp", FASE)
            _fase[0] = f
        except OSError:
            pass


VOLO = "/tmp/chat-in-volo"
FASE = "/tmp/fase"
_volo_lock = threading.Lock()
_fase = [None]
_fase_lock = threading.Lock()
