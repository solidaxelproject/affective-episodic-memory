#!/usr/bin/env python3
"""Fotografia del riflesso (PIANO-DIVISIONE-RIFLESSO.md, task 1): importa riflesso (e i riflesso_* che ci sono), lo
fa girare contro un server finto unico (llama, ponte, Lux) col Proxy vero, in 9 passi, e scrive un JSON con le
richieste ricevute dal finto (ordinate), i byte delle risposte del proxy, i file della cartella temporanea e le righe
dei diari. Su stdout lo sha256 del JSON. Prima e dopo ogni estrazione il JSON deve restare identico.

Si lancia SOLO nello spazio di rete isolato (trappola 9), dalla cartella del worktree:
  unshare -rn sh -c 'ip link set lo up; cd /data/memoria-episodica-affettiva-divisione && /usr/bin/python3 manutenzione/foto_riflesso.py [USCITA.json]'
Senza USCITA il JSON va in manutenzione/foto-riflesso-ultima.json. Esce con 1 se un ramo atteso manca."""
import os
import sys

# cose da fermare prima di tutto: hash() di processo e fuso orario (lo script si rilancia con l'ambiente giusto)
if os.environ.get("PYTHONHASHSEED") != "0" or os.environ.get("TZ") != "Europe/Rome":
    os.execve(sys.executable, [sys.executable] + sys.argv, {**os.environ, "PYTHONHASHSEED": "0", "TZ": "Europe/Rome"})
sys.dont_write_bytecode = True   # niente __pycache__ nelle cartelle di produzione (stato.py sta in workspace)

import atexit  # noqa: E402
import collections  # noqa: E402
import hashlib  # noqa: E402
import http.server  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from pathlib import Path  # noqa: E402

QUI = Path(__file__).resolve().parent.parent          # il worktree (o la cartella di riflesso.py)
P_FINTO, P_PROXY = 18090, 18091                        # porte fisse: nello spazio isolato sono libere
VIETATI = ("/data/memoria-episodica-affettiva", "/data/workspace", "/dev/shm/agente-kv")
PORTE_VERE = (8008, 8090, 8091, 8132)
# file di sola lettura che possono restare dove sono (mai scritti dalla fotografia)
AMMESSI = {
    ("via_emotiva", "TRADUZIONE"),   # traduzione-l29.npz: link del worktree verso la produzione, sola lettura
    ("ponte", "LENTE_NPY"), ("ponte", "BASE_LENTE_NPY"),   # lente L29: mai letta qui (leggi e' finta)
    ("ponte", "EMO_NPZ"),            # emo-cvec-v2.npz: lo leggerebbe solo dirs_emozione, mai chiamata (_vettori vuoti)
    ("via_emotiva", "addestra"),     # default uscita=TRADUZIONE: la scriverebbe solo addestra(), mai chiamata qui
    # 12/11: nel repo principale (non nel worktree) anche le cartelle dei moduli e la tabella delle dosi puntano li':
    # sola lettura (QUI serve a trovare i file accanto, TABELLA si legge e basta)
    ("via_emotiva", "QUI"), ("steering", "QUI"), ("steering", "TABELLA"),
}
# (steering.VETTORI sta in /data/jspace e non si legge: vettori finti; steering.TABELLA ed emozioni.json sono del
# worktree; gli attributi dunder dei moduli, es. stato.__file__, non sono percorsi su cui il codice scrive)


def _risponde(porta):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", porta))
        return True
    except OSError:
        return False
    finally:
        s.close()


for _p in PORTE_VERE + (P_FINTO, P_PROXY):
    if _risponde(_p):
        sys.exit(f"STOP: 127.0.0.1:{_p} risponde, la fotografia non e' nello spazio di rete isolato (unshare -rn)")

# ---------- orologio finto: avanza di 1000 s a ogni passo; PRIMA dell'import (_caricato = [time.time()]) ----------
OROLOGIO = [time.mktime((2026, 11, 12, 10, 0, 0, 0, 0, -1))]
_vero_localtime, _vero_strftime = time.localtime, time.strftime
time.time = lambda: OROLOGIO[0]
time.localtime = lambda t=None: _vero_localtime(OROLOGIO[0] if t is None else t)
time.strftime = lambda fmt, t=None: _vero_strftime(fmt, _vero_localtime(OROLOGIO[0]) if t is None else t)

