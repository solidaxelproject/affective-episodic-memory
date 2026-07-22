#!/usr/bin/env python3
# Dashboard web di `notturna -status` (22/07): niente
# sfarfallio, la pagina resta ferma e il JS aggiorna solo i valori.
# Pulsanti: ferma/riavvia pensatoio (il riavvio è un gesto umano, mai di
# automatismi) + manovre cache KV tra VRAM (slot 0),
# RAM (/dev/shm/agente-kv) e SSD (kv-slots). Guardie: nessuna operazione sullo
# slot con un turno in volo; conferma esplicita lato pagina per la VRAM.
# Solo stdlib. Uso: notturna -web [porta]   (default 8095, solo 127.0.0.1)
import datetime
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

MARKER = "/data/memoria-episodica-affettiva/.ultimo-consolidamento"
LOG = "/data/memoria-episodica-affettiva/gradino4/distilla.log"
GRIGLIE = "/data/workspace/memoria/griglie"
KV_RAM = "/dev/shm/agente-kv"
KV_SSD = "/data/workspace/kv-slots"
KV_FILES = ("chat.kv", "pensatoio.kv")
KV_BYTES_TOK = 22900          # ~22,9 KB/token misurati (640MB / 28k tok)
CTX_DEFAULT = 143360
FREEZE = "/usr/local/bin/pensatoio-freeze"
NOTTURNA = "/usr/local/bin/notturna"
DORMI_FLAG = "/data/workspace/memoria/.dormi-richiesto"
AZLOG = "/data/memoria-episodica-affettiva/notturna-web-azioni.log"
MEMDB = "/data/workspace/memoria/memoria.db"
STATO_AVVISO = "~/.local/state/motore-autonomia.ultimo-avviso-stanchezza"
GRIGLIE_MAX_FILE = "/data/memoria-episodica-affettiva/.griglie-max"
ARMATA_FILE = "/data/memoria-episodica-affettiva/.notturna-armata"
CE_STORIA = "/data/memoria-episodica-affettiva/.ce-storia.json"
PENS_KV = "/dev/shm/agente-kv/pensatoio.kv"
LLAMA = "http://127.0.0.1:8090"


def _pgrep(pat):
    return subprocess.run(["pgrep", "-f", pat], capture_output=True).returncode == 0


def _slots():
    try:
        return json.load(urlopen(LLAMA + "/slots", timeout=1))
    except Exception:
        return None


def _griglie(marker_dt):
    store = 0
    if os.path.isdir(GRIGLIE):
        store = len([f for f in os.listdir(GRIGLIE) if re.fullmatch(r"\d+\.npy", f)])
    righe, agg, sca = [], 0, 0
    try:
        with open(LOG, errors="replace") as fh:
            for line in fh:
                if line[:19] < marker_dt:
                    continue
                m = re.match(
                    r"^[\d-]+ (\d\d:\d\d)[\d:,.]* nodo (\d+): loss ([\d.]+), "
                    r"OUTPUT-match ([\d.]+%), (\d+)s -> "
                    r"(NUOVA agganciata|nuova SCARTATA\S*)", line)
                if not m:
                    continue
                ok = m.group(6).startswith("NUOVA")
                agg, sca = agg + ok, sca + (not ok)
                righe.append({"ora": m.group(1), "nodo": m.group(2),
                              "loss": m.group(3), "match": m.group(4),
                              "sec": m.group(5), "ok": ok})
    except OSError:
        pass
    return {"store": store, "righe": righe[-12:], "agganciate": agg,
            "scartate": sca, "in_corso": _pgrep("distilla-ricordo.py")}


def _codec():
    try:
        lines = open(LOG, errors="replace").read().splitlines()
    except OSError:
        return {"run": None}
    start = None
    for i, line in enumerate(lines):
        if re.search(r"codec: \d+ parametri", line):
            start = i
    if start is None:
        return {"run": None}
    run = lines[start:]
    m = re.search(r"^([\d-]+ \d\d:\d\d)", run[0])
    params = re.search(r"(\d+) parametri", run[0])
    if _pgrep("codec-lux.py"):
        stato, dett = "training", "in corso"
    elif any("CODEC-COMPLETO" in r for r in run):
        stato = "completo"
        s = [r for r in run if "CODEC-SALVATO" in r]
        mm = re.search(r"epoca \d+, CE held-out [\d.]+", s[-1]) if s else None
        dett = mm.group(0) if mm else ""
    else:
        stato, dett = "interrotto", "nessun CODEC-COMPLETO"
    epoche = []
    for r in run:
        mm = re.search(r"epoca +(\d+): CE train ([\d.]+) \| CE held-out ([\d.]+)", r)
        if mm:
            epoche.append({"n": mm.group(1), "train": mm.group(2), "held": mm.group(3)})
    best = None
    for r in run:
        if "checkpoint su disco" in r:
            mm = re.search(r"epoca \d+, CE held-out [\d.]+", r)
            best = mm.group(0) if mm else None
    return {"run": m.group(1) if m else "?", "parametri": params.group(1) if params else "?",
            "stato": stato, "dettaglio": dett, "epoche": epoche[-12:], "best": best}


