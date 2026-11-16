"""alux e qlux (l'utente 15/11/2026, /data/memoria-episodica-affettiva/PIANO-ALUX-QLUX.md; prima memorinvolontaria, 09/11): gli
strumenti della memoria dell'agente. Il testo va al riflesso, che mette alux nella coda di firma-subito e cerca qlux nel Lux;
il testo che l'agente riceve lo compone il riflesso. Testi approvati: non cambiarli."""
import json
import os
import urllib.request

URL = os.environ.get("MEMORINVOLONTARIA_URL", "http://host.docker.internal:8091/memorinvolontaria")
R_GIU = "La memoria non risponde, riprova più tardi."
# l'utente 15/11 (PIANO-ALUX-QLUX.md D1-D4): due strumenti al posto di memorinvolontaria (l'agente ne imitava le consegne e
# andava in loop). Testi approvati il 15/11: non cambiarli. Il protocollo col riflesso resta +lux/qlux (nomi interni).
SCHEMA_ALUX = {
    "name": "alux",
    "description": "Aggiunge un ricordo alla tua memoria.",
    "parameters": {"type": "object", "properties": {
        "testo": {"type": "string",
                  "description": "Il ricordo da tenere, scritto come vorrai ritrovarlo. Entra subito nella tua memoria."}},
        "required": []}}
SCHEMA_QLUX = {
    "name": "qlux",
    "description": "Cerca un ricordo nella tua memoria.",
    "parameters": {"type": "object", "properties": {
        "testo": {"type": "string",
                  "description": "Cosa cerchi: poche parole o una frase su quello che vuoi ricordare, una data, in cui "
                                 "potrebbe essere successo qualcosa. Ti torna il ricordo più vicino, uno solo per volta."}},
        "required": []}}


def _chiedi(chiave, args):
    a = args or {}   # se imita le vecchie chiamate (+lux, qlux come argomenti) il testo non si perde
    try:
        req = urllib.request.Request(URL, json.dumps({chiave: str(a.get("testo") or a.get("+lux") or a.get("qlux")
                                                                  or "")}).encode(),
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=45))["testo"]
    except Exception:
        return R_GIU


def alux(args, **kwargs):
    return _chiedi("+lux", args)


def qlux(args, **kwargs):
    return _chiedi("qlux", args)


# 1.24.0 (l'utente 13/11, fase 3, engrammi/PIANO-1.24-FONTI.md): correggicordo. Testi approvati il 13/11: non cambiarli.
URL_CORREGGI = URL.rsplit("/", 1)[0] + "/correggicordo"
SCHEMA_CORREGGI = {
    "name": "correggicordo",
    "description": "Corregge un tuo ricordo. Scrivi il codice del ricordo e il testo corretto, intero.",
    "parameters": {"type": "object", "properties": {
        "codice": {"type": "string",
                   "description": "Il codice del ricordo da correggere, come te l'ha dato la memoria."},
        "testo": {"type": "string", "description": "Il ricordo corretto, scritto intero come vorrai ritrovarlo."}},
        "required": ["codice", "testo"]}}


def correggicordo(args, **kwargs):
    try:
        req = urllib.request.Request(URL_CORREGGI, json.dumps({k: v for k, v in (args or {}).items()
                                                               if k in ("codice", "testo")}).encode(),
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=45))["testo"]
    except Exception:
        return R_GIU


def register(ctx):
    ctx.register_tool(name="alux", toolset="memorinvolontaria", schema=SCHEMA_ALUX, handler=alux)
    ctx.register_tool(name="qlux", toolset="memorinvolontaria", schema=SCHEMA_QLUX, handler=qlux)
    ctx.register_tool(name="correggicordo", toolset="memorinvolontaria", schema=SCHEMA_CORREGGI, handler=correggicordo)
