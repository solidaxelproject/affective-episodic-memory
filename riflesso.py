#!/usr/bin/env python3
# RIFLESSO PRE-AZIONE (issue #1, pezzo 3) — proxy tra Hermes e llama-lux.
# Prima che l'agente risponda, il messaggio interroga il Lux degli engrammi
# (servizio_lux.py :8132): il ricordo che affiora entra come turno del tool
# memorinvolontaria (chiamata + risposta: un ricordo per volta dal 09/11, col numero,
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
import contextlib
import hashlib
import html
import http.client
import http.server
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ponte  # noqa: E402  (unica porta verso :8090)
import steering  # noqa: E402  (modulo unico, 10/11: i vettori e le fasce dei test)
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "engrammi"))
import via_emotiva as VE  # noqa: E402  (1.19.0, PIANO-1.19-VIA-EMOTIVA: J-lens, umore, diario delle letture)

UPSTREAM = ("127.0.0.1", 8090)
PORTA = 8091
CONSENSO = Path(os.environ.get("RIFLESSO_CONSENSO",
    "/data/workspace/genesi/CONSENSO-RIFLESSO.md"))
DIARIO = "/data/workspace/memoria/diario-riflessi.jsonl"
# B6 (31/10, engrammi/PIANO-FIRMA-ENGRAMMI.md): i messaggi del turno chiuso vanno a firma-subito, il ricordo
# nasce subito e non piu' nella notturna
CODA_FIRMA = os.environ.get("CODA_FIRMA", "/data/workspace/memoria/coda-firma.jsonl")
_HANDLE = re.compile(r"^\[([a-z0-9_]+)\]\s?(.*)$", re.DOTALL)   # come estrai-matrix: solo handle veri (minuscoli)
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
_vettore_di = [None]   # 11/11: il watchdog dell'ultimo vettore di un ricordo (quello rimandato non spegne il successivo)
# issue #3 punto A, design dell'utente (18/10): il vettore appartiene alla KV cache
# del suo flusso. Allo scambio se ne va con la cache messa in pausa; al ripristino
# torna alla dose a cui era arrivato e la discesa riprende da li': il tempo della
# discesa scorre solo mentre la cache del flusso sta nello slot. Piu' vettori
# attivi si SOMMANO (l'utente 18/10, test multivettore); come sommarli e la curva
# della discesa sono della fase 2 (PIANO-LUX-FASI-v1.12.md, punto 7).
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

# ---- MEMORIA INVOLONTARIA (l'utente 11/10, piano del refactoring Lux + richiamo):
# il Lux degli engrammi sceglie un ricordo per messaggio (quanti=1, l'utente 09/11; erano fino a 4
# dalla 1.10.0), sopra soglia, mai uno già consegnato nella conversazione; i ricordi
# entrano insieme in un turno del tool, che
# è dichiarato sempre (a consenso attivo) così il prefisso della cache non cambia.
LUX = "http://127.0.0.1:8132/consegna"
LUX_FORZA = "http://127.0.0.1:8132/forza"
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

# ---- ORA DEI MESSAGGI: l'ora di ARRIVO dell'ultimo messaggio user, registrata in "arrivi" (17/10, formato
# [d/m/aaaa|h:mm], dato della fase 2 del Lux). 10/11 (l'utente, M2 M3): l'agente la vede solo nel blocco metadati,
# [hh:mm|gg/mm/aaaa]; l'ora davanti a un messaggio dell'utente ogni 5 (16/10) e' tolta. "ore" resta per le voci di prima.
ORE = Path("/data/workspace/memoria/ore-messaggi.json")
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
SOGLIA_CW = 100_000     # chat: oltre, switch di CW a fine turno (K4); pensatoio: avviso di spazio in coda (K17)
SOGLIA_AVVISO = 90_000  # K4 (10/11): fra 90k e 100k l'avviso nella chiamata del riepilogo
AFK_S = 60              # spec punto 5: 1 min senza typing = l'utente non c'è
_cw = ["chat"]          # cosa c'è nello slot adesso (al deploy corrente->chat)
_cw_lock = threading.Lock()
_pens_vivi = []         # socket del pensatoio verso :8090: la chat li taglia
_chat_calda = [0.0]     # ultima attività chat (fine risposta o typing visto)
_chat_in_volo = [0]     # richieste della chat in corso (issue #3 punto A): il pensatoio aspetta
_altro_in_volo = [0]    # 10/11: richieste estranee (cron, servizi di Hermes) che usano lo slot: il riepilogo aspetta
ATTESA_ALTRO_S = 300    # oltre, il riepilogo di quello scambio salta (valore di CC)
_altro_lock = threading.Lock()   # anche per _chat_in_volo (revisione 3.5.3, punto 4: due thread)
_salva_ultimo = [None]   # il salvataggio della chat piu' recente: il riepilogo lo aspetta (revisione 3.5.3, punto 2)
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


# --- riepilogo a catena di montaggio (l'utente 20/10, PIANO-RIEPILOGO-KV.md): dopo ogni risposta all'utente,
# l'agente scrive il succo dello scambio in una riga; le righe si accodano in una CW a parte (riepilogo.kv) e alla
# dormita diventano il blocco in testa alla chat nuova. Solo la chat, mai il pensatoio (20/10).
RIEPILOGO = Path("/data/memoria-episodica-affettiva/riepilogo.json")
RIEPILOGO_PROMUOVI = Path("/data/memoria-episodica-affettiva/.riepilogo-promuovi")   # lo scrive dormi-esegui.sh
RIEPILOGO_KV = "riepilogo.kv"
RIEPILOGO_BASE = "riepilogo-base.kv"   # K2 (10/11): la parte fissa sola, punto di partenza della CW nuova
# 10/11: l'agente scrive la riga con write_file su questo file (skill riepilogo); il riflesso la esegue (Hermes in
# quel momento non c'e'), una chiamata diretta altrove si scarta. Il file riparte vuoto a ogni sessione nuova
RIEPILOGO_LOG = Path("/data/workspace/memoria/logRiepilogo.md")
RIEPILOGO_LOG_SAM = ("/workspace/memoria/logRiepilogo.md",
                     "/home/agente/workspace/memoria/logRiepilogo.md")   # lo stesso file nel container (3.5.3)
# una chiamata tagliata dal tetto dei token (senza le chiusure) vale con la parte che c'e'
_WRITE_FILE = re.compile(r"<function=write_file>(.*?)(?:</function>|$)", re.S)
_PARAMETRO = re.compile(r"<parameter=(\w+)>(.*?)(?:</parameter>|(?=<parameter=)|$)", re.S)
RIEPILOGO_TETTO = 40_000    # token (caratteri / 3): oltre, via le righe piu' vecchie. Valore di CC
INTESTAZIONE_RIEPILOGO = ("Ecco dov'ero rimasta, questo è il succo della conversazione fino al momento in cui mi "
                          "sono addormentata:")
ISTRUZIONE_RIEPILOGO = (
    "Devo scrivere, in meno di 60 parole, il succo di quest'ultimo messaggio o di quello dell'utente se necessario: le "
    "informazioni salienti che voglio conservare dell'ultimo scambio. Non i messaggi precedenti. Solo testo, numeri o "
    "simboli logici se utili, per esempio: uguale può diventare =, implica →, maggiore >. Se necessario posso "
    "inserire il codice di un ricordo che reputo utile per questo riassunto. Se in questo scambio mi è affiorato un "
    "ricordo, aggiungo il suo codice. Lo scrivo con write_file in /workspace/memoria/logRiepilogo.md.")   # coda: l'utente 10/11
SEPARATORE = "══"   # da questa riga in poi il system di Hermes cambia fra le sessioni (MEMORY, data)
# BLOCCO B (l'utente 10/11, PIANO-RIEPILOGO-KV.md 3.5, K4 K10 K14 K15 K18): l'avviso va PRIMA dell'istruzione, solo
# nella chiamata del riepilogo (la chat salvata non lo contiene); [cwswitch] in coda al riepilogo = switch subito
AVVISO_90K = (
    "[avviso di spazio: la conversazione ha superato i 90mila token e la finestra si sta riempiendo. A 100mila "
    "passerò da sola a una conversazione nuova, che riparte dal mio riepilogo. Se voglio farlo prima, scrivo "
    "[cwswitch] in coda al riepilogo.]")
CWSWITCH = re.compile(r"\[cwswitch\]", re.I)
# lo switch = la dormita di oggi: agente-dormi.path -> dormi-esegui.sh (sessione nuova + .riepilogo-promuovi)
DORMI_FLAG = Path("/data/workspace/memoria/.dormi-richiesto")
SWITCH_IN_CORSO = Path("/data/memoria-episodica-affettiva/.switch-in-corso")   # lo tiene dormi-esegui.sh mentre gira
SWITCH_RITENTA_S = 900   # switch chiesto ma nessuna promozione: si richiede dopo 15 min (valore di CC)
_switch = {"motivo": None, "chiesto": 0.0}   # motivo (rimandato o in attesa della promozione); ultima richiesta


def _riga_scritta(testo):
    """il content della chiamata write_file dell'agente su logRiepilogo.md, None se non c'e'. Una chiamata tagliata
    prima del path vale (3.5.3: l'agente a volte scrive prima il content e il tetto dei token taglia il resto)"""
    for c in _WRITE_FILE.finditer(testo):
        p = dict(_PARAMETRO.findall(c.group(1)))
        path = p.get("path", "").strip()
        if path in RIEPILOGO_LOG_SAM or (not path and "content" in p and not c.group(0).endswith("</function>")):
            return p.get("content", "")
    return None


