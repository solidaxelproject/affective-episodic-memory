#!/usr/bin/env python3
"""Servizio del Lux degli engrammi per il riflesso (11/10/2026). Solo 127.0.0.1:8132.
  POST /consegna  {"testo": "...", "esclusi": ["codice", ...]}
       -> {"codici": [...], "risposta": "1°\\n<codice>\\n<testo>\\n2°..."} da mettere nel tool memorinvolontaria,
       oppure {} = niente. Fino a X.CONSEGNA_MAX ricordi (1.10.0), o catene di correzioni (1.11.0). Rinforza gli archi
       dei ricordi consegnati, tranne quelli corretti
       qlux (09/11): facoltativi "quanti" (il riflesso ne chiede 4, stessa dominante: fase 2 step b; qlux 1), "soglia" (0 = il piu' vicino), "da"/"a"
       (finestra sul momento del ricordo, secondi epoch)
       1.19.0 (via emotiva): facoltativo "emozione": {"assi": [...], "q": [...], "k": 0.2}; allora la risposta ha anche
       "traccia": {"candidati": [[nid, parole e senso, accordo], ...], "senza": [nid...], "scelti": [nid...]}
  POST /correggi  {"codice": "...", "testo": "..."} -> {"codice": codice della correzione} (1.11.0) (lux-<VERSIONE>/lux-stato.npz).
  POST /rinforza  {"nid": 123, "peso": 1.0} -> {"rinforzato": true} (B5: sincronizza-richiami a peso 1, eco della
       persistenza a 0.5); un ricordo corretto non si rinforza ({"rinforzato": false}), nid sconosciuto = 400
  POST /richiama  {"testo": "...", "quanti": 1} -> {"ricordi": [[nid, punteggio], ...]} sola lettura, senza soglia e senza
       predisposizione (B5: eco della persistenza, soglia tarata cosi' da taratura_persistenza.py)
  POST /sovrapposizione {"testo": "...", "nid": 123} -> {"n": engrammi del testo, "presi": quanti nel ricordo nid}
       (B6, l'utente 01/11 sera: cattura del behavioral tagging; sola lettura), nid sconosciuto = 400
  POST /forza    {"codice": "...", "emo": "fear"} -> {"forza": S_e o null} (PIANO-STEERING-RIFLESSO 7a, 11/11: dose del
       vettore del ricordo; sola lettura)
  POST /riconsolida {} -> {"consegne", "momenti", "spostati", "sorpresa_media", "effetto"} (1.14.0, notturna: qui perche'
       il servizio a un filo tiene lo stato in memoria; dopo si ricarica)
  POST /sbiadisci {} -> {"sbiadito", "giorno", "rodaggio", "umore", "freno_medio"} (1.18.0, notturna, una volta al giorno)
  POST /riaccendi {} -> {"messaggi", "engrammi"} (1.17.0, notturna prima di /riconsolida)
  POST /avvicina {} -> {"archi", "spostati", "rodaggio", "dominanti"} (1.21.0, notturna dopo /riconsolida)
       1.21.0: /consegna con "coda": [codici] (riflesso) torna anche "coda", la coda nuova, pure senza ricordi
  POST /aggiungi  {"testo", "firma": {asse: z}, "classe", "ts", "dominante", "fonte", "cattura", "salienza", "voluto"}
       -> {"nid": n} (1.20.0: il ricordo nuovo entra nel Lux e prende il numero, prima lo dava memoria.db; stesso testo =
       stesso nid); 400 = errore di questo ricordo (firma_subito lo segna e va avanti), 500 = si ritenta
  POST /ricordo   {"codice": "..."} -> {"nid", "testo", "dominante", "firma", "classe"} o {} (1.20.0, barra-prefill;
       le correzioni come ricordo sconosciuto, come quando si cercavano in memoria.db)
       1.20.0: /consegna torna anche "ricordi": [{"codice", "nid", "dominante", "classe"}] per il vettore del riflesso
       (correzione: nid e dominante null)
       1.22.0: /consegna con "tratti": true e "numero": N (memorinvolontaria) = ricombinazione mnemonica: "risposta" =
       "N° ricombinazione mnemonica" + un tratto per riga; "ricordi" = i ricordi dei tratti, la dominante (quella
       dell'engramma acceso piu' importante, per il vettore) solo sulla prima voce; "impronta" = la firma di
       quell'engramma per l'omeostato (barra-prefill, l'utente 13/11 sera); qlux resta col ricordo intero
  POST /ponti {} -> {"ponti", "provvisori", "calati", "tagliati"} (1.23.0, notturna dopo /avvicina: potatura dei ponti)
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
_orfani = sorted(set(L.A[:, 0].tolist()) - set(L.ricordi))   # 1.20.0: crash fra npz e meta in _aggiungi
if _orfani:
    print(f"CRITICO: archi di ricordi assenti dal meta: {_orfani[:20]}", flush=True)


def lux():
    """la notturna (lux_engrammi.py aggiungi) riscrive lux-meta.json per ultimo: se e' cambiato si ricarica"""
    global L
    t = os.path.getmtime(X.META)
    if t != _meta[0]:
        nuovo = X.Lux()
        nuovo.pronti = L.pronti   # 1.12.0: la predisposizione sopravvive alla ricarica della notturna
        L, _meta[0] = nuovo, t
    return L


def _info(cod):
    """1.20.0: il ricordo per il riflesso e barra-prefill; le correzioni non stavano in memoria.db: restano ignote"""
    r = lux().ricordo(cod)
    return None if r is None or r["classe"] == "correzione" else r


