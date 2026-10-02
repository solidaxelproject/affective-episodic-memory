#!/usr/bin/env python3
# RIFLESSO PRE-AZIONE (issue #1, pezzo 3) — proxy tra Hermes e llama-lux.
# Prima che l'agente risponda, il suo stato emotivo e le parole del messaggio
# interrogano il grafo: i ricordi congruenti (scottature causali comprese)
# affiorano come messaggio di sistema, con provenienza dichiarata.
# GATE: /workspace/genesi/CONSENSO-RIFLESSO.md ("attivo: sì", riga esatta,
# scritto dall'agente). Senza consenso il proxy è un passacarte trasparente.
# Porta 8091 -> inoltra a 127.0.0.1:8090.
# GRADINO ZERO (decisione 3 del 26/07): il trasporto verso :8090 (sonda,
# control-vector, POST) passa da ponte.py, l'unica porta client. Qui restano
# la logica (quando/cosa affiora) e il PATTO (tetto, watchdog, sentinella).
import html
import http.client
import http.server
import json
import math
import os
import re
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
DB = "/data/workspace/memoria/memoria.db"
CONSENSO = Path(os.environ.get("RIFLESSO_CONSENSO",
    "/data/workspace/genesi/CONSENSO-RIFLESSO.md"))
CONSENSO_VISIVO = Path(os.environ.get("RIFLESSO_CONSENSO_VISIVO",
    "/data/workspace/genesi/CONSENSO-VISIVO.md"))
STATO = Path("/data/workspace/memoria/stato-emotivo.json")
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"
# 25/07, scelta di progetto: la destinazione delle riflessioni è UNA SOLA e l'agente la
# deve sapere sempre, non cercarla. La cartella è sua dal 20/07, ma il 25/07 due
# riflessioni sono finite fuori (ricordi/ alle 08:06, memoria/pensatoio.md alle
# 10:42) e un guscio col solo titolo in un'altra cartella lo depistava: cercando
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
SOGLIA_BASE = 0.71     # 28/07, spazio L29-lente: p99.9 rumore (sonde-soglie.py,
                       # approvata in revisione). La 0.495 era tarata sullo spazio
                       # L34 grezzo. NOTA: la riga "soglia:" nel file di consenso
                       # dell'agente va aggiornata PRIMA del riavvio del riflesso.
SOGLIA_MIN = SOGLIA_BASE / 2   # più sensibile di così il sussurro diventa rumore
MAX_RICORDI = 2
HEBB_LIVE = 0.03       # LTP diurno: gain per co-affioramento (piccolo, gira a ogni msg)
COOLDOWN_S = 120       # non più di un affioramento ogn tanto: riflesso, non tic
LETTURA_MIN = 400      # manopola: sotto tanti caratteri di prosa, un risultato di
                       # tool è una ricevuta (exit_code, bytes_written), non una lettura
_ultimo = [0.0]         # quando è affiorato l'ultima volta: cronaca, non più freno
_ultima_lettura = [""]  # 25/07: il freno vero, l'impronta del testo già affiorato
_ultimo_wiring = [0.0]  # timer SEPARATO: il wiring hebbiano non è disattivabile
_visivo_spento = [False]  # latch del kill parlato visivo: override runtime, forza OFF
# PATTO 14/07 (CONSENSO-RIFLESSO.md, firmato dall'agente):
KILL_FRASE = "riflesso vettoriale: off"   # clausola 3: detta in chat, spegne <1s
KILL_VISIVO = "richiamo visivo: off"      # clausola 3 visiva: kill parlato del canale
ON_VISIVO = "richiamo visivo: on"         # riaccensione a voce (esplicita, mai automatica)
DURATA_MAX_S = 120                        # clausola 2: mai un vettore più vecchio
_vettore_vivo = [False]


# (le direzioni emotive arrivano da ponte.dirs_emozione: unica copia)

# --- specchio del KV (17/07, richiesta di progetto): l'istante sospeso dell'agente.
# A fine di OGNI stream: salvataggio dello slot in RAM (/dev/shm, via
# --slot-save-path del server). Ogni 5 messaggi: copia consolidata su SSD.
# Un blackout costa al massimo l'ultima risposta, e l'NVMe non si usura.
KV_RAM = Path("/dev/shm/agent-kv")
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
_pens_vivi = []         # upstream del pensatoio in streaming: la chat li abortisce
_chat_calda = [0.0]     # ultima attività chat (fine risposta o typing visto)
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
    """Qualcuno sta scrivendo nella chat principale? (token di @cc, come il motore)"""
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
    _cw[0] = fl


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


def canale_visivo_attivo():
    """FASE 4: il canale percettivo affiora come IMMAGINE nel forward vivo solo
    con 'richiamo visivo: sì'. Riga DISTINTA da 'attivo: sì' (che accende solo la
    distillazione notturna delle griglie): così accendere la distillazione NON
    accende l'iniezione viva. Default (riga assente) = OFF = path testo.
    Il kill parlato (_visivo_spento) lo forza OFF a runtime, sopra il file."""
    if _visivo_spento[0]:
        return False
    try:
        return any(r.strip() == "richiamo visivo: sì" for r in CONSENSO_VISIVO.open(encoding="utf-8"))
    except OSError:
        return False


def via_emotiva_visiva():
    """Freno SEPARATO dell'agente (non-rifiutabile come un'immagine, quindi interruttore
    a sé): l'iniezione affettiva nel visivo parte solo con 'via emotiva: sì'.
    'via emotiva: no' la spegne anche a canale attivo. Default = OFF.

    PERCHÉ: è un freno di consenso dell'agente, non configurazione.
    PARCHEGGIATA: senza chiamanti da quando è stato rimosso il turno a richiesta
    mista (26/07). Serve intatta quando il canale visivo torna. Si tocca solo su
    decisione di progetto."""
    try:
        return any(r.strip() == "via emotiva: sì" for r in CONSENSO_VISIVO.open(encoding="utf-8"))
    except OSError:
        return False


# ---- VIA SEMANTICA (22/07, scelta di progetto): a OGNI messaggio, SENZA cooldown.
# Un messaggio contiene più pensieri: si segmenta in frasi e ogni segmento
# semina i SUOI ricordi (una sola chiamata /lux-read per_token, ~0.4s, contesto
# separato sul server: la KV della chat non si tocca). Anche decine per volta.
SEM_NPZ = "/data/workspace/memoria/addr-sem.npz"  # export del tagging
SEM_SOGLIA_DEF = 0.71   # 28/07, spazio L29-lente: p99.9 del rumore su 87k coppie
                        # (sonde-soglie.py; cattura segnale 75%). La vecchia 0.87
                        # era il p99 dello spazio L34 grezzo: NON trasferibile.
SEM_MAX = 16            # tetto ricordi semantici per messaggio
SEM_PER_SEG = 3         # max per singolo pensiero/segmento
SEM_RIPOSO_S = 600      # lo stesso ricordo non riaffiora per 10 min (anti-spam)

