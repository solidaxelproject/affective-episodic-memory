# riflesso_cache.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import http.client
import json
import socket
import time
import urllib.request
from pathlib import Path
import riflesso_stato as S


# --- specchio del KV (17/07, richiesta di progetto): l'istante sospeso dell'agente.
# A fine di OGNI stream: salvataggio dello slot in RAM (/dev/shm, via
# --slot-save-path del server). Ogni 5 messaggi: copia consolidata su SSD.
# Un blackout costa al massimo l'ultima risposta, e l'NVMe non si usura.
KV_RAM = Path("/dev/shm/agente-kv")
KV_SSD = Path("/data/workspace/kv-slots")
KV_OGNI = 5
# 23/07, scelta di progetto (giorno del bit-rot sullo shard 16): la copia
# automatica su SSD è SPENTA; lo specchio vive solo in RAM (/dev/shm).
# Le copie su SSD restano possibili A MANO dalla dashboard (manovre cache).
KV_SSD_ATTIVO = False
_kv_conta = [0]

AFK_S = 60              # spec punto 5: 1 min senza typing = l'utente non c'è


HS = "http://127.0.0.1:8008"
STANZA = "!mainroom:example.local"
TOKFILE = Path.home() / ".config/motore/.matrix-token"


def _slot(azione, nomefile):
    up = http.client.HTTPConnection(*S.UPSTREAM, timeout=120)
    try:
        up.request("POST", f"/slots/0?action={azione}",
                   body=json.dumps({"filename": nomefile}),
                   headers={"Content-Type": "application/json"})
        r = up.getresponse(); r.read()
        return r.status == 200
    finally:
        up.close()


def _flusso(body):
    """'chat' | 'pensatoio' | 'altro', dal primo messaggio user della richiesta."""
    try:
        msgs = json.loads(body).get("messages", [])
        primo = next((m.get("content", "") for m in msgs
                      if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
    except Exception:
        return "altro"
    if primo.startswith("[IMPORTANT:"):
        # ponytail: il pensatoio è l'unico cron con la skill blocco-appunti;
        # se un giorno un altro job la attaccasse, servirà l'id del job
        return "pensatoio" if "blocco-appunti" in primo[:300] else "altro"
    if primo.startswith("["):
        return "chat"       # il bridge Matrix prefissa "[mittente] "
    return "altro"


def _typing():
    """Qualcuno sta scrivendo nella chat principale? (token Matrix di servizio, come il motore)"""
    try:
        tok = TOKFILE.read_text().strip()
        req = urllib.request.Request(f"{HS}/_matrix/client/v3/sync?timeout=0",
                                     headers={"Authorization": f"Bearer {tok}"})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read())
        ev = (d.get("rooms", {}).get("join", {}).get(STANZA, {})
               .get("ephemeral", {}).get("events", []))
        return any(e.get("type") == "m.typing" and e["content"].get("user_ids")
                   for e in ev)
    except Exception:
        return False        # senza sync niente attese: il fallback resta lo scambio


def _scambia(fl):
    """Porta nello slot la CW di fl. Solo dentro _cw_lock."""
    if S._cw[0] in S.KV_FLUSSO:
        _slot("save", S.KV_FLUSSO[S._cw[0]])
    if (KV_RAM / S.KV_FLUSSO[fl]).exists():
        _slot("restore", S.KV_FLUSSO[fl])
    _cambia_cw(fl)


def _cambia_cw(fl):
    """nello slot entra la cache di fl: l'orologio della discesa del flusso che esce si ferma"""
    esce = S._cw[0]
    if esce in S._vissuto:
        if esce in S._interrotto and esce in S._punto:
            S._vissuto[esce] = S._punto[esce]     # riparte dalla fine dell'ultimo tool
        else:
            S._vissuto[esce] += time.time() - S._caricato[0]
        S._interrotto.discard(esce)
    S._caricato[0] = time.time()
    S._cw[0] = fl


def _nuovo_pensiero(conv):
    """un risveglio nuovo nel pensatoio: cache ricominciata, vettori e orologio a zero"""
    if conv == S._pens_conv[0]:
        return
    S._pens_conv[0] = conv
    S._vettori["pensatoio"].clear()
    S._vissuto["pensatoio"] = 0.0
    S._punto.pop("pensatoio", None)
    if S._cw[0] == "pensatoio":
        S._caricato[0] = time.time()


def _chat_ferma():
    """il pensatoio puo' prendere lo slot: chat fredda da AFK_S e nessuna sua richiesta in corso"""
    return time.time() - S._chat_calda[0] >= AFK_S and not S._chat_in_volo[0]


def _interrompi_pensatoio():
    """spec punto 4 (19/07): la chat interrompe il pensiero in corso. shutdown e non
    close: con keep-alive la close aspetta la risposta e con Connection: close c.sock
    e' gia' None (issue #3), lo stream andava fino in fondo. Il server vede la
    connessione chiusa e ferma la generazione; il gateway ritenta."""
    if S._pens_vivi:
        S._interrotto.add("pensatoio")
    for s in list(S._pens_vivi):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _salva_kv():
    """A fine stream: la CW attiva si specchia su file (RAM, ogni 5 su SSD)
    e il conteggio token del flusso arma/riarma le soglie gemelle."""
    try:
        with S._cw_lock:
            fl = S._cw[0]
            if fl not in S.KV_FLUSSO:
                return      # slot sporco di un flusso estraneo: non toccare i file
            nome = S.KV_FLUSSO[fl]
            if not _slot("save", nome):
                return
        try:
            up = http.client.HTTPConnection(*S.UPSTREAM, timeout=10)
            up.request("GET", "/slots")
            s = json.loads(up.getresponse().read()); up.close()
            S._tok_cw[fl] = int(s[0].get("n_prompt_tokens", 0))
            if S._tok_cw[fl] <= S.SOGLIA_CW:
                S._avvisato_cw[fl] = False    # riarmo dopo dormita/riciclo
        except Exception:
            pass
        _kv_conta[0] += 1
        if KV_SSD_ATTIVO and _kv_conta[0] % KV_OGNI == 0:
            KV_SSD.mkdir(parents=True, exist_ok=True)
            src = KV_RAM / nome
            tmp = KV_SSD / (nome + ".tmp")
            tmp.write_bytes(src.read_bytes())
            tmp.replace(KV_SSD / nome)
    except Exception:
        pass    # lo specchio non deve MAI rompere la chat
