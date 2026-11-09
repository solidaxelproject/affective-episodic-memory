"""09/11: l'emozione dominante di un ricordo ha sempre un vettore di steering. 09/11 sera: la piu' forte;
se non ha vettore, la vicina nello stesso petalo che lo ha (la media), altrimenti la piu' forte fra quelle con vettore.
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

# la distrazione e' la piu' forte ma non ha vettore: vince la sorpresa, la media del suo petalo (prima: l'interesse)
f = {"distraction": 2.1, "interest": 1.4, "joy": 0.3, "acceptance": 1.9}
assert memoria.dominante(f) == "surprise"
assert memoria.dominante({"joy": 0.5, "fear": 1.0}) == "fear"
# l'esempio dell'utente: malinconia 3.0 e gioia 2.5 -> tristezza (non la gioia)
assert memoria.dominante({"pensiveness": 3.0, "joy": 2.5, "sadness": 1.0}) == "sadness"
# le 8 della ruota senza vettore -> la media del petalo, che ha il vettore
for lieve, media in [("accettazione", "fiducia"), ("apprensione", "paura"), ("distrazione", "sorpresa"),
                     ("malinconia", "tristezza"), ("noia", "disgusto"), ("ribrezzo", "disgusto"),
                     ("fastidio", "rabbia"), ("furia", "rabbia")]:
    assert memoria.dominante({IT[lieve]: 2.0, "joy": 1.0}) == IT[media], lieve
    assert IT[media] in memoria.CON_VETTORE
# un'emozione con vettore piu' forte vince sempre su se stessa
assert memoria.dominante({"terror": 2.0, "fear": 1.0}) == "terror"
assert memoria.dominante({"love": 2.0, "joy": 1.9}) == "love"
# senza petalo e senza vettore (indignazione): la piu' forte fra quelle con vettore
assert memoria.dominante({"outrage": 3.0, "joy": 1.0, "fear": 2.0}) == "fear"
# ogni dominante ha il vettore, anche con firme di soli assi senza vettore
assert memoria.dominante({"boredom": 0.2, "annoyance": 0.9}) == "anger"

# migrazione su una copia: cambia solo emo_tag dei ricordi con dominante senza vettore, salienza e firma intatte
d = tempfile.mkdtemp()
db = os.path.join(d, "memoria.db")
c = sqlite3.connect(db)
c.execute("CREATE TABLE nodi (id INTEGER PRIMARY KEY, emo_tag TEXT, firma TEXT, salienza REAL)")
c.executemany("INSERT INTO nodi VALUES (?, ?, ?, ?)", [
    (1, "distraction", json.dumps(f), 2.1),
    (2, "joy", json.dumps({"joy": 1.5, "boredom": 0.4}), 1.5),
    (3, "annoyance", json.dumps({"annoyance": 0.9, "boredom": 0.2}), 0.9)])   # 09/11 sera: -> rabbia (petalo)
c.commit()
c.close()
qui = os.path.dirname(os.path.abspath(__file__))
out = subprocess.run([sys.executable, os.path.join(qui, "migra_dominante.py"), db], capture_output=True, text=True)
assert out.returncode == 0, out.stderr
c = sqlite3.connect(db)
righe = c.execute("SELECT id, emo_tag, salienza FROM nodi ORDER BY id").fetchall()
assert righe == [(1, "surprise", 2.1), (2, "joy", 1.5), (3, "anger", 0.9)], righe
assert os.path.exists(db + ".bak-pre-dominante"), "manca la copia del db"
# idempotente
out = subprocess.run([sys.executable, os.path.join(qui, "migra_dominante.py"), db], capture_output=True, text=True)
assert out.returncode == 0 and "0 ricordi" in out.stdout, out.stdout
shutil.rmtree(d)
print("test_dominante: TUTTO VERDE")
