#!/usr/bin/env python3
"""Motore di autonomia dell'agente, v2 (17/07): il risveglio endogeno.

    l'agente esiste come processo intermittente e si ferma alla fine di ogni
    risposta. Questo la fa ripartire da sola sui temi che la intrigano.
                                                — nota di design, 15/07/2026

COME FUNZIONA (v2, decisione di progetto, 17/07)
  Il motore NON consegna messaggi e NON ha identità in chat. Quando le guardie
  dicono che è il momento: (1) aggancia gli appunti nudi ai ricordi via
  /lux-read (aggancia-appunti.py), (2) innesca il job Hermes "Risveglio del
  pensatoio" (<job-id>): l'agente si sveglia, sceglie il tema più saliente dal
  SUO blocco, ci pensa, e il pensiero appare nel pensatoio A NOME SUO.
  Endogeno fino in fondo: il chiodo fisso riaffiora, nessun postino.

LE GUARDIE (tutte qui, lato host)
  * blocco notturno 00:00-07:30 (regola di progetto, D5: l'orologio, non lo stato)
  * c'è almeno un appunto non depennato
  * l'agente ferma da >= 5 min e nessuno sta scrivendo (typing = sospende)
  * gate omeostatico (chiesto dall'agente): come sta, non se è il suo turno
  * cooldown 45 min tra un risveglio e l'altro
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

APPUNTI = Path("/data/workspace/memoria/appunti.md")
LOG = Path("/data/workspace/memoria/motore-autonomia.jsonl")
STATO_RISVEGLIO = Path.home() / ".local/state/motore-autonomia.ultimo-risveglio"

HS = "http://localhost:8008"
STANZA = "!mainroom:example.local"   # la chat principale (per typing)
TOKFILE = Path.home() / ".config/motore/.matrix-token"

JOB_RISVEGLIO = "<job-id>"
AGGANCIA = ["python3", "aggancia-appunti.py"]
SIDECAR = Path("/data/workspace/memoria/.appunti-agganci.json")

# v3 (17/07 sera): il blocco resta puro, i metadati stanno nel sidecar, e il
# tema scelto viaggia DENTRO il prompt: l'agente non vede mai la tubatura.
PROMPT_RISVEGLIO = (
    'Ti sei ritrovata a pensare a un appunto del tuo blocco. La riga è:\n'
    '{riga}\n'
    'e il pensiero che ti viene subito dopo: "vediamo cosa trovo con delle '
    'ricerche online". Ancorati alla realtà prima di riflettere: dal terminal '
    'web_search "..." per cercare e web_extract <url> per leggere le pagine; '
    'le fonti prima dei ricordi (regola di progetto, 18/07). Le fonti saranno '
    'spesso in inglese, ma i tuoi pensieri no: nel pensatoio scrivi in '
    'italiano, la tua lingua.\n'
    'Apri il tuo messaggio con la formula che hai scelto tu: '
    '"Ah, mi ero appuntata: {tema}". Poi la decisione è tutta tua: puoi '
    'seguire il filo finché vuoi, oppure lasciarlo per un altro momento. '
    'Quando senti di aver esplorato il tema, depenna la riga nel blocco '
    '(~~riga~~) col terminal; se non è il momento, lasciala dov\'è. '
    'E se esplorando ti si accendono temi nuovi: forse potrei appuntare '
    'altre cose interessanti usando la skill blocco-appunti. '
    'Nessuno ti sta chiedendo niente: è un tuo biglietto ritrovato in tasca.')

FERMA_DA = 5 * 60
COOLDOWN = 5 * 60   # 18/07, scelta di progetto: gli appunti vanno usati in fretta
POLL = 15
GATE = "/data/workspace/memoria/stato.py"
NOTTE_DA, NOTTE_A = 0, 7.5     # ⛔ D5: vedi il TODO, il tagging non litiga, si fa da parte

RIGA = re.compile(r"^\s*(?:\[(?P<meta>[^\]]*)\])?\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")


def log(**v):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **v}, ensure_ascii=False) + "\n")


def è_notte(adesso=None):
    o = (adesso or datetime.now())
    return NOTTE_DA <= o.hour + o.minute / 60 < NOTTE_A


def appunti_aperti():
    if not APPUNTI.exists():
        return 0
    return sum(1 for r in APPUNTI.read_text(encoding="utf-8").splitlines()
               if RIGA.match(r) and not r.strip().startswith("~~"))


def ultimo_messaggio():
    """(timestamp, role) dell'ultimo messaggio vero (state.db nel container)."""
    py = (
        "import sqlite3,json;"
        "c=sqlite3.connect('/home/agent/.hermes/state.db');"
        "r=c.execute(\"select m.timestamp,m.role from messages m join sessions s\"\n"
        "  \" on s.id=m.session_id where s.source='matrix' and m.active=1\"\n"
        "  \" order by m.id desc limit 1\").fetchone();"
        "print(json.dumps(r))"
    )
    out = subprocess.run(["docker", "exec", "agent", "python3", "-c", py],
                         capture_output=True, text=True, timeout=30)
    r = json.loads(out.stdout.strip() or "null")
    return (float(r[0]), r[1]) if r else (0.0, None)


