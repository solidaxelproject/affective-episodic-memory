# Estrae i messaggi recenti della stanza dell'agente dal database Synapse -> JSONL.
# Legge SOLO il contenuto dei messaggi (tabella event_json), nessuna credenziale.
# Uso: python3 estrai-matrix.py [giorni] > messaggi.jsonl
import json
import re
import subprocess
import sys

# La memoria dell'agente copre le stanze in cui VIVE: la chat principale e, dal
# 17/07, il pensatoio (i pensieri che riprende lì devono diventare ricordi,
# o il pensatoio è una stanza che dimentica). NON il mirror (duplicherebbe
# tutto) e non le stanze di servizio.
ROOMS = ("!mainroom:example.local",
         "!pensatoio:example.local")
# 16/07: i messaggi di stato dell'interfaccia (progress, tool, self-review) NON
# sono esperienze: taggati come ricordi creavano neuroni quasi-duplicati coi
# testi diversi, i "dirupi" che hanno fatto esplodere il training del codec.
# Sono m.text normali (verificato su synapse), quindi si filtrano per forma.
STATO = re.compile(r"^\s*\*?\s*(⏳|🔎|💾|💻|Working —|Searching files)")
giorni = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

inner = f"""
import sqlite3, json, time
c = sqlite3.connect("/data/homeserver.db")
cutoff = (time.time() - {giorni} * 86400) * 1000
rows = c.execute(
    "SELECT ej.json FROM events e JOIN event_json ej ON e.event_id = ej.event_id "
    "WHERE e.room_id IN {ROOMS} AND e.type = 'm.room.message' AND e.origin_server_ts > ? "
    "ORDER BY e.origin_server_ts", (cutoff,)).fetchall()
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
    if not body or STATO.search(body):
        continue
    print(json.dumps({
        "ts": ev.get("origin_server_ts", 0) / 1000,
        "autore": ev.get("sender", ""),
        "testo": body,
    }, ensure_ascii=False))