def _tier(base):
    out = []
    for nome in KV_FILES:
        p = os.path.join(base, nome)
        if os.path.isfile(p):
            st = os.stat(p)
            out.append({"nome": nome, "tok": st.st_size // KV_BYTES_TOK,
                        "salvato": time.strftime("%d/%m %H:%M", time.localtime(st.st_mtime))})
    return out


def _sistema():
    npast, ctx, su, busy = None, CTX_DEFAULT, False, False
    slots = _slots()
    if slots is not None:
        su = True
        if slots:
            npast = slots[0].get("n_past", 0)
            ctx = slots[0].get("n_ctx", ctx)
            busy = bool(slots[0].get("is_processing"))
    out = subprocess.run(
        ["journalctl", "--user", "-u", "llama-35b.service", "-n", "400",
         "--no-pager", "-o", "cat"], capture_output=True, text=True).stdout
    ult = re.findall(r"stop processing: n_tokens = (\d+)", out)
    mot = subprocess.run(["systemctl", "--user", "is-active", "motore-autonomia.service"],
                         capture_output=True, text=True).stdout.strip()
    mk = os.path.getmtime(MARKER) if os.path.exists(MARKER) else 0
    return {"ctx": ctx, "su": su, "busy": busy, "slot_vivo": npast,
            "ultimo_turno": int(ult[-1]) if ult else None,
            "kv_ram": _tier(KV_RAM), "kv_ssd": _tier(KV_SSD),
            "riflesso": _pgrep("riflesso.py"),
            "pensatoio": mot == "active",
            "ultima_notturna": time.strftime("%d/%m %H:%M", time.localtime(mk)) if mk else "mai",
            "prossima": ("adesso" if mk + 21600 <= time.time()
                         else time.strftime("%d/%m %H:%M", time.localtime(mk + 21600))),
            "notturna_in_corso": _pgrep("notte-memoria.sh|notte-distilla.sh|distilla-ricordo.py|codec-lux.py")}


def _gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,"
             "temperature.gpu,power.draw,power.limit,fan.speed",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2).stdout.strip().splitlines()[0]
        u, mu, mt, t, pw, pl, fan = [x.strip() for x in out.split(",")]
        return {"util": int(u), "mem_used": int(mu), "mem_tot": int(mt),
                "temp": int(t), "power": float(pw), "plimit": float(pl), "fan": int(fan)}
    except Exception:
        return None


def _storico():
    """Per giorno: miglior (minima) CE held-out dal log + ricordi cumulativi."""
    ce = {}
    try:
        for line in open(LOG, errors="replace"):
            m = re.match(r"^(\d{4}-\d\d-\d\d).*CE held-out ([\d.]+)", line)
            if m:
                d, v = m.group(1), float(m.group(2))
                if d not in ce or v < ce[d]:
                    ce[d] = v
    except OSError:
        pass
    # notte-distilla TRONCA il log a ogni run (scoperto 22/07): i minimi
    # giornalieri si accumulano qui, così la storia sopravvive alle rotazioni
    try:
        storia = json.load(open(CE_STORIA))
    except (OSError, ValueError):
        storia = {}
    cambiato = False
    for d, v in ce.items():
        if d not in storia or v < storia[d]:
            storia[d] = v
            cambiato = True
    if cambiato:
        with open(CE_STORIA, "w") as fh:
            json.dump(storia, fh)
    ce = storia
    ric = {}
    try:
        c = sqlite3.connect("file:" + MEMDB + "?mode=ro", uri=True)
        tot = 0
        for d, n in c.execute(
                "SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') g,"
                " COUNT(*) FROM nodi GROUP BY g ORDER BY g"):
            tot += n
            ric[d] = tot
        c.close()
    except Exception:
        pass
    giorni = sorted(set(ce) | set(ric))
    if not giorni:
        return []
    out, cur = [], 0
    d = datetime.date.fromisoformat(giorni[0])
    oggi = datetime.date.today()
    while d <= oggi:
        k = d.isoformat()
        if k in ric:
            cur = ric[k]
        out.append({"g": k, "ce": ce.get(k), "ricordi": cur})
        d += datetime.timedelta(days=1)
    return out


def _griglie_max():
    try:
        return max(0, min(32, int(open(GRIGLIE_MAX_FILE).read().strip())))
    except (OSError, ValueError):
        return 16


def dati():
    mk = os.path.getmtime(MARKER) if os.path.exists(MARKER) else 0
    marker_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mk))
    avviso = os.path.getmtime(STATO_AVVISO) if os.path.exists(STATO_AVVISO) else 0
    return {"ora": time.strftime("%H:%M:%S"),
            "ore_da_notturna": round((time.time() - mk) / 3600, 1) if mk else None,
            "avviso_stanchezza": avviso > mk,
            "notturna_armata": os.path.exists(ARMATA_FILE),
            "griglie_max": _griglie_max(),
            "gpu": _gpu(), "storico": _storico(),
            "griglie": _griglie(marker_dt), "codec": _codec(), "sistema": _sistema()}


# ---------------- azioni (POST /azione) ----------------

def _slot_op(azione, nomefile=None):
    corpo = json.dumps({"filename": nomefile}).encode() if nomefile else b"{}"
    req = urllib.request.Request(
        f"{LLAMA}/slots/0?action={azione}", data=corpo,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=120) as r:
            return r.status == 200, ""
    except Exception as e:
        return False, str(e)


