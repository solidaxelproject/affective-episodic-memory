# Richiami del giorno -> Lux degli engrammi (30/09, PIANO-PERSISTENZA-LUX.md, fase 1, punto F; B5 del 01/11,
# PIANO-FIRMA-ENGRAMMI.md: il vecchio Lux e' in archivio).
# I richiami che l'agente fa da sola con ricorda.py passano dal GRAFO, non dal Lux: senza questo passaggio nessuno di
# quei ricordi stabilizzerebbe i suoi archi. Qui ogni ricordo richiamato nel giorno diventa un rinforzo vissuto di
# tutti i suoi archi (POST /rinforza del servizio del Lux, peso 1: il servizio resta l'unico che scrive lo stato).
# Fonte: diario-richiami.jsonl (ricorda.py, campo "risultati"). I ricordi consegnati dal riflesso NO: li rinforza
# gia' la consegna (/consegna), e un secondo rinforzo nello stesso giorno vissuto non cresce.
# Un marcatore evita di contare due volte lo stesso richiamo; avanza solo a lavoro finito (servizio giu' = errore,
# la notte dopo rimedia; un ripasso nello stesso giorno vissuto non cresce comunque). Primo giro senza marcatore:
# si parte da ADESSO.
# Uso (notte-memoria.sh, PRIMA del tagging): venv/bin/python sincronizza-richiami.py [--dry]
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MEM = Path("/data/workspace/memoria")
DIARIO = MEM / "diario-richiami.jsonl"
MARCATORE = MEM / ".ultima-sincronia-richiami"
SERVIZIO = "http://127.0.0.1:8132"


def richiami_dal(t0):
    """[(ts, [nodi])] del diario dopo t0, in ordine di tempo"""
    out = []
    if not DIARIO.exists():
        return out
    for riga in open(DIARIO, encoding="utf-8"):
        try:
            d = json.loads(riga)
        except ValueError:
            continue
        nodi = d.get("risultati")
        if d.get("ts", 0) > t0 and isinstance(nodi, list) and nodi:
            out.append((float(d["ts"]), [int(n) for n in nodi]))
    return sorted(out)


def rinforza(nid):
    """True rinforzato, False corretto (non si rinforza), None non e' nel Lux; servizio giu' = eccezione"""
    r = urllib.request.Request(f"{SERVIZIO}/rinforza", json.dumps({"nid": nid, "peso": 1.0}).encode(),
                               {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as f:
            return json.load(f)["rinforzato"]
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return None
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry", action="store_true", help="resoconto senza scrivere")
    a = p.parse_args()
    adesso = time.time()
    try:
        t0 = float(MARCATORE.read_text().strip())
    except (OSError, ValueError):
        t0 = adesso
        print("primo giro: nessun marcatore, parto da adesso")
    eventi = richiami_dal(t0)
    conta = {}
    for _, nodi in eventi:
        for n in set(nodi):
            conta[n] = conta.get(n, 0) + 1
    print(f"richiami dal {time.strftime('%d/%m %H:%M', time.localtime(t0))}: {len(eventi)} eventi, "
          f"{len(conta)} ricordi")
    if a.dry:
        for n in sorted(conta, key=lambda k: -conta[k])[:10]:
            print(f"  ricordo {n}: {conta[n]} richiami")
        print("DRY: niente scritto")
        return
    esiti = {True: 0, False: 0, None: 0}
    for n in sorted(conta):            # un rinforzo vissuto per ricordo per notte
        esiti[rinforza(n)] += 1
    print(f"{esiti[True]} ricordi rinforzati, {esiti[False]} corretti (non si rinforzano), {esiti[None]} non nel Lux")
    MARCATORE.write_text(f"{adesso}\n")
    print("SINCRONIA-COMPLETA")


if __name__ == "__main__":
    sys.exit(main())
