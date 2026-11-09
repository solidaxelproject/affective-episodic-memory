#!/usr/bin/env python3
"""Servizio del Lux degli engrammi per il riflesso (11/10/2026). Solo 127.0.0.1:8132.
  POST /consegna  {"testo": "...", "esclusi": ["codice", ...]}
       -> {"codici": [...], "risposta": "1°\\n<codice>\\n<testo>\\n2°..."} da mettere nel tool memorinvolontaria,
       oppure {} = niente. Fino a X.CONSEGNA_MAX ricordi (1.10.0), o catene di correzioni (1.11.0). Rinforza gli archi
       dei ricordi consegnati, tranne quelli corretti
       qlux (09/11): facoltativi "quanti" (il riflesso ne chiede 1), "soglia" (0 = il piu' vicino), "da"/"a"
       (finestra sul momento del ricordo, secondi epoch)
  POST /correggi  {"codice": "...", "testo": "..."} -> {"codice": codice della correzione} (1.11.0) (lux-<VERSIONE>/lux-stato.npz).
  POST /rinforza  {"nid": 123, "peso": 1.0} -> {"rinforzato": true} (B5: sincronizza-richiami a peso 1, eco della
       persistenza a 0.5); un ricordo corretto non si rinforza ({"rinforzato": false}), nid sconosciuto = 400
  POST /richiama  {"testo": "...", "quanti": 1} -> {"ricordi": [[nid, punteggio], ...]} sola lettura, senza soglia e senza
       predisposizione (B5: eco della persistenza, soglia tarata cosi' da taratura_persistenza.py)
  POST /sovrapposizione {"testo": "...", "nid": 123} -> {"n": engrammi del testo, "presi": quanti nel ricordo nid}
       (B6, l'utente 01/11 sera: cattura del behavioral tagging; sola lettura), nid sconosciuto = 400
  GET  /salute    -> {"versione": ..., "ricordi": ..., "engrammi": ...}
Server a un filo solo: due consegne non scrivono lo stato insieme.
ponytail: libreria standard, niente framework"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import lux_engrammi as X

PORTA = int(os.environ.get("LUX_PORTA", 8132))   # B5: altra porta per lo stress-test su una copia (LUX_DIR)
L = X.Lux()
_meta = [os.path.getmtime(X.META)]


def lux():
    """la notturna (lux_engrammi.py aggiungi) riscrive lux-meta.json per ultimo: se e' cambiato si ricarica"""
    global L
    t = os.path.getmtime(X.META)
    if t != _meta[0]:
        nuovo = X.Lux()
        nuovo.pronti = L.pronti   # 1.12.0: la predisposizione sopravvive alla ricarica della notturna
        L, _meta[0] = nuovo, t
    return L


class H(BaseHTTPRequestHandler):
    def rispondi(self, oggetto, codice=200):
        corpo = json.dumps(oggetto, ensure_ascii=False).encode()
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/salute":
            self.rispondi({"versione": X.VERSIONE, "ricordi": len(lux().ricordi), "engrammi": len(L.testi)})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/consegna", "/correggi", "/rinforza", "/richiama", "/sovrapposizione"):
            self.send_error(404)
            return
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/rinforza":
                nid = int(d.get("nid", -1))
                if nid not in lux().per_ricordo:
                    self.rispondi({"errore": f"ricordo sconosciuto: {nid}"}, 400)
                    return
                peso = float(d.get("peso", 1.0))
                if not 0 < peso <= 1:   # anche NaN
                    self.rispondi({"errore": f"peso fuori da (0, 1]: {peso}"}, 400)
                    return
                if nid in L.errati:
                    self.rispondi({"rinforzato": False})
                    return
                L.rinforza(nid, peso=peso)
                self.rispondi({"rinforzato": True})
                return
            if self.path == "/sovrapposizione":
                nid = int(d.get("nid", -1))
                if nid not in lux().per_ricordo:
                    self.rispondi({"errore": f"ricordo sconosciuto: {nid}"}, 400)
                    return
                n, presi = L.sovrapposizione(str(d.get("testo", "")), nid)
                self.rispondi({"n": n, "presi": presi})
                return
            if self.path == "/richiama":
                r = lux().richiama(str(d.get("testo", "")), int(d.get("quanti", 1)), soglia=0, ora=float("inf"))
                self.rispondi({"ricordi": [[int(n), float(p)] for n, p in r]})
                return
            if self.path == "/correggi":
                if str(d.get("codice", "")) not in lux().da_codice or not str(d.get("testo", "")).strip():
                    self.rispondi({"errore": "codice sconosciuto o testo vuoto"}, 400)
                    return
                self.rispondi({"codice": X.correggi(d["codice"], str(d["testo"]))})
                return
            fin = {"da": float(d["da"]), "a": float(d["a"])} if d.get("da") is not None else {}   # qlux (09/11)
            c = lux().consegna(str(d.get("testo", "")), int(d.get("quanti", X.CONSEGNA_MAX)), esclusi=d.get("esclusi", []),
                               soglia=float(d.get("soglia", X.SOGLIA_RICHIAMO)), **fin)
        except Exception as e:   # il riflesso non deve mai fermarsi per il Lux: errore = nessun ricordo
            self.rispondi({"errore": repr(e)}, 500)
            return
        self.rispondi({"codici": [x[1] for x in c], "risposta": L.risposta_tool([x[0] for x in c])} if c else {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Lux {X.VERSIONE} servizio su 127.0.0.1:{PORTA} ({len(L.ricordi)} ricordi)", flush=True)
    HTTPServer.request_queue_size = 64   # B5: il default (5) rifiutava le richieste oltre la quinta arrivate insieme
    HTTPServer(("127.0.0.1", PORTA), H).serve_forever()
