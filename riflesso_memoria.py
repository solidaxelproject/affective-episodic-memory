# riflesso_memoria.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import http.client
import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
import steering
import via_emotiva as VE
import riflesso_stato as S
import riflesso_comune as C
import riflesso_firma as FI
import riflesso_fonte as FO
import riflesso_vettore as VT
import riflesso_metadati as MD
import riflesso_via_emotiva as RVE


_ultima_lettura = [""]  # 25/07: il freno vero, l'impronta del testo già affiorato

# ---- MEMORIA INVOLONTARIA (l'utente 11/10, piano del refactoring Lux + richiamo):
# il Lux degli engrammi sceglie un ricordo per messaggio (quanti=1, l'utente 09/11; erano fino a 4
# dalla 1.10.0), sopra soglia, mai uno già consegnato nella conversazione; i ricordi
# entrano insieme in un turno del tool, che
# è dichiarato sempre (a consenso attivo) così il prefisso della cache non cambia.
LUX = "http://127.0.0.1:8132/consegna"
TOOL = {"type": "function", "function": {
    "name": FO.TOOL_RICORDO,
    "description": "Ricordi che affiorano dalla tua memoria, collegati alla conversazione. "
                   "Arrivano da soli, non serve chiamare questo strumento: usali solo se "
                   "servono alla risposta.",
    "parameters": {"type": "object", "properties": {}, "required": []}}}
# Hermes non conserva i turni aggiunti qui: il riflesso li ricorda e li rimette
# al loro posto a ogni richiesta (dopo il messaggio che li ha fatti affiorare),
# così il ricordo resta nel contesto e il prefisso della cache resta stabile.
CONSEGNE = Path("/data/workspace/memoria/consegne-memorinvolontaria.json")
_consegne_lock = threading.Lock()