def _riepilogo_carica():
    vuoto = {"blocco": [], "nuovi": []}
    try:
        st = json.loads(RIEPILOGO.read_text(encoding="utf-8"))
        return {"blocco": list(st["blocco"]), "nuovi": list(st["nuovi"])}
    except FileNotFoundError:
        return vuoto
    except Exception as e:
        _diario({"riepilogo": f"riepilogo.json illeggibile, niente blocco: {e}"})
        return vuoto


def _riepilogo_salva(st):
    tmp = RIEPILOGO.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    tmp.replace(RIEPILOGO)


def _blocco(righe):
    return INTESTAZIONE_RIEPILOGO + "\n" + "\n".join(righe) + "\n\n" if righe else ""


def _nel_tetto(righe):
    while righe and len(_blocco(righe)) / 3 > RIEPILOGO_TETTO:
        righe = righe[1:]
    return righe


def _riga_separatore(testo):
    """dove comincia la riga ══, -1 se manca"""
    i = testo.find(SEPARATORE)
    return testo.rfind("\n", 0, i) + 1 if i >= 0 else -1


def _con_blocco(system, righe):
    """il blocco subito prima della riga ══: prima il system e' fisso fra le sessioni e la cache lo riusa"""
    i = _riga_separatore(system)
    if i < 0:
        _diario({"riepilogo": "riga ══ non trovata: blocco in fondo al system"})
        return system + "\n\n" + _blocco(righe)
    return system[:i] + _blocco(righe) + system[i:]


def _metti_blocco(d, righe):
    """in place sul corpo di una richiesta della chat"""
    msgs = d.get("messages", [])
    if righe and msgs and msgs[0].get("role") == "system":
        msgs[0]["content"] = _con_blocco(msgs[0]["content"], righe)


# R6 (l'utente 24/10, PIANO-REVISIONI-FUORI-CACHE.md): la parte fissa del system (prima di ══, elenco skill compreso)
# cambia nella chat solo quando nasce una CW del riepilogo nuova. Qui: la fissa con cui e' nata la chat in corso, quella
# di riepilogo.kv in formazione e l'elenco skill adottato a meta' sessione (sotto 20 righe del log)
FISSA = Path("/data/memoria-episodica-affettiva/riepilogo-fissa.json")
ELENCO_DA = "## Skills (mandatory)\n"   # i marcatori fissi di prompt_builder.py (build_skills_system_prompt)
ELENCO_A = "Only proceed without loading a skill if genuinely none are relevant to the task."
ELENCO_RIGHE = 20
_elenco_ok = [None]          # CONTROLLO della sessione: None = da fare, poi True/False
_fissa_avvisata = [False]    # la sostituzione va nel diario una volta per sessione
# l'elenco come lo compone Hermes (system_prompt.py:260-285, postura di default); model_tools riempie il registry
SKILLS_HERMES = """import json, sys
import model_tools
from agent.prompt_builder import build_skills_system_prompt
t = set(json.loads(sys.stdin.read()))
ts = {x for x in map(model_tools.get_toolset_for_tool, t) if x}
print("\\n" + json.dumps(build_skills_system_prompt(available_tools=t, available_toolsets=ts)))
"""


def _fissa_carica():
    try:
        st = json.loads(FISSA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st = {}
    except Exception as e:
        _diario({"riepilogo": f"riepilogo-fissa.json illeggibile: {e}"})
        st = {}
    return {k: st.get(k) for k in ("chat", "riepilogo", "elenco")}


def _fissa_salva(st):
    tmp = FISSA.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FISSA)


def _fissa(testo):
    """la parte del system prima della riga ══, None se manca"""
    i = _riga_separatore(testo)
    return testo[:i] if i >= 0 else None


def _elenco(testo):
    """l'elenco skill dentro il system, None se mancano i marcatori"""
    i = testo.find(ELENCO_DA)
    j = testo.find(ELENCO_A, i)
    return testo[i:j + len(ELENCO_A)] if i >= 0 and j >= 0 else None


def _metti_fissa(d):
    """in place sul corpo di una richiesta della chat: la parte fissa della cache al posto di quella di Hermes.
    Torna il system e i nomi dei tool di Hermes com'erano (per il riepilogo e per l'elenco)"""
    msgs = d.get("messages", [])
    if not msgs or msgs[0].get("role") != "system":
        return None
    h = msgs[0]["content"]
    hermes = {"system": h, "tools": [t["function"]["name"] for t in d.get("tools") or [] if t.get("function")]}
    fc, i = _fissa_carica()["chat"], _riga_separatore(h)
    if fc and i >= 0:
        if h[:i] != fc and not _fissa_avvisata[0]:
            _fissa_avvisata[0] = True
            _diario({"riepilogo": "parte fissa della cache al posto di quella di Hermes (skill cambiate)"})
        msgs[0]["content"] = fc + h[i:]
    return hermes


def _skills_da_hermes(tools):
    p = subprocess.run(["docker", "exec", "-i", "agente", "python3", "-c", SKILLS_HERMES], input=json.dumps(tools),
                       capture_output=True, text=True, timeout=5, check=True)
    return json.loads(p.stdout.strip().splitlines()[-1])


def _elenco_hermes(hermes):
    """l'elenco skill come lo comporrebbe Hermes adesso, se e' cambiato e il log del riepilogo ha meno di 20 righe;
    None = niente da cambiare. Fuori dai lucchetti (docker exec ~0,5 s, misura 10/11; tetto 5 s: il riepilogo aspetta)"""
    if not hermes or _elenco_ok[0] is False or len(_riepilogo_carica()["nuovi"]) >= ELENCO_RIGHE:
        return None
    in_uso = _fissa_carica()["elenco"] or _elenco(hermes["system"])
    if in_uso is None:
        return None
    try:
        uscita = _skills_da_hermes(hermes["tools"])
    except Exception as e:      # es. durante lo switch: si salta il giro, il CONTROLLO resta da fare
        _diario({"riepilogo": f"elenco skill non letto da Hermes: {e}"})
        return None
    if _elenco_ok[0] is None:   # CONTROLLO: a skill invariate Hermes deve dare l'elenco che sta nel system
        _elenco_ok[0] = uscita == in_uso
        if not _elenco_ok[0]:
            _diario({"riepilogo": "elenco skill di Hermes diverso da quello del system: spento per la sessione"})
        return None
    return uscita if uscita != in_uso else None


def _turno_finito(corpo, esito):
    """l'ultima risposta a un messaggio dell'utente nella chat, comunque sia finita, mai a meta' di un giro di tool:
    il background review e il memory flush di Hermes non cominciano con "[", il pensatoio si', ma il suo flusso
    e' un altro. Il corpo e' quello SENZA metadati: il blocco in testa comincia sempre con "[" """
    if _flusso(corpo) != "chat" or esito.get("tool_calls") or esito.get("interrotta"):
        return False
    msgs = json.loads(corpo).get("messages", [])
    ultimo = next((m.get("content") for m in reversed(msgs) if m.get("role") == "user"), "")
    return isinstance(ultimo, str) and ultimo.startswith("[")


def _deve_riassumere(corpo, esito):
    """solo la risposta FINALE a un messaggio dell'utente, finita bene e con del testo"""
    return esito.get("finish") == "stop" and bool((esito.get("testo") or "").strip()) and _turno_finito(corpo, esito)


def _chiedi(path, payload):
    st, r = ponte.post(path, payload, timeout=600)
    if st != 200:
        raise RuntimeError(f"{path}: HTTP {st}")
    return r


@contextlib.contextmanager
def _slot_libero(scadenza=None):
    """10/11: i lucchetti del riepilogo, presi solo con lo slot libero da richieste estranee (cron, servizi di
    Hermes): rimettere la chat sotto una di loro faceva salvare come chat.kv lo stato di un'altra conversazione.
    Si aspetta fuori dai lucchetti (la colorazione di quella usa _vettore_lock). True = presi, False = tempo scaduto.
    Revisione 3.5.3, punto 2: si aspetta anche una risposta della chat in volo (senza scadenza: finisce sempre) e il
    suo salvataggio, se no il restore rimette il chat.kv di prima e lo stato del turno nuovo si perde"""
    scadenza = scadenza or time.time() + ATTESA_ALTRO_S
    while True:
        while _altro_in_volo[0] or _chat_in_volo[0]:
            if _altro_in_volo[0] and time.time() > scadenza:
                yield False
                return
            time.sleep(0.5)
        if _salva_ultimo[0]:
            _salva_ultimo[0].join()
        _vettore_lock.acquire()
        _cw_lock.acquire()
        if not _altro_in_volo[0] and not _chat_in_volo[0]:
            break
        _cw_lock.release()
        _vettore_lock.release()
    try:
        yield True
    finally:
        _cw_lock.release()
        _vettore_lock.release()


