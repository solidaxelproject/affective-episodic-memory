#!/usr/bin/env python3
"""Stress-test di B2 (PIANO-FIRMA-ENGRAMMI.md): firma_se.firma_server contro un server luxifer con /lux-read.
Uso: /data/jspace/venv/bin/python test_firma_se.py [url, default http://127.0.0.1:8098]
Salva le firme dei 10 messaggi della fedelta' in fedelta-server.json (il confronto con HF lo fa test_fedelta_hf.py)."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import firma_se as F   # noqa: E402
import tagging35b as T  # noqa: E402  (pulisci, contesto_di: la stessa preparazione del tagging)

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8098"
QUI = "/data/memoria-episodica-affettiva/engrammi"
assi, M = F.vettori()
fallimenti = []


def ok(cond, cosa):
    if not cond:
        fallimenti.append(cosa)
        print("  ROSSO:", cosa, flush=True)


def finita(f):
    return f is not None and f.shape == (24,) and np.isfinite(f).all() and np.abs(f).max() <= 1.0 + 1e-9


# 1. proietta su stati finti
for k, a in enumerate(assi):
    f = F.proietta({l: M[l][k] * 7.0 for l in F.STRATI})
    ok(abs(f[k] - 1) < 1e-6, f"proietta: asse {a} su se stesso = {f[k]}")
    att = np.mean([M[l] @ M[l][k] for l in F.STRATI], 0)
    ok(np.allclose(f, att, atol=1e-6), f"proietta: coseni degli altri assi per {a}")
for cattivo in (0.0, np.nan):
    try:
        F.proietta({l: np.full(2048, cattivo) for l in F.STRATI})
        ok(False, f"proietta accetta una differenza {cattivo}")
    except ValueError:
        pass

# 2. messaggi veri della chat (20), col loro contesto come nel tagging
chat = [json.loads(r) for r in open("/data/memoria-episodica-affettiva/firme-occamy/chat-completa.jsonl")]
chat = [dict(m, testo=T.pulisci(m["testo"])) for m in chat]
chat = [m for m in chat if m["testo"] and len(m["testo"]) >= 15]
rng = np.random.default_rng(1)
scelti = sorted(rng.choice(np.arange(5, len(chat)), 20, replace=False).tolist())
veri, tempi = [], []
for i in scelti:
    ctx = T.contesto_di([m["testo"] for m in chat[max(0, i - 8):i]])
    t0 = time.time()
    try:
        f = F.firma_server(ctx, chat[i]["testo"], URL)
    except Exception as e:
        f = None
        ok(False, f"messaggio vero {i}: {type(e).__name__} {e}")
    tempi.append(time.time() - t0)
    ok(finita(f), f"messaggio vero {i}: firma non finita")
    veri.append((i, ctx, f))
print(f"20 messaggi veri: {np.mean(tempi):.1f} s a firma (max {max(tempi):.1f})", flush=True)

# 3. testi strani (col contesto di un messaggio vero)
ctx0 = veri[0][1]
STRANI = {"emoji": "🌅🌅 grazie mille 😂😂😂 sei fantastica ❤️",
          "apostrofi": "Dell'altro giorno l'un l'altra po' perche' c'e' un'idea: com'e' andata all'universita'?",
          "codice": "def f(x):\n    return {k: v for k, v in x.items() if v}  # ```python```",
          "url": "guarda https://github.com/solidaxelproject/affective-episodic-memory/blob/main/README.md?x=1#a",
          "inglese": "I honestly can't believe it worked on the first try, this is wonderful news.",
          "a capo": "\n\nprima riga\n\n\n   seconda riga   \n",
          "punteggiatura": "...!?!?... (((boh)))",
          "un token": "ok",
          "lungo": "Questa e' una frase molto lunga che si ripete. " * 120}
for nome, testo in STRANI.items():
    try:
        f = F.firma_server(ctx0, testo, URL)
        ok(finita(f), f"testo strano {nome}: firma non finita")
    except Exception as e:
        ok(False, f"testo strano {nome}: {type(e).__name__} {e}")
for nome, c in {"emoji in testa": "🔐 l'agente vuole eseguire un comando", "solo emoji": "🔐🔐"}.items():
    try:   # 01/11 (B3): carattere in piu' token all'inizio del contesto
        f = F.firma_server(c, "e adesso il messaggio vero", URL, mu={l: np.zeros(2048) for l in F.STRATI})
        ok(finita(f), f"contesto {nome}: firma non finita")
    except Exception as e:
        ok(False, f"contesto {nome}: {type(e).__name__} {e}")
ok(np.array_equal(F.firma_server("🔐 " + ctx0, "ciao", URL), F.firma_server(ctx0, "ciao", URL)),
   "emoji tolta dall'inizio: firma diversa dal contesto senza emoji")
try:   # contesto oltre i 512 token del per_token: va tagliato
    f = F.firma_server("Contesto lunghissimo, parola dopo parola. " * 300, "e adesso il messaggio vero", URL)
    ok(finita(f), "contesto lunghissimo: firma non finita")
except Exception as e:
    ok(False, f"contesto lunghissimo: {type(e).__name__} {e}")

# 4. contesto vuoto: senza mu errore chiaro, con mu una firma
try:
    F.firma_server("", "buongiorno", URL)
    ok(False, "contesto vuoto senza mu accettato")
except ValueError:
    pass
mu = {l: np.zeros(2048) for l in F.STRATI}
ok(finita(F.firma_server("", "buongiorno a tutti", URL, mu=mu)), "contesto vuoto con mu: firma non finita")

# 5. deterministico: tre volte la stessa firma; 100 letture dello stesso strato uguali
i, ctx, f0 = veri[1]
for _ in range(2):
    ok(np.array_equal(F.firma_server(ctx, chat[i]["testo"], URL), f0), "firma non deterministica")
m0 = F._post(URL, "/lux-read", {"content": chat[i]["testo"], "layer": 24})["mean"]
diverse = sum(F._post(URL, "/lux-read", {"content": chat[i]["testo"], "layer": 24})["mean"] != m0 for _ in range(100))
ok(diverse == 0, f"100 letture dello strato 24: {diverse} diverse")

# 6. server giu', e server che muore a meta': errore, mai una firma a meta'
try:
    F.firma_server(ctx, "ciao", "http://127.0.0.1:1")
    ok(False, "server giu': nessun errore")
except (urllib.error.URLError, ConnectionError, OSError):
    pass
contatore = {"n": 0}


class Morente(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers["Content-Length"]))
        contatore["n"] += 1
        if contatore["n"] > 12:   # muore dopo 12 richieste (a meta' degli strati)
            self.send_response(500); self.end_headers(); return
        r = urllib.request.urlopen(urllib.request.Request(URL + self.path, corpo, {"Content-Type": "application/json"}))
        dati = r.read()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(dati)


srv = ThreadingHTTPServer(("127.0.0.1", 18197), Morente)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    F.firma_server(ctx, "ciao a tutti", "http://127.0.0.1:18197")
    ok(False, "server morto a meta': nessun errore")
except urllib.error.HTTPError:
    pass
srv.shutdown()

# 7. il senso: sulle scene appaiate, la versione emotiva accende il suo asse piu' della neutra (dentro lo stesso
#    contesto vero). Sono scene da cui vengono i vettori: controlla segni, strati e assi, non la generalizzazione.
EN = {"gioia": "joy", "tristezza": "sadness", "rabbia": "anger", "paura": "fear", "fiducia": "trust",
      "disgusto": "disgust", "sorpresa": "surprise", "serenità": "serenity"}
scene = [json.loads(r) for g in range(1, 7)
         for r in open(f"/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering/scene/gruppo-{g}.jsonl")]
scene = [scene[k] for k in rng.choice(len(scene), 6, replace=False)]
vinte, prime = 0, 0
for emo, en in EN.items():
    k = assi.index(en)
    for sc in scene:
        fn = F.firma_server(ctx0, sc["versioni"]["neutra"], URL)
        fe = F.firma_server(ctx0, sc["versioni"][emo], URL)
        vinte += fe[k] > fn[k]
        prime += int(np.argmax(fe - fn) == k)
print(f"scene: asse giusto piu' alto nella versione emotiva {vinte}/48, asse giusto il primo per salita {prime}/48",
      flush=True)
ok(vinte >= 44, f"scene: asse giusto piu' alto solo {vinte}/48")
ok(prime >= 24, f"scene: asse giusto primo solo {prime}/48 (a caso 2/48)")

# 8. i 10 messaggi della fedelta' (per test_fedelta_hf.py)
json.dump([{"i": i, "contesto": c, "messaggio": chat[i]["testo"], "firma": f.tolist()} for i, c, f in veri[:10]],
          open(f"{QUI}/fedelta-server.json", "w"), ensure_ascii=False)

print("TUTTO VERDE" if not fallimenti else f"ROSSO: {len(fallimenti)} fallimenti")
sys.exit(1 if fallimenti else 0)
