#!/usr/bin/env python3
# Dashboard web di `notturna -status` (22/07): niente
# sfarfallio, la pagina resta ferma e il JS aggiorna solo i valori.
# Pulsanti: ferma pensatoio (MAI un pulsante di riattivazione: regola di
# progetto, la riattivazione è un gesto umano a mano) + manovre cache KV tra VRAM (slot 0),
# RAM (/dev/shm/agente-kv) e SSD (kv-slots). Guardie: nessuna operazione sullo
# slot con un turno in volo; conferma esplicita lato pagina per la VRAM.
# Solo stdlib. Uso: notturna -web [porta]   (default 8095, solo 127.0.0.1)
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

MARKER = "/data/memoria-episodica-affettiva/.ultimo-consolidamento"
KV_RAM = "/dev/shm/agente-kv"
KV_SSD = "/data/workspace/kv-slots"
KV_FILES = ("chat.kv", "pensatoio.kv")
KV_BYTES_TOK = 22900          # ~22,9 KB/token misurati (640MB / 28k tok)
CTX_DEFAULT = 143360
FREEZE = "/usr/local/bin/pensatoio-freeze"
AGENTE_START = "/usr/local/bin/agente-start"
AGENTE_STOP = "/usr/local/bin/agente-stop"
NOTTURNA = "/usr/local/bin/notturna"
DORMI_FLAG = "/data/workspace/memoria/.dormi-richiesto"
AZLOG = "/data/memoria-episodica-affettiva/notturna-web-azioni.log"
ENG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engrammi")   # 1.20.0: meta del Lux (prima memoria.db)
ARMATA_FILE = "/data/memoria-episodica-affettiva/.notturna-armata"
PENS_KV = "/dev/shm/agente-kv/pensatoio.kv"
LLAMA = "http://127.0.0.1:8090"
LUX3D = "http://127.0.0.1:8131"
CONFRONTO = "http://127.0.0.1:8097"   # 30/10: confronto steering/non steering (8-sistema-steering/confronto/)


def _pgrep(pat):
    return subprocess.run(["pgrep", "-f", pat], capture_output=True).returncode == 0


def _slots():
    try:
        return json.load(urlopen(LLAMA + "/slots", timeout=1))
    except Exception:
        return None


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
    cont = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", "agente"],
                          capture_output=True, text=True).stdout.strip() == "true"
    return {"ctx": ctx, "su": su, "busy": busy, "slot_vivo": npast, "container": cont,
            "ultimo_turno": int(ult[-1]) if ult else None,
            "kv_ram": _tier(KV_RAM), "kv_ssd": _tier(KV_SSD),
            "riflesso": _pgrep("riflesso.py"),
            "pensatoio": mot == "active",
            "ultima_notturna": time.strftime("%d/%m %H:%M", time.localtime(mk)) if mk else "mai",
            "prossima": "adesso",   # 10/11: nessun minimo fra due notturne
            "notturna_in_corso": _pgrep("notte-memoria.sh|tagging35b.py")}


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
    """Per giorno: ricordi cumulativi nel grafo. (30/09: tolta la curva CE del codec v1, archiviato)"""
    ce = {}
    ric = {}
    try:
        per_giorno = {}
        sys.path.insert(0, ENG)
        import meta_lux
        with open(meta_lux.percorso(), encoding="utf-8") as f:
            for r in json.load(f)["ricordi"].values():
                if r["classe"] != "correzione":
                    g = datetime.datetime.fromtimestamp(float(r["ts"])).strftime("%Y-%m-%d")
                    per_giorno[g] = per_giorno.get(g, 0) + 1
        tot = 0
        for d in sorted(per_giorno):
            tot += per_giorno[d]
            ric[d] = tot
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


# 13/11: quando arriva il prossimo appunto nel pensatoio. Il motore di autonomia controlla ogni 15 s e risveglia
# l'agente quando le guardie lo permettono (motore-autonomia.py): qui l'ultimo esito del suo giro, tradotto in un orario
RISVEGLIO = os.path.expanduser("~/.local/state/motore-autonomia.ultimo-risveglio")
QUIETE_S = COOLDOWN_S = 5 * 60   # FERMA_DA e COOLDOWN di motore-autonomia.py


