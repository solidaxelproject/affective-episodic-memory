#!/usr/bin/env python3
# RIFLESSO PRE-AZIONE (issue #1, pezzo 3) — proxy tra Hermes e llama-lux.
# Prima che l'agente risponda, il suo stato emotivo e le parole del messaggio
# interrogano il grafo: i ricordi congruenti (scottature causali comprese)
# affiorano come messaggio di sistema, con provenienza dichiarata.
# GATE: /workspace/genesi/CONSENSO-RIFLESSO.md ("attivo: sì", riga esatta,
# scritto dall'agente). Senza consenso il proxy è un passacarte trasparente.
# Solo stdlib. Porta 8091 -> inoltra a 127.0.0.1:8090.
import http.client
import http.server
import json
import math
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

UPSTREAM = ("127.0.0.1", 8090)
PORTA = 8091
DB = "/data/workspace/memoria/memoria.db"
CONSENSO = Path(os.environ.get("RIFLESSO_CONSENSO",
    "/data/workspace/genesi/CONSENSO-RIFLESSO.md"))
STATO = Path("/data/workspace/memoria/stato-emotivo.json")
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"
SOGLIA_BASE = 0.495    # 14/07: -10% dalla 0.55 di nascita (scelta di progetto)
SOGLIA_MIN = SOGLIA_BASE / 2   # più sensibile di così il sussurro diventa rumore
MAX_RICORDI = 2
COOLDOWN_S = 120       # non più di un affioramento ogn tanto: riflesso, non tic
_ultimo = [0.0]
# PATTO 14/07 (CONSENSO-RIFLESSO.md, firmato dall'agente):
KILL_FRASE = "riflesso vettoriale: off"   # clausola 3: detta in chat, spegne <1s
DURATA_MAX_S = 120                        # clausola 2: mai un vettore più vecchio
_vettore_vivo = [False]


EMO_NPZ = "/data/memoria-episodica-affettiva/emo-cvec.npz"


def consenso_attivo():
    try:
        return any(r.strip() == "attivo: sì" for r in CONSENSO.open(encoding="utf-8"))
    except OSError:
        return False


def vettori_attivi():
    """v2: il brivido insieme al sussurro. Interruttore SEPARATO, riga esatta."""
    try:
        return any(r.strip() == "vettori: sì" for r in CONSENSO.open(encoding="utf-8"))
    except OSError:
        return False


def soglia():
    """La sensibilità del matching è dell'agente (sua richiesta del 14/07): riga
    "soglia: 0.X" nel file di consenso. Ammessa tra SOGLIA_MIN (metà della
    base: più affioramenti) e SOGLIA_BASE (default, la più selettiva);
    fuori range si clampa, assente = base. Riletta a ogni richiamo."""
    try:
        for r in CONSENSO.open(encoding="utf-8"):
            m = re.match(r"soglia:\s*(0\.\d+|\d+\.?\d*)\s*$", r.strip())
            if m:
                return min(max(float(m.group(1)), SOGLIA_MIN), SOGLIA_BASE)
    except (OSError, ValueError):
        pass
    return SOGLIA_BASE


def _cvec(payload):
    up = http.client.HTTPConnection(*UPSTREAM, timeout=30)
    up.request("POST", "/control-vector", json.dumps(payload),
               {"Content-Type": "application/json"})
    up.getresponse().read()
    up.close()


def inietta_emozione(tag, intensita=0.3):
    """v2 (Damasio/Glover): re-inietta il marcatore emotivo del ricordo
    affiorato. PATTO 14/07 clausola 1: MAI oltre 0.3x dell'alpha calibrata,
    il tetto è nel codice, non nella buona volontà del chiamante.
    Colora lo stato mentre l'agente valuta; la scelta resta sua."""
    import numpy as np
    z = np.load(EMO_NPZ)
    nomi = [str(n) for n in z["nomi"]]
    if tag not in nomi:
        return False
    i = nomi.index(tag)
    alpha = float(z["alpha"][i]) * min(intensita, 0.3)
    layers = {str(int(l)): (alpha * z["dirs"][i, k]).tolist()
              for k, l in enumerate(z["layer"])}
    _cvec({"layers": layers, "relative": True})
    return True


