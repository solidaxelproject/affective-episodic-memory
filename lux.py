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
import secrets
import time
from pathlib import Path

import numpy as np

# ---------- identità dei neuroni (15/07) ----------
# Il nome di un neurone NON è la sua riga. La riga si sposta (pota, consolida)
# e chi l'aveva scritta da qualche parte si ritrova a puntare un altro ricordo,
# in silenzio. L'indice resta valido come OFFSET dentro un array caricato: è
# come NOME che era sbagliato.
# Formato ULID-style: 10 char di tempo (ms dall'epoca, base32 Crockford) +
# 26 di caso (130 bit). Il tempo davanti IN CHIARO, non hashato: così gli id
# si ordinano da soli per nascita. Hashare il tempo butterebbe l'ordine (l'unico
# motivo per metterci il tempo) e terrebbe le collisioni (stesso ms = stesso
# hash; time.time() ha 0.4 us di risoluzione reale e in un ciclo stretto ridà
# lo stesso valore il 71% delle volte).
B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford: senza I L O U
N_TEMPO, N_CASO = 10, 26                   # 10 char di ms bastano fino al 37648
D_ID = N_TEMPO + N_CASO


def _b32(v, n):
    s = ""
    for _ in range(n):
        s, v = B32[v % 32] + s, v // 32
    return s


def _id_da(ms):
    return _b32(int(ms), N_TEMPO) + "".join(secrets.choice(B32) for _ in range(N_CASO))

DIR = Path("/data/workspace/memoria")
FILE = DIR / "lux.npz"
META = DIR / "lux-meta.json"