def _appunto():
    """quanto manca alla prossima consegna, contato dall'ora in cui il motore ha scritto il suo esito (13/11: contare da
    adesso faceva scivolare l'orario in avanti fra un giro del motore e l'altro, ogni 15 s)"""
    if subprocess.run(["systemctl", "--user", "is-active", "--quiet", "motore-autonomia"]).returncode:
        return "motore spento"
    r = subprocess.run(["journalctl", "--user", "-u", "motore-autonomia", "-n", "1", "-o", "short-unix", "--no-pager"],
                       capture_output=True, text=True, timeout=5)
    riga = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    try:
        quando = float(riga.split()[0])
    except (IndexError, ValueError):
        return "?"
    esito = riga.split(": ", 1)[1].split("  ", 1)[-1].strip() if ": " in riga else ""
    m = re.search(r"(?:ferma da|scriveva) (\d+)s", esito)
    if m:
        fine = quando + QUIETE_S - int(m.group(1))
    elif esito == "cooldown":
        try:
            fine = float(open(RISVEGLIO).read()) + COOLDOWN_S
        except (OSError, ValueError):
            return "cooldown"
    else:
        return {"niente da riprendere": "nessun appunto aperto", "gate: non è il momento": "aspetta il via dello stato emotivo",
                "risveglio innescato": "consegnato adesso"}.get(esito, esito or "?")
    return {"fine": fine}


# 13/11: da quanto il pensatoio potrebbe prendere lo slot. Le condizioni del riflesso (riflesso_cache._chat_ferma
# e l'attesa in riflesso.py): nessuna richiesta della chat in volo, ultima attivita' della chat (fine risposta) e ultimo
# "sta scrivendo" ad almeno AFK_S. L'ultima attivita' = quando il riflesso ha riscritto /tmp/chat-in-volo
VOLO = "/tmp/chat-in-volo"
AFK_S = 60   # riflesso_cache.AFK_S
STANZA_CHAT = "!mainroom:localhost"
CC_TOKEN = os.path.expanduser("~/.claude/skills/agente-chat/.cc-token")
_scrive = [0.0]   # ultima volta che la dashboard ha visto "sta scrivendo" nella chat


def _guarda_typing():
    while True:
        try:
            req = urllib.request.Request("http://127.0.0.1:8008/_matrix/client/v3/sync?timeout=0",
                                         headers={"Authorization": "Bearer " + open(CC_TOKEN).read().strip()})
            d = json.loads(urllib.request.urlopen(req, timeout=10).read())
            ev = d.get("rooms", {}).get("join", {}).get(STANZA_CHAT, {}).get("ephemeral", {}).get("events", [])
            if any(e.get("type") == "m.typing" and e["content"].get("user_ids") for e in ev):
                _scrive[0] = time.time()
        except Exception:
            pass
        time.sleep(3)


def _durata(sec):
    sec = int(sec)
    return f"{sec // 3600} h {sec % 3600 // 60} min" if sec >= 3600 else f"{sec // 60} min {sec % 60} s" if sec >= 60 \
        else f"{sec} s"


def _pensatoio_libero():
    try:
        if int(open(VOLO).read().strip() or 0) > 0:
            return "no: la chat sta lavorando"
        ultima = os.path.getmtime(VOLO)
    except (OSError, ValueError):
        ultima = 0.0
    return {"libero": max(ultima, _scrive[0]) + AFK_S, "scrivi": time.time() - _scrive[0] < 10}


