#!/usr/bin/env python3
"""B6 di PIANO-FIRMA-ENGRAMMI.md (l'utente 31/10-01/11): il ricordo entra subito, non piu' nella notturna.
Il riflesso, a turno chiuso, scrive i messaggi in coda-firma.jsonl ({ts, autore, testo}); questo servizio li firma col
server vivo (firma_se.firma_server, stats e soglia di B3) e mette il ricordo nel Lux degli engrammi (1.20.0: POST /aggiungi
del servizio del Lux, che da' anche il numero; prima memoria.db).
Registro del giorno (giornata-firma.jsonl, una riga per messaggio, l'ultima per (ts, testo) vale): contesto, dedup,
trascinamento (behavioral tagging) e notturna.
  firma_subito.py servizio        giro ogni GIRO_S secondi sulla coda (firma-subito.service)
  firma_subito.py recupera J      notturna: in coda i messaggi di J che mancano, poi aspetta
                                  che il servizio svuoti la coda (35B spento o servizio fermo = uscita 1)
  firma_subito.py notte DA_TS     notturna: persistenza sugli scartati e omeostato dai nodi nati da DA_TS in poi
Uso: /data/jspace/venv/bin/python /data/memoria-episodica-affettiva/engrammi/firma_subito.py servizio"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import torch

sys.path.insert(0, "/data/memoria-episodica-affettiva")
sys.path.insert(0, "/data/memoria-episodica-affettiva/engrammi")
import firma_se as F  # noqa: E402
import memoria  # noqa: E402
import persistenza  # noqa: E402  (vettore = bge-m3 del messaggio intero, come le abitudini di B5)
import prepara_messaggi as T  # noqa: E402  (pulisci, contesto_di: gli stessi del tagging; 10/11 senza tagging35b)

QUI = os.path.dirname(os.path.abspath(__file__))
MEM = os.environ.get("MEM_SAM", "/data/workspace/memoria")   # MEM_SAM: copia per i test
CODA = f"{MEM}/coda-firma.jsonl"
POS = f"{MEM}/coda-firma.pos"
ROTTE = f"{MEM}/coda-firma-rotte.jsonl"
GIORNATA = f"{MEM}/giornata-firma.jsonl"
MARKER = os.environ.get("MARKER_NOTTE", "/data/memoria-episodica-affettiva/.ultimo-consolidamento")   # notte-memoria.sh
URL = os.environ.get("URL_FIRMA", "http://127.0.0.1:8090")
STATS = os.environ.get("STATS_SE", "/data/memoria-episodica-affettiva/stats-firma-se.pt")
GIRO_S = float(os.environ.get("GIRO_S", 5))
FINESTRA = 86400       # contesto e dedup: messaggi delle 24 ore prima, come B3
TRASCINA = 3600        # behavioral tagging: 60 minuti prima e dopo (Moncada e Viola 2007)
FORTE_DELTA = 0.76     # "forte" = salienza almeno 0.76 z sopra la soglia (09/11 l'utente: stessa quota di forti della firma a 24, 5.7%; prima 1.0)
# 01/11 sera: la cattura vuole anche la sovrapposizione PARZIALE degli engrammi col forte (cattura sinaptica:
# solo le tracce che condividono cellule col forte prendono le sue proteine; Dunsmoor 2015: solo i ricordi legati)
QUOTA_MIN = 0.25       # almeno un quarto degli engrammi del debole gia' nel forte (scelta di CC)
G_MIN = 0.25           # S0 del trascinato = S0 propria x g, g = G_MIN + (1 - G_MIN) x quota x forza del forte
FORZA_PIENA = 3.0      # forza del forte = (z - soglia) / FORZA_PIENA, fra 1/3 (soglia + 1) e 1 (soglia + 3)
LUX_URL = os.environ.get("LUX_URL", "http://127.0.0.1:8132")
FERMA_MAX = 600        # recupera: secondi senza che la coda avanzi = servizio fermo o 35B spento
TIENI = 3 * 86400      # B7: il registro tiene 3 giorni (e tutto quello dal marker della notturna meno un giorno)
POTA_OGNI = 6 * 3600   # B7: ogni quanto il servizio pota il registro
URL_RE = re.compile(r"https?://|www\.")   # regola 2: "letto"
log = T.log


class Aspetta(Exception):
    """il lettore non c'e' (35B spento, binario senza somme, altro modello): la coda resta ferma"""


# ---------- registro del giorno ----------

def _chiave(m):
    return f"{m['ts']!r}|{m['testo']}"


def registro():
    """{(ts, testo): voce}, l'ultima riga vince (append-only: un trascinamento riscrive l'esito)"""
    out = {}
    if os.path.exists(GIORNATA):
        for r in open(GIORNATA, encoding="utf-8"):
            try:
                v = json.loads(r)
                out[_chiave(v)] = v
            except (ValueError, KeyError, TypeError):   # riga a meta' (crash durante la scrittura): si salta
                pass
    return out


def _annota(reg, voce):
    with open(GIORNATA, "a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")
    reg[_chiave(voce)] = voce


def _limite(ora=None):
    """B7: le voci prima di qui non servono piu' (ne' contesto ne' dedup ne' notturna)"""
    ora = time.time() if ora is None else ora
    try:
        marker = os.path.getmtime(MARKER)
    except OSError:
        marker = 0   # niente marker: la notturna prende tutto, si tiene tutto
    return min(ora - TIENI, marker - FINESTRA)


def pota(ora=None):
    """B7: via dal registro le voci vecchie; restano quelle che servono a contesto e dedup (24 ore) e alla notturna (dal
    marker in poi, anche dopo notti fallite). Una riga per voce, scrittura atomica; la fa solo il servizio, l'unico che
    scrive il registro."""
    limite = _limite(ora)
    reg = registro()
    tieni = [v for v in reg.values() if v["ts"] >= limite]
    with open(GIORNATA + ".tmp", "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in tieni))
    os.replace(GIORNATA + ".tmp", GIORNATA)
    log.info("registro potato: %d voci, %d tolte", len(tieni), len(reg) - len(tieni))


def _vivi(reg, ts):
    """messaggi del registro nelle 24 ore prima di ts, in ordine di tempo (doppioni e corti fuori, come nel tagging)"""
    return sorted((v for v in reg.values() if ts - FINESTRA <= v["ts"] < ts - 0.5
                   and v["esito"] in ("nodo", "scartato", "trascinato")), key=lambda v: v["ts"])


def _dedup(m):
    return (m.get("autore", ""), m["testo"][:200])   # tagging35b.dedup (deciso dall'agente il 12/07)


# ---------- firma ----------

_st = {}


def stats():
    if not _st:
        s = torch.load(STATS, weights_only=False)
        F.usa(s.get("vettori", "/data/jspace/out-occamy/vettori-firma.pt"))   # 09/11: i vettori delle statistiche
        assert F.vettori()[0] == s["assi"] and len(s["mean"]) == len(s["assi"]), "vettori e statistiche diversi"
        _st.update(s=s, mean=s["mean"].double().numpy(), sd=np.sqrt(s["M2"].double().numpy() / max(s["n"] - 1, 1)),
                   mu={l: s["mu"][l].double().numpy() for l in F.STRATI})
    return _st


def controlla_lettore():
    try:
        with urllib.request.urlopen(URL + "/props", timeout=10) as f:
            mod = json.load(f).get("model_path")
    except Exception as e:
        raise Aspetta(f"server {URL} non risponde ({e})")
    if mod != stats()["s"]["lettore"]:
        raise Aspetta(f"lettore {mod} diverso da quello delle statistiche ({stats()['s']['lettore']})")


def firma(contesto, testo):
    """(firma {asse: z}, salienza, dominante); errori di rete o binario senza somme = Aspetta"""
    st = stats()
    try:
        r = F.firma_server(contesto, testo, URL, st["mu"])
    except urllib.error.HTTPError as e:
        if e.code < 500:   # il server rifiuta questo testo: la firma di questo messaggio non si fa
            raise ValueError(f"lettore: HTTP {e.code}")
        raise Aspetta(f"lettura fallita (HTTP {e.code})")
    except (OSError, RuntimeError) as e:   # URLError e' un OSError
        raise Aspetta(f"lettura fallita ({e})")
    z = (r - st["mean"]) / (st["sd"] + 1e-6)
    f = {a: round(float(z[j]), 3) for j, a in enumerate(st["s"]["assi"])}
    return f, max(f.values()), memoria.dominante(f)   # 09/11: dominante fra le emozioni con vettore


# ---------- nodi ----------

def _lux(rotta, corpo, attesa=30):
    """POST al servizio del Lux; servizio giu', 5xx o altro 4xx (rotta assente: servizio vecchio) = Aspetta (la coda
    aspetta), 400 = urllib.error.HTTPError"""
    r = urllib.request.Request(LUX_URL + rotta, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(r, timeout=attesa))
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise
        raise Aspetta(f"servizio del Lux: HTTP {e.code}")
    except OSError as e:
        raise Aspetta(f"servizio del Lux non risponde ({e})")


def nodo(v, fonte, cattura=None):
    """1.20.0: il ricordo nel Lux (POST /aggiungi: stesso testo = stesso ricordo, come faceva memoria.add_node) -> nid.
    Il Lux lo rifiuta (400) = ValueError: la voce si segna "errore" e la coda va avanti"""
    corpo = {"testo": v["testo"], "firma": v["firma"], "dominante": v["dominante"], "fonte": fonte, "ts": v["ts"],
             "classe": "letto" if URL_RE.search(v["testo"]) else "vissuto", "voluto": 1 if v.get("forzato") else 0,
             "cattura": cattura, "salienza": v["salienza"]}
    try:
        return _lux("/aggiungi", corpo, attesa=120)["nid"]
    except urllib.error.HTTPError as e:
        raise ValueError(f"Lux: HTTP {e.code} {e.read()[:300]!r}")


def cattura(testo, forte):
    """g del debole catturato dal ricordo forte (dict del registro), None = niente cattura. Sovrapposizione dal servizio
    del Lux (spaCy e bge-m3 stanno li'); servizio giu' = la coda aspetta"""
    try:
        o = _lux("/sovrapposizione", {"testo": testo, "nid": forte["nid"]}, attesa=120)
    except urllib.error.HTTPError as e:
        if e.code == 400:   # il forte non e' nel Lux (tolto): niente cattura
            return None
        raise Aspetta(f"servizio del Lux: HTTP {e.code}")
    n, presi = o["n"], o["presi"]
    if not n or presi < 1 or presi == n or presi / n < QUOTA_MIN:   # niente in comune, troppo poco, o niente di nuovo
        return None
    forza = min(1.0, max(1 / 3, (forte["salienza"] - stats()["s"]["soglia"]) / FORZA_PIENA))
    return round(G_MIN + (1 - G_MIN) * (presi / n) * forza, 4)


def _trascina(reg, v, forte, g):
    try:
        nid = nodo(v, "trascinato", g)
    except ValueError as e:   # resta scartato (la persistenza lo vede ancora), con l'errore
        _annota(reg, dict(v, esito="scartato", errore=str(e)))
        log.warning("trascinato rifiutato dal Lux: %s (%s)", e, v["testo"][:60])
        return
    _annota(reg, dict(v, esito="trascinato", nid=nid, da=forte["nid"], cattura=g))
    log.info("TRASCINATO da %s (z=%.2f, g=%.2f) %s", forte["nid"], v["salienza"], g, v["testo"][:60])


def elabora(m, reg):
    """una voce della coda; True = c'e' un nodo nuovo da mettere nel Lux"""
    if _chiave(m) in reg:          # gia' fatta (crash dopo il registro, prima del segnalibro): il Lux si ricontrolla
        return reg[_chiave(m)]["esito"] in ("nodo", "trascinato")
    if m["ts"] < _limite():        # B7: piu' vecchia del registro potato (segnalibro perso): gia' fatta a suo tempo
        return False
    forzato = bool(m.get("forzato"))
    testo = T.pulisci(m["testo"])
    if testo is not None:   # 09/11: tolto il marcatore [ricordare]; restano i forzati di +lux
        m = dict(m, testo=testo.strip())
    if testo is None or (len(m["testo"]) < 15 and not forzato):
        _annota(reg, dict(m, esito="corto"))
        return False
    vivi = _vivi(reg, m["ts"])
    if not forzato and any(_dedup(x) == _dedup(m) for x in vivi):
        _annota(reg, dict(m, esito="doppione"))
        return False
    try:
        f, sal, dom = firma(T.contesto_di([x["testo"] for x in vivi]), m["testo"])
    except ValueError as e:   # la firma di questo messaggio non si fa (testo che il lettore rifiuta)
        _annota(reg, dict(m, esito="errore", errore=str(e)))
        log.warning("firma impossibile: %s (%s)", e, m["testo"][:60])
        return False
    v = dict(m, firma=f, salienza=sal, dominante=dom, forzato=forzato)
    soglia = stats()["s"]["soglia"]
    if sal < soglia and not forzato:
        if not URL_RE.search(v["testo"]):   # il forte che cattura di piu' fra quelli dell'ultima ora
            prese = [(g, x) for x in vivi if x["esito"] == "nodo" and x["salienza"] >= soglia + FORTE_DELTA
                     and m["ts"] - x["ts"] <= TRASCINA for g in [cattura(v["testo"], x)] if g]
            if prese:
                g, x = max(prese, key=lambda p: p[0])
                _trascina(reg, v, x, g)
                return True
        _annota(reg, dict(v, esito="scartato"))
        log.info("SCARTO (z=%.2f) %s", sal, v["testo"][:60])
        return False
    try:
        nid = nodo(v, m.get("autore", ""))   # 1.20.0: e' gia' nel Lux, la sovrapposizione col forte si puo' misurare
    except ValueError as e:
        _annota(reg, dict(v, esito="errore", errore=str(e)))
        log.warning("ricordo rifiutato dal Lux: %s (%s)", e, m["testo"][:60])
        return False
    if sal >= soglia + FORTE_DELTA:
        for x in vivi:
            if x["esito"] == "scartato" and m["ts"] - x["ts"] <= TRASCINA and not URL_RE.search(x["testo"]):
                g = cattura(x["testo"], dict(v, nid=nid))
                if g:
                    _trascina(reg, x, dict(v, nid=nid), g)
    _annota(reg, dict(v, esito="nodo", nid=nid))   # dopo i trascinati: un crash in mezzo rifa' la voce e li finisce
    log.info("NODO %s (z=%.2f, %s%s) %s", nid, sal, dom, ", forzato" if forzato else "", v["testo"][:60])
    return True


# ---------- coda ----------

def _pos():
    """byte gia' elaborati; una coda ricreata piu' corta riparte da capo (le voci gia' fatte le salta il registro)"""
    try:
        p = int(open(POS).read())
    except (OSError, ValueError):
        return 0
    return p if os.path.exists(CODA) and p <= os.path.getsize(CODA) else 0


def _segna(p):
    with open(POS + ".tmp", "w") as f:
        f.write(str(p))
    os.replace(POS + ".tmp", POS)


def giro():
    """elabora le righe intere dopo il segnalibro; Aspetta = ferma, riprende da li' al giro dopo"""
    if not os.path.exists(CODA):
        return 0
    p, fatte = _pos(), 0
    with open(CODA, "rb") as f:
        f.seek(p)
        righe = f.read()
    if b"\n" not in righe:
        return 0
    controlla_lettore()
    reg = registro()
    for riga in righe.split(b"\n")[:-1]:   # l'ultimo pezzo senza a capo e' una riga ancora in scrittura
        try:
            m = json.loads(riga)
            m = {**m, "ts": float(m["ts"]), "testo": str(m["testo"])}
        except (ValueError, KeyError, TypeError) as e:
            with open(ROTTE, "a", encoding="utf-8") as g:
                g.write(json.dumps({"riga": riga.decode("utf-8", "replace"), "errore": str(e)}, ensure_ascii=False) + "\n")
            log.warning("riga rotta saltata: %s", riga[:80])
        else:
            elabora(m, reg)
        p += len(riga) + 1
        _segna(p)
        fatte += 1
    return fatte


_potato = [0.0]


def passo():
    """un giro del servizio -> stato ("pronto", "in attesa: ...", "errore: ...")"""
    try:
        if time.time() - _potato[0] > POTA_OGNI and os.path.exists(GIORNATA):
            _potato[0] = time.time()   # anche se fallisce: si riprova fra POTA_OGNI, il giro va avanti
            try:
                pota()
            except Exception:
                log.exception("potatura del registro fallita")
        giro()
        return "pronto"
    except Aspetta as e:
        return f"in attesa: {e}"
    except Exception as e:
        log.exception("giro fallito")
        return f"errore: {e}"


def servizio():
    stato = None
    while True:
        nuovo = passo()
        if nuovo != stato:
            log.info("STATO %s", nuovo)
            stato = nuovo
        time.sleep(GIRO_S)


# ---------- notturna ----------

def accoda(voci):
    """una sola write in append, come il riflesso: righe intere anche se scriviamo insieme"""
    fd = os.open(CODA, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voci).encode())
    finally:
        os.close(fd)


def _pronto(m):
    """chiave di dedup del messaggio com'e' nel registro (pulito); None = niente da firmare"""
    t = T.pulisci(m["testo"])
    return None if t is None else _dedup(dict(m, testo=t.strip()))


def recupera(jsonl):
    """i messaggi della giornata estratta che il riflesso non ha passato (riflesso giu', pensatoio) vanno in coda;
    poi si aspetta la coda vuota. Uscita 1 = la notte dopo rimedia. 09/11: ricorda-ora archiviato, c'e' +lux."""
    giorno = [json.loads(r) for r in open(jsonl, encoding="utf-8") if r.strip()]
    da = min((float(m["ts"]) for m in giorno), default=0) - FINESTRA   # stessa finestra del dedup di elabora
    viste = {_dedup(v) for v in registro().values() if v["ts"] >= da}
    if os.path.exists(CODA):
        with open(CODA, "rb") as f:
            f.seek(_pos())
            for r in f.read().split(b"\n"):
                try:
                    viste.add(_pronto(json.loads(r)))
                except (ValueError, KeyError, TypeError, AttributeError):
                    pass
    mancano = []
    for m in giorno:
        k = _pronto(m)
        if k is None or k in viste:
            continue
        viste.add(k)
        mancano.append({"ts": float(m["ts"]), "autore": m.get("autore", ""), "testo": m["testo"]})
    accoda(sorted(mancano, key=lambda v: v["ts"]))
    log.info("RECUPERO: %d messaggi mancanti in coda", len(mancano))
    p, fermo = _pos(), time.time()
    while p < os.path.getsize(CODA):
        if time.time() - fermo > FERMA_MAX:
            log.error("RECUPERO FALLITO: coda ferma da %d s (35B spento o firma-subito fermo)", FERMA_MAX)
            return 1
        time.sleep(GIRO_S)
        if _pos() != p:
            p, fermo = _pos(), time.time()
    log.info("RECUPERO-COMPLETO")
    return 0


def notte(da_ts):
    """persistenza sugli scartati e omeostato dai nodi del registro con ts >= da_ts (le parti del tagging che non
    leggono il modello)"""
    voci = [v for v in registro().values() if v["ts"] >= da_ts]
    sc = [(v["testo"], v["firma"], v["ts"]) for v in voci if v["esito"] == "scartato" and not URL_RE.search(v["testo"])]

    def promuovi(testo, firma, vettore, ts, giorni):   # 1.20.0: nel Lux (prima memoria.db)
        try:
            return nodo({"testo": testo, "firma": firma, "dominante": memoria.dominante(firma), "ts": ts,
                         "salienza": max(firma.values())}, "abitudine")
        except ValueError as e:   # il Lux rifiuta questo tema: gli altri e il buffer vanno avanti
            log.warning("abitudine rifiutata dal Lux: %s (%s)", e, testo[:60])
            return None

    firme = [v["firma"] for v in voci if v["esito"] in ("nodo", "trascinato")]
    if firme:   # prima della persistenza: se fallisce, la notte dopo rifa' tutto senza contare due volte eco e temi
        T.imprimi_omeostato(firme)
    try:
        esito = persistenza.notte(sc, promuovi=promuovi)
        log.info("PERSISTENZA: eco %d su %d ricordi, temi %d (+%d, -%d), promossi %d", esito["eco"], esito["ricordi_eco"],
                 esito["temi"], esito["temi_nuovi"], esito["temi_dimenticati"], len(esito["promossi"]))
    except Exception:   # come nel tagging: eco e abitudini saltano una notte, la notturna va avanti
        log.exception("persistenza NON eseguita")
    log.info("NOTTE-COMPLETA: %d scartati alla persistenza, %d firme all'omeostato", len(sc), len(firme))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "servizio":
        servizio()
    elif cmd == "recupera":
        sys.exit(recupera(sys.argv[2]))
    elif cmd == "notte":
        notte(float(sys.argv[2]))
    else:
        sys.exit(__doc__)
