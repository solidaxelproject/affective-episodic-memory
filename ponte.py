# Ponte tra la memoria in spazio input (griglie di sogno, fasci, vettori-ricordo)
# e il server llama-lux di Agente: compone [testo][vettori][testo] in un'unica
# sequenza e la manda a /completion via embeddings_input.
# Il lookup degli embedding del testo lo fa il server (/input-embeddings):
# qui servono solo stdlib + numpy.
#
# Uso: python3 ponte.py [griglia.npy] ["domanda"]
import json
import os
import urllib.request

import numpy as np

URL = os.environ.get("PONTE_URL", "http://127.0.0.1:8090")

# stesso scheletro del lab (distill35b.py): chat con una "immagine" i cui
# 81 token visivi sono la griglia; vision_start/end restano token veri
PREFISSO = "<|im_start|>user\n<|vision_start|>"
SUFFISSO = ("<|vision_end|>{domanda}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def _post(path, payload, timeout=600):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def embed_testo(testo):
    """righe embedding del testo, lookup fatto dal server dal GGUF"""
    return _post("/input-embeddings", {"content": testo})[0]["embedding"]


def componi(*parti):
    """concatena stringhe (embeddate) e matrici di righe in un'unica sequenza"""
    rows = []
    for p in parti:
        if isinstance(p, str):
            rows += embed_testo(p)
        else:
            rows += np.asarray(p, dtype=np.float32).tolist()
    return rows


def completa(rows, n_predict=80, temperature=0.0, **kw):
    payload = {"embeddings_input": rows, "n_predict": n_predict,
               "temperature": temperature}
    payload.update(kw)
    return _post("/completion", payload)["content"]


def chiedi_su_vettori(vettori, domanda, **kw):
    """la prova del lab: Agente guarda i vettori e risponde alla domanda"""
    return completa(componi(PREFISSO, vettori,
                            SUFFISSO.format(domanda=domanda)), **kw)


# ---- iniezione emotiva a layer nascosti (control vector, modalità relativa)
# emo-cvec.npz: 51 emozioni Plutchik, v_e normalizzati * sqrt(2048), finestra
# L26-28 (indici modulo, 1:1 col lab), alpha iso-effetto da alpha-calib-L26-28
EMO_NPZ = "/data/memoria-episodica-affettiva/emo-cvec.npz"


def emozione(nome, intensita=1.0):
    """attiva lo stato emotivo sul server: resta finché non si chiama calma()"""
    z = np.load(EMO_NPZ)
    nomi = list(z["nomi"])
    i = nomi.index(nome)
    alpha = float(z["alpha"][i]) * intensita
    layers = {str(int(l)): (alpha * z["dirs"][i, k]).tolist()
              for k, l in enumerate(z["layer"])}
    return _post("/control-vector", {"layers": layers, "relative": True})


def calma():
    """spegne l'iniezione emotiva"""
    return _post("/control-vector", {"clear": True})


def inietta_layer(layers_dict, relative=False, scale=1.0):
    """iniezione libera: {layer: vettore 2048} su layer arbitrari"""
    return _post("/control-vector",
                 {"layers": {str(k): np.asarray(v, dtype=np.float32).tolist()
                             for k, v in layers_dict.items()},
                  "relative": relative, "scale": scale})


# ---- richiamo VISIVO: Agente rivede il ricordo come scena (vision wormhole).
# La griglia distillata dello store viene re-iniettata via embeddings_input.
# GRIGLIE_DIR sovrascrivibile via env per i collaudi (store finto, Agente intatta).
STORE_GRIGLIE = os.environ.get("GRIGLIE_DIR", "/data/workspace/memoria/griglie")


def ha_griglia(node_id):
    return os.path.exists(f"{STORE_GRIGLIE}/{node_id}.npy")


# la domanda DEVE restare quella di training della distillazione (DOMANDA_TRAIN
# in distilla-ricordo.py): fuori da quella la griglia confabula (visto il 12/07)
def ricorda_visivo(node_id, domanda="Descrivi cosa vedi.", **kw):
    """richiama un ricordo come IMMAGINE: carica la sua griglia e la inietta"""
    g = np.load(f"{STORE_GRIGLIE}/{node_id}.npy")
    assert g.ndim == 2 and g.shape[1] == 2048, g.shape
    return chiedi_su_vettori(g, domanda, **kw)


# ---- codec Lux->token universali (wormhole ammortizzato, addestrato da
# codec-lux.py): traccia 128 -> griglia 81x2048, due matmul su CPU.
CODEC = "/data/workspace/memoria/codec-lux.npz"


def griglia_da_traccia(traccia):
    z = np.load(CODEC)
    t = np.asarray(traccia, np.float32)
    if z["W1"].shape[0] != t.shape[0]:
        return None  # codec addestrato su tracce di altra dimensione: retrain
    h = np.tanh(t @ z["W1"] + z["b1"])
    U = (h @ z["W2"] + z["b2"]).reshape(int(z["K"]), 2048)
    return z["base"] + float(z["gate"]) * (z["Wpos"] @ U)


# ---- anello 2->4 del loop maturo: Lux associa, la scena torna nel forward.
# query = firma 51-dim (via emotiva) o stato 2048 (via semantica).
def ricorda_lux(query, via="emotiva", domanda="Descrivi cosa vedi.",
                k=3, **kw):
    """Lux.richiama -> griglia distillata del nodo se c'è, altrimenti griglia
    dal codec sulla traccia del neurone. Ritorna (scena, hit) o (None, hit)."""
    import sys
    sys.path.insert(0, "/data/memoria-episodica-affettiva")
    from lux import Lux
    g = Lux()
    top = g.richiama(query, via=via, k=k)
    for h in top:
        if h["nodo_id"] >= 0 and ha_griglia(h["nodo_id"]):
            return ricorda_visivo(h["nodo_id"], domanda, **kw), h
    if top and os.path.exists(CODEC):
        gr = griglia_da_traccia(g.tracce[top[0]["neurone"]])
        if gr is not None:
            return chiedi_su_vettori(gr, domanda, **kw), top[0]
    return None, (top[0] if top else None)


if __name__ == "__main__":
    import sys
    npy = sys.argv[1] if len(sys.argv) > 1 else "/data/memoria-episodica-affettiva/sogno-gatto.npy"
    domanda = sys.argv[2] if len(sys.argv) > 2 else "Cosa vedi in questa immagine?"
    g = np.load(npy)
    assert g.ndim == 2 and g.shape[1] == 2048, g.shape
    print(chiedi_su_vettori(g, domanda).strip())