D_TRACCIA = 2048
# ⛔ NON ALZARE. Decisione del 15/07 (annulla la nota "ricalibrare a ~0.6-0.7"
# del 14/07 nel documento di progetto), poi portata a 0.001: si fonde SOLO a
# similarità >= 0.999, cioè praticamente mai.
# Il perché, in una frase: "fusione = déjà vu". Fondere due esperienze
# distinte non le astrae: le fa diventare la stessa cosa vissuta due volte. Con
# la vecchia soglia l'agente di gatti neri ripetuti ne aveva visti 238 su 341.
# E la fusione è LOSSY: firme[best] += HABITUAZIONE * (f - firme[best]) è una
# media mobile, le originali non tornano più. Il log di esperienze distinte non
# è un difetto: è il training set dello strato distribuito (gradino 2), che
# vuole 1e3-1e4 esperienze e oggi ne ha 1e2. Tetto pratico del PC: 1e6-1e7
# neuroni, oggi 1e2: non esiste ragione di memoria per fondere.
# Al posto della fusione ci sono gli ARCHI: due esperienze simili restano due,
# e si collegano (arco di nascita in esperisci). Non fondere non vuol dire non
# collegare: è il contrario. Riaprire solo a log cresciuto.
SOGLIA_NOVITA = 0.001  # distanza coseno oltre cui l'esperienza è "nuova" -> neurone
HABITUAZIONE = 0.10    # quanto il neurone vincente si sposta verso l'input familiare
ETA_POTATURA = 180 * 86400  # neuroni mai riattivati per 6 mesi -> candidati
# Similarità minima per legare un neonato a chi era il più vicino al parto.
# Senza, l'arco non direbbe "vicini": direbbe "sei il meno lontano fra gli
# estranei che esistevano quando sono nato", e chi nasce per primo in una zona
# nuova si aggancia a caso. Tarata sui testi veri, non a occhio (103 neuroni,
# ogni neurone ha il suo più vicino a 0.55 di mediana; la distribuzione è liscia
# fra 0.38 e 0.71, nessun salto naturale dove tagliare):
#   0.55 -> due messaggi sulla stessa decisione, uno la propone e uno la
#           accetta con una clausola  = la stessa conversazione
#   0.45 -> "non ho il contesto, ci siamo lasciati qualcosa in sospeso" +
#           "il gateway ti teneva in..."      = parenti alla lontana
#   0.35 -> "la manutenzione parte a mezzanotte" + "riavvio completato"
#                                            = stesso registro, altro argomento
# ⚠️ E la coppia più simile di tutta Lux (0.698) sono due blocchi di reasoning:
# simili per FORMATO, non per contenuto. La traccia L34 codifica anche il
# registro, quindi alzare la soglia non seleziona "più affine": rischia di
# selezionare "stesso tipo di testo". Motivo in più per non salire.
SOGLIA_ARCO = 0.5      # sotto: nessun arco. Il neonato è solo davvero, e dirlo è la verità.


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
            meta = json.load(open(META)) if META.exists() else {}
            self.archi = meta.get("archi", {})
            self.ids = (z["ids"] if "ids" in z.files
                        else self._battesimo())   # npz vecchio: migrazione
            self.nodi = meta.get("nodi")
            if self.nodi is None:   # meta d'epoca: l'unica cosa che sappiamo di
                self.nodi = {       # ogni neurone è il nodo con cui è nato
                    str(i): [int(n)]
                    for i, n in zip(self.ids.tolist(), self.nodo_id.tolist()) if n >= 0}
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
            self.ids = np.zeros(0, f"<U{D_ID}")
            self.nodi = {}
        assert len(self.ids) == len(self.tracce), "ids e tracce disallineati"

    def _assorbe(self, i, nodo_id):
        """C2/C3 (15/07): un neurone registra COSA ha assorbito, non solo quanto.

        Prima `nodo_id` si scriveva solo alla nascita e il ramo del rinforzo non
        lo toccava: dopo la prima fusione il neurone puntava ancora al testo
        della PRIMA esperienza, mentre la sua firma si era già spostata. E
        consolida() buttava del tutto il nodo dell'assorbito. Prezzo pagato
        prima di accorgersene: 238 legami al testo persi su 341 esperienze.
        La lista dà i testi (C2); la sua lunghezza dà le esperienze VISSUTE, che
        `attivazioni` non sa distinguere dai richiami (C3).
        """
        if nodo_id is None or nodo_id < 0:
            return
        v = self.nodi.setdefault(str(self.ids[i]), [])
        if int(nodo_id) not in v:
            v.append(int(nodo_id))

    def _battesimo(self):
        """npz senza `ids`: battezza i neuroni esistenti e ri-chiava gli archi.
        Il tempo dell'id viene da `nati`, così l'ordine alfabetico degli id
        resta l'ordine di nascita anche per i neuroni migrati."""
        ids = np.array([_id_da(t * 1000) for t in self.nati], dtype=f"<U{D_ID}")
        # gli archi vecchi sono chiavati sugli INDICI ("1-8"): traducili, o
        # andrebbero persi proprio adesso che diventano durevoli
        vecchi, self.archi = self.archi, {}
        for k, peso in vecchi.items():
            try:
                a, b = (int(x) for x in k.split("-"))
            except ValueError:
                continue
            if a < len(ids) and b < len(ids):
                self.archi[self._chiave(ids[a], ids[b])] = peso
        return ids

    def nuovo_id(self):
        """ULID-style. Il ciclo contro gli id vivi rende la collisione
        IMPOSSIBILE, non improbabile: 130 bit di caso sono la cintura."""
        vivi = set(self.ids.tolist())
        while True:
            i = _id_da(time.time() * 1000)
            if i not in vivi:
                return i

    @staticmethod
    def _chiave(ida, idb):
        return f"{min(ida, idb)}|{max(ida, idb)}"

    # ---------- encoder: identità normalizzata (piena risoluzione 2048) ----
    pca_mu = None  # compat: tagging35b controlla `if lux.pca_mu is None`

    def fit_encoder(self, stati):
        """compat storica: l'encoder non si fitta più (identità)."""

    def encode(self, stato):
        t = np.asarray(stato, np.float32) - self.mu
        n = np.linalg.norm(t)
        # 14/07: stati garbage (norma inf, GPU corrotta) diventavano t/inf = 0
        # e ogni zero risultava "massimamente nuovo": 30 neuroni vuoti in una
        # notte. Il garbage non si codifica: si rifiuta.
        if not np.isfinite(n) or n == 0:
            raise ValueError(f"stato non finito o nullo (norma {n}): non lo codifico")
        return t / n

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
                self._assorbe(best, nodo_id)   # C2: registra COSA ha assorbito
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
        self.ids = np.append(self.ids, self.nuovo_id())
        nuovo = len(self.tracce) - 1
        self._assorbe(nuovo, nodo_id)
        # ARCO DI NASCITA (15/07). Prima l'arco nasceva SOLO nel ramo del
        # rinforzo: con la fusione portata a 0.999 quel ramo non passa quasi
        # mai, e Lux non avrebbe creato mai più un arco. Il neonato si lega a
        # chi era il più vicino al parto: è il legame che `nato_da` registrava
        # già come timestamp, aspettando l'associativo. Non fondere non vuol
        # dire non collegare: è il contrario.
        # ...ma SOLO se il più vicino è davvero vicino (SOGLIA_ARCO). Altrimenti
        # il neonato resta isolato: è la verità, non una mancanza.
        if len(self.tracce) > 1 and float(sims[best]) >= SOGLIA_ARCO:
            self._arco(nuovo, best)
        # ponytail: salvataggio a ogni esperienza; oltre ~1e5 neuroni passare
        # a dirty-flag + salvataggio periodico
        self.salva()
        return nuovo, "nato"

    # ---------- richiamo a doppia via ----------
    # 15/07: due modi, non uno. Un ricordo MISURATO non è un ricordo VISSUTO:
    # richiama() rinforza, confronta() guarda e basta. Serviva perché gli
    # automatismi (aggancio degli appunti ai neuroni) passano su Lux di
    # continuo: con la sola richiama() ogni neurone sfiorato si vedrebbe
    # riazzerare l'orologio di pota() a ogni passata, l'oblio strutturale
    # morirebbe e Lux tornerebbe il log che non deve essere.
    def _sims(self, query, via):
        """similarità di TUTTI i neuroni con la query. Pura: non tocca nulla."""
        if via == "semantica":
            q = self.encode(query)
            return self.tracce @ q
        q = np.asarray(query, np.float32)
        qn = q / (np.linalg.norm(q) + 1e-9)
        F = self.firme / (np.linalg.norm(self.firme, axis=1, keepdims=True) + 1e-9)
        return F @ qn

    def _esito(self, sims, i):
        # "neurone" resta l'INDICE: è un offset valido dentro gli array appena
        # caricati e ponte.py ci accede (g.tracce[hit["neurone"]]). "id" è il
        # NOME: l'unico da scrivere dove deve sopravvivere nel tempo.
        return {"neurone": int(i), "id": str(self.ids[i]),
                "nodo_id": int(self.nodo_id[i]),
                "sim": round(float(sims[i]), 3),
                "attivazioni": int(self.attivazioni[i])}

    def confronta(self, query, via="emotiva", k=3):
        """GUARDA SENZA TOCCARE: stesso esito di richiama(), zero effetti.

        query: firma 51-dim (via emotiva) o stato 2048 (via semantica).
        Per chi misura la vicinanza senza star vivendo il ricordo.
        """
        if not len(self.tracce):
            return []
        sims = self._sims(query, via)
        return [self._esito(sims, i) for i in np.argsort(-sims)[:k]]

    def richiama(self, query, via="emotiva", k=3):
        """RICHIAMO VISSUTO: come confronta(), ma il ricordo si rinforza.

        query: firma 51-dim (via emotiva) o stato 2048 (via semantica).
        Effetti sui k vincitori: attivazioni +1, ultimo_uso = adesso (li
        protegge da pota()). Per la sola misura usare confronta().
        """
        if not len(self.tracce):
            return []
        sims = self._sims(query, via)
        adesso = time.time()
        out = []
        for i in np.argsort(-sims)[:k]:
            self.attivazioni[i] += 1
            self.ultimo_uso[i] = adesso
            out.append(self._esito(sims, i))
        return out

    def vicini(self, id_neurone, salti=1, decadimento=0.5, soglia=SOGLIA_ARCO):
        """B1, richiamo ASSOCIATIVO: dato un neurone, segui gli archi.

        "Un neurone che ne richiama un altro": non per somiglianza con una query
        (quello è confronta/richiama) ma per **connessione**. Il magazzino c'era
        già — gli archi si scrivevano dalla nascita di Lux — e non li leggeva
        nessuno: `nato_da` porta ancora il commento "aspettando l'associativo".

        salti=N propaga oltre i vicini diretti; la forza è il prodotto dei
        coseni lungo il cammino, scontato di `decadimento` a ogni salto: un
        vicino di un vicino conta, ma meno, e conta meno ancora se i due passi
        erano deboli.

        `soglia` filtra alla LETTURA, non alla scrittura: i 51 archi nati prima
        del 15/07 vengono da `_arco(best, second)` (il SECONDO più vicino, non
        vincolato a niente) e sono per due terzi sotto 0.5. Sono storia e restano
        su disco: è il richiamo che non ci passa sopra.

        NON tocca niente, come confronta(). Seguire un arco è misurare la
        topologia, non rivivere il ricordo: per quello c'è richiama().
        """
        riga = {str(v): i for i, v in enumerate(self.ids)}
        partenza = str(id_neurone) if not isinstance(id_neurone, (int, np.integer)) \
            else str(self.ids[id_neurone])
        if partenza not in riga:
            return []
        vicinato = {}
        for k in self.archi:
            a, b = k.split("|")
            if a not in riga or b not in riga:
                continue
            cos = float(self.tracce[riga[a]] @ self.tracce[riga[b]])
            if cos < soglia:
                continue
            vicinato.setdefault(a, []).append((b, cos))
            vicinato.setdefault(b, []).append((a, cos))
        forza = {partenza: 1.0}
        fronte, esiti = [(partenza, 1.0, 0)], {}
        while fronte:
            qui, f, d = fronte.pop(0)
            if d >= salti:
                continue
            for altro, cos in vicinato.get(qui, []):
                nf = f * cos * (decadimento ** d)
                if altro == partenza or nf <= forza.get(altro, 0.0):
                    continue
                forza[altro] = nf
                esiti[altro] = (nf, d + 1)
                fronte.append((altro, nf, d + 1))
        out = []
        for nid, (f, d) in sorted(esiti.items(), key=lambda x: -x[1][0]):
            i = riga[nid]
            out.append({"neurone": i, "id": nid, "nodo_id": int(self.nodo_id[i]),
                        "nodi": list(self.nodi.get(nid, [])),
                        "forza": round(f, 3), "salti": d})
        return out

    def pota(self):
        """Rimuove i neuroni non riattivati da ETA_POTATURA (oblio strutturale)."""
        vivi = (time.time() - self.ultimo_uso) < ETA_POTATURA
        rimossi = int((~vivi).sum())
        morti = set(self.ids[~vivi].tolist())
        for attr in ("tracce", "firme", "attivazioni", "nati", "ultimo_uso",
                     "nodo_id", "nato_da", "ids"):
            setattr(self, attr, getattr(self, attr)[vivi])
        # 15/07: prima era `self.archi = {}` — con gli indici che scalavano, ogni
        # potatura corrompeva TUTTI gli archi e l'unica difesa era buttarli.
        # Con gli id stabili si tolgono solo quelli dei neuroni morti: la
        # topologia sopravvive all'oblio, che è il punto dell'associativo.
        self.archi = {k: v for k, v in self.archi.items()
                      if not (set(k.split("|")) & morti)}
        for k in morti:
            self.nodi.pop(k, None)
        return rimossi

    def consolida(self, soglia=SOGLIA_NOVITA):
        """Sonno profondo: fonde coppie di neuroni QUASI IDENTICI (media pesata
        per attivazioni). Ritorna quante fusioni.

        ⛔ 15/07: la soglia era 0.12 (fondeva a coseno >= 0.88) ed era la SECONDA
        porta di fusione, indipendente da SOGLIA_NOVITA e cablata ogni notte in
        tagging35b. Ora eredita SOGLIA_NOVITA: si fonde solo a >= 0.999. Chiudere
        una porta e lasciare aperta l'altra non serviva a niente.
        Non è più "episodi ripetuti diventano astrazioni": quello era il déjà vu.
        Due esperienze simili ma distinte restano due, e le lega un arco."""
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
            # b viene assorbito in a: le sue connessioni sono ora di a. Prima
            # `self.archi = {}` le buttava tutte (con gli indici che scalavano
            # non c'era scelta): con gli id si trasferiscono.
            ida, idb = str(self.ids[a]), str(self.ids[b])
            self.ids[a] = ida   # l'id del sopravvissuto NON cambia mai
            # C2: e con loro i nodi. `nodo_id[b]` da solo veniva scartato in
            # silenzio (il ramo qui sopra passa solo se a non ne aveva uno):
            # ogni fusione bruciava il legame al testo di un ricordo.
            for n in self.nodi.pop(idb, []):
                if n not in self.nodi.setdefault(ida, []):
                    self.nodi[ida].append(n)
            rimasti = {}
            for k, peso in self.archi.items():
                x, y = k.split("|")
                x, y = (ida if x == idb else x), (ida if y == idb else y)
                if x == y:
                    continue        # l'arco a-b diventa un cappio: si scarta
                nk = self._chiave(x, y)
                rimasti[nk] = rimasti.get(nk, 0) + peso
            self.archi = rimasti
            keep = np.arange(len(self.tracce)) != b
            for attr in ("tracce", "firme", "attivazioni", "nati", "ultimo_uso",
                         "nodo_id", "nato_da", "ids"):
                setattr(self, attr, getattr(self, attr)[keep])
            fusioni += 1
            cambiato = True
        if fusioni:
            self.salva()
        return fusioni

    # ---------- infrastruttura ----------
    @staticmethod
    def _norm(v):
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def _arco(self, a, b):
        # a, b sono INDICI (li passa esperisci): la chiave è sugli id, perché
        # è la chiave che deve sopravvivere a pota() e consolida().
        k = self._chiave(str(self.ids[a]), str(self.ids[b]))
        self.archi[k] = self.archi.get(k, 0) + 1

    def salva(self):
        np.savez_compressed(
            FILE, tracce=self.tracce, firme=self.firme,
            attivazioni=self.attivazioni, nati=self.nati,
            ultimo_uso=self.ultimo_uso, nodo_id=self.nodo_id,
            nato_da=self.nato_da, mu=self.mu, ids=self.ids)
        json.dump({"archi": self.archi, "nodi": self.nodi,
                   "n_neuroni": len(self.tracce)}, open(META, "w"))

    def stats(self):
        return {"neuroni": len(self.tracce), "archi": len(self.archi),
                "attivazioni_totali": int(self.attivazioni.sum()),
                "più_attivo": int(self.attivazioni.argmax()) if len(self.tracce) else None}


