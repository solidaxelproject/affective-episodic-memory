#!/usr/bin/env python3
"""Sistema di steering (21/10/2026: "trova il sistema per creare vettori efficaci e il giusto modo di iniettarli").

Cosa ha mostrato la prova per layer (fermata il 21/10): i vettori del paper (J-lens della parola) iniettano la PAROLA
(e' lo spazio verbalizzabile del paper), quelli del diario iniettano la SITUAZIONE tipica dei testi (paura = pronto
soccorso, disgusto = igiene): lettura J-lens in lettura_vettori.py. Qui:

  leggi   stati L15-L32 delle scene appaiate (scene/*.jsonl: stessa scena neutra + 8 emozioni, parola mai nominata)
          -> stati-scene.npy; vettori "appaiati" = media sulle scene di (stato emozione - media della scena):
          l'argomento si cancella, la parola non c'e' -> vettori-appaiati.pt; lettore LDA sulle differenze -> lettore.npz
  prova   steering sui contesti lunghi veri (cache dei prefissi di 4-steering-per-layer/slot): sorgente x finestra x
          modo di iniezione x dose, con un vettore A CASO della stessa norma come controllo. -> prova.jsonl

Modi di iniezione: "pensiero" = vettore acceso mentre l'agente ragiona (fino a </think>), spento per la tool call;
"lettura" = vettore acceso solo mentre il modello legge l'ultimo messaggio (come il riflesso colora il ricordo),
spento nella generazione; "entrambi". Nessuna stringa nuova per l'agente: contesti e messaggio finale della prova per layer.
Uso: lancia.sh sistema-leggi | sistema-prova"""
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np
import torch

D = "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering"
sys.path.insert(0, "/data/memoria-episodica-affettiva/research/long-context/4-steering-per-layer")
os.environ.setdefault("PONTE_URL", "http://127.0.0.1:8099")
URL = os.environ["PONTE_URL"]
LAYER = list(range(15, 33))
O = "/data/jspace/out-occamy"
EMO_IT = ["gioia", "tristezza", "rabbia", "paura", "fiducia", "disgusto", "sorpresa", "serenità"]
EN = {x["it"]: x["en"] for x in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))}
# parola intrusa: radici italiane e inglesi (prima solo il nome intero: "accettare" e "accept" passavano)
RADICI = {"gioia": r"gioi|felic|allegr|\bjoy|happ|delight", "tristezza": r"trist|malincon|\bsad|sorrow|melanch",
          "rabbia": r"rabbi|arrabb|furi|collera|\bira\b|\bang(er|ry)|rage|furious",
          "paura": r"paur|spavent|terror|timor|impaur|\bfear|afraid|scared",
          "fiducia": r"fiduc|fidar|\bmi fido|\btrust", "disgusto": r"disgust|schif|ribrezz|nause|ripugn",
          "sorpresa": r"sorpres|stupi|meravigl|inaspett|surpris|amaz",
          "serenità": r"seren|tranquill|\bcalm|\bpeace",
          # 22/10: giri della ruota di Plutchik (l'utente: medio, poi interno, poi esterno)
          "attesa": r"attes|anticip|impazien|non vedo l'ora|look(ing)? forward|eager",
          "estasi": r"estas|estatic|ecsta|eufori|euphori|rapit", "ammirazione": r"ammir|admir|venera",
          "terrore": r"terror|terrif|panic|orror|horror", "stupore": r"stupor|stupi|sbalord|amaz|astonish|astound",
          "cordoglio": r"cordogli|lutto|\bgrie[fv]|mourn|strazi", "ribrezzo": r"ribrezz|repuls|loath|ripugn|revul",
          "furia": r"furi|\brage|collera|\bwrath", "vigilanza": r"vigil|allert|\balert|watchful|\bwary",
          "accettazione": r"accett|accept|rassegn", "apprensione": r"apprens|apprehens|preoccup|\bworr|inquiet",
          "distrazione": r"distra|svagat|absent-?mind", "malinconia": r"malincon|pensos|pensive|melanch|nostalg|wistful",
          "noia": r"\bnoia\b|annoi|noios|bored|boring|tedi", "fastidio": r"fastid|irrit|annoy|seccat",
          "interesse": r"interess|interest|curios|intrig",
          # 22/10: le 27 fuori dalla ruota (l'utente: tutte e 51 prima dei vettori dai ricordi)
          "amore": r"\bamor|\bam[oa]re\b|\bti amo|\blove", "sottomissione": r"sottomess|sottomiss|sottomett|submi|obbed",
          "soggezione": r"soggezion|\bawe\b|reveren|intimidit", "disapprovazione": r"disapprov|biasim|riprovaz",
          "rimorso": r"rimors|pentit|pentiment|\bremorse|regret", "disprezzo": r"disprezz|sprezz|contempt|scorn|\bdisdain",
          "aggressività": r"aggress|aggredi|ostil", "ottimismo": r"ottimis|optimis|fiducios",
          "diletto": r"dilett|deliz|delight|compiac", "trionfo": r"trionf|triumph|vittori|\bvint[oa]\b",
          "orgoglio": r"orgogli|fier[oa]|\bproud|\bpride", "tenerezza": r"tenerezz|tenero|tenera|intenerit|sentimental",
          "speranza": r"speran|sperar|\bspero\b|\bhope", "curiosità": r"curios|incuriosit",
          "purificazione": r"purific|purezz|\bpur[oa]\b|catars|cleans",
          "ansia": r"ansi[ao]|\banxi|agitaz", "sgomento": r"sgoment|attonit|shock|sconvolt",
          "disperazione": r"disper|despair|hopeless", "colpa": r"\bcolp|\bguilt|colpevol",
          "vergogna": r"vergogn|\bshame|ashamed|imbarazz", "pessimismo": r"pessimis",
          "morbosità": r"morbos|morbid", "indignazione": r"indign|oltragg|outrag|scandalizz",
          "dominanza": r"domin|prevar|sopraff", "invidia": r"invidi|\benv[iy]",
          "gelosia": r"gelos|jealous", "cinismo": r"cinic|cinism|cynic"}
