#!/usr/bin/env python3
"""Stress-test di B5 (PIANO-FIRMA-ENGRAMMI.md): vecchio Lux in archivio, persistenza e sincronia sul Lux degli engrammi.
Tutto su COPIE (Lux 1.13.0, memoria.db, vettori.pt, diario) e su un servizio del Lux di prova (porta 8133, LUX_DIR):
la produzione si legge e basta.
  servizio:     /richiama = Lux.richiama in processo; /rinforza a peso 1 e 0.5 = crescita FSRS attesa; errori (ricordo
                sconosciuto, peso fuori da (0, 1], NaN) = 400; ricordo corretto = non si rinforza
  persistenza:  eco vera (ricordo vero) rinforza a 0.5, tre eco nella stessa notte = un rinforzo; messaggio estraneo =
                tema; tema che torna a giorni alterni matura e diventa ricordo (tagging35b.persistenza_notte, su copia di
                memoria.db), poi entra nel Lux con S0 >= S_ABITUDINE (aggiungi) e la sentinella e' verde; settimanale
                matura; tema isolato dimenticato; migrazione dei 47 temi vecchi
  stress:       50 /rinforza in parallelo su 50 ricordi = 50 rinforzi giusti; 50 sullo stesso = uno solo; notte ripetuta
                (kill e rilancio) = nessuna crescita in piu'; servizio giu' = errore e buffer non salvato
  sincronia:    --dry sui diari veri; rinforzi dal diario di prova; ripasso = nessuna crescita in piu'; servizio giu' =
                errore e marcatore fermo; diario-riflessi ignorato
Uso: cd /data/memoria-episodica-affettiva/engrammi && /data/jspace/venv/bin/python test_persistenza_lux.py"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import lux as LUX  # noqa: E402
import memoria  # noqa: E402
import persistenza as P  # noqa: E402

QUI = "/data/memoria-episodica-affettiva/engrammi"
SPACY = "/data/venv-spacy/bin/python"
PORTA = 8133
URL = f"http://127.0.0.1:{PORTA}"
VERSIONE = "1.13.0"
fallimenti = []


def ok(cond, cosa):
    if not cond:
        fallimenti.append(cosa)
        print("  ROSSO:", cosa, flush=True)


def post(path, corpo, url=URL):
    r = urllib.request.Request(url + path, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120) as f:
            return f.status, json.load(f)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def stato(copia):
    z = np.load(f"{copia}/lux-stato.npz")
    return z["S"].copy(), z["S0"].copy(), z["U"].copy()


def archi(copia, nid):
    A = np.load(f"{copia}/lux.npz")["A"]
    return np.nonzero(A[:, 0] == nid)[0]


def atteso(S, U, js, oggi, peso):
    return np.asarray([LUX.cresci(float(s), float(LUX.curva(max(oggi - u, 0.0), s)), peso) for s, u in zip(S[js], U[js])])


tmp = tempfile.mkdtemp(prefix="test-b5-")
copia = f"{tmp}/lux-{VERSIONE}"
shutil.copytree(f"{QUI}/lux-{VERSIONE}", copia, ignore=shutil.ignore_patterns(".lucchetto"))
shutil.copy2(memoria.DB, f"{tmp}/memoria.db")
shutil.copy2(memoria.VEC, f"{tmp}/vettori.pt")
S, S0, U = stato(copia)
np.savez(f"{copia}/lux-stato.npz", S=S, S0=S0, U=U - 30)   # 30 giorni vissuti fa: un rinforzo deve crescere
OGGI = LUX.orologio()
orologio_vero = LUX.orologio
env = dict(os.environ, LUX_DIR=copia, LUX_PORTA=str(PORTA))
# un ricordo corretto, per vedere che non si rinforza (sulla copia, prima del servizio)
db = sqlite3.connect(f"file:{tmp}/memoria.db?mode=ro", uri=True)
testi = dict(db.execute("select id, testo from nodi where testo != '' and classe = 'vissuto'"))
db.close()
meta = json.load(open(f"{copia}/lux-meta.json"))
corretto = sorted(int(k) for k in meta["ricordi"])[5]
subprocess.run([SPACY, "-c", f"import lux_engrammi as X; X.correggi({meta['ricordi'][str(corretto)]['codice']!r}, "
                "'correzione di prova del test B5')"], cwd=QUI, env=env, check=True, capture_output=True)
servizio = subprocess.Popen([SPACY, "servizio_lux.py"], cwd=QUI, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{URL}/salute", timeout=2)
            break
        except OSError:
            time.sleep(1)
    print(f"servizio di prova su {PORTA}, copia in {tmp}, oggi vissuto {OGGI}", flush=True)
    P.SERVIZIO = URL
    P._file_temi = lambda: Path(tmp) / "temi-engrammi.npz"

    print("1. /richiama uguale al richiamo in processo; errori di /rinforza", flush=True)
    campione = [testi[n] for n in sorted(testi)[::80]]
    codice = ("import json, sys, lux_engrammi as X; L = X.Lux(); print(json.dumps([L.richiama(t, 3, soglia=0, "
              "ora=float('inf')) for t in json.load(sys.stdin)]))")
    inproc = json.loads(subprocess.run([SPACY, "-c", codice], cwd=QUI, env=env, input=json.dumps(campione),
                                       capture_output=True, text=True, check=True).stdout)
    for t, r in zip(campione, inproc):
        c, d = post("/richiama", {"testo": t, "quanti": 3})
        ok(c == 200 and [[int(a), round(b, 9)] for a, b in d["ricordi"]] == [[int(a), round(b, 9)] for a, b in r],
           f"/richiama diverso dal processo su «{t[:40]}»")
    ok(post("/richiama", {"testo": "", "quanti": 3}) == (200, {"ricordi": []}), "/richiama del testo vuoto")
    for corpo in ({"nid": 99999999, "peso": 1}, {"nid": 1, "peso": 0}, {"nid": 1, "peso": 2},
                  {"nid": 1, "peso": float("nan")}, {"nid": "x"}):
        c, d = post("/rinforza", corpo)
        ok(c in (400, 500) and "errore" in d, f"/rinforza {corpo} -> {c} {d}")
    S1, _, _ = stato(copia)
    ok(np.array_equal(S1, np.load(f"{copia}/lux-stato.npz")["S"]), "gli errori hanno scritto lo stato")
    js = archi(copia, corretto)
    c, d = post("/rinforza", {"nid": corretto, "peso": 1})
    ok(c == 200 and d == {"rinforzato": False} and np.array_equal(stato(copia)[0][js], S1[js]),
       f"ricordo corretto rinforzato: {d}")

    print("2. persistenza: eco vera, eco ripetuta, messaggio estraneo", flush=True)
    eco_nid = None
    for n in sorted(testi):
        if 120 <= len(testi[n]) <= 600 and n != corretto:
            c, d = post("/richiama", {"testo": testi[n], "quanti": 1})
            if d["ricordi"] and d["ricordi"][0][0] == n and d["ricordi"][0][1] >= P.SOGLIA_ECO:
                eco_nid = n
                break
    ok(eco_nid is not None, "nessun ricordo vero sopra la soglia d'eco con se stesso")
    js = archi(copia, eco_nid)
    Sp, _, Up = stato(copia)
    firma = {"joy": 0.4, "trust": 0.2, "sadness": -0.1}
    r = P.notte([(testi[eco_nid], firma, 1.0)] * 3, oggi=OGGI)
    Sd, _, Ud = stato(copia)
    ok(r["eco"] == 3 and r["ricordi_eco"] == 1 and r["temi_nuovi"] == 0, f"eco ripetuta: {r}")
    ok(np.allclose(Sd[js], atteso(Sp, Up, js, OGGI, P.PESO_ECO)) and (Ud[js] == OGGI).all(),
       "eco: crescita diversa da una sola crescita FSRS a peso 0.5")
    ok(np.array_equal(np.delete(Sd, js), np.delete(Sp, js)), "l'eco ha toccato altri ricordi")
    r = P.notte([(testi[eco_nid], firma, 1.0)], oggi=OGGI)   # notte rilanciata (kill a meta'): stesso giorno vissuto
    ok(np.array_equal(stato(copia)[0], Sd), "notte ripetuta: rinforzo contato due volte")
    estraneo = "Stanotte il pinguino imperatore ha attraversato il pack antartico trascinando una slitta di tonno."
    c, d = post("/richiama", {"testo": estraneo, "quanti": 1})
    ok(not d["ricordi"] or d["ricordi"][0][1] < P.SOGLIA_ECO, f"il messaggio estraneo fa eco: {d}")
    r = P.notte([(estraneo, firma, 2.0)], oggi=OGGI)
    ok(r["eco"] == 0 and r["temi_nuovi"] == 1 and r["temi"] == 1, f"estraneo: {r}")
    ok(np.array_equal(stato(copia)[0], Sd), "il messaggio estraneo ha rinforzato")

    print("3. abitudine: tema a giorni alterni -> ricordo (tagging35b) -> Lux con S0 >= S_ABITUDINE", flush=True)
    import tagging35b as TG
    import torch
    memoria.DB, memoria.VEC = Path(f"{tmp}/memoria.db"), Path(f"{tmp}/vettori.pt")
    cvec = np.load("/data/memoria-episodica-affettiva/emo-cvec-v2.npz")   # B7: solo per i nomi dei 51 assi
    emos = [str(x) for x in cvec["nomi"]]
    Z = torch.zeros(1, len(emos))
    Z[0, emos.index("joy")] = 0.9
    Z[0, emos.index("trust")] = 0.5
    ritorni = None
    for k, giorno in enumerate(range(OGGI + 1, OGGI + 61, 2)):
        validi = [{"testo": f"Stamattina sono passata al mercato di via Roma a prendere le arance ({giorno}).",
                   "ts": float(giorno)}]
        LUX.orologio = lambda g=giorno: g   # il tagger non passa oggi: la notte e' quella dell'orologio vissuto
        promossi = TG.persistenza_notte([0], validi, Z, emos)
        if promossi:
            ritorni = k + 1
            break
    LUX.orologio = orologio_vero
    ok(ritorni is not None, "il tema a giorni alterni non matura mai")
    nid_ab = promossi[0][1] if promossi else None
    db = sqlite3.connect(f"{tmp}/memoria.db")
    riga = db.execute("select fonte, classe, emo_tag, firma from nodi where id = ?", (nid_ab,)).fetchone()
    db.close()
    ok(riga is not None and riga[0] == "abitudine" and riga[1] == "vissuto" and riga[2] == "joy"
       and abs(json.loads(riga[3])["joy"] - 0.9) < 1e-3, f"nodo dell'abitudine: {riga}")
    v = torch.load(f"{tmp}/vettori.pt", weights_only=True)[nid_ab]["addr_sem"]
    ok(v.shape == (1024,) and abs(float(v.norm()) - 1) < 1e-3, f"addr_sem dell'abitudine {tuple(v.shape)}")
    ok(not any("mercato di via Roma" in t for t in P.Temi().testi), "il tema promosso resta nel buffer")
    n_a = len(np.load(f"{copia}/lux.npz")["A"])
    subprocess.run([SPACY, "-c", f"import taglia as T; T.DB = '{tmp}/memoria.db'; import lux_engrammi as X; X.aggiungi()"],
                   cwd=QUI, env=env, check=True, capture_output=True)
    S2, S02, U2 = stato(copia)
    js = archi(copia, nid_ab)
    ok(len(js) > 0 and (js >= n_a).all(), "l'abitudine non e' entrata nel Lux")
    ok((S02[js] >= P.S_ABITUDINE - 1e-9).all() and (S2[js] == S02[js]).all() and (U2[js] == OGGI).all(),
       f"S0 dell'abitudine {S02[js][:3]} sotto {P.S_ABITUDINE}")
    sent = subprocess.run([sys.executable, "sentinella_lux.py"], cwd=QUI, capture_output=True, text=True,
                          env=dict(env, MEMORIA_DB=f"{tmp}/memoria.db"))
    ok(sent.returncode == 0, f"sentinella sulla copia: {sent.stdout}")
    db = sqlite3.connect(f"{tmp}/memoria.db")
    db.execute("insert into nodi (ts, testo, fonte, emo_tag, emo_alpha, firma, salienza, classe, voluto) "
               "values (1, 'ricordo fuori dal Lux', '', 'joy', 0, '{}', 0, 'vissuto', 0)")
    db.commit()
    db.close()
    sent = subprocess.run([sys.executable, "sentinella_lux.py"], cwd=QUI, capture_output=True, text=True,
                          env=dict(env, MEMORIA_DB=f"{tmp}/memoria.db"))
    ok(sent.returncode == 1 and "CRITICO" in sent.stdout, f"sentinella non vede il ricordo mancante: {sent.stdout}")

    print("4. settimanale matura, tema isolato dimenticato", flush=True)
    settimane = None
    for k, giorno in enumerate(range(OGGI + 200, OGGI + 200 + 7 * 20, 7)):
        r = P.notte([(f"Domenica pranzo dalla nonna con i ravioli fatti in casa ({giorno}).", firma, float(giorno))],
                    oggi=giorno, promuovi=lambda *a: 1)
        if r["promossi"]:
            settimane = k + 1
            break
    ok(settimane is not None, "il settimanale non diventa mai abitudine")
    t0 = OGGI + 500
    P.notte([("Ho visto passare una mongolfiera gialla sopra la tangenziale.", firma, 3.0)], oggi=t0)
    giorni_oblio = int(np.ceil(P.S_ESPOSIZIONE * (P.R_RICONOSCIMENTO ** (1 / LUX.DECAY) - 1) / LUX.F_CURVA)) + 1
    r = P.notte([], oggi=t0 + giorni_oblio)
    ok(not any("mongolfiera" in t for t in P.Temi().testi) and r["temi_dimenticati"] >= 1, f"oblio del tema: {r}")

    print("5. stress: 50 /rinforza in parallelo", flush=True)
    nids = [n for n in sorted(int(k) for k in json.load(open(f"{copia}/lux-meta.json"))["ricordi"])
            if n not in (corretto, eco_nid, nid_ab) and n < 1_000_000][:50]
    Sp, _, Up = stato(copia)
    with ThreadPoolExecutor(50) as ex:
        esiti = list(ex.map(lambda n: post("/rinforza", {"nid": n, "peso": 1.0}), nids))
    Sd, _, Ud = stato(copia)
    ok(all(e == (200, {"rinforzato": True}) for e in esiti), f"risposte: {set(map(str, esiti))}")
    persi = [n for n in nids if not (np.allclose(Sd[archi(copia, n)], atteso(Sp, Up, archi(copia, n), OGGI, 1.0))
                                     and (Ud[archi(copia, n)] == OGGI).all())]
    ok(not persi, f"rinforzi persi o sbagliati: {persi[:10]}")
    stesso = nids[0]
    js = archi(copia, stesso)
    with ThreadPoolExecutor(50) as ex:
        list(ex.map(lambda _: post("/rinforza", {"nid": stesso, "peso": 1.0}), range(50)))
    ok(np.array_equal(stato(copia)[0][js], Sd[js]), "50 rinforzi dello stesso ricordo nello stesso giorno sono cresciuti")

    print("6. sincronizza-richiami", flush=True)
    sys.path.insert(0, "/data/memoria-episodica-affettiva")
    import importlib
    SR = importlib.import_module("sincronizza-richiami")
    dry = subprocess.run([sys.executable, "/data/memoria-episodica-affettiva/sincronizza-richiami.py", "--dry"],
                         capture_output=True, text=True)
    ok(dry.returncode == 0 and "DRY" in dry.stdout, f"--dry sui diari veri: {dry.stdout} {dry.stderr[-300:]}")
    SR.DIARIO, SR.MARCATORE, SR.SERVIZIO = Path(f"{tmp}/diario-richiami.jsonl"), Path(f"{tmp}/.marcatore"), URL
    nuovo = [n for n in sorted(int(k) for k in json.load(open(f"{copia}/lux-meta.json"))["ricordi"])
             if n not in nids and n not in (corretto, eco_nid, nid_ab) and n < 1_000_000][0]   # mai rinforzato oggi
    with open(SR.DIARIO, "w") as f:
        f.write('{"ts": 5.0, "risultati": [%d, %d]}\n' % (nuovo, nuovo))
        f.write("riga rotta\n")
        f.write('{"ts": 6.0, "risultati": [%d, %d, 99999999]}\n' % (nuovo, corretto))
        f.write('{"ts": 7.0, "modo": "id", "risultati": []}\n')
        f.write('{"ts": 0.5, "risultati": [%d]}\n' % nids[20])   # prima del marcatore: si salta
    with open(f"{tmp}/diario-riflessi.jsonl", "w") as f:   # il riflesso rinforza gia' alla consegna: si ignora
        f.write('{"ts": 8.0, "nid": [%d]}\n' % nids[21])
    SR.MARCATORE.write_text("1.0\n")
    Sp, _, Up = stato(copia)
    sys.argv = ["sincronizza-richiami.py"]
    SR.main()
    Sd, _, Ud = stato(copia)
    js = archi(copia, nuovo)
    ok(np.allclose(Sd[js], atteso(Sp, Up, js, OGGI, 1.0)) and (Ud[js] == OGGI).all(), "sincronia: ricordo non rinforzato")
    ok(float(SR.MARCATORE.read_text()) > 1.0, "marcatore non avanzato")
    toccati = set(np.nonzero(Sd != Sp)[0].tolist())
    ok(toccati == set(js.tolist()), f"la sincronia ha toccato archi di altri ricordi: {len(toccati - set(js.tolist()))}")
    SR.MARCATORE.write_text("1.0\n")   # notturna rilanciata dopo un kill: stesso diario, stesso giorno vissuto
    SR.main()
    ok(np.array_equal(stato(copia)[0], Sd), "sincronia ripetuta: rinforzo contato due volte")
    SR.MARCATORE.write_text("1.0\n")
    SR.SERVIZIO = "http://127.0.0.1:9"
    try:
        SR.main()
        ok(False, "servizio giu': nessun errore")
    except OSError:
        pass
    ok(SR.MARCATORE.read_text() == "1.0\n", "servizio giu': il marcatore e' avanzato")

    print("7. persistenza col servizio giu': errore e buffer fermo", flush=True)
    prima = open(P._file_temi(), "rb").read()
    P.SERVIZIO = "http://127.0.0.1:9"
    try:
        P.notte([("Un messaggio qualsiasi per la prova del servizio spento.", firma, 9.0)], oggi=OGGI + 900)
        ok(False, "persistenza col servizio giu': nessun errore")
    except OSError:
        pass
    ok(open(P._file_temi(), "rb").read() == prima, "servizio giu': il buffer dei temi e' cambiato")
    P.SERVIZIO = URL

    print("8. migrazione dei temi vecchi", flush=True)
    vecchio = "/data/workspace/memoria/temi-candidati.npz"
    if not os.path.exists(vecchio):
        vecchio = "/data/memoria-episodica-affettiva/archivio-firma-3110/temi-candidati.npz"
    os.remove(P._file_temi())
    n = P.migra(vecchio)
    z, t = np.load(vecchio), P.Temi()
    ok(n == len(z["testi"]) == len(t.testi) and t.centri.shape == (n, 1024), f"migrati {n}")
    ok(np.allclose(np.linalg.norm(t.centri, axis=1), 1, atol=2e-3), "centri non unitari")
    ok(all(len(f) == 51 for f in t.firme) and np.array_equal(t.stab, z["stab"]) and t.giorni == [json.loads(x) for x in z["giorni"]],
       "firme, stabilita' o giorni cambiati")
finally:
    servizio.terminate()
    servizio.wait()
    shutil.rmtree(tmp, ignore_errors=True)

print("TUTTO VERDE" if not fallimenti else f"ROSSO: {len(fallimenti)} fallimenti")
sys.exit(1 if fallimenti else 0)
