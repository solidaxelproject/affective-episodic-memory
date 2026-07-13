#!/usr/bin/env bash
# SOLO COLLAUDO, nessuna modifica alla produzione: ferma Agente, prova il 35B su
# llama-lux b9966 (flag di Agente, MTP) con test identità embeddings_input,
# poi riavvia Agente sul binario ATTUALE. Log: /tmp/finestra-lux.log
set -u
LOG=/tmp/finestra-lux.log
GGUF=/data/gguf/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
LUXBIN=/data/llama-lux/build/bin/llama-server
LIBS=/data/llama-lux/build/bin:/usr/local/lib/ollama/cuda_v13
say(){ echo "[$(date '+%T')] $*" | tee -a "$LOG"; }

: > "$LOG"
say "=== SMOKE LUX PORT 35B (b9966, nessuno swap) ==="
systemctl --user stop llama-35b.service voce-watcher.service
pkill -f vocalgen-server; sleep 3

say "avvio llama-lux 35B (MTP)..."
LD_LIBRARY_PATH="$LIBS" "$LUXBIN" -m "$GGUF" \
  --port 8097 --host 127.0.0.1 --n-gpu-layers 99 --n-cpu-moe 19 --flash-attn on \
  --threads 8 --threads-batch 8 -ctk q4_0 -ctv q4_0 -np 1 -c 8192 \
  --spec-type draft-mtp --spec-draft-n-max 3 > /tmp/lux-smoke-35b.log 2>&1 &
LUXPID=$!
HEALTH=0
for i in $(seq 1 120); do
  curl -sf --max-time 2 http://127.0.0.1:8097/health >/dev/null 2>&1 && { HEALTH=1; break; }
  kill -0 $LUXPID 2>/dev/null || break
  sleep 3
done

if [ "$HEALTH" = 1 ]; then
  say "server su, test identità prompt vs embeddings_input..."
  python3 - <<'PYEOF' 2>&1 | tee -a "$LOG"
import json, urllib.request
U = "http://127.0.0.1:8097"
def post(p, d, t=600):
    r = urllib.request.Request(U + p, data=json.dumps(d).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read())
P = "La capitale della Francia è"
base = post("/completion", {"prompt": P, "n_predict": 12, "temperature": 0, "seed": 7})["content"]
emb  = post("/input-embeddings", {"content": P})[0]["embedding"]
out  = post("/completion", {"embeddings_input": emb, "n_predict": 12, "temperature": 0, "seed": 7})["content"]
print("BASE:", base[:80].replace("\n", " "))
print("EMBD:", out[:80].replace("\n", " "))
print("SMOKE35B:", "OK" if base[:40] == out[:40] else "DIVERSI")
PYEOF
else
  say "llama-lux 35B NON parte (vedi /tmp/lux-smoke-35b.log)"
fi
kill $LUXPID 2>/dev/null; wait $LUXPID 2>/dev/null; sleep 3

say "riavvio Agente sul binario attuale (nessuna modifica)..."
systemctl --user start llama-35b.service
systemctl --user start voce-watcher.service
say "stato finale: llama-35b.service = $(systemctl --user is-active llama-35b.service)"
say "=== FINE SMOKE ==="