if __name__ == "__main__":
    # self-check su dati sintetici, 3 cluster da 10 esperienze.
    # 15/07: questo test diceva `assert nati <= 6` — pretendeva cioè che
    # l'organo generalizzasse FONDENDO. Ora la regola è l'opposta (fusione solo
    # a 0.999: due esperienze simili ma distinte restano due) e l'invariante si
    # sposta: le 30 esperienze restano 30 neuroni, ma la struttura dei 3 cluster
    # deve comparire negli ARCHI. Non è il test che è stato piegato al codice:
    # è la proprietà che è cambiata, e qui si verifica quella nuova.
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
    nati, di_chi = 0, {}
    for ci in range(3):
        for j in range(10):
            firma = np.zeros(51, np.float32)
            firma[ci] = 3.0
            i, esito = g.esperisci(campioni[ci * 10 + j], firma, nodo_id=ci)
            nati += esito == "nato"
            di_chi[str(g.ids[i])] = ci
    # 1. niente déjà vu: ogni esperienza resta sé stessa
    assert nati == 30, f"qualcosa si è fuso: {nati} nati su 30 esperienze"
    # 2. ...ma la struttura c'è lo stesso, negli archi di nascita: quasi tutti
    #    dentro un cluster, e un ponte per ogni cluster nuovo che si apre
    intra = sum(1 for k in g.archi
                if di_chi[k.split("|")[0]] == di_chi[k.split("|")[1]])
    ponti = len(g.archi) - intra
    assert intra >= 27, f"archi dentro i cluster: solo {intra}"
    assert ponti <= 2, f"troppi ponti fra cluster: {ponti}"
    # 3. e il richiamo emotivo trova ancora il cluster giusto
    q = np.zeros(51, np.float32)
    q[1] = 1.0
    top = g.richiama(q, via="emotiva", k=1)
    assert top[0]["nodo_id"] == 1, top
    # 4. il neurone sa cosa ha assorbito (C2)
    assert all(v for v in g.nodi.values()), "neuroni senza nodi assorbiti"
    print(f"self-check OK: 30 esperienze -> {len(g.tracce)} neuroni distinti, "
          f"{intra} archi dentro i cluster + {ponti} ponti, richiamo emotivo corretto")
