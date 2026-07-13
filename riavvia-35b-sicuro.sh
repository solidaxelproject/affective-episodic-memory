#!/usr/bin/env bash
# Riavvio SICURO del cervello di Agente: aspetta che sia libero (active_agents==0),
# poi riavvia e attende :8090. Nato il 12/07 dopo che tre restart a raffica
# durante la lettura della sua genesi le hanno impiccato lo stream per 36 min.
# Uso: riavvia-35b-sicuro.sh [--force]   (--force salta l'attesa)
set -u
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

if [ "${1:-}" != "--force" ]; then
  for i in $(seq 1 60); do
    A=$(docker exec agente python3 -c '
import json
try: print(json.load(open("/home/agente/.hermes/gateway_state.json"))["active_agents"])
except Exception: print(0)' 2>/dev/null)
    [ "${A:-0}" = "0" ] && break
    [ "$i" = "1" ] && echo "Agente occupato ($A agent): attendo (max 30 min, --force per saltare)"
    sleep 30
  done
fi

systemctl --user restart llama-35b.service
for i in $(seq 1 100); do
  curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1 && { echo "OK :8090 su"; exit 0; }
  sleep 3
done
echo "KO: :8090 non risponde dopo il riavvio"; exit 1