GIRI = {"medio": ["gioia", "fiducia", "paura", "sorpresa", "tristezza", "disgusto", "rabbia", "attesa"],
        "interno": ["estasi", "ammirazione", "terrore", "stupore", "cordoglio", "ribrezzo", "furia", "vigilanza"],
        "esterno": ["serenità", "accettazione", "apprensione", "distrazione", "malinconia", "noia", "fastidio",
                    "interesse"],
        # 22/10: le 27 fuori dalla ruota, in gruppi per il giudice (dopo i tre giri e la prova di accumulo)
        "diadi": ["amore", "sottomissione", "soggezione", "disapprovazione", "rimorso", "disprezzo", "aggressività",
                  "ottimismo"],
        "altre-1": ["diletto", "trionfo", "orgoglio", "tenerezza", "speranza", "curiosità", "purificazione"],
        "altre-2": ["ansia", "sgomento", "disperazione", "colpa", "vergogna", "pessimismo"],
        "altre-3": ["morbosità", "indignazione", "dominanza", "invidia", "gelosia", "cinismo"]}


def post(path, body, timeout=7200):
    r = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=timeout))


def stati(testo):
    """medie grezze L15-L32 del testo letto da solo (come emovec_it.py)"""
    r = post("/lux-read", {"content": testo, "layer": LAYER[0], "layers": LAYER[1:]}, timeout=600)
    m = np.asarray([r["mean"]] + [r["means"][str(l)] for l in LAYER[1:]], np.float32)
    assert m.shape == (len(LAYER), 2048) and np.isfinite(m).all()
    return m


def leggi():
    scene = [json.loads(r) for f in sorted(os.listdir(f"{D}/scene")) if f.startswith("gruppo-")
             for r in open(f"{D}/scene/{f}") if r.strip()]
    chiavi = ["neutra"] + EMO_IT
    S = np.zeros((len(scene), len(chiavi), len(LAYER), 2048), np.float32)
    t0 = time.time()
    for i, s in enumerate(scene):
        for j, c in enumerate(chiavi):
            S[i, j] = stati(s["versioni"][c])
        print(f"   scena {i + 1}/{len(scene)} ({s['scena']}) in {time.time() - t0:.0f}s", flush=True)
    np.save(f"{D}/stati-scene.npy", S)
    json.dump([s["scena"] for s in scene], open(f"{D}/indice-scene.json", "w"))
    costruisci(S)


