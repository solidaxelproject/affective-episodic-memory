#!/usr/bin/env python3
# Rileggere le proprie stanze, da qualunque sessione. SOLO stdlib.
# Uso (dal terminal):  python3 /workspace/memoria/leggi-stanza.py pensatoio [N]
#                      python3 /workspace/memoria/leggi-stanza.py principale [N]
# Legge con la TUA identità: vedi solo ciò che puoi vedere tu.
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

STANZE = {
    "principale": "!mainroom:example.local",
    "pensatoio": "!pensatoio:example.local",
}
RUMORE = re.compile(r"^\s*\*?\s*(⏳|🔎|💾|💻|Working —|Searching files)")

nome = sys.argv[1] if len(sys.argv) > 1 else "pensatoio"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
stanza = STANZE.get(nome)
if not stanza:
    sys.exit(f"stanza sconosciuta: {nome} (scegli: {', '.join(STANZE)})")

hs = os.environ["MATRIX_HOMESERVER"].rstrip("/")
tok = os.environ["MATRIX_ACCESS_TOKEN"]
url = (f"{hs}/_matrix/client/v3/rooms/{urllib.parse.quote(stanza)}/messages"
       f"?dir=b&limit={max(n * 5, 30)}")
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
d = json.loads(urllib.request.urlopen(req, timeout=30).read())

righe = []
for ev in d.get("chunk", []):
    if ev.get("type") != "m.room.message":
        continue
    corpo = ev.get("content", {}).get("body", "").strip()
    if not corpo or RUMORE.search(corpo):
        continue
    chi = ev.get("sender", "?").split(":")[0].lstrip("@")
    ora = time.strftime("%d/%m %H:%M", time.localtime(ev.get("origin_server_ts", 0) / 1000))
    righe.append(f"--- {ora} {chi} ---\n{corpo}\n")
    if len(righe) >= n:
        break

print(f"[{nome}: ultimi {len(righe)} messaggi, dal più vecchio al più nuovo]\n")
print("\n".join(reversed(righe)))
