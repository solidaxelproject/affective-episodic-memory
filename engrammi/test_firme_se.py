#!/usr/bin/env python3
"""Stress-test di B3 (PIANO-FIRMA-ENGRAMMI.md): rifirma di tutti i ricordi coi vettori se'.
  09/11 (PIANO-FIRMA-44-ASSI.md): assi dai vettori scritti nelle statistiche (44, variante C), emo_tag =
  memoria.dominante, letture = differenze per strato (letture-diff.pt); numero dei nodi e delle voci dal meta del Lux
  (1.20.0, prima memoria.db; LUX_DIR = una copia migrata, altrimenti la versione in servizio; addr_emo e vettori.pt via).
  dopo --scrivi:  tutti i nodi con firma sugli assi delle statistiche, dominante nei vettori del riflesso, salienza = max z,
                  statistiche coi metadati, quota della soglia nuova = quota vecchia (+-1 punto)
  stress:         --scrivi due volte su una copia = stesso risultato; il backup riporta il meta identico;
                  --leggi interrotto e ripreso = stesse letture di una corsa intera (server di prova acceso);
                  nodi senza contesto e nodi "letto" firmati come gli altri.
Uso: cd /data/jspace && venv/bin/python /data/memoria-episodica-affettiva/engrammi/test_firme_se.py"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
import firma_se as F  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firme-occamy", "ricalcola-firme-se.py")
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


def righe(meta):
    """1.20.0: (nid, firma, dominante, salienza) dei ricordi del meta, correzioni fuori"""
    r = json.load(open(meta))["ricordi"]
    return sorted((int(k), x["firma"], x["dominante"], x["salienza"]) for k, x in r.items() if x["classe"] != "correzione")


R = modulo()
stats = torch.load(R.STATS, weights_only=False)
F.usa(stats.get("vettori", F.VETTORI))
assi, _ = F.vettori()
voci_tutte = R.voci()[0]
n_nodi = sum(1 for x in voci_tutte if x[0] == "nodo")

print("1. meta del Lux dopo la scrittura", flush=True)
nodi = righe(R.META)
classi = {int(k): x["classe"] for k, x in json.load(open(R.META))["ricordi"].items()}
ok(len(nodi) == n_nodi, f"nodi {len(nodi)}, attesi {n_nodi}")
cvec = [str(x) for x in np.load("/data/memoria-episodica-affettiva/emo-cvec-v2.npz")["nomi"]]
for nid, f, tag, sal in nodi:
    ok(list(f) == assi, f"nodo {nid}: assi della firma {list(f)[:3]}...")
    ok(all(np.isfinite(x) for x in f.values()), f"nodo {nid}: firma non finita")
    ok(tag == R.memoria.dominante(f), f"nodo {nid}: emo_tag {tag} non e' la dominante (memoria.dominante)")
    ok(tag in cvec, f"nodo {nid}: emo_tag {tag} assente dai vettori del riflesso")
    ok(abs(sal - max(f.values())) < 1e-3, f"nodo {nid}: salienza {sal} != max z {max(f.values())}")
ok(any(classi[n] == "letto" for n, *_ in nodi), "nessun nodo 'letto' controllato")

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
    ok(firma == nuove[nid][0], f"nodo {nid}: firma nel meta diversa dal ricalcolo")

print("4. nodi senza contesto firmati", flush=True)
v, chat = R.voci()
soli = [x for x in v if x[0] == "nodo" and not R.contesto(chat, x[2])]
ok(len(soli) >= 1, "nessun nodo senza contesto da controllare")
for _, nid, _, _ in soli:
    ok(nid in nuove and len(nuove[nid][0]) == len(assi), f"nodo senza contesto {nid} non firmato")

print("5. --scrivi due volte su una copia = stesso risultato; il backup riporta il meta identico", flush=True)
tmp = tempfile.mkdtemp(prefix="test-b3-", dir="/data/memoria-episodica-affettiva/firme-occamy")
try:
    shutil.copy2(R.META, f"{tmp}/lux-meta.json")
    prima = open(f"{tmp}/lux-meta.json", "rb").read()
    C = modulo(LUX_DIR=tmp, STATS_SE=f"{tmp}/stats.pt")
    C.scrivi(False)
    uno = righe(f"{tmp}/lux-meta.json")
    C.scrivi(False)
    due = righe(f"{tmp}/lux-meta.json")
    ok(uno == due, "--scrivi lanciato due volte da' risultati diversi")
    ok(uno == nodi, "--scrivi sulla copia diverso dal meta vero")
    baks = sorted(p for p in os.listdir(tmp) if p.startswith("lux-meta.json.bak-pre-firme-se-"))
    ok(len(baks) >= 1, "nessun backup del meta")
    if baks:
        ok(open(f"{tmp}/{baks[0]}", "rb").read() == prima, "il backup non riporta il meta com'era prima di --scrivi")

    print("6. --leggi interrotto e ripreso = stesse letture (server di prova)", flush=True)
    del os.environ["LUX_DIR"]
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
