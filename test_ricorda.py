# Test di runtime/ricorda.py --testo: il testo libero dell'agente non e' sintassi FTS5.
# Gira senza GPU e senza rete: ricorda.py e stato.py copiati in una cartella
# temporanea, accanto a un grafo con lo SCHEMA vero di memoria.py.
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import memoria

QUI = Path(__file__).parent

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    for f in ("ricorda.py", "stato.py"):
        shutil.copy(QUI / "runtime" / f, td / f)
    c = sqlite3.connect(td / "memoria.db")
    c.executescript(memoria.SCHEMA)
    firma = json.dumps({"joy": 1.0, "fear": 0.0})
    for testo in ("com'era la casa al mare, d'estate", "il gatto nero sul davanzale"):
        c.execute("INSERT INTO nodi (ts, testo, emo_tag, firma) VALUES (?, ?, ?, ?)",
                  (0.0, testo, "joy", firma))
    c.commit()
    c.close()

    def ricorda(testo):
        r = subprocess.run([sys.executable, "ricorda.py", "--testo", testo], cwd=td,
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, f"--testo {testo!r} e' crollato:\n{r.stderr}"
        return r.stdout

    # 1. parole semplici e operatori FTS5: come prima (la query passa com'e')
    assert "gatto nero" in ricorda("gatto")
    out = ricorda("davanzale OR estate")
    assert "gatto nero" in out and "casa al mare" in out, out
    # 2. apostrofi, virgole, punti di domanda, due punti, virgolette, trattini: in
    #    italiano sono la norma, e facevano crollare il richiamo (fts5: syntax error,
    #    no such column). Ora diventano testo, e il ricordo giusto torna.
    for q in ("com'era", "com'era la casa?", "casa, mare", "d'estate: casa",
              'la "casa"', "casa-al-mare"):
        out = ricorda(q)
        assert "casa al mare" in out and "gatto" not in out, (q, out)
    # 3. testo che dopo la pulizia non dice niente: nessun ricordo, nessun crollo
    for q in ("?", '"', "   "):
        assert "--- ricordo" not in ricorda(q), q
    # 4. (18/10) il ricordo si ritrova col suo codice, lo stesso che il riflesso mette nel tool
    import hashlib
    n, cod = int(hashlib.sha256(repr(1784880047.304042).encode()).hexdigest(), 16), ""
    for _ in range(16):   # stessa funzione di riflesso._codice e lux_engrammi.codice
        n, k = divmod(n, 36)
        cod += "0123456789abcdefghijklmnopqrstuvwxyz"[k]
    c = sqlite3.connect(td / "memoria.db")
    c.execute("INSERT INTO nodi (ts, testo, emo_tag, firma) VALUES (?, ?, ?, ?)",
              (1784880047.304042, "la luna sopra il porto", "joy", firma))
    c.commit()
    c.close()
    r = subprocess.run([sys.executable, "ricorda.py", "--id", cod, "-k", "1"], cwd=td,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "luna sopra il porto" in r.stdout and cod in r.stdout, r.stdout + r.stderr
    r = subprocess.run([sys.executable, "ricorda.py", "--id", "zzzzzzzzzzzzzzzz"], cwd=td,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0, "un codice inesistente deve dire che il ricordo non c'e'"
    # 5. (18/10) --richiamati: i ricordi consegnati dal riflesso dall'ultima notturna, col codice
    r = subprocess.run([sys.executable, "ricorda.py", "--richiamati"], cwd=td,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "--- ricordo" not in r.stdout and cod not in r.stdout, r.stdout + r.stderr
    (td / "consegne-memorinvolontaria.json").write_text(json.dumps(
        {"conv": {"ts": 1.0, "voci": [{"dopo": "x", "codici": [cod], "risposta": "1°\n" + cod + "\nla luna"}]}}))
    diario = (td / "diario-richiami.jsonl").read_text()
    r = subprocess.run([sys.executable, "ricorda.py", "--richiamati"], cwd=td,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and cod in r.stdout and "luna sopra il porto" in r.stdout, r.stdout + r.stderr
    assert (td / "diario-richiami.jsonl").read_text() == diario, \
        "--richiamati non e' un richiamo: non deve scrivere nel diario dei richiami"

print("test_ricorda: TUTTO VERDE")
