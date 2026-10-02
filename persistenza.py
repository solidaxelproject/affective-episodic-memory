# Persistenza, fasi 2-3 (30/09, PIANO-PERSISTENZA-LUX.md): cosa succede di notte ai messaggi
# che il tagging SCARTA (salienza sotto soglia). CPU pura, niente GPU: gli stati li ha gia' letti
# il tagger. Criterio dei valori (scelta di progetto, 30/09): avvicinarsi il piu' possibile alla memoria umana.
#
# ECO. Un messaggio scartato che e' "di nuovo la stessa cosa" di un neurone esistente lo
#   riattiva: la stabilita' cresce (Lux.rinforza) con peso PESO_ECO, traccia e firma restano
#   ferme. E' il riconoscimento: il quotidiano si stabilizza anche se ogni volta e' banale.
#   SOGLIA_ECO = 0.85: sulle 169k coppie di ricordi veri (L29-lente, Occamy) e' il quantile che
#   tiene sotto il 5% la probabilita' di un'eco falsa per messaggio contro 450 neuroni; letto a
#   mano, sopra 0.85 ci sono ripetizioni vere ("Buongiorno, come stai oggi?" / "Ciao, come stai?").
#   PESO_ECO = 0.5: rivedere passivamente consolida meno che richiamare attivamente
#   (testing effect, Roediger & Karpicke 2006).
#
# ABITUDINI. Un messaggio scartato senza neurone vicino entra in un TEMA candidato (centroide,
#   firma media, testo piu' centrale, giorni in cui e' apparso, stabilita'). Ogni ritorno in un
#   giorno vissuto diverso e' un'esposizione: la stabilita' del tema cresce con la stessa
#   formula FSRS di Lux, con peso PESO_ECO. Quando raggiunge la stabilita' con cui nasce un
#   episodio emotivamente fortissimo (S_BASE * AROUSAL_MAX) il tema diventa un ricordo: la
#   frequenza fa le veci dell'intensita'. Un tema che smette di tornare sbiadisce con la stessa
#   curva dell'oblio e, sotto R_MIN, esce dal buffer.
#   Niente N e W scelti a mano: numero di ritorni e finestra escono dalla curva dell'oblio.
import json
from pathlib import Path

import numpy as np

import lux as L

SOGLIA_ECO = 0.85
PESO_ECO = 0.5
S_ABITUDINE = L.S_BASE * L.AROUSAL_MAX
# un'esposizione casuale non e' un ricordo appreso, ma il riconoscimento di cio' che si e' visto
# una volta dura giorni (Standing 1973): parte con la stabilita' di un "difficile" di FSRS (w1),
# codificato ma debole. Il tema esce dal buffer quando la ritenzione scende sotto il caso di un
# compito di riconoscimento a due scelte (0.5): da li' non si distingue piu' se lo si e' gia' visto.
# Con S = 1.18 un tema che non torna esce in ~15 giorni vissuti (una cosa settimanale regge).
S_ESPOSIZIONE = 1.18385
R_RICONOSCIMENTO = 0.5


def _file_temi():
    return L.FILE.parent / "temi-candidati.npz"


