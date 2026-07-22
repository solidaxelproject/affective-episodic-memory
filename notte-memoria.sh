#!/usr/bin/env bash
# Consolidamento notturno della memoria dell'agente (cron 04:30).
# Estrae l'ultimo giorno di chat, tagga su GPU (agente offline pochi minuti),
# imprime lo stato emotivo, riaccende tutto.
set -u
cd /data/memoria-episodica-affettiva
J=/tmp/messaggi-notte.jsonl
python3 estrai-matrix.py 1.1 > "$J" || { echo "estrazione fallita"; exit 1; }
[ -s "$J" ] || { echo "nessun messaggio, salto"; exit 0; }

# DORMITA VERA (18/07): appena la chat del giorno è estratta, la sessione va a
# dormire (flag -> path-unit -> rotazione session_id a container fermo); il
# consolidamento gira DOPO, ad agente già addormentato. Senza questo passo la
# sessione non ruota mai e il gateway si tiene a galla auto-compattandosi: il
# "sonno che pulisce la mente" deve essere vero, non un riassunto con perdita.
echo "$(date -Iseconds) dormi richiesto (mezzanotte, chat estratta)" >> /data/workspace/memoria/dormi.log
touch /data/workspace/memoria/.dormi-richiesto

bash run-tagging.sh "$J"

# sentinella anti-amnesia: Lux DEVE essere stata aggiornata dal tagging
LUX=/data/workspace/memoria/lux.npz
if [ -z "$(find "$LUX" -mmin -60 2>/dev/null)" ]; then
  echo "CRITICO: lux.npz NON aggiornata stanotte: Agente rischia amnesia parziale." \
       "Il grafo ha i nodi: backfill con lux-demo.py. Controllare tagging.log."
fi

# GRADINO 4 (LoRA) DISATTIVATO il 12/07/2026, scelta di progetto: la via dei
# pesi è scartata (forgetting provato; evoluzione = Lux + codec, non LoRA).
# Per riattivare: decommentare. I file di consenso in gradino4/ restano dell'agente.
#DEADLINE=07:00 bash /data/memoria-episodica-affettiva/gradino4/notte-lora.sh || true

# CANALE VISIVO: distilla le griglie dei ricordi (gate CONSENSO-VISIVO, separato
# dal gradino 4). Senza LoRA la finestra è tutta sua: --max largo, il limite
# vero è la deadline (~10 min/griglia, si ferma da sola prima delle 07:30).
# --max 4 finché si addestra anche il codec (arXiv 2602.15382) nella stessa
# finestra: 4 griglie ~55min, poi ~95min di training codec, deadline 07:20
# --max regolabile dal cursore della dashboard (notturna-web.py -> .griglie-max)
GMAX=$(cat /data/memoria-episodica-affettiva/.griglie-max 2>/dev/null || echo 4)
bash /data/memoria-episodica-affettiva/gradino4/notte-distilla.sh --deadline 05:45 --max "$GMAX" || true
