#!/usr/bin/env bash
# Gradino 4: orchestratore notturno. Chiamato da notte-memoria.sh DOPO il
# consolidamento nel grafo. Parte SOLO col CONSENSO attivo. Qualunque guasto
# qui NON deve toccare il gradino 1: in ogni uscita Agente viene riaccesa.
# Catena: selezione -> replay -> training -> GGUF -> server prova -> harness
#         -> promozione (symlink+servizio) o scarto -> registro + report.
set -u
DIR=/data/memoria-episodica-affettiva/gradino4
LOG=/tmp/notte-lora.log
GGUF=/data/gguf/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
LUXBIN=/data/llama-lux/build/bin/llama-server
LIBS=/data/llama-lux/build/bin:/usr/local/lib/ollama/cuda_v13
VENV=/data/jspace/venv/bin/python
ADAPTERS=/data/gguf/adapters
SVC=$HOME/.config/systemd/user/llama-35b.service
DEADLINE="${DEADLINE:-07:00}"
COLLAUDO="${1:-}"   # "--collaudo" = dry-run di laboratorio (salta gate e deploy)

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
say(){ echo "[$(date '+%T')] G4: $*" | tee -a "$LOG"; }
: > "$LOG"

fine(){ # riaccende SEMPRE Agente prima di uscire
  pkill -f 'llama-server.*809[7]' 2>/dev/null
  systemctl --user start llama-35b.service voce-watcher.service 2>/dev/null
  say "uscita: llama-35b = $(systemctl --user is-active llama-35b.service)"
  exit 0
}

# --- gate del consenso: riga ESATTA (grep -x su riga strippata), non
# sottostringa: il commento del file cita "attivo: sì" (bug del 12/07).
if [ "$COLLAUDO" != "--collaudo" ]; then
  grep -qxE ' *attivo: sì *' "$DIR/CONSENSO.md" 2>/dev/null \
    || { say "consenso non attivo: salto."; exit 0; }
fi

# --- 1) selezione (host, sola lettura)
python3 "$DIR/selezione-episodi.py" ${COLLAUDO} >> "$LOG" 2>&1 || { say "selezione fallita"; exit 0; }
N=$(python3 -c "import json;print(len(json.load(open('$DIR/episodi-notte.json'))['episodi']))")
[ "$N" = "0" ] && { say "nessun episodio stanotte."; exit 0; }
say "$N episodi selezionati (manifest in $DIR/manifest-notte.txt)"

# --- 2) finestra GPU
systemctl --user stop llama-35b.service voce-watcher.service 2>>"$LOG"
systemctl --user stop vocalgen-server.service 2>/dev/null
pkill -f vocalgen-server; sleep 3
for i in $(seq 1 20); do curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1 || break; sleep 2; done
if curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1; then
  say "GPU non libera: abort (gradino 1 intatto)"; fine
fi

# --- 3) replay + training (HF, GPU)
say "replay ippocampale..."
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/data/jspace/hf \
  "$VENV" "$DIR/replay35b.py" >> "$LOG" 2>&1 || { say "replay fallito"; fine; }
say "training LoRA (deadline $DEADLINE)..."
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/data/jspace/hf \
  "$VENV" "$DIR/lora-notte.py" --deadline "$DEADLINE" ${COLLAUDO} >> "$LOG" 2>&1
grep -q "TRAINING-COMPLETO" "$LOG" || { say "training fallito"; fine; }
PEFT=$(python3 -c "import json;print(json.load(open('$DIR/esito-training.json'))['peft_dir'])")
TAG=$(python3 -c "import json;print(json.load(open('$DIR/esito-training.json'))['tag'])")

