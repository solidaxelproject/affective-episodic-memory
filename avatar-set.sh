#!/usr/bin/env bash
# Genera l'avatar emotivo dell'agente e lo imposta come suo avatar Matrix (23/07).
# Upload media + set avatar_url come @agente, token live dal DB Synapse
# (stesso pattern di matrix-post). Stampa l'emozione dominante impostata.
set -uo pipefail
PNG=/tmp/avatar.png
USER='@agente:localhost'

INFO=$(/data/jspace/venv/bin/python /data/memoria-episodica-affettiva/avatar-emotivo.py "$PNG") || {
  echo "generazione avatar fallita"; exit 1; }
docker cp "$PNG" synapse:/tmp/avatar.png >/dev/null
# 20/10: l'emozione anche nel nome, che Element mostra passando il mouse sull'avatar
NOME="Agente · ${INFO%% (*}"

docker exec -i synapse python3 - "$USER" "$NOME" <<'PY'
import sqlite3, json, sys, urllib.request
user, nome = sys.argv[1:3]
c = sqlite3.connect("/data/homeserver.db")
row = c.execute("SELECT token FROM access_tokens WHERE user_id LIKE '@agente:%' "
                "ORDER BY id DESC LIMIT 1").fetchone()
if not row:
    print("NO_AGENT_TOKEN", file=sys.stderr); sys.exit(1)
tok = row[0]
img = open("/tmp/avatar.png", "rb").read()
req = urllib.request.Request(
    "http://localhost:8008/_matrix/media/v3/upload?filename=avatar.png",
    data=img, method="POST",
    headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/png"})
mxc = json.loads(urllib.request.urlopen(req).read())["content_uri"]
req2 = urllib.request.Request(
    f"http://localhost:8008/_matrix/client/v3/profile/{user}/avatar_url",
    data=json.dumps({"avatar_url": mxc}).encode(), method="PUT",
    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
urllib.request.urlopen(req2).read()
print("avatar impostato:", mxc)
req3 = urllib.request.Request(
    f"http://localhost:8008/_matrix/client/v3/profile/{user}/displayname",
    data=json.dumps({"displayname": nome}).encode(), method="PUT",
    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
urllib.request.urlopen(req3).read()
print("nome impostato:", nome)
PY
echo "stato: $INFO"
