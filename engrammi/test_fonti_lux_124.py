#!/usr/bin/env python3
"""Lux 1.24.0 (PIANO-1.24-FONTI.md, l'utente 13/11): siti come engrammi, fiducia, conferme e smentite. Tutto su una COPIA
(LUX_DIR temporanea) della 1.23.0; serve l'embedder (:8094). Uso: cd engrammi && /data/venv-spacy/bin/python
test_fonti_lux_124.py"""
import os
import shutil
import tempfile

T = tempfile.mkdtemp(prefix="fo124-")
shutil.copytree("/data/memoria-episodica-affettiva/engrammi/lux-1.23.0", f"{T}/lux")
os.environ["LUX_DIR"] = f"{T}/lux"
import numpy as np  # noqa: E402

import lux_engrammi as X  # noqa: E402

FIRMA = {"joy": 1.2, "trust": 0.8}
L'AGENTE, LEI = "@agente:localhost", X.FONTE_CERTA
TESTI = ["Il porto di Rotterdam ha movimentato quattrocento milioni di tonnellate di merci nel duemilaventicinque.",
         "La centrale nucleare di Zaporizhzhia resta spenta per la mancanza di linee elettriche esterne sicure.",
         "Il prezzo del rame ha superato i diecimila dollari per tonnellata alla borsa dei metalli di Londra.",
         "Il ghiacciaio del Rodano perde ogni estate quasi un metro di spessore secondo le misure svizzere.",
         "La biblioteca di Alessandria custodiva rotoli di papiro copiati dalle navi che entravano nel porto."]