T = Path(tempfile.mkdtemp(prefix="foto-riflesso-"))
atexit.register(shutil.rmtree, T, True)   # anche quando la fotografia si ferma
os.environ.pop("RIFLESSO_COLLAUDO", None)   # bloccherebbe i vettori
os.environ.update(
    VIA_EMOTIVA_STATO=str(T / "via-emotiva-stato.json"),
    VIA_EMOTIVA_DIARIO=str(T / "diario-via-emotiva.jsonl"),
    VIA_EMOTIVA_TRADUZIONE=str(QUI / "engrammi" / "via-emotiva" / "traduzione-l29.npz"),
    RIFLESSO_VETTORI_SPENTI=str(T / "vettori-spenti"),
    CODA_FIRMA=str(T / "coda-firma.jsonl"),
    PONTE_URL=f"http://127.0.0.1:{P_FINTO}",
)

sys.path.insert(0, str(QUI))
import riflesso  # noqa: E402,F401

for _f in sorted(QUI.glob("riflesso_*.py")):
    importlib.import_module(_f.stem)
MODULI = [m for n, m in sorted(sys.modules.items()) if n == "riflesso" or n.startswith("riflesso_")]
VE = sys.modules["via_emotiva"]
OMEOSTATO = VE.omeostato
PONTE = sys.modules["ponte"]
STEERING = sys.modules["steering"]


def dove(nome):
    return [m for m in MODULI if nome in vars(m)]


def prendi(nome):
    ms = dove(nome)
    if len(ms) != 1:
        sys.exit(f"STOP: {nome} sta in {len(ms)} moduli riflesso* ({[m.__name__ for m in ms]}), ne serve uno")
    return getattr(ms[0], nome)


def metti(nome, valore):
    """assegna nome nel modulo riflesso* che lo definisce; si ferma se non e' esattamente uno"""
    ms = dove(nome)
    if len(ms) != 1:
        sys.exit(f"STOP: metti({nome}): in {len(ms)} moduli riflesso* ({[m.__name__ for m in ms]}), ne serve uno")
    for m in ms:
        setattr(m, nome, valore)


def metti_percorso(nome, rel):
    vecchio = prendi(nome)
    metti(nome, str(T / rel) if isinstance(vecchio, str) else Path(T / rel))


# ---------- percorsi su file in temp, servizi sul finto ----------
for _n, _r in [("VETTORI_SPENTI", "vettori-spenti"), ("DIARIO", "diario-riflessi.jsonl"), ("CODA_FIRMA", "coda-firma.jsonl"),
               ("PENSATOIO_DIR", "pensatoio"), ("CONSEGNE", "consegne-memorinvolontaria.json"),
               ("ORE", "ore-messaggi.json"), ("KV_RAM", "kv"), ("KV_SSD", "kv-ssd"), ("TOKFILE", "cc-token"),
               ("RIEPILOGO", "riepilogo.json"), ("RIEPILOGO_PROMUOVI", ".riepilogo-promuovi"),
               ("RIEPILOGO_LOG", "logRiepilogo.md"), ("DORMI_FLAG", ".dormi-richiesto"),
               ("SWITCH_IN_CORSO", ".switch-in-corso"), ("FISSA", "riepilogo-fissa.json"),
               ("MEMORIA_B", "memoria-b.json"), ("MASTER", "master.json"),
               ("STREAM_LIVE", "stream-live.log"), ("VOLO", "chat-in-volo"), ("FASE", "fase")]:
    metti_percorso(_n, _r)
KV = Path(prendi("KV_RAM"))
KV.mkdir()
metti("UPSTREAM", ("127.0.0.1", P_FINTO))
metti("LUX", f"http://127.0.0.1:{P_FINTO}/consegna")
metti("LUX_FORZA", f"http://127.0.0.1:{P_FINTO}/forza")
metti("HS", f"http://127.0.0.1:{P_FINTO}")
prendi("_sam_accesa").__defaults__ = (("127.0.0.1", P_FINTO),)   # trappola 11
VE.omeostato.FILE = Path(T / "stato-emotivo.json")
VE.omeostato.CONF = Path(T / "eutimia.json")

# ---------- finti fissi ----------
FINTO = {}   # la configurazione del finto per la richiesta in corso (vedi PASSI)
metti("_typing", lambda: False)
metti("_motore_attivo", lambda: False)
metti("_skills_da_hermes", lambda tools: FINTO["elenco"])
OMEOSTATO.random = random.Random(0)   # il ritorno eutimico ha un rumore gaussiano: fermato con un seme

