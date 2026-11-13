#!/usr/bin/env python3
"""Lux 1.22.0 (PIANO-INTERFASE-23-TRATTI.md): ricombinazione mnemonica. Sul Lux vero in sola lettura.
Uso: cd engrammi && /data/venv-spacy/bin/python test_ricombina_122.py"""
import lux_engrammi as X

L = X.Lux()
L.salva_stato = lambda: None
spazi = lambda s: " ".join(s.split())   # noqa: E731

# 1. frasi: unite ridanno il ricordo, archi divisi senza buchi, ogni frase tranne l'ultima chiude a fine frase
for nid in L.ricordi:
    fr = L.frasi(nid)
    assert spazi(" ".join(t for t, _, _ in fr)) == spazi(L.ricomponi(nid)), (nid, [t for t, _, _ in fr])
    assert not any(t.startswith(tuple(",.;:!?)…")) for t, _, _ in fr[1:]), (nid, [t[:20] for t, _, _ in fr])   # niente segni attaccati in testa
    assert sorted(j for _, js, _ in fr for j in js) == sorted(L.per_ricordo.get(nid, [])), nid
    for t, _, _ in fr[:-1]:
        assert t.rstrip().rstrip(",;:)").endswith(tuple(X.FINE_FRASE)), (nid, t)   # anche "!)" e "...;"
    if len(fr) > 1:   # niente frasi senza lettere ("2.", un'emoji sola): stanno con la frase vicina
        assert all(any(c.isalpha() for c in t) for t, _, _ in fr), (nid, [t for t, _, _ in fr])
    for t, js, eng in fr:   # gli engrammi della frase sono quelli scritti nella frase
        assert eng <= {int(e) for j in js for e in L.A[j, 2:4]}, nid
print("1 frasi: ok", flush=True)

# 2. emoji per significato
assert X.e_emoji("😄") and X.e_emoji("❤️") and not X.e_emoji("ciao") and not X.e_emoji("")
assert X.significato("😄") == "gioia"
nulle = [e for e, s in {**X.EMOJI["emozioni"], **X.EMOJI["altre"]}.items() if s is None]
assert all(X.significato(e) is None for e in nulle)
q = "Ciao l'agente, come stai? 😄"
assert L.accendi(q) == L.accendi(q)   # niente stato
r1 = L.richiama(q, 5, soglia=0, oggi=100.0, ora=1.8e9)
r2 = L.richiama(q, 5, soglia=0, oggi=100.0, ora=1.8e9, att=L.accendi(q))
assert r1 == r2
em = [(i, X.significato(t)) for i, t in enumerate(L.testi) if X.e_emoji(t) and X.significato(t)]
assert em and all(i in L.accendi(g) for i, g in em[:5]), "un'emoji si accende col suo significato"
print("2 emoji e att: ok", flush=True)

import numpy as np  # noqa: E402

# 3. rinforza_archi: crescono solo gli archi dati; rinforza(nid) = rinforza_archi(archi del ricordo)
S0, U0 = L.S.copy(), L.U.copy()
nid = sorted(L.ricordi)[5]
js = L.per_ricordo[nid][:2]
L.rinforza_archi(js, oggi=float(L.U.max()) + 30)
cambiati = set(np.nonzero(L.S != S0)[0].tolist())
assert cambiati and cambiati <= set(js), cambiati
L.S[:], L.U[:] = S0, U0
print("3 rinforzo per archi: ok", flush=True)

# 4. ricombina
t = "Ciao l'agente, oggi ho pensato alla casa al mare"
r = L.ricombina(t, numero=3, oggi=100.0, ora=1.8e9)
assert r is not None
righe = r["risposta"].split("\n")
assert righe[0] == "3° ricombinazione mnemonica" and 1 <= len(righe) - 1 <= X.TRATTI_MAX, righe
assert len(set(r["nid"])) == len(r["nid"]) == len(righe) - 1                    # un tratto per ricordo
assert sum(len(x) for x in righe[1:]) / X.CAR_TOKEN <= X.TOKEN_MAX
assert all(x.strip() for x in righe[1:])
assert r["dominante"] is None or r["dominante"] in X.EMOZIONI
assert r["codici"] == [L.ricordi[n]["codice"] for n in r["nid"]]
# impronta (l'utente 13/11 sera): la firma dell'engramma guida, sugli stessi assi, con la stessa emozione piu' alta
assert (r["impronta"] is None) == (r["dominante"] is None)
if r["impronta"]:
    tr = np.load(X.TRADUZIONE_L29, allow_pickle=True)
    assert set(r["impronta"]) == {str(a) for a in tr["assi"]} and all(np.isfinite(v) for v in r["impronta"].values())
# esclusi: mai un ricordo gia' consegnato
r2 = L.ricombina(t, oggi=100.0, ora=1.8e9, esclusi=r["codici"])
assert r2 is None or not set(r2["nid"]) & set(r["nid"])
# niente sopra soglia = None
assert L.ricombina("zqxw vbnm", oggi=100.0, ora=1.8e9) is None
# rinforzo: solo archi dei tratti
S0, U0 = L.S.copy(), L.U.copy()
r3 = L.ricombina(t, oggi=float(L.U.max()) + 30, ora=1.8e9)
cambiati = set(np.nonzero(L.S != S0)[0].tolist())
assert cambiati and cambiati <= set(r3["archi"]), cambiati
L.S[:], L.U[:] = S0, U0
# coda: chi e' in coda e' candidato; chi e' mostrato esce dalla coda
coda = []
r4 = L.ricombina(t, oggi=100.0, ora=1.8e9, coda=coda)
assert not {L.da_codice[c] for c in coda} & set(r4["nid"])
# revisione 13/11: un ricordo in coda esce anche con un messaggio che non ne accende parole
if coda:
    testa = L.da_codice[coda[0]]
    r5 = L.ricombina("Ciao l'agente", oggi=100.0, ora=1.8e9, coda=list(coda), esclusi=r4["codici"])
    assert r5 is not None and (testa in r5["nid"] or len(r5["nid"]) == X.TRATTI_MAX), (testa, r5)
print("4 ricombina: ok", flush=True)
