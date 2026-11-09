#!/usr/bin/env python3
"""test di +lux e qlux nel riflesso (PIANO-MEMORINVOLONTARIA-LUX.md, l'utente 09/11): senza GPU, senza il Lux vero (un
Lux finto su una porta libera), coda, consenso e diario in una cartella temporanea. Uso: python3 test_qlux_riflesso.py"""
import http.server
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

import riflesso as R

TMP = R.Path(tempfile.mkdtemp())
diario = []
R._diario = diario.append
R.CODA_FIRMA = str(TMP / "coda-firma.jsonl")
R.CONSENSO = TMP / "consenso.md"
R.CONSENSO.write_text("[attivo: *sì*]\n", encoding="utf-8")
T0 = time.mktime((2026, 11, 9, 15, 0, 0, 0, 0, -1))   # lunedi' 9/11/2026, 15:00 ora locale


def giorno(a, m, g):
    return time.mktime((a, m, g, 0, 0, 0, 0, 0, -1))


# ---------- 1. date nella ricerca ----------
casi = {
    "il 9/11 con l'utente": ("con l'utente", giorno(2026, 11, 9), giorno(2026, 11, 10)),
    "9/11/2025": ("", giorno(2025, 11, 9), giorno(2025, 11, 10)),
    "3 novembre la pioggia": ("la pioggia", giorno(2026, 11, 3), giorno(2026, 11, 4)),
    "31 dicembre": ("", giorno(2025, 12, 31), giorno(2026, 1, 1)),          # anno mancante: il piu' recente passato
    "il 14 luglio 2026 il vettore": ("il vettore", giorno(2026, 7, 14), giorno(2026, 7, 15)),
    "ottobre 2026": ("", giorno(2026, 10, 1), giorno(2026, 11, 1)),
    "a dicembre": ("", giorno(2025, 12, 1), giorno(2026, 1, 1)),
    "ieri sera": ("sera", giorno(2026, 11, 8), giorno(2026, 11, 9)),
    "l'altro ieri": ("", giorno(2026, 11, 7), giorno(2026, 11, 8)),
    "oggi": ("", giorno(2026, 11, 9), giorno(2026, 11, 10)),
    "la canzone dell'agente": ("la canzone dell'agente", None, None),
    "il 30/2": ("il 30/2", None, None),                                       # data impossibile: resta testo
    "29 febbraio": ("29 febbraio", None, None),                               # 2026 non bisestile
    "9/11/25": ("", giorno(2025, 11, 9), giorno(2025, 11, 10)),               # anno a due cifre
    "il 1° novembre": ("", giorno(2026, 11, 1), giorno(2026, 11, 2)),
    "il primo novembre": ("", giorno(2026, 11, 1), giorno(2026, 11, 2)),
    "oggi ripenso al 3 marzo": ("ripenso al 3 marzo", giorno(2026, 11, 9), giorno(2026, 11, 10)),   # la prima nel testo
    "appoggi e maggiore": ("appoggi e maggiore", None, None),
}
for q, atteso in casi.items():
    r = R._data(q, T0)
    assert r == atteso, (q, r, atteso)

