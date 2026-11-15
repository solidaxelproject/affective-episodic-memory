#!/usr/bin/env python3
"""14/11: col pensatoio nello slot e QUIETE_S senza richieste, le cache della chat e del riepilogo si copiano su
disco una volta (agente-kv salva). Senza GPU, senza server: slot e agente-kv finti. Uso: python3 test_kv_disco.py"""
import tempfile
import time
from pathlib import Path

import riflesso as R  # noqa: F401  (percorsi e moduli come in produzione)
import riflesso_cache as CA
import riflesso_stato as S
import riflesso_comune as C

T = Path(tempfile.mkdtemp())
diario = []
C._diario = diario.append
CA._slot = lambda *a: None
CA.KV_RAM = T
CA.QUIETE_S = 1
finto = T / "agente-kv"
finto.write_text(f"#!/bin/sh\necho \"$1\" >> {T}/chiamate\necho 'agente-kv: chat.kv salvata'\n")
finto.chmod(0o755)
CA.SAM_KV = str(finto)


def chiamate():
    f = T / "chiamate"
    return f.read_text().split() if f.exists() else []


def aspetta(sec):
    time.sleep(sec)


# 1. pensatoio nello slot, nessuna richiesta: una copia dopo la quiete, una sola
S._cw[0] = "chat"
S._ultima_richiesta[0] = time.time()
CA._scambia("pensatoio")
aspetta(2.5)
assert chiamate() == ["salva"], chiamate()
aspetta(1.5)
assert chiamate() == ["salva"], "una copia sola per ingresso"
assert any("copia su disco" in str(x.get("cw", "")) for x in diario if isinstance(x, dict))
print("1 copia dopo la quiete: ok")

# 2. richieste continue: niente copia; la chat torna prima della quiete: niente copia
(T / "chiamate").unlink()
CA._scambia("chat")
CA._scambia("pensatoio")
for _ in range(4):
    S._ultima_richiesta[0] = time.time()
    aspetta(0.5)
assert chiamate() == [], "c'erano richieste: niente copia"
CA._scambia("chat")
aspetta(2.5)
assert chiamate() == [], "il pensatoio ha lasciato lo slot: niente copia"
print("2 richieste e ritorno della chat: ok")

# 3. richiesta in volo: si aspetta che finisca
CA._scambia("pensatoio")
S._ultima_richiesta[0] = time.time() - 10
S._altro_in_volo[0] = 1
aspetta(1.5)
assert chiamate() == [], "una richiesta in volo: niente copia"
S._altro_in_volo[0] = 0
aspetta(1.5)
assert chiamate() == ["salva"], chiamate()
print("3 richiesta in volo: ok")
print("test_kv_disco: TUTTO VERDE")
