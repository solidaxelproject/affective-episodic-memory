#!/usr/bin/env python3
"""Stress-test di B6 (PIANO-FIRMA-ENGRAMMI.md): il ricordo entra subito (firma_subito.py, riflesso._accoda_firma,
Lux con soglia nuova e trascinati; Lux 1.20.0: il ricordo lo crea il servizio del Lux, POST /aggiungi). Tutto su
COPIE (Lux 1.19.0 migrato alla 1.20.0 con da_precedente, memoria.db di produzione letto in sola lettura)
e su un finto server (/props, /tokenize, /detokenize, /lux-read con "layers" e "somme") sulla porta 18099: la produzione
si legge e basta (bge-m3 su :8094 solo in lettura).
La firma vera passa dal finto server (punto 8); per la logica (soglia, trascinamento, raffiche, crash) la firma e' finta:
"Z=<numero>" nel testo da' la salienza, cosi' i casi sono esatti.
Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/jspace/venv/bin/python test_firma_subito.py"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
PORTA = 18099
SPACY = "/data/venv-spacy/bin/python"
STATS_VERE = "/data/memoria-episodica-affettiva/stats-firma-se.pt"
FINTO = "--servizio-finto" in sys.argv

if not FINTO:
    TMP = tempfile.mkdtemp(prefix="test-b6-")
    os.makedirs(f"{TMP}/mem")
    subprocess.run([SPACY, "-c", "import lux_engrammi as X; X.da_precedente()"], cwd=QUI, check=True,
                   capture_output=True, env=dict(os.environ, LUX_DIR=f"{TMP}/lux"))   # 1.20.0: copia migrata
    os.environ.update(MEM_SAM=f"{TMP}/mem", LUX_DIR=f"{TMP}/lux", URL_FIRMA=f"http://127.0.0.1:{PORTA}", GIRO_S="0.2",
                      MARKER_NOTTE=f"{TMP}/nessun-marker",   # B7: senza marker la potatura tiene tutto
                      LUX_URL="http://127.0.0.1:18132", LUX_PORTA="18132")   # servizio del Lux sulla copia (cattura)

import firma_subito as FS  # noqa: E402

SOGLIA = FS.stats()["s"]["soglia"]
ASSI = FS.stats()["s"]["assi"]
firma_vera = FS.firma


def firma_finta(contesto, testo):
    """Z=<n> nel testo -> salienza n su A=<asse> (gioia di default); il lettore deve rispondere (35B spento = Aspetta)"""
    try:
        urllib.request.urlopen(FS.URL + "/props", timeout=5).read()
    except OSError as e:
        raise FS.Aspetta(f"finto giu' ({e})")
    time.sleep(float(os.environ.get("RITARDO", 0)))
    z = float((re.search(r"Z=(-?[\d.]+)", testo) or [0, "0"])[1])
    asse = (re.search(r"A=(\w+)", testo) or [0, "joy"])[1]
    f = {a: -0.5 for a in ASSI}
    f[asse] = round(z, 3)
    return f, f[asse], asse


if FINTO:   # il servizio vero con la firma finta, in un processo suo (raffica, crash)
    FS.firma = firma_finta
    FS.servizio()


# ---------- finto server ----------

MODELLO = [FS.stats()["s"]["lettore"]]
_cache = {}


def stato_car(c, l):
    if (c, l) not in _cache:
        r = np.random.default_rng(ord(c) * 100 + l)
        _cache[c, l] = np.ones(2048) * 0.05 + r.normal(0, 0.02, 2048)
    return _cache[c, l]


class Finto(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def manda(self, o, codice=200):
        b = json.dumps(o).encode()
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self.manda({"model_path": MODELLO[0]})

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tokenize":
            self.manda({"tokens": [ord(c) for c in d["content"]]})
        elif self.path == "/detokenize":
            self.manda({"content": "".join(chr(t) for t in d["tokens"])})
        elif self.path == "/lux-read":
            if "RIFIUTA" in d["content"]:
                self.manda({"error": "rifiutato"}, 400)
                return
            strati = [d["layer"]] + d.get("layers", [])
            self.manda({"n_tokens": len(d["content"]),
                        "sums": {str(l): list(sum(stato_car(c, l) for c in d["content"])) for l in strati}})
        else:
            self.manda({})


class Server:
    def __init__(self):
        self.s = None

    def su(self):
        ThreadingHTTPServer.allow_reuse_address = True
        self.s = ThreadingHTTPServer(("127.0.0.1", PORTA), Finto)
        threading.Thread(target=self.s.serve_forever, daemon=True).start()

    def giu(self):
        self.s.shutdown()
        self.s.server_close()


SRV = Server()
SRV.su()


# ---------- attrezzi ----------

def pulisci_coda():
    for f in (FS.CODA, FS.POS, FS.ROTTE, FS.GIORNATA):
        if os.path.exists(f):
            os.remove(f)


def ricordi():
    """1.20.0: i ricordi stanno nel meta del Lux (prima memoria.db)"""
    return {int(k): r for k, r in json.load(open(f"{TMP}/lux/lux-meta.json"))["ricordi"].items()}


def nodi_con(pezzo):
    return [(n, r["testo"], r.get("fonte"), r.get("voluto"), r["classe"]) for n, r in sorted(ricordi().items())
            if pezzo.lower() in r.get("testo", "").lower()]


def nel_lux():
    return set(ricordi())


def esiti():
    """testo -> esito (per testi unici)"""
    return {v["testo"]: v["esito"] for v in FS.registro().values()}


def esito_a(ts):
    return next(v["esito"] for v in FS.registro().values() if v["ts"] == ts)


def voce(ts, testo, autore="@agente:localhost", **k):
    return dict(ts=ts, autore=autore, testo=testo, **k)


def passo_finto():
    FS.firma = firma_finta
    try:
        return FS.passo()
    finally:
        FS.firma = firma_vera


def servizio(**env):
    return subprocess.Popen([sys.executable, __file__, "--servizio-finto"], cwd=QUI, env=dict(os.environ, **env),
                            stdout=open(f"{TMP}/servizio.log", "a"), stderr=subprocess.STDOUT)


def aspetta_vuota(limite=300):
    fine = time.time() + limite
    while FS._pos() < os.path.getsize(FS.CODA):
        assert time.time() < fine, f"coda non svuotata in {limite} s (pos {FS._pos()}, {os.path.getsize(FS.CODA)})"
        time.sleep(0.2)


def sentinella(attesa=0):
    """ogni nodo del registro nel Lux della copia (1.20.0: entra subito, l'attesa resta per i servizi in corsa)"""
    fine = time.time() + attesa
    while True:
        try:
            return _sentinella()
        except AssertionError:
            if time.time() > fine:
                raise
            time.sleep(0.5)


def _sentinella():
    ids = {v["nid"] for v in FS.registro().values() if v["esito"] in ("nodo", "trascinato")}
    assert ids <= nel_lux(), f"nodi fuori dal Lux: {sorted(ids - nel_lux())[:10]}"


T0 = time.time() - 30 * 86400   # ts lontani dai messaggi veri: nessun contesto o doppione dalla chat vera
FORTE = round(SOGLIA + 1.2, 2)
print(f"copie in {TMP}; soglia {SOGLIA:.3f}, forte da {SOGLIA + FS.FORTE_DELTA:.3f}", flush=True)

# ---------- 0. costanti ----------
print("0. soglia del Lux = soglia delle stats", flush=True)
out = subprocess.run([SPACY, "-c", "import lux_engrammi as X; print(X.SOGLIA_FIRMA, X.TRASCINATO_S0)"], cwd=QUI,
                     capture_output=True, text=True, check=True).stdout.split()
assert float(out[0]) == round(SOGLIA, 3) and float(out[1]) == 0.5, out

LUXSRV = subprocess.Popen([SPACY, "servizio_lux.py"], cwd=QUI, env=os.environ.copy(), stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)   # 1.20.0: serve dal primo ricordo (POST /aggiungi)
import atexit  # noqa: E402
atexit.register(LUXSRV.kill)   # anche se il test cade: niente servizi orfani su una copia cancellata
for _ in range(120):
    try:
        urllib.request.urlopen("http://127.0.0.1:18132/salute", timeout=2).read()
        break
    except OSError:
        time.sleep(0.5)

# ---------- 1-4. forte, debole, forzato, doppione ----------
print("1-4. forte, debole, forzato, doppione", flush=True)
pulisci_coda()
FS.accoda([voce(T0, f"B6uno forte e felice Z={FORTE - 1.1:.2f}"),
           voce(T0 + 20000, "B6due debole e piatto Z=0.5"),
           voce(T0 + 20100, "B6due debole e piatto Z=0.5"),
           voce(T0 + 40000, "B6tre voglio tenerlo Z=0.1", forzato=True),
           voce(T0 + 40100, "B6q", forzato=True),
           voce(T0 + 30000, "[ricordare]{B6vecchio marcatore Z=0.1}"),   # 09/11: il marcatore non forza piu'
           voce(T0 + 40200, "corto Z=9"),
           voce(T0 + 40300, "B6cinque parla di https://esempio.it molto Z=3.0")])
assert passo_finto() == "pronto"
e = esiti()
assert e[f"B6uno forte e felice Z={FORTE - 1.1:.2f}"] == "nodo", e
assert esito_a(T0 + 20000) == "scartato" and esito_a(T0 + 20100) == "doppione"   # stesso autore e stesso inizio
assert e["B6tre voglio tenerlo Z=0.1"] == "nodo" and e["B6q"] == "nodo" and e["corto Z=9"] == "corto"
assert e["[ricordare]{B6vecchio marcatore Z=0.1}"] == "scartato", e
uno, = nodi_con("B6uno")
assert uno[2] == "@agente:localhost" and uno[4] == "vissuto" and uno[3] == 0
assert not nodi_con("B6due")
tre, = nodi_con("B6tre")
assert tre[1] == "B6tre voglio tenerlo Z=0.1" and tre[3] == 1   # forzato (+lux), voluto
q, = nodi_con("B6q")
assert q[3] == 1                                               # forzato corto: entra lo stesso
cinque, = nodi_con("B6cinque")
assert cinque[4] == "letto"
assert {uno[0], tre[0], q[0], cinque[0]} <= nel_lux()
f = ricordi()[uno[0]]["firma"]
assert list(f) == ASSI
sentinella()

# ---------- 5. behavioral tagging ----------
print("5. cattura: tempo + sovrapposizione parziale, stabilita' graduale, URL, finestra, nodo non forte", flush=True)
tb = T0 + 100000
FORTE_T = "Stamattina al mercato di via Roma ho comprato le arance rosse di Sicilia per la marmellata della nonna"
LEGATO = "Le arance rosse di Sicilia per la marmellata della nonna le ho pulite stasera, e domani accendo il fuoco"
ESTRANEO = "Domani devo portare la bicicletta dal meccanico perche' il freno posteriore fa un rumore strano"
FS.accoda([voce(tb, f"{LEGATO} prima Z=0.3"),
           voce(tb + 30, f"{ESTRANEO} prima Z=0.3"),
           voce(tb + 60, f"{LEGATO} con www.esempio.it Z=0.2"),
           voce(tb + 600, f"{FORTE_T} Z={FORTE}"),
           voce(tb + 1200, f"{LEGATO} dopo Z=0.4"),
           voce(tb + 1300, f"{ESTRANEO} dopo Z=0.4"),
           voce(tb + 1400, FORTE_T),                            # tutto gia' nel forte (z 0): niente di nuovo
           voce(tb + 600 + 3700, f"{LEGATO} troppo tardi Z=0.4"),
           voce(tb + 20000, f"{FORTE_T} e poi basta col medio Z={SOGLIA + 0.3:.3f}"),
           voce(tb + 20010, f"{LEGATO} dopo un medio Z=0.2")])
st = passo_finto()
assert st == "pronto", st
reg = {v["testo"]: v for v in FS.registro().values()}
e = {t: v["esito"] for t, v in reg.items()}
assert e[f"{LEGATO} prima Z=0.3"] == "trascinato" and e[f"{LEGATO} dopo Z=0.4"] == "trascinato", e
assert e[f"{ESTRANEO} prima Z=0.3"] == "scartato" and e[f"{ESTRANEO} dopo Z=0.4"] == "scartato", e   # tempo non basta
assert e[f"{LEGATO} con www.esempio.it Z=0.2"] == "scartato" and e[f"{LEGATO} troppo tardi Z=0.4"] == "scartato"
assert e[FORTE_T] == "scartato", "ridondante catturato"
assert e[f"{LEGATO} dopo un medio Z=0.2"] == "scartato"
forte = reg[f"{FORTE_T} Z={FORTE}"]
for t in (f"{LEGATO} prima Z=0.3", f"{LEGATO} dopo Z=0.4"):   # g ricalcolato a mano dalla risposta del servizio
    o = json.loads(urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:18132/sovrapposizione", json.dumps({"testo": t, "nid": forte["nid"]}).encode(),
        {"Content-Type": "application/json"})).read())
    q = o["presi"] / o["n"]
    forza = min(1, max(1 / 3, (FORTE - SOGLIA) / FS.FORZA_PIENA))
    assert q >= FS.QUOTA_MIN and o["presi"] < o["n"], o
    assert abs(reg[t]["cattura"] - round(FS.G_MIN + (1 - FS.G_MIN) * q * forza, 4)) < 1e-9 and reg[t]["da"] == forte["nid"]