# ---------- 2. codici e chiamate di memorinvolontaria nei messaggi ----------
finto = R._turni_tool({"codici": ["aaaaaaaaaaaaaaaa"], "risposta": "1°\naaaaaaaaaaaaaaaa\nun ricordo"})
msgs = [{"role": "user", "content": "[utente] ciao"}] + finto + [
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_7", "type": "function",
                                                        "function": {"name": "memorinvolontaria", "arguments": "{\"qlux\": \"mare\"}"}}]},
    {"role": "tool", "tool_call_id": "call_7", "content": "1°\nbbbbbbbbbbbbbbbb\n" + "il mare d'inverno, " * 30},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_8", "type": "function",
                                                        "function": {"name": "read_file", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_8", "content": "un file letto dall'agente, " * 30}]
assert R._codici_nei_messaggi(msgs) == {"aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"}
i, fonte = R._fonte_indice(msgs)
assert i == len(msgs) - 1, "la lettura vera e' la fonte"
i, fonte = R._fonte_indice(msgs[:-2])
assert i == 0, "il risultato di qlux non e' fonte della memoria involontaria"
d = {"messages": msgs[:-2]}
assert R._code(json.dumps(d).encode(), ["coda"])[1] is False, "niente coda attaccata al risultato di qlux"

# ---------- 3. la route, con un Lux finto ----------
chiamate = []


class LuxFinto(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        chiamate.append(d)
        if d["testo"] == "rompi":
            self.send_response(500)
            self.end_headers()
            return
        r = {} if d["testo"] == "niente" else {"codici": ["cccccccccccccccc"], "risposta": "1°\ncccccccccccccccc\ntrovato"}
        b = json.dumps(r).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


lux = http.server.ThreadingHTTPServer(("127.0.0.1", 0), LuxFinto)
threading.Thread(target=lux.serve_forever, daemon=True).start()
R.LUX = f"http://127.0.0.1:{lux.server_port}/consegna"
rif = http.server.ThreadingHTTPServer(("127.0.0.1", 0), R.Proxy)
threading.Thread(target=rif.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{rif.server_port}/memorinvolontaria"


def chiedi(args):
    req = urllib.request.Request(URL, json.dumps(args).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))["testo"]


R._esclusi_chat[0] = {"aaaaaaaaaaaaaaaa"}
assert chiedi({"qlux": "il mare il 9/11"}) == "1°\ncccccccccccccccc\ntrovato"
q = chiamate[-1]
assert q["quanti"] == 1 and q["soglia"] == 0 and q["testo"] == "il mare" and q["esclusi"] == ["aaaaaaaaaaaaaaaa"]
assert q["da"] == R._data("9/11", time.time())[1]
chiedi({"qlux": "il mare"})
assert set(chiamate[-1]["esclusi"]) == {"aaaaaaaaaaaaaaaa", "cccccccccccccccc"}, "la seconda volta escluso il primo"
assert "da" not in chiamate[-1]
assert chiedi({"qlux": "niente"}) == R.R_NESSUNO
assert chiedi({"qlux": "rompi"}) == R.R_GIU
assert chiedi({}) == R.R_SENZA
assert chiedi({"+lux": "   "}) == R.R_VUOTO
assert not os.path.exists(R.CODA_FIRMA)
assert chiedi({"+lux": "  il giorno del mare  "}) == R.R_AGGIUNTO
riga, = [json.loads(r) for r in open(R.CODA_FIRMA, encoding="utf-8")]
assert riga["testo"] == "il giorno del mare" and riga["forzato"] is True and riga["autore"] == "@agente:localhost"
assert chiedi({"+lux": "secondo", "qlux": "il mare"}) == R.R_AGGIUNTO + "\n\n1°\ncccccccccccccccc\ntrovato"
# consenso spento: niente entra, niente si scrive
R.CONSENSO.write_text("[attivo: *no*]\n", encoding="utf-8")
n = len(open(R.CODA_FIRMA).readlines())
assert chiedi({"+lux": "terzo"}) == R.R_GIU and chiedi({"qlux": "il mare"}) == R.R_GIU
assert len(open(R.CODA_FIRMA).readlines()) == n
R.CONSENSO.write_text("[attivo: *sì*]\n", encoding="utf-8")
# il plugin di Hermes contro questo riflesso: stessi testi, argomenti estranei tolti
import importlib.util  # noqa: E402
os.environ["MEMORINVOLONTARIA_URL"] = URL
spec = importlib.util.spec_from_file_location("plugin_mi", os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes-plugin/memorinvolontaria/__init__.py"))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
assert P.memorinvolontaria({"qlux": "il mare", "altro": 1}) == "1°\ncccccccccccccccc\ntrovato"
assert P.memorinvolontaria({}) == R.R_SENZA and P.R_GIU == R.R_GIU
assert P.SCHEMA["parameters"]["required"] == [] and set(P.SCHEMA["parameters"]["properties"]) == {"+lux", "qlux"}
# Lux spento
lux.shutdown()
lux.server_close()
assert chiedi({"qlux": "il mare"}) == R.R_GIU
# solo dal PC e dalla rete docker
P.URL = "http://127.0.0.1:1/memorinvolontaria"
assert P.memorinvolontaria({"qlux": "x"}) == R.R_GIU   # riflesso giu'
assert R._ammesso("127.0.0.1") and R._ammesso("172.18.0.2") and not R._ammesso("192.168.1.20") and not R._ammesso("100.64.0.2")

# ---------- 4. stress: 200 +lux da 8 fili, righe intere e nessuna persa ----------
os.remove(R.CODA_FIRMA)
fili = [threading.Thread(target=lambda k=k: [chiedi({"+lux": f"ricordo {k}-{j} " + "x" * 300}) for j in range(25)])
        for k in range(8)]
[f.start() for f in fili]
[f.join() for f in fili]
righe = [json.loads(r) for r in open(R.CODA_FIRMA, encoding="utf-8")]
assert len(righe) == 200 and len({r["testo"] for r in righe}) == 200
rif.shutdown()
print("TUTTO VERDE")
