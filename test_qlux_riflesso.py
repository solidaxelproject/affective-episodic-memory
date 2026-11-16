#!/usr/bin/env python3
"""test di +lux e qlux nel riflesso (PIANO-MEMORINVOLONTARIA-LUX.md, l'utente 09/11): senza GPU, senza il Lux vero (un
Lux finto su una porta libera), coda e diario in una cartella temporanea. Uso: python3 test_qlux_riflesso.py"""
import http.server
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

import riflesso as R
import riflesso_memoria as M
import riflesso_metadati as MD
import riflesso_fonte as FO
import riflesso_firma as FI
import riflesso_comune as C

TMP = R.Path(tempfile.mkdtemp())
diario = []
C._diario = diario.append
FI.CODA_FIRMA = str(TMP / "coda-firma.jsonl")
# D6 (l'utente 15/11, PIANO-ALUX-QLUX.md): lo stato dell'agente allegato a ogni alux, dall'omeostato su una copia
M.VE.omeostato.FILE, M.VE.omeostato.CONF = TMP / "stato-emotivo.json", TMP / "eutimia.json"
M.VE.omeostato.FILE.write_text(json.dumps({"ts": time.time(), "stato": {"joy": 0.5, "fear": -0.2}}))
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
    r = M._data(q, T0)
    assert r == atteso, (q, r, atteso)

