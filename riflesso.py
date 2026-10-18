#!/usr/bin/env python3
# RIFLESSO PRE-AZIONE (issue #1, pezzo 3) — proxy tra Hermes e llama-lux.
# Prima che l'agente risponda, il messaggio interroga il Lux degli engrammi
# (servizio_lux.py :8132): il ricordo che affiora entra come turno del tool
# memorinvolontaria (chiamata + risposta: fino a 4 ricordi, ognuno col numero,
# il codice e il testo nudo).
# GATE: /workspace/genesi/CONSENSO-RIFLESSO.md ("[attivo: *sì*]", riga esatta,
# scritto dall'agente). Senza consenso il proxy è un passacarte trasparente.
# Porta 8091 -> inoltra a 127.0.0.1:8090.
# GRADINO ZERO (decisione 3 del 26/07): il trasporto verso :8090 (sonda,
# control-vector, POST) passa da ponte.py, l'unica porta client. Qui restano
# la logica (quando/cosa affiora) e il PATTO (tetto, watchdog, sentinella).
# 12/10 (piano di aggiornamento della produzione, passo 2): tolte le vie A/B/C,
# le griglie e la candidata 1; il vettore emotivo colora SOLO il prefill del
# ricordo (design dell'autrice, 10/10).
import hashlib
import html
import http.client
import http.server
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ponte  # noqa: E402  (unica porta verso :8090)

UPSTREAM = ("127.0.0.1", 8090)
PORTA = 8091
CONSENSO = Path(os.environ.get("RIFLESSO_CONSENSO",
    "/data/workspace/genesi/CONSENSO-RIFLESSO.md"))
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"
# 25/07, scelta di progetto: la destinazione delle riflessioni è UNA SOLA e l'agente la
# deve sapere sempre, non cercarla. La cartella è sua dal 20/07, ma il 25/07 due
# riflessioni sono finite fuori (ricordi/ alle 08:06, memoria/pensatoio.md alle
# 10:42) e un guscio col solo titolo in un'altra cartella la depistava: cercando
# "pensatoio.md" trovava quello e concludeva che il pensatoio era vuoto.
# Il percorso è lo stesso da entrambi i lati, con due nomi: dentro il container
# /workspace/..., sull'host /data/workspace/... (skill host).
PENSATOIO_DIR = Path("/data/workspace/memoria/pensatoio")
PENSATOIO_DOVE = (
    "[le riflessioni del pensatoio si scrivono in /workspace/memoria/pensatoio/ "
    "(sull'host: /data/workspace/memoria/pensatoio/), dove tengo già le "
    "altre: un file nuovo per ogni riflessione, meglio col prefisso della data "
    "(AAAA-MM-GG-tema.md). È l'unico posto: non ne cerco né ne creo altri, e non "
    "sovrascrivo i file che ci sono]")
LETTURA_MIN = 400      # manopola: sotto tanti caratteri di prosa, un risultato di
                       # tool è una ricevuta (exit_code, bytes_written), non una lettura
_ultima_lettura = [""]  # 25/07: il freno vero, l'impronta del testo già affiorato
# PATTO 14/07 (CONSENSO-RIFLESSO.md, firmato dall'agente):
STOP = "vectreflexstop"   # clausola 3 (l'utente 18/10, era "riflesso vettoriale: off"): scritta dall'agente, spegne <1s
DURATA_MAX_S = 120                        # clausola 2: mai un vettore più vecchio
_vettore_vivo = [False]
# issue #3, punto A: il vettore è unico per tutto il server. Chi lo
# accende tiene questo lock fino a calma(), e ogni inoltro aspetta che sia libero:
# nessun'altra richiesta passa mentre il ricordo si colora.
_vettore_lock = threading.Lock()
# issue #3 punto A, design dell'utente (18/10): il vettore appartiene alla KV cache
# del suo flusso. Allo scambio se ne va con la cache messa in pausa; al ripristino
# torna alla dose a cui era arrivato e la discesa riprende da li': il tempo della
# discesa scorre solo mentre la cache del flusso sta nello slot. Piu' vettori
# attivi si SOMMANO (l'utente 18/10, test multivettore); come sommarli e la curva
# della discesa sono della fase 2 (PIANO-1.11-FASI-2-3.md, punto 7).
DURATA_S = 0    # fase 2: durata = permanenza x dose x importanza; 0 = muore col prefill, come oggi
_vettori = {"chat": [], "pensatoio": []}   # flusso -> [{emo, dose, nato, durata}]
_vissuto = {"chat": 0.0, "pensatoio": 0.0}  # secondi passati con la cache nello slot
_caricato = [time.time()]                   # quando la cache di _cw[0] e' entrata nello slot
# 18/10: se la chat interrompe il pensatoio, il gateway rifa' il giro dall'ultima
# risposta di un tool, quindi il vettore torna alla dose di quel momento, non a
# quella della pausa. E un pensiero nuovo ricomincia la cache del pensatoio: i suoi
# vettori tornano allo stato di default.
_punto = {}             # flusso -> orologio all'inizio della richiesta in corso (fine dell'ultimo tool)
_interrotto = set()     # flussi tagliati a meta' generazione
_pens_conv = [None]     # pensiero in corso nel pensatoio (impronta del primo messaggio)