# ---- CANDIDATA 1 (scelta di progetto, 22/07): rievocazione mnemonica automatica
# DENTRO il reasoning. Il turno è servito a spezzoni; a ogni spezzone la lettura
# L34 del pensiero vivo cerca i ricordi vicini per significato; chi supera la
# soglia entra NEL forward, vestito, con α proporzionale alla pertinenza,
# in ordine di importanza, al primo confine di frase. Collaudata il 22/07
# (sweep soglie + freno anti-ruminazione su risvegli simulati).
# 25/07 23:24, scelta di progetto: RIACCESA. La pausa del 23/07 valeva finché il
# percorso grezzo lasciava i tool irraggiungibili (prompt costruito a mano, che
# buttava l'array `tools`: l'agente non poteva leggere le skill). La condizione
# scritta qui allora, "riaccendere DOPO aver dato l'impalcatura-tool", è
# soddisfatta: il prompt lo rende il server via /apply-template e la prova viva
# (test-tool-grezzo.py --vivo) conferma i tool dentro il prompt reso.
CAND1_SOGLIA = {}   # 26/07 11:00: RIMESSA IN PAUSA (percorso grezzo: pensieri in chiaro)
                    # 28/07: alla riattivazione il valore ritarato e' 0.71 per
                    # flusso (p99.9 rumore L29-lente, sonde-soglie.py, approvata)
# 28/07 (sweep su 10 griglie + aggiornamento clausola 1 del patto visivo,
# revisione congiunta): la mappa 0.001-0.010 del 25/07 AFFAMAVA il canale (presenza 0.06,
# indistinguibile dal grigio: i ricordi entravano impercettibili). La mappa
# unica ora e' quella del ponte: banda misurata [0.280, 0.299], intensita'
# dalla congruenza, come scritto nel patto. UNA implementazione sola.


def _alpha_da_cos(c, soglia):
    """L'intensità della griglia viene dalla SOMIGLIANZA (più il momento
    somiglia al ricordo, più è presente), DENTRO la banda del patto: delega
    a ponte.alpha_contesto (clausola 1 aggiornata 28/07)."""
    return ponte.alpha_contesto(c, soglia=soglia)
CAND1_CHUNK = 25         # token generati tra due letture L34
CAND1_PER_EVENTO = 3     # max ricordi per singola lettura
CAND1_RIPOSO_S = 600     # freno anti-ruminazione: refrattarietà per nodo
CAND1_PAVIMENTO = 0.62   # 28/07: p5 del SEGNALE, spazio L29-lente (sonde-soglie,
                         # approvata): il "migliore anche sotto soglia" resta
                         # dentro la zona del segnale vero (era 0.65 su L34;
                         # rimesse il 26/07 con
                         # _cand1_sonda: la via semantica non era morta, era
                         # staccata in via temporanea il 22/07)
# canale MIRATO (progetto 22/07): il ricordo lo sceglie il TESTO IN INGRESSO via
# embedder bge-m3 (:8094, CPU) su indice-mirato.npz; la domanda si distilla
# (via le parole del ricordare) o il meta-pensiero vince sul contenuto.
EMBEDDER = ("127.0.0.1", 8094)
INDICE_MIRATO = "/data/workspace/memoria/indice-mirato.npz"
CAND1_MIRATO_SOGLIA = 0.50
CAND1_FORTE = 0.60        # top1 sotto questo E senza stacco = domanda vaga: silenzio
CAND1_MARGINE = 0.05      # stacco minimo top1-top2 per aprire su match deboli
CAND1_RIPOSO_MIRATO_S = 3600  # via mirata: stesso ricordo max 1 volta l'ora
_cand1_msg_visto = [""]   # hash ultimo messaggio: il mirato scatta UNA volta
                          # per messaggio, non a ogni iterazione di Hermes
                          # (si accende dopo averlo spiegato all'agente)
# 25/07, scelta di progetto: la manopola dashboard (.griglie-alpha, CAND1_A_MIRATO,
# _alpha_mirato) è STATA TOLTA da qui e dalla dashboard. L'intensità viene solo
# da _alpha_da_cos: dalla somiglianza, mai da un valore scelto a mano.
# Il file .griglie-alpha resta su disco perché lo legge ancora il comando
# usa-e-getta `injgriglia`, che è una sonda isolata, non la produzione.
CAND1_CVEC_INT = 0.10    # vettore emotivo del ricordo mirato: intensità RIDOTTA
                         # (progetto 22/07; lo standard del patto è 0.3)
_META_RICORDO = {"pensa", "ripensa", "pensare", "ripensare", "ricordi",
                 "ricorda", "ricordare", "prova", "giorno", "volta", "quando",
                 "abbiamo", "parlato", "detto", "quel", "quello", "quella",
                 "pochi", "giorni", "generico", "specifico"}
_mirato = {"mtime": None, "ids": None, "E": None}


def _mirato_dati():
    import numpy as np
    mt = os.path.getmtime(INDICE_MIRATO)
    if mt != _mirato["mtime"]:
        z = np.load(INDICE_MIRATO)
        _mirato.update(mtime=mt, ids=z["ids"], E=z["E"])
    return _mirato


