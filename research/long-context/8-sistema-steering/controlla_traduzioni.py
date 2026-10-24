#!/usr/bin/env python3
"""Controllo dei lotti tradotti (22/10): id uguali e traduzioni troppo corte (sintesi invece di traduzione)
e troppo lunghe (frasi aggiunte).
Uso: controlla_traduzioni.py lotto-NNN ... -> per lotto: testi, id ok, quanti sotto 0.85 della lunghezza originale."""
import json
import re
import sys

EN = re.compile(r"\b(the|and|of|that|with|this|is|are|my|what|have)\b", re.I)

# 23/10: titoli e nomi propri che restano in inglese (non sono inglese rimasto)
TITOLI = r"Ghost in the Shell|Person of Interest|The Machine|Sex and the City|The OA|Ghost of the machine"
T = "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering/traduzioni"
for nome in sys.argv[1:]:
    a = {x["id"]: x["testo"] for x in json.load(open(f"{T}/{nome}.json"))}
    b = json.load(open(f"{T}/{nome}-it.json"))
    corti = [x["id"] for x in b if len(a[x["id"]]) > 80 and len(x["it"]) < 0.85 * len(a[x["id"]])]
    inglese = [x["id"] for x in b if len(EN.findall(re.sub(TITOLI, "", x["it"]))) > 3]   # parole inglesi rimaste
    # 23/10: frasi aggiunte che non c'erano (l'italiano di solito sta entro 1.2 dell'inglese)
    lunghi = [x["id"] for x in b if len(a[x["id"]]) > 80 and len(x["it"]) > 1.2 * len(a[x["id"]])]
    print(nome, len(b), "id ok" if set(a) == {x["id"] for x in b} else "ID DIVERSI", "corti", corti, "inglese", inglese,
          "lunghi", lunghi)