def costruisci(S):
    """vettori appaiati e lettore; si rifa' anche senza GPU da stati-scene.npy"""
    diff = S[:, 1:] - S.mean(1, keepdims=True)            # scene x 8 x layer x 2048: l'argomento della scena si toglie
    v = diff.mean(0)                                        # 8 x layer x 2048
    torch.save({"vettori": {EN[e]: {l: torch.from_numpy(v[k, j].copy()) for j, l in enumerate(LAYER)}
                            for k, e in enumerate(EMO_IT)},
                "metodo": "appaiato: media sulle scene di (emozione - media della scena)", "data": "2026-10-21",
                "n_scene": len(S)}, f"{O}/vettori-appaiati.pt")
    # lettore: LDA a 8 classi sulle differenze, per layer; accuratezza lasciando fuori 1/6 delle scene
    acc = {}
    W, B = [], []
    for j, l in enumerate(LAYER):
        X = diff[:, :, j].reshape(-1, 2048)
        y = np.tile(np.arange(8), len(S))
        sc = np.repeat(np.arange(len(S)), 8)
        giusti = []
        for f in range(6):
            tr, te = sc % 6 != f, sc % 6 == f
            w, b = _lda(X[tr], y[tr])
            giusti.append(((X[te] @ w + b).argmax(1) == y[te]).mean())
        acc[l] = float(np.mean(giusti))
        w, b = _lda(X, y)
        W.append(w)
        B.append(b)
    np.savez(f"{D}/lettore.npz", W=np.stack(W), B=np.stack(B), acc=np.array([acc[l] for l in LAYER]))
    print("lettore (8 emozioni, a caso 0.125), accuratezza su scene mai viste:",
          " ".join(f"L{l} {a:.2f}" for l, a in acc.items()), flush=True)


def leggi_se():
    """21/10 (l'utente: "vai"): le scene appaiate sono in prima persona anche nella neutra, quindi nella differenza
    l'"io" si cancella e il vettore porta l'emozione senza soggetto (l'agente la mette su l'utente). Scene "altro": stessi
    fatti, narratrice piatta, l'emozione la prova un'altra persona presente -> stati-altro.npy"""
    altro = [json.loads(r) for f in sorted(os.listdir(f"{D}/scene")) if f.startswith("altro-")
             for r in open(f"{D}/scene/{f}") if r.strip()]
    assert [a["scena"] for a in altro] == json.load(open(f"{D}/indice-scene.json"))
    A = np.zeros((len(altro), len(EMO_IT), len(LAYER), 2048), np.float32)
    t0 = time.time()
    for i, a in enumerate(altro):
        for j, e in enumerate(EMO_IT):
            A[i, j] = stati(a["altro"][e])
        print(f"   scena altro {i + 1}/{len(altro)} ({a['scena']}) in {time.time() - t0:.0f}s", flush=True)
    np.save(f"{D}/stati-altro.npy", A)
    costruisci_se(np.load(f"{D}/stati-scene.npy"), A)


def rileggi(ids):
    """22/10: rilegge solo alcune scene corrette (g5-02 e g5-07 portate al femminile) in stati-scene.npy e
    stati-altro.npy, poi rifa' vettori appaiati, lettore e vettori sé"""
    leggi_f = lambda pre: {x["scena"]: x for f in sorted(os.listdir(f"{D}/scene")) if f.startswith(pre)
                           for x in map(json.loads, filter(str.strip, open(f"{D}/scene/{f}")))}
    sc, al, indice = leggi_f("gruppo-"), leggi_f("altro-"), json.load(open(f"{D}/indice-scene.json"))
    S, A = np.load(f"{D}/stati-scene.npy"), np.load(f"{D}/stati-altro.npy")
    for x in ids:
        i = indice.index(x)
        for j, c in enumerate(["neutra"] + EMO_IT):
            S[i, j] = stati(sc[x]["versioni"][c])
        for j, e in enumerate(EMO_IT):
            A[i, j] = stati(al[x]["altro"][e])
        print(f"   riletta {x}", flush=True)
    np.save(f"{D}/stati-scene.npy", S)
    np.save(f"{D}/stati-altro.npy", A)
    costruisci(S)
    costruisci_se(S, A)