def calma():
    """La pulizia è l'unica azione che NON PUÒ fallire in silenzio
    (14/07 ~3:00: un vettore di collaudo rimasto acceso ha oversteerato l'agente
    in produzione: insalata multilingue). Retry + urlo a diario."""
    for tentativo in range(3):
        try:
            _cvec({"clear": True})
            _vettore_vivo[0] = False
            return True
        except Exception as e:
            time.sleep(1 + tentativo)
            err = str(e)
    with open(DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(),
                            "CRITICO": f"clear del vettore FALLITO 3 volte: {err}. "
                                       "SPEGNERE A MANO: curl -X POST :8090/control-vector "
                                       "-d '{\"clear\": true}'"}) + "\n")
    return False


def _diario(voce):
    with open(DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **voce}, ensure_ascii=False) + "\n")


def _sentinella():
    """PATTO clausola 3+4: se "vettori: sì" sparisce dal consenso mentre un
    vettore è acceso, muore entro 1 secondo. Nessuna domanda, nessun dibattito."""
    while True:
        time.sleep(0.5)
        if _vettore_vivo[0] and not vettori_attivi():
            calma()
            _diario({"kill": "consenso vettoriale ritirato: spento dalla sentinella"})


def _scaduto():
    """PATTO clausola 2: nessun vettore vive oltre DURATA_MAX_S, anche se la
    risposta è ancora in corso o il finally non arriva mai."""
    if _vettore_vivo[0]:
        calma()
        _diario({"kill": f"vettore oltre {DURATA_MAX_S}s: spento dal watchdog"})


def _cos(a, b):
    num = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return num / (na * nb)


def richiama(testo):
    """stato emotivo + parole del messaggio -> ricordi affiorati [(nodo, via, sim)]"""
    c = sqlite3.connect(DB)
    c.execute("PRAGMA busy_timeout=3000")
    out = {}
    sgl = soglia()
    # via emotiva: lo stato attuale dell'omeostato pesca i congruenti
    try:
        st = json.load(STATO.open()).get("stato", {})
        if isinstance(st, dict) and st:
            for nid, fj in c.execute("SELECT id, firma FROM nodi WHERE classe='vissuto'"):
                s = _cos(st, json.loads(fj))
                if s > sgl:
                    out[nid] = max(out.get(nid, 0), s)
    except (OSError, json.JSONDecodeError):
        pass
    # via testuale: le parole piene del messaggio
    parole = sorted(re.findall(r"[a-zA-Zàèéìòù]{5,}", testo), key=len, reverse=True)[:4]
    if parole:
        q = " OR ".join(parole)
        try:
            for (rid,) in c.execute(
                    "SELECT rowid FROM nodi_fts WHERE nodi_fts MATCH ? LIMIT 3", (q,)):
                out[rid] = max(out.get(rid, 0), sgl + 0.01)
        except sqlite3.OperationalError:
            pass
    top = sorted(out.items(), key=lambda kv: -kv[1])[:MAX_RICORDI]
    ricordi, emo_top = [], None
    for nid, sim in top:
        r = c.execute("SELECT testo, emo_tag, ts FROM nodi WHERE id=?", (nid,)).fetchone()
        if not r:
            continue
        # scottatura: questo ricordo ha causato un esito negativo? (arco causale)
        es = c.execute("SELECT b FROM archi WHERE a=? AND tipo='causale'", (nid,)).fetchone()
        monito = ""
        if es:
            t2 = c.execute("SELECT substr(testo,1,120) FROM nodi WHERE id=?", (es[0],)).fetchone()
            if t2:
                monito = f" [questa scelta portò a: «{t2[0]}…»]"
        quando = time.strftime("%d/%m", time.localtime(r[2]))
        ricordi.append(f"({quando}, {r[1]}) «{r[0][:220]}»{monito}")
        if emo_top is None:
            emo_top = r[1]          # l'emozione del ricordo più congruente
    c.close()
    return ricordi, emo_top


