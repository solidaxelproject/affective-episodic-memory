#!/usr/bin/env python3
"""Stress-test del task 1 di PIANO-FIRMA-44-ASSI.md: vettori_firma.lettura() (44 assi della lettura della firma,
variante C: media dei 44 tolta per strato). Scrive su una copia nello scratchpad del sistema, mai sul file vero.
Uso: /data/jspace/venv/bin/python test_vettori_lettura.py"""
import hashlib
import json
import os
import sys
import tempfile

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memoria  # noqa: E402
import vettori_firma as VF  # noqa: E402


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


VECCHI = ["/data/jspace/out-occamy/vettori-firma.pt", "/data/jspace/out-occamy/vettori-se-proprie.pt"]
prima = [sha(p) for p in VECCHI]
d = VF.lettura()
ordine = [e["en"] for e in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "emozioni.json")))]
print("1. 44 assi: i 24 della ruota + le 20 diadi con vettore, nell'ordine di emozioni.json", flush=True)
base = torch.load(VECCHI[0], weights_only=False)
assert len(d["assi"]) == 44, len(d["assi"])
assert set(base["assi"]) <= set(d["assi"])
diadi = [a for a in d["assi"] if a not in base["assi"]]
assert len(diadi) == 20 and set(diadi) <= memoria.CON_VETTORE, diadi
assert d["assi"] == [e for e in ordine if e in set(d["assi"])]
assert not {"aggressiveness", "outrage", "triumph"} & set(d["assi"])
print("2. fonte per tutti: la ruota come vettori-firma.pt, le diadi sé-proprio", flush=True)
assert set(d["fonte"]) == set(d["assi"])
assert all(d["fonte"][a] == base["fonte"][a] for a in base["assi"])
assert all(d["fonte"][a] == "sé-proprio" for a in diadi)
assert d["strati"] == list(range(15, 32)) and "C" in d["metodo"]
print("3. unitari per strato, media dei 44 circa zero, assi distinti", flush=True)
M = np.stack([np.stack([d["vettori"][a][l].numpy() for l in d["strati"]]) for a in d["assi"]])   # 44 x 17 x 2048
assert np.allclose(np.linalg.norm(M, axis=-1), 1, atol=1e-5)
C = np.einsum("ild,jld->ij", M, M) / M.shape[1]
fuori = C[~np.eye(44, dtype=bool)]
print(f"   coseno fra assi: medio {fuori.mean():+.3f}, massimo {fuori.max():.3f}")
assert abs(fuori.mean()) < 0.05 and fuori.max() < 0.9
grezzi = np.stack([np.stack([(lambda v: v / np.linalg.norm(v))(base["vettori"][a][l].numpy()) for l in d["strati"]])
                   for a in base["assi"]])
assert np.einsum("ild,jld->ij", grezzi, grezzi)[~np.eye(24, dtype=bool)].mean() / 17 > 0.3   # oggi: assi vicini
print("4. un asse corretto = (grezzo unitario - media dei 44), di nuovo unitario", flush=True)
src = VF.S.sorgenti()["sé-proprio"]
g = {a: np.stack([(lambda v: v / np.linalg.norm(v))((base["vettori"][a] if a in base["assi"] else src[a])[l].float().numpy())
                  for l in d["strati"]]) for a in d["assi"]}
m = np.mean(list(g.values()), 0)
for a in ("love", "joy", "terror"):
    atteso = (g[a] - m) / np.linalg.norm(g[a] - m, axis=-1, keepdims=True)
    assert np.allclose(atteso, M[d["assi"].index(a)], atol=1e-5), a
print("5. salvataggio solo dove si chiede; vettori dello steering e vettori-firma.pt intatti", flush=True)
with tempfile.TemporaryDirectory() as t:
    VF.salva_lettura(f"{t}/v.pt")
    assert torch.load(f"{t}/v.pt", weights_only=False)["assi"] == d["assi"]
assert [sha(p) for p in VECCHI] == prima
print("6. firma-subito: i vettori li dicono le statistiche; vettori e statistiche diversi = si ferma", flush=True)
import firma_se as F  # noqa: E402
import firma_subito as FS  # noqa: E402
vecchie = torch.load(FS.STATS, weights_only=False)   # dal 09/11 sera a 44 assi: le "vecchie" a 24 si costruiscono
vecchie = {k: v for k, v in vecchie.items() if k != "vettori"}
vecchie.update(assi=base["assi"], mean=torch.zeros(24))
with tempfile.TemporaryDirectory() as t:
    VF.salva_lettura(f"{t}/v.pt")
    casi = [(dict(vecchie), F.VETTORI, True),                                  # come oggi: niente chiave, 24 assi
            (dict(vecchie, vettori=f"{t}/v.pt"), f"{t}/v.pt", False),          # 44 vettori, statistiche a 24
            (dict(vecchie, vettori=f"{t}/v.pt", assi=d["assi"], mean=torch.zeros(44)), f"{t}/v.pt", True)]
    for k, (st, atteso, va) in enumerate(casi):
        torch.save(st, f"{t}/s{k}.pt")
        FS.STATS = f"{t}/s{k}.pt"
        FS._st.clear()
        try:
            FS.stats()
            assert va, f"caso {k}: doveva fermarsi"
        except AssertionError as e:
            assert not va and "diversi" in str(e), (k, e)
        assert F.VETTORI == atteso, (k, F.VETTORI)
        assert len(F.vettori()[0]) == (24 if k == 0 else 44)
print("TUTTO VERDE")