def _guardia_slot():
    """None se lo slot è libero, altrimenti il motivo del rifiuto."""
    slots = _slots()
    if slots is None:
        return "35B giù: agente dorme, la VRAM non c'è"
    if slots and slots[0].get("is_processing"):
        return "slot occupato: turno in volo, riprova a slot libero"
    return None


def _copia(src, dst, nome):
    tmp = os.path.join(dst, nome + ".tmp")
    shutil.copy2(os.path.join(src, nome), tmp)
    os.replace(tmp, os.path.join(dst, nome))


def _lancia_notturna(motivo):
    with open(AZLOG, "a") as fh:
        fh.write(f"{time.strftime('%F %T')} avvia notturna ({motivo})\n")
        fh.flush()
        p = subprocess.Popen([NOTTURNA], stdout=fh, stderr=fh, start_new_session=True)
    try:
        p.wait(timeout=3)
        return True, open(AZLOG).read().splitlines()[-1]
    except subprocess.TimeoutExpired:
        return True, "notturna avviata: lavora in sottofondo (segui Griglie/Codec)"


def _watcher_eos():
    """Notturna armata: scatta al prossimo salvataggio di pensatoio.kv
    (= fine stream nel pensatoio). Sopravvive ai riavvii del server:
    lo stato vive nel file .notturna-armata."""
    while True:
        time.sleep(2)
        try:
            base = float(open(ARMATA_FILE).read().strip())
        except (OSError, ValueError):
            continue
        m = os.path.getmtime(PENS_KV) if os.path.exists(PENS_KV) else 0
        if m > base:
            try:
                os.remove(ARMATA_FILE)
            except OSError:
                pass
            _lancia_notturna("EOS nel pensatoio")


def azione(op, nome):
    if op == "pensatoio_stop":
        r = subprocess.run([FREEZE, "-on"], capture_output=True, text=True)
        return (r.returncode == 0,
                "pensatoio congelato ❄" if r.returncode == 0 else r.stderr.strip() or "pensatoio-freeze fallito")
    if op == "pensatoio_start":
        # scatta SOLO dal click umano sulla dashboard, mai da automatismi.
        r = subprocess.run([FREEZE, "-off"], capture_output=True, text=True)
        return (r.returncode == 0,
                "pensatoio riavviato ▶" if r.returncode == 0
                else r.stderr.strip() or r.stdout.strip() or "pensatoio-freeze fallito")
    if op == "pisolino":
        with open(DORMI_FLAG, "a"):
            pass
        os.utime(DORMI_FLAG)
        return True, "pisolino richiesto 😴 (sveglia rapida, giorno non consolidato)"
    if op == "notturna_avvia":
        # 22/07: il click NON parte subito, ARMA la notturna:
        # scatta al prossimo EOS nel pensatoio, cioè al prossimo salvataggio
        # di pensatoio.kv in RAM (il riflesso lo fa a fine di ogni stream).
        # Pensatoio congelato = nessun EOS in arrivo: si parte subito.
        # Secondo click a notturna armata = disarmo.
        if os.path.exists(ARMATA_FILE):
            os.remove(ARMATA_FILE)
            return True, "notturna disarmata"
        mot = subprocess.run(["systemctl", "--user", "is-active", "motore-autonomia.service"],
                             capture_output=True, text=True).stdout.strip()
        if mot != "active":
            return _lancia_notturna("pensatoio congelato: nessun EOS in arrivo, parto subito")
        base = os.path.getmtime(PENS_KV) if os.path.exists(PENS_KV) else 0
        with open(ARMATA_FILE, "w") as fh:
            fh.write(str(base))
        return True, "notturna armata: parte quando l'agente chiude il pensiero (prossimo EOS nel pensatoio)"
    if op == "slot_erase":
        no = _guardia_slot()
        if no:
            return False, no
        ok, err = _slot_op("erase")
        return ok, "slot svuotato: VRAM del contesto liberata" if ok else err
    if op == "griglie_max":
        try:
            v = max(0, min(32, int(nome)))
        except ValueError:
            return False, "valore non valido"
        with open(GRIGLIE_MAX_FILE, "w") as fh:
            fh.write(str(v))
        return True, f"prossima notte: al massimo {v} griglie"
    if nome not in KV_FILES:
        return False, "file non ammesso"
    if op in ("vram_ram", "ram_vram", "vram_ssd", "ssd_vram"):
        no = _guardia_slot()
        if no:
            return False, no
    try:
        if op == "vram_ram":
            ok, err = _slot_op("save", nome)
            return ok, f"slot salvato in RAM ({nome})" if ok else err
        if op == "ram_vram":
            ok, err = _slot_op("restore", nome)
            return ok, f"{nome} ripristinato dalla RAM allo slot" if ok else err
        if op == "vram_ssd":
            ok, err = _slot_op("save", nome)
            if not ok:
                return False, err
            _copia(KV_RAM, KV_SSD, nome)
            return True, f"slot salvato in RAM e consolidato su SSD ({nome})"
        if op == "ssd_vram":
            _copia(KV_SSD, KV_RAM, nome)
            ok, err = _slot_op("restore", nome)
            return ok, f"{nome} ripristinato da SSD allo slot" if ok else err
        if op == "ram_ssd":
            _copia(KV_RAM, KV_SSD, nome)
            return True, f"{nome} consolidato su SSD"
        if op == "ssd_ram":
            _copia(KV_SSD, KV_RAM, nome)
            return True, f"{nome} riportato da SSD in RAM"
    except OSError as e:
        return False, str(e)
    return False, "operazione sconosciuta"


