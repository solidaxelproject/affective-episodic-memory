# riflesso_fonte.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import html
import json
import re
from urllib.parse import urlsplit
import riflesso_comune as C


LETTURA_MIN = 400      # manopola: sotto tanti caratteri di prosa, un risultato di
                       # tool è una ricevuta (exit_code, bytes_written), non una lettura


TOOL_RICORDO = "memorinvolontaria"


_URL = re.compile(r"https?://[^\s\"'<>\\]+")   # 1.24.0: un URL negli argomenti di una chiamata


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
    testo = C._ORA.sub("", testo or "")   # l'ora del messaggio non fa affiorare ricordi
    m = _MARCA_RISVEGLIO.search(testo)
    if not m:
        return _leggibile(testo)
    riga = m.group(1)
    r = _RIGA_APPUNTO.match(riga)
    return f"{r.group('tema')} {r.group('query')}" if r else riga


def dominio(url):
    """1.24.0, D1 (l'utente 13/11, PIANO-1.24-FONTI.md): il sito e' il dominio, senza www.; URL malformato = """""
    try:
        h = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _url(arguments):
    """il primo URL negli argomenti di una chiamata (stringa JSON di Hermes: si cerca nei valori decodificati)"""
    try:
        d = json.loads(arguments)
        testi = [str(v) for v in d.values()] if isinstance(d, dict) else [str(d)]
    except (ValueError, TypeError):
        testi = [str(arguments)]
    for t in testi:
        u = _URL.search(t)
        if u:
            return u.group()
    return ""


def letture(msgs):
    """1.24.0 (D1, D8): [(id della chiamata, dominio)] delle pagine lette: risultato di uno strumento con almeno
    LETTURA_MIN caratteri di prosa e un URL negli argomenti della sua chiamata (una ricerca non ha URL: D8)"""
    args = {tc.get("id"): (tc.get("function") or {}).get("arguments", "") for m in msgs
            if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])}
    ids = _ids_ricordo(msgs)
    out = []
    for m in msgs:
        if m.get("role") != "tool" or _e_ricordo(m, ids) or not isinstance(m.get("content"), str):
            continue
        d = dominio(_url(args.get(m.get("tool_call_id"), "")))
        if d and len(_leggibile(m["content"])) >= LETTURA_MIN:
            out.append((m.get("tool_call_id"), d))
    return out


def siti_del_turno(msgs):
    """1.24.0: i siti letti dopo l'ultimo messaggio user (il turno della risposta finale dell'agente), senza doppioni"""
    u = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
    return list(dict.fromkeys(d for _, d in letture(msgs[u + 1:])))