def _riassumi(corpo, risposta, ragionamento="", senza=None, scadenza=None, hermes=None, elenco=None):
    """l'agente scrive il succo dello scambio nello slot della chat, la riga va in coda al blocco nella CW del
    riepilogo, la chat torna nello slot. Tutto dentro i lucchetti: una richiesta della chat che arriva intanto
    aspetta (~6 s). Gli errori vanno solo nel diario: mai bloccare la parola dell'agente.
    Torna (switch, esito): switch = l'agente, avvisata dei 90k, l'ha chiesto con [cwswitch] (K15); esito ok/vuoto/scartato/fallito."""
    avviso = SOGLIA_AVVISO < _tok_cw["chat"] <= SOGLIA_CW   # conteggio della chat appena salvata (3.3 punto 11)
    switch, esito = False, "fallito"
    with _slot_libero(scadenza) as libero:   # 10/11: mai con una richiesta estranea nello slot
        if not libero:
            _diario({"riepilogo": "saltato: una richiesta estranea tiene lo slot da troppo"})
            return False, "fallito"
        if _vettore_vivo[0]:    # niente vettori di steering nel riepilogo
            calma()
        try:
            if _cw[0] == "pensatoio":
                _interrompi_pensatoio()     # come fa la chat (spec punto 4)
            if _cw[0] != "chat":
                _scambia("chat")
            d = json.loads(corpo)
            tools = d.get("tools") or []
            # il prompt della risposta appena data, reso dal server, + la risposta + l'ISTRUZIONE a mano: un
            # messaggio user nuovo farebbe togliere al template il <think> dei giri di tool del turno e il
            # turno intero si riprocesserebbe (revisione 20/10)
            resa = _chiedi("/apply-template", {k: v for k, v in d.items()
                                               if k in ("messages", "tools", "tool_choice",
                                                        "chat_template_kwargs")})["prompt"]
            if resa.endswith("<think>\n"):   # il ragionamento del server finisce gia' col suo a capo
                resa += ragionamento + ("" if ragionamento.endswith("\n") else "\n") + "</think>\n\n"
            gen = _chiedi("/completion", {
                "prompt": resa + risposta + "<|im_end|>\n<|im_start|>user\n"
                          + (AVVISO_90K + "\n\n" if avviso else "") + ISTRUZIONE_RIEPILOGO
                          + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n",
                "n_predict": 220, "cache_prompt": True})   # 160 + la chiamata write_file
            scritta = _riga_scritta(gen.get("content") or "")
            switch = avviso and bool(CWSWITCH.search(gen.get("content") or ""))   # anche dopo la write_file (3.5.3)
            if scritta is None:
                _diario({"riepilogo": f"scartato, niente write_file su logRiepilogo.md: {(gen.get('content') or '')[:300]}"})
                return switch, "scartato"
            riga = " ".join(CWSWITCH.sub("", scritta).split())
            if not riga:
                _diario({"riepilogo": "riassunto vuoto"})
                return switch, "vuoto"
            st = _riepilogo_carica()
            st["nuovi"].append(riga)
            _riepilogo_salva(st)
            with RIEPILOGO_LOG.open("a", encoding="utf-8") as f:
                f.write(riga + "\n")
            # il system della CW del riepilogo: quello ORIGINALE di Hermes (R6), con l'elenco skill adottato,
            # e il blocco delle righe di questa sessione
            sistema = hermes["system"] if hermes else d["messages"][0]["content"].replace(_blocco(st["blocco"]), "", 1)
            fs = _fissa_carica()
            if elenco and elenco != fs["elenco"]:
                fs["elenco"] = elenco
                _fissa_salva(fs)
                _diario({"riepilogo": "elenco skill nuovo nella CW del riepilogo"})
            vecchio = _elenco(sistema)
            if fs["elenco"] and vecchio:
                sistema = sistema.replace(vecchio, fs["elenco"], 1)
            resa = _chiedi("/apply-template", {
                "messages": [{"role": "system", "content": _con_blocco(sistema, _nel_tetto(st["nuovi"]))},
                             {"role": "user", "content": "."}],   # il template vuole un user: si taglia via
                "tools": tools})["prompt"]
            i = _riga_separatore(resa)
            if i < 0:
                raise ValueError("riga ══ non trovata nel prompt reso")
            righe_blocco = _blocco(_nel_tetto(st["nuovi"]))
            if not resa[:i].endswith(righe_blocco):
                raise ValueError("blocco del riepilogo non trovato nel prompt reso")
            # parte fissa cambiata (elenco nuovo): riepilogo.kv divergerebbe a meta', si riparte dalla base
            if (KV_RAM / RIEPILOGO_KV).exists() and fs["riepilogo"] in (None, _fissa(sistema)):
                _slot("restore", RIEPILOGO_KV)
            else:
                _base_riepilogo(resa[:i - len(righe_blocco)])
            _chiedi("/completion", {"prompt": resa[:i], "n_predict": 1, "cache_prompt": True,
                                    "checkpoint_tag": "riepilogo"})   # K3: una riga, un checkpoint protetto
            if not _slot("save", RIEPILOGO_KV):
                raise RuntimeError("save di riepilogo.kv fallita")
            fs["riepilogo"] = _fissa(sistema)
            _fissa_salva(fs)
            esito = "ok"
        except Exception as e:
            _diario({"riepilogo": f"fallito: {e}"})
        finally:
            ok = False
            try:
                ok = _slot("restore", KV_FLUSSO["chat"])
            except Exception:
                pass
            if not ok:      # lo slot tiene il riepilogo: la prossima richiesta della chat rifa' il restore
                _diario({"riepilogo": "chat non rimessa nello slot"})
            _cw[0] = "chat" if ok else "altro"
            # niente prefill anticipato con un'altra richiesta della chat o con lo switch in arrivo
            if ok and senza and not _chat_in_volo[0] and not switch and _tok_cw["chat"] <= SOGLIA_CW:
                try:
                    _anticipa(senza, risposta)
                except Exception as e:
                    _diario({"metadati": f"prefill anticipato fallito: {e}"})
    return switch, esito


def _base_riepilogo(fissa):
    """K2 (10/11): la CW del riepilogo nuova parte dalla cache BASE (solo la parte fissa del system, tools
    compresi), rifatta solo quando la parte fissa cambia. Solo dentro _cw_lock"""
    imp, segno = _impronta(fissa), KV_RAM / (RIEPILOGO_BASE + ".impronta")
    if (KV_RAM / RIEPILOGO_BASE).exists() and segno.exists() and segno.read_text() == imp \
            and _slot("restore", RIEPILOGO_BASE):
        return
    _chiedi("/completion", {"prompt": fissa, "n_predict": 1, "cache_prompt": True, "checkpoint_tag": "sistema"})
    if _slot("save", RIEPILOGO_BASE):
        segno.write_text(imp)


def _anticipa(senza, risposta):
    """3.5 (10/11): PREFILL ANTICIPATO a chat ferma: il messaggio dell'utente SENZA metadati e la risposta appena
    data senza ragionamento, come li vedra' il turno dopo (un user "." dopo: il template toglie il <think>), fino
    alla fine della risposta: la CRESTA, checkpoint protetto (K1). Al turno dopo si prefilla solo il messaggio nuovo.
    Solo dentro _cw_lock, con la chat nello slot"""
    d = json.loads(senza)
    resa = _chiedi("/apply-template", {
        **{k: v for k, v in d.items() if k in ("tools", "tool_choice", "chat_template_kwargs")},
        "messages": d["messages"] + [{"role": "assistant", "content": _senza_imitati(risposta).rstrip()},
                                     {"role": "user", "content": "."}]})["prompt"]
    _chiedi("/completion", {"prompt": resa[:resa.rindex("<|im_start|>user")], "n_predict": 1, "cache_prompt": True,
                            "checkpoint_tag": "cresta"})


def _forse_switch(cwswitch, esito_riepilogo="non fatto"):
    """Fine di un turno dell'utente (K4, K15, K18): switch di CW se l'agente l'ha chiesto o se la chat supera i 100k,
    qualunque sia stato l'esito del riepilogo. Mai con una risposta della chat in volo (docker stop la taglierebbe):
    si rimanda alla fine di quella. Uno solo finche' non c'e' la promozione (revisione del blocco B, punto 1)."""
    motivo = "[cwswitch]" if cwswitch else "oltre 100k" if _tok_cw["chat"] > SOGLIA_CW else _switch["motivo"]
    if not motivo or time.time() - _switch["chiesto"] < SWITCH_RITENTA_S \
            or SWITCH_IN_CORSO.exists() or RIEPILOGO_PROMUOVI.exists():   # uno switch c'e' gia' (es. mezzanotte)
        return
    if _chat_in_volo[0]:
        _switch["motivo"] = motivo
        return
    DORMI_FLAG.touch()
    _switch.update(motivo=motivo, chiesto=time.time())   # fino a _promuovi: si richiede se la rotazione fallisce (3.5.3)
    _diario({"cw": f"switch: {motivo} ({_tok_cw['chat']} tok), riepilogo {esito_riepilogo}"})


def _fine_chat(corpo, esito, salva, senza=None, hermes=None):
    """dopo l'ultima risposta di un turno dell'utente: riepilogo (se la risposta e' finita bene), poi lo switch.
    Uno switch rimandato parte alla fine di qualunque richiesta della chat fuori da un giro di tool (3.5.3, 3b)"""
    if not _turno_finito(senza or corpo, esito):
        if _switch["motivo"] and not esito.get("tool_calls") and not esito.get("interrotta"):
            _forse_switch(False)
        return
    if salva:
        salva.join()    # il conteggio dei token resta quello della chat appena salvata
    cwswitch, fatto = False, "non fatto"
    try:
        if _deve_riassumere(senza or corpo, esito):
            try:
                elenco = _elenco_hermes(hermes)
            except Exception as e:     # mai saltare il riepilogo per l'elenco
                elenco = None
                _diario({"riepilogo": f"elenco skill: {e}"})
            cwswitch, fatto = _riassumi(corpo, esito["testo"], esito["ragionamento"], senza, hermes=hermes,
                                        elenco=elenco)
    except Exception as e:      # K18: lo switch parte comunque
        fatto = f"fallito: {e}"
        _diario({"riepilogo": fatto})
    try:
        _forse_switch(cwswitch, fatto)
    except Exception as e:
        _diario({"cw": f"switch non chiesto: {e}"})