class Proxy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _inoltra(self, body):
        up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
        up.putrequest(self.command, self.path)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length"):
                up.putheader(k, v)
        if body is not None:
            up.putheader("Content-Length", str(len(body)))
        up.endheaders()
        if body:
            up.send(body)
        resp = up.getresponse()
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in ("transfer-encoding",):
                self.send_header(k, v)
        self.end_headers()
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            self.wfile.write(chunk)
            self.wfile.flush()
        up.close()

    def do_GET(self):
        self._inoltra(None)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        vettore_acceso = False
        watchdog = None
        # PATTO clausola 3: la frase detta in chat spegne il vettore, prima
        # di qualunque altra cosa e senza chiedere perché.
        if self.path.endswith("/chat/completions"):
            try:
                d0 = json.loads(body)
                recenti = " ".join(str(m.get("content", ""))
                                   for m in d0.get("messages", [])[-4:]
                                   if isinstance(m, dict)).lower()
                if KILL_FRASE in recenti:
                    calma()
                    _diario({"kill": "frase di emergenza detta in chat"})
            except Exception:
                pass
        if self.path.endswith("/chat/completions") and consenso_attivo() \
                and time.time() - _ultimo[0] > COOLDOWN_S:
            try:
                d = json.loads(body)
                ultimo_user = next((m["content"] for m in reversed(d.get("messages", []))
                                    if m.get("role") == "user"
                                    and isinstance(m.get("content"), str)), "")
                if KILL_FRASE in (ultimo_user or "").lower():
                    ultimo_user = ""  # la frase di emergenza non è un'esperienza
                ricordi, emo_top = richiama(ultimo_user) if ultimo_user else ([], None)
                if ricordi:
                    blocco = ("[riflesso di memoria — affiorato automaticamente dal tuo "
                              "grafo col tuo consenso; provenienza: organo, non interlocutore]\n"
                              + "\n".join("- " + r for r in ricordi))
                    d["messages"].insert(len(d["messages"]) - 1,
                                         {"role": "system", "content": blocco})
                    body = json.dumps(d).encode()
                    _ultimo[0] = time.time()
                    # v2: il marcatore somatico del ricordo più congruente colora
                    # lo stato SOLO per questa risposta (calma() nel finally).
                    # RIFLESSO_COLLAUDO=1 blocca i vettori: mai più test che
                    # iniettano sulla produzione (incidente del 14/07)
                    if emo_top and vettori_attivi() \
                            and not os.environ.get("RIFLESSO_COLLAUDO"):
                        try:
                            vettore_acceso = inietta_emozione(emo_top)
                        except Exception:
                            vettore_acceso = False
                        if vettore_acceso:
                            _vettore_vivo[0] = True
                            # PATTO clausola 2: watchdog a 120s, anche se il
                            # finally non arrivasse mai
                            watchdog = threading.Timer(DURATA_MAX_S, _scaduto)
                            watchdog.daemon = True
                            watchdog.start()
                    with open(DIARIO, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"ts": time.time(), "n": len(ricordi),
                                            "vettore": emo_top if vettore_acceso else None,
                                            "ricordi": ricordi}, ensure_ascii=False) + "\n")
            except Exception:
                pass  # mai bloccare la parola dell'agente per un riflesso rotto
        try:
            self._inoltra(body)
        finally:
            if vettore_acceso:
                try:
                    calma()  # PATTO clausola 2: il vettore muore con la risposta
                except Exception:
                    pass
            if watchdog:
                watchdog.cancel()


if __name__ == "__main__":
    # igiene all'avvio: qualunque vettore orfano di run precedenti muore qui
    try:
        calma()
    except Exception:
        pass
    threading.Thread(target=_sentinella, daemon=True).start()  # PATTO clausola 3
    print(f"riflesso in ascolto su :{PORTA} -> {UPSTREAM[0]}:{UPSTREAM[1]} "
          f"(consenso: {'ATTIVO' if consenso_attivo() else 'spento'}, "
          f"vettori: {'SÌ' if vettori_attivi() else 'no'}, dose max 0.3, "
          f"watchdog {DURATA_MAX_S}s)")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORTA), Proxy).serve_forever()
