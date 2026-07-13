# Estrae i messaggi recenti della stanza di Agente dal database Synapse -> JSONL.
# Legge SOLO il contenuto dei messaggi (tabella event_json), nessuna credenziale.
# Uso: python3 estrai-matrix.py [giorni] > messaggi.jsonl
import os
import json
import subprocess
import sys

ROOM = os.environ.get("MATRIX_ROOM", "!yourroom:example.local")
giorni = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

inner = f"""
import sqlite3, json, time
c = sqlite3.connect("/data/homeserver.db")
cutoff = (time.time() - {giorni} * 86400) * 1000
rows = c.execute(
    "SELECT ej.json FROM events e JOIN event_json ej ON e.event_id = ej.event_id "
    "WHERE e.room_id = ? AND e.type = 'm.room.message' AND e.origin_server_ts > ? "
    "ORDER BY e.origin_server_ts", ("{ROOM}", cutoff)).fetchall()
for (j,) in rows:
    print(j)
"""
out = subprocess.run(["docker", "exec", "-i", "synapse", "python3", "-", ],
                     input=inner, capture_output=True, text=True, check=True)

for line in out.stdout.splitlines():
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        continue
    c = ev.get("content", {})
    if c.get("msgtype") not in ("m.text", "m.notice"):
        continue
    body = c.get("body", "").strip()
    if not body:
        continue
    print(json.dumps({
        "ts": ev.get("origin_server_ts", 0) / 1000,
        "autore": ev.get("sender", ""),
        "testo": body,
    }, ensure_ascii=False))
