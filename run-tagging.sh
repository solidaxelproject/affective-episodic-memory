#!/usr/bin/env bash
set -u
# Da cron systemctl --user non trova il bus (OOM del 12/07: llama restava sulla
# GPU durante il tagging): ambiente ricostruito + verifica che la GPU sia libera.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
systemctl --user stop llama-35b.service voce-watcher.service
systemctl --user stop vocalgen-server.service 2>/dev/null
pkill -f 'vocalgen-serve[r]' 2>/dev/null  # TTS: 1.5GB GPU, riparte solo; [r] = mai auto-match
sleep 3
for i in $(seq 1 20); do
  curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1 || break
  sleep 2
done
if curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1; then
  echo "ABORT tagging: llama-35b ancora su :8090, GPU non libera (stop fallito?)" \
    > /data/memoria-episodica-affettiva/tagging.log
  systemctl --user start llama-35b.service voce-watcher.service
  exit 1
fi
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/data/jspace/hf \
  /data/jspace/venv/bin/python /data/memoria-episodica-affettiva/tagging35b.py "$1" \
  > /data/memoria-episodica-affettiva/tagging.log 2>&1
RC=$?
systemctl --user start llama-35b.service voce-watcher.service
echo "rc=$RC llama=$(systemctl --user is-active llama-35b.service)"
grep "TAGGING-COMPLETO" /data/memoria-episodica-affettiva/tagging.log || tail -5 /data/memoria-episodica-affettiva/tagging.log
