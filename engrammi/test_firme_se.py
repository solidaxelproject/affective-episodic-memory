#!/usr/bin/env python3
"""Stress-test di B3 (PIANO-FIRMA-ENGRAMMI.md): rifirma di tutti i ricordi coi vettori se'.
  09/11 (PIANO-FIRMA-44-ASSI.md): assi dai vettori scritti nelle statistiche (44, variante C), emo_tag =
  memoria.dominante, letture = differenze per strato (letture-diff.pt); numero dei nodi e delle voci da memoria.db.
  dopo --scrivi:  tutti i nodi con firma sugli assi delle statistiche, emo_tag nei vettori del riflesso, salienza = max z,
                  statistiche coi metadati, quota della soglia nuova = quota vecchia (+-1 punto), addr_emo coerente
  stress:         --scrivi due volte su una copia = stesso risultato; il backup riporta memoria.db identico;
                  --leggi interrotto e ripreso = stesse letture di una corsa intera (server di prova acceso);
                  nodi senza contesto e nodi "letto" firmati come gli altri.
Uso: cd /data/jspace && venv/bin/python /data/memoria-episodica-affettiva/engrammi/test_firme_se.py"""
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
import firma_se as F  # noqa: E402

SCRIPT = "/data/memoria-episodica-affettiva/firme-occamy/ricalcola-firme-se.py"
fallimenti = []


def ok(cond, cosa):
    if not cond:
        fallimenti.append(cosa)
        print("  ROSSO:", cosa, flush=True)


