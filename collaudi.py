# Collaudi: tutte le verifiche che girano senza GPU, senza modello e senza rete,
# una dopo l'altra: le auto-verifiche dei moduli e i test_*.py della radice.
# Uso: python3 collaudi.py   (numpy; torch per memoria.py). Esce con 1 se una fallisce.
# Gira anche su GitHub a ogni push e a ogni PR: .github/workflows/collaudi.yml.
# Un test_*.py nuovo entra da solo; un'auto-verifica nuova si aggiunge qui sotto.
import os
import subprocess
import sys
from pathlib import Path

QUI = Path(__file__).parent

AUTOVERIFICHE = [   # (argomenti, variabili d'ambiente in più)
    (["demo.py"], {}),
    (["lux.py"], {}),
    (["persistenza.py"], {}),
    (["memoria.py"], {}),
    (["runtime/stato.py", "--imprimi-test"], {}),
    (["ponte.py"], {"PONTE_SELFCHECK": "1"}),
]


def collauda(argomenti, extra):
    """Una verifica nella radice del repo: (riuscita, ultima riga o coda dell'output)."""
    r = subprocess.run([sys.executable, *argomenti], cwd=QUI, env={**os.environ, **extra},
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    righe = [x for x in (r.stdout + r.stderr).splitlines() if x.strip()]
    if r.returncode == 0:
        return True, righe[-1] if righe else ""
    return False, "\n".join("      " + x for x in righe[-20:])


if __name__ == "__main__":
    lista = AUTOVERIFICHE + [([p.name], {}) for p in sorted(QUI.glob("test_*.py"))]
    falliti = 0
    for argomenti, extra in lista:
        nome = " ".join(argomenti)
        ok, uscita = collauda(argomenti, extra)
        if ok:
            print(f"OK    {nome}  ->  {uscita}")
        else:
            falliti += 1
            print(f"FAIL  {nome}\n{uscita}")
    print(f"\n{len(lista) - falliti}/{len(lista)} collaudi OK")
    sys.exit(1 if falliti else 0)