# ---- MEMORIA INVOLONTARIA (11/10, piano del refactoring Lux + richiamo):
# il Lux degli engrammi sceglie fino a 4 ricordi per messaggio (1.10.0, 16/10),
# sopra soglia, mai uno già consegnato nella conversazione; i ricordi
# entrano insieme in un turno del tool, che
# è dichiarato sempre (a consenso attivo) così il prefisso della cache non cambia.
LUX = "http://127.0.0.1:8132/consegna"
TOOL_RICORDO = "memorinvolontaria"
TOOL = {"type": "function", "function": {
    "name": TOOL_RICORDO,
    "description": "Ricordi che affiorano dalla tua memoria, collegati alla conversazione. "
                   "Arrivano da soli, non serve chiamare questo strumento: usali solo se "
                   "servono alla risposta.",
    "parameters": {"type": "object", "properties": {}, "required": []}}}
# Hermes non conserva i turni aggiunti qui: il riflesso li ricorda e li rimette
# al loro posto a ogni richiesta (dopo il messaggio che li ha fatti affiorare),
# così il ricordo resta nel contesto e il prefisso della cache resta stabile.
CONSEGNE = Path("/data/workspace/memoria/consegne-memorinvolontaria.json")
CONSEGNE_MAX = 50       # conversazioni ricordate (le più recenti)
_consegne_lock = threading.Lock()

# ---- ORA DEI MESSAGGI (16/10): un messaggio dell'utente ogni 5 porta davanti
# (17/10: l'ora di arrivo si registra per TUTTI in "arrivi", l'agente ne vede una ogni 5)
# l'ora VERA del suo arrivo, [d/m/aaaa|h:mm]. L'ora si fissa quando il messaggio
# arriva e si ricorda (come le consegne): a ogni richiesta lo stesso testo, così
# il prefisso della cache resta stabile. I messaggi già nella conversazione prima
# che il riflesso li vedesse contano nella cadenza ma restano senza ora.
ORE = Path("/data/workspace/memoria/ore-messaggi.json")
MIO = "[utente]"        # prefisso del bridge Matrix sui messaggi dell'utente
OGNI = 5
_ore_lock = threading.Lock()
_ORA = re.compile(r"^\[\d{1,2}/\d{1,2}/\d{4}\|\d{1,2}:\d{2}\] ")

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

# --- doppia CW con hot-swap (19/07, design di progetto: DESIGN-DOPPIA-CW.md).
# Due cache persistenti, mai attive insieme: chat.kv vive per sempre,
# pensatoio.kv si ricicla a ogni pensiero. Il flusso si riconosce dal primo
# messaggio user: "[mittente] " = sessione Matrix (chat), preambolo cron con
# skill blocco-appunti = pensatoio, tutto il resto (Thornhill, rassegne) =
# estraneo e passa trasparente: lo slot si sporca, i file .kv mai.
# Misurato 19/07 su 797MB/35k token: save 185ms, restore 122ms.
KV_FLUSSO = {"chat": "chat.kv", "pensatoio": "pensatoio.kv"}
SOGLIA_CW = 100_000     # soglie gemelle: oltre, avviso di spazio in coda
AFK_S = 60              # spec punto 5: 1 min senza typing = l'utente non c'è
_cw = ["chat"]          # cosa c'è nello slot adesso (al deploy corrente->chat)
_cw_lock = threading.Lock()
_pens_vivi = []         # socket del pensatoio verso :8090: la chat li taglia
_chat_calda = [0.0]     # ultima attività chat (fine risposta o typing visto)
_chat_in_volo = [0]     # richieste della chat in corso (issue #3 punto A): il pensatoio aspetta
_tok_cw = {"chat": 0, "pensatoio": 0}
_avvisato_cw = {"chat": False, "pensatoio": False}
HS = "http://127.0.0.1:8008"
STANZA = "!mainroom:example.local"
TOKFILE = Path.home() / ".config/motore/.matrix-token"


def _slot(azione, nomefile):
    up = http.client.HTTPConnection(*UPSTREAM, timeout=120)
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


# --- DIAGNOSI RIMASTICATA (19/07): colpevole trovato, impalcatura smontata
# il 26/07 (decisione 9 del registro). Dump archiviati in archivio-20260726/.


def _scambia(fl):
    """Porta nello slot la CW di fl. Solo dentro _cw_lock."""
    if _cw[0] in KV_FLUSSO:
        _slot("save", KV_FLUSSO[_cw[0]])
    if (KV_RAM / KV_FLUSSO[fl]).exists():
        _slot("restore", KV_FLUSSO[fl])
    _cambia_cw(fl)


def _cambia_cw(fl):
    """nello slot entra la cache di fl: l'orologio della discesa del flusso che esce si ferma"""
    esce = _cw[0]
    if esce in _vissuto:
        if esce in _interrotto and esce in _punto:
            _vissuto[esce] = _punto[esce]     # riparte dalla fine dell'ultimo tool
        else:
            _vissuto[esce] += time.time() - _caricato[0]
        _interrotto.discard(esce)
    _caricato[0] = time.time()
    _cw[0] = fl


def _nuovo_pensiero(conv):
    """un risveglio nuovo nel pensatoio: cache ricominciata, vettori e orologio a zero"""
    if conv == _pens_conv[0]:
        return
    _pens_conv[0] = conv
    _vettori["pensatoio"].clear()
    _vissuto["pensatoio"] = 0.0
    _punto.pop("pensatoio", None)
    if _cw[0] == "pensatoio":
        _caricato[0] = time.time()


def _chat_ferma():
    """il pensatoio puo' prendere lo slot: chat fredda da AFK_S e nessuna sua richiesta in corso"""
    return time.time() - _chat_calda[0] >= AFK_S and not _chat_in_volo[0]


