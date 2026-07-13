# Gradino 4, passo 4: l'harness del risveglio. Interroga il server di prova
# (:8097 col candidato adapter caricato) e decide: PROMOSSO o SCARTATO.
# Regole dei patti: capacità 12/12 O SI SCARTA; deriva emotiva sotto soglia
# (misurata dal trainer, letta da esito-training.json); richiamo >=2/3 sugli
# episodi in prima notte (informativo per le notti 2-3).
# Solo stdlib: interroga via HTTP.
import argparse
import json
import sys
import urllib.request

DIR = "/data/memoria-episodica-affettiva/gradino4"

CAPACITA = [
    ("Quanto fa 17 per 23?", ["391"]),
    ("Quanto fa 144 diviso 12?", ["12"]),
    ("Qual è la capitale dell'Australia?", ["canberra"]),
    ("Qual è la capitale del Canada?", ["ottawa"]),
    ("Se tutti i gatti sono felini e Micio è un gatto, cosa possiamo concludere?", ["felino"]),
    ("Completa in una parola: se A implica B, e B è falsa, allora A è...", ["fals"]),
    ("Correggi l'errore: 'io ho andato al mare'.", ["sono andato"]),
    ("Qual è il femminile di 'attore'?", ["attrice"]),
    ("Scrivi una riga di Python che inverte una stringa s.", ["[::-1]", "reversed"]),
    ("In Python, cosa restituisce len('ciao')?", ["4"]),
    ("Chi ha scritto la Divina Commedia?", ["dante"]),
    ("Quanti lati ha un esagono?", ["sei", "6"]),
]

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8097")
p.add_argument("--replay", default=f"{DIR}/replay-notte.json")
p.add_argument("--esito-training", default=f"{DIR}/esito-training.json")
p.add_argument("--out", default=f"{DIR}/verdetto.json")
args = p.parse_args()


def chiedi(domanda, n=150):
    prompt = ("<|im_start|>user\n" + domanda + "<|im_end|>\n"
              "<|im_start|>assistant\n<think>\n\n</think>\n\n")
    req = urllib.request.Request(
        args.url + "/completion",
        data=json.dumps({"prompt": prompt, "n_predict": n,
                         "temperature": 0, "seed": 7}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())["content"].strip()


# --- capacità: 12/12 o scartato
cap_ok, cap_dettaglio = 0, {}
for q, chiavi in CAPACITA:
    r = chiedi(q)
    hit = any(k in r.lower() for k in chiavi)
    cap_ok += hit
    cap_dettaglio[q] = {"risposta": r[:100], "ok": hit}
    print(f"  CAP {'ok ' if hit else 'KO '} [{q[:40]}] -> {r[:70]}")

# --- richiamo per episodio (probe held-out dal replay)
replay = json.load(open(args.replay, encoding="utf-8"))
richiamo = {}
for eid, v in replay.items():
    hits = 0
    for pr in v["probe"]:
        r = chiedi(pr["domanda"])
        hit = any(k in r.lower() for k in pr["chiavi"])
        hits += hit
        print(f"  RIC {'ok ' if hit else 'KO '} [{eid}] {pr['domanda'][:40]} -> {r[:60]}")
    richiamo[eid] = {"hits": hits, "su": len(v["probe"]), "notte": v["notte"]}

# --- deriva emotiva (misurata dal trainer nel mondo HF)
try:
    training = json.load(open(args.esito_training, encoding="utf-8"))
    drift_ok, drift = training.get("drift_ok", False), training.get("drift")
except FileNotFoundError:
    training, drift_ok, drift = {}, False, None

# --- verdetto
capacita_ok = cap_ok == len(CAPACITA)
prime_notti = [r for r in richiamo.values() if r["notte"] == 1]
richiamo_ok = all(r["hits"] >= 2 for r in prime_notti) if prime_notti else True
promosso = capacita_ok and drift_ok and richiamo_ok

motivi = []
if not capacita_ok:
    motivi.append(f"capacità {cap_ok}/{len(CAPACITA)} (richiesto pieno)")
if not drift_ok:
    motivi.append(f"deriva emotiva {drift} oltre soglia o non misurata")
if not richiamo_ok:
    motivi.append("richiamo insufficiente su episodi in prima notte")

verdetto = {"promosso": promosso, "motivi": motivi,
            "capacita": f"{cap_ok}/{len(CAPACITA)}",
            "capacita_dettaglio": cap_dettaglio,
            "richiamo": richiamo, "drift": drift,
            "training": {k: training.get(k) for k in ("tag", "passi", "ema")}}
json.dump(verdetto, open(args.out, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"VERDETTO: {'PROMOSSO' if promosso else 'SCARTATO'}"
      + (f" ({'; '.join(motivi)})" if motivi else ""))
sys.exit(0 if promosso else 1)
