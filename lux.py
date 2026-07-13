# Lux v0 (Grow-When-Required): l'organo di memoria crescente dell'agente.
# Neuroni = tracce di esperienza. Cresce con la novità, si rinforza con la
# familiarità, si pota col disuso. Doppio indice: semantico + emotivo.
# CPU pura (numpy). Interfaccia: stato dentro -> id dei nodi fuori (la stessa
# del grafo v1, così un giorno può sostituirne il recupero).
# 13/07: tracce a PIENA risoluzione 2048 (lo stato L34 normalizzato, niente più
# PCA-128: era il ponytail dei tempi di 81 campioni; scelta di progetto per
# dettaglio del codec e spazio angolare nel tempo lungo).
# ponytail: indice = forza bruta (fino a ~1e5), poi hnswlib, poi DiskANN.
import json
import time
from pathlib import Path

import numpy as np

DIR = Path("/data/workspace/memoria")
FILE = DIR / "lux.npz"
META = DIR / "lux-meta.json"

D_TRACCIA = 2048
SOGLIA_NOVITA = 0.35   # distanza coseno oltre cui l'esperienza è "nuova" -> neurone
HABITUAZIONE = 0.10    # quanto il neurone vincente si sposta verso l'input familiare
ETA_POTATURA = 180 * 86400  # neuroni mai riattivati per 6 mesi -> candidati


class Lux:
    def __init__(self):
        if FILE.exists():
            z = np.load(FILE, allow_pickle=False)
            self.tracce = z["tracce"]          # [n, D_TRACCIA]
            self.firme = z["firme"]            # [n, 51]
            self.attivazioni = z["attivazioni"]
            self.nati = z["nati"]
            self.ultimo_uso = z["ultimo_uso"]
            assert self.tracce.shape[1] == D_TRACCIA, (
                f"lux.npz ha tracce {self.tracce.shape[1]}-dim, attese "
                f"{D_TRACCIA}: serve la migrazione (bak + rebuild da vettori.pt)")
            self.nodo_id = z["nodo_id"]        # link al grafo v1 (testo)
            # scatola nera delle nascite: timestamp `nati` del neurone vincente
            # al momento del parto (-1 se primo). Non usata dal richiamo: serve
            # a retrodatare gli archi di nascita quando arriverà l'associativo.
            self.nato_da = (z["nato_da"] if "nato_da" in z.files
                            else np.full(len(self.tracce), -1.0))
            # media di popolazione: senza centratura gli stati raw condividono
            # una direzione comune (cos medio 0.50) e i ricordi si sovrappongono
            self.mu = z["mu"] if "mu" in z.files else np.zeros(D_TRACCIA, np.float32)
            self.archi = json.load(open(META)).get("archi", {})
        else:
            self.tracce = np.zeros((0, D_TRACCIA), np.float32)
            self.firme = np.zeros((0, 51), np.float32)
            self.attivazioni = np.zeros(0, np.int64)
            self.nati = np.zeros(0, np.float64)
            self.ultimo_uso = np.zeros(0, np.float64)
            self.nodo_id = np.zeros(0, np.int64)
            self.nato_da = np.zeros(0, np.float64)
            self.mu = np.zeros(D_TRACCIA, np.float32)
            self.archi = {}

    # ---------- encoder: identità normalizzata (piena risoluzione 2048) ----
    pca_mu = None  # compat: tagging35b controlla `if lux.pca_mu is None`

    def fit_encoder(self, stati):
        """compat storica: l'encoder non si fitta più (identità)."""

    def encode(self, stato):
        t = np.asarray(stato, np.float32) - self.mu
        n = np.linalg.norm(t)
        return t / n if n > 0 else t

    # ---------- il cuore: esperienza in ingresso ----------
    def esperisci(self, stato, firma, nodo_id=-1):
        """Un'esperienza arriva: neurone nuovo se abbastanza NUOVA,
        rinforzo+habituazione del vicino se familiare.
        Ritorna (indice_neurone, "nato"|"rinforzato")."""
        t = self.encode(stato)
        f = np.asarray(firma, np.float32)
        adesso = time.time()
        if len(self.tracce):
            sims = self.tracce @ t
            best = int(sims.argmax())
            dist = 1.0 - float(sims[best])
            if dist < SOGLIA_NOVITA:  # familiare: rinforza, non crescere
                self.tracce[best] = self._norm(
                    self.tracce[best] + HABITUAZIONE * (t - self.tracce[best]))
                self.firme[best] += HABITUAZIONE * (f - self.firme[best])
                self.attivazioni[best] += 1
                self.ultimo_uso[best] = adesso
                if len(sims) > 1:  # arco topologico verso il secondo vicino
                    second = int(np.argsort(sims)[-2])
                    self._arco(best, second)
                self.salva()  # write-through: la copia su CEMS sempre viva
                return best, "rinforzato"
        # nuova: nasce un neurone (registrando CHI era il più vicino al parto)
        vincente = float(self.nati[best]) if len(self.tracce) else -1.0
        self.tracce = np.vstack([self.tracce, t[None]])
        self.firme = np.vstack([self.firme, f[None]])
        self.attivazioni = np.append(self.attivazioni, 1)
        self.nati = np.append(self.nati, adesso)
        self.ultimo_uso = np.append(self.ultimo_uso, adesso)
        self.nodo_id = np.append(self.nodo_id, nodo_id)
        self.nato_da = np.append(self.nato_da, vincente)
        # ponytail: salvataggio a ogni esperienza; oltre ~1e5 neuroni passare
        # a dirty-flag + salvataggio periodico
        self.salva()
        return len(self.tracce) - 1, "nato"

    # ---------- richiamo a doppia via ----------
    def richiama(self, query, via="emotiva", k=3):
        """query: firma 51-dim (via emotiva) o stato 2048 (via semantica)."""
        if not len(self.tracce):
            return []
        if via == "semantica":
            q = self.encode(query)
            sims = self.tracce @ q
        else:
            q = np.asarray(query, np.float32)
            qn = q / (np.linalg.norm(q) + 1e-9)
            F = self.firme / (np.linalg.norm(self.firme, axis=1, keepdims=True) + 1e-9)
            sims = F @ qn
        ordine = np.argsort(-sims)[:k]
        adesso = time.time()
        out = []
        for i in ordine:
            self.attivazioni[i] += 1
            self.ultimo_uso[i] = adesso
            out.append({"neurone": int(i), "nodo_id": int(self.nodo_id[i]),
                        "sim": round(float(sims[i]), 3),
                        "attivazioni": int(self.attivazioni[i])})
        return out

    def pota(self):
        """Rimuove i neuroni non riattivati da ETA_POTATURA (oblio strutturale)."""
        vivi = (time.time() - self.ultimo_uso) < ETA_POTATURA
        rimossi = int((~vivi).sum())
        for attr in ("tracce", "firme", "attivazioni", "nati", "ultimo_uso",
                     "nodo_id", "nato_da"):
            setattr(self, attr, getattr(self, attr)[vivi])
        self.archi = {}  # ponytail: gli archi si ricostruiscono con l'uso
        return rimossi

    def consolida(self, soglia=0.12):
        """Sonno profondo: fonde coppie di neuroni troppo simili in uno schema
        (media pesata per attivazioni). Ogni notte: episodi ripetuti diventano
        astrazioni, la popolazione resta magra. Ritorna quante fusioni."""
        fusioni = 0
        cambiato = True
        while cambiato and len(self.tracce) > 1:
            cambiato = False
            S = self.tracce @ self.tracce.T
            np.fill_diagonal(S, -1)
            a, b = np.unravel_index(int(S.argmax()), S.shape)
            if S[a, b] < 1.0 - soglia:
                break
            wa, wb = self.attivazioni[a], self.attivazioni[b]
            self.tracce[a] = self._norm((self.tracce[a] * wa + self.tracce[b] * wb) / (wa + wb))
            self.firme[a] = (self.firme[a] * wa + self.firme[b] * wb) / (wa + wb)
            self.attivazioni[a] += self.attivazioni[b]
            self.nati[a] = min(self.nati[a], self.nati[b])  # nascita = la più antica
            self.ultimo_uso[a] = max(self.ultimo_uso[a], self.ultimo_uso[b])
            if self.nodo_id[a] < 0:
                self.nodo_id[a] = self.nodo_id[b]  # tieni un link al testo
            keep = np.arange(len(self.tracce)) != b
            for attr in ("tracce", "firme", "attivazioni", "nati", "ultimo_uso",
                         "nodo_id", "nato_da"):
                setattr(self, attr, getattr(self, attr)[keep])
            fusioni += 1
            cambiato = True
        if fusioni:
            self.archi = {}
            self.salva()
        return fusioni

    # ---------- infrastruttura ----------
    @staticmethod
    def _norm(v):
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def _arco(self, a, b):
        k = f"{min(a, b)}-{max(a, b)}"
        self.archi[k] = self.archi.get(k, 0) + 1

    def salva(self):
        np.savez_compressed(
            FILE, tracce=self.tracce, firme=self.firme,
            attivazioni=self.attivazioni, nati=self.nati,
            ultimo_uso=self.ultimo_uso, nodo_id=self.nodo_id,
            nato_da=self.nato_da, mu=self.mu)
        json.dump({"archi": self.archi, "n_neuroni": len(self.tracce)},
                  open(META, "w"))

    def stats(self):
        return {"neuroni": len(self.tracce), "archi": len(self.archi),
                "attivazioni_totali": int(self.attivazioni.sum()),
                "più_attivo": int(self.attivazioni.argmax()) if len(self.tracce) else None}


