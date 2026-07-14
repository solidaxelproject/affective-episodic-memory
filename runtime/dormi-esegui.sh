#!/usr/bin/env bash
# Lato host della dormita: eseguito (es. da una systemd path-unit) quando
# l'agente tocca .dormi-richiesto con runtime/dormi.sh.
# 14/07: le sessioni del gateway persistono su disco (group_sessions_per_user:
# false) e il solo restart del container non svuota più il contesto. La
# dormita ruota il session_id a container fermo, come farebbe /reset in chat:
# al risveglio la sessione è davvero fresca. Diario e ricordi non c'entrano:
# restano.
# Config: AGENT_CONTAINER (nome container), HERMES_VOLUME (volume ~/.hermes),
#         MATRIX_ROOM (stanza della chat principale).
CONTAINER="${AGENT_CONTAINER:-agent}"
VOLUME="${HERMES_VOLUME:-agent-hermes}"
ROOM="${MATRIX_ROOM:-!yourroom:example.local}"
FLAG=/data/workspace/memoria/.dormi-richiesto
[ -f "$FLAG" ] || exit 0
rm -f "$FLAG"
echo "$(date -Iseconds) riavvio $CONTAINER su richiesta dell'agente" >> /tmp/dormi.log
docker stop "$CONTAINER" >> /tmp/dormi.log 2>&1
docker run --rm --entrypoint python3 -v "$VOLUME":/h -e ROOM="$ROOM" \
  "$(docker inspect "$CONTAINER" --format '{{.Config.Image}}')" - \
  >> /tmp/dormi.log 2>&1 <<'PY'
import sqlite3, json, datetime, os, secrets
now = datetime.datetime.now()
nid = now.strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(4)
key = f"agent:main:matrix:group:{os.environ['ROOM']}"
c = sqlite3.connect("/h/state.db")
row = c.execute("SELECT entry_json FROM gateway_routing WHERE session_key=?",
                (key,)).fetchone()
if row:
    e = json.loads(row[0])
    e.update(session_id=nid, created_at=now.isoformat(),
             updated_at=now.isoformat(), last_prompt_tokens=0,
             is_fresh_reset=True, was_auto_reset=False,
             auto_reset_reason=None, reset_had_activity=False)
    c.execute("UPDATE gateway_routing SET entry_json=?, updated_at=? "
              "WHERE session_key=?", (json.dumps(e), now.timestamp(), key))
    c.commit()
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(f"sessione ruotata -> {nid}")
else:
    print("nessuna entry di routing: niente da ruotare")
c.close()
try:  # specchio legacy: il primario e' la tabella gateway_routing
    p = "/h/sessions/sessions.json"
    d = json.load(open(p))
    if key in d:
        d[key].update(session_id=nid, created_at=now.isoformat(),
                      updated_at=now.isoformat(), last_prompt_tokens=0,
                      is_fresh_reset=True)
        json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)
except Exception as ex:
    print("mirror sessions.json non aggiornato:", ex)
PY
docker start "$CONTAINER" >> /tmp/dormi.log 2>&1
