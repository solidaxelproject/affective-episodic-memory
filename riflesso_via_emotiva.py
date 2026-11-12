# riflesso_via_emotiva.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import threading
import via_emotiva as VE
import riflesso_stato as S
import riflesso_comune as C
import riflesso_fonte as FO
import riflesso_metadati as MD


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
        return FO._leggibile(c), "strumento"
    if flusso == "pensatoio":
        return (FO.query_riflesso(c), "pensatoio") if FO._MARCA_RISVEGLIO.search(c) else None
    m = C._HANDLE.match(C._ORA.sub("", c).strip())
    return (m.group(2).strip(), m.group(1)) if m and m.group(2).strip() else None


def _via_emotiva(msgs, i, flusso):
    """1.19.0 (l'utente 11/11, due tempi): la fonte passa dalla lente e imprime l'umore; l'indizio = meta' emozione della
    fonte e meta' umore di PRIMA della sua lettura. -> (emozione per il Lux, voce del diario) o (None, None): mai bloccare
    la parola dell'agente"""
    try:
        x = _da_leggere(msgs, i, flusso)
        conv, _ = MD._chiavi(msgs)
        chiave = f"{flusso}|{conv}|{i}|{C._impronta(x[0])}" if x else None
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
    if flusso not in S.KV_FLUSSO or not esito or esito.get("finish") != "stop" or esito.get("tool_calls"):
        return
    if flusso == "chat":   # come la firma: la risposta a Hermes (review, memory flush, ultimo user senza handle) no
        m = C._HANDLE.match(ultimo.strip()) if isinstance(ultimo, str) else None
        if not m or not m.group(2).strip():
            return
    testo = C._senza_imitati(esito.get("testo") or "").strip()
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
