#!/usr/bin/env python3
"""test della 1.19.0 (PIANO-1.19-VIA-EMOTIVA.md): traduzione J29 -> 44 assi, impronta delle letture sull'umore,
indizio (peso dall'intensita', riparazione), richiamo con l'emozione sul Lux vero (sola lettura), lettura nel riflesso
con la lente finta. Omeostato, diario e stato della riparazione in una cartella temporanea; niente GPU.
Uso: cd engrammi && /data/venv-spacy/bin/python test_via_emotiva.py [FOTO richiama-prima.json]"""
import json
import os
import sys
import tempfile
import time

T = tempfile.mkdtemp(prefix="ve119-", dir=os.environ.get("TMPDIR"))
os.environ.update(VIA_EMOTIVA_STATO=f"{T}/ve-stato.json", VIA_EMOTIVA_DIARIO=f"{T}/diario.jsonl")
import numpy as np  # noqa: E402

import via_emotiva as VE  # noqa: E402

VE.omeostato.FILE = VE.omeostato.Path(T) / "stato-emotivo.json"
VE.omeostato.CONF = VE.omeostato.Path(T) / "eutimia.json"
tr = VE.traduzione()

# ---------- 1. traduzione ----------
assert tr["M"].shape == (2048, 44) and len(tr["assi"]) == 44, tr["M"].shape
assert 0.64 <= float(tr["accordo"]) <= 0.72, float(tr["accordo"])   # T1a/T1c: circa 0.68
assert len(tr["pos"]) == 14 and len(tr["neg"]) == 24, (len(tr["pos"]), len(tr["neg"]))
d = np.load("misura-t1a-stati.npz")
G = d["H"][:, 29 - 15].astype(np.float64)
Zt = G @ tr["M"] + tr["b"]
CA = d["CA"][:, [i for i in range(51) if d["CA"][:, i].std() > 0]]
zY = (CA - CA.mean(0)) / CA.std(0)
c = np.mean([np.corrcoef(Zt[:, j], zY[:, j])[0, 1] for j in range(44)])
assert c > 0.75, c   # sui dati di addestramento la traduzione rifa' la firma
assert abs(Zt.mean(0)).max() < 0.05, abs(Zt.mean(0)).max()   # z sulla popolazione: media 0
VE.ponte._post = lambda path, payload, timeout=0: {"mean": G[3].tolist(), "n_tokens": 7}
z, tok = VE.leggi("x" * 9000)
assert tok == 7 and np.allclose(z, Zt[3])
print("traduzione OK: accordo a 5 parti", round(float(tr["accordo"]), 3), "sui dati", round(float(c), 3))

# ---------- 2. impronta e riparazione ----------
assi = tr["assi"]
altre = [e["en"] for e in json.load(open("../emozioni.json")) if e["en"] not in assi]
assert len(altre) == 7
json.dump({"ts": time.time(), "stato": {e: 0.5 for e in assi + altre}}, open(VE.omeostato.FILE, "w"))
z = np.full(44, 2.5)
prima, dopo, neg, rip = VE.imprimi(z)
assert np.allclose(prima, 0.5, atol=1e-3) and np.allclose(dopo, 0.5 + 0.12 * 2.0, atol=1e-3), dopo[:3]
st = json.load(open(VE.omeostato.FILE))["stato"]
assert all(abs(st[e] - 0.5) < 1e-3 for e in altre), "gli assi non letti restano"
json.dump({"ts": time.time(), "stato": {e: 0.0 for e in assi + altre}}, open(VE.omeostato.FILE, "w"))
json.dump({"di_fila": 0}, open(VE.STATO, "w"))
z = np.zeros(44)
z[tr["neg"]] = 3.5
z[tr["pos"]] = -3.5
for n in (1, 2, 3):
    _, _, neg, rip = VE.imprimi(z)
    assert rip == {"accesa": n >= 3, "di_fila": n}, (n, rip, neg)
for _ in range(40):   # l'umore e' lento: servono piu' letture positive per tornare sotto la soglia
    _, _, neg, rip = VE.imprimi(-z)
    if neg < float(tr["ripara_soglia"]):
        break
