"""memorinvolontaria (l'utente 09/11/2026, /data/memoria-episodica-affettiva/PIANO-MEMORINVOLONTARIA-LUX.md): lo strumento della
memoria dell'agente. Gli argomenti vanno al riflesso, che scrive +lux nella coda di firma-subito e cerca qlux nel Lux; il
testo che l'agente riceve lo compone il riflesso. Testi approvati il 09/11: non cambiarli."""
import json
import os
import urllib.request

URL = os.environ.get("MEMORINVOLONTARIA_URL", "http://host.docker.internal:8091/memorinvolontaria")
R_GIU = "La memoria non risponde, riprova più tardi."
SCHEMA = {
    "name": "memorinvolontaria",
    "description": "Ricordi che affiorano dalla tua memoria, collegati alla conversazione. Arrivano da soli, uno alla "
                   "volta: usali solo se servono alla risposta. Puoi anche chiamare tu questo strumento: con +lux "
                   "aggiungi un ricordo alla tua memoria, con qlux cerchi un ricordo.",
    "parameters": {"type": "object", "properties": {
        "+lux": {"type": "string",
                 "description": "Il ricordo da tenere, scritto come vorrai ritrovarlo. Entra subito nella tua memoria."},
        "qlux": {"type": "string",
                 "description": "Cosa cerchi: poche parole o una frase su quello che vuoi ricordare, una data, in cui "
                                "potrebbe essere successo qualcosa. Ti torna il ricordo più vicino, uno solo per volta."}},
        "required": []}}


def memorinvolontaria(args, **kwargs):
    try:
        req = urllib.request.Request(URL, json.dumps({k: v for k, v in (args or {}).items() if k in ("+lux", "qlux")}).encode(),
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=45))["testo"]
    except Exception:
        return R_GIU


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
    ctx.register_tool(name="memorinvolontaria", toolset="memorinvolontaria", schema=SCHEMA, handler=memorinvolontaria)
    ctx.register_tool(name="correggicordo", toolset="memorinvolontaria", schema=SCHEMA_CORREGGI, handler=correggicordo)
