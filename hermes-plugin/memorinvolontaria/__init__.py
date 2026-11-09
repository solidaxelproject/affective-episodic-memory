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


def register(ctx):
    ctx.register_tool(name="memorinvolontaria", toolset="memorinvolontaria", schema=SCHEMA, handler=memorinvolontaria)