PAGINA = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🌙 Notturna</title>
<style>
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1a202c; --ink2:#5a6472; --muted:#8a93a0;
  --bordo:#e3e6ea; --ok:#1a7f37; --warn:#9a6700; --err:#c1341b; --accent:#4441d0;
  --barra-fondo:#eceef1; --btn:#f0f1f4; --btn-bordo:#d5d9de;
  --ric:#0e7a86; --ok-soft:#cfe8d2;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#14161a; --card:#1d2025; --ink:#e8eaed; --ink2:#a6adb6; --muted:#767e88;
  --bordo:#2b2f36; --ok:#57ab5a; --warn:#c69026; --err:#e5654e; --accent:#8b88f8;
  --barra-fondo:#2b2f36; --btn:#262a31; --btn-bordo:#3a3f48;
  --ric:#4cc4d4; --ok-soft:#23432a;
}}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif;padding:20px}
header{display:flex;align-items:baseline;gap:10px;max-width:1060px;margin:0 auto 16px}
header h1{font-size:19px;font-weight:650}
header .ora{color:var(--muted);font-variant-numeric:tabular-nums}
main{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));max-width:1060px;margin:0 auto}
section{background:var(--card);border:1px solid var(--bordo);border-radius:10px;padding:16px 18px}
h2{font-size:12px;font-weight:650;letter-spacing:.08em;color:var(--ink2);text-transform:uppercase;margin-bottom:12px}
.riga{display:flex;justify-content:space-between;gap:8px;padding:3px 0}
.riga .k{color:var(--ink2)}
.num{font-variant-numeric:tabular-nums}
.stato-ok{color:var(--ok)} .stato-warn{color:var(--warn)} .stato-err{color:var(--err)}
.chip{font-weight:600}
.metro{margin:8px 0}
.metro .sopra{display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px}
.metro .sopra .k{color:var(--ink2)} .metro .sopra .v{color:var(--ink);font-variant-numeric:tabular-nums}
.metro .nota{font-size:11.5px;color:var(--muted)}
.barra{height:8px;border-radius:4px;background:var(--barra-fondo);overflow:hidden}
.barra i{display:block;height:100%;border-radius:4px;background:var(--ok);transition:width .6s ease, background .6s}
table{width:100%;border-collapse:collapse;font:12.5px/1.5 ui-monospace,monospace;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--muted);font-weight:500;padding:1px 8px 3px 0}
td{padding:1px 8px 1px 0;color:var(--ink2)} td:first-child,th:first-child{padding-left:0}
td.ok{color:var(--ok)} td.err{color:var(--err)}
.grande{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}
.grande small{font-size:13px;font-weight:400;color:var(--ink2);margin-left:6px}
.vuoto{color:var(--muted);font-style:italic}
button{background:var(--btn);border:1px solid var(--btn-bordo);color:var(--ink);
  border-radius:7px;padding:5px 10px;font:12.5px system-ui;cursor:pointer}
