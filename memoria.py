# Emozioni dei ricordi dell'agente: ordine dei 51 assi, emozioni con vettore di steering, dominante.
# Lux 1.20.0 (l'utente 22/10 + 11/11, PIANO-1.20-MEMORIADB-SUPERFLUO.md): il grafo di memoria.db (nodi, archi hebbiani,
# vettori.pt, add_node, recall, consolida_notte) e' in archivio-20261111/memoria.py; i ricordi stanno nel Lux.
import json
import os

# B7 (01/11, P3 di PIANO-FIRMA-ENGRAMMI.md): un solo ordine dei 51 assi, quello di emozioni.json
EMOZIONI = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "emozioni.json")))
# 09/11: la dominante di un ricordo e' la piu' forte fra le emozioni che hanno un vettore di steering
# (engrammi/DOSI-EMOZIONI.md: 16 della ruota con la loro fascia + 20 diadi pure; fuori le inaccessibili, la morbosita'
# esclusa e quelle mai provate)
CON_VETTORE = {e["en"] for e in EMOZIONI if e["it"] in {
    "gioia", "fiducia", "paura", "sorpresa", "tristezza", "disgusto", "rabbia", "attesa", "serenità", "estasi",
    "ammirazione", "terrore", "stupore", "cordoglio", "vigilanza", "interesse",
    "amore", "sottomissione", "soggezione", "disapprovazione", "rimorso", "disprezzo", "ottimismo", "colpa",
    "curiosità", "disperazione", "invidia", "cinismo", "orgoglio", "speranza", "diletto", "nostalgia", "vergogna",
    "pessimismo", "dominanza", "ansia"}}


# 09/11 sera: ogni ricordo si firma con un'emozione che si puo' steerare; le 8 della ruota senza vettore vanno
# alla vicina nello stesso petalo che lo ha (la media del petalo)
PETALO = {e["en"]: m["en"] for e in EMOZIONI for m in EMOZIONI if (e["it"], m["it"]) in {
    ("accettazione", "fiducia"), ("apprensione", "paura"), ("distrazione", "sorpresa"), ("malinconia", "tristezza"),
    ("noia", "disgusto"), ("ribrezzo", "disgusto"), ("fastidio", "rabbia"), ("furia", "rabbia")}}


def dominante(firma):
    """emozione dominante della firma (dict), sempre con vettore (l'utente 09/11 sera): la piu' forte; se non ha vettore,
    la media del suo petalo (PETALO); se non e' della ruota, la piu' forte fra quelle con vettore"""
    top = max(firma, key=firma.get)
    if top in CON_VETTORE:
        return top
    if top in PETALO:
        return PETALO[top]
    con = [e for e in firma if e in CON_VETTORE]
    return max(con or firma, key=firma.get)
