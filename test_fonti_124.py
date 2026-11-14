#!/usr/bin/env python3
"""test delle fonti nel riflesso (engrammi/PIANO-1.24-FONTI.md, l'utente 13/11): siti delle pagine lette, siti del turno,
registro delle letture e correggicordo con un Lux finto. Senza GPU e senza il Lux vero. Uso: python3 test_fonti_124.py"""
import http.server
import json
import tempfile
import threading
import time
from pathlib import Path

import riflesso as R  # noqa: F401  (aggiunge i percorsi di via_emotiva e steering)
import riflesso_fonte as FO
import riflesso_firma as FI
import riflesso_memoria as M
import riflesso_stato as S
import riflesso_comune as C

TMP = Path(tempfile.mkdtemp())
diario = []
C._diario = diario.append
FI.CODA_FIRMA = str(TMP / "coda-firma.jsonl")
C.CONSENSO = TMP / "consenso.md"
C.CONSENSO.write_text("[attivo: *sì*]\n", encoding="utf-8")

PROSA = "parola " * 100   # 700 caratteri: una lettura


def chiamata(i, comando):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": i, "type": "function", "function": {"name": "terminal", "arguments": json.dumps({"command": comando})}}]}


def risultato(i, testo):
    return {"role": "tool", "tool_call_id": i, "content": json.dumps({"output": testo})}


# 1. letture e dominio (D1, D8)
msgs = [{"role": "user", "content": "[utente] ciao"},
        chiamata("a", 'web_extract "https://www.Example.org/pagina?x=1"'), risultato("a", PROSA),
        chiamata("b", "web_extract https://it.wikipedia.org/wiki/Roma"), risultato("b", "breve"),
        chiamata("c", 'web_search "notizie oggi"'), risultato("c", PROSA),
        chiamata("d", "web_extract https://[::1/rotto"), risultato("d", PROSA)]
assert FO.letture(msgs) == [("a", "example.org")], FO.letture(msgs)
assert FO.dominio("https://www.Example.org/x") == "example.org"
assert FO.dominio("https://[::1/rotto") == ""
print("1 letture e dominio: ok")

# 2. siti del turno: solo dopo l'ultimo user, senza doppioni
msgs2 = [{"role": "user", "content": "[utente] primo"},
         chiamata("p", "web_extract https://vecchio.it/a"), risultato("p", PROSA),
         {"role": "assistant", "content": "risposta"},
         {"role": "user", "content": "[utente] secondo"},
         chiamata("q", "web_extract https://uno.it/a"), risultato("q", PROSA),
         chiamata("r", "web_extract https://www.uno.it/b"), risultato("r", PROSA),
         chiamata("s", "web_extract https://due.org/c"), risultato("s", PROSA)]
assert FO.siti_del_turno(msgs2) == ["uno.it", "due.org"], FO.siti_del_turno(msgs2)
assert FO.siti_del_turno([{"role": "user", "content": "[utente] x"}]) == []
print("2 siti del turno: ok")

# 3. la riga dell'agente nella coda di firma porta i siti; +lux pure
FI._accoda_firma("chat", "[utente] dimmi", 1.0, {"finish": "stop", "testo": "ecco la risposta"}, ["uno.it"])
FI._accoda_firma("chat", "[utente] ancora", 2.0, {"finish": "stop", "testo": "senza pagine"})
FI._accoda_forzato("ricordo voluto", ["due.org"])
righe = [json.loads(x) for x in open(FI.CODA_FIRMA)]
assert righe[1]["siti"] == ["uno.it"] and "siti" not in righe[0], righe
assert "siti" not in righe[3] and righe[4]["siti"] == ["due.org"], righe
print("3 coda di firma: ok")

# 4. registro delle letture: una volta per chiamata, ultime N, solo negli ultimi M minuti (D10)
M._letture.clear()
M.registra_letture(msgs2)
M.registra_letture(msgs2)   # Hermes rimanda la storia: niente doppioni
assert [x[2] for x in M._letture] == ["vecchio.it", "uno.it", "uno.it", "due.org"], list(M._letture)
assert M._recenti() == ["vecchio.it", "uno.it", "due.org"]
assert M._recenti(time.time() + 31 * 60) == []
M._letture.clear()
for k in range(7):
    M._letture.append((time.time(), f"x{k}", f"s{k}.it"))
assert M._recenti() == [f"s{k}.it" for k in range(2, 7)]
print("4 letture recenti: ok")

# 5. correggicordo con un Lux finto
certi, ricevute = {}, []


class LuxFinto(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ricevute.append((self.path, d))
        if self.path == "/fiducia":
            r, c = {"certi": {s: certi.get(s, False) for s in d["siti"]}}, 200
        elif d["codice"] == "0123456789abcdef":
            r, c = {"codice": "fedcba9876543210"}, 200
        else:
            r, c = {"errore": "codice sconosciuto"}, 400
        b = json.dumps(r).encode()
        self.send_response(c)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), LuxFinto)
threading.Thread(target=srv.serve_forever, daemon=True).start()
M.LUX_BASE = f"http://127.0.0.1:{srv.server_port}"
GIUSTO = {"codice": "0123456789abcdef", "testo": "il testo giusto"}

M._letture.clear()
M._letture.append((time.time() - 600, "p", "dubbio.it"))   # sito non certo letto 10 minuti fa
assert M.correggicordo(GIUSTO) == M.R_DUBBIO
assert not any(p == "/correggi" for p, _ in ricevute)
M._letture.clear()
M._letture.append((time.time() - 40 * 60, "p", "dubbio.it"))   # 40 minuti fa: fuori dalla finestra
S._fonte_utente[0] = True
assert M.correggicordo(GIUSTO) == "Ricordo corretto. Il nuovo codice è fedcba9876543210."
assert ricevute[-1] == ("/correggi", {**GIUSTO, "fonte": "@utente:localhost", "siti": []}), ricevute[-1]
M._letture.append((time.time() - 60, "q", "dubbio.it"))
for k in range(5):   # cinque pagine certe dopo quella dubbia: esce dalle ultime N
    certi[f"c{k}.it"] = True
    M._letture.append((time.time(), f"c{k}", f"c{k}.it"))
S._fonte_utente[0] = False
assert M.correggicordo(GIUSTO).startswith("Ricordo corretto.")
assert ricevute[-1][1]["fonte"] == "@agente:localhost" and len(ricevute[-1][1]["siti"]) == 5
assert M.correggicordo({"codice": "zzz", "testo": "x"}) == M.R_CODICE
C.CONSENSO.write_text("[attivo: *no*]\n", encoding="utf-8")
n = len(ricevute)
assert M.correggicordo(GIUSTO) == M.R_GIU and len(ricevute) == n   # consenso spento: niente si scrive
C.CONSENSO.write_text("[attivo: *sì*]\n", encoding="utf-8")
srv.shutdown()
srv.server_close()
assert M.correggicordo(GIUSTO) == M.R_GIU   # Lux giu'
print("5 correggicordo: ok")

print("test_fonti_124: TUTTO VERDE")