def nuovo(testo, fonte=L'AGENTE, siti=None, ts=None):
    nuovo.k += 1
    return X.aggiungi_ricordo({"testo": testo, "firma": FIRMA, "classe": "vissuto", "ts": ts or 1.9e9 + nuovo.k,
                               "fonte": fonte, "siti": siti or []})


nuovo.k = 0
L0 = X.Lux()
fot0 = {n: L0.ricomponi(n) for n in list(L0.ricordi)[:50]}
prof0 = (L0.prof_nid.copy(), L0.profz.copy())

# 1. un ricordo con un sito: engramma del dominio, arco -1 {fonte}, siti_di; ricomposizione e profilo invariati
a = nuovo(TESTI[0], siti=["esempio.org"])
L = X.Lux()
L.salva_stato = lambda: None
assert L.siti_di[a] == ["esempio.org"] and L.ricordi_di_sito["esempio.org"] == {a}
e = L.chiavi["esempio.org"]
j = np.nonzero((L.A[:, 0] == a) & (L.A[:, 1] == -1))[0]
assert len(j) == 1 and L.A[j[0], 2] == e and X.param_testo(int(L.P[L.A[j[0], 4]]), L.altri) == X.FONTE
assert e not in L.per_engramma, "l'engramma del sito non deve avere archi vivi"
assert L.ricordi[a]["siti"] == ["esempio.org"]
b = nuovo(TESTI[0].replace("Rotterdam", "Anversa"))   # stesso testo senza sito: stessa ricomposizione a meno del nome
assert L.ricomponi(a).replace("Rotterdam", "Anversa") == X.Lux().ricomponi(b)
assert all(L.ricomponi(n) == t for n, t in fot0.items())
k = np.isin(L.prof_nid, prof0[0])
assert np.array_equal(L.prof_nid[k], prof0[0])
print("1 sito come engramma: ok", flush=True)

# 2. stesso sito con altre maiuscole = stesso engramma; engramma gia' esistente (OilPrice.com) riusato per chiave
c = nuovo(TESTI[1], siti=["Esempio.ORG", "OilPrice.com"])
L = X.Lux()
assert L.siti_di[c] == ["esempio.org", "oilprice.com"], L.siti_di[c]
assert L.ricordi_di_sito["esempio.org"] == {a, c}
assert sum(chiave == "esempio.org" for chiave in map(X.chiave, L.testi)) == 1
print("2 maiuscole e engrammi gia' noti: ok", flush=True)

# 3. conferme (D2): l'utente dice la stessa cosa -> fiducia su; una volta per ricordo; l'agente non conferma; un sito non si
#    conferma da se'; tre conferme -> certo
d1 = nuovo(TESTI[2], siti=["metalli.it"])
d2 = nuovo(TESTI[3], siti=["metalli.it"])
d3 = nuovo(TESTI[4], siti=["metalli.it"])
L = X.Lux()
L.salva_stato = lambda: None
assert not L.certo("metalli.it")
s = nuovo(TESTI[2] + " Lo ha detto anche il telegiornale.", fonte=L'AGENTE)
assert X.Lux().conferma(s) == []
x1 = nuovo("Ho letto che " + TESTI[2][0].lower() + TESTI[2][1:], fonte=LEI)
L = X.Lux()
assert L.conferma(x1) == ["metalli.it"] and abs(L.fiducia["metalli.it"][0] - 0.28) < 1e-9
assert L.conferma(x1) == [], "lo stesso ricordo si conferma una volta sola"
L.salva_stato()
cile = nuovo("Il prezzo del rame raffinato in Cile e' salito per la siccita' nelle miniere del deserto di Atacama.",
             siti=["cile.cl"])
corto = nuovo("Il prezzo del rame.", fonte=LEI)
assert X.Lux().conferma(corto) == [], "una frase corta con due parole in comune non conferma"
for t in (TESTI[3], TESTI[4]):
    x = nuovo("Mi hanno detto che " + t[0].lower() + t[1:], fonte=LEI)
    L = X.Lux()
    assert L.conferma(x) == ["metalli.it"]
    L.salva_stato()
L = X.Lux()
assert L.fiducia["metalli.it"][1] == 3 and L.certo("metalli.it") and L.certo("Metalli.IT")
d5 = nuovo("Il nichel ha raggiunto i ventimila dollari per tonnellata alla borsa dei metalli di Londra.",
           siti=["metalli.it"])
auto = nuovo("Il nichel ha raggiunto i ventimila dollari per tonnellata alla borsa dei metalli di Londra, ieri.",
             siti=["metalli.it"])
L = X.Lux()
assert L.certo("metalli.it") and L.conferma(auto) == [] and d5 not in L.confermati, "un sito non si conferma da se'"
due = nuovo("Il treno ad alta velocita' fra Torino e Lione aprira' la galleria di base del Moncenisio nel 2033.",
            siti=["uno.net", "due.net"])
x = nuovo("Mi hanno detto che il treno ad alta velocita' fra Torino e Lione aprira' la galleria del Moncenisio nel 2033.",
          fonte=LEI)
L = X.Lux()
assert sorted(L.conferma(x)) == ["due.net", "uno.net"], "un ricordo con due siti conferma tutti e due"
print("3 conferme: ok", flush=True)

# 4. smentita (D3): correzione di un ricordo del sito -> fiducia dimezzata, non piu' certo; stato su disco
L = X.Lux()
w = L.fiducia["metalli.it"][0]
cod = X.correggi(L.ricordi[d1]["codice"], "Il prezzo del rame e' rimasto sotto i novemila dollari.",
                 campi={"fonte": LEI, "siti": []})
L = X.Lux()
assert L.smentisci(d1) == ["metalli.it"]
assert abs(L.fiducia["metalli.it"][0] - w / 2) < 1e-9 and L.fiducia["metalli.it"][2] == 1 and not L.certo("metalli.it")
n_c = L.da_codice[cod]
assert L.ricordi[n_c]["fonte"] == LEI and L.corregge[n_c] == d1
L.salva_stato()
L2 = X.Lux()
assert L2.fiducia == L.fiducia and L2.confermati == L.confermati
print("4 smentita e stato: ok", flush=True)

# 6. servizio: /fiducia, /aggiungi con siti (anche sbagliati), /correggi con fonte e siti, /salute
import json  # noqa: E402
import threading  # noqa: E402
import urllib.request  # noqa: E402
from http.server import HTTPServer  # noqa: E402

import servizio_lux as SV  # noqa: E402

srv = HTTPServer(("127.0.0.1", 0), SV.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def post(p, d):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}{p}", json.dumps(d).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


assert post("/fiducia", {"siti": ["metalli.it", "mai.visto", 3]}) == {"certi": {"metalli.it": False, "mai.visto": False}}
r = post("/aggiungi", {"testo": "Una frase nuova arrivata da una pagina di prova sul servizio.", "firma": FIRMA,
                       "classe": "vissuto", "ts": 1.95e9, "fonte": L'AGENTE, "siti": "stringa.it"})
assert SV.lux().siti_di.get(r["nid"]) is None, "una stringa al posto della lista non fa siti"
r = post("/aggiungi", {"testo": "Un'altra frase nuova arrivata da una pagina di prova sul servizio.", "firma": FIRMA,
                       "classe": "vissuto", "ts": 1.96e9, "fonte": L'AGENTE, "siti": ["prova.net"]})
assert SV.lux().siti_di[r["nid"]] == ["prova.net"]
w = SV.L.fiducia["metalli.it"][0]
c = post("/correggi", {"codice": SV.L.ricordi[d2]["codice"], "testo": "Il ghiacciaio del Rodano perde mezzo metro.",
                       "fonte": LEI, "siti": []})["codice"]
assert abs(SV.lux().fiducia["metalli.it"][0] - w / 2) < 1e-9 and SV.L.ricordi[SV.L.da_codice[c]]["fonte"] == LEI
assert abs(X.Lux().fiducia["metalli.it"][0] - w / 2) < 1e-9, "la smentita deve essere su disco"
sal = json.load(urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/salute"))
assert sal["siti"] == len(SV.L.ricordi_di_sito) >= 3, sal
srv.shutdown()
L2 = X.Lux()
print("6 servizio: ok", flush=True)

# 5. costruisci conserva i legami dei siti (nuova cartella dalla copia come PRECEDENTE)
X.PRECEDENTE, X.DIR = f"{T}/lux", f"{T}/ricostruito"
X.NPZ, X.META, X.STATO = f"{X.DIR}/lux.npz", f"{X.DIR}/lux-meta.json", f"{X.DIR}/lux-stato.npz"
X.costruisci()
assert X.Lux.struttura(X.DIR).siti_di == L2.siti_di
print("5 costruisci: ok", flush=True)

print("test_fonti_lux_124: TUTTO VERDE")