if __name__ == "__main__":
    # self-check su dati sintetici: 3 cluster -> deve crescere ~3 neuroni,
    # non 30; il richiamo emotivo deve trovare il cluster giusto.
    import tempfile
    rng = np.random.default_rng(7)
    _td = tempfile.TemporaryDirectory()
    FILE = Path(_td.name) / "lux.npz"
    META = Path(_td.name) / "lux-meta.json"
    g = Lux()
    base = rng.normal(size=(3, 2048)).astype(np.float32)
    campioni = np.vstack([b + 0.05 * rng.normal(size=(10, 2048)).astype(np.float32)
                          for b in base])
    g.fit_encoder(campioni)
    nati = 0
    for ci in range(3):
        for j in range(10):
            firma = np.zeros(51, np.float32)
            firma[ci] = 3.0
            _, esito = g.esperisci(campioni[ci * 10 + j], firma, nodo_id=ci)
            nati += esito == "nato"
    assert nati <= 6, f"cresciuto troppo: {nati} neuroni per 3 cluster"
    q = np.zeros(51, np.float32)
    q[1] = 1.0
    top = g.richiama(q, via="emotiva", k=1)
    assert top[0]["nodo_id"] == 1, top
    print(f"self-check OK: 30 esperienze in 3 cluster -> {len(g.tracce)} neuroni, "
          f"richiamo emotivo corretto")