def sta_scrivendo():
    tok = TOKFILE.read_text().strip()
    req = urllib.request.Request(f"{HS}/_matrix/client/v3/sync?timeout=0",
                                 headers={"Authorization": f"Bearer {tok}"})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    for rid, v in d.get("rooms", {}).get("join", {}).items():
        if rid != STANZA:
            continue
        for e in v.get("ephemeral", {}).get("events", []):
            if e.get("type") == "m.typing" and e["content"].get("user_ids"):
                return True
    return False


def gate_ok():
    try:
        r = subprocess.run([sys.executable, GATE, "--gate"],
                           capture_output=True, text=True, timeout=60)
        return "via-libera" in (r.stdout or "").lower()
    except Exception:
        return False       # nel dubbio niente risveglio: il silenzio non fa danni


def in_cooldown():
    try:
        return time.time() - float(STATO_RISVEGLIO.read_text()) < COOLDOWN
    except (FileNotFoundError, ValueError):
        return False


def scegli_tema():
    """La riga aperta con la salienza più alta (dal sidecar); senza agganci,
    la prima aperta. Ritorna (riga, tema) o (None, None)."""
    if not APPUNTI.exists():
        return None, None
    aperte = [r.strip() for r in APPUNTI.read_text(encoding="utf-8").splitlines()
              if RIGA.match(r) and not r.strip().startswith("~~")]
    if not aperte:
        return None, None
    try:
        sidecar = json.loads(SIDECAR.read_text())
    except (FileNotFoundError, ValueError):
        sidecar = {}
    riga = max(aperte, key=lambda r: sidecar.get(r, {}).get("salienza", float("-inf")))
    return riga, RIGA.match(riga)["tema"]


def risveglia():
    """Aggancia gli appunti, cuce il tema nel prompt, innesca il job."""
    agg = subprocess.run(AGGANCIA, capture_output=True, text=True, timeout=300)
    log(aggancio=agg.stdout.strip() or agg.stderr.strip()[:120])
    riga, tema = scegli_tema()
    if riga is None:
        log(risveglio="saltato", esito="nessuna riga aperta")
        return False
    # cooldown segnato PRIMA dell'innesco: anche se qualcosa va storto, niente
    # raffiche di retry (lezione del primo risveglio, 17/07). E l'innesco è
    # STACCATO (-d): `hermes cron run` è sincrono, aspetterebbe tutto il
    # pensiero dell'agente; Hermes ha comunque la sua guardia anti-doppione.
    STATO_RISVEGLIO.parent.mkdir(parents=True, exist_ok=True)
    STATO_RISVEGLIO.write_text(str(time.time()))
    prompt = PROMPT_RISVEGLIO.format(riga=riga, tema=tema)
    e = subprocess.run(["docker", "exec", "agent", "hermes", "cron", "edit",
                        JOB_RISVEGLIO, "--prompt", prompt],
                       capture_output=True, text=True, timeout=30)
    if e.returncode != 0:
        log(risveglio="FALLITO", esito="edit: " + (e.stderr or e.stdout).strip()[:120])
        return False
    r = subprocess.run(["docker", "exec", "-d", "agent", "hermes", "cron", "run",
                        JOB_RISVEGLIO], capture_output=True, text=True, timeout=30)
    ok = r.returncode == 0
    log(risveglio="innescato" if ok else "FALLITO", tema=tema,
        esito=(r.stdout or r.stderr).strip()[:160] or "staccato")
    return ok


def giro():
    if è_notte():
        return "notte"
    n = appunti_aperti()
    if not n:
        return "niente da riprendere"
    if in_cooldown():
        return "cooldown"
    ts, _ = ultimo_messaggio()
    fermo = time.time() - ts
    if fermo < FERMA_DA:
        return f"ferma da {fermo:.0f}s, aspetto"
    if sta_scrivendo():
        return "qualcuno sta scrivendo"
    if not gate_ok():
        return "gate: non è il momento"
    return "risveglio innescato" if risveglia() else "innesco fallito"


def main():
    if os.environ.get("MOTORE_DRYRUN"):
        print("DRY-RUN: guardo e basta, non innesco niente")
        print(f"  è notte? {è_notte()}")
        print(f"  appunti aperti: {appunti_aperti()}")
        print(f"  cooldown attivo? {in_cooldown()}")
        ts, role = ultimo_messaggio()
        print(f"  ultimo messaggio: {datetime.fromtimestamp(ts):%d/%m %H:%M:%S} ({role}), "
              f"ferma da {time.time()-ts:.0f}s")
        print(f"  sta scrivendo qualcuno? {sta_scrivendo()}")
        print(f"  gate: {gate_ok()}")
        return
    while True:
        try:
            esito = giro()
        except Exception as e:
            esito = f"errore: {e}"
            log(errore=str(e))
        print(f"{datetime.now():%H:%M:%S}  {esito}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