w1, = nodi_con("le ho pulite stasera, e domani accendo il fuoco prima")
assert w1[2] == "trascinato" and w1[0] in nel_lux()
codice = f"""
import json, numpy as np, lux_engrammi as X, salienza as SA
ricordi = json.load(open(X.META))["ricordi"]
firme = {{int(k): r.get("firma") for k, r in ricordi.items()}}
g = ricordi["{w1[0]}"]["cattura"]
z = np.load(X.NPZ); st = np.load(X.STATO)
for n in ({w1[0]}, {forte["nid"]}):
    s0 = X.s0_ricordi(firme, SA.ranghi(z), [n])[n]
    k = z["A"][:, 0] == n
    print(n, s0, float(st["S0"][k].min()), float(st["S0"][k].max()), int(k.sum()), g)
"""
righe = subprocess.run([SPACY, "-c", codice], cwd=QUI, capture_output=True, text=True, check=True).stdout.split("\n")
_, attesa, lo, hi, n, g = righe[0].split()
assert int(n) > 0 and lo == hi and abs(float(lo) - float(g) * float(attesa)) < 1e-9, righe   # S0 x g
_, attesa, lo, hi, n, _ = righe[1].split()
assert int(n) > 0 and abs(float(lo) - float(attesa)) < 1e-9, righe                            # forte: S0 intera
try:
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18132/sovrapposizione",
                           json.dumps({"testo": "x", "nid": 99999999}).encode(), {"Content-Type": "application/json"}))
    assert False, "nid sconosciuto accettato"
