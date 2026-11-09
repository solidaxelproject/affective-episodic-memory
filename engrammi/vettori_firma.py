#!/usr/bin/env python3
"""Vettori della firma (PIANO-FIRMA-ENGRAMMI.md, B1, l'utente 31/10/2026): i 24 vettori se' in uso per le emozioni della
ruota di Plutchik, ognuno dalla fonte che ha dato la sua fascia, sugli strati 15-31, unitari per strato.
Uscita: /data/jspace/out-occamy/vettori-firma.pt = {"assi", "fonte", "strati", "vettori": {asse: {strato: tensore}}}.
Uso: /data/jspace/venv/bin/python vettori_firma.py"""
import json
import os
import sys

import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # memoria.CON_VETTORE (lettura, 09/11)
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


LETTURA = "/data/jspace/out-occamy/vettori-lettura-firma.pt"


def lettura():
    """PIANO-FIRMA-44-ASSI.md (l'utente 09/11, variante C): i vettori con cui si LEGGE la firma, 44 assi = i 24 della ruota
    (costruisci) + le 20 diadi pure con vettore di steering (sé-proprio, memoria.CON_VETTORE), nell'ordine di
    emozioni.json; per strato la media dei 44 (unitari) si toglie da ognuno, poi di nuovo unitari. Lo steering non
    usa questi vettori: vettori-firma.pt e le fonti restano come sono."""
    import memoria
    base = costruisci()
    src = S.sorgenti()["sé-proprio"]
    diadi = [e for e in memoria.CON_VETTORE if e not in base["assi"]]
    assert len(diadi) == 20 and all(e in src for e in diadi), diadi
    fonte = {**base["fonte"], **dict.fromkeys(diadi, "sé-proprio")}
    assi = [S.EN[e] for e in ORDINE if S.EN[e] in fonte]
    assert len(assi) == 44, len(assi)
    grezzi = {a: base["vettori"][a] if a in base["vettori"] else
              {l: src[a][l].float() / src[a][l].float().norm() for l in STRATI} for a in assi}
    media = {l: torch.stack([grezzi[a][l] for a in assi]).mean(0) for l in STRATI}
    vettori = {a: {l: ((grezzi[a][l] - media[l]) / (grezzi[a][l] - media[l]).norm()).clone() for l in STRATI} for a in assi}
    return {"assi": assi, "fonte": {a: fonte[a] for a in assi}, "strati": STRATI, "vettori": vettori,
            "metodo": "C: 24 della ruota + 20 diadi, unitari, media dei 44 tolta per strato, di nuovo unitari"}


def salva_lettura(uscita=LETTURA):
    d = lettura()
    torch.save(d, uscita)
    return d


if __name__ == "__main__":
    if sys.argv[1:] == ["lettura"]:   # 09/11: Uso: ... vettori_firma.py lettura
        d = salva_lettura()
        print(f"{len(d['assi'])} assi (C), strati {STRATI[0]}-{STRATI[-1]} -> {LETTURA}")
        sys.exit(0)
    d = costruisci()
    torch.save(d, USCITA)
    print(f"{len(d['assi'])} assi, strati {STRATI[0]}-{STRATI[-1]} -> {USCITA}")