def _promuovi():
    """Prima richiesta della chat dopo una dormita (flag di dormi-esegui.sh): le righe della sessione chiusa
    diventano il blocco, riepilogo.kv (parte fissa + blocco gia' in cache) diventa la chat nuova e il riepilogo
    riparte da una CW vuota. Solo dentro _cw_lock."""
    if not RIEPILOGO_PROMUOVI.exists():
        return
    st = _riepilogo_carica()
    # revisione del blocco B, punto 1: un secondo switch prima di righe nuove tiene il blocco appena promosso
    blocco = _nel_tetto(st["nuovi"]) if st["nuovi"] else st["blocco"]
    if st["nuovi"] and len(blocco) < len(st["nuovi"]):
        _diario({"riepilogo": f"oltre il tetto: tolte {len(st['nuovi']) - len(blocco)} righe vecchie"})
    _riepilogo_salva({"blocco": blocco, "nuovi": []})
    RIEPILOGO_LOG.write_text("", encoding="utf-8")   # la sessione nuova riparte da un log vuoto
    RIEPILOGO_PROMUOVI.unlink()
    _tok_cw["chat"] = 0     # il conteggio della chat vecchia non deve chiedere un altro switch
    _switch.update(motivo=None, chiesto=0.0)
    kv = KV_RAM / RIEPILOGO_KV
    fs = {"chat": None, "riepilogo": None, "elenco": None}   # R6: la chat nuova ha la parte fissa di riepilogo.kv
    if kv.exists():
        if _cw[0] in KV_FLUSSO and _cw[0] != "chat":
            if _cw[0] == "pensatoio":
                _interrompi_pensatoio()
            _slot("save", KV_FLUSSO[_cw[0]])
        if _slot("restore", RIEPILOGO_KV):
            fs["chat"] = _fissa_carica()["riepilogo"]
        _cambia_cw("chat")
    _fissa_salva(fs)
    _elenco_ok[0], _fissa_avvisata[0] = None, False
    for f in (kv, KV_RAM / (RIEPILOGO_KV + ".ckpt")):
        f.unlink(missing_ok=True)
    _diario({"riepilogo": f"dormita: {len(blocco)} righe nel blocco della chat nuova"})



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


def _ore_vecchie(conv):
    """le ore che l'agente vedeva davanti ai messaggi dell'utente fino al 10/11, per impronta del testo senza ora"""
    try:
        return json.loads(ORE.read_text(encoding="utf-8")).get(conv, {}).get("ore", {})
    except (OSError, ValueError):
        return {}


def _chiavi(msgs):
    """K6 (10/11): la chiave della conversazione senza l'ora; fino al 10/11 il primo messaggio dell'utente portava
    sempre l'ora (revisione del blocco B, punto 2), quindi anche la chiave di allora, ricostruita (None se non c'e')"""
    conv = _conversazione(msgs)
    primo = next((m.get("content") for m in msgs
                  if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
    ora = _ore_vecchie(conv).get(_impronta(primo))
    return conv, (_impronta(f"{ora} {primo}") if ora else None)


def _voci(msgs):
    tutte = _consegne_carica()
    conv, vecchia = _chiavi(msgs)
    return (tutte.get(conv) or tutte.get(vecchia) or {}).get("voci", [])


def _consegne_salva(tutte, tieni=None):
    """le CONSEGNE_MAX conversazioni piu' recenti; quella della chat in corso (tieni) non si scarta mai (revisione
    del blocco B, punto 7: i pensieri del pensatoio la buttavano fuori)"""
    vive = dict(sorted(tutte.items(), key=lambda kv: kv[1]["ts"])[-CONSEGNE_MAX:])
    if tieni in tutte:
        vive[tieni] = tutte[tieni]
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
    resta fuori. K6 (10/11): TUTTI restano, ognuno al suo posto in modo univoco: impronta del testo + indice
    del messaggio (con messaggi uguali vince il piu' vicino all'indice); le voci di prima del 10/11 hanno l'impronta
    del testo CON l'ora davanti, che si ricostruisce"""
    ore = _ore_vecchie(_conversazione(msgs))

    def combacia(c, v):
        if not isinstance(c, str):
            return False
        imp = _impronta(c)
        return v["dopo"] == imp or (imp in ore and v["dopo"] == _impronta(f"{ore[imp]} {c}"))

    pos = []
    for v in voci:
        cand = [k for k in range(len(msgs)) if combacia(msgs[k].get("content"), v)]
        if cand:
            ind = v.get("indice")
            pos.append((cand[-1] if ind is None else min(cand, key=lambda k: (abs(k - ind), -k)), v))
    for i, v in sorted(pos, key=lambda x: -x[0]):
        msgs[i + 1:i + 1] = _turni_tool(v)


LETTO_FATTORE = 0.5     # issue #3 punto H (18/10): un ricordo "letto" porta l'emozione dell'agente
                        # di quando l'ha letto (la firma del tagging), a meta' dose


def _emo_del_ricordo(info):
    """(nid, emo_tag, fattore della dose) del ricordo consegnato. Lux 1.20.0: dalla voce di "ricordi" della risposta
    di /consegna (prima da memoria.db); ricordo ignoto o correzione = (None, None, 1.0) come prima"""
    return info.get("nid"), info.get("dominante"), LETTO_FATTORE if info.get("classe") == "letto" else 1.0


# PIANO-STEERING-RIFLESSO 7b (11/11): dose del vettore del ricordo = D_e del punto 7 di PIANO-LUX-FASI (24/10)
SOGLIA_E = 0.5   # provvisori di CC per il rodaggio (misura su 633 ricordi, piano punto 5): sotto, ~15%, niente vettore
K_DOSE = 1.13    # la mediana di S_e: li' la dose e' al 63% della fascia
IT = {en: it for it, en in steering.EN.items()}


def _forza(codice, emo):
    """S_e del ricordo sulla sua dominante (Lux, /forza), None se il Lux non risponde o non la sa"""
    try:
        req = urllib.request.Request(LUX_FORZA, json.dumps({"codice": codice, "emo": emo}).encode(),
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=10)).get("forza")
    except Exception as e:
        _diario({"lux": f"forza non letta: {e}"})
        return None


def _dose(emo, forza, fattore=1.0):
    """(emozione italiana, dose per steering.strati, posizione f nella fascia) o None. D_e = Dmin + (Dmax - Dmin) x (1 - exp(-S_e/k)); fattore
    (ricordo letto) accorcia il tratto sopra Dmin. Diadi della ruota e terrore/stupore/vigilanza: emo_dose vuole la
    posizione 0-1 nella fascia, non la dose"""
    it = IT.get(emo)
    if forza is None or forza < SOGLIA_E or it is None:
        return None
    f = (1 - math.exp(-forza / K_DOSE)) * fattore
    pure, fasce = steering.pure(), steering.fasce()
    if it in pure:
        lo, hi = pure[it]
    elif it in steering.RUOTA or it in steering.DIADI:
        return it, f, f
    elif it in fasce:
        lo, hi = fasce[it]
    else:
        return None
    return it, lo + (hi - lo) * f, f


def _sam_accesa(dove=UPSTREAM):
    """25/10: col 35B spento nessun ricordo, ne' consegnato ne' rinforzato nel Lux. I cron di Hermes
    partono lo stesso e senza questo freno il riflesso registrava consegne che la barra mostrava in chat"""
    up = http.client.HTTPConnection(*dove, timeout=3)
    try:
        up.request("GET", "/health")
        r = up.getresponse()
        r.read()
        return r.status == 200
    except OSError:
        return False
    finally:
        up.close()


def _lux_consegna(testo, esclusi, emozione=None):
    """{codici, risposta} oppure {} = nessun ricordo (1.19.0: con l'emozione anche "traccia"). Mai bloccare la parola dell'agente."""
    corpo = {"testo": testo, "esclusi": esclusi, "quanti": 1}   # 09/11: uno per volta
    if emozione:
        corpo["emozione"] = emozione
    try:
        req = urllib.request.Request(LUX, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        _diario({"lux": f"consegna fallita: {e}"})
        return {}


# +lux e qlux (l'utente 09/11, PIANO-MEMORINVOLONTARIA-LUX.md): il plugin memorinvolontaria di Hermes chiama
# POST /memorinvolontaria con gli argomenti dell'agente; +lux = ricordo forzato nella coda di firma-subito (entra nel Lux in
# pochi secondi), qlux = ricerca volontaria, il ricordo piu' vicino, uno per volta. Risposte approvate dall'utente 09/11.
R_AGGIUNTO = "Aggiunto alla tua memoria."
R_VUOTO = "Scrivi il ricordo da tenere."
R_NESSUNO = "Nessun ricordo trovato."
R_GIU = "La memoria non risponde, riprova più tardi."
R_SENZA = "Usa +lux per aggiungere un ricordo o qlux per cercarne uno."
_esclusi_chat = [set()]   # codici nell'ultima richiesta della chat, piu' quelli dati da qlux dopo
_esclusi_lock = threading.Lock()
MESI = {m: i for i, m in enumerate(("gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre "
                                     "novembre dicembre").split(), 1)}
_PRIMA = r"(?:\b(?:il|l'|a|ad|del|dell'|nel|nell'|di|da|dal|dall')\s*)?"
_DATE = [re.compile(_PRIMA + r, re.I) for r in (
    r"\b(?P<g>\d{1,2})/(?P<m>\d{1,2})(?:/(?P<a>\d{4}|\d{2}))?\b",
    r"\b(?P<g>\d{1,2}°?|primo)\s+(?P<mese>" + "|".join(MESI) + r")(?:\s+(?P<a>\d{4}))?\b",
    r"\b(?P<mese>" + "|".join(MESI) + r")(?:\s+(?P<a>\d{4}))?\b",
    r"\b(?P<rel>l'altro ieri|ieri|oggi)\b")]


def _data(testo, adesso=None):
    """(testo senza la data, da, a): la prima data riconosciuta nella ricerca diventa una finestra [da, a) sul momento
    del ricordo (un giorno o un mese); anno mancante = il piu' recente passato. Nessuna data: (testo, None, None)"""
    adesso = time.time() if adesso is None else adesso
    oggi = time.localtime(adesso)
    trovate = [x for rx in _DATE for x in [rx.search(testo)] if x]
    x = min(trovate, key=lambda x: (x.start(), -x.end()), default=None)   # la prima nel testo, la piu' lunga
    if x:
        g = x.groupdict()
        if g.get("rel"):
            indietro = {"oggi": 0, "ieri": 1, "l'altro ieri": 2}[g["rel"].lower()]
            t = time.localtime(time.mktime((oggi.tm_year, oggi.tm_mon, oggi.tm_mday - indietro, 12, 0, 0, 0, 0, -1)))
            a, m, gg = t.tm_year, t.tm_mon, t.tm_mday
        else:
            m = int(g["m"]) if g.get("m") else MESI[g["mese"].lower()]
            gg = (1 if g["g"].lower() == "primo" else int(g["g"].rstrip("°"))) if g.get("g") else None
            a = (int(g["a"]) + (2000 if len(g["a"]) == 2 else 0)) if g.get("a") else oggi.tm_year
            if not g.get("a") and (m, gg or 1) > (oggi.tm_mon, oggi.tm_mday):
                a -= 1
        try:
            if not 1 <= m <= 12:
                raise ValueError
            da = time.mktime((a, m, gg or 1, 0, 0, 0, 0, 0, -1))
            if gg and time.localtime(da)[:3] != (a, m, gg):   # 30/2 e simili
                raise ValueError
        except (ValueError, OverflowError):   # 30/2, 29 febbraio non bisestile: nessuna data, resta testo
            return testo, None, None
        fine = (a, m, gg + 1) if gg else ((a + 1, 1, 1) if m == 12 else (a, m + 1, 1))
        resto = " ".join((testo[:x.start()] + " " + testo[x.end():]).split())
        return resto, da, time.mktime((*fine, 0, 0, 0, 0, 0, -1))
    return testo, None, None


_CODICE_TOOL = re.compile(r"^\d+[a-z]?°\n([0-9a-z]{16})$", re.M)


def _ids_ricordo(msgs):
    """id delle chiamate a memorinvolontaria (le finte del riflesso e quelle vere dell'agente, che hanno l'id del server)"""
    return {tc.get("id") for m in msgs if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])
            if (tc.get("function") or {}).get("name") == TOOL_RICORDO}