except urllib.error.HTTPError as err:
    assert err.code == 400
sentinella(30)

# ---------- 6. coda corrotta ----------
print("6. righe rotte saltate e segnate", flush=True)
with open(FS.CODA, "ab") as fh:
    fh.write(b'{rotto\n5\n{"ts": 1}\nnull\n')
FS.accoda([voce(T0 + 200000, "B6dopo le rotte Z=0.1")])
assert passo_finto() == "pronto"
assert len(open(FS.ROTTE).readlines()) == 4
assert esiti()["B6dopo le rotte Z=0.1"] == "scartato"
with open(FS.CODA, "ab") as fh:   # riga a meta' (il riflesso sta scrivendo): non si tocca finche' non finisce
    fh.write(b'{"ts": 1, "autore": "x", "testo": "B6meta')
p = FS._pos()
assert passo_finto() == "pronto" and FS._pos() == p
with open(FS.CODA, "ab") as fh:
    fh.write(b' finita Z=0.1"}\n')
assert passo_finto() == "pronto" and FS._pos() == os.path.getsize(FS.CODA)
assert esiti()["B6meta finita Z=0.1"] == "scartato"

# ---------- 7. lettore diverso, server giu' ----------
print("7. altro modello e 35B spento: la coda aspetta", flush=True)
MODELLO[0] = "/altro/modello.gguf"
FS.accoda([voce(T0 + 210000, "B6attesa del lettore Z=0.2")])
p = FS._pos()
st = passo_finto()
assert st.startswith("in attesa") and "diverso" in st and FS._pos() == p, st
MODELLO[0] = FS.stats()["s"]["lettore"]
SRV.giu()
st = passo_finto()
assert st.startswith("in attesa") and FS._pos() == p, st
SRV.su()
st = passo_finto()
assert st == "pronto" and esiti()["B6attesa del lettore Z=0.2"] == "scartato", (st, FS._pos(), os.path.getsize(FS.CODA), open(FS.CODA,"rb").read()[-300:], [v for v in FS.registro().values() if "attesa" in v["testo"]])

