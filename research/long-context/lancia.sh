#!/bin/bash
# Prova contesto lungo (11/10/2026): J-lens e steering con contesti veri fino a 140k token.
# Si lancia a mano, con l'agente e llama-35b SPENTI (la GPU serve tutta). Usa un llama-server di PROVA
# (copia di luxifer.cpp con /lux-read esteso, patch in lux-read-lungo.diff; percorso in $LUXIFER_PROVA) sulla porta 8099: la produzione non si tocca.
# Fase 1: lente (server -c 8192, la lettura lunga apre il suo contesto). Fase 2: steering (server -c 143360).
# Argomento facoltativo: "lente" o "steering" per una fase sola (default: tutte e due);
# "taratura" = prova del prefill colorato del riflesso (prova_prefill.py), poi dose e finestra delle
# 51 emozioni (tara_emozioni.py), server -c 143360. "layer" = steering_layer.py (ogni emozione su ogni layer
# L15-L32, 14 contesti fino a 140k, cache dei prefissi in slot/) poi analizza_layer.py (schede e pagina).
# "emovec" = vettori emotivi italiani contrastivi sul dataset diaristico (5-vettori-italiani/emovec_it.py).
# "paper" = vettori col metodo del paper workspace: J-lens per le parole di un token, template lens per le altre (6-template-lens/).
set -u
D=/data/memoria-episodica-affettiva/research/long-context; cd $D
BIN=${LUXIFER_PROVA:-/data/luxifer-prova}/build-prova/bin/llama-server
GGUF=/data/gguf/occamy-1.0/occamy-1.0-Q8_0.gguf
PY=/data/jspace/venv/bin/python
systemctl --user is-active --quiet llama-35b && { echo "llama-35b e' acceso: spegnilo prima (lo decidi tu)"; exit 1; }
USATA=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
[ "$USATA" -gt 2600 ] && { echo "GPU gia' occupata ($USATA MiB, oltre la voce residente): fermo"; exit 1; }
[ -s dati/contesti.json ] || HF_HOME=/data/jspace/hf HF_HUB_OFFLINE=1 $PY dati/estrai_contesti.py ${SESSIONI:?id delle sessioni del gateway} || exit 1

server() {   # $1 = contesto del server
  $BIN -m $GGUF --port 8099 --host 127.0.0.1 --n-gpu-layers 99 --n-cpu-moe 34 --flash-attn on \
    --threads 8 --threads-batch 8 -np 1 -c $1 --repeat-penalty 1.1 --slot-save-path $D/4-steering-per-layer/slot/ > server-$1.log 2>&1 &
  SPID=$!
  for i in $(seq 1 300); do curl -sf -m 2 http://127.0.0.1:8099/health >/dev/null && return 0; kill -0 $SPID 2>/dev/null || break; sleep 2; done
  echo "il server di prova non parte: vedi server-$1.log"; kill $SPID 2>/dev/null; exit 1
}
trap 'kill $SPID 2>/dev/null' EXIT

FASI=${1:-lente steering}
if [[ $FASI == *lente* ]]; then
echo "== fase 1: lente $(date +%T)"
server 8192
HF_HOME=/data/jspace/hf $PY -u 1-lente/prova_lente.py 2>&1 | tee 1-lente/log-lente.txt
kill $SPID; wait $SPID 2>/dev/null; sleep 5
fi
if [[ $FASI == emovec ]]; then
echo "== vettori italiani $(date +%T)"
server 8192
$PY -u 5-vettori-italiani/emovec_it.py 2>&1 | tee -a 5-vettori-italiani/log-emovec.txt
echo "== fine $(date +%T)"
exit 0
fi
if [[ $FASI == confronto ]]; then
echo "== confronto vettori italiani / inglesi $(date +%T)"
mkdir -p 4-steering-per-layer/slot
server 143360
HF_HOME=/data/jspace/hf HF_HUB_OFFLINE=1 $PY -u 4-steering-per-layer/steering_layer.py confronto 2>&1 | tee -a 4-steering-per-layer/log-confronto.txt
echo "== fine $(date +%T)"
exit 0
fi

if [[ $FASI == paper ]]; then
echo "== vettori col metodo del paper (J-lens + template lens) $(date +%T)"
server 8192
HF_HOME=/data/jspace/hf HF_HUB_OFFLINE=1 $PY -u 6-template-lens/estrai_vettori.py 2>&1 | tee -a 6-template-lens/log-estrai.txt
echo "== fine $(date +%T)"
exit 0
fi
if [[ $FASI == layer ]]; then
echo "== steering per layer $(date +%T)"
mkdir -p 4-steering-per-layer/slot
server 143360
HF_HOME=/data/jspace/hf HF_HUB_OFFLINE=1 $PY -u 4-steering-per-layer/steering_layer.py 2>&1 | tee -a 4-steering-per-layer/log-layer.txt
$PY -u 4-steering-per-layer/analizza_layer.py 2>&1 | tee -a 4-steering-per-layer/log-layer.txt
echo "== fine $(date +%T)"
exit 0
fi
if [[ $FASI == taratura ]]; then
echo "== taratura $(date +%T)"
server 143360
HF_HOME=/data/jspace/hf HF_HUB_OFFLINE=1 $PY -u 3-taratura/prova_prefill.py 2>&1 | tee 3-taratura/log-prefill.txt
$PY -u 3-taratura/tara_emozioni.py 2>&1 | tee 3-taratura/log-taratura.txt
echo "== fine $(date +%T): $D/3-taratura/taratura-emozioni.json, /data/jspace/out-occamy/emo-cvec-v3.npz"
exit 0
fi
[[ $FASI == *steering* ]] || exit 0

echo "== fase 2: steering $(date +%T)"
server 143360
$PY -u 2-steering/prova_steering.py 2>&1 | tee 2-steering/log-steering.txt
echo "== fine $(date +%T): risultati in $D/1-lente/risultati-lente.json e $D/2-steering/risultati-steering.json"
