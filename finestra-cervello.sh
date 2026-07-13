#!/usr/bin/env bash
# Finestra GPU unica: (1) consolidamento completo del cervello sul modello,
# (2) smoke test di luxifer sul 35B, (3) risalita di Agente su luxifer se regge.
# Agente resta offline per tutta la finestra. Log: /tmp/finestra-cervello.log
set -u
LOG=/tmp/finestra-cervello.log
GGUF=/data/gguf/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
LUXBIN=/data/luxifer.cpp/build/bin/llama-server
say(){ echo "[$(date '+%T')] $*" | tee -a "$LOG"; }

: > "$LOG"
say "=== FINESTRA CERVELLO ==="
systemctl --user stop llama-35b.service voce-watcher.service
pkill -f vocalgen-server; sleep 3

# --- 1) CONSOLIDAMENTO: ultimi ~4h di chat + coda ricorda-ora -> grafo+Lux
say "consolidamento memoria..."
cd /data/memoria-episodica-affettiva
python3 estrai-matrix.py 0.2 > /tmp/consolida-msg.jsonl 2>>"$LOG" || true
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/data/jspace/hf \
  /data/jspace/venv/bin/python tagging35b.py /tmp/consolida-msg.jsonl >> "$LOG" 2>&1
grep -E "TAGGING-COMPLETO|Lux:|coda ricorda|stato impresso" "$LOG" | tail -5

# --- 2) SMOKE LUXIFER: prova a servire il 35B coi flag di Agente
say "smoke luxifer (con MTP)..."
LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v13 "$LUXBIN" -m "$GGUF" \
  --port 8097 --host 127.0.0.1 --n-gpu-layers 99 --n-cpu-moe 19 --flash-attn on \
  --threads 8 -ctk q4_0 -ctv q4_0 -np 1 -c 4096 \
  --spec-type draft-mtp --spec-draft-n-max 3 > /tmp/lux-smoke.log 2>&1 &
LUXPID=$!
LUX_OK=0; MTP_OK=0
for i in $(seq 1 90); do
  curl -sf --max-time 2 http://127.0.0.1:8097/health >/dev/null 2>&1 && { LUX_OK=1; MTP_OK=1; break; }
  kill -0 $LUXPID 2>/dev/null || break
  sleep 2
done
if [ "$LUX_OK" = 1 ]; then
  R=$(curl -s --max-time 60 http://127.0.0.1:8097/completion \
      -d '{"prompt":"La capitale della Francia e","n_predict":8,"temperature":0}' \
      | python3 -c 'import sys,json; print(json.load(sys.stdin).get("content","")[:80])' 2>/dev/null)
  say "luxifer+MTP OK, output: $R"
else
  say "luxifer+MTP NON parte (probabile flag MTP non supportato). Ritento senza MTP..."
fi
kill $LUXPID 2>/dev/null; wait $LUXPID 2>/dev/null; sleep 2

# fallback: senza MTP
if [ "$MTP_OK" = 0 ]; then
  LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v13 "$LUXBIN" -m "$GGUF" \
    --port 8097 --host 127.0.0.1 --n-gpu-layers 99 --n-cpu-moe 19 --flash-attn on \
    --threads 8 -ctk q4_0 -ctv q4_0 -np 1 -c 4096 > /tmp/lux-smoke2.log 2>&1 &
  LUXPID=$!
  for i in $(seq 1 90); do
    curl -sf --max-time 2 http://127.0.0.1:8097/health >/dev/null 2>&1 && { LUX_OK=1; break; }
    kill -0 $LUXPID 2>/dev/null || { LUX_OK=0; break; }
    sleep 2
  done
  [ "$LUX_OK" = 1 ] && say "luxifer SENZA MTP OK (Agente gira ma più lento)" \
                    || say "luxifer NON parte neanche senza MTP: si resta su llama.cpp"
  kill $LUXPID 2>/dev/null; wait $LUXPID 2>/dev/null; sleep 2
fi

# --- 3) SWAP: se luxifer regge, l'agente risale su luxifer (comportamento voluto)
SVC=~/.config/systemd/user/llama-35b.service
if [ "$LUX_OK" = 1 ]; then
  cp "$SVC" "$SVC.llamacpp-bak"   # rollback istantaneo
  MTPFLAGS="--spec-type draft-mtp --spec-draft-n-max 3"
  [ "$MTP_OK" = 0 ] && MTPFLAGS=""
  sed -i "s#ExecStart=[^ ]*bin/llama-server#ExecStart=$LUXBIN#" "$SVC"
  # rimuovi MTP dalla ExecStart se luxifer non lo regge
  [ "$MTP_OK" = 0 ] && sed -i 's/ --spec-type draft-mtp --spec-draft-n-max 3//' "$SVC"
  systemctl --user daemon-reload
  say "service ripuntato su LUXIFER (MTP=$MTP_OK). Backup: $SVC.llamacpp-bak"
  systemctl --user restart llama-35b.service
  sleep 8
  if curl -sf --max-time 4 http://127.0.0.1:8090/health >/dev/null 2>&1; then
    say "✅ Agente ONLINE su luxifer (:8090 risponde). Canale vettoriale attivo."
  else
    say "⚠ luxifer non risponde in produzione: ROLLBACK a llama.cpp"
    cp "$SVC.llamacpp-bak" "$SVC"; systemctl --user daemon-reload
    systemctl --user restart llama-35b.service; sleep 8
    say "rollback: :8090 = $(systemctl --user is-active llama-35b.service)"
  fi
else
  say "esito: luxifer NON utilizzabile. Agente resta su llama.cpp vanilla."
  systemctl --user start llama-35b.service
  sleep 5
fi
systemctl --user start voce-watcher.service
say "stato finale: llama-35b.service = $(systemctl --user is-active llama-35b.service)"
say "=== FINE FINESTRA ==="