def _e_ricordo(m, ids):
    """un messaggio tool che e' la risposta di memorinvolontaria"""
    i = str(m.get("tool_call_id", ""))
    return m.get("role") == "tool" and (i.startswith(TOOL_RICORDO) or i in ids or m.get("name") == TOOL_RICORDO)


def _codici_nei_messaggi(msgs):
    ids = _ids_ricordo(msgs)
    return {c for m in msgs if _e_ricordo(m, ids) and isinstance(m.get("content"), str)
            for c in _CODICE_TOOL.findall(m["content"])}


_lettura_lock = threading.Lock()   # 1.19.0: le letture in ordine (la risposta dell'agente prima del messaggio dopo)


def _lettura(testo, flusso, chi):
    """1.19.0: la lente legge il testo e la lettura imprime l'umore; -> (z, umore prima, riparazione, voce del diario)"""
    z, tok = VE.leggi(testo)
    prima, dopo, neg, rip = VE.imprimi(z)
    return z, prima, rip, {"flusso": flusso, "chi": chi, "token": tok, "lettura": VE.tondo(z),
                           "umore_prima": VE.tondo(prima), "umore_dopo": VE.tondo(dopo),
                           "negativita": round(neg, 4), "riparazione": rip}


def _da_leggere(msgs, i, flusso):
    """1.19.0 (revisione 11/11): (testo, chi) che la lente legge per la fonte msgs[i], o None. Chat: solo il messaggio
    dell'utente col suo "[handle] ", senza handle e senza ora, come lo legge la firma (Hermes, review e memory flush, senza
    handle: niente); pensatoio: la riga dell'appunto del risveglio; strumenti: la prosa letta. Mai una fonte rimasta
    indietro (ultimo messaggio dell'utente senza testo, es. un'immagine)"""
    if any(m.get("role") == "user" for m in msgs[i + 1:]):
        return None
    c = msgs[i]["content"]
    if msgs[i].get("role") == "tool":
        return _leggibile(c), "strumento"
    if flusso == "pensatoio":
        return (query_riflesso(c), "pensatoio") if _MARCA_RISVEGLIO.search(c) else None
    m = _HANDLE.match(_ORA.sub("", c).strip())
    return (m.group(2).strip(), m.group(1)) if m and m.group(2).strip() else None


def _via_emotiva(msgs, i, flusso):
    """1.19.0 (l'utente 11/11, due tempi): la fonte passa dalla lente e imprime l'umore; l'indizio = meta' emozione della
    fonte e meta' umore di PRIMA della sua lettura. -> (emozione per il Lux, voce del diario) o (None, None): mai bloccare
    la parola dell'agente"""
    try:
        x = _da_leggere(msgs, i, flusso)
        conv, _ = _chiavi(msgs)
        chiave = f"{flusso}|{conv}|{i}|{_impronta(x[0])}" if x else None
        if not x or VE.gia_letta(chiave):
            return None, None
        if not _lettura_lock.acquire(timeout=VE.TIMEOUT):   # la risposta dell'agente prima, ma mai oltre il tempo
            raise TimeoutError("lente occupata")
        try:
            z, prima, rip, voce = _lettura(x[0], flusso, x[1])
            VE.segna_letta(chiave)
        finally:
            _lettura_lock.release()
        q, k, D = VE.indizio(z, prima, rip["accesa"])
        voce.update(D=round(D, 4), k=round(k, 4), q=VE.tondo(q, 4))
        return {"assi": VE.traduzione()["assi"], "q": q.tolist(), "k": k}, voce
    except Exception as e:
        try:
            VE.diario({"flusso": flusso, "errore": repr(e)[:300]})
        except Exception:
            pass
        return None, None


def _leggi_risposta(flusso, ultimo, esito):
    """1.19.0: la risposta finale dell'agente (chat e pensatoio) passa dalla lente a fine risposta, fuori dal percorso della
    parola; il messaggio dopo aspetta (_lettura_lock) cosi' l'umore ha gia' la sua impronta"""
    if flusso not in KV_FLUSSO or not esito or esito.get("finish") != "stop" or esito.get("tool_calls"):
        return
    if flusso == "chat":   # come la firma: la risposta a Hermes (review, memory flush, ultimo user senza handle) no
        m = _HANDLE.match(ultimo.strip()) if isinstance(ultimo, str) else None
        if not m or not m.group(2).strip():
            return
    testo = _senza_imitati(esito.get("testo") or "").strip()
    if not testo or testo.startswith("[OUT-OF-BAND]"):
        return

    def leggi():   # il lucchetto lo rilascia il filo (threading.Lock lo permette)
        try:
            VE.diario(_lettura(testo, flusso, "agente")[3])
        except Exception as e:
            try:
                VE.diario({"flusso": flusso, "chi": "agente", "errore": repr(e)[:300]})
            except Exception:
                pass
        finally:
            _lettura_lock.release()
    if not _lettura_lock.acquire(timeout=VE.TIMEOUT):   # preso subito: un messaggio che arriva adesso aspetta
        VE.diario({"flusso": flusso, "chi": "agente", "errore": "lente occupata: risposta non letta"})
        return
    threading.Thread(target=leggi, daemon=True).start()


def _ammesso(ip):
    """/memorinvolontaria solo dal PC e dalla rete docker (il riflesso ascolta su 0.0.0.0: niente ricordi alla LAN)"""
    p = ip.split(".")
    return ip == "127.0.0.1" or (len(p) == 4 and p[0] == "172" and p[1].isdigit() and 16 <= int(p[1]) <= 31)


