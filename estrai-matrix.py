# Estrae i messaggi recenti dell'agente -> JSONL, dalla CONVERSAZIONE vera.
# Uso: python3 estrai-matrix.py [giorni] > messaggi.jsonl
#
# 20/07: la sorgente NON è più la stanza Matrix (Synapse). Quella è la VETRINA:
# contiene anche la telemetria del gateway (⏳ Working, 💾 Self-improvement,
# ⏰ Scheduling...) postata come messaggi normali, e diventava spazzatura in
# memoria. La telemetria è SOLO display: nello state.db del gateway (la
# conversazione vera) non c'è. Perciò leggiamo da lì. La spazzatura non si
# filtra: non la si legge proprio, perché non è mai stata conversazione.
# I doppioni interni (stessa riga compacted+active dopo la compattazione) li
# chiude l'invariante anti-doppione in memoria.add_node (stesso testo = 1 nodo);
# qui deduplico comunque sul testo per non mandarli al tagging.
import json
import re
import subprocess
import sys

STATE_DB = "/home/agente/.hermes/state.db"
# le due "stanze" dove l'agente VIVE: la chat principale e il pensatoio. La chat sta
# nelle sessioni matrix (chat_id della stanza, o NULL = sessioni vecchie
# pre-tracking); il pensatoio è il job cron del pensatoio (gli altri cron sono
# job di servizio: compiti, non esperienze).
STANZA_CHAT = "!mainroom:example.local"
CRON_PENSATOIO = "cron_pensatoio"

giorni = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

inner = f"""
import sqlite3, json, time
c = sqlite3.connect("{STATE_DB}")
cutoff = time.time() - {giorni} * 86400
rows = c.execute(
    "SELECT m.timestamp, m.role, m.content, m.active "
    "FROM messages m JOIN sessions s ON s.id = m.session_id "
    "WHERE m.content != '' AND m.role IN ('user','assistant') "
    "  AND m.timestamp > ? "
    "  AND ( (s.source='matrix' AND (s.chat_id IS NULL OR s.chat_id=?)) "
    "        OR s.id LIKE ? ) "
    # solo il PENSIERO consegnato, non i passi di orchestrazione: un assistant
    # che chiama un tool ('Ora cerco...', 'Ora scrivo...') è processo, non
    # esperienza. Il pensiero finale non ha tool_calls (scelta di progetto, 20/07).
    "  AND ( m.role='user' OR m.tool_calls IS NULL OR m.tool_calls='' ) "
    "ORDER BY m.timestamp", (cutoff, "{STANZA_CHAT}", "{CRON_PENSATOIO}%")).fetchall()
for r in rows:
    print(json.dumps(r))
"""
out = subprocess.run(["docker", "exec", "-i", "agente", "python3", "-"],
                     input=inner, capture_output=True, text=True, check=True)

PREFISSO = re.compile(r"^\[([^\]]+)\]\s?(.*)$", re.DOTALL)

# dedup sul testo, preferendo la copia active (canonica) a quella compacted
per_testo = {}
for line in out.stdout.splitlines():
    try:
        ts, role, content, active = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        continue
    content = content.strip()
    if not content:
        continue
    if role == "assistant":
        # "[OUT-OF-BAND] The user is asking me to..." è orchestrazione che
        # sfugge al filtro tool_calls: processo, non esperienza (22/07)
        if content.startswith("[OUT-OF-BAND]"):
            continue
        autore, testo = "@agente:example.local", content
    else:  # user
        # il preambolo cron ("[IMPORTANT: ...skill...]") non è un'esperienza
        if content.startswith("[IMPORTANT:"):
            continue
        m = PREFISSO.match(content)
        if m and re.fullmatch(r"[a-z0-9_]+", m.group(1)):
            # "[handle] testo": SOLO handle veri (minuscoli). I marcatori di
            # sistema ("[CONTEXT COMPACTION...]", "[System note...]") hanno il
            # prefisso in maiuscolo: non sono conversazione, si scartano.
            autore = f"@{m.group(1)}:example.local"
            testo = m.group(2).strip()
        elif content.startswith("["):
            continue                # artefatto di sistema, non un'esperienza
        else:                       # sessioni vecchie senza prefisso: chat principale
            autore, testo = "@human:example.local", content
        if not testo:
            continue
    vecchia = per_testo.get(testo)
    if vecchia is None or (active and not vecchia[2]):
        per_testo[testo] = (ts, autore, testo, active)

# FILTRO UNA-TANTUM (22/07): se accanto allo script c'è filtro-notte.json,
# i messaggi nelle finestre "escludi" si scartano, salvo i ts in "salva".
# I timestamp sono assoluti: passata la notte che li riguarda, il file è
# inerte e si può cestinare.
import os
_fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filtro-notte.json")
if os.path.exists(_fp):
    _f = json.load(open(_fp))
    _salva = set(_f.get("salva", []))
    _escludi = _f.get("escludi", [])
else:
    _salva, _escludi = set(), []

for ts, autore, testo, _ in sorted(per_testo.values()):
    if ts not in _salva and any(a <= ts <= b for a, b in _escludi):
        continue
    print(json.dumps({"ts": ts, "autore": autore, "testo": testo}, ensure_ascii=False))
