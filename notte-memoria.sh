#!/usr/bin/env bash
# Consolidamento notturno della memoria dell'agente (cron 04:30, autorizzato
# l'11/07/2026). Estrae l'ultimo giorno di chat, tagga su GPU (agente
# offline pochi minuti), imprime lo stato emotivo, riaccende tutto.
set -u
cd /data/memoria-episodica-affettiva

# GUARDIA ANTI-DOPPIONE: cron e richiesta dell'agente (.notte-richiesta) possono sovrapporsi. 10/11: tolto il
# minimo di 6 ore fra due notturne (ormai durano pochi secondi); resta solo il lucchetto: mai due notturne insieme.
MARKER=/data/memoria-episodica-affettiva/.ultimo-consolidamento
exec 9>/tmp/notte-memoria.lock
flock -n 9 || { echo "$(date -Iseconds) notturna gia' in corso: salto"; exit 0; }

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
# revisione 3.5.3 (10/11): con uno switch in corso o gia' fatto (promozione in attesa) niente seconda rotazione
if [ -e /data/memoria-episodica-affettiva/.switch-in-corso ] || [ -e /data/memoria-episodica-affettiva/.riepilogo-promuovi ]; then
  echo "$(date -Iseconds) dormi saltato (mezzanotte): switch gia' in corso o fatto" >> /data/workspace/memoria/dormi.log
else
  echo "$(date -Iseconds) dormi richiesto (mezzanotte, chat estratta)" >> /data/workspace/memoria/dormi.log
  touch /data/workspace/memoria/.dormi-richiesto
fi
# la lista dei ricordi consegnati (18/10) la svuota dormi-esegui.sh a sessione ruotata (10/11, vale per ogni switch)
# step d (l'utente 12/11, PIANO-MEMORY-A-B.md): B = MEMORY.md e USER.md dell'agente, base della CW del riepilogo rifatta.
# Qui e non dopo: l'agente scrive nel memory anche dal pensatoio, nei giorni senza chat. L'esito va nel diario del riflesso; un errore non ferma la notturna
echo "$(date -Iseconds) memoria B: $(curl -sf -m 10 -X POST http://127.0.0.1:8091/memoria-b || echo 'chiamata fallita')"

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
# grafo; qui, PRIMA del tagging, diventano rinforzi degli archi del Lux degli engrammi
# (B5 01/11: attraverso il suo servizio; il vecchio Lux e' in archivio).
/data/jspace/venv/bin/python sincronizza-richiami.py \
  || echo "$(date -Iseconds) sincronia richiami FALLITA (non critico: la prossima notte li riprende)"
# B6 (01/11, engrammi/PIANO-FIRMA-ENGRAMMI.md): niente piu' tagging col 35B spento, i ricordi li fa firma-subito
# durante il giorno. Qui: in coda i messaggi che il riflesso non ha passato, coda svuotata, poi
# persistenza sugli scartati e omeostato dai ricordi nati dal marker in poi
DA=$(stat -c %Y "$MARKER" 2>/dev/null || echo 0)
FS="/data/jspace/venv/bin/python /data/memoria-episodica-affettiva/engrammi/firma_subito.py"
$FS recupera "$J" > /data/memoria-episodica-affettiva/tagging.log 2>&1 \
  || { echo "$(date -Iseconds) recupero FALLITO (35B spento o firma-subito fermo): marker fermo, la prossima notte rimedia"; exit 1; }
$FS notte "$DA" >> /data/memoria-episodica-affettiva/tagging.log 2>&1 \
  || { echo "$(date -Iseconds) persistenza/omeostato FALLITI: marker fermo, la prossima notte rimedia"; exit 1; }
touch "$MARKER"
# un giorno VISSUTO in piu' per l'oblio di Lux: solo a notturna riuscita con
# messaggi veri (una notte senza chat, o da spento, non fa dimenticare)
/data/jspace/venv/bin/python -c "import lux; print('$(date -Iseconds) giorni vissuti:', lux.avanza_orologio())" \
  || echo "$(date -Iseconds) orologio vissuto NON avanzato (non critico)"
# specchio nel workspace dell'agente: dormita-quando.py lo legge per dirgli
# quanto manca alla prossima notturna possibile (lui non vede memoria-episodica-affettiva)
touch /data/workspace/memoria/.ultima-notturna