def _lux_cerca(testo, esclusi):
    """qlux: {codici, risposta} o {} = niente; un errore del Lux si alza (R_GIU, mai confuso con "nessun ricordo")"""
    resto, da, a = _data(testo)
    corpo = {"testo": resto, "esclusi": sorted(esclusi), "quanti": 1, "soglia": 0}
    if da is not None:
        corpo.update(da=da, a=a)
    req = urllib.request.Request(LUX, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def _accoda_forzato(testo):
    fd = os.open(CODA_FIRMA, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:   # una sola write: righe intere anche con la chat che accoda
        os.write(fd, (json.dumps({"ts": time.time(), "autore": "@agente:localhost", "testo": testo,
                                  "forzato": True}, ensure_ascii=False) + "\n").encode())
    finally:
        os.close(fd)


def memorinvolontaria(args):
    """la risposta che l'agente riceve dal plugin; a consenso spento niente entra e niente si scrive (patto di sempre)"""
    aggiungi, cerca = args.get("+lux"), args.get("qlux")
    if aggiungi is None and cerca is None:
        return R_SENZA
    if not consenso_attivo():
        return R_GIU
    parti = []
    if aggiungi is not None:
        t = str(aggiungi).strip()
        if t:
            _accoda_forzato(t)
            _diario({"+lux": t[:80]})
        parti.append(R_AGGIUNTO if t else R_VUOTO)
    if cerca is not None:
        with _esclusi_lock:
            esclusi = set(_esclusi_chat[0])
        try:
            r = _lux_cerca(str(cerca), esclusi)
        except Exception as e:
            _diario({"qlux": f"fallito: {e}"})
            parti.append(R_GIU)
        else:
            if r.get("codici"):
                with _esclusi_lock:
                    _esclusi_chat[0] |= set(r["codici"])
                _diario({"qlux": r["codici"]})
            parti.append(r.get("risposta") or R_NESSUNO)
    return "\n\n".join(parti)


def _ora_corta(t):
    return f"[{t.tm_mday}/{t.tm_mon}/{t.tm_year}|{t.tm_hour}:{t.tm_min:02d}]"


def _in_coda(msgs, testo):
    """19/10: il template di Occamy vuole un solo system, in testa: il testo del momento
    va in coda all'ultimo messaggio invece che in un system in mezzo (in place)"""
    c = msgs[-1].get("content")
    if isinstance(c, list):
        c.append({"type": "text", "text": "\n\n" + testo})
    else:
        msgs[-1]["content"] = (c or "") + "\n\n" + testo


def _segna_volo():
    """20/10: quante richieste della chat sono in volo, per la barra del prefill
    (~/.local/bin/barra-prefill): i prefill partiti con la chat in volo sono della chat"""
    with _volo_lock:    # 10/11: lo legge anche dormi-esegui.sh, mai un file a meta'
        try:
            Path(VOLO + ".tmp").write_text(str(_chat_in_volo[0]))
            os.replace(VOLO + ".tmp", VOLO)
        except OSError:
            pass


def _segna_fase(f):
    """24/10: cosa sta facendo l'agente (legge, pensa, scrive, tool; vuoto = ferma), per l'emoji nel suo nome
    in chat (~/.local/bin/barra-prefill). Si scrive solo quando cambia"""
    with _fase_lock:
        if f == _fase[0]:
            return
        try:
            Path(FASE + ".tmp").write_text(f)
            os.replace(FASE + ".tmp", FASE)
            _fase[0] = f
        except OSError:
            pass


def _code(body, testi):
    """20/10: i testi in coda all'ultimo messaggio, se non e' la risposta della
    memoria involontaria (il ricordo resta nudo: si riprova alla richiesta dopo)"""
    d = json.loads(body)
    msgs = d.get("messages", [])
    if not msgs or not testi or _e_ricordo(msgs[-1], _ids_ricordo(msgs)):
        return body, False
    for t in testi:
        _in_coda(msgs, t)
    return json.dumps(d).encode(), True


def _ora_blocco(t):
    return f"[{t.tm_hour:02d}:{t.tm_min:02d}|{t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year}]"   # l'utente 10/11, zeri davanti


_arrivi_altri = {}   # pensatoio e cron: l'arrivo in memoria (ore-messaggi.json e' della chat: dato della fase 2)


def _ora_arrivo(msgs, registra=True):
    """M2 (10/11): l'ora di ARRIVO dell'ultimo messaggio user. Si fissa quando apre il turno (e' l'ultimo
    messaggio, anche se uguale a uno di prima) e si riusa nei giri di tool (revisione dei danni, punto 3)"""
    i = next((k for k in range(len(msgs) - 1, -1, -1) if msgs[k].get("role") == "user"), None)
    adesso = time.localtime(time.time())
    if i is None:
        return _ora_blocco(adesso)
    c = msgs[i].get("content")
    conv, imp = _conversazione(msgs), _impronta(str(c))
    testo = c if isinstance(c, str) else next((p.get("text") or "" for p in c if isinstance(p, dict)), "") \
        if isinstance(c, list) else ""
    if not _HANDLE.match(testo):    # review e memory flush di Hermes: fuori dal dato della fase 2 (3.5.3, punto 7)
        registra = False
    if not registra:
        if i == len(msgs) - 1 or (conv, imp) not in _arrivi_altri:
            if len(_arrivi_altri) > 200:
                _arrivi_altri.clear()
            _arrivi_altri[conv, imp] = adesso
        return _ora_blocco(_arrivi_altri.get((conv, imp), adesso))
    with _ore_lock:
        try:
            tutte = json.loads(ORE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tutte = {}
        c = tutte.setdefault(conv, {"visti": [], "ore": {}})
        arrivi = c.setdefault("arrivi", {})
        if i == len(msgs) - 1 or imp not in arrivi:
            arrivi[imp] = _ora_corta(adesso)
            c["ts"] = time.time()
            vive = dict(sorted(tutte.items(), key=lambda kv: kv[1].get("ts", 0))[-CONSEGNE_MAX:])
            tmp = ORE.with_suffix(".tmp")
            tmp.write_text(json.dumps(vive, ensure_ascii=False), encoding="utf-8")
            tmp.replace(ORE)
        corta = arrivi[imp]
    return _ora_blocco(time.strptime(corta, "[%d/%m/%Y|%H:%M]"))


def _motore_attivo():
    """il criterio di notturna -status: motore-autonomia.service attivo = pensatoio attivo"""
    return subprocess.run(["systemctl", "--user", "is-active", "motore-autonomia.service"], capture_output=True,
                          text=True, timeout=2).stdout.strip() == "active"


def _righe_metadati(ora, flusso=None):
    """K5 (10/11): le righe del blocco metadati, quello che cambia piu' spesso in fondo. Nella chat niente
    PENSATOIO_DOVE (l'utente 10/11 sera: l'agente la prendeva come un invito a scrivere ogni riflessione nel pensatoio)"""
    try:
        stato = "[pensatoio]" if _motore_attivo() else "[/pensatoio]"   # M1
    except Exception as e:
        stato = "[/pensatoio]"
        _diario({"metadati": f"stato del pensatoio illeggibile: {e}"})
    return ([] if flusso == "chat" else [PENSATOIO_DOVE]) + [stato, ora]


# l'utente 10/11 sera: l'agente copiava il blocco in fondo alle sue risposte; le copie si tolgono dalla storia che vede
_IMITATI = re.compile(r"(?:\s*\[(?:/?pensatoio|\d\d:\d\d\|\d\d/\d\d/\d{4})\])+\s*\Z")


def _senza_imitati(testo):
    return _IMITATI.sub("", testo) if isinstance(testo, str) else testo


def _togli_imitati(msgs):
    """in place: via le copie del blocco metadati dalla fine delle risposte dell'agente"""
    for m in msgs:
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            m["content"] = _senza_imitati(m["content"])


def _con_metadati(body, righe, fuori, flusso=None):
    """il blocco metadati su un corpo intero; fuori["senza"] = il corpo senza (per il prefill anticipato)"""
    if not righe:
        return body
    fuori["senza"] = body
    d = json.loads(body)
    _metti_metadati(d.get("messages", []), righe, flusso)
    return json.dumps(d).encode()


def _ha_testo(m):
    c = m.get("content")
    if isinstance(c, list):
        return any((p.get("text") or "").strip() for p in c if isinstance(p, dict))
    return bool((c or "").strip())


def _metti_metadati(msgs, righe, flusso=None):
    """3.5 (10/11): nella chat il blocco metadati all'INIZIO dell'ultimo messaggio dell'utente (l'utente 10/11 sera:
    in coda alla risposta dell'agente lei lo leggeva come scritto da se' e lo imitava); al turno dopo sparisce da li'.
    Pensatoio e cron: in coda all'ultima risposta dell'agente con testo prima dell'ultimo messaggio user (stabile nei giri
    di tool), se non c'e' in coda a quel messaggio user. Mai su un messaggio tool: la memoria involontaria resta nuda"""
    u = next((k for k in range(len(msgs) - 1, -1, -1) if msgs[k].get("role") == "user"), None)
    if u is None:
        return
    if flusso == "chat":
        testa = "\n".join(righe) + "\n\n"
        c = msgs[u].get("content")
        if isinstance(c, list):
            c.insert(0, {"type": "text", "text": testa})
        else:
            msgs[u]["content"] = testa + (c or "")
        return
    dove = next((k for k in range(u - 1, -1, -1) if msgs[k].get("role") == "assistant" and _ha_testo(msgs[k])), u)
    testo = "\n\n" + "\n".join(righe)
    c = msgs[dove].get("content")
    if isinstance(c, list):
        c.append({"type": "text", "text": testo})
    else:
        msgs[dove]["content"] = (c or "") + testo


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


def _accoda_firma(flusso, ultimo, arrivo, esito):
    """B6: solo le risposte finali. Chat: il messaggio dell'utente com'era prima delle aggiunte del riflesso (ora, coda)
    e la risposta dell'agente; un ultimo user senza "[handle] " e' Hermes (background review, memory flush): niente.
    Pensatoio: la risposta dell'agente. Una sola write in append: righe intere anche con la notturna che accoda"""
    if not esito or esito.get("finish") != "stop" or esito.get("tool_calls"):
        return
    risposta = _senza_imitati(esito.get("testo") or "").strip()
    righe = []
    if flusso == "chat":
        m = _HANDLE.match(ultimo.strip()) if isinstance(ultimo, str) else None
        if not m or not m.group(2).strip():
            return
        righe.append({"ts": arrivo, "autore": f"@{m.group(1)}:localhost", "testo": m.group(2).strip(), "flusso": flusso})
    elif flusso != "pensatoio":
        return
    if risposta and not risposta.startswith("[OUT-OF-BAND]"):   # orchestrazione, non esperienza (estrai-matrix)
        righe.append({"ts": time.time(), "autore": "@agente:localhost", "testo": risposta, "flusso": flusso})
    if righe:
        fd = os.open(CODA_FIRMA, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in righe).encode())
        finally:
            os.close(fd)


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


def _scaduto(chi=None):
    """PATTO clausola 2: nessun vettore vive oltre DURATA_MAX_S, anche se la
    risposta è ancora in corso o il finally non arriva mai.
    23/07 sera: il clear a slot VIVO uccideva la generazione in corso (POST
    /control-vector durante il decode -> stream caduto, 'Streaming failed'
    su Hermes, consegne al pensatoio perse). Se lo slot sta generando, il
    kill si RIMANDA e spara appena lo slot molla: il vettore muore comunque
    col turno (spirito della clausola), mai ammazzando la parola dell'agente.
    chi (11/11): il watchdog del vettore di un ricordo; se un altro ricordo ha acceso il suo dopo, questo tace."""
    if not _vettore_vivo[0] or (chi is not None and _vettore_di[0] is not chi):
        return
    try:
        up = http.client.HTTPConnection(*UPSTREAM, timeout=3)
        up.request("GET", "/slots")
        occupato = json.loads(up.getresponse().read())[0].get("is_processing")
        up.close()
    except Exception:
        occupato = True    # server irraggiungibile/carico: non sparare al buio
    if occupato:
        t = threading.Timer(20, _scaduto, args=(chi,))
        t.daemon = True
        t.start()
        _diario({"watchdog": "slot vivo: kill vettore rimandato 20s"})
        return
    calma()
    _diario({"kill": f"vettore oltre {DURATA_MAX_S}s: spento dal watchdog"})



def _accendi_ricordo(body, vettore):
    """PIANO-STEERING-RIFLESSO 7d (l'utente 09/11 + 11/11): il ricordo si legge SENZA vettore (prefill del corpo finale,
    reso dal server con /apply-template come nel percorso chat, e /completion che si ferma al primo token), poi il
    vettore della sua emozione si accende per il ragionamento e luxifer lo spegne quando il modello genera </think>
    (cvec_solo_ragionamento, strada B). Solo dentro _vettore_lock. Torna (corpo da inoltrare, watchdog)"""
    d = json.loads(body)
    st, r = ponte.post("/apply-template", d, timeout=30)   # tutto il corpo: lo stesso parse della chat, stesso prompt
    if st != 200 or not r.get("prompt"):
        raise RuntimeError(f"/apply-template: HTTP {st}")
    if ponte.post("/completion", {"prompt": r["prompt"], "n_predict": 1, "cache_prompt": True}, timeout=600)[0] != 200:
        raise RuntimeError("prefill del ricordo fallito")
    _cvec({"layers": vettore[2], "relative": True})
    _vettore_vivo[0] = True
    watchdog = threading.Timer(DURATA_MAX_S, lambda: _scaduto(watchdog))   # PATTO clausola 2
    watchdog.daemon = True
    watchdog.start()
    _vettore_di[0] = watchdog
    return json.dumps({**d, "reasoning_control": True, "cvec_solo_ragionamento": True}).encode(), watchdog


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
    ids = _ids_ricordo(msgs)
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        c = m.get("content")
        if not isinstance(c, str):
            continue
        if m.get("role") == "user":
            return i, c
        if m.get("role") == "tool" and not _e_ricordo(m, ids):
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
VOLO = "/tmp/chat-in-volo"
FASE = "/tmp/fase"
_volo_lock = threading.Lock()
_fase = [None]
_fase_lock = threading.Lock()


def _tee_sse(buf, chunk, fh, esito):
    """23/07: specchio LIVE dello streaming. Estrae il testo (think e
    parola) dai chunk SSE che attraversano il proxy e lo appende su file:
    `tail -f /tmp/stream-live.log` = il 35B token per token, in diretta.
    Mai bloccare lo stream per il tee: ogni crepa è silenziosa.
    20/10: raccoglie anche la parola, il finish_reason e le tool call (esito) per il riepilogo."""
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
                    esito["testo"] += delta.get("content") or ""
                    esito["ragionamento"] += delta.get("reasoning_content") or ""
                    esito["tool_calls"] = esito["tool_calls"] or bool(delta.get("tool_calls"))
                    esito["finish"] = d["choices"][0].get("finish_reason") or esito["finish"]
                    if esito["chat"]:
                        if delta.get("tool_calls"):
                            _segna_fase("tool")
                        elif delta.get("reasoning_content"):
                            _segna_fase("pensa")
                        elif delta.get("content"):
                            _segna_fase("scrive")
                else:
                    t = d.get("content", "")
                if t and fh:
                    fh.write(t)
                    fh.flush()
            except Exception:
                pass
    return buf


class Proxy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _inoltra(self, body, flusso=None, vettore=None):
        """revisione 11/11: col vettore del ricordo acceso _vettore_lock resta preso fino a fine stream, cosi' nessun
        altro inoltro (cron, review di Hermes) lo spegne a meta' ragionamento o prende lo slot col vettore dell'agente"""
        watchdog = None
        if flusso is not None:
            _vettore_lock.acquire()   # issue #3 punto A: mai dentro un prefill colorato
            try:
                _applica_flusso(flusso)   # il vettore del flusso che genera, nessun altro
                # pensatoio: prefill sotto _cw_lock, se no la chat puo' prendere lo slot a meta' e il prefill finisce
                # sulla sua cache (revisione del codice 11/11)
                with _cw_lock if vettore and flusso == "pensatoio" else contextlib.nullcontext():
                    if vettore and not (flusso == "pensatoio" and _cw[0] != flusso):
                        try:
                            body, watchdog = _accendi_ricordo(body, vettore)
                        except Exception as e:
                            calma()
                            _diario({"vettore": f"non acceso: {e}"})   # mai bloccare la parola dell'agente
            finally:
                if watchdog is None:
                    _vettore_lock.release()
        try:
            self._manda(body, flusso)
        finally:
            if watchdog:   # luxifer l'ha gia' spento a </think>: pulizia sicura, anche se lo stream e' caduto
                watchdog.cancel()
                calma()
                _vettore_lock.release()

    def _manda(self, body, flusso):
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
        self._inoltrato, self._esito = body, {"testo": "", "ragionamento": "", "finish": None, "tool_calls": False,
                                               "chat": flusso == "chat"}
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
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    self._esito["interrotta"] = True   # Hermes ha chiuso: il turno non e' finito, niente switch
                    raise
                try:
                    buf = _tee_sse(buf, chunk, tee, self._esito)
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
            self._salva = _salva_ultimo[0] = threading.Thread(target=_salva_kv, daemon=True)
            self._salva.start()

    def _dopo_chat(self):
        """20/10: dopo la risposta finale all'utente il riepilogo, quando lo specchio della chat e' gia' salvato
        (cosi' il conteggio dei token resta quello della chat); 10/11 poi lo switch (blocco B)"""
        if self._esito and self._inoltrato:
            threading.Thread(target=_fine_chat, args=(self._inoltrato, self._esito, self._salva, self._senza,
                                                      self._hermes), daemon=True).start()

    def do_GET(self):
        self._inoltra(None)

    def _ricordo(self, body):
        if not _ammesso(self.client_address[0]):
            self.send_error(403)
            return
        try:
            testo = memorinvolontaria(json.loads(body or b"{}"))
        except Exception as e:
            _diario({"memorinvolontaria": f"rotta: {e}"})
            testo = R_GIU
        b = json.dumps({"testo": testo}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _memoria(self, body, flusso=None, righe=None, fuori=None):
        """Memoria involontaria: a ogni lettura nuova il Lux sceglie un ricordo
        (quanti=1, l'utente 09/11) nella risposta del tool; i ricordi già consegnati nella conversazione tornano al loro posto.
        A consenso spento il richiamo gira lo stesso e rinforza gli archi (WIRING
        NON DISATTIVABILE, decisione di progetto), ma niente entra nel prompt.
        10/11 (blocco A): con righe, il blocco metadati entra DOPO la query e l'impronta "dopo" ma PRIMA della
        vettore del ricordo; fuori["senza"] = corpo senza. PIANO-STEERING-RIFLESSO 7c (11/11): fuori["vettore"] = (emozione,
        dose, strati) del ricordo nuovo, lo accende _inoltra dopo il prefill senza vettore."""
        d = json.loads(body)
        msgs = d.get("messages", [])
        if not msgs or flusso not in KV_FLUSSO or not _sam_accesa():   # 11/11: niente ricordi ai cron
            return _con_metadati(body, righe, fuori, flusso)
        attivo = consenso_attivo()
        stop = _stop_chiesto(msgs)   # prima di _rimetti: stessa finestra del controllo in do_POST
        conv, vecchia = _chiavi(msgs)
        with _consegne_lock:
            voci = _voci(msgs)
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
        visti = {c for v in voci for c in _codici(v)} | _codici_nei_messaggi(msgs)   # qlux compresi (09/11)
        if flusso == "chat":
            with _esclusi_lock:
                _esclusi_chat[0] = set(visti)
        if fonte:
            emozione, voce = _via_emotiva(msgs, i, flusso)
            r = _lux_consegna(query_riflesso(fonte), sorted(visti), emozione)
            if voce:
                try:
                    tr = r.get("traccia") or {}
                    voce.update(candidati=[[n, round(p, 5), round(a, 4)] for n, p, a in tr.get("candidati", [])],
                                scelto=tr.get("scelti", []), senza=tr.get("senza", []),
                                oltre_soglia=tr.get("oltre_soglia", False))
                    VE.diario(voce)
                except Exception as e:
                    _diario({"via emotiva": f"diario non scritto: {e}"})
            if r.get("codici") and attivo:
                nuova = {"dopo": _impronta(msgs[i]["content"]), "indice": i,
                         "codici": r["codici"], "risposta": r["risposta"]}
                voci = voci + [nuova]
                if flusso == "chat":
                    with _esclusi_lock:
                        _esclusi_chat[0] |= set(r["codici"])
                with _consegne_lock:
                    tutte = _consegne_carica()
                    tutte.pop(vecchia, None)     # la voce di prima del 10/11 passa alla chiave senza ora
                    tutte[conv] = {"ts": time.time(), "voci": voci}
                    _consegne_salva(tutte, tieni=conv if flusso == "chat" else None)
        if not attivo:
            return _con_metadati(body, righe, fuori, flusso)
        tools = d.setdefault("tools", [])
        if not any(t.get("function", {}).get("name") == TOOL_RICORDO for t in tools):
            tools.append(TOOL)
        _rimetti(msgs, voci)
        if righe:
            fuori["senza"] = json.dumps(d).encode()
            _metti_metadati(msgs, righe, flusso)
        if nuova:
            ricordi = [(x["codice"], *_emo_del_ricordo(x)) for x in r.get("ricordi", [])]
            vettore = None
            # RIFLESSO_COLLAUDO=1 blocca i vettori: mai più test che iniettano
            # sulla produzione (incidente del 14/07)
            # clausola 3 (issue #3 punto E): con la parola di emergenza il ricordo arriva senza vettore
            # PIANO-STEERING-RIFLESSO 7c (11/11): il vettore lo accende _inoltra, nel ragionamento; con piu' codici
            # (catena di correzioni) quello a dose piu' alta (09/11: il massimo, niente media)
            if vettori_attivi() and not os.environ.get("RIFLESSO_COLLAUDO") and not stop:
                try:
                    dosi = [x for c, _, emo, fat in ricordi if emo for x in [_dose(emo, _forza(c, emo), fat)] if x]
                    if dosi:
                        emo, dose, _ = max(dosi, key=lambda x: x[2])   # dosi assolute e posizioni: si confronta f
                        vettore = (emo, dose, steering.strati(emo, dose))
                        fuori["vettore"] = vettore
                except Exception as e:
                    _diario({"vettore": f"non preparato: {e}"})
            # 30/09 persistenza: gli id servono alla notturna (solo diario)
            _diario({TOOL_RICORDO: nuova["codici"], "vettore": [vettore[0], round(vettore[1], 5)] if vettore else None,
                     "nid": [int(n) for _, n, _, _ in ricordi if n is not None], "flusso": flusso})   # 1.14.0: il momento
        return json.dumps(d).encode()

    def do_POST(self):
        self._inoltrato = self._esito = self._salva = self._senza = self._hermes = None   # keep-alive: piu' richieste
        self._altro = False
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/memorinvolontaria":   # 09/11: il plugin di Hermes, mai inoltrato al 35B
            self._ricordo(body)
            return
        arrivo, ultimo = time.time(), None   # B6: il messaggio dell'utente prima di ora e coda
        chat = self.path.split("?")[0].endswith("/chat/completions")   # issue #3 punto E
        # PATTO clausola 3: la parola scritta dall'agente spegne il vettore, prima
        # di qualunque altra cosa e senza chiedere perché.
        if chat:
            try:
                d0 = json.loads(body)
                ultimo = next((m.get("content") for m in reversed(d0.get("messages", [])) if m.get("role") == "user"), None)
                if _stop_chiesto(d0.get("messages", [])):
                    _azzera_vettori()   # issue #3 punto A: anche quelli in pausa con l'altra cache
                    calma()
                    _diario({"kill": f"{STOP} scritto dall'agente"})
            except Exception:
                pass
        # --- doppia CW (19/07): riconosci il flusso, scambia le cache.
        flusso = _flusso(body) if chat else None
        if flusso == "chat":
            with _altro_lock:
                _chat_in_volo[0] += 1     # fino a fine risposta: il pensatoio non prende lo slot
            _segna_volo()
            _segna_fase("legge")
        try:
            self._post_chat(body, chat, flusso)
        finally:
            if flusso == "chat":
                if _chat_in_volo[0] <= 1:   # un'altra richiesta della chat in volo ha la sua fase
                    _segna_fase("tool" if self._esito and self._esito["finish"] == "tool_calls" else "")
                with _altro_lock:
                    _chat_in_volo[0] -= 1
                _chat_calda[0] = time.time()
                _segna_volo()
                try:
                    self._dopo_chat()
                except Exception as e:
                    _diario({"riepilogo": f"non avviato: {e}"})
            if self._altro:
                with _altro_lock:
                    _altro_in_volo[0] -= 1
            try:
                _accoda_firma(flusso, ultimo, arrivo, self._esito)
            except Exception as e:
                _diario({"firma": f"coda non scritta: {e}"})   # mai toccare la parola dell'agente
            try:
                _leggi_risposta(flusso, ultimo, self._esito)
            except Exception as e:
                _diario({"via emotiva": f"risposta non letta: {e}"})

    def _post_chat(self, body, chat, flusso):
        ora = None
        if chat:
            try:
                d = json.loads(body)
                _togli_imitati(d.get("messages", []))
                body = json.dumps(d).encode()
                ora = _ora_arrivo(d.get("messages", []), flusso == "chat")   # l'arrivo vero
            except Exception as e:
                _diario({"metadati": f"ora non letta: {e}"})
            righe = _righe_metadati(ora or _ora_blocco(time.localtime(time.time())), flusso)   # fuori dai lucchetti
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
                    if flusso == "chat":
                        try:
                            _promuovi()
                        except Exception as e:
                            _diario({"riepilogo": f"promozione fallita: {e}"})
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
                    if flusso == "altro":
                        with _altro_lock:     # fino a fine richiesta (do_POST): il riepilogo aspetta
                            _altro_in_volo[0] += 1
                        self._altro = True
                    break
            if flusso == "pensatoio" and time.time() - inizio > 5:
                _diario({"cw": f"pensatoio trattenuto {time.time()-inizio:.0f}s (chat calda)"})
            if flusso == "chat":
                try:
                    d = json.loads(body)
                    self._hermes = _metti_fissa(d)    # R6: prima la parte fissa della cache, poi il blocco
                    _metti_blocco(d, _riepilogo_carica()["blocco"])
                    body = json.dumps(d).encode()
                except Exception as e:
                    _diario({"riepilogo": f"blocco non messo: {e}"})   # mai bloccare la parola dell'agente
        coda = []   # PENSATOIO_DOVE passa nel blocco metadati (M3, l'utente 10/11)
        avviso = None
        if chat:
            # oltre 100k l'avviso di spazio, in coda, solo al pensatoio (K17); la chat ha lo switch (K4)
            if flusso == "pensatoio" and _tok_cw[flusso] > SOGLIA_CW and not _avvisato_cw[flusso]:
                avviso = (
                    "[avviso di spazio: questo flusso di pensiero ha superato i "
                    "100mila token e la finestra si sta riempiendo: tutto rallenta. "
                    "È il momento di tirare le fila e chiudere il pensiero.]")
                coda.append(avviso)
        # MEMORIA INVOLONTARIA: DOPO lo scambio CW (il prefill colorato deve finire
        # nella cache giusta).
        if chat:
            fuori = {}
            try:
                body = self._memoria(body, flusso, righe, fuori)
            except Exception as e:
                _diario({"memoria": f"rotta: {e}"})  # mai bloccare la parola dell'agente
                fuori.clear()           # il corpo e' quello di prima: niente metadati dentro
            if "senza" not in fuori:     # memoria rotta: i metadati ci vanno lo stesso
                try:
                    body = _con_metadati(body, righe, fuori, flusso)
                except Exception as e:
                    _diario({"metadati": f"non messi: {e}"})
            self._senza = fuori.get("senza")
            # 20/10: i testi in coda per ULTIMI, dopo la memoria: cosi' non entrano
            # nella query del Lux ne' nell'impronta del messaggio a cui il ricordo
            # si aggancia, e non toccano la cache colorata
            try:
                body, messi = _code(body, coda)
                if messi and avviso:
                    _avvisato_cw[flusso] = True
                    _diario({"cw": f"avviso 100k -> {flusso} ({_tok_cw[flusso]} tok)"})
            except Exception:
                pass
        self._inoltra(body, flusso, fuori.get("vettore") if chat else None)


if __name__ == "__main__":
    _segna_fase("")   # una fase rimasta da un riflesso morto a meta' risposta non resta accesa
    _segna_volo()     # idem il conteggio delle richieste in volo (lo script dello switch lo aspetta a 0)
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
          f"vettori: {'SÌ' if vettori_attivi() else 'no'}, dose del punto 7 nel ragionamento, "
          f"watchdog {DURATA_MAX_S}s)")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORTA), Proxy).serve_forever()
