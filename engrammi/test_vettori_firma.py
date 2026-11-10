#!/usr/bin/env python3
"""Stress-test di B1 (PIANO-FIRMA-ENGRAMMI.md): vettori-firma.pt. Uso: /data/jspace/venv/bin/python test_vettori_firma.py"""
import itertools
import json
import os
import sys

import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering/confronto")
import vettori_firma as VF   # noqa: E402
import confronto as C        # noqa: E402  (le fonti usate dalla pagina del confronto)

S = VF.S
d = torch.load(VF.USCITA, weights_only=False)
RUOTA = ["gioia", "fiducia", "paura", "sorpresa", "tristezza", "disgusto", "rabbia", "attesa",
         "estasi", "ammirazione", "terrore", "stupore", "cordoglio", "ribrezzo", "furia", "vigilanza",
         "serenità", "accettazione", "apprensione", "distrazione", "malinconia", "noia", "fastidio", "interesse"]
EN = S.EN

# 24 assi, solo la ruota, nell'ordine di emozioni.json
assert len(d["assi"]) == 24 and set(d["assi"]) == {EN[e] for e in RUOTA}, d["assi"]
ordine = [x["en"] for x in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))]
assert d["assi"] == [e for e in ordine if e in d["assi"]]
assert d["strati"] == list(range(15, 32))

# ogni asse: strati 15-31, finiti, norma 1
for a in d["assi"]:
    assert sorted(d["vettori"][a]) == list(range(15, 32)), a
    for l, v in d["vettori"][a].items():
        assert v.shape == (2048,) and torch.isfinite(v).all(), (a, l)
        assert abs(float(v.norm()) - 1) < 1e-4, (a, l, float(v.norm()))

# stessi vettori della pagina del confronto (sistema.strati, finestra fino31) per le emozioni che la pagina inietta da sole
cos = lambda x, y: float(torch.dot(x, y) / (x.norm() * y.norm()))
for e in C.FONTI:
    if e in C.DIADI:
        continue
    L = C.strati(e, 0.03)
    for l in range(15, 32):
        assert cos(torch.tensor(L[str(l)]), d["vettori"][EN[e]][l]) > 0.9999, (e, l)
assert d["fonte"][EN["vigilanza"]] == C.FONTI["vigilanza"] == "sé-nuovo"
# le diadi della pagina: la componente intensa dalla stessa fonte (sé-proprio per terrore e stupore)
for e in ("terrore", "stupore"):
    assert C.FONTI[e] == d["fonte"][EN[e]] == "sé-proprio"   # 10/11: una tabella sola (steering.FONTI)
    src = S.sorgenti()["sé-medio+proprio"][EN[e]]
    assert cos(src[24].float(), d["vettori"][EN[e]][24]) > 0.9999, e

# nessun doppione: due assi diversi non hanno lo stesso vettore (fonte sbagliata = copia di un altro asse)
for a, b in itertools.combinations(d["assi"], 2):
    assert cos(d["vettori"][a][24], d["vettori"][b][24]) < 0.99, (a, b)
# terrore/stupore/ribrezzo/furia davvero dalle scene proprie, non dal giro interno
interno = S.sorgenti()["sé-interno"]
for e in ("terrore", "stupore", "ribrezzo", "furia"):
    assert cos(interno[EN[e]][24].float(), d["vettori"][EN[e]][24]) < 0.99, e

# deterministico: rifarlo da' gli stessi numeri; il file si rilegge identico
d2 = VF.costruisci()
assert d2["assi"] == d["assi"] and d2["fonte"] == d["fonte"]
for a in d["assi"]:
    for l in range(15, 32):
        assert torch.equal(d2["vettori"][a][l], d["vettori"][a][l]), (a, l)
assert os.path.getsize(VF.USCITA) > 24 * 17 * 2048 * 4
print("TUTTO VERDE")