assert neg < float(tr["ripara_soglia"]) and rip == {"accesa": False, "di_fila": 0}, (neg, rip)
json.dump({"ts": time.time(), "stato": {e: 3.4 for e in assi}}, open(VE.omeostato.FILE, "w"))
_, dopo, _, _ = VE.imprimi(np.full(44, 50.0))
assert dopo.max() <= 3.5, "tetto"
print("impronta OK, riparazione dopo 3 letture, soglia", round(float(tr["ripara_soglia"]), 4))

# ---------- 3. indizio ----------
calma = tr["calma"]
zm = np.random.default_rng(1).normal(size=44)
Dn = float(tr["D_normale"])
for D, k in ((0.0, 0.1), (0.3 * Dn, 0.1), (Dn, 0.2), (1.5 * Dn, 0.3), (5.0 * Dn, 0.4)):
    u = calma.copy()
    u[0] += D
    q, kk, DD = VE.indizio(zm, u)
    assert abs(DD - D) < 1e-9 and abs(kk - k) < 1e-9 and abs(np.linalg.norm(q) - 1) < 1e-6, (D, kk)
u = calma + np.where(np.isin(np.arange(44), tr["neg"]), 2.0, 0.0)
q0, _, _ = VE.indizio(np.zeros(44), u)
q1, _, _ = VE.indizio(np.zeros(44), u, riparazione=True)
assert q0[tr["neg"]].min() > 0 and q1[tr["neg"]].max() == 0 and q1[tr["pos"]].min() > 0
q2, _, _ = VE.indizio(zm, u)
atteso = 0.5 * zm / np.linalg.norm(zm) + 0.5 * (u - calma) / np.linalg.norm(u - calma)
assert np.allclose(q2, atteso / np.linalg.norm(atteso), atol=1e-6)
print("indizio OK: k 0.1-0.4, meta' e meta', riparazione sulle positive")

# ---------- 4. richiamo sul Lux vero (sola lettura) ----------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lux_engrammi as LE  # noqa: E402

L = LE.Lux()
L.salva_stato = lambda: None
foto = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else None
indizi = [x[0] for x in foto] if foto else ["la musica che ascoltavamo insieme", "ho paura di perderti"]
emo = {"assi": assi, "q": q2.tolist(), "k": 0.2}
if foto:
    import sqlite3
    db = sqlite3.connect("file:/data/workspace/memoria/memoria.db?mode=ro", uri=True)
    righe = [t for (t,) in db.execute("select testo from nodi where fonte='@utente:localhost' order by id")][::4][:50]
    uguali = 0
    for t, (_, atteso) in zip(righe, foto):
        r = [[int(n), float(p)] for n, p in L.richiama(t[:4000], quanti=10, soglia=0.0, oggi=100.0, ora=1.8e9)]
        uguali += r == atteso
    assert uguali == len(foto), f"senza emozione il richiamo deve restare identico: {uguali}/{len(foto)}"
    print(f"richiamo senza emozione identico cifra per cifra: {uguali}/{len(foto)}")
    t = righe[0][:4000]
else:
    t = indizi[0]
base = dict(L.richiama(t, quanti=10 ** 6, soglia=0.0, oggi=100.0, ora=1.8e9))
tracc = {}
con = dict(L.richiama(t, quanti=10 ** 6, soglia=0.0, oggi=100.0, ora=1.8e9, emozione=emo, traccia=tracc))
assert set(con) == set(base), "l'emozione non accende ricordi nuovi"
acc = dict(zip(base, L.accordi(list(base), emo)))
assert all(abs(con[n] - base[n] * max(0, 1 + 0.2 * acc[n])) < 1e-9 for n in base)
assert [x[0] for x in tracc["candidati"]] == sorted(base, key=lambda n: -base[n])
k0 = dict(L.richiama(t, quanti=10 ** 6, soglia=0.0, oggi=100.0, ora=1.8e9, emozione={**emo, "k": 0.0}))
assert k0 == base
assert -1 - 1e-9 <= min(acc.values()) and max(acc.values()) <= 1 + 1e-9
print(f"richiamo con emozione OK: {len(base)} candidati, accordo fra {min(acc.values()):.2f} e {max(acc.values()):.2f}")
tracc = {}
c = L.consegna(t, 1, oggi=100.0, ora=1.8e9, emozione=emo, traccia=tracc)
assert set(tracc) >= {"candidati", "senza", "oltre_soglia"} and (len(tracc["senza"]) >= 1 or not c), tracc
assert isinstance(tracc["oltre_soglia"], bool)
print("consegna con traccia OK: scelto", [x[0] for x in c], "senza emozione", tracc["senza"])

