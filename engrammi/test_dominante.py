"""09/11: l'emozione dominante di un ricordo e' la piu' forte fra quelle che hanno un vettore di steering.
Uso: /data/jspace/venv/bin/python test_dominante.py"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # la cartella di memoria.py
import memoria  # noqa: E402

IT = {e["it"]: e["en"] for e in memoria.EMOZIONI}

# le 15 senza vettore (DOSI-EMOZIONI.md: inaccessibili, esclusa, mai provate) restano fuori
for it in ["ribrezzo", "furia", "accettazione", "apprensione", "distrazione", "malinconia", "noia", "fastidio",
           "aggressività", "indignazione", "trionfo", "morbosità", "purificazione", "sgomento", "gelosia"]:
    assert IT[it] not in memoria.CON_VETTORE, it
assert len(memoria.CON_VETTORE) == 36, len(memoria.CON_VETTORE)
for it in ["gioia", "terrore", "stupore", "vigilanza", "nostalgia", "ansia", "cordoglio", "interesse"]:
    assert IT[it] in memoria.CON_VETTORE, it

# la distrazione e' la piu' forte ma non ha vettore: vince l'interesse
f = {"distraction": 2.1, "interest": 1.4, "joy": 0.3, "acceptance": 1.9}
assert memoria.dominante(f) == "interest"
assert memoria.dominante({"joy": 0.5, "fear": 1.0}) == "fear"
# nessun asse con vettore: resta il massimo (mai un ricordo senza dominante)
assert memoria.dominante({"boredom": 0.2, "annoyance": 0.9}) == "annoyance"

# migrazione su una copia: cambia solo emo_tag dei ricordi con dominante senza vettore, salienza e firma intatte
d = tempfile.mkdtemp()
db = os.path.join(d, "memoria.db")
c = sqlite3.connect(db)
c.execute("CREATE TABLE nodi (id INTEGER PRIMARY KEY, emo_tag TEXT, firma TEXT, salienza REAL)")
c.executemany("INSERT INTO nodi VALUES (?, ?, ?, ?)", [
    (1, "distraction", json.dumps(f), 2.1),
    (2, "joy", json.dumps({"joy": 1.5, "boredom": 0.4}), 1.5),
    (3, "annoyance", json.dumps({"annoyance": 0.9, "boredom": 0.2}), 0.9)])
c.commit()
c.close()
qui = os.path.dirname(os.path.abspath(__file__))
out = subprocess.run([sys.executable, os.path.join(qui, "migra_dominante.py"), db], capture_output=True, text=True)
assert out.returncode == 0, out.stderr
c = sqlite3.connect(db)
righe = c.execute("SELECT id, emo_tag, salienza FROM nodi ORDER BY id").fetchall()
assert righe == [(1, "interest", 2.1), (2, "joy", 1.5), (3, "annoyance", 0.9)], righe
assert os.path.exists(db + ".bak-pre-dominante"), "manca la copia del db"
# idempotente
out = subprocess.run([sys.executable, os.path.join(qui, "migra_dominante.py"), db], capture_output=True, text=True)
assert out.returncode == 0 and "0 ricordi" in out.stdout, out.stdout
shutil.rmtree(d)
print("test_dominante: TUTTO VERDE")