import numpy as np  # noqa: E402

_g = np.random.default_rng(0)   # vettori di steering finti come test_riflesso.py:8-12 (sempre: il npz si rigenera)
STEERING._vettori.clear()
STEERING._norme.clear()
for _a in STEERING.EN.values():
    STEERING._vettori[_a] = {l: _g.standard_normal(2048).astype(np.float32) for l in STEERING.STRATI}
    STEERING._norme[_a] = {l: np.float32(1.0) for l in STEERING.STRATI}


def _leggi_finta(testo):
    """via_emotiva.leggi fissa: z sui 44 assi dal testo (sempre lo stesso per lo stesso testo), token = parole"""
    seme = int(hashlib.sha1(testo[:VE.TESTO_MAX].encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seme).standard_normal(44) * 0.7, len(testo.split())


VE.leggi = _leggi_finta


# ---------- controllo: nessun percorso di produzione, nessun servizio vero ----------
def _vietato(v):
    s = str(v)
    if s.startswith("/tmp/"):
        return True
    if not s.startswith("/"):
        return False
    for p in {s, os.path.realpath(s)}:
        if any(p == r or p.startswith(r + "/") for r in VIETATI):
            return True
    return False


def _indirizzo_vero(v):
    if isinstance(v, tuple) and len(v) == 2 and v[1] in PORTE_VERE:
        return True
    return isinstance(v, str) and any(f":{p}" in v and "127.0.0.1" in v for p in PORTE_VERE)


def _valori(v):
    if isinstance(v, (str, Path)):
        return [v]
    if isinstance(v, (tuple, list)) and all(isinstance(x, (str, Path, int)) for x in v):
        return [v] + [x for x in v if isinstance(x, (str, Path))]
    return []


def controlla_isolamento():
    errori, fuori = [], []
    for m in MODULI + [VE, OMEOSTATO, PONTE, STEERING]:
        nome_m = "via_emotiva" if m is VE else m.__name__
        for k, v in vars(m).items():
            if k.startswith("__"):
                continue
            for x in _valori(v):
                if _vietato(x) or _indirizzo_vero(x):
                    if (nome_m, k) not in AMMESSI:
                        errori.append(f"{nome_m}.{k} = {x!r}")
                elif isinstance(x, (str, Path)) and str(x).startswith("/") and not str(x).startswith(str(T)):
                    fuori.append(f"{nome_m}.{k}")
            funzioni = [v] if callable(v) else []
            if isinstance(v, type) and m in MODULI:
                funzioni += list(vars(v).values())
            for f in funzioni:
                for d in (getattr(f, "__defaults__", None) or ()) + tuple((getattr(f, "__kwdefaults__", None) or {})
                                                                          .values()):
                    if any(_vietato(x) or _indirizzo_vero(x) for x in _valori(d)) and (nome_m, k) not in AMMESSI:
                        errori.append(f"default di {nome_m}.{k}: {d!r}")
    if errori:
        sys.exit("STOP: puntano ancora alla produzione:\n  " + "\n  ".join(errori))
    return sorted(set(fuori))


FUORI_TEMP = controlla_isolamento()

# ---------- il server finto unico (llama :8090, ponte, Lux :8132), nel formato vero ----------
RICHIESTE, ULTIMA = [], [time.monotonic()]
_rich_lock = threading.Lock()
SYSTEM_FISSO = ("Sono l'agente. Parlo in italiano con l'utente.\n\n## Skills (mandatory)\n<available_skills>\n"
                "- riepilogo: scrivere il succo dello scambio\n- blocco-appunti: il risveglio del pensatoio\n"
                "</available_skills>\n"
                "Only proceed without loading a skill if genuinely none are relevant to the task.\n\n"
                "Regole fisse della casa.\n")
ELENCO_A = "Only proceed without loading a skill if genuinely none are relevant to the task."
ELENCO_VECCHIO = SYSTEM_FISSO[SYSTEM_FISSO.index("## Skills"):SYSTEM_FISSO.index(ELENCO_A) + len(ELENCO_A)]
ELENCO_NUOVO = ELENCO_VECCHIO.replace("</available_skills>", "- qlux: cercare un ricordo\n</available_skills>")
SYSTEM_A = SYSTEM_FISSO + "══════ sessione ══════\nMEMORY: l'utente ama il mare.\nOggi: giovedi' 12/11/2026\n"
SYSTEM_B = (SYSTEM_FISSO.replace(ELENCO_VECCHIO, ELENCO_NUOVO)
            + "══════ sessione ══════\nMEMORY: l'utente ama il mare. l'agente ha dormito.\nOggi: venerdi' 13/11/2026\n")
RIGA_OK = ("<function=write_file>\n<parameter=path>\n/workspace/memoria/logRiepilogo.md\n</parameter>\n"
           "<parameter=content>\nl'utente mi ha chiesto del mare di agosto: la luce sull'acqua = il ricordo piu' vivo (passo {passo}).\n"
           "</parameter>\n</function>")
TESTO_RICORDO = "Ad agosto l'utente mi ha mandato la foto del mare alle sette di sera, la luce era bassa e dorata."
RISPOSTA_SAM = "Si', l'utente: il mare di agosto me lo ricordo, la luce bassa sull'acqua.\n\n[/pensatoio]"
RAGIONAMENTO = "l'utente mi chiede del mare. Mi e' affiorato un ricordo: la foto delle sette di sera.\n"


def _rendi(d):
    """/apply-template finto: un template chatml che tiene i messaggi come sono (il system con la riga ══ e il
    blocco del riepilogo prima di lei), i tools in fondo al system, e finisce con l'apertura del ragionamento"""
    out = []
    for k, m in enumerate(d.get("messages", [])):
        c = m.get("content")
        c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, sort_keys=True)
        if m.get("tool_calls"):
            c += "<tool_call>" + json.dumps(m["tool_calls"], ensure_ascii=False, sort_keys=True) + "</tool_call>"
        if k == 0 and m.get("role") == "system" and d.get("tools"):
            c += "\n\n# Tools\n" + json.dumps(d["tools"], ensure_ascii=False, sort_keys=True)
        out.append(f"<|im_start|>{m.get('role')}\n{c}<|im_end|>\n")
    return "".join(out) + "<|im_start|>assistant\n<think>\n"