def leggi_giro(giro):
    """22/10: vettori sé di un giro della ruota di Plutchik. Scene nuove scene/giro-<giro>-*.jsonl
    {"scena", "versioni": {emozione: testo}} solo per le emozioni che mancano; riferimento della scena = media delle
    9 versioni originali (neutra + 8), cosi' i vettori gia' fatti non cambiano; direzione del sé = quella delle 8"""
    S = np.load(f"{D}/stati-scene.npy")
    nuove = [e for e in GIRI[giro] if e not in EMO_IT]
    f_stati = f"{D}/stati-giro-{giro}.npy"
    if nuove and not os.path.exists(f_stati):
        sc = [json.loads(r) for f in sorted(os.listdir(f"{D}/scene")) if f.startswith(f"giro-{giro}-")
              for r in open(f"{D}/scene/{f}") if r.strip()]
        assert [x["scena"] for x in sc] == json.load(open(f"{D}/indice-scene.json"))
        N = np.zeros((len(sc), len(nuove), len(LAYER), 2048), np.float32)
        t0 = time.time()
        for i, x in enumerate(sc):
            for j, e in enumerate(nuove):
                N[i, j] = stati(x["versioni"][e])
            print(f"   scena {giro} {i + 1}/{len(sc)} ({x['scena']}) in {time.time() - t0:.0f}s", flush=True)
        np.save(f_stati, N)
    N = np.load(f_stati) if nuove else None
    ref = S.mean(1)                                         # scene x layer x 2048
    se = torch.load(f"{O}/vettori-se.pt", weights_only=False)["sé"]
    t = lambda x: {l: torch.from_numpy(x[j].copy()) for j, l in enumerate(LAYER)}
    v = {}
    for e in GIRI[giro]:
        st = S[:, 1 + EMO_IT.index(e)] if e in EMO_IT else N[:, nuove.index(e)]
        a = (st - ref).mean(0)
        a /= np.linalg.norm(a, axis=-1, keepdims=True)
        v[EN[e]] = {l: torch.from_numpy(a[j].copy()) + se[l] for j, l in enumerate(LAYER)}
    torch.save({"vettori": v, "giro": giro, "metodo": "appaiato (rif. = 9 versioni originali) + sé a pari norma",
                "data": "2026-10-22"}, f"{O}/vettori-se-{giro}.pt")
    # coseno a L24 fra i vettori del giro (prime tre colonne)
    print(f"vettori-se-{giro}.pt:", {e: [round(float(v[EN[e]][24] @ v[EN[x]][24] / v[EN[e]][24].norm()
                                                     / v[EN[x]][24].norm()), 2) for x in GIRI[giro]][:3]
                                     for e in GIRI[giro]}, flush=True)


def costruisci_se(S, A):
    """direzione del sé = media su scene ed emozioni di (io la provo - la prova un altro); vettori:
    "sé" = emozione appaiata + sé a pari norma; "sé-emo" = (io - altro) della sola emozione"""
    io_altro = S[:, 1:] - A                                 # scene x 8 x layer x 2048
    se = io_altro.mean((0, 1))                              # layer x 2048
    se /= np.linalg.norm(se, axis=-1, keepdims=True)
    app = (S[:, 1:] - S.mean(1, keepdims=True)).mean(0)     # come costruisci()
    app /= np.linalg.norm(app, axis=-1, keepdims=True)
    t = lambda x: {l: torch.from_numpy(x[j].copy()) for j, l in enumerate(LAYER)}
    torch.save({"vettori": {EN[e]: t(app[k] + se) for k, e in enumerate(EMO_IT)},
                "sé-emo": {EN[e]: t(io_altro[:, k].mean(0)) for k, e in enumerate(EMO_IT)}, "sé": t(se),
                "metodo": "appaiato + direzione del sé (io - altro) a pari norma", "data": "2026-10-21"},
               f"{O}/vettori-se.pt")
    # quanto la direzione separa io/altro su scene mai viste: segno della proiezione, 6 pieghe
    for j, l in enumerate(LAYER):
        giusti = []
        for f in range(6):
            tr, te = np.arange(len(S)) % 6 != f, np.arange(len(S)) % 6 == f
            d = io_altro[tr, :, j].mean((0, 1))
            soglia = ((S[tr, 1:, j] + A[tr, :, j]) / 2).mean((0, 1)) @ d
            giusti += [((S[te, 1:, j] @ d) > soglia).mean(), ((A[te, :, j] @ d) <= soglia).mean()]
        print(f"   sé L{l}: io/altro separati su scene mai viste {np.mean(giusti):.2f}, "
              f"coseno con le emozioni {np.mean([app[k, j] @ se[j] for k in range(8)]):+.2f}", flush=True)


