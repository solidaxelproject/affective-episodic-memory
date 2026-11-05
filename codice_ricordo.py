"""Codice del ricordo che l'agente vede (11/10): SHA-256 del timestamp, 16 caratteri [0-9a-z].
B7 (01/11, P4 di engrammi/PIANO-FIRMA-ENGRAMMI.md): un solo posto per lux_engrammi e il riflesso; solo libreria standard
(il riflesso gira col python3 di sistema). ricorda.py, nel container, tiene la sua copia: engrammi/test_codice.py le
confronta."""
import hashlib


def codice(ts):
    n, s = int(hashlib.sha256(repr(ts).encode()).hexdigest(), 16), ""
    for _ in range(16):
        n, r = divmod(n, 36)
        s += "0123456789abcdefghijklmnopqrstuvwxyz"[r]
    return s
