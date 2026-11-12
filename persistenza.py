# Persistenza, fasi 2-3 (30/09, PIANO-PERSISTENZA-LUX.md): cosa succede di notte ai messaggi
# che il tagging SCARTA (salienza sotto soglia). CPU pura, niente GPU. Criterio dei valori (l'utente, 30/09):
# avvicinarsi il piu' possibile alla memoria umana.
# B5 (01/11, PIANO-FIRMA-ENGRAMMI.md, D6 dell'utente: "il vecchio lux si archivi e non venga piu' usato"): eco e temi
# lavorano sul Lux degli engrammi, attraverso il suo servizio (:8132, unico che scrive lo stato), e su bge-m3 (:8094).
#
# ECO. Un messaggio scartato che e' "di nuovo la stessa cosa" di un ricordo lo riattiva: i suoi archi crescono
#   (POST /rinforza) con peso PESO_ECO. E' il riconoscimento: il quotidiano si stabilizza anche se ogni volta e' banale.
#   SOGLIA_ECO = 1.35 sul punteggio del richiamo (POST /richiama: senza predisposizione), stesso criterio del 30/09:
#   sui 644 ricordi veri, il punteggio massimo di un ricordo contro gli ALTRI supera 1.35 nel 5% dei casi
#   (taratura_persistenza.py, 01/11: mediana 0.42). Prima 0.85 sul coseno delle tracce L29 del vecchio Lux.
#   PESO_ECO = 0.5: rivedere passivamente consolida meno che richiamare attivamente
#   (testing effect, Roediger & Karpicke 2006).
#
# ABITUDINI. Un messaggio scartato senza ricordo vicino entra in un TEMA candidato (centroide bge-m3 del messaggio
#   intero, firma media, testo piu' centrale, giorni in cui e' apparso, stabilita'). SOGLIA_TEMA = 0.84: coseno bge-m3
#   con lo stesso criterio (taratura del 01/11, mediana 0.70). Ogni ritorno in un giorno vissuto diverso e'
#   un'esposizione: la stabilita' del tema cresce con la stessa formula FSRS di Lux, con peso PESO_ECO. Quando
#   raggiunge la stabilita' con cui nasce un episodio emotivamente fortissimo (S_BASE * AROUSAL_MAX) il tema diventa
#   un ricordo (fonte "abitudine": lux_engrammi lo fa nascere con S0 >= S_ABITUDINE): la frequenza fa le veci
#   dell'intensita'. Un tema che smette di tornare sbiadisce con la stessa curva dell'oblio e, sotto
#   R_RICONOSCIMENTO, esce dal buffer. Niente N e W scelti a mano: numero di ritorni e finestra escono dalla curva.
import json
import urllib.request

import numpy as np

import lux as L   # solo FSRS e orologio vissuto

SOGLIA_ECO = 1.35
SOGLIA_TEMA = 0.84
PESO_ECO = 0.5
S_ABITUDINE = L.S_BASE * L.AROUSAL_MAX
# un'esposizione casuale non e' un ricordo appreso, ma il riconoscimento di cio' che si e' visto
# una volta dura giorni (Standing 1973): parte con la stabilita' di un "difficile" di FSRS (w1),
# codificato ma debole. Il tema esce dal buffer quando la ritenzione scende sotto il caso di un
# compito di riconoscimento a due scelte (0.5): da li' non si distingue piu' se lo si e' gia' visto.
# Con S = 1.18 un tema che non torna esce in ~15 giorni vissuti (una cosa settimanale regge).
S_ESPOSIZIONE = 1.18385
R_RICONOSCIMENTO = 0.5
SERVIZIO = "http://127.0.0.1:8132"
EMBEDDER = "http://127.0.0.1:8094/v1/embeddings"
MAX_CAR = 6000   # bge-m3 (:8094) legge al massimo 2048 token: per riconoscere un tema basta l'inizio
D_TEMA = 1024


