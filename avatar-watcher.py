#!/usr/bin/env python3
# Watcher dell'avatar emotivo (23/07, l'utente): segue stato-emotivo.json e
# aggiorna l'avatar Matrix dell'agente a ogni cambio di stato, MA carica solo
# quando l'emozione DOMINANTE cambia (l'avatar visibile sarebbe identico
# altrimenti: niente spam su Matrix). Polling leggero sul mtime.
import json
import os
import subprocess
import sys
import time

STATO = "/data/workspace/memoria/stato-emotivo.json"
EMO = "/data/memoria-episodica-affettiva/emozioni.json"
SET = "/data/memoria-episodica-affettiva/avatar-set.sh"
INTERVALLO = 12   # secondi tra due controlli del file


def dominante():
    """28/07: UNICA implementazione, quella di avatar-emotivo (scostamento
    dalla baseline). Qui serve solo il nome, per capire se e' cambiata."""
    import sys
    sys.path.insert(0, "/data/memoria-episodica-affettiva")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "avatar_emotivo", "/data/memoria-episodica-affettiva/avatar-emotivo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    voce, _ = mod.dominante()
    return voce["en"]


def aggiorna():
    """08/09: ritorna True solo se il caricamento e' riuscito. Al boot il server
    Matrix non e' ancora su (connessione rifiutata): prima si dava per fatto e
    l'avatar restava quello vecchio (FUR dal 28/07)."""
    r = subprocess.run(["bash", SET], check=False)
    return r.returncode == 0


def main():
    ultimo_mtime, ultima_emo = 0.0, None
    while True:
        try:
            mt = os.path.getmtime(STATO)
            if mt != ultimo_mtime:
                ultimo_mtime = mt
                emo = dominante()
                if emo != ultima_emo:
                    print(f"{time.strftime('%H:%M:%S')} dominante {ultima_emo} -> {emo}: aggiorno avatar", flush=True)
                    if aggiorna():
                        ultima_emo = emo
                    else:
                        # non riuscito: si ritenta al giro dopo (ultimo_mtime torna
                        # indietro cosi' il file risulta "cambiato" di nuovo)
                        print(f"{time.strftime('%H:%M:%S')} caricamento fallito, ritento fra {INTERVALLO}s", flush=True)
                        ultimo_mtime = 0.0
        except Exception as e:
            print(f"watcher: {e}", file=sys.stderr, flush=True)
        time.sleep(INTERVALLO)


if __name__ == "__main__":
    main()