# ---------- 8. firma vera dal finto server ----------
print("8. firma vera (firma_server sul finto), testo rifiutato dal lettore", flush=True)
FS.accoda([voce(T0 + 220000, "B6 RIFIUTA questo testo per favore"),
           voce(T0 + 220100, "B6vera una frase qualunque per la firma vera")])
assert FS.passo() == "pronto"
reg = {v["testo"]: v for v in FS.registro().values()}
assert reg["B6 RIFIUTA questo testo per favore"]["esito"] == "errore"
v = reg["B6vera una frase qualunque per la firma vera"]
f, sal, dom = firma_vera(FS.T.contesto_di([x["testo"] for x in FS._vivi(FS.registro(), v["ts"])]), v["testo"])
assert v["firma"] == f and v["salienza"] == sal and list(f) == ASSI
assert v["esito"] == ("nodo" if sal >= SOGLIA else "scartato"), (v["esito"], sal)
assert "B6dopo le rotte" in FS.T.contesto_di([x["testo"] for x in FS._vivi(FS.registro(), v["ts"])])   # contesto = 24 h prima
sentinella()

# ---------- 9. raffica di 200 dal servizio vero, 4 scrittori insieme ----------
print("9. raffica: 200 messaggi da 4 scrittori insieme", flush=True)
proc = servizio()
rng = np.random.default_rng(6)
zs = rng.choice([0.2, 0.8, 2.0], size=200, p=[0.6, 0.3, 0.1])   # 2.0: nodo ma non forte (niente trascinamenti)
t9 = T0 + 400000