def dati():
    mk = os.path.getmtime(MARKER) if os.path.exists(MARKER) else 0
    return {"ora": time.strftime("%H:%M:%S"),
            "ore_da_notturna": round((time.time() - mk) / 3600, 1) if mk else None,
            "notturna_armata": os.path.exists(ARMATA_FILE),
            "gpu": _gpu(), "storico": _storico(), "appunto": _appunto(), "pens_libero": _pensatoio_libero(), "adesso": time.time(),
            "sistema": _sistema()}


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
        return "35B giù: l'agente dorme, la VRAM non c'è"
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
        return True, "notturna avviata: lavora in sottofondo"


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
    if op == "agente_sveglia":
        # 30/09: SOLO dal click umano (regola di progetto: l'agente lo riavvia solo l'autrice). agente-start ha la sua guardia GPU.
        with open(AZLOG, "a") as fh:
            fh.write(f"{time.strftime('%F %T')} sveglia l'agente (agente-start, dalla dashboard)\n")
            fh.flush()
            p = subprocess.Popen([AGENTE_START], stdout=fh, stderr=fh, start_new_session=True)
        try:
            p.wait(timeout=5)
            return p.returncode == 0, open(AZLOG).read().splitlines()[-1]
        except subprocess.TimeoutExpired:
            return True, "sveglia avviata: agente-start accende container, 35B e servizi (qualche minuto)"
    if op == "agente_spegni":
        # 13/11: SOLO dal click umano. agente-stop salva la KV della chat, ferma lo specchio della chat e i container
        with open(AZLOG, "a") as fh:
            fh.write(f"{time.strftime('%F %T')} spegni l'agente (agente-stop, dalla dashboard)\n")
            fh.flush()
            p = subprocess.Popen([AGENTE_STOP], stdout=fh, stderr=fh, start_new_session=True)
        try:
            p.wait(timeout=5)
            return p.returncode == 0, open(AZLOG).read().splitlines()[-1]
        except subprocess.TimeoutExpired:
            return True, "spegnimento avviato: agente-stop salva la chat e ferma i container (fino a un minuto)"
    if op == "pensatoio_stop":
        r = subprocess.run([FREEZE, "-on"], capture_output=True, text=True)
        return (r.returncode == 0,
                "pensatoio congelato ❄" if r.returncode == 0 else r.stderr.strip() or "pensatoio-freeze fallito")
    if op == "pensatoio_start":
        # scatta SOLO dal click umano sulla dashboard: è l'interruttore
        # manuale (regola di progetto, mai da automatismi); autorizzato
        # esplicitamente il 22/07 sera.
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
        # 22/07 sera: il click NON parte subito, ARMA la notturna:
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