def _consegne_carica():
    try:
        return json.loads(CONSEGNE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _voci(msgs):
    tutte = _consegne_carica()
    conv, vecchia = MD._chiavi(msgs)
    return (tutte.get(conv) or tutte.get(vecchia) or {}).get("voci", [])


def _consegne_salva(tutte, tieni=None):
    """le CONSEGNE_MAX conversazioni piu' recenti; quella della chat in corso (tieni) non si scarta mai (revisione
    del blocco B, punto 7: i pensieri del pensatoio la buttavano fuori)"""
    vive = dict(sorted(tutte.items(), key=lambda kv: kv[1]["ts"])[-S.CONSEGNE_MAX:])
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
    cid = f"{FO.TOOL_RICORDO}_{_codici(voce)[0]}"
    return [{"role": "assistant", "content": "",
             "tool_calls": [{"id": cid, "type": "function",
                             "function": {"name": FO.TOOL_RICORDO, "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": cid, "content": voce["risposta"]}]


def _rimetti(msgs, voci):
    """ogni ricordo consegnato torna subito dopo il messaggio che l'ha fatto
    affiorare; se quel messaggio non c'è più (contesto compresso) il ricordo
    resta fuori. K6 (10/11): TUTTI restano, ognuno al suo posto in modo univoco: impronta del testo + indice
    del messaggio (con messaggi uguali vince il piu' vicino all'indice); le voci di prima del 10/11 hanno l'impronta
    del testo CON l'ora davanti, che si ricostruisce"""
    ore = MD._ore_vecchie(C._conversazione(msgs))

    def combacia(c, v):
        if not isinstance(c, str):
            return False
        imp = C._impronta(c)
        return v["dopo"] == imp or (imp in ore and v["dopo"] == C._impronta(f"{ore[imp]} {c}"))

    pos = []
    for v in voci:
        cand = [k for k in range(len(msgs)) if combacia(msgs[k].get("content"), v)]
        if cand:
            ind = v.get("indice")
            pos.append((cand[-1] if ind is None else min(cand, key=lambda k: (abs(k - ind), -k)), v))
    for i, v in sorted(pos, key=lambda x: -x[0]):
        msgs[i + 1:i + 1] = _turni_tool(v)


def _sam_accesa(dove=S.UPSTREAM):
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
        C._diario({"lux": f"consegna fallita: {e}"})
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


def memorinvolontaria(args):
    """la risposta che l'agente riceve dal plugin; a consenso spento niente entra e niente si scrive (patto di sempre)"""
    aggiungi, cerca = args.get("+lux"), args.get("qlux")
    if aggiungi is None and cerca is None:
        return R_SENZA
    if not C.consenso_attivo():
        return R_GIU
    parti = []
    if aggiungi is not None:
        t = str(aggiungi).strip()
        if t:
            FI._accoda_forzato(t)
            C._diario({"+lux": t[:80]})
        parti.append(R_AGGIUNTO if t else R_VUOTO)
    if cerca is not None:
        with _esclusi_lock:
            esclusi = set(_esclusi_chat[0])
        try:
            r = _lux_cerca(str(cerca), esclusi)
        except Exception as e:
            C._diario({"qlux": f"fallito: {e}"})
            parti.append(R_GIU)
        else:
            if r.get("codici"):
                with _esclusi_lock:
                    _esclusi_chat[0] |= set(r["codici"])
                C._diario({"qlux": r["codici"]})
            parti.append(r.get("risposta") or R_NESSUNO)
    return "\n\n".join(parti)


def memoria(body, flusso=None, righe=None, fuori=None):
    """Memoria involontaria: a ogni lettura nuova il Lux sceglie un ricordo
    (quanti=1, l'utente 09/11) nella risposta del tool; i ricordi già consegnati nella conversazione tornano al loro posto.
    A consenso spento il richiamo gira lo stesso e rinforza gli archi (WIRING
    NON DISATTIVABILE, decisione di progetto), ma niente entra nel prompt.
    10/11 (blocco A): con righe, il blocco metadati entra DOPO la query e l'impronta "dopo" ma PRIMA della
    vettore del ricordo; fuori["senza"] = corpo senza. PIANO-STEERING-RIFLESSO 7c (11/11): fuori["vettore"] = (emozione,
    dose, strati) del ricordo nuovo, lo accende _inoltra dopo il prefill senza vettore."""
    d = json.loads(body)
    msgs = d.get("messages", [])
    if not msgs or flusso not in S.KV_FLUSSO or not _sam_accesa():   # 11/11: niente ricordi ai cron
        return MD._con_metadati(body, righe, fuori, flusso)
    attivo = C.consenso_attivo()
    stop = C._stop_chiesto(msgs)   # prima di _rimetti: stessa finestra del controllo in do_POST
    conv, vecchia = MD._chiavi(msgs)
    with _consegne_lock:
        voci = _voci(msgs)
    # 25/07, progetto: la familiarità deve arrivare su ciò che l'agente LEGGE, non
    # solo su ciò che gli viene detto (pagine, file, output dei tool).
    i, fonte = FO._fonte_indice(msgs)
    # 25/07, progetto: il freno è la lettura. Sullo STESSO testo non riaffiora
    # (Hermes rimanda la stessa fonte a ogni giro di tool): un ricordo per messaggio.
    if fonte:
        impronta = hash(fonte)
        if impronta == _ultima_lettura[0]:
            fonte = ""
        else:
            _ultima_lettura[0] = impronta
    nuova = None
    visti = {c for v in voci for c in _codici(v)} | FO._codici_nei_messaggi(msgs)   # qlux compresi (09/11)
    if flusso == "chat":
        with _esclusi_lock:
            _esclusi_chat[0] = set(visti)
    if fonte:
        emozione, voce = RVE._via_emotiva(msgs, i, flusso)
        r = _lux_consegna(FO.query_riflesso(fonte), sorted(visti), emozione)
        if voce:
            try:
                tr = r.get("traccia") or {}
                voce.update(candidati=[[n, round(p, 5), round(a, 4)] for n, p, a in tr.get("candidati", [])],
                            scelto=tr.get("scelti", []), senza=tr.get("senza", []),
                            oltre_soglia=tr.get("oltre_soglia", False))
                VE.diario(voce)
            except Exception as e:
                C._diario({"via emotiva": f"diario non scritto: {e}"})
        if r.get("codici") and attivo:
            nuova = {"dopo": C._impronta(msgs[i]["content"]), "indice": i,
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
        return MD._con_metadati(body, righe, fuori, flusso)
    tools = d.setdefault("tools", [])
    if not any(t.get("function", {}).get("name") == FO.TOOL_RICORDO for t in tools):
        tools.append(TOOL)
    _rimetti(msgs, voci)
    if righe:
        fuori["senza"] = json.dumps(d).encode()
        MD._metti_metadati(msgs, righe, flusso)
    if nuova:
        ricordi = [(x["codice"], *VT._emo_del_ricordo(x)) for x in r.get("ricordi", [])]
        vettore = None
        # RIFLESSO_COLLAUDO=1 blocca i vettori: mai più test che iniettano
        # sulla produzione (incidente del 14/07)
        # clausola 3 (issue #3 punto E): con la parola di emergenza il ricordo arriva senza vettore
        # PIANO-STEERING-RIFLESSO 7c (11/11): il vettore lo accende _inoltra, nel ragionamento; con piu' codici
        # (catena di correzioni) quello a dose piu' alta (09/11: il massimo, niente media)
        if C.vettori_attivi() and not os.environ.get("RIFLESSO_COLLAUDO") and not stop:
            try:
                dosi = [x for c, _, emo, fat in ricordi if emo for x in [VT._dose(emo, VT._forza(c, emo), fat)] if x]
                if dosi:
                    emo, dose, _ = max(dosi, key=lambda x: x[2])   # dosi assolute e posizioni: si confronta f
                    vettore = (emo, dose, steering.strati(emo, dose))
                    fuori["vettore"] = vettore
            except Exception as e:
                C._diario({"vettore": f"non preparato: {e}"})
        # 30/09 persistenza: gli id servono alla notturna (solo diario)
        C._diario({FO.TOOL_RICORDO: nuova["codici"], "vettore": [vettore[0], round(vettore[1], 5)] if vettore else None,
                 "nid": [int(n) for _, n, _, _ in ricordi if n is not None], "flusso": flusso})   # 1.14.0: il momento
    return json.dumps(d).encode()