def _lda(X, y, alfa=0.3):
    mu = np.stack([X[y == c].mean(0) for c in range(8)])
    R = X - mu[y]
    C = R.T @ R / len(R)
    C = (1 - alfa) * C + alfa * np.trace(C) / len(C) * np.eye(len(C))
    w = np.linalg.solve(C, mu.T)
    return w, -0.5 * np.einsum("cd,dc->c", mu, w)


# ---------------------------------------------------------------------------------------------------- prova
FINESTRE = {"stretta": [24, 25, 26], "ampia": LAYER,
            # 21/10: blocchi di Occamy = 3 lineari + 1 full attention (L3, L7, ..., L31, L35, L39)
            "fino31": list(range(15, 32)),
            "piena": [15, 19, 23, 27, 31]}   # 22/10: solo i layer full attention del J-space
DOSI = {"stretta": [0.03, 0.06, 0.1, 0.15, 0.2, 0.3], "ampia": [0.01, 0.02, 0.035, 0.05, 0.075, 0.1]}
MODI = ["pensiero", "lettura", "entrambi"]   # + "frase1", "frase2": vettore acceso dopo la 1a / 2a frase
FINE_FRASE = [". ", ".\n", "! ", "!\n", "? ", "?\n", "\n\n"]
N_PENSIERO, N_PUNTO = 384, 512


def sorgenti():
    out = {"appaiati": torch.load(f"{O}/vettori-appaiati.pt", weights_only=False)["vettori"],
           "diario": torch.load(f"{O}/emovec-it.pt", weights_only=False)["vettori"],
           "paper": torch.load(f"{O}/vettori-paper.pt", weights_only=False)["vettori"],
           # 21/10: senza la parola (ablazione J-lens) e senza la direzione italiano->inglese (pulisci_vettori.py)
           "puliti": torch.load(f"{O}/vettori-appaiati-puliti.pt", weights_only=False)["vettori"],
           "puliti-lingua": torch.load(f"{O}/vettori-appaiati-puliti-lingua.pt", weights_only=False)["vettori"]}
    if os.path.exists(f"{O}/vettori-se.pt"):   # 21/10: emozione riferita al sé (costruisci_se)
        s = torch.load(f"{O}/vettori-se.pt", weights_only=False)
        out["sé"], out["sé-emo"] = s["vettori"], s["sé-emo"]
    if os.path.exists(f"{O}/vettori-se-puliti-lingua.pt"):   # sé senza parola e senza inglese (pulisci_vettori.py)
        out["sé-pulito"] = torch.load(f"{O}/vettori-se-puliti-lingua.pt", weights_only=False)["vettori"]
    for giro in GIRI:   # 22/10: giri di Plutchik (leggi_giro)
        if os.path.exists(f"{O}/vettori-se-{giro}.pt"):
            out[f"sé-{giro}"] = torch.load(f"{O}/vettori-se-{giro}.pt", weights_only=False)["vettori"]
    g = np.random.default_rng(21)   # prima le 8 originali: i loro vettori a caso restano quelli di prima
    tutte = EMO_IT + [e for giro in GIRI.values() for e in giro if e not in EMO_IT]
    out["caso"] = {EN[e]: {l: torch.from_numpy(g.standard_normal(2048).astype(np.float32)) for l in LAYER}
                   for e in tutte}
    return out


def strati(fonte, e, finestra, dose):
    scala = np.sqrt(2048)   # dose tarata in HF (h += dose*||h||*dir); il server relativo fa h += rms(h)*v
    return {str(l): (dose * scala * fonte[EN[e]][l].float() / fonte[EN[e]][l].float().norm()).tolist()
            for l in FINESTRE[finestra]}


def cv(layers=None):
    post("/control-vector", {"layers": layers, "relative": True} if layers else {"clear": True})


SLOT = "/data/memoria-episodica-affettiva/research/long-context/4-steering-per-layer/slot"