def scrivi(k):
    for i in range(k, 200, 4):
        FS.accoda([voce(t9 + i * 7, f"B6raffica {i:03d} Z={zs[i]}")])


th = [threading.Thread(target=scrivi, args=(k,)) for k in range(4)]
t_inizio = time.time()
[t.start() for t in th]
[t.join() for t in th]
aspetta_vuota()
print(f"   200 messaggi elaborati in {time.time() - t_inizio:.1f} s", flush=True)
reg = [v for v in FS.registro().values() if v["testo"].startswith("B6raffica")]
assert len(reg) == 200, len(reg)
nodi = nodi_con("B6raffica")
assert len(nodi) == int((zs >= SOGLIA).sum()), (len(nodi), int((zs >= SOGLIA).sum()))
coda = [json.loads(r)["testo"] for r in open(FS.CODA, encoding="utf-8") if "B6raffica" in r]
giornata = [json.loads(r)["testo"] for r in open(FS.GIORNATA, encoding="utf-8") if "B6raffica" in r]
assert coda == giornata   # elaborati nell'ordine della coda
sentinella(30)

# ---------- 10. crash a meta' ----------
print("10. crash del servizio a meta' (kill -9) e ripartenza", flush=True)
proc.kill()
proc.wait()
proc = servizio(RITARDO="0.15")
t10 = T0 + 500000
p0 = os.path.getsize(FS.CODA)
FS.accoda([voce(t10 + i * 30, f"B6crash {i:02d} Z={FORTE if i % 5 == 0 else (2.0 if i % 3 == 0 else 0.3)}")
           for i in range(30)])
fine = time.time() + 60
while FS._pos() <= p0 + 200:   # qualche voce fatta, poi giu' a meta'
    assert time.time() < fine
    time.sleep(0.05)
