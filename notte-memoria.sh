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
# margine), non un fisso 1.1 giorni: la finestra è la prima difesa contro i
# neuroni doppi se due notturne sono ravvicinate (dal 20/07 memoria.add_node
# deduplica anche sul testo). Senza marker (primo giro): 1.1 come sempre.
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
# 18/10, l'utente: con la dormita la conversazione finisce, e con lei la lista dei ricordi
# consegnati dal riflesso (quella che l'agente legge con ricorda.py --richiamati)
rm -f /data/workspace/memoria/consegne-memorinvolontaria.json

# REGOLA DI PROGETTO (19/07 sera): il marker avanza SOLO a lavoro riuscito: se
# una notte salta o fallisce, la successiva riparte da dov'era il marker e
# rimedia a quello che non è stato fatto. ponytail: se il tagging muore a
# metà coi nodi mezzi scritti, la rilettura della stessa finestra fa
# doppioni (oggi li ferma memoria.add_node, che deduplica sul testo):
# rimediare batte il rischio, scelta di progetto.
if [ ! -s "$J" ]; then
  echo "nessun messaggio, salto"
  touch "$MARKER"
  touch /data/workspace/memoria/.ultima-notturna
  exit 0
fi
# PERSISTENZA (30/09, PIANO-PERSISTENZA-LUX.md): i richiami del giorno passano dal
# grafo; qui, PRIMA del tagging (che pota Lux), diventano riattivazioni dei neuroni.
/data/jspace/venv/bin/python sincronizza-richiami.py \
  || echo "$(date -Iseconds) sincronia richiami FALLITA (non critico: la prossima notte li riprende)"
bash run-tagging.sh "$J" \
  || { echo "$(date -Iseconds) tagging FALLITO: marker fermo, la prossima notte rimedia"; exit 1; }
touch "$MARKER"
# un giorno VISSUTO in piu' per l'oblio di Lux: solo a notturna riuscita con
# messaggi veri (una notte senza chat, o da spento, non fa dimenticare)
/data/jspace/venv/bin/python -c "import lux; print('$(date -Iseconds) giorni vissuti:', lux.avanza_orologio())" \
  || echo "$(date -Iseconds) orologio vissuto NON avanzato (non critico)"
# specchio nel workspace dell'agente: dormita-quando.py lo legge per dirgli
# quanto manca alla prossima notturna possibile (lui non vede memoria-episodica-affettiva)
touch /data/workspace/memoria/.ultima-notturna

# SHY: il wiring hebbiano è diurno (ricorda.py); qui la notte riscala
# giù i pesi e pota i legami non tornati. I causali (scottature) restano intatti.
/data/jspace/venv/bin/python -c "import memoria; print('$(date -Iseconds) consolida_notte:', memoria.consolida_notte())" \
  || echo "$(date -Iseconds) consolida_notte FALLITA (non critico)"

# Lux degli engrammi (12/10): i ricordi nati stanotte entrano nel Lux che consegna
# i ricordi al riflesso (taglio + archi nuovi, i rinforzi degli altri restano);
# il servizio (lux-engrammi.service) se ne accorge da solo e ricarica
/data/venv-spacy/bin/python /data/memoria-episodica-affettiva/engrammi/lux_engrammi.py aggiungi \
  || echo "$(date -Iseconds) Lux degli engrammi NON aggiornato (non critico, ritenta domani)"

# sentinella anti-amnesia: Lux DEVE essere stata aggiornata dal tagging
LUX=/data/workspace/memoria/lux.npz
if [ -z "$(find "$LUX" -mmin -60 2>/dev/null)" ]; then
  echo "CRITICO: lux.npz NON aggiornata stanotte: l'agente rischia amnesia parziale." \
       "Il grafo ha i nodi: backfill con lux-demo.py. Controllare tagging.log."
fi