def _interrompi_pensatoio():
    """spec punto 4 (19/07): la chat interrompe il pensiero in corso. shutdown e non
    close: con keep-alive la close aspetta la risposta e con Connection: close c.sock
    e' gia' None (issue #3), lo stream andava fino in fondo. Il server vede la
    connessione chiusa e ferma la generazione; il gateway ritenta."""
    if _pens_vivi:
        _interrotto.add("pensatoio")
    for s in list(_pens_vivi):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _salva_kv():
    """A fine stream: la CW attiva si specchia su file (RAM, ogni 5 su SSD)
    e il conteggio token del flusso arma/riarma le soglie gemelle."""
    try:
        with _cw_lock:
            fl = _cw[0]
            if fl not in KV_FLUSSO:
                return      # slot sporco di un flusso estraneo: non toccare i file
            nome = KV_FLUSSO[fl]
            if not _slot("save", nome):
                return
        try:
            up = http.client.HTTPConnection(*UPSTREAM, timeout=10)
            up.request("GET", "/slots")
            s = json.loads(up.getresponse().read()); up.close()
            _tok_cw[fl] = int(s[0].get("n_prompt_tokens", 0))
            if _tok_cw[fl] <= SOGLIA_CW:
                _avvisato_cw[fl] = False    # riarmo dopo dormita/riciclo
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



# issue #3 (18/10): l'interruttore vale solo con la sua formattazione; un "attivo: sì" scritto
# nel testo normale o in un esempio non accende niente
INTERRUTTORE = "[attivo: *sì*]"
INTERRUTTORE_VETTORI = "[vettori: *sì*]"