time.sleep(0.3)
proc.send_signal(signal.SIGKILL)
proc.wait()
p = FS._pos()
assert 0 < p < os.path.getsize(FS.CODA), "il crash doveva cadere a meta' coda"
proc = servizio()
aspetta_vuota()
reg = [v for v in FS.registro().values() if v["testo"].startswith("B6crash")]
assert len(reg) == 30, len(reg)
testi = [n[1] for n in nodi_con("B6crash")]
assert len(testi) == len(set(testi))   # nessun doppione
attesi = {v["testo"] for v in reg if v["esito"] in ("nodo", "trascinato")}
assert set(testi) == attesi
sentinella(30)

# ---------- 11. 35B spento a meta', col servizio vero ----------
print("11. 35B spento con il servizio acceso: aspetta e riparte", flush=True)
SRV.giu()
FS.accoda([voce(T0 + 600000 + i, f"B6spento numero {i} Z=0.2") for i in range(10)])
time.sleep(2)
p = FS._pos()
assert p < os.path.getsize(FS.CODA)
SRV.su()
aspetta_vuota()
assert len([v for v in FS.registro().values() if v["testo"].startswith("B6spento")]) == 10

# ---------- 12. notturna e firma-subito insieme ----------
print("12. persistenza della notturna e firma-subito insieme (lucchetti)", flush=True)
proc.kill()
proc.wait()
proc = servizio(RITARDO="0.05")
FS.accoda([voce(T0 + 700000 + i * 10, f"B6insieme {i:02d} Z={2.0 if i % 2 else 0.2}") for i in range(40)])
ab = [FS.nodo({"testo": f"B6abitudine {i:02d} della notte", "firma": {a: 0.1 for a in ASSI}, "dominante": "joy",
              "ts": T0 + 700000 + i, "salienza": 0.1}, "abitudine") for i in range(20)]   # 1.20.0: come promuovi
aspetta_vuota()
assert len(set(ab)) == 20
assert len(nodi_con("B6insieme")) == 20
assert all(ricordi()[n]["fonte"] == "abitudine" for n in ab)
sentinella(30)   # nessuna scrittura persa: ogni nodo e' nel Lux

# ---------- 13. recupero notturno ----------
print("13. recupera: solo i mancanti, uscita 1 a servizio fermo, niente due volte", flush=True)
proc.kill()
proc.wait()
t13 = T0 + 770000
FS.accoda([voce(t13 - 5000, "B6dodici forzato Z=0.1", forzato=True)])   # passato dal servizio
proc = servizio()
aspetta_vuota()
proc.kill()
proc.wait()
FS.accoda([voce(t13, "B6pendente in coda Z=0.2"),    # in coda, non ancora elaborato (servizio fermo)
           voce(t13 + 1, "B6forzato pendente Z=0.1", forzato=True)])
J = f"{TMP}/notte.jsonl"
with open(J, "w") as fh:
    for m in [voce(T0 + 760000, "B6insieme 03 Z=2.0"),           # gia' nel registro (altro ts, stesse 24 ore)
              voce(t13 + 5, "B6pendente in coda Z=0.2"),          # gia' in coda
              voce(t13 + 10, "B6nuovo dalla notte Z=0.2"),
              voce(t13 + 12, "B6dodici forzato Z=0.1"),   # gia' passato
              voce(t13 + 14, "B6forzato pendente Z=0.1"),                # gia' in coda
              voce(t13 + 16, f"B6uno forte e felice Z={FORTE - 1.1:.2f}"),   # 09/11: la stessa del punto 1-4   # come un messaggio di 9 giorni fa: non e' un doppione
              voce(t13 + 20, "💭 **Reasoning:**\n```\npensieri\n```")]:   # vuoto dopo pulisci
        fh.write(json.dumps(m, ensure_ascii=False) + "\n")
FS.FERMA_MAX = 2
assert FS.recupera(J) == 1
nuove = [json.loads(r)["testo"] for r in open(FS.CODA, encoding="utf-8").readlines()[-4:]]
assert nuove == ["B6pendente in coda Z=0.2", "B6forzato pendente Z=0.1", "B6nuovo dalla notte Z=0.2",
                 f"B6uno forte e felice Z={FORTE - 1.1:.2f}"], nuove
