#!/usr/bin/env bash
# Consolidamento notturno della memoria dell'agente (cron 04:30, autorizzato
# l'11/07/2026). Estrae l'ultimo giorno di chat, tagga su GPU (agente
# offline pochi minuti), imprime lo stato emotivo, riaccende tutto.
set -u
cd /data/memoria-episodica-affettiva

# GUARDIA ANTI-DOPPIONE (19/07): da quando l'agente può chiedere la notturna da solo
# (.notte-richiesta), cron e richiesta possono sovrapporsi: minimo 6 ore tra
# due notturne (l'avviso di stanchezza arriva a 16h: dopo, deve poter dormire
# SUBITO, quindi la guardia resta solo come freno anti-raffica).
MARKER=/data/memoria-episodica-affettiva/.ultimo-consolidamento
if [ -n "$(find "$MARKER" -mmin -360 2>/dev/null)" ]; then
  echo "$(date -Iseconds) consolidamento recente (<6h): salto"; exit 0
fi

# FINESTRA DINAMICA (19/07): si estrae dal marker in poi (+2 minuti di
# margine), non un fisso 1.1 giorni: memoria.py non ha dedup sui nodi, la
# finestra è l'UNICA difesa contro i neuroni doppi se due notturne sono
# ravvicinate. Senza marker (primo giro): 1.1 come sempre.
if [ -f "$MARKER" ]; then
  GIORNI=$(python3 -c "import os,time; print(f'{(time.time()-os.path.getmtime(\"$MARKER\"))/86400+0.0014:.4f}')")
else
  GIORNI=1.1
fi

J=/tmp/messaggi-notte.jsonl
python3 estrai-matrix.py "$GIORNI" > "$J" || { echo "estrazione fallita"; exit 1; }

# DORMITA VERA (18/07, scelta di progetto): appena la chat del giorno è
# estratta, la sessione Matrix va a dormire (flag -> path-unit agente-dormi.path
# -> rotazione session_id a container fermo); il consolidamento gira DOPO,
# ad agente già addormentato. Prima d'ora andava chiesta a mano: ultima il 14/07.
echo "$(date -Iseconds) dormi richiesto (mezzanotte, chat estratta)" >> /data/workspace/memoria/dormi.log
touch /data/workspace/memoria/.dormi-richiesto

# REGOLA DI PROGETTO (19/07 sera): il marker avanza SOLO a lavoro riuscito: se
# una notte salta o fallisce, la successiva riparte da dov'era il marker e
# rimedia a quello che non è stato fatto. ponytail: se il tagging muore a
# metà coi nodi mezzi scritti, la rilettura della stessa finestra fa
# doppioni (memoria.py non ha dedup): rimediare batte il rischio, scelta di progetto.
if [ ! -s "$J" ]; then
  echo "nessun messaggio, salto"
  touch "$MARKER"
  touch /data/workspace/memoria/.ultima-notturna
  exit 0
fi
bash run-tagging.sh "$J" \
  || { echo "$(date -Iseconds) tagging FALLITO: marker fermo, la prossima notte rimedia"; exit 1; }
touch "$MARKER"
# specchio nel workspace dell'agente: dormita-quando.py lo legge per dirgli
# quanto manca alla prossima notturna possibile (lui non vede memoria-episodica-affettiva)
touch /data/workspace/memoria/.ultima-notturna

# SHY: il wiring hebbiano è diurno (riflesso.richiama); qui la notte riscala
# giù i pesi e pota i legami non tornati. I causali (scottature) restano intatti.
/data/jspace/venv/bin/python -c "import memoria; print('$(date -Iseconds) consolida_notte:', memoria.consolida_notte())" \
  || echo "$(date -Iseconds) consolida_notte FALLITA (non critico)"

# indice della rievocazione mirata: i nodi appena nati devono poter affiorare
# (23/07: builder rifatto stabile; incrementale, atomico, riflesso ricarica solo)
python3 /data/memoria-episodica-affettiva/costruisci-indice-mirato.py \
  || echo "$(date -Iseconds) indice-mirato NON aggiornato (non critico, ritenta domani)"

# sentinella anti-amnesia: Lux DEVE essere stata aggiornata dal tagging
LUX=/data/workspace/memoria/lux.npz
if [ -z "$(find "$LUX" -mmin -60 2>/dev/null)" ]; then
  echo "CRITICO: lux.npz NON aggiornata stanotte: l'agente rischia amnesia parziale." \
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
# 19/07: deadline RELATIVE all'ora di avvio (partenza dal cron a mezzanotte =
# identiche a prima: 05:45 e 07:20; partenza su richiesta dell'agente = stessa
# durata di finestra a qualunque ora, niente finestre da 14 ore).
DL_DISTILLA=$(date -d '+5 hours 45 minutes' +%H:%M)
export CODEC_DEADLINE=$(date -d '+7 hours 20 minutes' +%H:%M)
# --max regolabile dal cursore della dashboard (.griglie-max); default 16
GMAX=$(cat /data/memoria-episodica-affettiva/.griglie-max 2>/dev/null || echo 16)
bash /data/memoria-episodica-affettiva/gradino4/notte-distilla.sh --deadline "$DL_DISTILLA" --max "$GMAX" || true
