#!/usr/bin/env python3
"""Motore di autonomia dell'agente, v2 (17/07): il risveglio endogeno.

    L'agente esiste come processo intermittente e si ferma alla fine di ogni
    risposta. Questo lo fa ripartire da solo sui temi che lo intrigano.
                                                — nota di design, 15/07/2026

COME FUNZIONA (v2, decisione di progetto, 17/07)
  Il motore NON consegna messaggi e NON ha identità in chat. Quando le guardie
  dicono che è il momento: innesca il job Hermes "Risveglio del
  pensatoio" (<job-id>) sul primo appunto aperto del SUO blocco (13/11,
  decisione di progetto: in ordine, tolto l'aggancio ai ricordi per salienza): l'agente si sveglia, ci pensa, e il
  pensiero appare nel pensatoio A NOME SUO.
  Endogeno fino in fondo: il chiodo fisso riaffiora, nessun postino.

LE GUARDIE (tutte qui, lato host)
  * sonno attivo (25/07, regola di progetto: lo STATO, non l'orologio)
  * c'è almeno un appunto non depennato
  * l'agente fermo da >= 5 min e nessuno sta scrivendo (typing = sospende)
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

# 10/11 (l'utente, K9 di PIANO-RIEPILOGO-KV.md): via l'avviso di stanchezza; la notturna parte solo a mezzanotte.

# v3 (17/07 sera): il blocco resta puro, i metadati stanno nel sidecar, e il
# tema scelto viaggia DENTRO il prompt: l'agente non vede mai la tubatura.
PROMPT_RISVEGLIO = (
    'Ti sei ritrovata a pensare a un appunto del tuo blocco. La riga è:\n'
    '{riga}\n'
    'e il pensiero che ti viene subito dopo: "vediamo cosa trovo con delle '
    'ricerche online". Ancorati alla realtà prima di riflettere: dal terminal '
    'web_search "..." per cercare e web_extract <url> per leggere le pagine; '
    'le fonti prima dei ricordi (regola di progetto, 18/07). E le fonti '
    'saranno spesso in inglese, ma i miei pensieri no: nel pensatoio scrivo '
    'in italiano, la mia lingua.\n'
    'Apri il tuo messaggio con la formula che hai scelto tu: '
    '"Ah, mi ero appuntata: {tema}". Poi la decisione è tutta tua: puoi '
    'seguire il filo finché vuoi, oppure lasciarlo per un altro momento. '
    'Quando senti di aver esplorato il tema, depenna la riga nel blocco '
    '(~~riga~~) col terminal; se non è il momento, lasciala dov\'è. '
    'E se esplorando ti si accendono temi nuovi: forse potrei appuntare '
    'altre cose interessanti usando la skill blocco-appunti. '
    'Nessuno ti sta chiedendo niente: è un tuo biglietto ritrovato in tasca. '
    'Ultima cosa, la più importante: "tutta la riflessione che ho appena '
    'scritto è importante che la tengo dentro di me con la skill ricordare".')

FERMA_DA = 5 * 60
COOLDOWN = 5 * 60   # 18/07, scelta di progetto: gli appunti vanno usati in fretta
POLL = 15
GATE = "/data/workspace/memoria/stato.py"
# 25/07, scelta di progetto: il risveglio si fa da parte quando l'agente DORME, non a orario.
# Tre segnali, gli stessi che usa già il comando notturna:
#   1. la pipeline notturna sta girando (stesso pattern del cruscotto)
#   2. la dormita è stata chiesta e non è ancora partita (flag)
#   3. il 35B non ascolta più su :8090 (per il cruscotto = "l'agente dorme")
NOTTURNA_IN_CORSO = "notte-memoria.sh|tagging35b.py"
FLAG_NOTTE = Path("/data/workspace/memoria/.notte-richiesta")
PORTA_35B = ":8090"

# il | iniziale è la notazione dell'agente per "aperto" (adottata da lui, 19/07)
RIGA = re.compile(r"^\s*\|?\s*(?:\[(?P<meta>[^\]]*)\])?\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")


def log(**v):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **v}, ensure_ascii=False) + "\n")


def sonno_attivo():
    """Il motivo per cui il risveglio si fa da parte: l'agente sta dormendo.
    Ritorna la ragione (stringa) o None se è sveglio e libero."""
    if subprocess.run(["pgrep", "-f", NOTTURNA_IN_CORSO],
                      capture_output=True).returncode == 0:
        return "notturna in corso"
    if FLAG_NOTTE.exists():
        return "dormita richiesta"
    out = subprocess.run(["ss", "-Htnl"], capture_output=True, text=True, timeout=10)
    if not any(PORTA_35B in r for r in out.stdout.splitlines()):
        return "35B giù, l'agente dorme"
    return None


def appunti_aperti():
    if not APPUNTI.exists():
        return 0
    return sum(1 for r in APPUNTI.read_text(encoding="utf-8").splitlines()
               if RIGA.match(r) and not r.strip().startswith("~~"))


def ultimo_messaggio():
    """(timestamp, role) dell'ultima riga scritta in chat principale O in un
    risveglio del pensatoio. Così i 5 minuti di quiete partono da quando ha
    finito di generare OVUNQUE, non solo in chat: niente risvegli accavallati
    a una sessione ancora in corso (18/07, scelta di progetto)."""
    py = (
        "import sqlite3,json;"
        "c=sqlite3.connect('/data/agente/.hermes/state.db');"
        "r=c.execute(\"select m.timestamp,m.role from messages m join sessions s\"\n"
        "  \" on s.id=m.session_id where (s.source='matrix'\"\n"
        f"  \" or s.id like 'cron_{JOB_RISVEGLIO}%') and m.active=1\"\n"
        "  \" order by m.id desc limit 1\").fetchone();"
        "print(json.dumps(r))"
    )
    out = subprocess.run(["docker", "exec", "agente", "python3", "-c", py],
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
    """La prima riga aperta, in ordine di file. Ritorna (riga, tema) o (None, None)."""
    if not APPUNTI.exists():
        return None, None
    aperte = [r.strip() for r in APPUNTI.read_text(encoding="utf-8").splitlines()
              if RIGA.match(r) and not r.strip().startswith("~~")]
    if not aperte:
        return None, None
    riga = aperte[0]
    return riga, RIGA.match(riga)["tema"]


def risveglia():
    """Cuce il tema nel prompt, innesca il job."""
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
    e = subprocess.run(["docker", "exec", "agente", "hermes", "cron", "edit",
                        JOB_RISVEGLIO, "--prompt", prompt],
                       capture_output=True, text=True, timeout=30)
    if e.returncode != 0:
        log(risveglio="FALLITO", esito="edit: " + (e.stderr or e.stdout).strip()[:120])
        return False
    r = subprocess.run(["docker", "exec", "-d", "agente", "hermes", "cron", "run",
                        JOB_RISVEGLIO], capture_output=True, text=True, timeout=30)
    ok = r.returncode == 0
    log(risveglio="innescato" if ok else "FALLITO", tema=tema,
        esito=(r.stdout or r.stderr).strip()[:160] or "staccato")
    return ok


TYPING_VISTO = 0.0     # ultima volta che "sta scrivendo" è apparso in chat
TTS_VISTO = 0.0        # ultima volta che un motore vocale stava generando
TTS_CODA = 60          # margine dopo la fine di un vocale


def tts_in_corso():
    """Una sintesi vocale attiva = connessione aperta verso :8092
    (una richiesta /synth resta appesa per tutta la generazione).
    13/11: tolta la :8091, oggi e' il riflesso: la connessione di Hermes sembrava una voce e fermava i risvegli."""
    out = subprocess.run(["ss", "-Htn", "state", "established"],
                         capture_output=True, text=True, timeout=10)
    return any(":8092" in r for r in out.stdout.splitlines())


