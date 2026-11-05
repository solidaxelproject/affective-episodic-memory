#!/usr/bin/env python3
"""Stress-test di B5b (PIANO-FIRMA-ENGRAMMI.md): firma_server con "layers" (3 letture) contro la firma di B2 (34
letture), velocita', errori, e letture concorrenti a una generazione. Uso: venv/bin/python test_b5b.py [url]"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
import firma_se as F   # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8098"
fallimenti = []


def ok(cond, cosa):
    if not cond:
        fallimenti.append(cosa)
        print("  ROSSO:", cosa, flush=True)


# TOLLERANZA (01/11, misurata): la firma di B2 ricavava il messaggio da una media float32 x n_token (resto fino a 2.5e-4);
# la nuova usa somme in doppia precisione. Un valore "esatto" unico non esiste: lo stesso token letto in passaggi di
# lunghezza diversa esce un poco diverso (la GPU sceglie kernel diversi per numeri di token diversi, fino a 5e-3 sulla
# firma), quindi il riferimento e' lo STESSO metodo (contesto in un passaggio suo, contesto + messaggio in un altro).
TOLL = 5e-4


def uguali(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return float(np.abs(a - b).max()), float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


# 1. equivalenza coi 10 messaggi veri di B2 (firma vecchia salvata) e velocita'
voci = json.load(open("/data/memoria-episodica-affettiva/engrammi/fedelta-server.json"))
tempi = []
for v in voci:
    t0 = time.time()
    f = F.firma_server(v["contesto"], v["messaggio"], URL)
    tempi.append(time.time() - t0)
    d, c = uguali(f, v["firma"])
    ok(d < TOLL and c > 0.99999, f"messaggio {v['i']}: scarto {d:.2e}, coseno {c:.6f} dalla firma di B2")
print(f"10 messaggi veri: {np.mean(tempi):.2f} s a firma (max {max(tempi):.2f})", flush=True)
ok(np.mean(tempi) <= 5, f"tempo medio {np.mean(tempi):.1f} s > 5 s")

# 2. testi strani: nuova = vecchia (la vecchia rifatta qui, 34 letture)
ctx = voci[0]["contesto"]
for nome, t in {"emoji": "🌅🌅 grazie mille 😂😂😂 sei fantastica ❤️", "un token": "ok",
                "apostrofi": "Dell'altro giorno l'un l'altra po' perche' c'e' un'idea",
                "lungo": "Questa e' una frase molto lunga che si ripete. " * 120,
                "a capo": "\n\nprima riga\n\n\n   seconda riga   \n"}.items():
    d, c = uguali(F.firma_server(ctx, t, URL), F._firma_per_strato(ctx, t, URL))
    ok(d < TOLL and c > 0.99999, f"testo strano {nome}: scarto {d:.2e}, coseno {c:.6f}")
f1 = F.firma_server("Contesto lunghissimo, parola dopo parola. " * 300, "e adesso il messaggio", URL)
f2 = F._firma_per_strato("Contesto lunghissimo, parola dopo parola. " * 300, "e adesso il messaggio", URL)
ok(uguali(f1, f2)[0] < TOLL, "contesto lunghissimo: nuova diversa dalla vecchia")
mu = {l: np.zeros(2048) for l in F.STRATI}
ok(uguali(F.firma_server("", "buongiorno a tutti", URL, mu=mu), F._firma_per_strato("", "buongiorno a tutti", URL, mu=mu))[0]
   < TOLL, "contesto vuoto: nuova diversa dalla vecchia")

# 3. deterministica
v = voci[3]
ok(np.array_equal(F.firma_server(v["contesto"], v["messaggio"], URL), F.firma_server(v["contesto"], v["messaggio"], URL)),
   "firma non deterministica")

# 4. errori: strato fuori range dal server; server senza "layers" -> errore chiaro
for cattivo in ([40], [-1], [15, 99]):
    try:
        F._post(URL, "/lux-read", {"content": "ciao", "layer": 15, "layers": cattivo})
        ok(False, f"layers {cattivo} accettato")
    except urllib.error.HTTPError:
        pass


class Vecchio(BaseHTTPRequestHandler):   # un luxifer senza "layers": risponde solo "mean"
    def log_message(self, *a):
        pass

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/lux-read":
            b.pop("layers", None)
            b.pop("somme", None)
        r = urllib.request.urlopen(urllib.request.Request(URL + self.path, json.dumps(b).encode(),
                                                          {"Content-Type": "application/json"})).read()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(r)


srv = ThreadingHTTPServer(("127.0.0.1", 18198), Vecchio)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    F.firma_server(ctx, "ciao a tutti", "http://127.0.0.1:18198")
    ok(False, "server senza layers: nessun errore")
except RuntimeError:
    pass
srv.shutdown()

# 5. letture concorrenti durante una generazione: la generazione resta identica byte per byte
gen = {"prompt": "<|im_start|>user\nRaccontami in tre frasi come si prepara il pane.<|im_end|>\n<|im_start|>assistant\n",
       "n_predict": 96, "temperature": 0, "cache_prompt": False}
base = F._post(URL, "/completion", gen, timeout=600)["content"]
errori = []


def firma_a_caso(k):
    try:
        w = voci[k % 10]
        return F.firma_server(w["contesto"], w["messaggio"], URL)
    except Exception as e:
        errori.append(repr(e))


with ThreadPoolExecutor(8) as pool:
    lavori = [pool.submit(firma_a_caso, k) for k in range(20)]
    sotto = F._post(URL, "/completion", gen, timeout=600)["content"]
    firme = [x.result() for x in lavori]
ok(sotto == base, "generazione cambiata dalle letture concorrenti")
ok(not errori, f"letture concorrenti: {len(errori)} errori {errori[:2]}")
scarti = [float(np.abs(firme[k] - firme[k % 10]).max()) for k in range(10, 20)
          if firme[k] is not None and firme[k % 10] is not None]
ok(len(scarti) == 10 and max(scarti) == 0.0, f"letture concorrenti: stesso messaggio, scarti {scarti}")

print("TUTTO VERDE" if not fallimenti else f"ROSSO: {len(fallimenti)} fallimenti")
sys.exit(1 if fallimenti else 0)