n_prima = len(open(FS.CODA).readlines())
proc = servizio()
FS.FERMA_MAX = 60
assert FS.recupera(J) == 0
assert len(open(FS.CODA).readlines()) == n_prima   # niente due volte
assert esiti()["B6nuovo dalla notte Z=0.2"] == "scartato"
assert esito_a(t13 + 16) == "nodo"   # entrato e firmato: il dedup guarda solo le 24 ore prima
assert sum(v["testo"] == "B6dodici forzato Z=0.1" for v in FS.registro().values()) == 1

# ---------- 14. notte ----------
print("14. notte: persistenza solo sugli scartati, omeostato dai nodi", flush=True)
preso = {}
vera_notte, vero_imprimi = FS.persistenza.notte, FS.T.imprimi_omeostato
FS.persistenza.notte = lambda sc, promuovi=None: preso.update(sc=sc) or {
    "eco": 0, "ricordi_eco": 0, "temi": 0, "temi_nuovi": 0, "temi_dimenticati": 0, "promossi": []}
FS.T.imprimi_omeostato = lambda firme: preso.update(firme=firme)
FS.notte(tb)
FS.persistenza.notte, FS.T.imprimi_omeostato = vera_notte, vero_imprimi
reg = [v for v in FS.registro().values() if v["ts"] >= tb]
assert sorted(t for t, _, _ in preso["sc"]) == sorted(v["testo"] for v in reg if v["esito"] == "scartato"
                                                       and not FS.URL_RE.search(v["testo"]))
assert f"{LEGATO} con www.esempio.it Z=0.2" not in [t for t, _, _ in preso["sc"]]
assert f"{LEGATO} prima Z=0.3" not in [t for t, _, _ in preso["sc"]]   # trascinato: e' gia' un ricordo
assert f"{ESTRANEO} prima Z=0.3" in [t for t, _, _ in preso["sc"]]
assert len(preso["firme"]) == sum(v["esito"] in ("nodo", "trascinato") for v in reg)
assert all(list(f) == ASSI for _, f, _ in preso["sc"])

# ---------- 15. riflesso ----------
print("15. riflesso: righe solo per le risposte finali", flush=True)
proc.kill()
proc.wait()
codice = r"""
import json, os, sys
sys.path.insert(0, "/data/memoria-episodica-affettiva")
import riflesso as R
C = os.environ["CODA_FIRMA"]
def righe():
    r = [json.loads(x) for x in open(C)] if os.path.exists(C) else []
    if os.path.exists(C): os.remove(C)
    return r
fin = lambda t="Ciao l'utente, sto bene.": {"finish": "stop", "tool_calls": False, "testo": t}
R._accoda_firma("chat", "[utente] ciao l'agente, come stai oggi?", 100.0, fin())
r = righe()
assert [(x["autore"], x["testo"]) for x in r] == [("@utente:localhost", "ciao l'agente, come stai oggi?"),
                                                   ("@agente:localhost", "Ciao l'utente, sto bene.")], r
assert r[0]["ts"] == 100.0 and r[1]["ts"] > 100.0
R._accoda_firma("chat", "[utente] ciao", 1.0, {"finish": "tool_calls", "tool_calls": True, "testo": ""})
R._accoda_firma("chat", "[utente] ciao", 1.0, {"finish": "stop", "tool_calls": True, "testo": "x"})
R._accoda_firma("chat", "[utente] ciao", 1.0, {"finish": "length", "tool_calls": False, "testo": "x"})
R._accoda_firma("chat", "[IMPORTANT: usa la skill]", 1.0, fin())
R._accoda_firma("chat", "[CONTEXT COMPACTION] riassunto", 1.0, fin())
R._accoda_firma("chat", "Review the conversation above", 1.0, fin())
R._accoda_firma("chat", [{"type": "text", "text": "[utente] x"}], 1.0, fin())
R._accoda_firma("chat", "[utente]   ", 1.0, fin())
R._accoda_firma("altro", "[utente] ciao", 1.0, fin())
R._accoda_firma("chat", "[utente] ciao", 1.0, None)
assert righe() == []
R._accoda_firma("pensatoio", "[IMPORTANT: pensa]", 1.0, fin("Un pensiero mio."))
assert [x["testo"] for x in righe()] == ["Un pensiero mio."]
R._accoda_firma("chat", "[utente] dimmi", 1.0, fin("[OUT-OF-BAND] The user is asking"))
assert [x["autore"] for x in righe()] == ["@utente:localhost"]
R._accoda_firma("chat", "[utente] dimmi", 1.0, fin("   "))
assert [x["autore"] for x in righe()] == ["@utente:localhost"]
lungo = "parola " * 5000
R._accoda_firma("chat", "[utente] lungo", 1.0, fin(lungo))
assert righe()[1]["testo"] == lungo.strip()
src = open("/data/memoria-episodica-affettiva/riflesso.py").read()
i = src.index("_accoda_firma(flusso, ultimo, arrivo, self._esito)")
assert "try:" in src[i - 40:i] and "except Exception" in src[i:i + 120]   # un errore non tocca la risposta
j, k = src.index("ultimo = next("), src.index("ora = _ora_arrivo(d.get(\"messages\"")
assert j < k   # il messaggio dell'utente si prende prima dell'ora e dei metadati
print("riflesso ok")
"""
r = subprocess.run(["python3", "-c", codice], capture_output=True, text=True,
                   env=dict(os.environ, CODA_FIRMA=f"{TMP}/coda-riflesso.jsonl"))