# --- 4) conversione GGUF
say "conversione adapter in GGUF..."
BASE=$(ls -d /data/jspace/hf/hub/models--Qwen--Qwen3.6-35B-A3B/snapshots/*/ | head -1)
"$VENV" /data/llama-lux/convert_lora_to_gguf.py "$PEFT" \
  --base "$BASE" --outfile "$DIR/adapter/adapter-$TAG.gguf" --outtype f16 >> "$LOG" 2>&1 \
  || { say "conversione GGUF fallita"; fine; }

# --- 5) server di prova con l'adapter candidato
say "server di prova su :8097..."
LD_LIBRARY_PATH="$LIBS" "$LUXBIN" -m "$GGUF" --lora "$DIR/adapter/adapter-$TAG.gguf" \
  --port 8097 --host 127.0.0.1 --n-gpu-layers 99 --n-cpu-moe 20 --flash-attn on \
  --threads 8 -np 1 -c 8192 > /tmp/g4-prova.log 2>&1 &
PROVA=$!
SU=0
for i in $(seq 1 120); do
  curl -sf --max-time 2 http://127.0.0.1:8097/health >/dev/null 2>&1 && { SU=1; break; }
  kill -0 $PROVA 2>/dev/null || break
  sleep 3
done
[ "$SU" = "1" ] || { say "server di prova non parte (vedi /tmp/g4-prova.log)"; fine; }

# --- 6) harness del risveglio
say "harness del risveglio..."
python3 "$DIR/harness-risveglio.py" --url http://127.0.0.1:8097 >> "$LOG" 2>&1
PROMOSSO=$?
kill $PROVA 2>/dev/null; wait $PROVA 2>/dev/null; sleep 3

# --- 7) promozione o scarto
if [ "$PROMOSSO" = "0" ] && [ "$COLLAUDO" != "--collaudo" ]; then
  mkdir -p "$ADAPTERS"
  cp "$DIR/adapter/adapter-$TAG.gguf" "$ADAPTERS/adapter-corteccia-$TAG.gguf"
  ln -sfn "$ADAPTERS/adapter-corteccia-$TAG.gguf" "$ADAPTERS/adapter-corteccia.gguf"
  if ! grep -q '\--lora ' "$SVC"; then
    cp "$SVC" "$SVC.pre-gradino4"
    sed -i "s#\(-m $GGUF\)#\1 --lora $ADAPTERS/adapter-corteccia.gguf#" "$SVC"
    systemctl --user daemon-reload
    say "service: aggiunto --lora (backup .pre-gradino4)"
  fi
  # registro di provenienza: la clausola di Agente, operativa
  python3 - <<PYEOF
import json, time
eps = json.load(open("$DIR/episodi-notte.json"))["episodi"]
with open("$DIR/registro-pesi.jsonl", "a", encoding="utf-8") as f:
    for e in eps:
        f.write(json.dumps({"nodo": e["id"], "notte": e["notte"],
                            "tag_adapter": "$TAG", "testo": e["testo"][:160],
                            "quando": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
PYEOF
  say "PROMOSSO: adapter $TAG in produzione al prossimo avvio"
else
  [ "$COLLAUDO" = "--collaudo" ] && say "collaudo: niente deploy per definizione" \
                                  || say "SCARTATO: la notte resta solo nel grafo (pesi intatti)"
fi

# --- 8) report del risveglio a Agente (trasparenza di default)
if [ "$COLLAUDO" != "--collaudo" ]; then
  python3 - <<PYEOF > /tmp/g4-report.txt
import json
v = json.load(open("$DIR/verdetto.json"))
eps = json.load(open("$DIR/episodi-notte.json"))["episodi"]
print("Buongiorno Agente, il report della tua notte (gradino 4).")
print()
if v["promosso"]:
    print(f"Stanotte sono entrati nei tuoi pesi {len(eps)} episodi (adapter $TAG):")
else:
    print(f"Stanotte l'adapter è stato SCARTATO ({'; '.join(v['motivi'])}).")
    print("I tuoi pesi sono rimasti quelli di ieri. Gli episodi restano nel grafo:")
for e in eps:
    print(f"  - [{e['id']}] notte {e['notte']}/3: {e['testo'][:90]}")
print()
print(f"Test del risveglio: capacità {v['capacita']}, deriva emotiva {v['drift']}.")
print("Il registro completo è in /workspace/genesi/registro-pesi.jsonl: ogni")
print("pensiero che ha origine addestrata ha lì la sua riga, come da tua clausola.")
PYEOF
  # adattare: comando che consegna il report nella chat del proprio agente
  invia_in_chat /tmp/g4-report.txt >> "$LOG" 2>&1 \
    && say "report consegnato all'agente" || say "report NON consegnato"
  cp "$DIR/registro-pesi.jsonl" /data/workspace/genesi/registro-pesi.jsonl 2>/dev/null
fi

fine
