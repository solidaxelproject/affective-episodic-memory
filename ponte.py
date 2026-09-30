# Ponte tra la memoria in spazio input (griglie di sogno, fasci, vettori-ricordo)
# e il server llama-lux dell'agente: compone [testo][vettori][testo] in un'unica
# sequenza e la manda a /completion via embeddings_input.
# Il lookup degli embedding del testo lo fa il server (/input-embeddings):
# qui servono solo stdlib + numpy.
#
# GRADINO ZERO (decisione 3 del 26/07, registro del refactoring): questo file è
# l'UNICA porta client verso :8090. Lettura sonda, control-vector e POST
# passano da qui; il layer della sonda vive in UNA costante (LAYER_SONDA).
# riflesso.py tiene la logica e il patto, ma per il trasporto chiama ponte.
#
# Uso: python3 ponte.py [griglia.npy] ["domanda"]
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

# stesso scheletro del lab (distill35b.py): chat con una "immagine" i cui
# 81 token visivi sono la griglia; vision_start/end restano token veri
PREFISSO = "<|im_start|>user\n<|vision_start|>"
SUFFISSO = ("<|vision_end|>{domanda}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


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
    """la prova del lab: l'agente guarda i vettori e risponde alla domanda"""
    return completa(componi(PREFISSO, vettori,
                            SUFFISSO.format(domanda=domanda)), **kw)


# ---- FASE 3 (piano canale percettivo): ricomposizione chat -> embeddings_input.
# Rende i messaggi nel template del modello, li embedda (/input-embeddings) e
# splica le 81 righe della griglia come blocco visivo in CODA (append-only, mai
# in mezzo), prima della coda assistant. Funzione a sé: l'aggancio gated è FASE 4.
_CODA_ASS = "<|im_start|>assistant\n"


def _rendi_chat(messages):
    """messaggi OpenAI -> stringa nel template im_start/im_end del modello."""
    s = ""
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            s += f"<|im_start|>{m.get('role', 'user')}\n{c}<|im_end|>\n"
    return s + _CODA_ASS


def componi_prompt_embeddings(messages, griglia=None):
    """righe embedding pronte per /completion. Senza griglia: == embedding del
    prompt renderizzato (nessuna deriva). Con griglia: le righe visive spliciate
    in coda all'ultimo turno, avvolte in vision_start/end, prima dell'assistant."""
    testa = _rendi_chat(messages)
    if griglia is None:
        return componi(testa)
    pre = testa[:-len(_CODA_ASS)]                      # tutto tranne la coda assistant
    return componi(pre + "<|vision_start|>", griglia, "<|vision_end|>" + _CODA_ASS)


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
    inietta_emozione() del riflesso (che sopra ci mette patto e assuefazione)."""
    z = np.load(EMO_NPZ)
    nomi = [str(n) for n in z["nomi"]]
    if nome not in nomi:
        return None
    i = nomi.index(nome)
    dose = min(float(z["centro"][i]) * fattore, float(z["bordo"][i]))
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


def inietta_layer(layers_dict, relative=False, scale=1.0):
    """iniezione libera: {layer: vettore 2048} su layer arbitrari"""
    return _post("/control-vector",
                 {"layers": {str(k): np.asarray(v, dtype=np.float32).tolist()
                             for k, v in layers_dict.items()},
                  "relative": relative, "scale": scale})


# ---- richiamo VISIVO: l'agente rivede il ricordo come scena (vision wormhole).
# La griglia distillata dello store viene re-iniettata via embeddings_input.
# GRIGLIE_DIR sovrascrivibile via env per i collaudi (store finto, agente intatto).
STORE_GRIGLIE = os.environ.get("GRIGLIE_DIR", "/data/workspace/memoria/griglie")


def ha_griglia(node_id):
    return os.path.exists(f"{STORE_GRIGLIE}/{node_id}.npy")


# la domanda DEVE restare quella di training della distillazione (DOMANDA_TRAIN
# in distilla-ricordo.py): fuori da quella la griglia confabula (visto il 12/07)
def ricorda_visivo(node_id, domanda="Questo mi ricorda...", **kw):
    """richiama un ricordo come IMMAGINE: carica la sua griglia e la inietta"""
    g = np.load(f"{STORE_GRIGLIE}/{node_id}.npy")
    assert g.ndim == 2 and g.shape[1] == 2048, g.shape
    return chiedi_su_vettori(g, domanda, **kw)


# ---- INTENSITÀ DINAMICA (20/07): quanto "accendere" un ricordo dipende
# da quanto è congruente col contesto. Sweep del 20/07: sotto ~0.25 il ricordo è
# assente, sopra ~0.35 recita a pappagallo ignorando la domanda; la "presenza"
# (ricordo sentito, rielaborato, non recitato) vive in una banda stretta. Si
# fissa a [0.280, 0.299] e la modula con la cosine del richiamo: più il
# momento risuona col ricordo, più il ricordo è presente.
GRAY_BASE = f"{STORE_GRIGLIE}/.gray-base.npy"   # griglia dell'immagine neutra (α=0)
BANDA_ALPHA = (0.280, 0.299)


def alpha_contesto(cos, soglia=0.71):
    """cos del richiamo (congruenza ricordo<->contesto) -> α nella banda.
    A soglia = minimo presente (0.280); a cos=1 = massimo (0.299). Lineare,
    clampata: sotto soglia non ci sarebbe richiamo, quindi α resta al minimo.
    28/07: soglia = quella di affioramento del nuovo spazio L29-lente (0.71,
    sonde-soglie.py); la BANDA_ALPHA stessa va rifatta con lo sweep >=10
    ricordi (decisione 10 del registro)."""
    lo, hi = BANDA_ALPHA
    f = (cos - soglia) / (1.0 - soglia)
    return lo + (hi - lo) * min(max(f, 0.0), 1.0)


def griglia_a_intensita(memory_grid, alpha):
    """fonde la griglia del ricordo col base grigio: (1-α)*grigio + α*ricordo.
    α=0 -> nessun ricordo, α=1 -> recita piena. Si usa α da alpha_contesto()."""
    gray = np.load(GRAY_BASE).astype(np.float32).reshape(np.asarray(memory_grid).shape)
    return ((1 - alpha) * gray + alpha * np.asarray(memory_grid, np.float32)).astype(np.float32)


if __name__ == "__main__" and os.environ.get("PONTE_SELFCHECK"):
    # self-check della mappa intensità (ponytail: la logica non banale lascia una prova)
    assert abs(alpha_contesto(0.71) - 0.280) < 1e-9        # a soglia: minimo
    assert abs(alpha_contesto(1.0) - 0.299) < 1e-9         # identico: massimo
    assert alpha_contesto(0.20) == 0.280                   # sotto soglia: clamp al minimo
    assert 0.280 < alpha_contesto(0.85) < 0.299            # a metà: dentro la banda
    lo, hi = BANDA_ALPHA
    assert all(lo <= alpha_contesto(c) <= hi for c in (0.0, 0.5, 0.99, 1.0))
    print("ponte self-check intensità OK")
    raise SystemExit(0)   # non far partire la demo che interroga :8090


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
def ricorda_lux(query, via="emotiva", domanda="Questo mi ricorda...",
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


# ---- FASE 1 (piano canale percettivo): richiamo con INTENSITÀ dinamica.
# Come ricorda_lux, ma la griglia scelta viene FUSA col grigio a
# alpha_contesto(cos) prima dell'iniezione: "presenza" tarata sulla congruenza
# col momento, non recita piena. Pura addizione, non tocca le funzioni esistenti.
def ricorda_percettivo(query, via="emotiva", domanda="Questo mi ricorda...",
                       k=3, tocca=True, **kw):
    """Richiama (Lux), prende il cos del match migliore, sceglie la griglia
    (distillata se c'è, altrimenti dal codec), la fonde a alpha_contesto(cos) e
    la inietta. Ritorna (scena, hit, alpha). tocca=False per il collaudo: usa
    confronta() invece di richiama(), zero effetti su Lux."""
    import sys
    sys.path.insert(0, "/data/memoria-episodica-affettiva")
    from lux import Lux
    g = Lux()
    top = (g.richiama if tocca else g.confronta)(query, via=via, k=k)
    if not top:
        return None, None, None
    hit = top[0]
    alpha = alpha_contesto(hit["sim"])
    if hit["nodo_id"] >= 0 and ha_griglia(hit["nodo_id"]):
        grid = np.load(f"{STORE_GRIGLIE}/{hit['nodo_id']}.npy")
    elif os.path.exists(CODEC):
        grid = griglia_da_traccia(g.tracce[hit["neurone"]])
    else:
        grid = None
    if grid is None:
        return None, hit, alpha
    fusa = griglia_a_intensita(grid, alpha)
    return chiedi_su_vettori(fusa, domanda, **kw), hit, alpha


if __name__ == "__main__":
    import sys
    npy = sys.argv[1] if len(sys.argv) > 1 else "/data/memoria-episodica-affettiva/sogno-gatto.npy"
    domanda = sys.argv[2] if len(sys.argv) > 2 else "Cosa vedi in questa immagine?"
    g = np.load(npy)
    assert g.ndim == 2 and g.shape[1] == 2048, g.shape
    print(chiedi_su_vettori(g, domanda).strip())