def modulo(**env):
    """lo script caricato con le variabili d'ambiente date (copie al posto dei file veri)"""
    for k, v in env.items():
        os.environ[k] = v
    spec = importlib.util.spec_from_file_location("ricalcola_se", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def righe(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    r = c.execute("SELECT id, firma, emo_tag, salienza FROM nodi ORDER BY id").fetchall()
    c.close()
    return r


def dump(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    d = list(c.iterdump())
    c.close()
    return d


R = modulo()
stats = torch.load(R.STATS, weights_only=False)
F.usa(stats.get("vettori", F.VETTORI))
assi, _ = F.vettori()
voci_tutte = R.voci()[0]
n_nodi = sum(1 for x in voci_tutte if x[0] == "nodo")

print("1. memoria.db dopo la scrittura", flush=True)
nodi = righe(R.DB)
c = sqlite3.connect(f"file:{R.DB}?mode=ro", uri=True)
classi = dict(c.execute("SELECT id, classe FROM nodi"))
c.close()
ok(len(nodi) == n_nodi, f"nodi {len(nodi)}, attesi {n_nodi}")
cvec = [str(x) for x in np.load("/data/memoria-episodica-affettiva/emo-cvec-v2.npz")["nomi"]]
for nid, firma, tag, sal in nodi:
    f = json.loads(firma)
    ok(list(f) == assi, f"nodo {nid}: assi della firma {list(f)[:3]}...")
    ok(all(np.isfinite(x) for x in f.values()), f"nodo {nid}: firma non finita")
    ok(tag == R.memoria.dominante(f), f"nodo {nid}: emo_tag {tag} non e' la dominante (memoria.dominante)")
    ok(tag in cvec, f"nodo {nid}: emo_tag {tag} assente dai vettori del riflesso")
    ok(abs(sal - max(f.values())) < 1e-3, f"nodo {nid}: salienza {sal} != max z {max(f.values())}")
ok(any(classi[n] == "letto" for n, *_ in nodi), "nessun nodo 'letto' controllato")

print("2. addr_emo in vettori.pt", flush=True)
vec = torch.load(R.VEC, weights_only=True)
for nid, firma, *_ in nodi:
    if nid in vec:
        f = json.loads(firma)
        a = vec[nid]["addr_emo"]
        ok(torch.allclose(a, R.memoria.addr_emo(f), atol=1e-6),   # B7: 51 assi nell'ordine di emozioni.json
           f"nodo {nid}: addr_emo diversa dalla firma")

print("3. statistiche", flush=True)
ok(stats["assi"] == assi and stats["strati"] == list(range(15, 32)), "assi o strati delle statistiche")
ok(set(stats["fonti"]) == set(assi), "fonti delle statistiche")
ok("occamy-1.0-Q8_0.gguf" in stats["lettore"], f"lettore {stats['lettore']}")
ok(stats["n"] == len(voci_tutte) and len(stats["mean"]) == len(assi) and len(stats["mu"]) == 17,
   "n, mean o mu delle statistiche")
ok(stats.get("vettori") == R.VETTORI and len(assi) == 44, f"vettori delle statistiche {stats.get('vettori')}")
ok(all(len(v) == 2048 and torch.isfinite(v).all() for v in stats["mu"].values()), "mu non finita")
nuove, _, res = R.calcola()
ok(abs(res["quota_nuova"] - res["quota"]) <= 0.01, f"quota nuova {res['quota_nuova']:.4f} contro {res['quota']:.4f}")
ok(abs(res["soglia"] - stats["soglia"]) < 1e-12, "soglia ricalcolata diversa da quella salvata")
for nid, firma, tag, sal in nodi:
    ok(json.loads(firma) == nuove[nid][0], f"nodo {nid}: firma in memoria.db diversa dal ricalcolo")

print("4. nodi senza contesto firmati", flush=True)
v, chat = R.voci()
soli = [x for x in v if x[0] == "nodo" and not R.contesto(chat, x[2])]
ok(len(soli) >= 1, "nessun nodo senza contesto da controllare")
for _, nid, _, _ in soli:
    ok(nid in nuove and len(nuove[nid][0]) == len(assi), f"nodo senza contesto {nid} non firmato")

print("5. --scrivi due volte su una copia = stesso risultato; il backup riporta memoria.db identico", flush=True)
tmp = tempfile.mkdtemp(prefix="test-b3-", dir="/data/memoria-episodica-affettiva/firme-occamy")
try:
    sqlite3.connect(R.DB).backup(sqlite3.connect(f"{tmp}/memoria.db"))
    shutil.copy2(R.VEC, f"{tmp}/vettori.pt")
    prima = dump(f"{tmp}/memoria.db")
    C = modulo(MEM_SAM=tmp, STATS_SE=f"{tmp}/stats.pt")
    C.scrivi(False)
    uno = righe(f"{tmp}/memoria.db")
    C.scrivi(False)
    due = righe(f"{tmp}/memoria.db")
    ok(uno == due, "--scrivi lanciato due volte da' risultati diversi")
    ok(uno == nodi, "--scrivi sulla copia diverso da memoria.db vero")
    baks = sorted(p for p in os.listdir(tmp) if p.startswith("memoria.db.bak-pre-firme-se-"))
    ok(len(baks) >= 1, "nessun backup di memoria.db")
    if baks:
        ok(dump(f"{tmp}/{baks[-1]}") == prima, "il backup non riporta memoria.db com'era prima di --scrivi")

    print("6. --leggi interrotto e ripreso = stesse letture (server di prova)", flush=True)
    del os.environ["MEM_SAM"]
    L = modulo(LETTURE_SE=f"{tmp}/interrotta.pt")
    tutte, chat = L.voci()
    scelte = [x for x in tutte if x[0] == "nodo" and not L.contesto(chat, x[2])][:1]
    scelte += [x for x in tutte if x[0] == "nodo" and L.contesto(chat, x[2])][:3]
    scelte += [x for x in tutte if x[0] == "campione"][:2]
    L.voci = lambda: (scelte[:3], chat)
    L.leggi()
    L.voci = lambda: (scelte, chat)
    L.leggi()
    I = torch.load(f"{tmp}/interrotta.pt", weights_only=False)
    os.environ["LETTURE_SE"] = f"{tmp}/intera.pt"
    L.LETTURE = f"{tmp}/intera.pt"
    L.leggi()
    U = torch.load(f"{tmp}/intera.pt", weights_only=False)
    V = torch.load(R.LETTURE, weights_only=False)
    ok(I["mu_n"] == U["mu_n"] == len(scelte), f"mu_n {I['mu_n']}/{U['mu_n']}, attesi {len(scelte)}")
    ok(np.array_equal(I["mu_somma"], U["mu_somma"]), "mu della corsa ripresa diversa dalla corsa intera")
    for k in U["D"]:
        ok(np.array_equal(I["D"][k], U["D"][k]), f"{k}: ripresa diversa dalla corsa intera")
        ok(np.abs(U["D"][k] - V["D"][k]).max() < 1e-5, f"{k}: diversa dalla lettura di --leggi")
    for k in U["soli"]:
        ok(np.array_equal(I["soli"][k], U["soli"][k]) and np.array_equal(U["soli"][k], V["soli"][k]),
           f"{k}: messaggio senza contesto letto diverso")
finally:
    shutil.rmtree(tmp)

print("TUTTO VERDE" if not fallimenti else f"ROSSO: {len(fallimenti)} fallimenti")
sys.exit(1 if fallimenti else 0)