def _post(url, corpo, timeout=600):
    r = urllib.request.Request(url, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.load(f)


def vettore(testi):
    """bge-m3 dei messaggi interi (primi MAX_CAR caratteri), unitari"""
    out = []
    for i in range(0, len(testi), 64):
        out += [d["embedding"] for d in _post(EMBEDDER, {"input": [t[:MAX_CAR] for t in testi[i:i + 64]]})["data"]]
    v = np.asarray(out, np.float32).reshape(-1, D_TEMA)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def richiama(testo):
    """(ricordo, punteggio) del ricordo piu' vicino nel Lux degli engrammi, o None"""
    r = _post(f"{SERVIZIO}/richiama", {"testo": testo, "quanti": 1})["ricordi"]
    return (int(r[0][0]), float(r[0][1])) if r else None


def rinforza(nid, peso):
    return _post(f"{SERVIZIO}/rinforza", {"nid": int(nid), "peso": peso})["rinforzato"]


def _file_temi():
    return L.FILE.parent / "temi-engrammi.npz"   # accanto a tempo-vissuto.json (anche nei test)


def _media(a, b, n):
    """firma media (dict) dopo n esposizioni: a e' la media delle n-1 precedenti"""
    return {e: round((a.get(e, 0.0) * (n - 1) + b.get(e, 0.0)) / n, 3) for e in a.keys() | b.keys()}


class Temi:
    """buffer dei temi candidati: pochi vettori (uno per tema), non un log di messaggi"""

    def __init__(self):
        f = _file_temi()
        if f.exists():
            z = np.load(f, allow_pickle=False)
            self.centri = z["centri"].astype(np.float32)
            self.firme = [json.loads(x) for x in z["firme"]]
            self.n = z["n"]
            self.giorni = [json.loads(x) for x in z["giorni"]]
            self.stab = z["stab"]
            self.ultimo = z["ultimo"]
            self.testi = [str(x) for x in z["testi"]]
            self.ts = z["ts"]
            self.dist = z["dist"]           # distanza del testo rappresentante dal centro
        else:
            self.centri = np.zeros((0, D_TEMA), np.float32)
            self.firme, self.giorni, self.testi = [], [], []
            self.n = np.zeros(0, np.int32)
            self.stab = np.zeros(0, np.float32)
            self.ultimo = np.zeros(0, np.float64)
            self.ts = np.zeros(0, np.float64)
            self.dist = np.zeros(0, np.float32)

    def salva(self):
        tmp = _file_temi().with_suffix(".tmp.npz")
        np.savez_compressed(tmp, centri=self.centri.astype(np.float16),
                            firme=np.array([json.dumps(f) for f in self.firme], dtype=str), n=self.n,
                            giorni=np.array([json.dumps(g) for g in self.giorni], dtype=str),
                            stab=self.stab, ultimo=self.ultimo, testi=np.array(self.testi, dtype=str),
                            ts=self.ts, dist=self.dist)
        tmp.replace(_file_temi())

    def _tieni(self, keep):
        for a in ("centri", "n", "stab", "ultimo", "ts", "dist"):
            setattr(self, a, getattr(self, a)[keep])
        for a in ("firme", "giorni", "testi"):
            setattr(self, a, [x for x, k in zip(getattr(self, a), keep) if k])

    def esponi(self, t, firma, testo, ts, oggi):
        """t: vettore bge-m3 unitario del messaggio, firma: dict {emozione: z}. Ritorna l'indice del tema."""
        if len(self.centri):
            sims = self.centri @ t
            i = int(sims.argmax())
            if sims[i] >= SOGLIA_TEMA:
                n = int(self.n[i]) + 1
                c = self.centri[i] * (n - 1) / n + t / n
                self.centri[i] = c / (np.linalg.norm(c) + 1e-9)
                self.firme[i] = _media(self.firme[i], firma, n)
                self.n[i] = n
                d = 1 - float(self.centri[i] @ t)
                if d < self.dist[i]:          # rappresentante = il messaggio vero piu' centrale
                    self.testi[i], self.ts[i], self.dist[i] = testo, ts, d
                if oggi not in self.giorni[i]:  # esposizione in un giorno vissuto NUOVO
                    r = L.curva(oggi - float(self.ultimo[i]), float(self.stab[i]))
                    self.stab[i] = L.cresci(float(self.stab[i]), r, PESO_ECO)
                    self.giorni[i].append(oggi)
                    self.ultimo[i] = oggi
                return i
        self.centri = np.vstack([self.centri, t[None].astype(np.float32)])
        self.firme.append(dict(firma))
        self.n = np.append(self.n, np.int32(1))
        self.giorni.append([oggi])
        self.stab = np.append(self.stab, np.float32(S_ESPOSIZIONE))
        self.ultimo = np.append(self.ultimo, float(oggi))
        self.testi.append(testo)
        self.ts = np.append(self.ts, float(ts))
        self.dist = np.append(self.dist, np.float32(0))
        return len(self.centri) - 1

    def maturi(self):
        return [i for i in range(len(self.centri)) if self.stab[i] >= S_ABITUDINE]

    def dimentica(self, oggi):
        """via i temi che non tornano piu': stessa curva di Lux, soglia del riconoscimento"""
        keep = L.curva(oggi - self.ultimo, self.stab) >= R_RICONOSCIMENTO
        self._tieni(keep)
        return int((~keep).sum())


def notte(scartati, oggi=None, promuovi=None):
    """scartati: [(testo, firma dict {emozione: z}, ts)] dei messaggi 'vissuti' sotto soglia.
    promuovi(testo, firma, vettore bge-m3, ts, giorni) -> nodo_id: crea il nodo in memoria.db (lo passa il tagger,
    che conosce memoria.py); il ricordo entra nel Lux degli engrammi con `lux_engrammi.py aggiungi`, nella notturna.
    None = nessuna promozione (collaudi). Servizio del Lux giu' = eccezione: il buffer non si salva, eco e temi
    saltano una notte. Salva il buffer, ritorna il resoconto."""
    oggi = L.orologio() if oggi is None else oggi
    temi = Temi()
    eco_per = {}
    nuovi_temi = 0
    vettori = vettore([t for t, _, _ in scartati]) if scartati else np.zeros((0, D_TEMA), np.float32)
    for (testo, firma, ts), t in zip(scartati, vettori):
        r = richiama(testo)
        if r and r[1] >= SOGLIA_ECO:
            if r[0] not in eco_per:            # al massimo un'eco per ricordo per notte
                rinforza(r[0], PESO_ECO)
            eco_per[r[0]] = eco_per.get(r[0], 0) + 1
            continue
        prima = len(temi.centri)
        temi.esponi(t, firma, testo, ts, oggi)
        nuovi_temi += len(temi.centri) > prima
    promossi = []
    maturi = temi.maturi() if promuovi else []
    for i in maturi:
        nid = promuovi(temi.testi[i], temi.firme[i], temi.centri[i], float(temi.ts[i]), temi.giorni[i])
        promossi.append((temi.testi[i], nid))
    temi._tieni(~np.isin(np.arange(len(temi.centri)), maturi))
    dimenticati = temi.dimentica(oggi)
    temi.salva()
    return {"eco": sum(eco_per.values()), "ricordi_eco": len(eco_per),
            "temi_nuovi": nuovi_temi, "temi": len(temi.centri), "promossi": promossi,
            "temi_dimenticati": dimenticati}


def migra(vecchio):
    """B5, una volta: i temi del vecchio buffer (spazio L29 del vecchio Lux) -> temi-engrammi.npz. Centro = bge-m3 del
    testo rappresentante; firma, n, giorni, stabilita', ultimo giorno e ts restano"""
    z = np.load(vecchio, allow_pickle=False)
    emos = sorted(json.load(open("/data/memoria-episodica-affettiva/emozioni.json")), key=lambda e: e["en"])
    t = Temi.__new__(Temi)
    t.testi = [str(x) for x in z["testi"]]
    t.centri = vettore(t.testi)
    t.firme = [{e["en"]: round(float(x), 3) for e, x in zip(emos, f)} for f in z["firme"]]   # ordine sorted del tagger
    t.n, t.stab, t.ultimo, t.ts = z["n"], z["stab"], z["ultimo"], z["ts"]
    t.giorni = [json.loads(x) for x in z["giorni"]]
    t.dist = 1 - np.einsum("ij,ij->i", t.centri, t.centri)   # il centro e' il rappresentante
    t.salva()
    return len(t.testi)