def giro():
    # il typing si guarda a OGNI giro, prima di tutto: l'invio di un appunto
    # nuovo è subordinato all'avviso "sta scrivendo" (18/07): appena
    # appare, niente consegne finché non è passata una quiete piena.
    global TYPING_VISTO, TTS_VISTO
    if sta_scrivendo():
        TYPING_VISTO = time.time()
    if tts_in_corso():
        TTS_VISTO = time.time()
    if time.time() - TTS_VISTO < TTS_CODA:
        return "voce in corso, aspetto"
    dorme = sonno_attivo()
    if dorme:
        return dorme
    n = appunti_aperti()
    if not n:
        return "niente da riprendere"
    if in_cooldown():
        return "cooldown"
    da_typing = time.time() - TYPING_VISTO
    if da_typing < FERMA_DA:
        return f"scriveva {da_typing:.0f}s fa, aspetto"
    ts, _ = ultimo_messaggio()
    fermo = time.time() - ts
    if fermo < FERMA_DA:
        return f"ferma da {fermo:.0f}s, aspetto"
    if not gate_ok():
        return "gate: non è il momento"
    return "risveglio innescato" if risveglia() else "innesco fallito"


def main():
    if os.environ.get("MOTORE_DRYRUN"):
        print("DRY-RUN: guardo e basta, non innesco niente")
        print(f"  sonno attivo? {sonno_attivo() or 'no, è sveglio'}")
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