class Temi:
    """buffer dei temi candidati: pochi vettori (uno per tema), non un log di messaggi"""

    def __init__(self):
        f = _file_temi()
        if f.exists():
            z = np.load(f, allow_pickle=False)
            self.centri = z["centri"].astype(np.float32)
            self.firme = z["firme"]
            self.n = z["n"]
            self.giorni = [json.loads(x) for x in z["giorni"]]
            self.stab = z["stab"]
            self.ultimo = z["ultimo"]
            self.testi = [str(x) for x in z["testi"]]
            self.ts = z["ts"]
            self.dist = z["dist"]           # distanza del testo rappresentante dal centro
            self.rappr = z["rappr"].astype(np.float32)   # stato grezzo del rappresentante (per il nodo)
        else:
            self.centri = np.zeros((0, L.D_TRACCIA), np.float32)
            self.firme = np.zeros((0, 51), np.float32)
            self.n = np.zeros(0, np.int32)
            self.giorni, self.testi = [], []
            self.stab = np.zeros(0, np.float32)
            self.ultimo = np.zeros(0, np.float64)
            self.ts = np.zeros(0, np.float64)
            self.dist = np.zeros(0, np.float32)
            self.rappr = np.zeros((0, L.D_TRACCIA), np.float32)

    def salva(self):
        tmp = _file_temi().with_suffix(".tmp.npz")
        np.savez_compressed(tmp, centri=self.centri.astype(np.float16), firme=self.firme, n=self.n,
                            giorni=np.array([json.dumps(g) for g in self.giorni]),
                            stab=self.stab, ultimo=self.ultimo, testi=np.array(self.testi),
                            ts=self.ts, dist=self.dist, rappr=self.rappr.astype(np.float16))
        tmp.replace(_file_temi())

    def _tieni(self, keep):
        for a in ("centri", "firme", "n", "stab", "ultimo", "ts", "dist", "rappr"):
            setattr(self, a, getattr(self, a)[keep])
        self.giorni = [g for g, k in zip(self.giorni, keep) if k]
        self.testi = [t for t, k in zip(self.testi, keep) if k]

    def esponi(self, t, stato, firma, testo, ts, oggi):
        """t: traccia codificata (Lux.encode), stato: lo stesso grezzo. Ritorna l'indice del tema."""
        if len(self.centri):
            sims = self.centri @ t
            i = int(sims.argmax())
            if sims[i] >= SOGLIA_ECO:
                n = int(self.n[i]) + 1
                c = self.centri[i] * (n - 1) / n + t / n
                self.centri[i] = c / (np.linalg.norm(c) + 1e-9)
                self.firme[i] = self.firme[i] * (n - 1) / n + firma / n
                self.n[i] = n
                d = 1 - float(self.centri[i] @ t)
                if d < self.dist[i]:          # rappresentante = il messaggio vero piu' centrale
                    self.testi[i], self.ts[i], self.dist[i] = testo, ts, d
                    self.rappr[i] = stato
                if oggi not in self.giorni[i]:  # esposizione in un giorno vissuto NUOVO
                    r = L.curva(oggi - float(self.ultimo[i]), float(self.stab[i]))
                    self.stab[i] = L.cresci(float(self.stab[i]), r, PESO_ECO)
                    self.giorni[i].append(oggi)
                    self.ultimo[i] = oggi
                return i
        self.centri = np.vstack([self.centri, t[None].astype(np.float32)])
        self.firme = np.vstack([self.firme, np.asarray(firma, np.float32)[None]])
        self.n = np.append(self.n, np.int32(1))
        self.giorni.append([oggi])
        self.stab = np.append(self.stab, np.float32(S_ESPOSIZIONE))
        self.ultimo = np.append(self.ultimo, float(oggi))
        self.testi.append(testo)
        self.ts = np.append(self.ts, float(ts))
        self.dist = np.append(self.dist, np.float32(0))
        self.rappr = np.vstack([self.rappr, np.asarray(stato, np.float32)[None]])
        return len(self.centri) - 1

    def maturi(self):
        return [i for i in range(len(self.centri)) if self.stab[i] >= S_ABITUDINE]

    def dimentica(self, oggi):
        """via i temi che non tornano piu': stessa curva di Lux, soglia del riconoscimento"""
        keep = L.curva(oggi - self.ultimo, self.stab) >= R_RICONOSCIMENTO
        self._tieni(keep)
        return int((~keep).sum())


def notte(organo, scartati, oggi=None, promuovi=None):
    """scartati: [(stato 2048 grezzo, firma 51 (z), testo, ts)] dei messaggi 'vissuti' sotto soglia.
    promuovi(testo, firma, stato grezzo, ts, giorni) -> nodo_id: crea il nodo nel grafo (lo passa il
    tagger, che conosce memoria.py e le alpha); None = nessuna promozione (collaudi).
    Salva Lux e il buffer, ritorna il resoconto."""
    oggi = L.orologio() if oggi is None else oggi
    temi = Temi()
    eco_per = {}
    nuovi_temi = 0
    for stato, firma, testo, ts in scartati:
        t = organo.encode(stato)        # stati gia' passati dalla guardia del tagger
        if len(organo.tracce):
            sims = organo.tracce @ t
            i = int(sims.argmax())
            if sims[i] >= SOGLIA_ECO:
                if i not in eco_per:            # al massimo un'eco per neurone per notte
                    organo.rinforza(i, peso=PESO_ECO, oggi=oggi)
                    organo.echi[i] += 1
                eco_per[i] = eco_per.get(i, 0) + 1
                continue
        prima = len(temi.centri)
        temi.esponi(t, np.asarray(stato, np.float32), np.asarray(firma, np.float32), testo, ts, oggi)
        nuovi_temi += len(temi.centri) > prima
    promossi = []
    maturi = temi.maturi() if promuovi else []
    for i in maturi:
        nid = promuovi(temi.testi[i], temi.firme[i], temi.rappr[i], float(temi.ts[i]), temi.giorni[i])
        j, _ = organo.esperisci(temi.rappr[i], temi.firme[i], nodo_id=nid)
        organo.stabilita[j] = max(float(organo.stabilita[j]), float(temi.stab[i]))
        organo.ultimo_vissuto[j] = float(oggi)
        promossi.append((temi.testi[i], nid))
    temi._tieni(~np.isin(np.arange(len(temi.centri)), maturi))
    dimenticati = temi.dimentica(oggi)
    potati = organo.pota(oggi)
    organo.salva()
    temi.salva()
    return {"eco": sum(eco_per.values()), "neuroni_eco": len(eco_per),
            "temi_nuovi": nuovi_temi, "temi": len(temi.centri), "promossi": promossi,
            "temi_dimenticati": dimenticati, "potati": potati}


