# riflesso_vettore.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import http.client
import json
import math
import os
import threading
import time
import urllib.request
import ponte
import steering
import riflesso_stato as S
import riflesso_comune as C


DURATA_MAX_S = 120                        # clausola 2: mai un vettore più vecchio
# issue #3 punto A, design dell'utente (18/10): il vettore appartiene alla KV cache
# del suo flusso. Allo scambio se ne va con la cache messa in pausa; al ripristino
# torna alla dose a cui era arrivato e la discesa riprende da li': il tempo della
# discesa scorre solo mentre la cache del flusso sta nello slot. Piu' vettori
# attivi si SOMMANO (l'utente 18/10, test multivettore); come sommarli e la curva
# della discesa sono della fase 2 (PIANO-LUX-FASI-v1.12.md, punto 7).
DURATA_S = 0    # fase 2: durata = permanenza x dose x importanza; 0 = muore col prefill, come oggi


LUX_FORZA = "http://127.0.0.1:8132/forza"


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
        C._diario({"lux": f"forza non letta: {e}"})
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
            S._vettore_vivo[0] = False
            return True
        except Exception as e:
            time.sleep(1 + tentativo)
            err = str(e)
    with open(C.DIARIO, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(),
                            "CRITICO": f"clear del vettore FALLITO 3 volte: {err}. "
                                       "SPEGNERE A MANO: curl -X POST :8090/control-vector "
                                       "-d '{\"clear\": true}'"}) + "\n")
    return False


def _orologio(fl):
    """secondi vissuti dal flusso fl con la sua cache nello slot (si ferma in pausa)"""
    return S._vissuto[fl] + (time.time() - S._caricato[0] if S._cw[0] == fl else 0.0)


def _vivi(fl):
    """[(emo, dose di adesso)] dei vettori ancora vivi del flusso; i finiti si tolgono.
    ponytail: discesa lineare, la curva vera e' della fase 2"""
    t = _orologio(fl)
    S._vettori[fl][:] = [v for v in S._vettori[fl] if t - v["nato"] < v["durata"]]
    return [(v["emo"], v["dose"] * (1 - (t - v["nato"]) / v["durata"])) for v in S._vettori[fl]]


def _azzera_vettori():
    for vv in S._vettori.values():
        vv.clear()


def _applica_flusso(fl):
    """Prima di ogni calcolo di un flusso (prefill o inoltro): sul server la SOMMA,
    layer per layer, dei vettori vivi di quel flusso alla dose gia' scesa; nessuno =
    spento. Il server tiene un vettore solo e lo sostituisce, quindi la somma si fa
    qui. Solo dentro _vettore_lock."""
    if not C.vettori_attivi() or os.environ.get("RIFLESSO_COLLAUDO"):
        _azzera_vettori()      # consenso ritirato: al ritorno non riappare niente di vecchio
    dosi = _vivi(fl) if fl in S._vettori else []
    if not dosi:
        if S._vettore_vivo[0]:
            calma()
        return
    somma = {}
    for emo, dose in dosi:
        for l, v in (ponte.dirs_emozione(emo, dose) or {}).items():
            somma[l] = [a + b for a, b in zip(somma[l], v)] if l in somma else list(v)
    _cvec({"layers": somma, "relative": True})
    S._vettore_vivo[0] = True
    watchdog = threading.Timer(DURATA_MAX_S, _scaduto)   # PATTO clausola 2, come per il prefill
    watchdog.daemon = True
    watchdog.start()


def _sentinella():
    """PATTO clausola 3+4: se "[vettori: *sì*]" sparisce dal consenso mentre un
    vettore è acceso, muore entro 1 secondo. Nessuna domanda, nessun dibattito."""
    while True:
        time.sleep(0.5)
        # issue #3 punto C: un giro in errore non ferma la sentinella; "kill" solo
        # se lo spegnimento e' riuscito (se fallisce, calma() ha gia' scritto CRITICO)
        try:
            if S._vettore_vivo[0] and not C.vettori_attivi() and calma():
                C._diario({"kill": "consenso vettoriale ritirato: spento dalla sentinella"})
        except Exception as e:
            try:
                C._diario({"sentinella": f"giro fallito: {e!r}"})
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
    if not S._vettore_vivo[0] or (chi is not None and S._vettore_di[0] is not chi):
        return
    try:
        up = http.client.HTTPConnection(*S.UPSTREAM, timeout=3)
        up.request("GET", "/slots")
        occupato = json.loads(up.getresponse().read())[0].get("is_processing")
        up.close()
    except Exception:
        occupato = True    # server irraggiungibile/carico: non sparare al buio
    if occupato:
        t = threading.Timer(20, _scaduto, args=(chi,))
        t.daemon = True
        t.start()
        C._diario({"watchdog": "slot vivo: kill vettore rimandato 20s"})
        return
    calma()
    C._diario({"kill": f"vettore oltre {DURATA_MAX_S}s: spento dal watchdog"})



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
    S._vettore_vivo[0] = True
    watchdog = threading.Timer(DURATA_MAX_S, lambda: _scaduto(watchdog))   # PATTO clausola 2
    watchdog.daemon = True
    watchdog.start()
    S._vettore_di[0] = watchdog
    return json.dumps({**d, "reasoning_control": True, "cvec_solo_ragionamento": True}).encode(), watchdog
