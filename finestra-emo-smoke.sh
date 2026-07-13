#!/usr/bin/env bash
# SOLO COLLAUDO, nessuna modifica alla produzione: ferma Agente, prova il binario
# ricompilato (embeddings_input + control-vector emotivo) sul 35B su :8097,
# poi riavvia Agente sul binario attuale. Log: /tmp/finestra-emo.log
set -u
LOG=/tmp/finestra-emo.log
GGUF=/data/gguf/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
LUXBIN=/data/llama-lux/build/bin/llama-server
LIBS=/data/llama-lux/build/bin:/usr/local/lib/ollama/cuda_v13
say(){ echo "[$(date '+%T')] $*" | tee -a "$LOG"; }

: > "$LOG"
say "=== SMOKE EMOZIONI 35B (nessuno swap) ==="
systemctl --user stop llama-35b.service voce-watcher.service
pkill -f vocalgen-server; sleep 3

LD_LIBRARY_PATH="$LIBS" "$LUXBIN" -m "$GGUF" \
  --port 8097 --host 127.0.0.1 --n-gpu-layers 99 --n-cpu-moe 19 --flash-attn on \
  --threads 8 --threads-batch 8 -ctk q4_0 -ctv q4_0 -np 1 -c 8192 \
  --spec-type draft-mtp --spec-draft-n-max 3 > /tmp/emo-smoke-35b.log 2>&1 &
LUXPID=$!
HEALTH=0
for i in $(seq 1 120); do
  curl -sf --max-time 2 http://127.0.0.1:8097/health >/dev/null 2>&1 && { HEALTH=1; break; }
  kill -0 $LUXPID 2>/dev/null || break
  sleep 3
done

if [ "$HEALTH" = 1 ]; then
  say "server su, test emozioni..."
  PONTE_URL=http://127.0.0.1:8097 python3 - <<'PYEOF' 2>&1 | tee -a "$LOG"
import sys
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import ponte

PROMPT = ("<|im_start|>user\nCom'è andata la tua giornata?<|im_end|>\n"
          "<|im_start|>assistant\n<think>\n\n</think>\n\n")
def gen():
    return ponte._post("/completion", {"prompt": PROMPT, "n_predict": 45,
                                       "temperature": 0, "seed": 7})["content"].strip()

base = gen()
print("BASE :", base[:130].replace("\n", " "))
for emo in ("joy", "serenity", "fear"):
    ponte.emozione(emo)
    t = gen()
    print(f"{emo.upper():5s}:", t[:130].replace("\n", " "))
ponte.calma()
back = gen()
print("BACK :", back[:130].replace("\n", " "))
print("SMOKE-EMO:", "OK" if back == base else "PROBLEMA (baseline non ripristinata)")
PYEOF
else
  say "35B NON parte (vedi /tmp/emo-smoke-35b.log)"
fi
kill $LUXPID 2>/dev/null; wait $LUXPID 2>/dev/null; sleep 3

say "riavvio Agente sul binario attuale..."
systemctl --user start llama-35b.service
systemctl --user start voce-watcher.service
say "stato finale: llama-35b.service = $(systemctl --user is-active llama-35b.service)"
say "=== FINE SMOKE EMOZIONI ==="