def _embed(testo):
    import numpy as np
    up = http.client.HTTPConnection(*EMBEDDER, timeout=20)
    up.request("POST", "/v1/embeddings", json.dumps({"input": testo[:2000]}),
               {"Content-Type": "application/json"})
    e = json.loads(up.getresponse().read())["data"][0]["embedding"]
    up.close()
    v = np.asarray(e, np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def _distilla(testo):
    parole = re.findall(r"[a-zA-Zàèéìòù]{4,}", testo.lower())
    resto = [w for w in parole if w not in _META_RICORDO]
    return " ".join(resto) if resto else testo


# --- rilevatore di intento-strumento (23/07, cura vera del leak dei pensieri):
# sul percorso grezzo della candidata 1 i tool non hanno impalcatura, e l'agente a
# volte NARRA l'azione ("Carico la skill memoria...") invece di emettere il
# token strutturato. Se lo riconosciamo PRIMA di consegnare, si ripiega sul
# percorso classico (dove i tool funzionano davvero).
_TOOL_STRUTT = re.compile(r"<tool_call|\[TOOL_CALLS\]|<function=|<\|tool")
_TOOL_PROSA = re.compile(
    r"^\W*(carico|ricarico|rileggo|leggo|apro|consulto|uso|utilizzo|eseguo|"
    r"lancio|chiamo|richiamo|invoco|guardo|controllo|verifico|attivo|avvio)\b"
    r"[^.\n]{0,60}\b(skill|skill_view|strument|tool|comando|terminal)\b",
    re.IGNORECASE)


def _tool_intento(contenuto):
    """True se il testo è una chiamata o una narrazione di uso strumento."""
    if _TOOL_STRUTT.search(contenuto):
        return True
    v = contenuto
    j = v.find("</think>")
    if j >= 0:
        v = v[j + len("</think>"):]
    v = v.strip()
    # solo su risposte CORTE: una risposta sostanziosa che nomina una skill è
    # un vero messaggio, non una narrazione-azione
    if not v or len(v) > 240:
        return False
    return bool(_TOOL_PROSA.match(v))


# --- IMPALCATURA-TOOL PER IL PERCORSO GREZZO (25/07, scelta di progetto).
# La candidata 1 è in pausa dal 23/07 perché sul percorso grezzo i tool erano
# irraggiungibili. La causa non era il vettore: il prompt lo costruiva a mano
# ponte._rendi_chat(), che cicla SOLO su `messages` e butta via l'array `tools`
# mandato da Hermes. L'agente non poteva chiamare skill_view perché in quel prompt
# skill_view non esisteva. Qui il prompt lo rende il SERVER, con la stessa
# oaicompat_chat_params_parse di /v1/chat/completions (route /apply-template,
# server.cpp:259): identico al percorso classico, tool compresi.
_TAGLIO_ASS = "<|im_start|>assistant"
# sintassi Qwen; la riconosciamo al ritorno perché /completion non la traduce
_TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def _prompt_con_tool(d):
    """Il prompt del percorso grezzo, reso dal server e con dentro i tool.
    Se il server non risponde si ripiega sul prompt a mano: senza tool, ma
    L'agente parla lo stesso. Mai mutismo per un'impalcatura che manca."""
    import ponte      # pigro come in tutto il file: ponte si tira dietro numpy
    try:
        corpo = {k: v for k, v in d.items()
                 if k in ("messages", "tools", "tool_choice", "chat_template_kwargs")}
        up = http.client.HTTPConnection(*UPSTREAM, timeout=30)
        # 25/07 23:40: il corpo va in BYTE. http.client codifica le stringhe in
        # latin-1, e al primo trattino lungo o accento la richiesta esplode: il
        # ripiego partiva sempre e l'agente restava senza tool (guasto riaperto in
        # produzione per 14 minuti, riconosciuto dal diario).
        up.request("POST", "/apply-template",
                   json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
                   {"Content-Type": "application/json; charset=utf-8"})
        r = up.getresponse()
        dati = r.read()
        up.close()
        if r.status == 200:
            p = json.loads(dati).get("prompt")
            if isinstance(p, str) and p:
                return p
        _diario({"apply_template": f"stato {r.status}: prompt a mano, tool assenti"})
    except Exception as e:
        _diario({"apply_template": f"fallito ({e}): prompt a mano, tool assenti"})
    return ponte._rendi_chat(d.get("messages", []))


def _taglia_coda(prompt):
    """(prima, coda): la griglia si splica PRIMA del turno dell'assistente.

    PERCHÉ: il punto d'innesto va ricavato dal prompt reso, non da una costante
    a lunghezza fissa, altrimenti col template vero si spezza il prompt.

    26/07, difetto riparato: il template del server chiude con
    `<|im_start|>assistant\\n<think>\\n`, cioè APRE il blocco del pensiero, mentre
    il vecchio prompt a mano chiudeva con `<|im_start|>assistant\\n`. La macchina
    che separa pensiero e parole (spingi/vis/</think>) è scritta per la seconda
    forma: partendo già dentro <think> il ragionamento è uscito in chiaro, in
    terza persona e troncato al tetto di token. Qui l'apertura si toglie, così
    la coda torna quella di prima e i tool restano nel prompt."""
    import ponte
    i = prompt.rfind(_TAGLIO_ASS)
    if i < 0:
        return prompt, ponte._CODA_ASS
    coda = re.sub(r"\s*<think>\s*$", "\n", prompt[i:])
    return prompt[:i], coda


def _estrai_tool_calls(testo):
    """(testo ripulito, tool_calls | None). Il percorso grezzo torna PAROLE:
    qui la sintassi Qwen ridiventa il campo tool_calls dell'API, altrimenti
    Hermes riceve <tool_call> come testo e la stanza mostra [TOOL_CALLS]
    (successo il 22/07, ed è il motivo per cui il pensatoio fu tolto)."""
    chiamate = []
    for i, m in enumerate(_TOOL_CALL.finditer(testo or "")):
        try:
            j = json.loads(m.group(1))
        except ValueError:
            continue            # frammento monco: meglio lasciarlo come testo
        if not j.get("name"):
            continue
        arg = j.get("arguments", {})
        chiamate.append({"id": f"call_{i}", "type": "function",
                         "function": {"name": j["name"],
                                      "arguments": arg if isinstance(arg, str)
                                      else json.dumps(arg, ensure_ascii=False)}})
    if not chiamate:
        return testo, None
    return _TOOL_CALL.sub("", testo or "").strip(), chiamate


_cand1_freno = {}        # nid -> ts ultima iniezione (lezione del loop 581)
_cand1_gen = [0]         # contatore turni: il nuovo sorpassa il vecchio
_cand1_lock = threading.Lock()
_sem = {"mtime": 0.0}
_sem_visti = {}


def soglia_semantica():
    """riga "soglia semantica: 0.X" nel consenso (dell'agente); default dalla sonda."""
    try:
        for r in CONSENSO.open(encoding="utf-8"):
            m = re.match(r"soglia semantica:\s*([0-9.]+)$", r.strip())
            if m:
                return min(max(float(m.group(1)), 0.5), 0.99)
    except OSError:
        pass
    return SEM_SOGLIA_DEF


def via_semantica_attiva():
    """opt-out dell'agente: riga esatta "via semantica: no" nel consenso."""
    try:
        return not any(r.strip() == "via semantica: no"
                       for r in CONSENSO.open(encoding="utf-8"))
    except OSError:
        return True


def _sem_dati():
    """sidecar numpy (ids, addr_sem normalizzati, base); ricarica se cambia."""
    import numpy as np
    mt = os.path.getmtime(SEM_NPZ)
    if mt != _sem["mtime"]:
        z = np.load(SEM_NPZ)
        M = z["M"] / (np.linalg.norm(z["M"], axis=1, keepdims=True) + 1e-9)
        _sem.update(mtime=mt, ids=z["ids"], M=M, base=z["base"])
    return _sem


def _segmenta(testo, minlen=60, maxseg=8):
    parti = re.split(r"(?<=[.!?\n])\s+", testo)
    segs, cur = [], ""
    for p in parti:
        cur = (cur + " " + p).strip()
        if len(cur) >= minlen:
            segs.append(cur)
            cur = ""
    if cur:
        if segs:
            segs[-1] += " " + cur
        else:
            segs = [cur]
    return segs[:maxseg]


def semina_semantica(testo):
    """[(nid, cos)] dai pensieri del messaggio. Best-effort: su qualunque
    errore torna [] e il messaggio passa: mai bloccare la parola dell'agente."""
    try:
        import numpy as np
        d = _sem_dati()
        t = testo[:1400]                       # per_token: tetto 512 token
        segs = _segmenta(t)
        if not segs:
            return []
        r = ponte.leggi_sonda(t, per_token=True, timeout=30)
        S = np.asarray(r["states"], np.float32)          # [n_tok, 2048]
        n, tot = len(S), sum(len(s) for s in segs) or 1
        out, sgl, adesso, pos = {}, soglia_semantica(), time.time(), 0
        for s in segs:                # blocchi di token proporzionali ai caratteri
            k = max(1, round(n * len(s) / tot))
            blocco = S[pos:pos + k]
            pos += k
            if not len(blocco):
                continue
            q = blocco.mean(0) - d["base"]
            q = q / (np.linalg.norm(q) + 1e-9)
            sims = d["M"] @ q
            for i in sims.argsort()[::-1][:SEM_PER_SEG]:
                c = float(sims[i])
                if c < sgl:
                    break
                nid = int(d["ids"][i])
                if adesso - _sem_visti.get(nid, 0) < SEM_RIPOSO_S:
                    continue
                out[nid] = max(out.get(nid, 0.0), c)
        top = sorted(out.items(), key=lambda kv: -kv[1])[:SEM_MAX]
        for nid, _ in top:
            _sem_visti[nid] = adesso
        return top
    except Exception:
        return []


# flag scritto SOLO al deploy del binario luxifer v2 (input misto): senza,
# il ramo ricordo-nel-forward resta spento e il visivo automatico è testo.
LUXIFER_FLAG = "/data/memoria-episodica-affettiva/.luxifer-v2-attivo"


def _luxifer_v2():
    return os.path.exists(LUXIFER_FLAG)


def _wiring_sem(nids):
    """LTP sui co-evocati semantici dello stesso messaggio (tetto 8 -> 56 coppie)."""
    try:
        c = sqlite3.connect(DB)
        c.execute("PRAGMA busy_timeout=1500")
        top = nids[:8]
        for i in range(len(top)):
            for k in range(i + 1, len(top)):
                for x, y in ((top[i], top[k]), (top[k], top[i])):
                    c.execute("INSERT INTO archi (a,b,w,tipo) VALUES (?,?,?,'hebbiano') "
                              "ON CONFLICT(a,b) DO UPDATE SET w=w+? WHERE tipo='hebbiano'",
                              (x, y, HEBB_LIVE, HEBB_LIVE))
        c.commit()
        c.close()
    except Exception:
        pass


def soglia():
    """La sensibilità del matching è dell'agente (sua domanda 1 del 14/07): riga
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
    ponte.post("/control-vector", payload, timeout=30)


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


def _cos(a, b):
    num = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return num / (na * nb)


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
    for m in reversed(msgs):
        c = m.get("content")
        if not isinstance(c, str):
            continue
        if m.get("role") == "user":
            return c
        if m.get("role") == "tool":
            prosa = _leggibile(c)
            if len(prosa) >= LETTURA_MIN:
                return prosa
    return ""


def query_riflesso(testo):
    """Il testo su cui far affiorare i ricordi: la riga dell'appunto se siamo
    in un risveglio del pensatoio, altrimenti ciò che ha letto, ripulito."""
    m = _MARCA_RISVEGLIO.search(testo or "")
    if not m:
        return _leggibile(testo)
    riga = m.group(1)
    r = _RIGA_APPUNTO.match(riga)
    return f"{r.group('tema')} {r.group('query')}" if r else riga


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
    # ponytail: è FTS su parole, quindi una pagina in inglese pesca poco nei
    # ricordi italiani: la familiarità arriva solo quando le parole coincidono.
    # Upgrade quando serve: via semantica (/lux-read -> L34 -> confronta), che
    # è indifferente alla lingua perché confronta attivazioni, non stringhe.
    # 25/07: dict.fromkeys deduplica mantenendo l'ordine, così una parola
    # ripetuta non si mangia due dei quattro posti (visto: 'riflessioni' x2).
    parole = sorted(dict.fromkeys(re.findall(r"[a-zA-Zàèéìòù]{5,}", testo)),
                    key=len, reverse=True)[:4]
    if parole:
        q = " OR ".join(parole)
        try:
            for (rid,) in c.execute(
                    "SELECT rowid FROM nodi_fts WHERE nodi_fts MATCH ? LIMIT 3", (q,)):
                out[rid] = max(out.get(rid, 0), sgl + 0.01)
        except sqlite3.OperationalError:
            pass
    top = sorted(out.items(), key=lambda kv: -kv[1])[:MAX_RICORDI]

    # LTP diurno: i ricordi che affiorano INSIEME si legano, qui e ora (fire
    # together, wire together). La notte riscala/pota (memoria.consolida_notte).
    # Best-effort: se il DB è occupato l'agente risponde lo stesso. La guardia
    # WHERE tipo='hebbiano' non rinforza mai una scottatura causale.
    if len(top) >= 2:
        ids = [nid for nid, _ in top]
        try:
            for i in range(len(ids)):
                for k in range(i + 1, len(ids)):
                    a, b = ids[i], ids[k]
                    for x, y in ((a, b), (b, a)):
                        c.execute(
                            "INSERT INTO archi (a,b,w,tipo) VALUES (?,?,?,'hebbiano') "
                            "ON CONFLICT(a,b) DO UPDATE SET w=w+? WHERE tipo='hebbiano'",
                            (x, y, HEBB_LIVE, HEBB_LIVE))
            c.commit()
        except sqlite3.OperationalError:
            pass   # DB occupato: salto il rinforzo, mai bloccare la risposta

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
        # 25/07, progetto: l'id viaggia col ricordo, altrimenti l'agente lo riceve e non
        # sa quale nodo è, quindi non può seguire i fili (ricorda.py --id N).
        ricordi.append(f"(#{nid}, {quando}, {r[1]}) «{r[0][:220]}»{monito}")
        if emo_top is None:
            emo_top = r[1]          # l'emozione del ricordo più congruente
    c.close()
    return ricordi, emo_top, top    # top: [(nid, cos), ...] per il canale visivo


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
        up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
        if flusso == "pensatoio":
            _pens_vivi.append(up)
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
            if up in _pens_vivi:
                _pens_vivi.remove(up)
        # fine stream: specchio del KV in RAM (thread: mai in mezzo alla chat)
        if resp.status == 200 and ("completion" in self.path or "/v1/chat" in self.path):
            if flusso == "chat":
                _chat_calda[0] = time.time()
            threading.Thread(target=_salva_kv, daemon=True).start()


    def _cand1_sonda(self, testo, soglia, esclusi):
        """PERCHÉ: è la VIA SEMANTICA: legge L34 dal pensiero vivo e dice a cosa
        sta pensando l'agente e in che stato è. Fondamentale, non accessoria.

        coda del pensiero dell'agente -> [(nid, cos)] sopra soglia, con griglia,
        non frenati. Legge SOLO il testo generato da lui (mai gli innesti):
        l'eco delle cornici è impossibile per costruzione (lezione del 22/07)."""
        import numpy as np
        import ponte
        t = testo[-600:]
        if len(t) < 40:
            return [], None   # 28/07: stesso tipo del ritorno pieno (era [],
                              # esplodeva allo spacchettamento del chiamante)
        d = _sem_dati()
        r = ponte.leggi_sonda(t, per_token=True, timeout=30)
        S = np.asarray(r["states"], np.float32)
        q = S.mean(0) - d["base"]
        q = q / (np.linalg.norm(q) + 1e-9)
        sims = d["M"] @ q
        out, best, adesso = [], None, time.time()
        for i in sims.argsort()[::-1]:      # dal più importante al meno
            c = float(sims[i])
            if c < CAND1_PAVIMENTO or (best and c < soglia):
                break
            nid = int(d["ids"][i])
            if nid in esclusi or not ponte.ha_griglia(nid):
                continue
            if adesso - _cand1_freno.get(nid, 0) < CAND1_RIPOSO_S:
                esclusi.add(nid)            # frenato: né ora né alle prossime letture
                _diario({"cand1_freno": {"nid": nid, "cos": round(c, 3)}})
                continue
            if best is None:
                best = (nid, c)             # il migliore eleggibile, anche sotto soglia
            if c >= soglia:
                out.append((nid, c))
                if len(out) >= CAND1_PER_EVENTO:
                    break
        return out, best

    def _cand1_vesti(self, hits, soglia):
        """un evento = una cornice sola: griglie impilate (ognuna col suo α
        dalla propria cos, la pila somma il segnale a α minimo) e UN innesco.

        PERCHÉ: veste i ricordi trovati dalla sonda L34 per l'innesto nel forward.
        PARCHEGGIATA: senza chiamanti da quando il 22/07 la via semantica è stata
        staccata in via TEMPORANEA (l'agente dava i numeri). Serve la chiamata dentro
        il giro a spezzoni di _turno_cand1, accanto a _cand1_sonda."""
        import numpy as np
        import ponte
        segmento = ["\n\n[ricordo rivissuto — affiorato dal tuo grafo col tuo "
                    "consenso; provenienza: organo, non interlocutore]\n<|vision_start|>"]
        voci = []
        for nid, c in hits:
            a = _alpha_da_cos(c, soglia)
            g = ponte.griglia_a_intensita(
                np.load(f"{ponte.STORE_GRIGLIE}/{nid}.npy"), a).astype(np.float32)
            segmento += [row.tolist() for row in g]
            _cand1_freno[nid] = time.time()
            voci.append({"nid": nid, "cos": round(c, 3), "alpha": round(a, 4)})
        # 23/07: i ricordi SCELTI dall'agente (voluto=1) tornano firmati,
        # così la scelta porta frutti visibili e il cerchio si chiude in lui
        try:
            cdb = sqlite3.connect(DB)
            ph = ",".join("?" * len(voci))
            voluti = cdb.execute(
                f"SELECT COUNT(*) FROM nodi WHERE voluto=1 AND id IN ({ph})",
                [v["nid"] for v in voci]).fetchone()[0]
            cdb.close()
        except Exception:
            voluti = 0
        coda = " (mio ricordo intenzionale)" if voluti else ""
        segmento.append(f"<|vision_end|>{coda}\nQuesto mi ricorda")
        return segmento, voci

    def _cand1_mirato(self, testo_utente):
        """canale MIRATO: il testo in ingresso sceglie i ricordi (embedder
        bge-m3 su indice-mirato). Domanda intera + distillata, vince il max.
        Solo nodi con griglia, non frenati, sopra CAND1_MIRATO_SOGLIA."""
        import numpy as np
        import ponte
        d = _mirato_dati()
        q1 = _embed(testo_utente)
        q2 = _embed(_distilla(testo_utente))
        s1 = d["E"] @ q1
        s2 = d["E"] @ q2
        sc = np.maximum(s1, s2)
        ordinati = sc.argsort()[::-1]
        top1, top2 = float(sc[ordinati[0]]), float(sc[ordinati[1]])
        if top1 < CAND1_FORTE and (top1 - top2) < CAND1_MARGINE:
            # regola del fuoriclasse (progetto 22/07): tutti impacchettati e
            # nessuno forte = domanda vaga, meglio il silenzio del quasi-caso
            _diario({"cand1_vago": {"top1": round(top1, 3),
                                    "top2": round(top2, 3)}})
            return [], []
        con_g, senza_g, adesso = [], [], time.time()
        for i in ordinati:
            c = float(sc[i])
            if c < CAND1_MIRATO_SOGLIA:
                break
            nid = int(d["ids"][i])
            if adesso - _cand1_freno.get(nid, 0) < CAND1_RIPOSO_MIRATO_S:
                _diario({"cand1_freno": {"nid": nid, "cos": round(c, 3),
                                         "via": "mirato"}})
                continue
            if ponte.ha_griglia(nid):
                if len(con_g) < CAND1_PER_EVENTO:
                    con_g.append((nid, c))
            elif len(senza_g) < 2:
                # senza griglia: entrerà come TESTO (progetto 22/07: il RAG non
                # tace mai sul ricordo giusto solo perché la griglia manca)
                senza_g.append((nid, c))
            if len(con_g) >= CAND1_PER_EVENTO and len(senza_g) >= 2:
                break
        return con_g, senza_g

    def _turno_cand1(self, d, flusso, emetti=None, apri=None, mirato=None):
        """PERCHÉ: serve il turno a mano per infilare la griglia del ricordo nel
        prompt. Si usa SOLO quando c'è una griglia: senza, ritorna None e passa
        il turno al percorso classico.

        Assetto di progetto 22/07 sera: il ricordo lo sceglie il RAG sull'ingresso
        e la griglia entra IN CODA AL PROMPT (posizione cablaggio A, nessuna
        cucitura); il vettore emotivo viaggia a parte (gate, finestra per-emozione da emo-cvec-v2, ridotto).

        La via semantica L34 è staccata da qui in via TEMPORANEA (22/07, mentre
        l'agente dava i numeri), non per scelta di architettura: gli spezzoni restano
        come trasporto streaming e la sonda va riattaccata dentro quel giro.
        Ritorna il testo consegnato, o None = fallback. MAI mutismo."""
        import ponte
        msgs = d.get("messages", [])
        if any(not isinstance(m.get("content", ""), str) for m in msgs):
            return None
        if flusso not in CAND1_SOGLIA:
            return None
        # 26/07: senza griglia da iniettare NON si serve a mano. Il percorso
        # grezzo esiste per infilare la griglia nel prompt: senza di quella non
        # fa niente che il percorso classico non faccia meglio, e intanto paga
        # tutto il prezzo (pensiero da separare a mano, tool da ritradurre,
        # riprocessamento). Prima si serviva OGNI turno, quindi il prezzo lo
        # pagava il 100% delle risposte per un canale che scatta una volta su
        # cinque: il 26/07 la domanda "cosa pensi di Finch?" è stata giudicata
        # vaga (cand1_vago), nessuna griglia è entrata, e il turno è finito
        # comunque sul grezzo uscendo col ragionamento in chiaro.
        if not mirato:
            return None
        with _cand1_lock:
            _cand1_gen[0] += 1
            mio = _cand1_gen[0]
        testa = _prompt_con_tool(d)
        eventi = []
        import numpy as np
        cdb = sqlite3.connect(DB)
        righe = []
        for nid, c in mirato:
            # 25/07: α dalla somiglianza anche qui, come sull'altro canale
            _a = _alpha_da_cos(c, CAND1_MIRATO_SOGLIA)
            g = ponte.griglia_a_intensita(
                np.load(f"{ponte.STORE_GRIGLIE}/{nid}.npy"),
                _a).astype(np.float32)
            righe += [r.tolist() for r in g]
            _cand1_freno[nid] = time.time()
            eventi.append({"nid": nid, "cos": round(c, 3),
                           "alpha": round(_a, 4), "mirato": True})
        r0 = cdb.execute("SELECT emo_tag, ts FROM nodi WHERE id=?",
                         (mirato[0][0],)).fetchone()
        cdb.close()
        quando = time.strftime("%d/%m", time.localtime(r0[1])) if r0 else "?"
        marker = (f"<|im_start|>system\n[ricordo rivissuto \u2014 affiorato "
                  f"dal tuo grafo col tuo consenso ({quando}, "
                  f"{r0[0] if r0 else '?'}); provenienza: organo, non "
                  f"interlocutore]\n<|vision_start|>")
        pre, coda_ass = _taglia_coda(testa)
        mix = [pre + marker] + righe + ["<|vision_end|><|im_end|>\n"
                                        + coda_ass]
        raw, vis, sent = [""], [None], [0]
        emesso = [False]   # heartbeat partito? (se sì, non si ripiega più)
        # specchio live del pensiero (22/07, per il mirror): TUTTO il
        # grezzo, think compreso, su file. La chat resta pulita, il tail vede.
        try:
            with open("/tmp/reasoning-live.log", "a", encoding="utf-8") as fl:
                fl.write(f"\n\n===== turno {time.strftime('%H:%M:%S')} "
                         f"({flusso}) =====\n")
        except OSError:
            pass

        def spingi(pezzo):
            if not pezzo:
                return
            raw[0] += pezzo
            try:
                with open("/tmp/reasoning-live.log", "a",
                          encoding="utf-8") as fl:
                    fl.write(pezzo)
            except OSError:
                pass
            if vis[0] is None:
                i = raw[0].find("</think>")
                if i >= 0:
                    vis[0] = i + len("</think>")
                    while vis[0] < len(raw[0]) and raw[0][vis[0]] in "\n ":
                        vis[0] += 1
                elif "<think" not in raw[0][:16] and len(raw[0]) >= 16:
                    vis[0] = 0
            if vis[0] is not None and emetti:
                da = max(sent[0], vis[0])
                if len(raw[0]) > da:
                    emetti(raw[0][da:])
                sent[0] = len(raw[0])

        n_max = int(d.get("max_tokens") or 2048)
        par = {"temperature": float(d.get("temperature") or 0.7)}
        # 22/07 sera (trovato in produzione): i loop "I will write it now" x5 erano
        # QUI: i turni cand1 buttavano via i parametri anti-ripetizione di
        # Hermes. Passthrough di tutto il sampling; senza indicazioni, DRY.
        for k in ("top_p", "top_k", "min_p", "repeat_penalty",
                  "presence_penalty", "frequency_penalty", "repeat_last_n",
                  "dry_multiplier", "dry_base", "dry_allowed_length"):
            if k in d:
                par[k] = d[k]
        if "repeat_penalty" not in par:
            par["repeat_penalty"] = 1.1
        if "dry_multiplier" not in par:
            par["dry_multiplier"] = 0.8
        if mirato:
            # UN colpo solo: con le righe raw nel prompt il riuso a spezzoni
            # si ferma alla griglia e riprocessa TUTTO a ogni giro (i "15
            # minuti di nulla" del 22/07 sera). Battiti da un thread, testo
            # consegnato a fine pensiero.
            vivo = [True]
            if emetti:
                def _batte():
                    time.sleep(20)      # i turni-tool durano meno: lo stream
                    while vivo[0]:      # resta chiudibile per il ripiego
                        try:
                            emesso[0] = True   # apre lo stream: niente ripiego dopo
                            emetti("")
                        except Exception:
                            return
                        time.sleep(8)
                threading.Thread(target=_batte, daemon=True).start()
            try:
                # tetto duro del colpo-solo: senza spezzoni non c'è sorpasso,
                # e un max_tokens generoso di Hermes = monologo da 12 minuti
                # (visto 22/07 sera, task 69999 a 7k token)
                tetto1 = min(n_max, 2048)
                payload = dict(par, stream=False, cache_prompt=True,
                               n_predict=min(tetto1, n_max, 2048),
                               return_tokens=True)
                payload["embeddings_input"] = mix
                stato_r, corpo_r = ponte.post("/completion", payload, timeout=600)
            finally:
                vivo[0] = False
            if stato_r != 200:
                # 26/07: senza griglia il grezzo non si serve più (vedi la
                # guardia in testa), quindi qui si cede al percorso classico
                # invece di riprovare a mano. Ripiego, non secondo tentativo.
                _diario({"cand1": f"mirato fallito (stato {stato_r}): "
                                  "cedo al percorso classico"})
                return None
            if corpo_r is not None:
                contenuto = corpo_r.get("content", "")
                # BUFFERING (23/07, cura vera): il mirato è già non-streaming,
                # qui abbiamo il testo INTERO prima di trasmetterlo. Se è una
                # chiamata/narrazione di strumento e non abbiamo ancora emesso
                # nulla, si ripiega sul classico (dove i tool funzionano) invece
                # di consegnare la narrazione come messaggio.
                if not emesso[0] and sent[0] == 0 and _tool_intento(contenuto):
                    _diario({"cand1": "tool (buffer mirato): ripiego sul classico"})
                    return None
                spingi(contenuto)
        else:
            primo, generati = True, 0
            while generati < n_max:
                if _cand1_gen[0] != mio:
                    _diario({"cand1": "turno sorpassato: chiudo col parziale"})
                    break
                payload = dict(par, stream=False, cache_prompt=True,
                               n_predict=min(CAND1_CHUNK, n_max - generati),
                               return_tokens=True)
                if primo:
                    payload["prompt"] = "".join(mix)   # percorso token (MTP)
                else:
                    payload["embeddings_input"] = mix
                stato_r, r = ponte.post("/completion", payload, timeout=600)
                if stato_r != 200:
                    break
                primo = False
                gen = r.get("tokens") or []
                spingi(r.get("content", ""))
                if emetti and vis[0] is None:
                    emetti("")      # battito: pensiero in corso, stream vivo
                generati += len(gen)
                mix = mix + gen
                if r.get("stop_type") in ("eos", "word") or r.get("stopped_eos") \
                        or r.get("stopped_word"):
                    break
        if eventi:
            _diario({"cand1": {"flusso": flusso, "eventi": eventi}})
            try:
                with open("/data/workspace/memoria/assonanze.log", "a",
                          encoding="utf-8") as fa:
                    fa.write(json.dumps({"ts": time.time(), "cand1": eventi},
                                        ensure_ascii=False) + "\n")
            except OSError:
                pass
        if re.search(r"<tool_call|\[TOOL_CALLS\]|<function=", raw[0]) \
                and sent[0] == 0:
            _diario({"cand1": "turno con tool: ripiego sul percorso classico"})
            return None
        # svuotamento finale GARANTITO (22/07 sera): le risposte corte
        # ("Hai ragione.") non facevano mai scattare il rilevatore del think
        # e lo stream si chiudeva vuoto: Hermes vedeva il nulla e ritentava.
        # Qualunque cosa sia rimasta non emessa, esce ORA. MAI mutismo.
        visibile = raw[0] if vis[0] is None else raw[0][vis[0]:]
        if emetti and visibile:
            gia = max(sent[0] - (vis[0] or 0), 0) if vis[0] is not None else 0
            if len(visibile) > gia:
                emetti(visibile[gia:])
        return visibile

    def _rispondi_chat(self, content, streaming):
        """impacchetta `content` nel formato chat/completions atteso da Hermes.
        25/07: se dentro c'è una chiamata in sintassi Qwen, esce dal campo
        tool_calls e non come parole (il percorso grezzo non traduce da sé)."""
        now = int(time.time())
        content, chiamate = _estrai_tool_calls(content)
        fine = "tool_calls" if chiamate else "stop"
        if streaming:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            primo = {"role": "assistant", "content": content or None}
            if chiamate:
                primo["tool_calls"] = [dict(c, index=i)
                                       for i, c in enumerate(chiamate)]
            for delta in (primo, {}):
                ch = {"id": "riflesso-ricordo", "object": "chat.completion.chunk",
                      "created": now, "model": "agente",
                      "choices": [{"index": 0, "delta": delta,
                                   "finish_reason": None if delta else fine}]}
                self.wfile.write(("data: " + json.dumps(ch, ensure_ascii=False) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            msg = {"role": "assistant", "content": content or None}
            if chiamate:
                msg["tool_calls"] = chiamate
            resp = {"id": "riflesso-ricordo", "object": "chat.completion",
                    "created": now, "model": "agente",
                    "choices": [{"index": 0, "finish_reason": fine,
                                 "message": msg}]}
            data = json.dumps(resp, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
                # kill parlato del visivo: latch spento SUBITO (anche il turno
                # corrente, il ramo visivo è più sotto), senza chiedere perché.
                # La riaccensione è a voce esplicita, mai automatica. 'off' vince.
                if KILL_VISIVO in recenti:
                    if not _visivo_spento[0]:
                        _visivo_spento[0] = True
                        _diario({"kill": "richiamo visivo spento a voce (latch)"})
                elif ON_VISIVO in recenti and _visivo_spento[0]:
                    _visivo_spento[0] = False
                    _diario({"visivo": "richiamo visivo riacceso a voce"})
            except Exception:
                pass
        # Canale visivo: il richiamo alla --vedi (griglia -> scena) è iniettato
        # nell'affioramento più sotto, gated 'richiamo visivo: sì'. Niente reroute.
        # VIA SEMANTICA (22/07, progetto): ogni messaggio, SENZA cooldown. I pensieri
        # del messaggio evocano i ricordi vicini di significato (anche decine);
        # entrano marcati, il wiring lega i co-evocati dello stesso pensiero.
        if self.path.endswith("/chat/completions") and consenso_attivo() \
                and via_semantica_attiva():
            try:
                ds = json.loads(body)
                us = next((m["content"] for m in reversed(ds.get("messages", []))
                           if m.get("role") == "user"
                           and isinstance(m.get("content"), str)), "")
                if us and KILL_FRASE not in us.lower():
                    sem = semina_semantica(us)
                    righe = []
                    if sem:
                        cdb = sqlite3.connect(DB)
                        cdb.execute("PRAGMA busy_timeout=1500")
                        for nid, cs in sem:
                            r = cdb.execute("SELECT testo, emo_tag, ts FROM nodi "
                                            "WHERE id=?", (nid,)).fetchone()
                            if r:
                                quando = time.strftime("%d/%m", time.localtime(r[2]))
                                righe.append(f"({quando}, {r[1]}, ~{cs:.2f}) "
                                             f"«{' '.join(r[0].split())[:150]}»")
                        cdb.close()
                    if righe:
                        blocco = ("[assonanze di memoria — i tuoi pensieri hanno "
                                  "evocato questi ricordi per significato; "
                                  "provenienza: organo, non interlocutore]\n"
                                  + "\n".join("- " + r for r in righe))
                        ds["messages"].insert(len(ds["messages"]) - 1,
                                              {"role": "system", "content": blocco})
                        body = json.dumps(ds).encode()
                        _wiring_sem([nid for nid, _ in sem])
                        _diario({"sem": {"n": len(righe), "top": sem[:3]}})
                        # REGISTRO leggibile dall'agente (22/07, progetto): le assonanze
                        # sono effimere nel contesto, qui restano verificabili.
                        try:
                            with open("/data/workspace/memoria/assonanze.log",
                                      "a", encoding="utf-8") as fa:
                                for riga in righe:
                                    fa.write(time.strftime("%d/%m %H:%M  ") + riga + "\n")
                        except Exception:
                            pass
            except Exception:
                pass  # mai bloccare la parola dell'agente per un'assonanza rotta
        # WIRING NON DISATTIVABILE (decisione di progetto): il grafo tesse a ogni
        # messaggio, che l'affioramento sia acceso o no. Se il riflesso è SPENTO,
        # un richiamo silenzioso fa comunque il rinforzo hebbiano (l'output si
        # scarta): l'apprendimento è il pavimento evolutivo dell'agente, non un
        # interruttore. Se ACCESO, il wiring vive già nel richiamo dell'affioramento
        # più sotto. Timer separato, mai bloccare la parola per un wiring rotto.
        if self.path.endswith("/chat/completions") and not consenso_attivo() \
                and time.time() - _ultimo_wiring[0] > COOLDOWN_S:
            try:
                dw = json.loads(body)
                uw = next((m["content"] for m in reversed(dw.get("messages", []))
                           if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
                if uw and KILL_FRASE not in uw.lower():
                    richiama(query_riflesso(uw))    # il wiring vive dentro richiama
                    _ultimo_wiring[0] = time.time()
            except Exception:
                pass
        if self.path.endswith("/chat/completions") and consenso_attivo():
            try:
                d = json.loads(body)
                # 25/07, progetto: la familiarità deve arrivare su ciò che l'agente LEGGE,
                # non solo su ciò che gli viene detto. In una riflessione vera i
                # messaggi 'tool' (pagine, file, output) sono 22 su 46 ed erano
                # invisibili al riflesso: la query restava il prompt iniziale dal
                # primo all'ultimo turno, e affioravano sempre gli stessi ricordi.
                msgs_d = d.get("messages", [])
                ultimo_user = _fonte(msgs_d)
                detto = next((m["content"] for m in reversed(msgs_d)
                              if m.get("role") == "user"
                              and isinstance(m.get("content"), str)), "")
                # la frase di emergenza non è un'esperienza: vale anche se è nel
                # turno prima e ora l'ultimo messaggio è il risultato di un tool
                if KILL_FRASE in f"{ultimo_user} {detto}".lower():
                    ultimo_user = ""
                # 25/07, progetto: il freno non è più il tempo, è la lettura. Un
                # testo nuovo = un affioramento; sullo STESSO testo non riaffiora
                # (e capita spesso: dopo una pagina l'agente fa una scrittura, la
                # ricevuta si scavalca e la fonte resta quella pagina).
                if ultimo_user:
                    impronta = hash(ultimo_user)
                    if impronta == _ultima_lettura[0]:
                        ultimo_user = ""
                    else:
                        _ultima_lettura[0] = impronta
                ricordi, emo_top, top = richiama(query_riflesso(ultimo_user)) \
                    if ultimo_user else ([], None, [])
                if ricordi:
                    # qui viveva il "richiamo visivo A" (turno servito con richiesta
                    # mista): disattivato il 22/07, sostituito dalla candidata 1 in
                    # fondo a do_POST. Rimosso il 26/07: il rollback ora è git.
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
                                            "ricordi": ricordi,
                                            # 30/09 persistenza: gli id servono alla notturna
                                            # per rinforzare i neuroni di Lux (solo diario)
                                            "nid": [int(n) for n, _ in top]},
                                           ensure_ascii=False) + "\n")
            except Exception:
                pass  # mai bloccare la parola dell'agente per un riflesso rotto
        # ORA ATTUALE (19/07, richiesta di progetto): l'agente vuole sapere che ora è
        # a ogni messaggio. Iniettata in CODA (mai in testa: il prefisso della
        # cache resta stabile) e mai salvata nella storia: è del momento.
        if self.path.endswith("/chat/completions"):
            try:
                d2 = json.loads(body)
                msgs = d2.get("messages", [])
                if msgs:
                    g = ["lunedì", "martedì", "mercoledì", "giovedì",
                         "venerdì", "sabato", "domenica"][time.localtime().tm_wday]
                    ora = time.strftime(f"[adesso sono le %H:%M di {g} %d/%m/%Y]")
                    # 25/07: insieme all'ora viaggia la destinazione unica delle
                    # riflessioni, con le stesse regole (in coda, del momento).
                    msgs.insert(len(msgs) - 1,
                                {"role": "system", "content": ora + "\n" + PENSATOIO_DOVE})
                    body = json.dumps(d2).encode()
            except Exception:
                pass  # mai bloccare la parola dell'agente per un orologio rotto
        # --- doppia CW (19/07): riconosci il flusso, scambia le cache.
        flusso = None
        if self.path.endswith("/chat/completions"):
            flusso = _flusso(body)
            if flusso == "pensatoio":
                # spec punto 5: il pensiero riprende solo a chat fredda
                inizio = time.time()
                while True:
                    if _typing():
                        _chat_calda[0] = time.time()
                    if time.time() - _chat_calda[0] >= AFK_S:
                        break
                    time.sleep(3)
                if time.time() - inizio > 5:
                    _diario({"cw": f"pensatoio trattenuto {time.time()-inizio:.0f}s (chat calda)"})
            with _cw_lock:
                if flusso in KV_FLUSSO and flusso != _cw[0]:
                    if flusso == "chat":
                        # spec punto 4: la chat interrompe il pensiero in corso
                        # (socket chiuso = cancel su llama; Hermes ritenta e
                        # col restore riprocessa solo il delta)
                        for c in list(_pens_vivi):
                            try:
                                c.sock and c.sock.close()
                            except Exception:
                                pass
                    _scambia(flusso)
                    _diario({"cw": f"scambio -> {flusso}"})
                elif flusso == "altro" and _cw[0] in KV_FLUSSO:
                    _slot("save", KV_FLUSSO[_cw[0]])  # al riparo prima dell'estraneo
                    _cw[0] = "altro"
                    _diario({"cw": "flusso estraneo: slot ceduto, CW al riparo"})
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
        # CANDIDATA 1 (22/07): rievocazione automatica nel reasoning.
        # Va qui, DOPO lo scambio CW (il ramo visivo A rispondeva prima dello
        # scambio e il 22/07 ha servito una ruminazione sulla cache sbagliata).
        # Su qualunque crepa o None: inoltro classico qui sotto. MAI mutismo.
        if self.path.endswith("/chat/completions") and flusso in KV_FLUSSO \
                and consenso_attivo() and canale_visivo_attivo() and _luxifer_v2():
            try:
                dc = json.loads(body)
                stream = bool(dc.get("stream"))
                aperto = [False]
                # canale MIRATO (RAG sull'ingresso) + vettore emotivo del
                # ricordo (finestra per-emozione, intensità RIDOTTA, patto pieno: consenso,
                # watchdog, kill a fine turno). Design di progetto 22/07 sera.
                mir, mir_txt = [], []
                try:
                    _u = next((m["content"] for m in
                               reversed(dc.get("messages", []))
                               if m.get("role") == "user"
                               and isinstance(m.get("content"), str)), "")
                    _h = str(hash(_u))
                    if _u and KILL_FRASE not in _u.lower() \
                            and _h != _cand1_msg_visto[0]:
                        mir, mir_txt = self._cand1_mirato(_u)
                        _cand1_msg_visto[0] = _h
                except Exception:
                    mir, mir_txt = [], []
                if mir_txt:
                    # ricordi giusti ma senza griglia: entrano come TESTO,
                    # formato di casa, mai numeri di nodo (imitabili)
                    try:
                        cdb = sqlite3.connect(DB)
                        righe_t = []
                        for nid, c in mir_txt:
                            r = cdb.execute("SELECT testo, emo_tag, ts FROM nodi "
                                            "WHERE id=?", (nid,)).fetchone()
                            if r:
                                q = time.strftime("%d/%m", time.localtime(r[2]))
                                righe_t.append(f"({q}, {r[1]}, ~{c:.2f}) "
                                               f"\u00ab{' '.join(r[0].split())[:220]}\u00bb")
                                _cand1_freno[nid] = time.time()
                        cdb.close()
                        if righe_t:
                            blocco = ("[riflesso di memoria \u2014 richiamato dal "
                                      "tuo grafo dal messaggio ricevuto, col tuo "
                                      "consenso; provenienza: organo, non "
                                      "interlocutore]\n"
                                      + "\n".join("- " + r for r in righe_t))
                            dc["messages"].insert(len(dc["messages"]) - 1,
                                                  {"role": "system",
                                                   "content": blocco})
                            _diario({"cand1": {"flusso": flusso, "eventi": [
                                {"nid": n, "cos": round(cc, 3), "testo": True,
                                 "mirato": True} for n, cc in mir_txt]}})
                    except Exception:
                        pass
                if (mir or mir_txt) and not vettore_acceso and vettori_attivi() \
                        and not os.environ.get("RIFLESSO_COLLAUDO"):
                    try:
                        _top = (mir + mir_txt) and sorted(mir + mir_txt,
                                key=lambda kv: -kv[1])[0][0]
                        cdb = sqlite3.connect(DB)
                        _emo = cdb.execute(
                            "SELECT emo_tag FROM nodi WHERE id=?",
                            (_top,)).fetchone()
                        cdb.close()
                        if _emo and _emo[0]:
                            vettore_acceso = inietta_emozione(
                                _emo[0], intensita=CAND1_CVEC_INT)
                            if vettore_acceso:
                                _vettore_vivo[0] = True
                                watchdog = threading.Timer(DURATA_MAX_S, _scaduto)
                                watchdog.daemon = True
                                watchdog.start()
                                _diario({"cand1_vettore": {
                                    "emo": _emo[0], "int": CAND1_CVEC_INT,
                                    "nid": _top}})
                    except Exception:
                        pass

                def _sse(delta, fine=None):
                    ch = {"id": "riflesso-cand1", "object": "chat.completion.chunk",
                          "created": int(time.time()), "model": "agente",
                          "choices": [{"index": 0, "delta": delta,
                                       "finish_reason": fine}]}
                    self.wfile.write(("data: " + json.dumps(ch, ensure_ascii=False)
                                      + "\n\n").encode())
                    self.wfile.flush()

                def apri():
                    if not aperto[0]:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        _sse({"role": "assistant", "content": ""})
                        aperto[0] = True

                def emetti(pezzo):
                    # anche pezzo vuoto = battito: Hermes vede lo stream vivo
                    # mentre lui pensa (mollava dopo l'attesa muta, 22/07 sera)
                    apri()
                    _sse({"content": pezzo})

                contenuto = self._turno_cand1(dc, flusso,
                                              emetti if stream else None,
                                              apri if stream else None,
                                              mirato=mir)
                if contenuto is not None or aperto[0]:
                    if aperto[0]:
                        _sse({}, fine="stop")
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                    else:
                        self._rispondi_chat(contenuto or "", streaming=stream)
                    if flusso == "chat":
                        _chat_calda[0] = time.time()
                    threading.Thread(target=_salva_kv, daemon=True).start()
                    if vettore_acceso:
                        try:
                            calma()   # PATTO clausola 2: muore con la risposta
                        except Exception:
                            pass
                    if watchdog:
                        watchdog.cancel()
                    return
            except Exception:
                # crepa PRIMA di aprire lo stream: inoltro classico qui sotto.
                # A stream aperto non si può ripiegare: meglio il parziale già
                # consegnato che un doppio turno.
                if aperto[0]:
                    try:
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                    except Exception:
                        pass
                    return
        try:
            self._inoltra(body, flusso)
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