assert r.returncode == 0 and "riflesso ok" in r.stdout, r.stdout + r.stderr

# ---------- 16. servizio del Lux 1.20.0 ----------
print("16. Lux 1.20.0: dedup, rifiuto, servizio giu', /ricordo e ricordi in /consegna", flush=True)


def post(rotta, corpo):
    r = urllib.request.Request("http://127.0.0.1:18132" + rotta, json.dumps(corpo).encode(),
                               {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120))


v16 = {"testo": "B6sedici il gatto rosso dorme sul davanzale della cucina al sole di novembre", "firma": f,
       "dominante": "joy", "ts": T0 + 800000, "salienza": 2.0}
n16 = FS.nodo(v16, "@utente:localhost")
assert FS.nodo(dict(v16, ts=T0 + 800500), "@utente:localhost") == n16   # stesso testo = stesso ricordo
for male in ({"testo": ""}, dict(v16, testo="B6sedici bis", firma="non un dict"), dict(v16, testo="B6sedici ter", classe="x")):
    try:
        post("/aggiungi", male)
        assert False, f"accettato: {male}"
    except urllib.error.HTTPError as err:
        assert err.code == 400
vero_lux = FS._lux
FS._lux = lambda rotta, corpo, attesa=30: (_ for _ in ()).throw(urllib.error.HTTPError(rotta, 400, "no", {}, None))
try:
    FS.nodo(dict(v16, testo="B6sedici rifiutato"), "@utente:localhost")
    assert False, "rifiuto del Lux non diventato ValueError"
except ValueError:
    pass
FS._lux = vero_lux
r16 = ricordi()[n16]
cod16 = r16["codice"]
d = post("/ricordo", {"codice": cod16})
assert d == {"nid": n16, "testo": v16["testo"], "dominante": "joy", "firma": f, "classe": "vissuto"}, d
assert post("/ricordo", {"codice": "zzzzinesistente"}) == {}
c16 = post("/consegna", {"testo": v16["testo"], "quanti": 1, "soglia": 0})
assert c16["ricordi"] and c16["ricordi"][0]["codice"] == c16["codici"][0], c16
x = c16["ricordi"][0]
assert x["nid"] == next(n for n, r in ricordi().items() if r["codice"] == x["codice"]) and "dominante" in x and "classe" in x
LUXSRV.kill()
LUXSRV.wait()
try:
    FS.nodo(dict(v16, testo="B6sedici con il Lux spento"), "@utente:localhost")
    assert False, "Lux spento: doveva aspettare"
except FS.Aspetta:
    pass

SRV.giu()
shutil.rmtree(TMP)
print("TUTTO VERDE")