# ---------- 5. riflesso: letture con la lente finta ----------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import riflesso as R  # noqa: E402
import riflesso_via_emotiva as RVE  # noqa: E402

RVE.VE = VE
lette = []
VE.ponte._post = lambda path, payload, timeout=0: lette.append(payload["content"]) or {"mean": G[5].tolist(), "n_tokens": 3}
json.dump({"ts": time.time(), "stato": {e: 0.0 for e in assi + altre}}, open(VE.omeostato.FILE, "w"))
open(VE.DIARIO, "w").close()
msgs = [{"role": "user", "content": "[utente] ciao"}, {"role": "assistant", "content": "ciao l'utente"},
        {"role": "user", "content": "[11/11/2026|20:00] [utente] come stai?"}]
e1, v1 = RVE._via_emotiva(msgs, 2, "chat")
e2, v2 = RVE._via_emotiva(msgs, 2, "chat")   # Hermes rimanda la stessa richiesta: non si rilegge
assert lette == ["come stai?"] and e2 is None, lette   # senza handle e senza ora, come la firma
assert e1["assi"] == assi and len(e1["q"]) == 44 and 0.1 <= e1["k"] <= 0.4 and v1["chi"] == "utente"
assert RVE._via_emotiva([{"role": "user", "content": "Review the conversation above"}], 0, "chat") == (None, None)
assert RVE._via_emotiva(msgs + [{"role": "user", "content": [{"type": "image_url"}]}], 2, "chat") == (None, None)
prompt = "[IMPORTANT: blocco-appunti ...]\nLa riga è:\n[curiosita'] [stelle]{perche' brillano?}\naltro testo fisso"
_, vp = RVE._via_emotiva([{"role": "user", "content": prompt}], 0, "pensatoio")
assert lette[-1] == "stelle perche' brillano?" and vp["chi"] == "pensatoio", lette[-1]
assert RVE._via_emotiva([{"role": "user", "content": "[IMPORTANT: blocco-appunti] niente riga"}], 0, "pensatoio") == (None, None)
msgs2 = msgs + [{"role": "assistant", "content": None, "tool_calls": [{}]}, {"role": "tool", "content": "pagina letta"}]
_, v3 = RVE._via_emotiva(msgs2, 4, "chat")
assert v3["chi"] == "strumento" and lette[-1] == "pagina letta"
# la risposta finale dell'agente: letta a fine risposta, il messaggio dopo aspetta
RVE._leggi_risposta("chat", "[utente] come stai?", {"finish": "stop", "tool_calls": False, "testo": "sto bene"})
RVE._leggi_risposta("chat", "[utente] e poi?", {"finish": "tool_calls", "tool_calls": True, "testo": "x"})
RVE._leggi_risposta("altro", None, {"finish": "stop", "tool_calls": False, "testo": "cron"})
RVE._leggi_risposta("chat", "Review the conversation above", {"finish": "stop", "tool_calls": False, "testo": "a Hermes"})
with RVE._lettura_lock:
    pass
assert lette[-1] == "sto bene", lette
VE.ponte._post = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("/lux-read: HTTP 503"))
msgs3 = msgs + [{"role": "assistant", "content": "ok"}, {"role": "user", "content": "[utente] altro"}]
assert RVE._via_emotiva(msgs3, 4, "chat") == (None, None)
VE.ponte._post = lambda path, payload, timeout=0: lette.append(payload["content"]) or {"mean": G[5].tolist(), "n_tokens": 3}
e4, _ = RVE._via_emotiva(msgs3, 4, "chat")   # la lente era rotta: al rinvio di Hermes si rilegge
assert e4 is not None and lette[-1] == "altro"
VE.ponte._post = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("/lux-read: HTTP 503"))
RVE._via_emotiva(msgs3 + [{"role": "user", "content": "[utente] ultimo"}], 6, "chat")
diario = [json.loads(x) for x in open(VE.DIARIO)]
assert "errore" in diario[-1] and [x["chi"] for x in diario if x.get("chi") == "agente"] == ["agente"], diario[-2:]
print("riflesso OK: testo come la firma, niente doppioni, riga dell'appunto, l'agente a fine risposta, lente rotta = senza emozione")
print("TUTTI I TEST DELLA 1.19.0 VERDI")