def _ricordo(testo, emozione, dominante, classe):
    codice = hashlib.sha1(testo.encode()).hexdigest()[:16]
    nid = int(codice[:6], 16) % 1000
    r = {"codici": [codice], "risposta": f"1°\n{codice}\n{TESTO_RICORDO}",
         "ricordi": [{"codice": codice, "nid": nid, "dominante": dominante, "classe": classe}]}
    if emozione:
        r["traccia"] = {"candidati": [[nid, 0.612345, 0.71234], [nid + 1, 0.4, 0.3]], "senza": [nid + 1],
                        "scelti": [nid], "oltre_soglia": True}
    return r


def _sse():
    pezzi = [{"delta": {"role": "assistant", "content": None}}]
    pezzi += [{"delta": {"reasoning_content": p}} for p in (RAGIONAMENTO[:30], RAGIONAMENTO[30:])]
    pezzi += [{"delta": {"content": p}} for p in (RISPOSTA_SAM[:25], RISPOSTA_SAM[25:])]
    pezzi += [{"delta": {}, "finish_reason": "stop"}]
    righe = [json.dumps({"id": "chatcmpl-finto", "object": "chat.completion.chunk", "created": 1,
                         "model": "occamy", "choices": [{"index": 0, "finish_reason": None, **p}]},
                        ensure_ascii=False) for p in pezzi]
    return "".join(f"data: {r}\n\n" for r in righe + ["[DONE]"]).encode()