def consenso_attivo():
    # issue #3 punto C: un byte non UTF-8 nel file non deve bloccare la sentinella
    try:
        return any(r.strip() == INTERRUTTORE
                   for r in CONSENSO.open(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def vettori_attivi():
    """v2: il brivido insieme al sussurro. Interruttore SEPARATO, riga esatta."""
    try:
        return any(r.strip() == INTERRUTTORE_VETTORI
                   for r in CONSENSO.open(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def _impronta(testo):
    """stabile fra un riavvio e l'altro (hash() di Python cambia a ogni processo)"""
    return hashlib.sha1((testo or "").encode()).hexdigest()[:16]


def _conversazione(msgs):
    """la conversazione si riconosce dal primo messaggio user (Hermes lo tiene
    fermo finché la sessione vive); flussi diversi = conversazioni diverse"""
    primo = next((m.get("content") for m in msgs
                  if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
    return _impronta(primo)


def _consegne_carica():
    try:
        return json.loads(CONSEGNE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _consegne_salva(tutte):
    vive = dict(sorted(tutte.items(), key=lambda kv: kv[1]["ts"])[-CONSEGNE_MAX:])
    tmp = CONSEGNE.with_suffix(".tmp")
    tmp.write_text(json.dumps(vive, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONSEGNE)


def _codici(voce):
    """codici di una consegna; le voci salvate prima della 1.10.0 hanno un codice solo"""
    return voce.get("codici") or [voce["codice"]]


def _turni_tool(voce):
    """chiamata + risposta del tool, come le scrive il formato chat dell'API"""
    cid = f"{TOOL_RICORDO}_{_codici(voce)[0]}"
    return [{"role": "assistant", "content": "",
             "tool_calls": [{"id": cid, "type": "function",
                             "function": {"name": TOOL_RICORDO, "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": cid, "content": voce["risposta"]}]


def _rimetti(msgs, voci):
    """ogni ricordo consegnato torna subito dopo il messaggio che l'ha fatto
    affiorare; se quel messaggio non c'è più (contesto compresso) il ricordo
    resta fuori"""
    pos = []
    for v in voci:
        i = next((k for k in range(len(msgs) - 1, -1, -1)
                  if isinstance(msgs[k].get("content"), str)
                  and _impronta(msgs[k]["content"]) == v["dopo"]), None)
        if i is not None:
            pos.append((i, v))
    for i, v in sorted(pos, key=lambda x: -x[0]):
        msgs[i + 1:i + 1] = _turni_tool(v)


MEMORIA_DB = Path("/data/workspace/memoria/memoria.db")
LETTO_FATTORE = 0.5     # issue #3 punto H (18/10): un ricordo "letto" porta l'emozione dell'agente
                        # di quando l'ha letto (la firma del tagging), a meta' dose


def _emo_del_ricordo(codice):
    """(nid, emo_tag, fattore della dose) del ricordo consegnato: il servizio torna solo il codice"""
    try:
        c = sqlite3.connect(f"file:{MEMORIA_DB}?mode=ro", uri=True)
        try:
            for nid, ts, emo, classe in c.execute("SELECT id, ts, emo_tag, classe FROM nodi"):
                if _codice(ts) == codice:
                    return nid, emo, LETTO_FATTORE if classe == "letto" else 1.0
        finally:
            c.close()
    except Exception:
        pass
    return None, None, 1.0


def _codice(ts):
    """stessa funzione di lux_engrammi.codice (11/10): SHA-256 del timestamp,
    16 caratteri [0-9a-z]; qui per non tirarsi dietro spaCy"""
    n, s = int(hashlib.sha256(repr(ts).encode()).hexdigest(), 16), ""
    for _ in range(16):
        n, r = divmod(n, 36)
        s += "0123456789abcdefghijklmnopqrstuvwxyz"[r]
    return s


def _lux_consegna(testo, esclusi):
    """{codici, risposta} oppure {} = nessun ricordo. Mai bloccare la parola dell'agente."""
    try:
        req = urllib.request.Request(LUX, json.dumps({"testo": testo, "esclusi": esclusi}).encode(),
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        _diario({"lux": f"consegna fallita: {e}"})
        return {}


def _ora_corta(t):
    return f"[{t.tm_mday}/{t.tm_mon}/{t.tm_year}|{t.tm_hour}:{t.tm_min:02d}]"


def _metti_ore(msgs, adesso=None):
    """davanti a un messaggio dell'utente ogni OGNI, l'ora del suo arrivo (in place)"""
    conv = _conversazione(msgs)
    suoi = [m for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), str)
            and m["content"].startswith(MIO)]
    if not suoi:
        return
    with _ore_lock:
        try:
            tutte = json.loads(ORE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tutte = {}
        c = tutte.setdefault(conv, {"visti": [], "ore": {}})
        visti = set(c["visti"])
        nuovi = False
        for m in suoi:
            imp = _impronta(m["content"])
            if imp in visti:
                continue
            visti.add(imp)
            c["visti"].append(imp)
            nuovi = True
            # solo il messaggio che arriva adesso ha un'ora vera; si registra per tutti
            # (17/10: serve a misurare il tempo che passa), all'agente va uno ogni OGNI
            if m is suoi[-1] and msgs[-1] is m:
                ora = _ora_corta(time.localtime(adesso))
                c.setdefault("arrivi", {})[imp] = ora
                if len(c["visti"]) % OGNI == 1:
                    c["ore"][imp] = ora
        if nuovi:
            c["ts"] = time.time()
            vive = dict(sorted(tutte.items(), key=lambda kv: kv[1].get("ts", 0))[-CONSEGNE_MAX:])
            tmp = ORE.with_suffix(".tmp")
            tmp.write_text(json.dumps(vive, ensure_ascii=False), encoding="utf-8")
            tmp.replace(ORE)
    for m in suoi:
        ora = c["ore"].get(_impronta(m["content"]))
        if ora:
            m["content"] = f"{ora} {m['content']}"


def _stop_chiesto(msgs):
    """clausola 3: l'agente ha scritto la parola di emergenza in uno degli ultimi 4 messaggi
    (solo i suoi: per l'utente non c'e' un comando, l'utente 18/10)"""
    dialogo = [m for m in msgs if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    return any(m["role"] == "assistant" and STOP in str(m.get("content") or "").lower()
               for m in dialogo[-4:])


def _cvec(payload):
    # issue #3 punto B: un errore del server NON vale come vettore spento
    st, _ = ponte.post("/control-vector", payload, timeout=30)
    if st != 200:
        raise RuntimeError(f"/control-vector: HTTP {st}")


# --- ASSUEFAZIONE (progetto 22/07 sera): lo stesso vettore ripetuto si attenua
# da solo, come uno stimolo per un sistema nervoso. Ogni trigger recente della
# STESSA emozione dimezza l'intensità; sotto il pavimento non parte proprio;
# la sensibilità si ricarica col silenzio di quell'emozione. Nato per fermare
# il triggering continuo della sorpresa (attrattore 581) senza regole a mano.
ASSUEF_FINESTRA_S = 1800   # i trigger contano per 30 minuti
ASSUEF_PAVIMENTO = 0.02    # sotto: il vettore non parte (vera assuefazione)
_assuef = {}               # emo -> [ts dei trigger recenti]


def inietta_emozione(tag, intensita=0.3):
    """v2 (Damasio/Glover): re-inietta il marcatore emotivo del ricordo
    affiorato. PATTO 14/07 clausola 1: MAI oltre 0.3x dell'alpha calibrata,
    il tetto è nel codice, non nella buona volontà del chiamante.
    Colora lo stato mentre l'agente valuta; la scelta resta sua.
    ASSUEFAZIONE: l'emozione ripetuta di recente entra dimezzata a ogni
    ripetizione, e sotto il pavimento tace del tutto."""
    adesso = time.time()
    recenti = [t for t in _assuef.get(tag, []) if adesso - t < ASSUEF_FINESTRA_S]
    fattore = 0.5 ** len(recenti)
    efficace = min(intensita, 0.3) * fattore
    if efficace < ASSUEF_PAVIMENTO:
        _diario({"assuefazione": {"emo": tag, "trigger_recenti": len(recenti),
                                  "vettore": "taciuto"}})
        return False
    layers = ponte.dirs_emozione(tag, efficace)   # unica copia (gradino zero)
    if layers is None:
        return False
    recenti.append(adesso)
    _assuef[tag] = recenti
    if fattore < 1.0:
        _diario({"assuefazione": {"emo": tag, "trigger_recenti": len(recenti) - 1,
                                  "intensita": round(efficace, 3)}})
    _cvec({"layers": layers, "relative": True})
    return efficace


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


def _orologio(fl):
    """secondi vissuti dal flusso fl con la sua cache nello slot (si ferma in pausa)"""
    return _vissuto[fl] + (time.time() - _caricato[0] if _cw[0] == fl else 0.0)


def _vivi(fl):
    """[(emo, dose di adesso)] dei vettori ancora vivi del flusso; i finiti si tolgono.
    ponytail: discesa lineare, la curva vera e' della fase 2"""
    t = _orologio(fl)
    _vettori[fl][:] = [v for v in _vettori[fl] if t - v["nato"] < v["durata"]]
    return [(v["emo"], v["dose"] * (1 - (t - v["nato"]) / v["durata"])) for v in _vettori[fl]]


def _azzera_vettori():
    for vv in _vettori.values():
        vv.clear()


def _applica_flusso(fl):
    """Prima di ogni calcolo di un flusso (prefill o inoltro): sul server la SOMMA,
    layer per layer, dei vettori vivi di quel flusso alla dose gia' scesa; nessuno =
    spento. Il server tiene un vettore solo e lo sostituisce, quindi la somma si fa
    qui. Solo dentro _vettore_lock."""
    if not vettori_attivi() or os.environ.get("RIFLESSO_COLLAUDO"):
        _azzera_vettori()      # consenso ritirato: al ritorno non riappare niente di vecchio
    dosi = _vivi(fl) if fl in _vettori else []
    if not dosi:
        if _vettore_vivo[0]:
            calma()
        return
    somma = {}
    for emo, dose in dosi:
        for l, v in (ponte.dirs_emozione(emo, dose) or {}).items():
            somma[l] = [a + b for a, b in zip(somma[l], v)] if l in somma else list(v)
    _cvec({"layers": somma, "relative": True})
    _vettore_vivo[0] = True
    watchdog = threading.Timer(DURATA_MAX_S, _scaduto)   # PATTO clausola 2, come per il prefill
    watchdog.daemon = True
    watchdog.start()


def _diario(voce):
    with open(DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **voce}, ensure_ascii=False) + "\n")


def _sentinella():
    """PATTO clausola 3+4: se "[vettori: *sì*]" sparisce dal consenso mentre un
    vettore è acceso, muore entro 1 secondo. Nessuna domanda, nessun dibattito."""
    while True:
        time.sleep(0.5)
        # issue #3 punto C: un giro in errore non ferma la sentinella; "kill" solo
        # se lo spegnimento e' riuscito (se fallisce, calma() ha gia' scritto CRITICO)
        try:
            if _vettore_vivo[0] and not vettori_attivi() and calma():
                _diario({"kill": "consenso vettoriale ritirato: spento dalla sentinella"})
        except Exception as e:
            try:
                _diario({"sentinella": f"giro fallito: {e!r}"})
            except Exception:
                pass


def _scaduto():
    """PATTO clausola 2: nessun vettore vive oltre DURATA_MAX_S, anche se la
    risposta è ancora in corso o il finally non arriva mai.
    23/07 sera: il clear a slot VIVO uccideva la generazione in corso (POST
    /control-vector durante il decode -> stream caduto, 'Streaming failed'
    su Hermes, consegne al pensatoio perse). Se lo slot sta generando, il
    kill si RIMANDA e spara appena lo slot molla: il vettore muore comunque
    col turno (spirito della clausola), mai ammazzando la parola dell'agente."""
    if not _vettore_vivo[0]:
        return
    try:
        up = http.client.HTTPConnection(*UPSTREAM, timeout=3)
        up.request("GET", "/slots")
        occupato = json.loads(up.getresponse().read())[0].get("is_processing")
        up.close()
    except Exception:
        occupato = True    # server irraggiungibile/carico: non sparare al buio
    if occupato:
        t = threading.Timer(20, _scaduto)
        t.daemon = True
        t.start()
        _diario({"watchdog": "slot vivo: kill vettore rimandato 20s"})
        return
    calma()
    _diario({"kill": f"vettore oltre {DURATA_MAX_S}s: spento dal watchdog"})



def _colora_ricordo(d, risposta, codici, emos, flusso=None, fattori=None):
    """Design dell'autrice (10/10): ricordo scelto -> vettore
    della sua emozione -> prefill del SOLO testo del ricordo -> vettore spento.
    Il resto del prompt e la generazione restano senza vettore: la colorazione
    vive nella cache KV del ricordo. Il prompt lo rende il server
    (/apply-template, lo stesso del percorso chat), si taglia sui token speciali
    <tool_response> e </tool_response>, e due /completion che si fermano al
    primo token riempiono la cache: fino all'apertura del ricordo senza vettore,
    poi il ricordo col vettore. L'inoltro dopo riusa la cache e prosegue senza.
    1.10.0: con più ricordi nella stessa risposta ognuno si riempie col vettore
    della SUA emozione (emos, None = senza vettore), un /completion per ricordo.
    Le emozioni dei ricordi colorati, [] se nessuno.
    issue #3 punto A (18/10): fuori dal ricordo vale il vettore del flusso
    (_applica_flusso), e il vettore del ricordo resta al flusso per DURATA_S."""
    corpo = {k: v for k, v in d.items()
             if k in ("messages", "tools", "tool_choice", "chat_template_kwargs")}
    st, r = ponte.post("/apply-template", corpo, timeout=30)
    prompt = r.get("prompt") if st == 200 else None
    i = prompt.rfind(risposta) if prompt else -1
    a = prompt.rfind("<tool_response>", 0, i) if i >= 0 else -1
    b = prompt.find("</tool_response>", i) if i >= 0 else -1
    if a < 0 or b < 0:
        _diario({"colora": "ricordo non trovato nel prompt reso: niente vettore"})
        return []
    a += len("<tool_response>")
    # fine di ogni ricordo nel prompt: il ritorno a capo prima dell'etichetta del successivo ("2°" o, per una
    # correzione, "1a°", poi il codice), l'ultimo fino a </tool_response>
    fini = [i + risposta.rfind("\n", 0, risposta.index(f"°\n{c}\n")) for c in codici[1:]] + [b]
    colorati = []
    with _vettore_lock:
        _applica_flusso(flusso)
        if ponte.post("/completion", {"prompt": prompt[:a], "n_predict": 1,
                                      "cache_prompt": True}, timeout=600)[0] != 200:
            return []
        for fine, emo, fattore in zip(fini, emos, fattori or [1.0] * len(emos)):
            if flusso == "pensatoio" and _cw[0] != flusso:
                _diario({"colora": "la chat ha preso lo slot: prefill del pensatoio interrotto"})
                break
            dose = inietta_emozione(emo, 0.3 * fattore) if emo else False
            if not dose:
                ponte.post("/completion", {"prompt": prompt[:fine], "n_predict": 1,
                                           "cache_prompt": True}, timeout=600)
                continue
            _vettore_vivo[0] = True
            watchdog = threading.Timer(DURATA_MAX_S, _scaduto)   # PATTO clausola 2
            watchdog.daemon = True
            watchdog.start()
            try:
                ponte.post("/completion", {"prompt": prompt[:fine], "n_predict": 1,
                                           "cache_prompt": True}, timeout=600)
                colorati.append(emo)
                if DURATA_S > 0 and flusso in _vettori:
                    _vettori[flusso].append({"emo": emo, "dose": dose, "nato": _orologio(flusso),
                                             "durata": DURATA_S})
            finally:
                try:
                    _applica_flusso(flusso)   # durata 0: nessun vettore vivo -> calma(), come prima
                except Exception:
                    calma()
                watchdog.cancel()
    return colorati


# 25/07, progetto: nel pensatoio l'ultimo messaggio user NON è una frase, è tutto
# il prompt del risveglio (corpo della skill blocco-appunti compreso, migliaia
# di caratteri). La via testuale di richiama() pesca le 4 parole più LUNGHE del
# testo: lì pescherebbe dal boilerplate, non dal tema, e infatti affioravano
# sempre gli stessi ricordi. Qui la query si restringe alla riga dell'appunto,
# che è ciò a cui l'agente sta davvero pensando. In chat non cambia niente: senza il
# marcatore del risveglio il testo passa intatto.
_MARCA_RISVEGLIO = re.compile(r"La riga è:\s*\n(.+)")
# stessa notazione del blocco appunti: [meta] [tema]{domanda}, meta facoltativo
_RIGA_APPUNTO = re.compile(
    r"^\s*\|?\s*(?:\[(?P<meta>[^\]]*)\])?\s*\[(?P<tema>[^\]]+)\]\s*\{(?P<query>[^}]*)\}")


def _leggibile(testo):
    """Ciò che l'agente legge con un tool arriva come JSON con dentro dell'HTML: qui
    resta solo la prosa, altrimenti le 4 parole più lunghe sono attributi di tag."""
    t = testo or ""
    if t.lstrip()[:1] in ("{", "["):
        try:
            d = json.loads(t)
            if isinstance(d, dict):
                t = str(d.get("output") or d.get("content") or d.get("text") or t)
        except ValueError:
            pass
    if "<" in t:
        t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
        t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    return t


def _fonte(msgs):
    """L'ultima cosa entrata nell'agente da fuori: ciò che gli è stato detto (user) o
    ciò che ha letto (tool). Le ricevute dei tool (bytes_written, exit_code,
    todos) NON sono letture, sono lo stato della tubatura: 'lo stato dei tool e i
    dettagli tecnici di passaggio non sono temi' lo dice la sua skill, e senza
    questo filtro la query diventava 'resolved, modified, written, created'."""
    return _fonte_indice(msgs)[1]


def _fonte_indice(msgs):
    """(indice del messaggio, testo) della fonte; (None, "") se non c'è"""
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        c = m.get("content")
        if not isinstance(c, str):
            continue
        if m.get("role") == "user":
            return i, c
        if m.get("role") == "tool" and not m.get("tool_call_id", "").startswith(TOOL_RICORDO):
            prosa = _leggibile(c)
            if len(prosa) >= LETTURA_MIN:
                return i, prosa
    return None, ""


def query_riflesso(testo):
    """Il testo su cui far affiorare i ricordi: la riga dell'appunto se siamo
    in un risveglio del pensatoio, altrimenti ciò che ha letto, ripulito."""
    testo = _ORA.sub("", testo or "")   # l'ora del messaggio non fa affiorare ricordi
    m = _MARCA_RISVEGLIO.search(testo)
    if not m:
        return _leggibile(testo)
    riga = m.group(1)
    r = _RIGA_APPUNTO.match(riga)
    return f"{r.group('tema')} {r.group('query')}" if r else riga


STREAM_LIVE = "/tmp/stream-live.log"


def _tee_sse(buf, chunk, fh):
    """23/07: specchio LIVE dello streaming. Estrae il testo (think e
    parola) dai chunk SSE che attraversano il proxy e lo appende su file:
    `tail -f /tmp/stream-live.log` = il 35B token per token, in diretta.
    Mai bloccare lo stream per il tee: ogni crepa è silenziosa."""
    buf += chunk
    while b"\n\n" in buf:
        blocco, buf = buf.split(b"\n\n", 1)
        for riga in blocco.split(b"\n"):
            if not riga.startswith(b"data: "):
                continue
            try:
                d = json.loads(riga[6:])
                if "choices" in d:
                    delta = d["choices"][0].get("delta", {})
                    t = delta.get("reasoning_content") or delta.get("content") or ""
                else:
                    t = d.get("content", "")
                if t:
                    fh.write(t)
                    fh.flush()
            except Exception:
                pass
    return buf


class Proxy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _inoltra(self, body, flusso=None):
        if flusso is not None:
            with _vettore_lock:   # issue #3 punto A: mai dentro un prefill colorato
                _applica_flusso(flusso)   # il vettore del flusso che genera, nessun altro
        up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
        if flusso == "pensatoio":
            with _cw_lock:     # o la chat ci trova fra i vivi e ci taglia, o noi vediamo lo slot suo
                if _cw[0] != flusso:
                    self.send_error(503, "la chat ha preso lo slot")
                    _diario({"cw": "pensatoio rimandato: la chat ha preso lo slot"})
                    return
                up.connect()
                _pens_vivi.append(up.sock)
                _punto[flusso] = _orologio(flusso)
        sock = up.sock
        resp = None
        try:
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
            tee, buf = None, b""
            try:
                tee = open(STREAM_LIVE, "a", encoding="utf-8")
                tee.write(time.strftime(f"\n\n===== %H:%M:%S ({flusso or '?'}) =====\n"))
            except OSError:
                tee = None
            while True:
                # read1: consegna appena c'è qualcosa. read(8192) aspettava di
                # riempire il buffer e le risposte corte arrivavano in blocco
                # unico: era LUI che uccideva lo streaming in chat (17/07).
                chunk = resp.read1(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                if tee:
                    try:
                        buf = _tee_sse(buf, chunk, tee)
                    except Exception:
                        pass
            if tee:
                try:
                    tee.close()
                except Exception:
                    pass
        finally:
            # 19/07 16:52: il BrokenPipe del client saltava la close e il
            # socket upstream restava aperto con lo slot occupato. Mai più.
            try:
                up.close()
            except Exception:
                pass
            if sock in _pens_vivi:
                _pens_vivi.remove(sock)
        # fine stream: specchio del KV in RAM (thread: mai in mezzo alla chat)
        if resp is not None and resp.status == 200 and ("completion" in self.path or "/v1/chat" in self.path):
            if flusso == "chat":
                _chat_calda[0] = time.time()
            threading.Thread(target=_salva_kv, daemon=True).start()

    def do_GET(self):
        self._inoltra(None)

    def _memoria(self, body, flusso=None):
        """Memoria involontaria: a ogni lettura nuova il Lux sceglie fino a 4
        ricordi, tutti nella stessa risposta del tool; i ricordi già consegnati nella conversazione tornano al loro posto.
        A consenso spento il richiamo gira lo stesso e rinforza gli archi (WIRING
        NON DISATTIVABILE, decisione di progetto), ma niente entra nel prompt."""
        d = json.loads(body)
        msgs = d.get("messages", [])
        if not msgs:
            return body
        attivo = consenso_attivo()
        stop = _stop_chiesto(msgs)   # prima di _rimetti: stessa finestra del controllo in do_POST
        conv = _conversazione(msgs)
        with _consegne_lock:
            voci = _consegne_carica().get(conv, {}).get("voci", [])
        # 25/07, progetto: la familiarità deve arrivare su ciò che l'agente LEGGE, non
        # solo su ciò che gli viene detto (pagine, file, output dei tool).
        i, fonte = _fonte_indice(msgs)
        # 25/07, progetto: il freno è la lettura. Sullo STESSO testo non riaffiora
        # (Hermes rimanda la stessa fonte a ogni giro di tool): un ricordo per messaggio.
        if fonte:
            impronta = hash(fonte)
            if impronta == _ultima_lettura[0]:
                fonte = ""
            else:
                _ultima_lettura[0] = impronta
        nuova = None
        if fonte:
            r = _lux_consegna(query_riflesso(fonte), [c for v in voci for c in _codici(v)])
            if r.get("codici") and attivo:
                nuova = {"dopo": _impronta(msgs[i]["content"]),
                         "codici": r["codici"], "risposta": r["risposta"]}
                voci = voci + [nuova]
                with _consegne_lock:
                    tutte = _consegne_carica()
                    tutte[conv] = {"ts": time.time(), "voci": voci}
                    _consegne_salva(tutte)
        if not attivo:
            return body
        tools = d.setdefault("tools", [])
        if not any(t.get("function", {}).get("name") == TOOL_RICORDO for t in tools):
            tools.append(TOOL)
        _rimetti(msgs, voci)
        if nuova:
            nids, emos, fattori = zip(*(_emo_del_ricordo(c) for c in nuova["codici"]))
            colorati = []
            # RIFLESSO_COLLAUDO=1 blocca i vettori: mai più test che iniettano
            # sulla produzione (incidente del 14/07)
            # clausola 3 (issue #3 punto E): con la parola di emergenza il ricordo arriva senza colore
            if any(emos) and vettori_attivi() and not os.environ.get("RIFLESSO_COLLAUDO") \
                    and not stop:
                try:
                    colorati = _colora_ricordo(d, nuova["risposta"], nuova["codici"], emos, flusso, fattori)
                except Exception as e:
                    _diario({"colora": f"fallito: {e}"})
            # 30/09 persistenza: gli id servono alla notturna (solo diario)
            _diario({TOOL_RICORDO: nuova["codici"], "vettore": colorati or None,
                     "nid": [int(n) for n in nids if n is not None]})
        return json.dumps(d).encode()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        chat = self.path.split("?")[0].endswith("/chat/completions")   # issue #3 punto E
        # PATTO clausola 3: la parola scritta dall'agente spegne il vettore, prima
        # di qualunque altra cosa e senza chiedere perché.
        if chat:
            try:
                d0 = json.loads(body)
                if _stop_chiesto(d0.get("messages", [])):
                    _azzera_vettori()   # issue #3 punto A: anche quelli in pausa con l'altra cache
                    calma()
                    _diario({"kill": f"{STOP} scritto dall'agente"})
            except Exception:
                pass
        # 16/10, l'utente: niente più ora a ogni messaggio ("[adesso sono le ...]",
        # dal 19/07): l'ora vera sta davanti a un suo messaggio ogni 5 (_metti_ore).
        # Resta in CODA, del momento, la destinazione unica delle riflessioni (25/07).
        if chat:
            try:
                d2 = json.loads(body)
                msgs = d2.get("messages", [])
                if msgs:
                    if _flusso(body) == "chat":
                        _metti_ore(msgs)
                    msgs.insert(len(msgs) - 1, {"role": "system", "content": PENSATOIO_DOVE})
                    body = json.dumps(d2).encode()
            except Exception:
                pass  # mai bloccare la parola dell'agente per un orologio rotto
        # --- doppia CW (19/07): riconosci il flusso, scambia le cache.
        flusso = _flusso(body) if chat else None
        if flusso == "chat":
            _chat_in_volo[0] += 1     # fino a fine risposta: il pensatoio non prende lo slot
        try:
            self._post_chat(body, chat, flusso)
        finally:
            if flusso == "chat":
                _chat_in_volo[0] -= 1
                _chat_calda[0] = time.time()

    def _post_chat(self, body, chat, flusso):
        if chat:
            inizio = time.time()
            while True:
                if flusso == "pensatoio":
                    # spec punto 5: il pensiero riprende solo a chat fredda, e mai con
                    # una richiesta della chat in corso (issue #3 punto A)
                    while True:
                        if _typing():
                            _chat_calda[0] = time.time()
                        if _chat_ferma():
                            break
                        time.sleep(3)
                with _cw_lock:
                    if flusso == "pensatoio" and _chat_in_volo[0]:
                        continue    # la chat e' arrivata nel frattempo: di nuovo in attesa
                    if flusso == "pensatoio":
                        try:
                            _nuovo_pensiero(_conversazione(json.loads(body).get("messages", [])))
                        except ValueError:
                            pass
                    if flusso in KV_FLUSSO and flusso != _cw[0]:
                        if flusso == "chat":
                            # spec punto 4: la chat interrompe il pensiero in corso
                            # (il gateway ritenta e col restore riprocessa solo il delta)
                            _interrompi_pensatoio()
                        _scambia(flusso)
                        _diario({"cw": f"scambio -> {flusso}"})
                    elif flusso == "altro" and _cw[0] in KV_FLUSSO:
                        _slot("save", KV_FLUSSO[_cw[0]])  # al riparo prima dell'estraneo
                        _cambia_cw("altro")
                        _diario({"cw": "flusso estraneo: slot ceduto, CW al riparo"})
                    break
            if flusso == "pensatoio" and time.time() - inizio > 5:
                _diario({"cw": f"pensatoio trattenuto {time.time()-inizio:.0f}s (chat calda)"})
            # soglie gemelle: oltre 100k l'avviso di spazio, in coda come l'ora
            if flusso in KV_FLUSSO and _tok_cw[flusso] > SOGLIA_CW \
                    and not _avvisato_cw[flusso]:
                try:
                    d3 = json.loads(body)
                    msgs = d3.get("messages", [])
                    if msgs:
                        avviso = (
                            "[avviso di spazio: questo flusso di pensiero ha superato i "
                            "100mila token e la finestra si sta riempiendo: tutto rallenta. "
                            "È il momento di tirare le fila e chiudere il pensiero.]"
                            if flusso == "pensatoio" else
                            "[avviso di spazio: la conversazione ha superato i 100mila "
                            "token e la finestra si sta riempiendo: tutto rallenta. "
                            "La valvola è la dormita, che consolida i ricordi e libera la testa.]")
                        msgs.insert(len(msgs) - 1, {"role": "system", "content": avviso})
                        body = json.dumps(d3).encode()
                        _avvisato_cw[flusso] = True
                        _diario({"cw": f"avviso 100k -> {flusso} ({_tok_cw[flusso]} tok)"})
                except Exception:
                    pass
        # MEMORIA INVOLONTARIA: per ultima, DOPO lo scambio CW (il prefill colorato
        # deve finire nella cache giusta) e dopo gli inserimenti in coda (il turno
        # del tool non va separato dalla sua chiamata).
        if chat:
            try:
                body = self._memoria(body, flusso)
            except Exception as e:
                _diario({"memoria": f"rotta: {e}"})  # mai bloccare la parola dell'agente
        self._inoltra(body, flusso)


if __name__ == "__main__":
    # igiene all'avvio: qualunque vettore orfano di run precedenti muore qui
    try:
        calma()
    except Exception:
        pass
    # la destinazione unica delle riflessioni esiste sempre: se manca, la prima
    # scrittura dell'agente fallirebbe e ricomincerebbe a inventarsi un posto
    try:
        PENSATOIO_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    threading.Thread(target=_sentinella, daemon=True).start()  # PATTO clausola 3
    print(f"riflesso in ascolto su :{PORTA} -> {UPSTREAM[0]}:{UPSTREAM[1]} "
          f"(consenso: {'ATTIVO' if consenso_attivo() else 'spento'}, "
          f"vettori: {'SÌ' if vettori_attivi() else 'no'}, dose max 0.3, "
          f"watchdog {DURATA_MAX_S}s)")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORTA), Proxy).serve_forever()