# ---------- 2. codici e chiamate di memorinvolontaria nei messaggi ----------
finto = M._turni_tool({"codici": ["aaaaaaaaaaaaaaaa"], "risposta": "1°\naaaaaaaaaaaaaaaa\nun ricordo"})
msgs = [{"role": "user", "content": "[utente] ciao"}] + finto + [
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_7", "type": "function",
                                                        "function": {"name": "memorinvolontaria", "arguments": "{\"qlux\": \"mare\"}"}}]},
    {"role": "tool", "tool_call_id": "call_7", "content": "1°\nbbbbbbbbbbbbbbbb\n" + "il mare d'inverno, " * 30},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_8", "type": "function",
                                                        "function": {"name": "read_file", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_8", "content": "un file letto dall'agente, " * 30}]
assert FO._codici_nei_messaggi(msgs) == {"aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"}
# D5 (l'utente 15/11, PIANO-ALUX-QLUX.md): le consegne col nome §ricordo:, i ricordi di qlux riconosciuti
assert FO.NOME_CONSEGNA == "§ricordo:"
assert finto[0]["tool_calls"][0]["function"]["name"] == "§ricordo:" and finto[0]["tool_calls"][0]["id"] == "ricordo_aaaaaaaaaaaaaaaa"
assert finto[1]["tool_call_id"] == "ricordo_aaaaaaaaaaaaaaaa"
msgs_q = [{"role": "assistant", "content": "", "tool_calls": [{"id": "x1", "type": "function",
           "function": {"name": "qlux", "arguments": "{\"testo\": \"mare\"}"}}]},
          {"role": "tool", "tool_call_id": "x1", "content": "1°\nqqqqqqqqqqqqqqqq\nil mare"}] + finto
assert FO._codici_nei_messaggi(msgs_q) == {"qqqqqqqqqqqqqqqq", "aaaaaaaaaaaaaaaa"}
i, fonte = FO._fonte_indice(msgs)
assert i == len(msgs) - 1, "la lettura vera e' la fonte"
i, fonte = FO._fonte_indice(msgs[:-2])
assert i == 0, "il risultato di qlux non e' fonte della memoria involontaria"
d = {"messages": msgs[:-2]}
assert MD._code(json.dumps(d).encode(), ["coda"])[1] is False, "niente coda attaccata al risultato di qlux"

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
M.LUX = f"http://127.0.0.1:{lux.server_port}/consegna"
rif = http.server.ThreadingHTTPServer(("127.0.0.1", 0), R.Proxy)
threading.Thread(target=rif.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{rif.server_port}/memorinvolontaria"


def chiedi(args):
    req = urllib.request.Request(URL, json.dumps(args).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=10))["testo"]


M._esclusi_chat[0] = {"aaaaaaaaaaaaaaaa"}
assert chiedi({"qlux": "il mare il 9/11"}) == "1°\ncccccccccccccccc\ntrovato"
q = chiamate[-1]
assert q["quanti"] == 1 and q["soglia"] == 0 and q["testo"] == "il mare" and q["esclusi"] == ["aaaaaaaaaaaaaaaa"]
assert q["da"] == M._data("9/11", time.time())[1]
chiedi({"qlux": "il mare"})
assert set(chiamate[-1]["esclusi"]) == {"aaaaaaaaaaaaaaaa", "cccccccccccccccc"}, "la seconda volta escluso il primo"
assert "da" not in chiamate[-1]
assert chiedi({"qlux": "niente"}) == M.R_NESSUNO
assert chiedi({"qlux": "rompi"}) == M.R_GIU
assert chiedi({}) == M.R_GIU
assert chiedi({"+lux": "   "}) == M.R_VUOTO_ALUX == "Cosa vuoi ricordare? Scrivilo come vorrai ritrovarlo."
assert chiedi({"qlux": "  "}) == M.R_VUOTO_QLUX == "Cosa vuoi cercare? Scrivi poche parole o una data."
assert not os.path.exists(FI.CODA_FIRMA)
assert chiedi({"+lux": "  il giorno del mare  "}) == M.R_AGGIUNTO
riga, = [json.loads(r) for r in open(FI.CODA_FIRMA, encoding="utf-8")]
assert riga["testo"] == "il giorno del mare" and riga["forzato"] is True and riga["autore"] == "@agente:localhost"
assert abs(riga["stato"]["joy"] - 0.5) < 0.05 and abs(riga["stato"]["fear"] + 0.2) < 0.05, riga
assert chiedi({"+lux": "secondo", "qlux": "il mare"}) == M.R_AGGIUNTO + "\n\n1°\ncccccccccccccccc\ntrovato"
assert not hasattr(M, "R_SENZA") and not hasattr(M, "R_VUOTO")
os.remove(M.VE.omeostato.FILE)   # stato illeggibile: il ricordo si accoda lo stesso, senza "stato"
assert chiedi({"+lux": "terzo"}) == M.R_AGGIUNTO
assert "stato" not in [json.loads(r) for r in open(FI.CODA_FIRMA, encoding="utf-8")][-1]
# il plugin di Hermes contro questo riflesso: stessi testi, argomenti estranei tolti
import importlib.util  # noqa: E402
os.environ["MEMORINVOLONTARIA_URL"] = URL
spec = importlib.util.spec_from_file_location("plugin_mi", os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes-plugin/memorinvolontaria/__init__.py"))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
# alux e qlux (l'utente 15/11, PIANO-ALUX-QLUX.md D1-D4): due strumenti, testi approvati
assert P.alux({"testo": "  il giorno del mare  "}) == M.R_AGGIUNTO
assert P.alux({}) == M.R_VUOTO_ALUX and P.alux({"testo": "  "}) == M.R_VUOTO_ALUX
assert P.alux({"+lux": "vecchio stile"}) == M.R_AGGIUNTO   # imita le vecchie chiamate: il testo non si perde
assert P.qlux({"testo": "il mare", "altro": 1}) == "1°\ncccccccccccccccc\ntrovato"
assert P.qlux({}) == M.R_VUOTO_QLUX
assert P.R_GIU == M.R_GIU and not hasattr(P, "memorinvolontaria")
assert P.SCHEMA_ALUX["name"] == "alux" and P.SCHEMA_QLUX["name"] == "qlux"
assert P.SCHEMA_ALUX["description"] == "Aggiunge un ricordo alla tua memoria."
assert P.SCHEMA_QLUX["description"] == "Cerca un ricordo nella tua memoria."
assert P.SCHEMA_ALUX["parameters"]["properties"]["testo"]["description"] == (
    "Il ricordo da tenere, scritto come vorrai ritrovarlo. Entra subito nella tua memoria.")
assert P.SCHEMA_QLUX["parameters"]["properties"]["testo"]["description"] == (
    "Cosa cerchi: poche parole o una frase su quello che vuoi ricordare, una data, in cui potrebbe essere successo "
    "qualcosa. Ti torna il ricordo più vicino, uno solo per volta.")
assert P.SCHEMA_ALUX["parameters"]["required"] == [] == P.SCHEMA_QLUX["parameters"]["required"]
registrati = []
P.register(type("Ctx", (), {"register_tool": lambda self, **k: registrati.append(k["name"])})())
assert registrati == ["alux", "qlux", "correggicordo"], registrati
# Lux spento
lux.shutdown()
lux.server_close()
assert chiedi({"qlux": "il mare"}) == M.R_GIU
# solo dal PC e dalla rete docker
P.URL = "http://127.0.0.1:1/memorinvolontaria"
assert P.qlux({"testo": "x"}) == M.R_GIU   # riflesso giu'
assert M._ammesso("127.0.0.1") and M._ammesso("172.18.0.2") and not M._ammesso("192.168.1.20") and not M._ammesso("100.64.0.2")

# ---------- 4. stress: 200 +lux da 8 fili, righe intere e nessuna persa ----------
os.remove(FI.CODA_FIRMA)
fili = [threading.Thread(target=lambda k=k: [chiedi({"+lux": f"ricordo {k}-{j} " + "x" * 300}) for j in range(25)])
        for k in range(8)]
[f.start() for f in fili]
[f.join() for f in fili]
righe = [json.loads(r) for r in open(FI.CODA_FIRMA, encoding="utf-8")]
assert len(righe) == 200 and len({r["testo"] for r in righe}) == 200
rif.shutdown()
print("TUTTO VERDE")