def _risposta(metodo, percorso, corpo):
    d = {}
    if corpo:
        try:
            d = json.loads(corpo)
        except ValueError:
            pass
    js = "application/json"
    if percorso == "/health":
        return 200, js, {"status": "ok"}
    if percorso == "/slots" and metodo == "GET":
        return 200, js, [{"id": 0, "id_task": -1, "n_ctx": 262144, "n_prompt_tokens": FINTO["n_tok"],
                          "is_processing": False}]
    if percorso.startswith("/slots/0?action="):
        azione, nome = percorso.split("=", 1)[1], d.get("filename", "")
        f = KV / nome
        if azione == "save":
            f.write_text(f"kv finto: {nome}, passo {FINTO['passo']}, {FINTO['n_tok']} token\n")
            return 200, js, {"id_slot": 0, "filename": nome, "n_saved": FINTO["n_tok"], "n_written": 1000}
        if azione == "restore":
            if not f.exists():
                return 400, js, {"error": {"code": 400, "message": "failed to restore slot", "type": "invalid"}}
            return 200, js, {"id_slot": 0, "filename": nome, "n_restored": FINTO["n_tok"], "n_read": 1000}
    if percorso == "/apply-template":
        return 200, js, {"prompt": _rendi(d)}
    if percorso == "/completion":
        testo = FINTO["riepilogo"].replace("{passo}", str(FINTO["passo"])) if d.get("n_predict", 0) > 1 else "."
        return 200, js, {"content": testo, "stop": True, "tokens_predicted": d.get("n_predict", 1),
                         "tokens_evaluated": len(d.get("prompt", "")) // 4}
    if percorso == "/control-vector":
        return 200, js, {"success": True}
    if percorso == "/lux-read":
        return 200, js, {"mean": [0.0] * 4, "n_tokens": 1}
    if percorso == "/v1/chat/completions":
        return 200, "text/event-stream", _sse()
    if percorso == "/consegna":
        if "soglia" in d:   # qlux (_lux_cerca): soglia 0, ricerca volontaria
            r = FINTO["qlux"]
            return 200, js, _ricordo("qlux " + d.get("testo", ""), None, *r) if r else {}
        r = FINTO["consegna"]
        return 200, js, _ricordo(d.get("testo", ""), d.get("emozione"), *r) if r else {}
    if percorso == "/forza":
        return 200, js, {"forza": 0.8}
    if metodo == "GET":
        return 200, js, {"default_generation_settings": {"n_ctx": 262144}, "total_slots": 1}
    return 404, js, {"error": {"code": 404, "message": "File Not Found", "type": "not_found_error"}}


class Finto(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._tratta(None)

    def do_POST(self):
        self._tratta(self.rfile.read(int(self.headers.get("Content-Length", 0))))

    def _tratta(self, corpo):
        with _rich_lock:
            RICHIESTE.append((self.command, self.path, corpo))
            ULTIMA[0] = time.monotonic()
        stato, tipo, dati = _risposta(self.command, self.path, corpo)
        b = dati if isinstance(dati, bytes) else json.dumps(dati, ensure_ascii=False).encode()
        self.send_response(stato)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
        with _rich_lock:
            ULTIMA[0] = time.monotonic()


ERRORI_PROXY = []


class ServerProxy(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        e = sys.exc_info()[1]
        ERRORI_PROXY.append(f"{type(e).__name__}: {e}")
        traceback.print_exc()


finto = http.server.ThreadingHTTPServer(("127.0.0.1", P_FINTO), Finto)
proxy = ServerProxy(("127.0.0.1", P_PROXY), prendi("Proxy"))
for _s in (finto, proxy):
    threading.Thread(target=_s.serve_forever, daemon=True, name=f"server {_s.server_address[1]}").start()
BASE_THREAD = set(threading.enumerate())


def quiete():
    """nessuna richiesta nuova al finto per 1 s e nessun thread oltre quelli di partenza (_salva_kv, _fine_chat,
    _leggi_risposta, Timer del vettore); un Timer vivo oltre 30 s ferma la fotografia"""
    t0 = time.monotonic()
    while True:
        extra = [t for t in threading.enumerate() if t not in BASE_THREAD]
        if not extra and time.monotonic() - ULTIMA[0] >= 1.0:
            return
        trascorso = time.monotonic() - t0
        timer = [t for t in extra if isinstance(t, threading.Timer)]
        if timer and trascorso > 30:
            sys.exit(f"STOP: Timer vivo oltre 30 s: {[t.name for t in timer]}")
        if trascorso > 120:
            sys.exit(f"STOP: nessuna quiete dopo 120 s, thread: {[t.name for t in extra]}")
        time.sleep(0.05)


def manda(metodo, percorso, corpo=None):
    """una richiesta al Proxy vero, byte grezzi; -> byte grezzi della risposta"""
    b = b"" if corpo is None else (corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False)
                                   .encode())
    testa = f"{metodo} {percorso} HTTP/1.1\r\nHost: 127.0.0.1:{P_PROXY}\r\n"
    if corpo is not None:
        testa += f"Content-Type: application/json\r\nContent-Length: {len(b)}\r\n"
    testa += "Connection: close\r\n\r\n"
    s = socket.create_connection(("127.0.0.1", P_PROXY), timeout=300)
    try:
        s.sendall(testa.encode() + b)
        out = b""
        while True:
            x = s.recv(65536)
            if not x:
                return out
            out += x
    finally:
        s.close()


# ---------- la sequenza ----------
TOOLS = [{"type": "function", "function": {"name": "write_file", "description": "Scrive un file",
                                           "parameters": {"type": "object", "properties": {
                                               "path": {"type": "string"}, "content": {"type": "string"}},
                                               "required": ["path", "content"]}}},
         {"type": "function", "function": {"name": "read_file", "description": "Legge un file",
                                           "parameters": {"type": "object", "properties": {
                                               "path": {"type": "string"}}, "required": ["path"]}}}]


def u(t):
    return {"role": "user", "content": t}


def a(t):
    return {"role": "assistant", "content": t}


def chat(system, msgs):
    return {"model": "occamy", "stream": True, "messages": [{"role": "system", "content": system}] + msgs,
            "tools": TOOLS}


U1 = u("[utente] l'agente, ti ricordi il mare di agosto? Mi e' tornato in mente oggi.")
U2 = u("[utente] Raccontami cosa ti e' rimasto di quel giorno.")
A2 = a("Mi e' rimasta la luce sull'acqua, ma adesso mi gira la testa: vectreflexstop")
U3 = u("[utente] Va bene, fermiamoci un attimo.")
U3B = u("[utente] Ti va di riprendere fra poco?")
U4 = u("[utente] Ok, chiudiamo per oggi: domani ne riparliamo.")
UB1 = u("[utente] Buongiorno l'agente, sono di nuovo qui.")
UB2 = u("[utente] Oggi parliamo a lungo, ho tante cose da dirti.")
RISVEGLIO = ("[IMPORTANT: You are running as a scheduled cron job. Load the skill blocco-appunti and follow it.]\n\n"
             "Risveglio del pensatoio.\nLa riga è:\n| [12/11] [mare]{cosa resta di un ricordo quando cambia la luce?}\n")
LETTURA = ("La luce radente della sera allunga le ombre sull'acqua e cambia il colore del mare: "
           "dal blu al verde, poi all'oro. ") * 6
PENS = [{"role": "system", "content": "Sei l'agente nel pensatoio."}, u(RISVEGLIO)]
PENS2 = PENS + [{"role": "assistant", "content": "", "tool_calls": [
    {"id": "call_1", "type": "function", "function": {"name": "read_file",
                                                      "arguments": "{\"path\": \"/workspace/memoria/mare.md\"}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": json.dumps({"content": "<p>" + LETTURA + "</p>"})}]
BASE = {"n_tok": 20000, "consegna": ("joy", "vissuto"), "qlux": ("trust", "vissuto"), "riepilogo": RIGA_OK,
        "elenco": ELENCO_VECCHIO}
CHAT = "/v1/chat/completions"
MEMO = "/memorinvolontaria"


def prima_della_promozione():
    """quello che fa dormi-esegui.sh alla dormita: consuma la richiesta di switch e lascia il flag"""
    Path(prendi("DORMI_FLAG")).unlink(missing_ok=True)
    Path(prendi("RIEPILOGO_PROMUOVI")).write_text("", encoding="utf-8")


PASSI = [
    ("1 chat con ricordo e vettore", None, [
        ("POST", CHAT, chat(SYSTEM_A, [U1]), {})]),
    ("2 chat senza ricordo", None, [
        ("POST", CHAT, chat(SYSTEM_A, [U1, a(RISPOSTA_SAM), U2]), {"consegna": None, "elenco": ELENCO_NUOVO})]),
    ("3 chat con vectreflexstop", None, [
        ("POST", CHAT, chat(SYSTEM_A, [U1, a(RISPOSTA_SAM), U2, A2, U3]),
         {"elenco": ELENCO_NUOVO, "riepilogo": "Va bene, ci fermiamo."})]),
    ("4 pensatoio", None, [
        ("POST", CHAT, {"model": "occamy", "stream": True, "messages": PENS, "tools": TOOLS},
         {"n_tok": 120000, "consegna": ("sadness", "letto")}),
        ("POST", CHAT, {"model": "occamy", "stream": True, "messages": PENS2, "tools": TOOLS},
         {"n_tok": 121000, "consegna": None})]),
    ("5 cron (flusso altro)", None, [
        ("POST", CHAT, {"model": "occamy", "stream": True, "messages": [
            {"role": "system", "content": "Sei il servizio rassegne."}, u("Prepara la rassegna stampa di oggi.")]},
         {}),
        ("GET", "/props", None, {})]),
    ("6 memorinvolontaria +lux e qlux", None, [
        ("POST", MEMO, {"+lux": "l'utente mi ha insegnato a guardare il mare la sera."}, {}),
        ("POST", MEMO, {"+lux": "   "}, {}),
        ("POST", MEMO, {"qlux": "il mare del 3/8"}, {}),
        ("POST", MEMO, {"qlux": "nuvole di ieri"}, {"qlux": None}),
        ("POST", MEMO, {}, {})]),
    ("7 fine turno con riepilogo (avviso 90k e [cwswitch])", None, [
        ("POST", CHAT, chat(SYSTEM_A, [U1, a(RISPOSTA_SAM), U2, A2, U3, a("Va bene."), U3B, a("Si', fra poco."), U4]),
         {"n_tok": 95000, "elenco": ELENCO_NUOVO, "riepilogo": RIGA_OK + "\n[cwswitch]"})]),
    ("8 promozione col flag", prima_della_promozione, [
        ("POST", CHAT, chat(SYSTEM_B, [UB1]), {"n_tok": 3000, "elenco": ELENCO_NUOVO})]),
    ("9 switch oltre 100k", None, [
        ("POST", CHAT, chat(SYSTEM_B, [UB1, a(RISPOSTA_SAM), UB2]), {"n_tok": 120000, "elenco": ELENCO_NUOVO})]),
]
LOG = {"diario-riflessi.jsonl", "coda-firma.jsonl", "diario-via-emotiva.jsonl"}   # append da piu' thread
_letto = collections.defaultdict(int)


def _corpo(b):
    if b is None:
        return None
    try:
        v = json.loads(b)
    except ValueError:
        v = b.decode("utf-8", "backslashreplace")
    if len(b) > 20000:   # i vettori di steering: 17 strati x 2048 numeri
        return {"sha256": hashlib.sha256(b).hexdigest(), "byte": len(b), "inizio": b[:300].decode("utf-8", "replace")}
    return v


def _contenuto(p):
    b = p.read_bytes()
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return {"sha256": hashlib.sha256(b).hexdigest(), "byte": len(b)}


def _righe_nuove():
    nuove = {}
    for nome in sorted(LOG):
        p = T / nome
        if p.exists():
            b = p.read_bytes()
            nuove[nome] = sorted(b[_letto[nome]:].decode("utf-8").splitlines())
            _letto[nome] = len(b)
    return nuove


def _file():
    return {str(p.relative_to(T)): ("(cartella)" if p.is_dir() else _contenuto(p))
            for p in sorted(T.rglob("*")) if p.name not in LOG}


def _breve(riga):
    try:
        d = json.loads(riga)
    except ValueError:
        return riga[:120]
    return "; ".join(f"{k}: {json.dumps(v, ensure_ascii=False)[:90]}" for k, v in d.items() if k != "ts")


# i nomi dei moduli cambiano con la divisione: solo su stderr, mai nel JSON (che deve restare identico)
print(f"moduli: {[m.__name__ for m in MODULI]}; percorsi assoluti fuori dalla cartella temporanea (sola lettura o "
      f"stringhe del container): {FUORI_TEMP}", file=sys.stderr)
uscita = {"fotografia": "PIANO-DIVISIONE-RIFLESSO task 1", "passi": []}
for n, (nome, prima, richieste) in enumerate(PASSI, 1):
    OROLOGIO[0] += 1000
    if prima:
        prima()
    risposte = []
    inizio = len(RICHIESTE)
    for metodo, percorso, corpo, conf in richieste:
        FINTO.clear()
        FINTO.update(BASE, passo=n, **conf)
        risposte.append({"richiesta": f"{metodo} {percorso}", "corpo": corpo,
                         "risposta": manda(metodo, percorso, corpo).decode("utf-8", "backslashreplace")})
        quiete()
    ricevute = sorted(((m, p, _corpo(c)) for m, p, c in RICHIESTE[inizio:]),
                      key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
    nuove = _righe_nuove()
    uscita["passi"].append({
        "passo": nome,
        "riassunto": {"percorsi del proxy verso il finto": dict(sorted(collections.Counter(
            f"{m} {p}" for m, p, _ in ricevute).items())),
            "diario dei riflessi": [_breve(r) for r in nuove.get("diario-riflessi.jsonl", [])],
            "file dopo il passo": sorted(_file())},
        "ricevute dal finto": [{"metodo": m, "percorso": p, "corpo": c} for m, p, c in ricevute],
        "risposte del proxy": risposte,
        "righe nuove dei diari": nuove,
        "errori del proxy": ERRORI_PROXY[:],
    })
    ERRORI_PROXY.clear()
uscita["file finali"] = _file()
uscita["diari"] = {nome: [r for p in uscita["passi"] for r in p["righe nuove dei diari"].get(nome, [])]
                   for nome in sorted(LOG)}


# ---------- i rami attesi (se un passo prende solo un ramo d'errore, la fotografia non vale) ----------
def _ha(p, *chiavi):
    return all(any(k in r for r in p["riassunto"]["diario dei riflessi"]) for k in chiavi)


def _chiamate(p, k):
    return p["riassunto"]["percorsi del proxy verso il finto"].get(k, 0)


P = uscita["passi"]
diari = "\n".join(r for righe in uscita["diari"].values() for r in righe)
RAMI = {
    "1 ricordo consegnato col vettore": _ha(P[0], 'memorinvolontaria: ["') and '"vettore": ["gioia"' in diari
    and _chiamate(P[0], "POST /forza") == 1 and _chiamate(P[0], "POST /control-vector") == 2,
    "1 prefill del ricordo e riepilogo con base nuova": _chiamate(P[0], "POST /apply-template") >= 3
    and _chiamate(P[0], "POST /completion") >= 4 and "kv/riepilogo-base.kv.impronta" in P[0]["riassunto"]["file dopo il passo"],
    "1 via emotiva letta (messaggio e risposta)": '"chi": "utente"' in diari and '"chi": "agente"' in diari,
    "1 coda di firma-subito": '"autore": "@utente:localhost"' in diari,
    "2 ricordo rimesso al suo posto, nessuno nuovo": not _ha(P[1], "memorinvolontaria")
    and _chiamate(P[1], "POST /consegna") == 1,
    "2 elenco skill nuovo": _ha(P[1], "elenco skill nuovo nella CW del riepilogo"),
    "3 vectreflexstop": _ha(P[2], "kill: \"vectreflexstop scritto dall'agente\"") and _ha(P[2], "vettore: null"),
    "3 riepilogo scartato": _ha(P[2], "scartato, niente write_file"),
    "4 pensatoio: scambio, vettore, avviso 100k": _ha(P[3], "scambio -> pensatoio", "avviso 100k -> pensatoio")
    and '"vettore": ["tristezza"' in diari and _chiamate(P[3], "POST /control-vector") == 2,
    "5 cron: slot ceduto": _ha(P[4], "flusso estraneo: slot ceduto") and _chiamate(P[4], "GET /props") == 1,
    "6 +lux e qlux": _ha(P[5], "+lux", "qlux") and _chiamate(P[5], "POST /consegna") == 2,
    "7 riepilogo ok, avviso 90k, [cwswitch], vettore": _ha(P[6], "scambio -> chat", "switch: [cwswitch]")
    and _ha(P[6], 'vettore: ["gioia"') and not _ha(P[6], "kill")
    and "superato i 90mila token" in json.dumps(P[6]["ricevute dal finto"], ensure_ascii=False),
    "8 promozione": _ha(P[7], "dormita: ") and ".riepilogo-promuovi" not in P[7]["riassunto"]["file dopo il passo"],
    "9 switch oltre 100k": _ha(P[8], "switch: oltre 100k") and ".dormi-richiesto" in P[8]["riassunto"]["file dopo il passo"],
    "nessun errore del proxy": not any(p["errori del proxy"] for p in P),
    "nessun ramo d'errore nel diario": not any(k in diari for k in ("fallit", "rotta", "non messo", "non letta",
                                                                    "non scritto", "non acceso", "non preparato",
                                                                    "illeggibile", "errore")),
}
uscita["rami attesi"] = RAMI
testo = json.dumps(uscita, ensure_ascii=False, sort_keys=True, indent=1).replace(str(T), "<TMP>")
dest = Path(sys.argv[1]) if len(sys.argv) > 1 else QUI / "manutenzione" / "foto-riflesso-ultima.json"
dest.write_text(testo + "\n", encoding="utf-8")
shutil.rmtree(T, ignore_errors=True)
finto.shutdown()
proxy.shutdown()
mancano = [k for k, v in RAMI.items() if not v]
for k in mancano:
    print(f"RAMO MANCANTE: {k}", file=sys.stderr)
print(hashlib.sha256((testo + "\n").encode()).hexdigest())
sys.exit(1 if mancano else 0)
