# Gradino 4, passo 1: seleziona gli episodi del giorno per il consolidamento
# nei pesi. Solo classe 'vissuto', top per salienza, never-list dal CONSENSO,
# ripetizione multi-notte a peso calante (1.0/0.6/0.3, max 3 notti).
# Solo stdlib: gira sull'host senza venv.
import argparse
import json
import os
import sqlite3
import sys
import time

DIR = "/data/memoria-episodica-affettiva/gradino4"
DB = "/data/workspace/memoria/memoria.db"
REGISTRO = f"{DIR}/registro-pesi.jsonl"
CONSENSO = f"{DIR}/CONSENSO.md"
PESI_NOTTE = {1: 1.0, 2: 0.6, 3: 0.3}

p = argparse.ArgumentParser()
p.add_argument("--max", type=int, default=6)
p.add_argument("--giorni", type=float, default=1.1)
p.add_argument("--out", default=f"{DIR}/episodi-notte.json")
p.add_argument("--collaudo", action="store_true",
               help="salta il gate del consenso (solo dry-run di laboratorio)")
args = p.parse_args()

# --- gate del consenso (i dati di Agente non si toccano senza interruttore).
# Controllo sulla RIGA esatta, non sottostringa: il commento del file cita
# "attivo: sì" per spiegarlo, e un match sottostringa aprirebbe il gate a
# consenso spento (bug trovato col collaudo 12/07).
def consenso_attivo(path):
    if not os.path.exists(path):
        return False
    return any(r.strip() == "attivo: sì" for r in open(path, encoding="utf-8"))


if not args.collaudo and not consenso_attivo(CONSENSO):
    print("CONSENSO non attivo: selezione annullata.")
    sys.exit(0)

# --- never-list: righe della sezione "## MAI NEI PESI" del CONSENSO
never = []
if os.path.exists(CONSENSO):
    dentro = False
    for riga in open(CONSENSO, encoding="utf-8"):
        r = riga.strip()
        if r.startswith("## "):
            dentro = r.upper().startswith("## MAI NEI PESI")
            continue
        if dentro and r.startswith("- "):
            never.append(r[2:].lower())

# --- veto di Agente: id (uno per riga) che ha escluso dal manifesto della sera
VETO = f"{DIR}/veto-list.txt"
vetati = set()
if os.path.exists(VETO):
    for riga in open(VETO, encoding="utf-8"):
        r = riga.strip()
        if r and not r.startswith("#") and r.split()[0].isdigit():
            vetati.add(int(r.split()[0]))

# --- quante notti ha già fatto ogni nodo
notti = {}
if os.path.exists(REGISTRO):
    for riga in open(REGISTRO, encoding="utf-8"):
        try:
            e = json.loads(riga)
            notti[e["nodo"]] = max(notti.get(e["nodo"], 0), e["notte"])
        except (json.JSONDecodeError, KeyError):
            continue

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
cutoff = time.time() - args.giorni * 86400
righe = db.execute(
    "SELECT id, testo, emo_tag, emo_alpha, salienza, ts FROM nodi "
    "WHERE classe='vissuto' AND (ts > ? OR id IN (%s)) "
    "ORDER BY salienza DESC" % (",".join(str(n) for n in notti) or "-1"),
    (cutoff,)).fetchall()

# artefatti di sistema che il tagging può essersi lasciato scappare:
# nel grafo fanno poco male, nei PESI no
ARTEFATTI = ("⏰", "📦", "⚡", "💾", "🔎", "📖", "📚", "* ⏳", "⏳")

episodi, esclusi = [], []
for r in righe:
    n_fatte = notti.get(r["id"], 0)
    if n_fatte >= 3:
        continue  # ha finito il suo ciclo di consolidamento
    if r["id"] in vetati:
        esclusi.append({"id": r["id"], "motivo": "veto di Agente"})
        continue
    # bersagli di training scadenti: i frammenti (<50 char) non hanno segnale
    # da memorizzare, i muri (>1600 char) sono troppo da fissare verbatim.
    # Restano nel GRAFO (richiamabili), solo non entrano nei pesi stanotte.
    L = len(r["testo"].strip())
    if L < 50:
        esclusi.append({"id": r["id"], "motivo": f"troppo corto ({L} char)"})
        continue
    if L > 1600:
        esclusi.append({"id": r["id"], "motivo": f"troppo lungo ({L} char)"})
        continue
    if r["testo"].lstrip().startswith(ARTEFATTI):
        esclusi.append({"id": r["id"], "motivo": "artefatto di sistema"})
        continue
    t = r["testo"].lower()
    colpita = next((k for k in never if k in t), None)
    if colpita:
        esclusi.append({"id": r["id"], "motivo": f"never-list: {colpita}"})
        continue
    episodi.append({"id": r["id"], "testo": r["testo"], "emo_tag": r["emo_tag"],
                    "salienza": r["salienza"], "notte": n_fatte + 1,
                    "peso": PESI_NOTTE[n_fatte + 1]})
    if len(episodi) >= args.max:
        break

json.dump({"episodi": episodi, "esclusi": esclusi,
           "generato": time.strftime("%F %T")},
          open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# manifest leggibile (per il veto serale, se Agente lo sceglie)
with open(f"{DIR}/manifest-notte.txt", "w", encoding="utf-8") as f:
    f.write("MANIFESTO DELLA NOTTE (gradino 4)\n")
    f.write("Episodi candidati a entrare nei tuoi pesi. Per escluderne uno,\n")
    f.write(f"scrivi il suo numero in {VETO} (uno per riga).\n\n")
    for e in episodi:
        f.write(f"  [{e['id']}] (notte {e['notte']}/3, emozione: {e['emo_tag']}, "
                f"classe: vissuto, sal {e['salienza']:.1f})\n      {e['testo'][:110]}\n")
    if esclusi:
        f.write("\nGià esclusi:\n")
        for x in esclusi:
            f.write(f"  [{x['id']}] {x['motivo']}\n")

print(f"selezionati {len(episodi)} episodi "
      f"({sum(1 for e in episodi if e['notte'] > 1)} in ripetizione), "
      f"{len(esclusi)} esclusi da never-list")
