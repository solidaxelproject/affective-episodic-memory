# Ponte tra riflesso/strumenti e il server llama-lux dell'agente: lettura della sonda
# a L29 in coordinate della lente, control-vector emotivi, POST.
#
# GRADINO ZERO (decisione 3 del 26/07, registro del refactoring): questo file è
# l'UNICA porta client verso :8090. Lettura sonda, control-vector e POST
# passano da qui; il layer della sonda vive in UNA costante (LAYER_SONDA).
# riflesso.py tiene la logica e il patto, ma per il trasporto chiama ponte.
# 12/10: tolta la parte delle griglie e del codec (abbandonati il 10/10).
import json
import os
import urllib.error
import urllib.request

import numpy as np

URL = os.environ.get("PONTE_URL", "http://127.0.0.1:8090")

# Il layer della sonda semantica: L29, scelto il 29/07 sui dati
# (misura-layer.json: richiamo di testa, 2° margine, migliore separazione
# emotiva del gruppo, 3 layer dal bordo motorio L32). La sonda legge lo stato
# grezzo dal server e lo TRASPORTA in coordinate della lente di Jacobi (J29):
# la somiglianza si misura lì, mai sull'attivazione piena (decisione 2).
LAYER_SONDA = 29
LENTE_NPY = "/data/memoria-episodica-affettiva/lente-L29.npy"
BASE_LENTE_NPY = "/data/memoria-episodica-affettiva/base-L29-lente.npy"
_lente = {"J": None}


def trasporta(stati):
    """stati grezzi del layer-sonda -> coordinate lente (J29 @ h, per riga)"""
    if _lente["J"] is None:
        _lente["J"] = np.load(LENTE_NPY)
    return np.asarray(stati, np.float32) @ _lente["J"].T


def base_lente():
    """la BASE nel nuovo spazio (da sottrarre prima delle cosine)"""
    return np.load(BASE_LENTE_NPY)


def post(path, payload, timeout=600):
    """POST JSON al server. Ritorna (status, dict); su status HTTP di errore
    NON solleva (torna (codice, {})), così il chiamante decide il ripiego.
    Errori di rete (server giù) sollevano come sempre."""
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def _post(path, payload, timeout=600):
    st, r = post(path, payload, timeout)
    if st != 200:
        raise RuntimeError(f"{path}: HTTP {st}")
    return r


def leggi_sonda(testo, per_token=False, timeout=120, lente=True):
    """Lettura della sonda semantica (/lux-read) al layer LAYER_SONDA.
    Ritorna il dict del server ("mean" o "states" con per_token), con gli
    stati GIA' trasportati in coordinate lente. lente=False = grezzo (solo
    per gli usi legacy L34-raw, es. la salienza finché emovec non e' rifatto)."""
    payload = {"content": testo, "layer": LAYER_SONDA}
    if per_token:
        payload["per_token"] = True
    r = _post("/lux-read", payload, timeout=timeout)
    if lente:
        if "states" in r:
            r["states"] = trasporta(r["states"]).tolist()
        if "mean" in r:
            r["mean"] = trasporta([r["mean"]])[0].tolist()
    return r


# ---- iniezione emotiva a layer nascosti (control vector, modalità relativa)
# emo-cvec-v2.npz (28/07, fase D del registro): 51 emozioni, OGNUNA con la sua
# finestra di 3 layer (misurata: C1-bis/C2), vettori unitari (gradiente per 38,
# contrastivi dai ricordi veri per le 13 del gruppo rosso), centro dose e bordo
# alto misurati. Il dimmer: dose effettiva = centro * fattore; il bordo e' la
# scogliera (parola intrusa / testo rotto) e non si supera.
EMO_NPZ = "/data/memoria-episodica-affettiva/emo-cvec-v2.npz"


def dirs_emozione(nome, fattore=1.0):
    """layers-dict pronto per /control-vector (relative): direzioni della
    emozione alla dose centro * fattore, sulla SUA finestra. None se l'emozione
    non esiste. UNICA implementazione (gradino zero): la usano emozione() qui e
    _applica_flusso() del riflesso (la discesa della fase 2; il vettore del ricordo usa steering.py dall'11/11)."""
    z = np.load(EMO_NPZ)
    nomi = [str(n) for n in z["nomi"]]
    if nome not in nomi:
        return None
    i = nomi.index(nome)
    dose = min(float(z["centro"][i]) * fattore, float(z["bordo"][i]))
    # la dose e' tarata in HF (h += dose*||h||*dir); il server relativo fa
    # h += rms(h)*v e ||h|| = rms(h)*sqrt(d): senza questo fattore arrivava 45x piu'
    # debole (12/10/2026, misurato con research/long-context/2-steering)
    dose *= np.sqrt(z["dirs"].shape[-1])
    return {str(int(l)): (dose * z["dirs"][i, k]).tolist()
            for k, l in enumerate(z["layers"][i])}


def emozione(nome, intensita=1.0):
    """attiva lo stato emotivo sul server: resta finché non si chiama calma()"""
    layers = dirs_emozione(nome, intensita)
    if layers is None:
        raise ValueError(f"emozione sconosciuta: {nome}")
    return _post("/control-vector", {"layers": layers, "relative": True})


def calma():
    """spegne l'iniezione emotiva"""
    return _post("/control-vector", {"clear": True})