# 13/11: pagina per vedere e modificare il blocco appunti dell'agente (quello che legge il motore di autonomia)
APPUNTI = "/data/workspace/memoria/appunti-agente.md"
PAGINA_APPUNTI = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blocco appunti dell'agente</title>
<style>
:root{color-scheme:dark;--bg:#14161a;--card:#1d2026;--ink:#e6e3dc;--muted:#9a978f;--bordo:#3a3d44;--accent:#c79a5b;--ok:#7fb069;--err:#e07a6a}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:16px;max-width:1100px;margin:auto}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:20px;font-weight:650;flex:1}
.nota{color:var(--muted);font-size:13px;margin-bottom:10px}
textarea{width:100%;min-height:65vh;background:var(--card);color:var(--ink);border:1px solid var(--bordo);border-radius:10px;
  padding:12px;font:13.5px/1.6 ui-monospace,monospace;resize:vertical}
button{background:var(--card);color:var(--ink);border:1px solid var(--bordo);border-radius:8px;padding:6px 14px;font:inherit;cursor:pointer}
button:hover{border-color:var(--accent)}
#esito{font-size:13px;color:var(--muted)} #esito.ok{color:var(--ok)} #esito.err{color:var(--err)}
</style></head><body>
<header><h1>📝 Blocco appunti dell'agente</h1>
<button onclick="location.href='/'">← dashboard</button><button onclick="carica()">↻ ricarica</button>
<button onclick="salva()" style="border-color:var(--accent);color:var(--accent);font-weight:600">💾 salva</button></header>
<div class="nota">Una riga per appunto, nel formato <code>[tema]{domanda}</code>. Una riga che comincia con <code>~~</code> e' depennata e il motore
la salta. Ogni salvataggio tiene una copia della versione di prima (<code>appunti-agente.md.prima</code>).
<span id="info"></span></div>
<textarea id="testo" spellcheck="false"></textarea>
<div id="esito"></div>
<script>
const $=i=>document.getElementById(i);
let caricato="";
async function carica(){
  const d=await (await fetch("/appunti/testo",{cache:"no-store"})).json();
  $("testo").value=caricato=d.testo; $("info").textContent=" Ultima modifica: "+d.modificato+".";
  $("esito").textContent=""; $("esito").className="";
}
async function salva(){
  const r=await (await fetch("/appunti/salva",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({testo:$("testo").value,prima:caricato})})).json();
  $("esito").textContent=r.msg; $("esito").className=r.ok?"ok":"err";
  if(r.ok) carica().then(()=>{$("esito").textContent=r.msg;$("esito").className="ok";});
}
carica();
</script></body></html>
"""


PAGINA = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard dell'agente</title>
<style>
/* 11/10: stile grafico della vecchia dashboard di addestramento (dismessa), stessi colori e stesso tema sole/luna.
   13/10: niente verde, arancio, giallo: gli stati usano la rampa blu della pagina emozioni (rosso solo per gli errori) */
:root{color-scheme:light;
  --bg:#f4f3ef; --card:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#8a8984;
  --bordo:#e6e5e0; --ok:#1c5cab; --warn:#5598e7; --err:#c0362c; --accent:#2a78d6;
  --barra-fondo:#efeee9; --btn:#efeee9; --btn-bordo:#e6e5e0;
  --ric:#3987e5; --ok-soft:#cde2fb;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;
  --bg:#111110; --card:#1a1a19; --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e86;
  --bordo:#2d2d2a; --ok:#6da7ec; --warn:#cde2fb; --err:#ea6b60; --accent:#3987e5;
  --barra-fondo:#262624; --btn:#262624; --btn-bordo:#2d2d2a;
  --ric:#9ec5f4; --ok-soft:#104281;
}}
:root[data-theme="dark"]{color-scheme:dark;
  --bg:#111110; --card:#1a1a19; --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e86;
  --bordo:#2d2d2a; --ok:#6da7ec; --warn:#cde2fb; --err:#ea6b60; --accent:#3987e5;
  --barra-fondo:#262624; --btn:#262624; --btn-bordo:#2d2d2a;
  --ric:#9ec5f4; --ok-soft:#104281;
}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:20px 16px 60px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;max-width:1100px;margin:0 auto 14px}
header h1{font-size:22px;font-weight:700}
header nav{margin-left:auto}
.tema{background:none;border:1px solid var(--bordo);border-radius:50%;width:32px;height:32px;padding:0;display:inline-flex;align-items:center;justify-content:center;color:var(--ink);cursor:pointer;vertical-align:middle}
header .ora{color:var(--muted);font-variant-numeric:tabular-nums}
main{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));max-width:1100px;margin:0 auto}
section{background:var(--card);border-radius:12px;padding:14px 16px}
h2{font-size:16px;font-weight:600;color:var(--ink);margin-bottom:10px;display:flex;align-items:center;gap:6px}
.riga{display:flex;justify-content:space-between;gap:8px;padding:3px 0}
.riga .k{color:var(--ink2)}
.num{font-variant-numeric:tabular-nums}
.stato-ok{color:var(--ok)} .stato-warn{color:var(--warn)} .stato-err{color:var(--err)}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;background:var(--btn);font-size:12px;font-weight:600;white-space:nowrap}
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
  border-radius:8px;padding:6px 14px;font:inherit;cursor:pointer}
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
footer{max-width:1100px;margin:14px auto 0;color:var(--muted);font-size:12px}
</style>
<script>
// 11/10: pulsante sole/luna della dashboard. Senza scelta salvata segue il browser; un tocco passa all'altro tema e lo ricorda.
const SOLE='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const LUNA='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
function scuroAdesso(){const d=document.documentElement.dataset.theme;return d?d==="dark":matchMedia("(prefers-color-scheme: dark)").matches}
function disegnaTema(){const el=document.getElementById("tema");if(!el)return;el.innerHTML=scuroAdesso()?SOLE:LUNA;el.title=scuroAdesso()?"Passa al tema chiaro":"Passa al tema scuro"}
function cambiaTema(){const x=scuroAdesso()?"light":"dark";document.documentElement.dataset.theme=x;try{localStorage.setItem("tema-dashboard",x)}catch(e){}disegnaTema()}
(function(){let x=null;try{x=localStorage.getItem("tema-dashboard")}catch(e){}if(x==="light"||x==="dark")document.documentElement.dataset.theme=x})();
document.addEventListener("DOMContentLoaded",disegnaTema);
</script>
</head><body>
<header><h1>🧭 Dashboard</h1><span class="ora" id="ora">…</span>
<span class="ora" id="h-notturna"></span>
<span class="chip stato-warn" id="notturna-chip"></span>
<nav><button id="tema" class="tema" onclick="cambiaTema()" aria-label="Cambia tema chiaro/scuro"></button></nav></header>
<main>
<section><h2>Sistema</h2>
  <div class="riga"><span class="k">35B <i class="info" data-tip="35 miliardi di parametri: il modello che fa girare l'agente (Occamy-1.0, post-training del Qwen3.6-35B, quantizzato Q8_0).">ⓘ</i> (:8090)</span><span id="s-35b">…</span></div>
  <div class="riga"><span class="k">slot</span><span id="s-busy">…</span></div>
  <div class="riga"><span class="k">riflesso (:8091)</span><span id="s-rifl">…</span></div>
  <div class="riga"><span class="k">pensatoio</span><span id="s-pens">…</span></div>
  <div class="riga"><span class="k">pensatoio libero <i class="info" data-tip="Da quanto il pensatoio potrebbe prendere lo slot: nessuna risposta della chat in corso, e almeno 1 minuto dalla fine dell'ultima risposta e dall'ultimo &quot;sta scrivendo&quot;.">ⓘ</i></span><span class="num" id="s-penslib">…</span></div>
  <div class="riga"><span class="k">prossimo appunto</span><span class="num" id="s-appunto">…</span></div>
  <div class="bottoni">
    <button id="btn-sveglia" onclick="fai_conf('agente_sveglia','Sveglio l\'agente? agente-start accende container, 35B e servizi (qualche minuto). Il pensatoio NON riparte da solo.')">☀ sveglia l'agente</button>
    <button id="btn-spegni" onclick="fai_conf('agente_spegni','Spengo l\'agente? agente-stop salva la KV della chat, ferma lo specchio della chat e i container dell\'agente e di Matrix. Il 35B resta acceso.')">⏻ spegni l'agente</button>
    <button id="btn-pens-on" onclick="fai('pensatoio_start','')">▶ riavvia pensatoio</button>
    <button id="btn-pens" onclick="fai('pensatoio_stop','')">❄ ferma pensatoio</button>
  </div>
  <!-- 25/07: le due finestre dell'agente, stesso servizio sulla 8096 -->
  <div class="bottoni">
    <button onclick="finestra('/')">🧠 stream del reasoning</button>
    <button onclick="location.href='/appunti'">📝 blocco appunti</button>
    <button onclick="location.href='/lux3d/'">✨ Lux in 3D</button>
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
    SSD <i class="info" data-tip="Il disco: copia persistente, sopravvive a riavvii e blackout. La copia automatica è spenta dal 23/07 (KV_SSD_ATTIVO in riflesso.py): qui si consolida solo a mano.">ⓘ</i>
  </div>
  <div class="bottoni">
    <button onclick="fai_conf('slot_erase','Svuoto lo slot dal server (evict)? Quello che c\'è in VRAM va perso se non è salvato in RAM o SSD.')">🗑 svuota slot (evict)</button>
  </div>
  <div id="kv-manovre"></div>
  <div id="esito"></div>
  <div class="avviso">⚠︎ le mosse che toccano lo slot (VRAM) chiedono conferma: il server
  non sa quale flusso è nello slot in questo momento, lo sai tu. Rifiutate da sole se un
  turno è in volo.</div>
</section>
<section><h2>GPU <i class="info" data-tip="I valori di nvidia-smi sulla RTX 5060 Ti: uso del processore grafico, VRAM occupata, temperatura, potenza assorbita e ventola.">ⓘ</i></h2>
  <div id="gpu-metri"><span class="vuoto">nvidia-smi non disponibile</span></div>
</section>
<section class="largo"><h2>Storia <i class="info" data-tip="Per ogni giorno: quanti ricordi vivono nel grafo.">ⓘ</i></h2>
  <div id="grafico"><span class="vuoto">nessun dato</span></div>
  <div class="avviso"><span style="color:var(--ric)">●</span> ricordi nel grafo</div>
</section>
<section class="largo"><h2>Altre pagine</h2>
  <div class="bottoni">
    <button onclick="finestra('/diario')">📖 diario del riflesso</button>
    <button onclick="location.href='/emozioni/'">🎭 test inefficace</button>
    <button onclick="location.href='/vettori/'">🧭 vettori emotivi</button>
    <button onclick="location.href='/dosi/'">💉 dosi steering</button>
    <button onclick="location.href='/confronto/'">👥 confronto steering</button>
    <button onclick="location.href='/protocollo/'">🧪 protocollo steering</button>
  </div>
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
// 25/07: le finestre dell'agente vivono sulla 8096, stesso host da cui arriva questa
// pagina (così vale anche se la dashboard è aperta con un altro nome host).
function finestra(p){   // 13/10 l'utente: il tema passa anche a stream e diario (altra porta, niente localStorage in comune)
  let x="";try{x=localStorage.getItem("tema-dashboard")||""}catch(e){}
  location.href=location.protocol+"//"+location.hostname+":8096"+p+(x?"#tema="+x:"");}
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
let busyVisto=0, ultimoSlot=0;
async function giro(){
  let d;
  try{ d=await (await fetch("dati.json")).json(); }
  catch(e){ $("ora").textContent="⚠︎ dashboard non raggiungibile"; $("ora").className="stato-err"; return; }
  $("ora").className="ora";
  $("ora").textContent=d.ora;
  $("h-notturna").innerHTML = d.ore_da_notturna==null ? "" :
    "· ultima notturna <b>"+d.ore_da_notturna.toLocaleString("it")+" h fa</b>";
  $("gpu-metri").innerHTML=gpuMetri(d.gpu);
  grafico(d.storico);
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
  $("btn-sveglia").disabled=s.su&&s.container;
  $("btn-spegni").disabled=!s.container;
  // isteresi 10s: mentre l'agente pensa fitto, la riga non sfarfalla
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
  timer={appunto:d.appunto, libero:s.pensatoio?d.pens_libero:"❄ congelato", scarto:d.adesso-Date.now()/1000};
  conta();
  $("r-ultima").textContent=s.ultima_notturna;
  $("r-prossima").textContent=s.prossima;
  $("cw-ctx").textContent="· ctx "+s.ctx.toLocaleString("it")+" tok";
  const metri=[];
  if(s.ultimo_turno) metri.push({nome:"ultimo turno",tok:s.ultimo_turno});
  for(const k of s.kv_ram) metri.push({nome:k.nome+" (RAM)",tok:k.tok,nota:"stima da file, salvato "+k.salvato});
  $("cw-metri").innerHTML=metri.map(m=>metro(m,s.ctx)).join("");
  $("kv-manovre").innerHTML=manovre(s);
}

// 13/11: i due timer scendono ogni secondo fra un aggiornamento e l'altro (ogni 3 s si riallineano al server)
let timer=null;
function durata(s){s=Math.max(0,Math.floor(s));
  return s>=3600?Math.floor(s/3600)+" h "+Math.floor(s%3600/60)+" min":s>=60?Math.floor(s/60)+" min "+(s%60)+" s":s+" s";}
function conta(){
  if(!timer) return;
  const ora=Date.now()/1000+timer.scarto, a=timer.appunto, l=timer.libero;
  $("s-appunto").textContent=typeof a==="string"?a:(a.fine>ora?"fra "+durata(a.fine-ora):"a momenti");
  $("s-penslib").textContent=typeof l==="string"?l:(l.libero>ora?"fra "+durata(l.libero-ora)+(l.scrivi?" (stai scrivendo)":""):"da "+durata(ora-l.libero));
}
giro(); setInterval(giro,3000); setInterval(conta,1000);
</script></body></html>"""