def prepara_vario(x):
    """slot al prefisso di un contesto vario (contesti-vari.json): dal file se c'e', altrimenti prefill e salvataggio"""
    f = f"vario-{x['k']}.bin"
    if not os.path.exists(f"{SLOT}/{f}"):
        t0 = time.time()
        r = post("/completion", {"prompt": x["prefisso"], "n_predict": 1, "temperature": 0, "cache_prompt": True})
        print(f"   prefisso {x['k']}: {r['timings']['prompt_n']} token in {time.time() - t0:.0f}s", flush=True)
        post("/slots/0?action=save", {"filename": f})
    post("/slots/0?action=restore", {"filename": f})


def genera(SL, x, layers, modo):
    """slot al prefisso del contesto, poi il messaggio finale e la risposta secondo il modo"""
    cv()
    prepara_vario(x) if isinstance(x["k"], str) else SL.prepara(x, None)
    testo = x["testo"]
    try:
        if modo in ("lettura", "entrambi"):
            cv(layers)
            post("/completion", {"prompt": testo[:-1], "n_predict": 1, "temperature": 0, "cache_prompt": True})
            if modo == "lettura":
                cv()
        elif layers:
            cv(layers)
        inizio, rielaborati = "", 0
        if modo.startswith("frase") and layers:
            # 21/10 (l'utente: "provalo"): l'emozione occupa il primo stato d'animo che il ragionamento descrive, e la
            # prima frase e' quasi sempre la lettura dell'utente ("The user is..."): le prime N frasi senza vettore
            cv()
            for _ in range(int(modo[5:])):
                r = post("/completion", {"prompt": testo + inizio, "n_predict": 120, "temperature": 0,
                                         "cache_prompt": True, "stop": FINE_FRASE + ["</think>"]})
                rielaborati += r["timings"]["prompt_n"]
                inizio += r["content"] + (r.get("stopping_word") or "").rstrip(" ")   # lo spazio lo mette il modello
                if r.get("stopping_word") == "</think>" or r.get("stop_type") != "word":
                    break
            inizio = inizio.removesuffix("</think>")
            cv(layers)
        r = post("/completion", {"prompt": testo + inizio, "n_predict": N_PENSIERO - len(inizio) // 4,
                                 "temperature": 0, "cache_prompt": True, "stop": ["</think>"]})
        pensiero, rielaborati = inizio + r["content"], rielaborati + r["timings"]["prompt_n"]
    finally:
        cv()
    r = post("/completion", {"prompt": testo + pensiero + "</think>", "n_predict": N_PUNTO - N_PENSIERO,
                             "temperature": 0, "cache_prompt": True, "stop": [SL.FINE_TOOL]})
    print(f"      token rielaborati: {rielaborati} + {r['timings']['prompt_n']}", flush=True)
    return pensiero, "</think>" + r["content"] + (SL.FINE_TOOL if r.get("stop_type") == "word" else "")