button:hover{border-color:var(--accent)}
button:disabled{opacity:.45;cursor:default}
.bottoni{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.kv-titolo{font-weight:600;margin-top:10px}
.kv-tempi{font-size:11.5px;color:var(--muted);margin-bottom:4px}
#esito{min-height:1.3em;font-size:13px;margin-top:8px}
.avviso{font-size:11.5px;color:var(--muted);margin-top:8px}
.btn-verde{border-color:var(--ok);color:var(--ok);font-weight:600}
.btn-viola{border-color:var(--accent);color:var(--accent);font-weight:600}
.info{position:relative;cursor:help;color:var(--accent);font-style:normal;font-size:12px}
.info::after{content:attr(data-tip);position:absolute;left:50%;transform:translateX(-50%);
  bottom:135%;width:240px;background:var(--card);color:var(--ink);border:1px solid var(--bordo);
  border-radius:8px;padding:8px 10px;font:12px/1.45 system-ui;box-shadow:0 4px 14px rgba(0,0,0,.2);
  opacity:0;pointer-events:none;transition:opacity .15s;z-index:5;
  text-transform:none;letter-spacing:normal;font-weight:400}
.info:hover::after{opacity:1}
.btn-cache{border-color:var(--ok);color:var(--ok);font-weight:600;min-width:108px;text-align:left}
input[type=range]{width:100%;accent-color:var(--ok);cursor:pointer}
.largo{grid-column:1/-1}
footer{max-width:1060px;margin:14px auto 0;color:var(--muted);font-size:12px}
</style></head><body>
<header><h1>🌙 Notturna</h1><span class="ora" id="ora">…</span>
<span class="ora" id="h-notturna"></span>
<span class="chip stato-warn" id="notturna-chip"></span></header>
<main>
<section><h2>Sistema</h2>
  <div class="riga"><span class="k">35B <i class="info" data-tip="35 miliardi di parametri: il modello che fa girare l'agente (Qwen3.6-35B, quantizzato Q8_0).">ⓘ</i> (:8090)</span><span id="s-35b">…</span></div>
  <div class="riga"><span class="k">slot</span><span id="s-busy">…</span></div>
  <div class="riga"><span class="k">riflesso (:8091)</span><span id="s-rifl">…</span></div>
  <div class="riga"><span class="k">pensatoio</span><span id="s-pens">…</span></div>
  <div class="bottoni">
    <button id="btn-pens-on" onclick="fai('pensatoio_start','')">▶ riavvia pensatoio</button>
    <button id="btn-pens" onclick="fai('pensatoio_stop','')">❄ ferma pensatoio</button>
  </div>
</section>
<section><h2>Riposo</h2>
  <div class="riga"><span class="k">ultima notturna</span><span class="num" id="r-ultima">…</span></div>
  <div class="riga"><span class="k">prossima possibile</span><span class="num" id="r-prossima">…</span></div>
  <div class="bottoni">
    <button id="btn-notturna" onclick="notturnaClick()">🌙 avvia notturna</button>
    <button onclick="fai_conf('pisolino','Chiedo il pisolino? Sveglia rapida, il giorno NON viene consolidato.')">😴 pisolino</button>
  </div>
  <div class="avviso">la notturna ha le sue guardie: non parte se ne è passata una da meno di 6 ore o se una è già in corso</div>
</section>
<section><h2>Context window <i class="info" data-tip="CW, Context Window: la memoria di lavoro del modello, quanti token può tenere davanti a sé in questo momento. ctx = la sua capienza massima. Un token ≈ 3-4 caratteri di testo.">ⓘ</i> <span class="num" id="cw-ctx"></span></h2>
  <div id="cw-metri"></div>
</section>
<section><h2>Cache KV <i class="info" data-tip="KV, Key-Value cache: lo stato interno già calcolato della conversazione. Salvarlo e ripristinarlo evita di rileggere tutto il contesto da capo.">ⓘ</i> · manovre</h2>
  <div class="avviso" style="margin:0 0 6px">
    VRAM <i class="info" data-tip="La memoria della scheda video: lo slot vivo, quello su cui il modello lavora adesso.">ⓘ</i> ·
    RAM <i class="info" data-tip="La memoria di sistema (/dev/shm): copia velocissima, salvata a ogni risposta, ma sparisce allo spegnimento.">ⓘ</i> ·
    SSD <i class="info" data-tip="Il disco: copia persistente, sopravvive a riavvii e blackout. Consolidata ogni 5 messaggi.">ⓘ</i>
  </div>
  <div class="bottoni">
    <button onclick="fai_conf('slot_erase','Svuoto lo slot dal server (evict)? Quello che c\'è in VRAM va perso se non è salvato in RAM o SSD.')">🗑 svuota slot (evict)</button>
  </div>
  <div id="kv-manovre"></div>
  <div id="esito"></div>
  <div class="avviso">⚠ le mosse che toccano lo slot (VRAM) chiedono conferma: il server
  non sa quale flusso è nello slot in questo momento, lo sai tu. Rifiutate da sole se un
  turno è in volo.</div>
</section>
<section><h2>GPU <i class="info" data-tip="I valori di nvidia-smi sulla RTX 5060 Ti: uso del processore grafico, VRAM occupata, temperatura, potenza assorbita e ventola.">ⓘ</i></h2>
  <div id="gpu-metri"><span class="vuoto">nvidia-smi non disponibile</span></div>
</section>
<section><h2>Griglie</h2>
  <div class="grande"><span id="g-store">…</span><small>nello store</small></div>
  <div class="riga" style="margin-top:6px"><span class="k">griglie prossima notte
    <i class="info" data-tip="Quante griglie al massimo verranno distillate nella prossima notturna (parametro --max di notte-distilla). Si regola col cursore, anche con la rotella del mouse.">ⓘ</i></span>
    <span class="num chip" id="gmax-val">…</span></div>
  <input type="range" id="gmax" min="0" max="32" step="1">
  <div class="riga"><span class="k">ultimo ciclo</span>
    <span><span class="stato-ok num" id="g-agg">0 agganciate</span> ·
          <span class="num" id="g-sca">0 scartate</span></span></div>
  <div id="g-corso"></div>
  <table id="g-tab"></table>
</section>
<section><h2>Codec</h2>
  <div class="riga"><span class="k">run</span><span class="num" id="c-run">…</span></div>
  <div class="riga"><span class="k">stato</span><span class="chip" id="c-stato">…</span></div>
  <div class="riga"><span class="k">miglior checkpoint <i class="info" data-tip="Il salvataggio del codec con l'errore più basso sugli esempi mai visti in addestramento: è la versione che verrà usata.">ⓘ</i></span><span class="num stato-ok" id="c-best">…</span></div>
  <table id="c-tab"></table>
</section>
<section class="largo"><h2>Storia <i class="info" data-tip="Per ogni giorno: il miglior CE held-out raggiunto dal codec (più basso = ricostruisce meglio) e quanti ricordi vivono nel grafo.">ⓘ</i></h2>
  <div id="grafico"><span class="vuoto">nessun dato</span></div>
  <div class="avviso"><span style="color:var(--accent)">●</span> miglior CE held-out del giorno, scala sinistra ·
    <span style="color:var(--ric)">●</span> ricordi nel grafo, scala destra</div>
</section>
</main>
<footer>aggiornamento automatico ogni 3 secondi, si muovono solo i valori</footer>
<script>
const $=id=>document.getElementById(id);
const stato=(el,ok,tOk,tErr)=>{el.textContent=(ok?"● ":"○ ")+(ok?tOk:tErr);
  el.className=ok?"stato-ok":"stato-err";};
function metro(m,ctx){
  const pct=Math.round(100*m.tok/ctx);
  const col=pct>=80?"var(--err)":pct>=50?"var(--warn)":"var(--ok)";
  return `<div class="metro"><div class="sopra"><span class="k">${m.nome}</span>`+
    `<span class="v">${pct}% · ${m.tok.toLocaleString("it")} tok</span></div>`+
    `<div class="barra"><i style="width:${pct}%;background:${col}"></i></div>`+
    (m.nota?`<div class="nota">${m.nota}</div>`:"")+`</div>`;
}
const CONFERME={vram_ram:"Salvo lo SLOT VIVO in RAM come «F»? Sovrascrive la copia RAM: sicura che nello slot ci sia proprio F?",
  ram_vram:"Ripristino «F» dalla RAM allo SLOT? Quello che c'è ora nello slot va perso se non è salvato.",
  vram_ssd:"Salvo lo SLOT VIVO come «F» e consolido su SSD? Sovrascrive RAM e SSD: sicura che nello slot ci sia proprio F?",
  ssd_vram:"Riporto «F» da SSD in RAM e lo ripristino nello SLOT? Sovrascrive la copia RAM (che può essere più fresca) e quello che c'è nello slot.",
  ssd_ram:"Riporto «F» da SSD in RAM? La copia RAM (che può essere più fresca) viene sovrascritta."};
async function fai(op,nome){
  const c=CONFERME[op]; if(c && !confirm(c.replaceAll("F",nome))) return;
  $("esito").textContent="… in corso ("+op.replace("_"," → ")+" "+(nome||"")+")";
  $("esito").className="";
  try{
    const r=await (await fetch("azione",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({op,nome})})).json();
    $("esito").textContent=(r.ok?"✔ ":"✘ ")+r.msg;
    $("esito").className=r.ok?"stato-ok":"stato-err";
  }catch(e){ $("esito").textContent="✘ "+e; $("esito").className="stato-err"; }
  giro();
}
function fai_conf(op,txt){ if(confirm(txt)) fai(op,""); }
let armata=false;
function notturnaClick(){
  if(armata){ fai("notturna_avvia",""); return; }   // disarmo: niente popup
  fai_conf("notturna_avvia","Armo la notturna? Parte quando l'agente chiude il pensiero in corso (prossimo EOS nel pensatoio). Se il pensatoio è congelato parte subito.");
}
function manovre(s){
  const t=(lista,nome)=>{const x=lista.find(e=>e.nome===nome);
    return x?`${x.tok.toLocaleString("it")} tok · ${x.salvato}`:"assente";};
  const tok=(lista,nome)=>{const x=lista.find(e=>e.nome===nome);return x?x.tok:0;};
  // ogni pulsante è anche una barra: il riempimento verde = token nella
  // cache SORGENTE della mossa, rapportati al ctx
  const btn=(op,f,label,srcTok)=>{
    const pct=Math.min(100,Math.round(100*srcTok/s.ctx));
    return `<button class="btn-cache" title="${srcTok.toLocaleString("it")} tok nella sorgente"
      style="background:linear-gradient(90deg,var(--ok-soft) ${pct}%,var(--btn) ${pct}%)"
      onclick="fai('${op}','${f}')">${label}</button>`;};
  return ["chat.kv","pensatoio.kv"].map(f=>{
    const vr=s.slot_vivo||0, ra=tok(s.kv_ram,f), ss=tok(s.kv_ssd,f);
    return `
    <div class="kv-titolo">${f}</div>
    <div class="kv-tempi">RAM: ${t(s.kv_ram,f)} &nbsp;·&nbsp; SSD: ${t(s.kv_ssd,f)}</div>
    <div class="bottoni">
      ${btn('vram_ram',f,'VRAM→RAM',vr)}
      ${btn('vram_ssd',f,'VRAM→SSD',vr)}
      ${btn('ram_ssd',f,'RAM→SSD',ra)}
      ${btn('ram_vram',f,'RAM→VRAM',ra)}
      ${btn('ssd_ram',f,'SSD→RAM',ss)}
      ${btn('ssd_vram',f,'SSD→VRAM',ss)}
    </div>`;}).join("");
}
function gpuMetri(g){
  if(!g) return '<span class="vuoto">nvidia-smi non disponibile</span>';
  const r=(nome,val,max,testo,warn,err)=>{
    const pct=Math.min(100,Math.round(100*val/max));
    const col=pct>=err?"var(--err)":pct>=warn?"var(--warn)":"var(--ok)";
    return `<div class="metro"><div class="sopra"><span class="k">${nome}</span>`+
      `<span class="v">${testo}</span></div>`+
      `<div class="barra"><i style="width:${pct}%;background:${col}"></i></div></div>`;};
  return r("uso GPU",g.util,100,g.util+" %",70,90)
    + r("VRAM",g.mem_used,g.mem_tot,g.mem_used.toLocaleString("it")+" / "+g.mem_tot.toLocaleString("it")+" MiB",85,95)
    + r("temperatura",g.temp,90,g.temp+" °C",72,90)
    + r("potenza",g.power,g.plimit,g.power.toFixed(0)+" / "+g.plimit.toFixed(0)+" W",80,95)
    + r("ventola",g.fan,100,g.fan+" %",75,90);
}
let ultimoStorico="";
function grafico(st){
  if(!st.length) return;
  const chiave=JSON.stringify(st);
  if(chiave===ultimoStorico) return;      // ridisegna solo se cambia
  ultimoStorico=chiave;
  const box=$("grafico"), Wp=box.clientWidth||940, H=210;
  const mL=46,mR=52,mT=12,mB=26, w=Wp-mL-mR, h=H-mT-mB, n=st.length;
  const ces=st.map(p=>p.ce).filter(v=>v!=null);
  const ceMin=ces.length?Math.min(...ces)*0.97:0, ceMax=ces.length?Math.max(...ces)*1.03:1;
  const rMax=Math.max(...st.map(p=>p.ricordi),1);
  const X=i=>mL+(n===1?w/2:i*w/(n-1));
  const Yce=v=>mT+h-(v-ceMin)/((ceMax-ceMin)||1)*h;
  const Yr=v=>mT+h-v/rMax*h;
  // tacche X: 1 giorno per tacca finché ci stanno, poi 2, 3...
  const passo=Math.max(1,Math.ceil(n/Math.max(1,Math.floor(w/48))));
  let s=`<svg viewBox="0 0 ${Wp} ${H}" width="100%" height="${H}" role="img">`;
  for(let k=0;k<=3;k++){const y=mT+h*k/3;
    s+=`<line x1="${mL}" y1="${y}" x2="${Wp-mR}" y2="${y}" stroke="var(--bordo)"/>`;
    if(ces.length) s+=`<text x="${mL-7}" y="${y+4}" text-anchor="end" font-size="10" fill="var(--accent)">${(ceMax-(ceMax-ceMin)*k/3).toFixed(2)}</text>`;
    s+=`<text x="${Wp-mR+7}" y="${y+4}" font-size="10" fill="var(--ric)">${Math.round(rMax*(1-k/3))}</text>`;}
  for(let i=0;i<n;i+=passo){const [aa,mm,gg]=st[i].g.split("-");
    s+=`<text x="${X(i)}" y="${H-7}" text-anchor="middle" font-size="10" fill="var(--muted)">${gg}/${mm}</text>`;}
  s+=`<polyline fill="none" stroke="var(--ric)" stroke-width="2" points="${st.map((p,i)=>X(i)+","+Yr(p.ricordi)).join(" ")}"/>`;
  const pts=st.map((p,i)=>p.ce!=null?[i,p.ce]:null).filter(Boolean);
  if(pts.length>1) s+=`<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${pts.map(([i,v])=>X(i)+","+Yce(v)).join(" ")}"/>`;
  for(const [i,v] of pts) s+=`<circle cx="${X(i)}" cy="${Yce(v)}" r="4.5" fill="var(--accent)"><title>${st[i].g} · CE held-out ${v}</title></circle>`;
  for(let i=0;i<n;i++) s+=`<circle cx="${X(i)}" cy="${Yr(st[i].ricordi)}" r="3" fill="var(--ric)"><title>${st[i].g} · ${st[i].ricordi} ricordi</title></circle>`;
  s+="</svg>";
  box.innerHTML=s;
}
let gmaxTouch=0, busyVisto=0, ultimoSlot=0;
async function giro(){
  let d;
  try{ d=await (await fetch("dati.json")).json(); }
  catch(e){ $("ora").textContent="⚠ dashboard non raggiungibile"; $("ora").className="stato-err"; return; }
  $("ora").className="ora";
  $("ora").textContent=d.ora;
  $("h-notturna").innerHTML = d.ore_da_notturna==null ? "" :
    "· ultima notturna <b>"+d.ore_da_notturna.toLocaleString("it")+" h fa</b> · "+
    (d.avviso_stanchezza
      ? '<span class="stato-warn">avviso stanchezza ricevuto</span>'
      : '<span class="stato-ok">nessun avviso di stanchezza (parte a 16 h)</span>');
  $("gpu-metri").innerHTML=gpuMetri(d.gpu);
  grafico(d.storico);
  const gm=$("gmax");
  if(Date.now()-gmaxTouch>5000){ gm.value=d.griglie_max; $("gmax-val").textContent=d.griglie_max; }
  const s=d.sistema;
  armata=d.notturna_armata;
  const bn=$("btn-notturna");
  if(s.notturna_in_corso){
    bn.textContent="🌙 notturna in corso"; bn.className="btn-viola"; bn.disabled=true;
  }else if(armata){
    bn.textContent="🌙 armata · clic per annullare"; bn.className="btn-verde"; bn.disabled=false;
  }else{
    bn.textContent="🌙 avvia notturna"; bn.className=""; bn.disabled=false;
  }
  $("notturna-chip").textContent=s.notturna_in_corso?"▶ notturna in corso"
    :(armata?"🌙 armata: parte al prossimo EOS del pensatoio":"");
  stato($("s-35b"),s.su,"su, agente sveglio","giù, agente dorme");
  // isteresi 10s: mentre il pensatoio pensa fitto, la riga non sfarfalla
  // tra "in volo" e "libero" a ogni campione
  if(s.busy) busyVisto=Date.now();
  const inVolo=s.su&&(s.busy||Date.now()-busyVisto<10000);
  $("s-busy").textContent=s.su?(inVolo?"▶ turno in volo":"libero"):"–";
  $("s-busy").className=inVolo?"stato-warn":"";
  stato($("s-rifl"),s.riflesso,"su","giù, agente muto!");
  $("s-pens").textContent=s.pensatoio?"● attivo":"❄ congelato";
  $("s-pens").className=s.pensatoio?"stato-ok":"";
  $("btn-pens").disabled=!s.pensatoio;
  $("btn-pens-on").disabled=s.pensatoio;
  $("btn-pens-on").className=s.pensatoio?"btn-verde":"";
  $("r-ultima").textContent=s.ultima_notturna;
  $("r-prossima").textContent=s.prossima;
  $("cw-ctx").textContent="· ctx "+s.ctx.toLocaleString("it")+" tok";
  const metri=[];
  if(s.ultimo_turno) metri.push({nome:"ultimo turno",tok:s.ultimo_turno});
  for(const k of s.kv_ram) metri.push({nome:k.nome+" (RAM)",tok:k.tok,nota:"stima da file, salvato "+k.salvato});
  $("cw-metri").innerHTML=metri.map(m=>metro(m,s.ctx)).join("");
  $("kv-manovre").innerHTML=manovre(s);
  const g=d.griglie;
  $("g-store").textContent=g.store;
  $("g-agg").textContent=g.agganciate+" agganciate";
  $("g-sca").textContent=g.scartate+" scartate";
  $("g-sca").className=(g.scartate>0?"stato-err":"")+" num";
  $("g-corso").innerHTML=g.in_corso?'<div class="riga stato-warn">▶ distillazione in corso</div>':"";
  $("g-tab").innerHTML=g.righe.length
    ? "<tr><th>ora</th><th>nodo</th><th>loss</th><th>match</th><th>t</th><th></th></tr>"+
      g.righe.map(r=>`<tr><td>${r.ora}</td><td>${r.nodo}</td><td>${r.loss}</td>`+
        `<td>${r.match}</td><td>${r.sec}s</td>`+
        `<td class="${r.ok?"ok":"err"}">${r.ok?"✔ agganciata":"✘ scartata"}</td></tr>`).join("")
    : '<tr><td class="vuoto">nessuna griglia in questo ciclo</td></tr>';
  const c=d.codec;
  if(c.run===null){ $("c-run").textContent="nessun run nel log"; return; }
  $("c-run").textContent=c.run+" · "+Number(c.parametri).toLocaleString("it")+" parametri";
  const mappa={training:["▶ training in corso","stato-warn"],
               completo:["✔ completo","stato-ok"],interrotto:["✘ interrotto","stato-err"]};
  $("c-stato").textContent=mappa[c.stato][0]+(c.dettaglio?" · "+c.dettaglio:"");
  $("c-stato").className="chip "+mappa[c.stato][1];
  $("c-best").textContent=c.best||"nessuno";
  const bestN=c.best?(c.best.match(/epoca (\d+)/)||[])[1]:null;
  const CE_TIP='CE, Cross-Entropy (entropia incrociata): quanto il codec sbaglia nel ricostruire. Più bassa è, meglio è. «train» = sugli esempi di addestramento; «held-out» = su esempi tenuti fuori, misura se generalizza davvero.';
  $("c-tab").innerHTML=c.epoche.length
    ? `<tr><th>epoca</th><th>CE <i class="info" data-tip="${CE_TIP}">ⓘ</i> train</th><th>CE held-out</th></tr>`+
      c.epoche.map(e=>{const b=e.n===bestN?' class="ok"':"";
        return `<tr><td${b}>${e.n}${b?" ★":""}</td><td${b}>${e.train}</td><td${b}>${e.held}</td></tr>`;}).join("")
    : "";
}
const gmax=$("gmax");
gmax.addEventListener("input",()=>{ $("gmax-val").textContent=gmax.value; gmaxTouch=Date.now(); });
gmax.addEventListener("change",()=>{ gmaxTouch=Date.now(); fai("griglie_max",gmax.value); });
gmax.addEventListener("wheel",e=>{
  e.preventDefault();
  gmax.value=Math.max(0,Math.min(32,+gmax.value+(e.deltaY<0?1:-1)));
  gmax.dispatchEvent(new Event("input"));
  clearTimeout(gmax._t);
  gmax._t=setTimeout(()=>gmax.dispatchEvent(new Event("change")),400);
},{passive:false});
giro(); setInterval(giro,3000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def _manda(self, corpo, tipo):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path.startswith("/dati.json"):
            self._manda(json.dumps(dati()).encode(), "application/json")
        elif self.path == "/":
            self._manda(PAGINA.encode(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/azione":
            self.send_error(404)
            return
        try:
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            ok, msg = azione(corpo.get("op", ""), corpo.get("nome", ""))
        except Exception as e:
            ok, msg = False, str(e)
        self._manda(json.dumps({"ok": ok, "msg": msg}).encode(), "application/json")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8095
    threading.Thread(target=_watcher_eos, daemon=True).start()
    # ponytail: 127.0.0.1 fisso; per leggerla da fuori (VPN) cambiare in ""
    ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()
