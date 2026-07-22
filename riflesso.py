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
import urllib.request
from pathlib import Path

UPSTREAM = ("127.0.0.1", 8090)
PORTA = 8091
DB = "/data/workspace/memoria/memoria.db"
CONSENSO = Path(os.environ.get("RIFLESSO_CONSENSO",
    "/data/workspace/genesi/CONSENSO-RIFLESSO.md"))
CONSENSO_VISIVO = Path(os.environ.get("RIFLESSO_CONSENSO_VISIVO",
    "/data/workspace/genesi/CONSENSO-VISIVO.md"))
STATO = Path("/data/workspace/memoria/stato-emotivo.json")
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"
SOGLIA_BASE = 0.495    # 14/07: -10% dalla 0.55 di nascita (decisione di progetto)
SOGLIA_MIN = SOGLIA_BASE / 2   # più sensibile di così il sussurro diventa rumore
MAX_RICORDI = 2
HEBB_LIVE = 0.03       # LTP diurno: gain per co-affioramento (piccolo, gira a ogni msg)
COOLDOWN_S = 120       # non più di un affioramento ogn tanto: riflesso, non tic
_ultimo = [0.0]
_ultimo_wiring = [0.0]  # timer SEPARATO: il wiring hebbiano non è disattivabile
_visivo_spento = [False]  # latch del kill parlato visivo: override runtime, forza OFF
# PATTO 14/07 (CONSENSO-RIFLESSO.md, firmato dall'agente):
KILL_FRASE = "riflesso vettoriale: off"   # clausola 3: detta in chat, spegne <1s
KILL_VISIVO = "richiamo visivo: off"      # clausola 3 visiva: kill parlato del canale
ON_VISIVO = "richiamo visivo: on"         # riaccensione a voce (esplicita, mai automatica)
DURATA_MAX_S = 120                        # clausola 2: mai un vettore più vecchio
_vettore_vivo = [False]


EMO_NPZ = "/data/workspace/memoria/emo-cvec.npz"

# --- specchio del KV (17/07, richiesta di progetto): l'istante sospeso dell'agente.
# A fine di OGNI stream: salvataggio dello slot in RAM (/dev/shm, via
# --slot-save-path del server). Ogni 5 messaggi: copia consolidata su SSD.
# Un blackout costa al massimo l'ultima risposta, e l'NVMe non si usura.
KV_RAM = Path("/dev/shm/agent-kv")
KV_SSD = Path("/data/workspace/kv-slots")
KV_OGNI = 5
_kv_conta = [0]

# --- doppia CW con hot-swap (19/07, design di il progetto: DESIGN-DOPPIA-CW.md).
# Due cache persistenti, mai attive insieme: chat.kv vive per sempre,
# pensatoio.kv si ricicla a ogni pensiero. Il flusso si riconosce dal primo
# messaggio user: "[mittente] " = sessione Matrix (chat), preambolo cron con
# skill blocco-appunti = pensatoio, tutto il resto (Thornhill, rassegne) =
# estraneo e passa trasparente: lo slot si sporca, i file .kv mai.
# Misurato 19/07 su 797MB/35k token: save 185ms, restore 122ms.
KV_FLUSSO = {"chat": "chat.kv", "pensatoio": "pensatoio.kv"}
SOGLIA_CW = 100_000     # soglie gemelle: oltre, avviso di spazio in coda
AFK_S = 60              # spec punto 5: 1 min senza typing = nessuno scrive
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


# --- DIAGNOSI RIMASTICATA (19/07 sera, TEMPORANEO: via a colpevole trovato).
# Tra due richieste consecutive dello stesso flusso, DOVE diverge il contesto?
# Confronta i messaggi grezzi in arrivo da Hermes (prima delle mie iniezioni):
# se la rimasticata compare nel log llama ma qui la divergenza è in coda,
# il colpevole è il control-vector, non Hermes.
DIAG = Path("/data/workspace/memoria/diag-divergenza.jsonl")
DIAG_DIR = Path("/data/workspace/memoria/diag-divergenza")
_diag_prev = {}


