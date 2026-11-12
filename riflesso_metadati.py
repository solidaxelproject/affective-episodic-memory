# riflesso_metadati.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import json
import subprocess
import threading
import time
from pathlib import Path
import riflesso_stato as S
import riflesso_comune as C
import riflesso_fonte as FO


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


# ---- ORA DEI MESSAGGI: l'ora di ARRIVO dell'ultimo messaggio user, registrata in "arrivi" (17/10, formato
# [d/m/aaaa|h:mm], dato della fase 2 del Lux). 10/11 (l'utente, M2 M3): l'agente la vede solo nel blocco metadati,
# [hh:mm|gg/mm/aaaa]; l'ora davanti a un messaggio dell'utente ogni 5 (16/10) e' tolta. "ore" resta per le voci di prima.
ORE = Path("/data/workspace/memoria/ore-messaggi.json")
_ore_lock = threading.Lock()


def _anticipa(senza, risposta):
    """3.5 (10/11): PREFILL ANTICIPATO a chat ferma: il messaggio dell'utente SENZA metadati e la risposta appena
    data senza ragionamento, come li vedra' il turno dopo (un user "." dopo: il template toglie il <think>), fino
    alla fine della risposta: la CRESTA, checkpoint protetto (K1). Al turno dopo si prefilla solo il messaggio nuovo.
    Solo dentro _cw_lock, con la chat nello slot"""
    d = json.loads(senza)
    resa = C._chiedi("/apply-template", {
        **{k: v for k, v in d.items() if k in ("tools", "tool_choice", "chat_template_kwargs")},
        "messages": d["messages"] + [{"role": "assistant", "content": C._senza_imitati(risposta).rstrip()},
                                     {"role": "user", "content": "."}]})["prompt"]
    C._chiedi("/completion", {"prompt": resa[:resa.rindex("<|im_start|>user")], "n_predict": 1, "cache_prompt": True,
                            "checkpoint_tag": "cresta"})


def _ore_vecchie(conv):
    """le ore che l'agente vedeva davanti ai messaggi dell'utente fino al 10/11, per impronta del testo senza ora"""
    try:
        return json.loads(ORE.read_text(encoding="utf-8")).get(conv, {}).get("ore", {})
    except (OSError, ValueError):
        return {}


def _chiavi(msgs):
    """K6 (10/11): la chiave della conversazione senza l'ora; fino al 10/11 il primo messaggio dell'utente portava
    sempre l'ora (revisione del blocco B, punto 2), quindi anche la chiave di allora, ricostruita (None se non c'e')"""
    conv = C._conversazione(msgs)
    primo = next((m.get("content") for m in msgs
                  if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
    ora = _ore_vecchie(conv).get(C._impronta(primo))
    return conv, (C._impronta(f"{ora} {primo}") if ora else None)


def _code(body, testi):
    """20/10: i testi in coda all'ultimo messaggio, se non e' la risposta della
    memoria involontaria (il ricordo resta nudo: si riprova alla richiesta dopo)"""
    d = json.loads(body)
    msgs = d.get("messages", [])
    if not msgs or not testi or FO._e_ricordo(msgs[-1], FO._ids_ricordo(msgs)):
        return body, False
    for t in testi:
        C._in_coda(msgs, t)
    return json.dumps(d).encode(), True


_arrivi_altri = {}   # pensatoio e cron: l'arrivo in memoria (ore-messaggi.json e' della chat: dato della fase 2)


def _ora_arrivo(msgs, registra=True):
    """M2 (10/11): l'ora di ARRIVO dell'ultimo messaggio user. Si fissa quando apre il turno (e' l'ultimo
    messaggio, anche se uguale a uno di prima) e si riusa nei giri di tool (revisione dei danni, punto 3)"""
    i = next((k for k in range(len(msgs) - 1, -1, -1) if msgs[k].get("role") == "user"), None)
    adesso = time.localtime(time.time())
    if i is None:
        return C._ora_blocco(adesso)
    c = msgs[i].get("content")
    conv, imp = C._conversazione(msgs), C._impronta(str(c))
    testo = c if isinstance(c, str) else next((p.get("text") or "" for p in c if isinstance(p, dict)), "") \
        if isinstance(c, list) else ""
    if not C._HANDLE.match(testo):    # review e memory flush di Hermes: fuori dal dato della fase 2 (3.5.3, punto 7)
        registra = False
    if not registra:
        if i == len(msgs) - 1 or (conv, imp) not in _arrivi_altri:
            if len(_arrivi_altri) > 200:
                _arrivi_altri.clear()
            _arrivi_altri[conv, imp] = adesso
        return C._ora_blocco(_arrivi_altri.get((conv, imp), adesso))
    with _ore_lock:
        try:
            tutte = json.loads(ORE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tutte = {}
        c = tutte.setdefault(conv, {"visti": [], "ore": {}})
        arrivi = c.setdefault("arrivi", {})
        if i == len(msgs) - 1 or imp not in arrivi:
            arrivi[imp] = C._ora_corta(adesso)
            c["ts"] = time.time()
            vive = dict(sorted(tutte.items(), key=lambda kv: kv[1].get("ts", 0))[-S.CONSEGNE_MAX:])
            tmp = ORE.with_suffix(".tmp")
            tmp.write_text(json.dumps(vive, ensure_ascii=False), encoding="utf-8")
            tmp.replace(ORE)
        corta = arrivi[imp]
    return C._ora_blocco(time.strptime(corta, "[%d/%m/%Y|%H:%M]"))


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
        C._diario({"metadati": f"stato del pensatoio illeggibile: {e}"})
    return ([] if flusso == "chat" else [PENSATOIO_DOVE]) + [stato, ora]


def _togli_imitati(msgs):
    """in place: via le copie del blocco metadati dalla fine delle risposte dell'agente"""
    for m in msgs:
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            m["content"] = C._senza_imitati(m["content"])


def _con_metadati(body, righe, fuori, flusso=None):
    """il blocco metadati su un corpo intero; fuori["senza"] = il corpo senza (per il prefill anticipato)"""
    if not righe:
        return body
    fuori["senza"] = body
    d = json.loads(body)
    _metti_metadati(d.get("messages", []), righe, flusso)
    return json.dumps(d).encode()


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
    dove = next((k for k in range(u - 1, -1, -1) if msgs[k].get("role") == "assistant" and C._ha_testo(msgs[k])), u)
    testo = "\n\n" + "\n".join(righe)
    c = msgs[dove].get("content")
    if isinstance(c, list):
        c.append({"type": "text", "text": testo})
    else:
        msgs[dove]["content"] = (c or "") + testo