if __name__ == "__main__":
    # collaudo su una Lux sintetica in una cartella temporanea (mai la produzione)
    import tempfile
    _td = tempfile.TemporaryDirectory()
    L.FILE = Path(_td.name) / "lux.npz"
    L.META = Path(_td.name) / "lux-meta.json"
    rng = np.random.default_rng(3)
    D = L.D_TRACCIA

    def vicino(b, rumore=0.02):
        return b + rumore * rng.normal(size=D).astype(np.float32) * np.linalg.norm(b) / np.sqrt(D)

    g = L.Lux()
    base_a, base_h, base_x = (rng.normal(size=D).astype(np.float32) for _ in range(3))
    firma = np.zeros(51, np.float32)
    firma[0] = 2.5
    g.esperisci(base_a, firma, nodo_id=1)
    traccia_a = g.tracce[0].copy()
    s0 = float(g.stabilita[0])
    # 1. ECO: tre ripetizioni di A nella stessa notte -> una sola crescita, traccia ferma
    r = notte(g, [(vicino(base_a), firma, "ciao, come stai?", 1.0)] * 3, oggi=0)
    assert r["eco"] == 3 and r["neuroni_eco"] == 1, r
    assert abs(float(g.stabilita[0]) - s0) < 1e-6, "stesso giorno: nessuna crescita"
    assert np.allclose(g.tracce[0], traccia_a), "l'eco non deve spostare la traccia"
    # ...e a giorni distanziati la stabilita' cresce, meno di un richiamo vero (PESO_ECO)
    g2 = L.Lux()
    for giorno in (5, 12, 20):
        notte(g2, [(vicino(base_a), firma, "ciao, come stai?", 2.0)], oggi=giorno)
    s_eco = float(L.Lux().stabilita[0])
    assert s_eco > s0 * 2, (s0, s_eco)
    # 2. ABITUDINE: un tema nuovo che torna in giorni diversi diventa un ricordo
    creati = []

    def promuovi(testo, firma_, stato, ts, giorni):
        creati.append((testo, sorted(giorni)))
        return 100 + len(creati)

    giorni_serviti = None
    for giorno in range(21, 21 + 60, 2):          # un giorno si', uno no
        rr = notte(L.Lux(), [(vicino(base_h), firma * 0.3, f"faccio la spesa ({giorno})", float(giorno))],
                   oggi=giorno, promuovi=promuovi)
        if rr["promossi"]:
            giorni_serviti = (giorno - 21) // 2 + 1
            break
    assert giorni_serviti and creati and creati[0][0].startswith("faccio la spesa"), creati
    gg = L.Lux()
    assert len(gg.tracce) == 2 and float(gg.stabilita[1]) >= S_ABITUDINE, (len(gg.tracce), gg.stabilita)
    assert len(Temi().centri) == 0, "il tema promosso esce dal buffer"
    # 2b. anche una cosa SETTIMANALE diventa abitudine (piu' lentamente)
    base_w = rng.normal(size=D).astype(np.float32)
    settimane = None
    for k, giorno in enumerate(range(200, 200 + 7 * 20, 7)):
        rr = notte(L.Lux(), [(vicino(base_w), firma * 0.3, "pranzo della domenica", float(giorno))],
                   oggi=giorno, promuovi=promuovi)
        if rr["promossi"]:
            settimane = k + 1
            break
    assert settimane, "il settimanale non diventa mai abitudine"
    # 3. un tema visto una volta sola non diventa abitudine e prima o poi si dimentica
    notte(L.Lux(), [(vicino(base_x), firma * 0.3, "una volta sola", 99.0)], oggi=500)
    assert len(Temi().centri) == 1
    giorni_oblio = int(np.ceil(S_ESPOSIZIONE * (R_RICONOSCIMENTO ** (1 / L.DECAY) - 1) / L.F_CURVA)) + 1
    rr = notte(L.Lux(), [], oggi=500 + giorni_oblio)
    assert rr["temi_dimenticati"] == 1 and len(Temi().centri) == 0, rr
    print(f"collaudo persistenza OK: eco ammassate 1 crescita e traccia ferma; eco distanziate S {s0:.1f}->{s_eco:.1f}; "
          f"abitudine promossa dopo {giorni_serviti} ritorni a giorni alterni, settimanale dopo {settimane} settimane; "
          f"tema isolato dimenticato dopo {giorni_oblio} giorni vissuti")
