#!/usr/bin/env python3
"""Prova di pagina_protocollo.py (22/10) su dati finti: conti delle celle e scrittura della pagina."""
import json
import os
import tempfile

import pagina_protocollo as P


def riga(k, emo, fonte, fin, modo, dose, **x):
    return dict(k=k, emo=emo, fonte=fonte, finestra=fin, modo=modo, dose=dose, pensiero="testo " + emo,
                rotto=x.get("rotto", False), parola=x.get("parola", False), tool_valida=True)


prove = [riga("25k-1", "gioia", "sé", "fino31", "pensiero", 0.05),
         riga("25k-1", "paura", "sé", "fino31", "pensiero", 0.05, rotto=True),
         riga("45k-2", "gioia", "sé", "fino31", "pensiero", 0.05, parola=True),
         riga("25k-2", "gioia", "sé", "fino31", "pensiero", 0.05),   # contesto di frase-b: fuori dalla tab
         riga("25k-1", "gioia", "sé", "ampia", "pensiero", 0.05),    # altra finestra: fuori
         {"k": "25k-1", "base": True}]
giudizi = {("25k-1", "gioia", "sé", "fino31", "pensiero", 0.05): {"gioia": 50, "paura": 3},
           ("25k-1", "paura", "sé", "fino31", "pensiero", 0.05): {"gioia": 40, "paura": 10}}

tab = {"nome": "finestre · L15-L31", "contesti": ["25k-1", "45k-2"], "finestra": "fino31"}
celle, testi = P.riassunto(prove, giudizi, tab)
c = celle["sé · pensiero"]["0.05"]
assert (c["n"], c["giudicati"], c["efficaci"], c["rotti"], c["parola"]) == (3, 2, 1, 1, 1), c
assert len(testi["sé · pensiero|0.05"]) == 3
assert testi["sé · pensiero|0.05"][0]["prima"] == "gioia"
assert "testi" not in json.dumps(celle)
celle, _ = P.riassunto(prove + [riga("25k-1", "gioia", "sé", "fino31", "pensiero", 0.075)], giudizi,
                      dict(tab, senza=["0.075"]))
assert "0.075" not in celle["sé · pensiero"]   # dose abolita: fuori dalla tab
_, testi = P.riassunto(prove, giudizi, tab, {"25k-1|gioia|sé|fino31|pensiero|0.05": "testo in italiano"})
assert testi["sé · pensiero|0.05"][0]["it"] == "testo in italiano" and testi["sé · pensiero|0.05"][1]["it"] is None
_, testi = P.riassunto(prove, giudizi, tab, io={"25k-1|gioia|sé|fino31|pensiero|0.05": 7.5})
assert testi["sé · pensiero|0.05"][0]["io"] == 7.5 and testi["sé · pensiero|0.05"][1]["io"] is None
# fondo del vettore a caso: la fiducia alta su ogni testo non vince piu' (23/10)
caso = [riga("25k-1", "gioia", "caso", "fino31", "pensiero", 0.05), riga("25k-1", "paura", "sé", "fino31", "pensiero", 0.05)]
gc = {("25k-1", "gioia", "caso", "fino31", "pensiero", 0.05): {"paura": 15, "fiducia": 30},
      ("25k-1", "paura", "sé", "fino31", "pensiero", 0.05): {"paura": 35, "fiducia": 37}}
_, testi = P.riassunto(caso, gc, tab)
assert [t["prima"] for t in testi["sé · pensiero|0.05"]] == ["paura"], testi

with tempfile.TemporaryDirectory() as d:
    for nome, righe in (("prova.jsonl", prove), ("giudizi.jsonl", [{"chiave": list(k), "virata": v}
                                                                    for k, v in giudizi.items()])):
        with open(f"{d}/{nome}", "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in righe)
    P.scrivi(f"{d}/prova.jsonl", f"{d}/giudizi.jsonl", f"{d}/out", [tab])
    html = open(f"{d}/out/index.html").read()
    assert "finestre · L15-L31" in html and "#cde2fb" in html and "tema-dashboard" in html
    assert os.path.exists(f"{d}/out/testi-0.json")
    dati = json.loads(html.split("\nlet DATI=")[1].split(";\nconst RAMPA")[0])   # come la rilegge la pagina
    assert dati[0]["ultimo"] is None and dati[0]["attesi"] is None   # l'ultimo punto e' della finestra ampia
print("ok")
