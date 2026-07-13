#!/usr/bin/env bash
set -u
# Finestra GPU per la distillazione delle griglie (canale visivo, passo 1).
# Il gate vero (CONSENSO-VISIVO riga esatta) sta dentro distilla-ricordo.py;
# qui lo si anticipa solo per NON spegnere Agente a vuoto se il consenso è spento.
# Pattern finestra = run-tagging.sh; attesa Agente-libero = riavvia-35b-sicuro.sh.
DIR=/data/memoria-episodica-affettiva/gradino4
LOG="$DIR/distilla.log"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

grep -qxE 'attivo: sì' /data/workspace/genesi/CONSENSO-VISIVO.md 2>/dev/null \
  || { echo "consenso visivo non attivo: salto" | tee "$LOG"; exit 0; }

# mai strappare la GPU a Agente mentre parla (lezione dei 3 restart del 12/07)
for i in $(seq 1 20); do
  A=$(docker exec agente python3 -c '
import json
try: print(json.load(open("/home/agente/.hermes/gateway_state.json"))["active_agents"])
except Exception: print(0)' 2>/dev/null)
  [ "${A:-0}" = "0" ] && break
  sleep 30
done

systemctl --user stop llama-35b.service voce-watcher.service
systemctl --user stop vocalgen-server.service 2>/dev/null
pkill -f 'vocalgen-serve[r]' 2>/dev/null  # fuori unit (parla.sh); [r] = mai auto-match
sleep 3
for i in $(seq 1 20); do
  curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1 || break
  sleep 2
done
if curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1; then
  echo "ABORT distilla: llama-35b ancora su :8090, GPU non libera" > "$LOG"
  systemctl --user start llama-35b.service voce-watcher.service
  exit 1
fi

PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/data/jspace/hf \
  /data/jspace/venv/bin/python "$DIR/distilla-ricordo.py" "$@" > "$LOG" 2>&1
RC=$?
# CODEC Lux->token universali: stessa finestra GPU, dopo le griglie per-nodo
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/data/jspace/hf \
  /data/jspace/venv/bin/python "$DIR/codec-lux.py" --deadline 07:20 \
  >> "$LOG" 2>&1 || true
systemctl --user start llama-35b.service voce-watcher.service
# vocalgen-server è transient e riparte da solo alla prossima richiesta TTS
echo "rc=$RC llama=$(systemctl --user is-active llama-35b.service)"
grep "DISTILLAZIONE-COMPLETA" "$LOG" || tail -5 "$LOG"