def _aggiungi(d):
    """1.20.0: (risposta, codice HTTP) di POST /aggiungi"""
    v = {k: d.get(k) for k in ("testo", "firma", "classe", "ts", *X.CAMPI)}
    if not isinstance(v["testo"], str) or not v["testo"].strip() or not isinstance(v["firma"], dict) \
            or v["classe"] not in ("vissuto", "letto") or not isinstance(v["ts"], (int, float)):
        return {"errore": "servono testo, firma (dict), classe vissuto/letto e ts"}, 400
    v["ts"] = float(v["ts"])   # il codice del ricordo si calcola sul float, come il REAL di memoria.db
    try:
        nid = X.aggiungi_ricordo(v)
    except OSError as e:   # embedder, disco: si ritenta
        return {"errore": repr(e)}, 500
    except Exception as e:   # questo ricordo non entra (taglio, salienza): firma_subito lo segna e va avanti
        return {"errore": repr(e)}, 400
    _meta[0] = None   # ricarica subito, la predisposizione resta (lux())
    lux()
    return {"nid": nid}, 200


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
            self.rispondi({"versione": X.VERSIONE, "ricordi": len(lux().ricordi), "engrammi": len(L.testi),
                           "ponti": len(L.ponti)})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/consegna", "/correggi", "/rinforza", "/richiama", "/sovrapposizione", "/forza", "/riconsolida",
                             "/riaccendi", "/sbiadisci", "/aggiungi", "/ricordo", "/avvicina", "/ponti"):
            self.send_error(404)
            return
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/aggiungi":
                self.rispondi(*_aggiungi(d))
                return
            if self.path == "/ricordo":
                r = _info(str(d.get("codice", "")))
                self.rispondi({k: r[k] for k in ("nid", "testo", "dominante", "firma", "classe")} if r else {})
                return
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
            if self.path in ("/riconsolida", "/riaccendi", "/sbiadisci", "/avvicina", "/ponti"):   # 1.17.0-1.23.0
                r = {"/riconsolida": X.riconsolida, "/riaccendi": X.riaccendi, "/sbiadisci": X.sbiadisci,
                     "/avvicina": X.avvicina, "/ponti": X.pota_ponti}[self.path]()
                _meta[0] = None   # ricarica subito: lo stato in memoria e' quello di prima
                lux()
                self.rispondi(r)
                return
            if self.path == "/forza":
                nid = lux().da_codice.get(str(d.get("codice", "")))
                self.rispondi({"forza": None if nid is None else L.forza(nid, str(d.get("emo", "")))})
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
            if d.get("tratti"):   # 1.22.0 (13/11): ricombinazione mnemonica per memorinvolontaria
                traccia = {} if d.get("emozione") else None
                coda = [str(x) for x in d["coda"]] if isinstance(d.get("coda"), list) else None
                c = lux().ricombina(str(d.get("testo", "")), int(d.get("numero", 1)), esclusi=d.get("esclusi", []),
                                    emozione=d.get("emozione"), traccia=traccia, coda=coda)
                r = {} if c is None else {
                    "codici": c["codici"], "risposta": c["risposta"], "impronta": c["impronta"],
                    # il vettore: dominante dell'engramma sulla prima voce, dose da /forza su quel ricordo (riflesso)
                    "ricordi": [{"codice": cod, "nid": n, "dominante": c["dominante"] if k == 0 else None,
                                 "classe": L.ricordi[n].get("classe")} for k, (n, cod) in enumerate(zip(c["nid"], c["codici"]))]}
                if traccia is not None:
                    r["traccia"] = {**traccia, "scelti": c["nid"] if c else []}
                if coda is not None:
                    r["coda"] = coda
                self.rispondi(r)
                return
            fin = {"da": float(d["da"]), "a": float(d["a"])} if d.get("da") is not None else {}   # qlux (09/11)
            traccia = {} if d.get("emozione") else None   # 1.19.0: via emotiva, candidati per il diario
            coda = [str(x) for x in d["coda"]] if isinstance(d.get("coda"), list) else None   # 1.21.0
            c = lux().consegna(str(d.get("testo", "")), int(d.get("quanti", X.CONSEGNA_MAX)), esclusi=d.get("esclusi", []),
                               soglia=float(d.get("soglia", X.SOGLIA_RICHIAMO)), emozione=d.get("emozione"),
                               traccia=traccia, coda=coda, **fin)
        except Exception as e:   # il riflesso non deve mai fermarsi per il Lux: errore = nessun ricordo
            self.rispondi({"errore": repr(e)}, 500)
            return
        r = {"codici": [x[1] for x in c], "risposta": L.risposta_tool([x[0] for x in c]),
             "ricordi": [{"codice": x[1], **{k: (i or {}).get(k) for k in ("nid", "dominante", "classe")}}
                         for x in c for i in [_info(x[1])]]} if c else {}
        if traccia is not None:
            r["traccia"] = {**traccia, "scelti": [x[0] for x in c]}
        if coda is not None:
            r["coda"] = coda
        self.rispondi(r)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Lux {X.VERSIONE} servizio su 127.0.0.1:{PORTA} ({len(L.ricordi)} ricordi)", flush=True)
    HTTPServer.request_queue_size = 64   # B5: il default (5) rifiutava le richieste oltre la quinta arrivate insieme
    HTTPServer(("127.0.0.1", PORTA), H).serve_forever()