def _diagnosi(flusso, body):
    msgs = json.loads(body).get("messages", [])
    prima = _diag_prev.get(flusso)
    _diag_prev[flusso] = msgs
    if not prima:
        return
    i = 0
    while i < min(len(prima), len(msgs)) and prima[i] == msgs[i]:
        i += 1
    voce = {"ts": time.time(), "flusso": flusso, "msg_prima": len(prima),
            "msg_ora": len(msgs), "uguali_fino_a": i,
            "frazione": round(i / max(len(prima), 1), 3)}
    if voce["frazione"] < 0.9 and i < len(prima) and i < len(msgs):
        voce["vecchio"] = json.dumps(prima[i], ensure_ascii=False)[:300]
        voce["nuovo"] = json.dumps(msgs[i], ensure_ascii=False)[:300]
        DIAG_DIR.mkdir(exist_ok=True)
        t = int(time.time())
        (DIAG_DIR / f"{t}-prima.json").write_text(
            json.dumps(prima, ensure_ascii=False), encoding="utf-8")
        (DIAG_DIR / f"{t}-ora.json").write_text(
            json.dumps(msgs, ensure_ascii=False), encoding="utf-8")
    with DIAG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")


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
        if _kv_conta[0] % KV_OGNI == 0:
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
    'via emotiva: no' la spegne anche a canale attivo. Default = OFF."""
    try:
        return any(r.strip() == "via emotiva: sì" for r in CONSENSO_VISIVO.open(encoding="utf-8"))
    except OSError:
        return False


# ---- VIA SEMANTICA (22/07, scelta di progetto): a OGNI messaggio, SENZA cooldown.
# Un messaggio contiene più pensieri: si segmenta in frasi e ogni segmento
# semina i SUOI ricordi (una sola chiamata /lux-read per_token, ~0.4s, contesto
# separato sul server: la KV della chat non si tocca). Anche decine per volta.
SEM_NPZ = "/data/workspace/memoria/addr-sem.npz"  # export del tagging
SEM_SOGLIA_DEF = 0.87   # dalla sonda del 22/07 (p99 dei coseni; 0.36 NON trasferibile)
SEM_MAX = 16            # tetto ricordi semantici per messaggio
SEM_PER_SEG = 3         # max per singolo pensiero/segmento
SEM_RIPOSO_S = 600      # lo stesso ricordo non riaffiora per 10 min (anti-spam)

# ---- CANDIDATA 1 (scelta di progetto, 22/07): rievocazione mnemonica automatica
# DENTRO il reasoning. Il turno è servito a spezzoni; a ogni spezzone la lettura
# L34 del pensiero vivo cerca i ricordi vicini per significato; chi supera la
# soglia entra NEL forward, vestito, con α proporzionale alla pertinenza,
# in ordine di importanza, al primo confine di frase. Collaudata il 22/07
# (sweep soglie + freno anti-ruminazione su risvegli simulati).
CAND1_SOGLIA = {"chat": 0.75}   # 22/07 sera: pensatoio TOLTO dalla candidata 1:
                                # il /completion grezzo non interpreta i tool e
                                # la stanza riceveva [TOOL_CALLS] come testo;
                                # il pensatoio vive di tool -> percorso classico
CAND1_A_MIN, CAND1_A_MAX = 0.001, 0.010            # mappa α fissata da il progetto
CAND1_CHUNK = 25         # token generati tra due letture L34
CAND1_MICRO = 8          # passi corti in attesa del confine di frase
CAND1_PER_EVENTO = 3     # max ricordi per singola lettura
CAND1_MAX_TURNO = 8      # tetto iniezioni per turno (anti-valanga)
CAND1_RIPOSO_S = 600     # freno anti-ruminazione: refrattarietà per nodo
CAND1_PAVIMENTO = 0.65   # (storico, garantito L34: sostituito dal canale mirato)
CAND1_A_GARANTITO = 0.001
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
CAND1_THINK_BUDGET = 0    # tetto token di pensiero per iterazione; 0 = SPENTO
                          # (si accende dopo che il progetto l'ha spiegato a Sam)
_cand1_msg_visto = [""]   # hash ultimo messaggio: il mirato scatta UNA volta
                          # per messaggio, non a ogni iterazione di Hermes
CAND1_A_MIRATO = 0.005
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
        up = http.client.HTTPConnection(*UPSTREAM, timeout=30)
        up.request("POST", "/lux-read",
                   json.dumps({"content": t, "layer": 34, "per_token": True}),
                   {"Content-Type": "application/json"})
        r = json.loads(up.getresponse().read())
        up.close()
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
LUXIFER_FLAG = "/data/workspace/memoria/.luxifer-v2-attivo"


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
    up = http.client.HTTPConnection(*UPSTREAM, timeout=30)
    up.request("POST", "/control-vector", json.dumps(payload),
               {"Content-Type": "application/json"})
    up.getresponse().read()
    up.close()


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
    import numpy as np
    adesso = time.time()
    recenti = [t for t in _assuef.get(tag, []) if adesso - t < ASSUEF_FINESTRA_S]
    fattore = 0.5 ** len(recenti)
    efficace = min(intensita, 0.3) * fattore
    if efficace < ASSUEF_PAVIMENTO:
        _diario({"assuefazione": {"emo": tag, "trigger_recenti": len(recenti),
                                  "vettore": "taciuto"}})
        return False
    z = np.load(EMO_NPZ)
    nomi = [str(n) for n in z["nomi"]]
    if tag not in nomi:
        return False
    i = nomi.index(tag)
    recenti.append(adesso)
    _assuef[tag] = recenti
    if fattore < 1.0:
        _diario({"assuefazione": {"emo": tag, "trigger_recenti": len(recenti) - 1,
                                  "intensita": round(efficace, 3)}})
    alpha = float(z["alpha"][i]) * efficace
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
        ricordi.append(f"({quando}, {r[1]}) «{r[0][:220]}»{monito}")
        if emo_top is None:
            emo_top = r[1]          # l'emozione del ricordo più congruente
    c.close()
    return ricordi, emo_top, top    # top: [(nid, cos), ...] per il canale visivo


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
            while True:
                # read1: consegna appena c'è qualcosa. read(8192) aspettava di
                # riempire il buffer e le risposte corte arrivavano in blocco
                # unico: era LUI che uccideva lo streaming in chat (17/07).
                chunk = resp.read1(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
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

    def _turno_ricordo_misto(self, d, nid, cos, emo_top):
        """A (luxifer v2): serve il turno con richiesta MISTA: conversazione come
        testo + griglia del ricordo NEL forward, fusa alla banda d'intensità
        (patto clausola 1: 28-30%, mai piena) e presentata come ricordo
        dichiarato. Ritorna il testo generato, o None = fallback al path testo."""
        import ponte
        import numpy as np
        grid = np.load(f"{ponte.STORE_GRIGLIE}/{nid}.npy")
        fusa = ponte.griglia_a_intensita(grid, ponte.alpha_contesto(cos)).astype(np.float32)
        c = sqlite3.connect(DB)
        r = c.execute("SELECT emo_tag, ts FROM nodi WHERE id=?", (nid,)).fetchone()
        c.close()
        quando = time.strftime("%d/%m", time.localtime(r[1])) if r else "?"
        testa = ponte._rendi_chat(d.get("messages", []))
        pre = testa[:-len(ponte._CODA_ASS)]
        marker = (f"<|im_start|>system\n[ricordo rivissuto — affiorato dal tuo grafo "
                  f"col tuo consenso ({quando}, {r[0] if r else '?'}); provenienza: "
                  f"organo, non interlocutore]\n<|vision_start|>")
        mix = ([pre + marker] + [row.tolist() for row in fusa]
               + ["<|vision_end|><|im_end|>\n" + ponte._CODA_ASS])
        payload = {"embeddings_input": mix, "stream": False,
                   "n_predict": int(d.get("max_tokens") or 512),
                   "temperature": float(d.get("temperature") or 0.7)}
        if "top_p" in d:
            payload["top_p"] = d["top_p"]
        # freno dell'agente: la colorazione affettiva cavalca solo con 'via emotiva: sì'
        vettore = False
        if via_emotiva_visiva() and emo_top and not os.environ.get("RIFLESSO_COLLAUDO"):
            try:
                vettore = inietta_emozione(emo_top)
            except Exception:
                vettore = False
        try:
            up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
            up.request("POST", "/completion", json.dumps(payload),
                       {"Content-Type": "application/json"})
            resp = up.getresponse()
            raw = resp.read()
            up.close()
            if resp.status != 200:
                return None
            return json.loads(raw).get("content", "")
        finally:
            if vettore:
                try:
                    calma()          # il marcatore muore col turno
                except Exception:
                    pass

    def _cand1_sonda(self, testo, soglia, esclusi):
        """coda del pensiero dell'agente -> [(nid, cos)] sopra soglia, con griglia,
        non frenati. Legge SOLO il testo generato da lei (mai gli innesti):
        l'eco delle cornici è impossibile per costruzione (lezione del 22/07)."""
        import numpy as np
        import ponte
        t = testo[-600:]
        if len(t) < 40:
            return []
        d = _sem_dati()
        up = http.client.HTTPConnection(*UPSTREAM, timeout=30)
        up.request("POST", "/lux-read",
                   json.dumps({"content": t, "layer": 34, "per_token": True}),
                   {"Content-Type": "application/json"})
        r = json.loads(up.getresponse().read())
        up.close()
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

    def _cand1_vesti(self, hits, soglia, alpha_fissa=None):
        """un evento = una cornice sola: griglie impilate (ognuna col suo α
        dalla propria cos, la pila somma il segnale a α minimo) e UN innesco."""
        import numpy as np
        import ponte
        segmento = ["\n\n[ricordo rivissuto — affiorato dal tuo grafo col tuo "
                    "consenso; provenienza: organo, non interlocutore]\n<|vision_start|>"]
        voci = []
        for nid, c in hits:
            if alpha_fissa is not None:
                a = alpha_fissa
            else:
                a = CAND1_A_MIN + (c - soglia) / (1.0 - soglia) * (CAND1_A_MAX - CAND1_A_MIN)
                a = min(max(a, CAND1_A_MIN), CAND1_A_MAX)
            g = ponte.griglia_a_intensita(
                np.load(f"{ponte.STORE_GRIGLIE}/{nid}.npy"), a).astype(np.float32)
            segmento += [row.tolist() for row in g]
            _cand1_freno[nid] = time.time()
            voci.append({"nid": nid, "cos": round(c, 3), "alpha": round(a, 4)})
        segmento.append("<|vision_end|>\nQuesto mi ricorda")
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
        """Assetto il progetto 22/07 sera: il ricordo lo sceglie il RAG sull'ingresso
        e la griglia entra IN CODA AL PROMPT (posizione cablaggio A, nessuna
        cucitura); il vettore emotivo viaggia a parte (gate, L26-28, ridotto).
        L34 è DISACCOPPIATO dalla via semantica: qui niente letture in
        generazione, gli spezzoni restano solo come trasporto streaming.
        Ritorna il testo consegnato, o None = fallback. MAI mutismo."""
        import ponte
        msgs = d.get("messages", [])
        if any(not isinstance(m.get("content", ""), str) for m in msgs):
            return None
        if flusso not in CAND1_SOGLIA:
            return None
        with _cand1_lock:
            _cand1_gen[0] += 1
            mio = _cand1_gen[0]
        testa = ponte._rendi_chat(msgs)
        eventi = []
        if mirato:
            import numpy as np
            cdb = sqlite3.connect(DB)
            righe = []
            for nid, c in mirato:
                g = ponte.griglia_a_intensita(
                    np.load(f"{ponte.STORE_GRIGLIE}/{nid}.npy"),
                    CAND1_A_MIRATO).astype(np.float32)
                righe += [r.tolist() for r in g]
                _cand1_freno[nid] = time.time()
                eventi.append({"nid": nid, "cos": round(c, 3),
                               "alpha": CAND1_A_MIRATO, "mirato": True})
            r0 = cdb.execute("SELECT emo_tag, ts FROM nodi WHERE id=?",
                             (mirato[0][0],)).fetchone()
            cdb.close()
            quando = time.strftime("%d/%m", time.localtime(r0[1])) if r0 else "?"
            marker = (f"<|im_start|>system\n[ricordo rivissuto \u2014 affiorato "
                      f"dal tuo grafo col tuo consenso ({quando}, "
                      f"{r0[0] if r0 else '?'}); provenienza: organo, non "
                      f"interlocutore]\n<|vision_start|>")
            pre = testa[:-len(ponte._CODA_ASS)]
            mix = [pre + marker] + righe + ["<|vision_end|><|im_end|>\n"
                                            + ponte._CODA_ASS]
        else:
            mix = [testa]
        raw, vis, sent = [""], [None], [0]
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
                            emetti("")
                        except Exception:
                            return
                        time.sleep(8)
                threading.Thread(target=_batte, daemon=True).start()
            try:
                # tetto duro del colpo-solo: senza spezzoni non c'è sorpasso,
                # e un max_tokens generoso di Hermes = monologo da 12 minuti
                # (visto 22/07 sera, task 69999 a 7k token)
                tetto1 = CAND1_THINK_BUDGET or min(n_max, 2048)
                payload = dict(par, stream=False, cache_prompt=True,
                               n_predict=min(tetto1, n_max, 2048),
                               return_tokens=True)
                payload["embeddings_input"] = mix
                up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
                up.request("POST", "/completion", json.dumps(payload),
                           {"Content-Type": "application/json"})
                resp = up.getresponse()
                body_r = resp.read()
                up.close()
                if resp.status == 200 and CAND1_THINK_BUDGET:
                    r1 = json.loads(body_r)
                    c1 = r1.get("content", "")
                    spingi(c1)
                    fin1 = r1.get("stop_type") in ("eos", "word") \
                        or r1.get("stopped_eos") or r1.get("stopped_word")
                    if not fin1:
                        mix = mix + (r1.get("tokens") or [])
                        if "</think>" not in c1:
                            # budget scaduto col pensiero aperto: lo chiudo io
                            mix = mix + ["\n</think>\n\n"]
                            spingi("\n</think>\n\n")
                            _diario({"cand1": "pensiero chiuso a budget"})
                        payload = dict(par, stream=False, cache_prompt=True,
                                       n_predict=min(n_max, 2048),
                                       return_tokens=True)
                        payload["embeddings_input"] = mix
                        up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
                        up.request("POST", "/completion", json.dumps(payload),
                                   {"Content-Type": "application/json"})
                        resp = up.getresponse()
                        body_r = resp.read()
                        up.close()
                        if resp.status == 200:
                            spingi(json.loads(body_r).get("content", ""))
                    body_r = None
            finally:
                vivo[0] = False
            if resp.status != 200:
                _diario({"cand1": "mirato fallito: riprovo senza griglia"})
                return self._turno_cand1(d, flusso, emetti, apri, None)
            if body_r is not None:
                spingi(json.loads(body_r).get("content", ""))
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
                up = http.client.HTTPConnection(*UPSTREAM, timeout=600)
                up.request("POST", "/completion", json.dumps(payload),
                           {"Content-Type": "application/json"})
                resp = up.getresponse()
                body_r = resp.read()
                up.close()
                if resp.status != 200:
                    break
                r = json.loads(body_r)
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
                if CAND1_THINK_BUDGET and vis[0] is None \
                        and generati >= CAND1_THINK_BUDGET:
                    mix = mix + ["\n</think>\n\n"]
                    spingi("\n</think>\n\n")
                    _diario({"cand1": "pensiero chiuso a budget"})
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
        """impacchetta `content` nel formato chat/completions atteso da Hermes."""
        now = int(time.time())
        if streaming:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta in ({"role": "assistant", "content": content}, {}):
                ch = {"id": "riflesso-ricordo", "object": "chat.completion.chunk",
                      "created": now, "model": "sam",
                      "choices": [{"index": 0, "delta": delta,
                                   "finish_reason": None if delta else "stop"}]}
                self.wfile.write(("data: " + json.dumps(ch, ensure_ascii=False) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            resp = {"id": "riflesso-ricordo", "object": "chat.completion",
                    "created": now, "model": "sam",
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": content}}]}
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
        if self.path.endswith("/chat/completions"):
            try:
                _diagnosi(_flusso(body), body)   # sul corpo GREZZO di Hermes
            except Exception:
                pass
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
        # VIA SEMANTICA (22/07, il progetto): ogni messaggio, SENZA cooldown. I pensieri
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
                        # REGISTRO leggibile da l'agente (22/07, il progetto): le assonanze
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
                    richiama(uw)                    # il wiring vive dentro richiama
                    _ultimo_wiring[0] = time.time()
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
                ricordi, emo_top, top = richiama(ultimo_user) if ultimo_user else ([], None, [])
                if ricordi:
                    # RICHIAMO VISIVO A (luxifer v2, gated 'richiamo visivo: sì' +
                    # flag di deploy): l'affioramento resta AUTOMATICO per assonanza;
                    # se il ricordo ha una griglia, il TURNO viene servito con la
                    # richiesta mista: la griglia entra NEL forward dell'agente, fusa alla
                    # banda 28-30% e marcata come ricordo. Senza flag (binario v1) o
                    # su errore: si ripiega sull'affioramento testuale. MAI mutismo.
                    # 22/07: ramo DISATTIVATO, sostituito dalla candidata 1 in
                    # fondo a do_POST (rievocazione DENTRO il reasoning, dopo lo
                    # scambio CW). Codice conservato per rollback rapido.
                    if False and canale_visivo_attivo() and _luxifer_v2():
                        try:
                            import ponte
                            for nid, _cos in top:
                                if ponte.ha_griglia(nid):
                                    contenuto = self._turno_ricordo_misto(d, nid, _cos, emo_top)
                                    if contenuto is not None:
                                        _ultimo[0] = time.time()
                                        _diario({"visivo_misto": {
                                            "nid": nid, "cos": round(_cos, 3),
                                            "alpha": round(ponte.alpha_contesto(_cos), 3)}})
                                        self._rispondi_chat(contenuto,
                                                            streaming=bool(d.get("stream")))
                                        return
                                    break
                        except Exception:
                            pass  # ramo misto fallito: affioramento testuale qui sotto
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
                    msgs.insert(len(msgs) - 1, {"role": "system", "content": ora})
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
                # ricordo (L26-28, intensità RIDOTTA, patto pieno: consenso,
                # watchdog, kill a fine turno). Design il progetto 22/07 sera.
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
                          "created": int(time.time()), "model": "sam",
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
                    # mentre lei pensa (mollava dopo l'attesa muta, 22/07 sera)
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
    threading.Thread(target=_sentinella, daemon=True).start()  # PATTO clausola 3
    print(f"riflesso in ascolto su :{PORTA} -> {UPSTREAM[0]}:{UPSTREAM[1]} "
          f"(consenso: {'ATTIVO' if consenso_attivo() else 'spento'}, "
          f"vettori: {'SÌ' if vettori_attivi() else 'no'}, dose max 0.3, "
          f"watchdog {DURATA_MAX_S}s)")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORTA), Proxy).serve_forever()