EMOZIONI = "/data/memoria-episodica-affettiva/research/long-context/4-steering-per-layer/emozioni-layer"
VETTORI = "/data/memoria-episodica-affettiva/research/long-context/6-template-lens/vettori-pagina"   # 12/10 sera: vettori col metodo del paper (prima 5-vettori-italiani)
PROTOCOLLO = "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering/pagina-protocollo"   # 22/10: prove del protocollo di steering
DOSI = "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering/pagina-dosi"   # 24/10: curve di efficacia per dose

class H(BaseHTTPRequestHandler):
    def _confronto(self, corpo=None):
        """30/10: inoltra /confronto/ al suo server; il testo generato passa a pezzi mentre arriva"""
        r = urllib.request.Request(CONFRONTO + self.path[len("/confronto"):], corpo,
                                   {"Content-Type": "application/json"} if corpo is not None else {})
        try:
            risp = urlopen(r, timeout=3600)
        except urllib.error.HTTPError as e:
            risp = e
        except Exception as e:
            self._manda(f"confronto non raggiungibile ({e}): systemctl --user status confronto-steering".encode(),
                        "text/plain; charset=utf-8")
            return
        tipo = risp.headers.get("Content-Type", "application/octet-stream")
        if not tipo.startswith("text/event-stream"):
            self.send_response(risp.status)
            corpo = risp.read()
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while pezzo := risp.read1(65536):
                self.wfile.write(pezzo)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            risp.close()

    def _manda(self, corpo, tipo):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")   # 13/10: il telefono teneva la pagina vecchia
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path in ("/appunti", "/appunti/"):
            self._manda(PAGINA_APPUNTI.encode(), "text/html; charset=utf-8")
            return
        if self.path.startswith("/appunti/testo"):
            t = open(APPUNTI, encoding="utf-8").read() if os.path.exists(APPUNTI) else ""
            mod = time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(APPUNTI))) if t else "mai"
            self._manda(json.dumps({"testo": t, "modificato": mod}).encode(), "application/json")
            return
        if self.path.startswith("/dati.json"):
            self._manda(json.dumps(dati()).encode(), "application/json")
        elif self.path == "/":
            self._manda(PAGINA.encode(), "text/html; charset=utf-8")
        elif self.path == "/lux3d":
            self.send_response(301)
            self.send_header("Location", "/lux3d/")
            self.end_headers()
        elif self.path.startswith("/lux3d/"):   # 12/10: il Lux in 3D (lux3d.py, solo 127.0.0.1) passa da qui
            try:
                r = urlopen(LUX3D + self.path[len("/lux3d"):], timeout=60)
                self._manda(r.read(), r.headers.get("Content-Type", "application/octet-stream"))
            except Exception as e:
                self._manda(f"Lux 3D non raggiungibile ({e}): systemctl --user status lux3d".encode(),
                            "text/plain; charset=utf-8")
        elif self.path in ("/vettori", "/vettori/") or self.path.startswith("/vettori/"):   # 12/10: vettori italiani (pagina_vettori.py)
            nome = self.path[len("/vettori/"):].split("?")[0] if self.path.startswith("/vettori/") else ""
            if self.path == "/vettori":
                self.send_response(301); self.send_header("Location", "/vettori/"); self.end_headers(); return
            # 12/10 sera: a estrazione in corso la pagina si rigenera quando ci sono passaggi o vettori nuovi
            sorgenti_v = [VETTORI.rsplit("/", 1)[0] + "/fatti.txt", "/data/jspace/out-occamy/vettori-paper.pt"]
            dati_v = VETTORI + "/dati.json"
            if (nome or "index.html") in ("index.html", "dati.json") and any(
                    os.path.exists(s) and (not os.path.exists(dati_v) or os.path.getmtime(s) > os.path.getmtime(dati_v)) for s in sorgenti_v):
                subprocess.run(["/data/jspace/venv/bin/python", VETTORI.rsplit("/", 1)[0] + "/pagina_vettori.py"],
                               capture_output=True, timeout=120)
            f = os.path.realpath(os.path.join(VETTORI, nome or "index.html"))
            if not f.startswith(VETTORI + "/") or not os.path.isfile(f):
                self.send_error(404)
                return
            self._manda(open(f, "rb").read(), "application/json" if f.endswith(".json") else "text/html; charset=utf-8")
        elif self.path == "/emozioni":
            self.send_response(301)
            self.send_header("Location", "/emozioni/")
            self.end_headers()
        elif self.path.startswith("/emozioni/"):   # 12/10: steering per layer (research/long-context/4-steering-per-layer/analizza_layer.py)
            nome = self.path[len("/emozioni/"):].split("?")[0] or "index.html"
            f = os.path.realpath(os.path.join(EMOZIONI, nome))
            if not f.startswith(EMOZIONI + "/") or not os.path.isfile(f):
                self.send_error(404)
                return
            tipo = {".html": "text/html; charset=utf-8", ".json": "application/json",
                    ".md": "text/plain; charset=utf-8"}.get(os.path.splitext(f)[1], "application/octet-stream")
            self._manda(open(f, "rb").read(), tipo)
        elif self.path == "/protocollo":
            self.send_response(301)
            self.send_header("Location", "/protocollo/")
            self.end_headers()
        elif self.path.startswith("/protocollo/"):   # 22/10: una tab per prova (8-sistema-steering/pagina_protocollo.py)
            nome = self.path[len("/protocollo/"):].split("?")[0] or "index.html"
            cartella = PROTOCOLLO.rsplit("/", 1)[0]
            pagina = PROTOCOLLO + "/index.html"
            if nome == "index.html" and (not os.path.exists(pagina) or any(
                    os.path.exists(s) and os.path.getmtime(s) > os.path.getmtime(pagina)
                    for s in (cartella + "/prova-frase.jsonl", cartella + "/giudizi-prova-frase.jsonl"))):
                try:
                    subprocess.run(["python3", cartella + "/pagina_protocollo.py"], capture_output=True, timeout=120)
                except subprocess.TimeoutExpired:
                    pass   # si serve la pagina di prima
            f = os.path.realpath(os.path.join(PROTOCOLLO, nome))
            if not f.startswith(PROTOCOLLO + "/") or not os.path.isfile(f):
                self.send_error(404)
                return
            self._manda(open(f, "rb").read(), "application/json" if f.endswith(".json") else "text/html; charset=utf-8")
        elif self.path == "/confronto":
            self.send_response(301)
            self.send_header("Location", "/confronto/")
            self.end_headers()
        elif self.path.startswith("/confronto/"):
            self._confronto()
        elif self.path == "/dosi":
            self.send_response(301)
            self.send_header("Location", "/dosi/")
            self.end_headers()
        elif self.path.startswith("/dosi/"):   # 24/10: una riga per emozione, curva per dose (8-sistema-steering/pagina_dosi.py)
            nome = self.path[len("/dosi/"):].split("?")[0] or "index.html"
            cartella = DOSI.rsplit("/", 1)[0]
            dati_d = DOSI + "/dati.json"
            sorgenti_d = [cartella + "/prova-dosi-medio.jsonl", cartella + "/prova-dosi-fini.jsonl", cartella + "/prova-dosi-giri.jsonl",
                          "/data/memoria-episodica-affettiva/engrammi/DOSI-EMOZIONI.md"] + glob.glob(cartella + "/giudizio-dosi/uscite/*.jsonl")
            if nome in ("index.html", "dati.json") and (not os.path.exists(dati_d) or any(
                    os.path.exists(x) and os.path.getmtime(x) > os.path.getmtime(dati_d) for x in sorgenti_d)):
                try:
                    subprocess.run(["python3", cartella + "/pagina_dosi.py"], capture_output=True, timeout=120)
                except subprocess.TimeoutExpired:
                    pass   # si servono i dati di prima
            f = os.path.realpath(os.path.join(DOSI, nome))
            if not f.startswith(DOSI + "/") or not os.path.isfile(f):
                self.send_error(404)
                return
            self._manda(open(f, "rb").read(), "application/json" if f.endswith(".json") else "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/appunti/salva":   # 13/11: il blocco appunti dell'agente si modifica dalla pagina
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                ora = open(APPUNTI, encoding="utf-8").read() if os.path.exists(APPUNTI) else ""
                if ora != d.get("prima", ""):   # intanto l'ha cambiato l'agente: niente sovrascrittura
                    ok, msg = False, "il file e' cambiato dopo che l'hai aperto (forse l'ha scritto l'agente): ricarica e rifai la modifica"
                else:
                    testo = d["testo"].replace("\r\n", "\n")
                    testo += "" if testo.endswith("\n") or not testo else "\n"
                    open(APPUNTI + ".prima", "w", encoding="utf-8").write(ora)
                    open(APPUNTI + ".tmp", "w", encoding="utf-8").write(testo)
                    os.replace(APPUNTI + ".tmp", APPUNTI)
                    ok, msg = True, "salvato alle " + time.strftime("%H:%M:%S")
            except Exception as e:
                ok, msg = False, str(e)
            self._manda(json.dumps({"ok": ok, "msg": msg}).encode(), "application/json")
            return
        if self.path.startswith("/confronto/"):
            self._confronto(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            return
        if self.path == "/dosi/didascalie":   # 28/10: le didascalie dei grafici si modificano dalla pagina
            try:
                testo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))["testo"]
                f = DOSI + "/didascalie.txt"
                open(f + ".tmp", "w").write(testo)
                os.replace(f + ".tmp", f)
                ok, msg = True, "salvato"
            except Exception as e:
                ok, msg = False, str(e)
            self._manda(json.dumps({"ok": ok, "msg": msg}).encode(), "application/json")
            return
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
    # 11/10: la dashboard di addestramento e' dismessa; questa pagina prende il suo posto sulla :8095,
    # su localhost e sull'IP della VPN Tailscale (100.x)
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8095
    # 13/11 (blackout): su localhost subito; l'indirizzo Tailscale si aggiunge quando la VPN sale (prima, senza VPN la
    # dashboard non partiva nemmeno sul PC)
    def _vpn():
        while True:
            ts = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True).stdout.split()
            ips = [ip for ip in ts if ip.startswith("100.")]
            if ips:
                for ip in ips:
                    threading.Thread(target=ThreadingHTTPServer((ip, porta), H).serve_forever, daemon=True).start()
                print("notturna anche su " + ", ".join(f"http://{ip}:{porta}" for ip in ips), flush=True)
                return
            time.sleep(10)
    threading.Thread(target=_vpn, daemon=True).start()
    threading.Thread(target=_guarda_typing, daemon=True).start()
    threading.Thread(target=_watcher_eos, daemon=True).start()
    print(f"notturna su http://127.0.0.1:{porta}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()