# 09/11: tolta consolida_notte (SHY sugli archi hebbiani di memoria.db). Dopo qlux nessuno li crea piu'.
# 1.20.0: memoria.db e' archivio in sola lettura (i dati dei ricordi stanno nel Lux), gli archi hebbiani restano li'.

# 1.20.0: tolta la chiamata lux_engrammi.py aggiungi: i ricordi entrano subito nel Lux dal servizio (POST /aggiungi,
# firma-subito), non piu' di notte da memoria.db

# sentinella anti-amnesia (B5 01/11, P6; 1.20.0): ogni nid del registro di firma-subito (esito nodo o trascinato) DEVE
# stare nel Lux degli engrammi, e ogni ricordo del Lux deve avere testo e firma
(cd /data/memoria-episodica-affettiva/engrammi && /data/venv-spacy/bin/python sentinella_lux.py) \
  || echo "CRITICO: ricordi del registro fuori dal Lux degli engrammi (o senza testo/firma): l'agente non li richiama." \
          "Rimedio: guardare il journal di firma-subito e lux-engrammi (journalctl --user -u firma-subito -u lux-engrammi)."

# 1.14.0 (PIANO-1.14-RICONSOLIDAMENTO.md, punto 9): copia del Lux della notte (sotto il lucchetto del Lux, tiene le
# ultime 7), poi il riconsolidamento nel servizio, che tiene lo stato in memoria (fallimento non critico)
LD=$(cd /data/memoria-episodica-affettiva/engrammi && /data/venv-spacy/bin/python -c "import lux_engrammi as X, numpy as np
print(X.DIR if 'C0' in np.load(X.NPZ).files else '')")   # solo dalla 1.14.0 (prima: niente M da scrivere)
if [ -n "$LD" ] && [ -d "$LD" ]; then
  N="$LD/notti/$(date +%Y%m%d)"
  mkdir -p "$N" && flock "$LD/.lucchetto" cp -p "$LD/lux.npz" "$LD/lux-stato.npz" "$LD/lux-meta.json" "$N/" \
    || echo "$(date -Iseconds) copia del Lux della notte FALLITA (non critico)"
  ls -1d "$LD"/notti/2* 2>/dev/null | head -n -7 | xargs -r rm -rf --
  # 1.17.0: i messaggi del giorno riaccendono gli engrammi (contatori del tema aperto), poi il riconsolidamento
  R=$(curl -sf -m 600 -X POST http://127.0.0.1:8132/riaccendi -H 'Content-Type: application/json' -d '{}') \
    && echo "$(date -Iseconds) riaccendi: $R" \
    || echo "$(date -Iseconds) riaccendi NON fatto (non critico, ritenta domani)"
  # 1.18.0: lo sbiadimento della notte (una volta per giorno vissuto)
  R=$(curl -sf -m 600 -X POST http://127.0.0.1:8132/sbiadisci -H 'Content-Type: application/json' -d '{}') \
    && echo "$(date -Iseconds) sbiadisci: $R" \
    || echo "$(date -Iseconds) sbiadisci NON fatto (non critico, ritenta domani)"
  R=$(curl -sf -m 600 -X POST http://127.0.0.1:8132/riconsolida -H 'Content-Type: application/json' -d '{}') \
    && echo "$(date -Iseconds) riconsolida: $R" \
    || echo "$(date -Iseconds) riconsolida NON fatto (non critico, ritenta domani)"
  # 1.21.0 (PIANO-FASE2-C-ARCHI-E-CODA.md): le firme dei ricordi legati si avvicinano, la dominante si ricalcola
  R=$(curl -sf -m 600 -X POST http://127.0.0.1:8132/avvicina -H 'Content-Type: application/json' -d '{}') \
    && echo "$(date -Iseconds) avvicina: $R" \
    || echo "$(date -Iseconds) avvicina NON fatto (non critico, ritenta domani)"
  # 1.23.0 (PIANO-PONTI-123.md): la potatura dei ponti fra engrammi (provvisori via, calo dei non usati, taglio)
  R=$(curl -sf -m 600 -X POST http://127.0.0.1:8132/ponti -H 'Content-Type: application/json' -d '{}') \
    && echo "$(date -Iseconds) ponti: $R" \
    || echo "$(date -Iseconds) ponti NON fatto (non critico, ritenta domani)"
fi
