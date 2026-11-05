#!/usr/bin/env python3
"""Vettori della firma (PIANO-FIRMA-ENGRAMMI.md, B1, l'utente 31/10/2026): i 24 vettori se' in uso per le emozioni della
ruota di Plutchik, ognuno dalla fonte che ha dato la sua fascia, sugli strati 15-31, unitari per strato.
Uscita: /data/jspace/out-occamy/vettori-firma.pt = {"assi", "fonte", "strati", "vettori": {asse: {strato: tensore}}}.
Uso: /data/jspace/venv/bin/python vettori_firma.py"""
import json
import sys

import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering")
import sistema as S   # noqa: E402  (sorgenti(): gli stessi vettori delle prove e del confronto)

USCITA = "/data/jspace/out-occamy/vettori-firma.pt"
STRATI = list(range(15, 32))   # D3: gli strati dell'iniezione
# fonte di ogni emozione = quella delle fasce (DOSI-EMOZIONI.md, pagina_dosi, confronto.py); vigilanza: il vettore
# vecchio sé-nuovo, quello della diade con attesa
FONTI = {**dict.fromkeys(["gioia", "fiducia", "paura", "sorpresa", "tristezza", "disgusto", "rabbia"], "sé-medio"),
         **dict.fromkeys(["attesa", "vigilanza", "accettazione", "apprensione", "distrazione", "noia", "fastidio",
                          "interesse"], "sé-nuovo"),
         **dict.fromkeys(["serenità", "malinconia"], "sé-esterno"),
         **dict.fromkeys(["estasi", "ammirazione", "cordoglio"], "sé-interno"),
         **dict.fromkeys(["terrore", "stupore", "ribrezzo", "furia"], "sé-proprio")}
ORDINE = [x["it"] for x in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))]


def costruisci():
    src = S.sorgenti()
    it = [e for e in ORDINE if e in FONTI]   # ordine di emozioni.json
    vettori = {}
    for e in it:
        v = src[FONTI[e]][S.EN[e]]
        vettori[S.EN[e]] = {l: (v[l].float() / v[l].float().norm()).clone() for l in STRATI}
    return {"assi": [S.EN[e] for e in it], "fonte": {S.EN[e]: FONTI[e] for e in it}, "strati": STRATI,
            "vettori": vettori}


if __name__ == "__main__":
    d = costruisci()
    torch.save(d, USCITA)
    print(f"{len(d['assi'])} assi, strati {STRATI[0]}-{STRATI[-1]} -> {USCITA}")