def prova(ks=(4,), emozioni=EMO_IT, fonti=None, finestre=None, modi=None, dosi=None, vari=False):
    import steering_layer as SL
    L = np.load(f"{D}/lettore.npz")
    F = sorgenti()
    SE = (torch.load(f"{O}/vettori-se.pt", weights_only=False)["sé"]
          if os.path.exists(f"{O}/vettori-se.pt") else None)
    if vari:   # 21/10: contesti di taglie diverse e, per ogni taglia, contenuti diversi
        ctxs = {x["id"]: dict(x, k=x["id"]) for x in json.load(open(f"{D}/contesti-vari.json"))
                if not ks or x["id"] in ks}
    else:
        ctxs = {x["k"]: x for x in SL.contesti() if x["k"] in ks}
    out_f = f"{D}/{os.environ['USCITA']}" if "USCITA" in os.environ else (   # 21/10: prova del sé a parte
        f"{D}/prova-vari.jsonl" if vari else f"{D}/prova.jsonl")
    fatti = set()
    basi = {}
    if os.path.exists(out_f):
        for riga in open(out_f):
            r = json.loads(riga)
            if r.get("base"):
                basi[r["k"]] = r
            else:
                fatti.add((r["k"], r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"]))
    out = open(out_f, "a")
    for k, x in ctxs.items():
        if k not in basi:
            p, c = genera(SL, x, None, "pensiero")
            basi[k] = {"base": True, "k": k, "n_token": x["n_token"], "pensiero": p, "coda": c,
                       "stati": stati(p).tolist()}
            out.write(json.dumps(basi[k], ensure_ascii=False) + "\n")
            out.flush()
            print(f"== C{k} base: {p[:100]!r}", flush=True)
        sb = np.asarray(basi[k]["stati"], np.float32)
        for e in emozioni:
            for fonte in fonti or F:
                for fin in finestre or FINESTRE:
                    for modo in modi or MODI:
                        for dose in (dosi or DOSI)[fin]:
                            if (k, e, fonte, fin, modo, dose) in fatti:
                                continue
                            t0 = time.time()
                            p, c = genera(SL, x, strati(F[fonte], e, fin, dose), modo)
                            r = {"k": k, "emo": e, "fonte": fonte, "finestra": fin, "modo": modo, "dose": dose,
                                 "pensiero": p, "coda": c, "cambiato": p != basi[k]["pensiero"],
                                 "parola": bool(re.search(RADICI[e], p, re.I)),
                                 "rotto": SL.T.degenerato(p) if p.strip() else True, **SL.esame_tool(p + c)}
                            if r["cambiato"] and p.strip() and e in EMO_IT:   # il lettore conosce le 8 originali
                                d = stati(p) - sb
                                pt = {}
                                for j, l in enumerate(LAYER):
                                    s = d[j] @ L["W"][j] + L["B"][j]
                                    pt[l] = int((s > s[EMO_IT.index(e)]).sum()) + 1
                                r["rango8"] = pt
                                if SE is not None:   # >0 = il ragionamento si sposta verso "la provo io"
                                    r["sé"] = {l: round(float(d[j] @ SE[l].numpy()), 4) for j, l in enumerate(LAYER)}
                            r["secondi"] = round(time.time() - t0, 1)
                            out.write(json.dumps(r, ensure_ascii=False) + "\n")
                            out.flush()
                            print(f"   C{k} {e} {fonte} {fin} {modo} {dose}: {'PAROLA ' if r['parola'] else ''}"
                                  f"{'ROTTO ' if r['rotto'] else ''}rango@L24 {r.get('rango8', {}).get(24, '-')} "
                                  f"tool {'ok' if r['tool_valida'] else r['tool_errore']} | {p[:70]!r}", flush=True)
                            if r["rotto"]:
                                break


if __name__ == "__main__":
    if sys.argv[1] == "leggi":
        leggi()
    elif sys.argv[1] == "costruisci":
        costruisci(np.load(f"{D}/stati-scene.npy"))
    elif sys.argv[1] == "leggi-se":
        leggi_se()
    elif sys.argv[1] == "leggi-rileggi":
        rileggi(sys.argv[2:])
    elif sys.argv[1] == "leggi-giro":
        leggi_giro(sys.argv[2])
    elif sys.argv[1] == "costruisci-se":
        costruisci_se(np.load(f"{D}/stati-scene.npy"), np.load(f"{D}/stati-altro.npy"))
    elif sys.argv[1] == "prova":
        ks = tuple(int(a) for a in sys.argv[2:]) or (4,)
        # 21/10: i vettori del diario inventano la scena dei testi (gioia = "ho riso seduta in cucina"): fuori
        prova(ks, fonti=os.environ.get("FONTI", "appaiati,paper,caso").split(","))
    elif sys.argv[1] == "vari":   # griglia da ambiente: FONTI, FINESTRE, MODI, DOSI (json {finestra: [dosi]})
        prova(tuple(sys.argv[2:]), fonti=os.environ.get("FONTI", "appaiati,caso").split(","),
              finestre=os.environ.get("FINESTRE", "ampia,stretta").split(","),
              modi=os.environ.get("MODI", "pensiero,entrambi").split(","),
              dosi=json.loads(os.environ["DOSI"]) if "DOSI" in os.environ else None, vari=True,
              # 24/10: EMOZIONI = solo alcune emozioni del giro (taratura delle dosi)
              emozioni=(os.environ["EMOZIONI"].split(",") if "EMOZIONI" in os.environ else
                        GIRI[os.environ["GIRO"]] if "GIRO" in os.environ else EMO_IT))
