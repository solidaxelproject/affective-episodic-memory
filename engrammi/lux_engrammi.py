#!/usr/bin/env python3
"""Lux degli engrammi (11/10/2026): ricordi come indici di engrammi condivisi, legati da archi con parametri.
Il Lux originale (lux.npz, lux-meta.json) e memoria.db NON si toccano: si leggono e basta, l'uscita va in lux-<VERSIONE>/.
  costruisci   CPU: taglia i ricordi (taglia.py), engrammi unici, archi in ordine, vettori bge-m3 (:8094), firme
  aggiungi     notturna: i ricordi nuovi di memoria.db entrano senza ricostruire (i rinforzi restano)
  prova        ricomposizione di tutti i ricordi + richiamo da indizi parziali + domande di prova
  richiama "testo"   i ricordi richiamati, ricomposti (non rinforza)
  consegna "testo"   come la consegna all'agente: richiama sopra soglia, RINFORZA gli archi, ricompone
  correggi CODICE "testo"   1.11.0: un ricordo nuovo che corregge quello di CODICE (l'originale non si tocca)
Arco = (ricordo, posizione, engramma a, engramma b, parametri fra i due): niente errori di strada sugli engrammi condivisi.
ponytail: modificatori dei parametri non ancora usati nella scelta, propagazione solo come predisposizione (1.12.0);
via emotiva assente nel richiamo
(la firma del messaggio richiede il 35B, GPU): le firme degli engrammi sono pronte in F."""
import contextlib
import fcntl
import hashlib
import json
import os
import random
import sqlite3
import sys
import time
import urllib.request

import numpy as np

import salienza as SA
import taglia as T

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import lux as LUX   # solo le funzioni FSRS e l'orologio vissuto (lettura): il Lux originale non si tocca

# VERSIONE MAJOR.MINOR.PATCH (11/10): MAJOR = formato dei dati incompatibile (lo stato dei rinforzi non si
# porta), MINOR = ricostruzione con regole nuove (taglio, vettori) o funzione nuova, PATCH = correzione che non
# cambia i dati. Ogni versione ha la sua cartella: le vecchie restano.
VERSIONE = "1.12.0"   # 1.3.0: codice dei ricordi; 1.4.0: vettori L29 degli engrammi (lux-l29.npz); 1.5.0: aggiungi();
# 1.6.0 (15/10): vettori bge-m3 in float16 su disco e in RAM (misurato sul Lux dell'agente: scarto coseni max 1.4e-4,
# richiamo identico su 94/94 indizi); il coseno si calcola a blocchi riportati in float32
# 1.7.0 (15/10): taglio per lingua (taglia.py: le frasi inglesi sicure vanno a en_core_web_lg); costruisci()
# riusa i vettori degli engrammi gia' presenti nella versione PRECEDENTE (stesso testo = stesso vettore)
# 1.8.0 (16/10): stabilita' iniziale con la salienza (salienza.py: distintivita' e riferimento a se'),
# vettori delle frasi dei ricordi in lux-salienza.npz
# 1.8.1 (16/10): la salienza sta dentro lux.npz (chiavi sal_*) con engrammi e archi, niente file a parte
# 1.9.0 (16/10): riferimento a se' coi vettori centrati (salienza.py, sal_mu)
# 1.10.0 (16/10): fino a CONSEGNA_MAX ricordi nella stessa risposta del tool, numerati (risposta_tool)
# 1.11.0 (16/10): correzioni (correggi): ricordi legati al ricordo corretto da un arco a posizione -1, consegnati
# in catena (un posto solo fra i CONSEGNA_MAX), originale barrato e mai piu' rinforzato. Fasi 2 e 3: PIANO-1.11-FASI-2-3.md
# 1.12.0 (20/10): predisposizione dopo il richiamo (predisponi): i ricordi che condividono engrammi e archi coi
# ricordi consegnati salgono prima col prossimo indizio; apostrofi veri distinti dagli apici delle citazioni (taglia.py,
# unisci): si ricostruisce. Piano: PIANO-1.12-PREDISPOSIZIONE.md
DIR = f"/data/memoria-episodica-affettiva/engrammi/lux-{VERSIONE}"
PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.11.0"   # da qui costruisci() riprende i vettori gia' calcolati
NPZ, META, STATO = f"{DIR}/lux.npz", f"{DIR}/lux-meta.json", f"{DIR}/lux-stato.npz"
CRESCITA_PIENA = 100.0   # S/S0 a cui la facilita' tocca il tetto
FACILITA_MAX = 2.0   # tetto: un ricordo richiamato spesso arriva alla soglia con un indizio fino a 2x piu' debole
EMOZIONI = [e["en"] for e in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))]   # ordine fisso dei 51 assi
EMBEDDER = "http://127.0.0.1:8094/v1/embeddings"
CONSEGNA_MAX = 4   # 1.10.0 (16/10): ricordi al massimo nella stessa risposta del tool (1.11.0: catene)
PRIMO_CORREZIONE = 1_000_000   # 1.11.0: numeri delle correzioni, fuori dalla serie di memoria.db
CORREGGE = "corregge"   # 1.11.0: parametro dell'arco che lega una correzione al ricordo corretto
SOGLIA_RICHIAMO = 0.2   # sotto: nessun ricordo, nessun turno del tool (taratura_soglia.py, 11/10: negativi max 0.177, positivi giusti min 0.268)
VTIPO = np.float16   # 1.6.0
SOGLIA_SEM = 0.8     # coseno minimo perche' un engramma del messaggio ne accenda uno del Lux
PREDISPOSIZIONE_EMIVITA = 21600.0   # 1.12.0 (6 ore, Cai 2016, Rashid 2016): secondi di parete, dopo i quali la spinta e' a meta'
PREDISPOSIZIONE_MAX = 2.0   # 1.12.0: tetto del moltiplicatore del richiamo
PESO_COPPIA = 1.0   # 1.12.0: un arco condiviso (stessa coppia di engrammi) vale quanto un engramma in piu'
INVERSO = {}
for _k, _v in T.PREPOSIZIONI.items():   # forma canonica: la prima della tabella (di, non d'; a, non ad; tra, non fra)
    INVERSO.setdefault(_v, _k)


def codice(ts):
    """identificativo del ricordo che l'agente vede (11/10): SHA-256 del timestamp, 16 caratteri [0-9a-z]"""
    n, s = int(hashlib.sha256(repr(ts).encode()).hexdigest(), 16), ""
    for _ in range(16):
        n, r = divmod(n, 36)
        s += "0123456789abcdefghijklmnopqrstuvwxyz"[r]
    return s


@contextlib.contextmanager
def lucchetto():
    """1.11.0: notturna (aggiungi), correzioni e servizio (salva_stato) non scrivono i file del Lux insieme"""
    with open(f"{DIR}/.lucchetto", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def chiave(testo):
    return " ".join(testo.lower().split())


def embed(testi):
    out = []
    for i in range(0, len(testi), 64):
        r = urllib.request.Request(EMBEDDER, json.dumps({"input": testi[i:i + 64]}).encode(), {"Content-Type": "application/json"})
        out += [d["embedding"] for d in json.load(urllib.request.urlopen(r, timeout=600))["data"]]
    v = np.asarray(out, np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def coseni(Q, V, blocco=65536):
    """Q (float32) contro V (float16): a blocchi di righe riportati in float32, la RAM resta quella del float16"""
    return np.concatenate([Q @ V[i:i + blocco].astype(np.float32).T for i in range(0, len(V), blocco)], axis=1)


def s0_ricordi(firme, ranghi, nids):
    """stabilita' iniziale per ricordo (1.8.0): firma (json o None) + ranghi di salienza (salienza.py)"""
    out = {}
    for nid in nids:
        f = firme.get(nid)
        f = np.asarray([json.loads(f).get(e, 0.0) for e in EMOZIONI]) if f else None
        out[nid] = SA.stabilita_iniziale(f, *ranghi.get(nid, (0.0, 0.0)), LUX.S_BASE)
    return out


def param_id(testo, tab):
    """parametro -> intero: preposizioni = simbolo*8+articolo (0-71), gli altri (punteggiatura, congiunzioni, che) da 100 in su"""
    c = T.codice(testo)
    if c is not None:
        return c
    k = testo.lower()
    if k not in tab:
        tab[k] = 100 + len(tab)
    return tab[k]


def param_testo(pid, altri):
    if pid < 100:
        return INVERSO[(T.SIMBOLI[pid // 8], pid % 8)]
    return altri[pid - 100]


def unisci(pezzi):
    """[(tipo, testo)] -> testo. 1.12.0 (20/10): dopo un apostrofo si incolla solo l'elisione (consonante prima:
    l', dell', c'), non po' o perche'; i pezzi inglesi che iniziano con l'apostrofo si attaccano (it's, I've, aren't).
    ponytail: il genitivo inglese davanti a una parola ("students' books") esce attaccato"""
    out = ""
    for k, t in pezzi:
        elisione = out[-1:] in ("'", "’") and out[-2:-1].isalpha() and out[-2:-1].lower() not in "aeiouàèéìòù"
        clitico = k == "nodo" and t.startswith(("'", "’", "n't", "n’t"))
        attacca = k == "arco" and (t in ",.;:!?)…" or t.startswith("...")) or out.endswith("(") or elisione or clitico
        out += ("" if attacca or not out else " ") + t
    return out


def _inserisci(righe, eid, testi, firme_e, tab, A, par_lista, ricordi):
    """taglia i ricordi (id, testo, firma, classe, ts) e li aggiunge alle strutture: engrammi unici (chiave -> indice),
    firme per engramma, archi in ordine (ricordo, posizione, a, b, primo parametro, n parametri), parametri"""
    for nid, testo, firma, classe, ts in righe:
        pezzi = T.taglia(testo)
        f = np.asarray([json.loads(firma).get(e, 0.0) for e in EMOZIONI], np.float32) if firma else None
        nodi, legami, attesa = [], [], []
        for k, t in pezzi:
            if k == "arco":
                attesa.append(param_id(t, tab))
                continue
            kk = chiave(t)
            if kk not in eid:
                eid[kk] = len(testi)
                testi.append(t)
                firme_e.append([])
            if f is not None:
                firme_e[eid[kk]].append(f)
            nodi.append(eid[kk])
            legami.append(attesa)
            attesa = []
        ricordi[nid] = {"classe": classe, "codice": codice(ts), "n": len(nodi), "testa": legami[0] if legami else [], "coda": attesa}
        if classe == "correzione":   # non sta in memoria.db: il momento serve a ricostruire lo stesso codice
            ricordi[nid]["ts"] = ts
        for p in range(1, len(nodi)):
            A.append((nid, p, nodi[p - 1], nodi[p], len(par_lista), len(legami[p])))
            par_lista += legami[p]
        if len(nodi) == 1:   # ricordo di un engramma solo: arco su se stesso, cosi' l'indice lo trova
            A.append((nid, 0, nodi[0], nodi[0], len(par_lista), 0))


def _primo(A, nid):
    """primo engramma del ricordo nid negli archi A (array)"""
    r = A[(A[:, 0] == nid) & (A[:, 1] >= 0)]
    return int(r[r[:, 1].argmin(), 2])


def _lega(A, par_lista, tab, legami, ricordi, tutti):
    """1.11.0: archi fra ricordi (posizione -1) dal primo engramma della correzione al primo del ricordo corretto,
    parametri {corregge}{codice del corretto}; tutti = archi in cui cercare i primi engrammi"""
    for c, o in legami:
        A.append((c, -1, _primo(tutti, c), _primo(tutti, o), len(par_lista), 2))
        par_lista += [param_id(CORREGGE, tab), param_id(ricordi[o]["codice"], tab)]


def costruisci():
    os.makedirs(DIR, exist_ok=True)
    if os.path.exists(STATO):   # gli archi cambiano numerazione: lo stato dei rinforzi non varrebbe piu'
        sys.exit(f"{STATO} esiste: ricostruire cancella i rinforzi degli archi. Spostalo a mano se e' voluto.")
    c = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
    righe = c.execute("select id, testo, firma, classe, ts from nodi where testo != '' order by id").fetchall()
    legami = []
    if os.path.exists(f"{PRECEDENTE}/lux.npz"):   # 1.11.0: le correzioni non stanno in memoria.db, si riprendono
        Lp = Lux.struttura(PRECEDENTE)
        corr = sorted(n for n, r in Lp.ricordi.items() if r["classe"] == "correzione")
        righe += [(n, Lp.ricomponi(n), None, "correzione", Lp.ricordi[n]["ts"]) for n in corr]
        legami = [(n, Lp.corregge[n]) for n in corr if n in Lp.corregge]
    eid, testi, firme_e, tab, A, par_lista, ricordi = {}, [], [], {}, [], [], {}
    _inserisci(righe, eid, testi, firme_e, tab, A, par_lista, ricordi)
    _lega(A, par_lista, tab, legami, ricordi, np.asarray(A, np.int64))
    print(f"{len(righe)} ricordi -> {len(testi)} engrammi unici, {len(A)} archi, {len(tab)} parametri non preposizione", flush=True)
    V = np.zeros((len(testi), 1024), VTIPO)
    vecchi = {}
    if os.path.exists(f"{PRECEDENTE}/lux.npz"):
        zp, mp = np.load(f"{PRECEDENTE}/lux.npz"), json.load(open(f"{PRECEDENTE}/lux-meta.json"))
        vecchi = {t: j for j, t in enumerate(mp["engrammi"])}
        for i, t in enumerate(testi):
            if t in vecchi:
                V[i] = zp["V"][vecchi[t]]
    nuovi = [i for i, t in enumerate(testi) if t not in vecchi]
    print(f"vettori: {len(testi) - len(nuovi)} ripresi da {PRECEDENTE}, {len(nuovi)} da calcolare", flush=True)
    if nuovi:
        V[nuovi] = embed([testi[i] for i in nuovi]).astype(VTIPO)
    F = np.stack([np.mean(x, 0) if x else np.zeros(51, np.float32) for x in firme_e])
    A = np.asarray(A, np.int64)
    np.savez(NPZ, V=V, F=F, A=A, P=np.asarray(par_lista, np.int32), **SA.costruisci([(r[0], r[1]) for r in righe], embed))
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(META, "w"), ensure_ascii=False)
    print(f"scritto {NPZ} e {META}")


def aggiungi():
    """notturna: i ricordi nuovi di memoria.db entrano nel Lux"""
    with lucchetto():
        _aggiungi()


def correggi(codice_errato, testo, ts=None):
    """1.11.0 (16/10): un ricordo che corregge quello di codice_errato. Entra nel Lux come gli altri, con un numero
    fuori dalla serie di memoria.db, legato al corretto da un arco {corregge}{codice}; l'originale non si tocca e da
    adesso non si rinforza piu'. Una correzione si corregge allo stesso modo (ripensamento). Torna il codice nuovo."""
    with lucchetto():
        m = json.load(open(META))
        ricordi = {int(k): v for k, v in m["ricordi"].items()}
        o = next(n for n, r in ricordi.items() if r["codice"] == codice_errato)
        nid = max(PRIMO_CORREZIONE - 1, *ricordi) + 1
        ts = time.time() if ts is None else ts
        _aggiungi([(nid, testo, None, "correzione", ts)], [(nid, o)])
        return codice(ts)


def _aggiungi(righe=None, legami=()):
    """1.5.0 (notturna, 12/10): i ricordi nuovi di memoria.db entrano nel Lux senza ricostruire. Engrammi nuovi in coda
    (vettori bge-m3, firme), quelli gia' noti si condividono, archi nuovi in coda con la stabilita' iniziale; i rinforzi
    degli archi esistenti restano. Scrittura atomica: il servizio ricarica quando cambia lux-meta.json.
    ponytail: la firma di un engramma gia' noto non si ricalcola con i ricordi nuovi (servirebbero i conteggi);
    lux-l29.npz copre solo gli engrammi della costruzione (non usato nel richiamo)."""
    z, m = np.load(NPZ), json.load(open(META))
    ricordi = {int(k): v for k, v in m["ricordi"].items()}
    c = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
    if righe is None:
        righe = [r for r in c.execute("select id, testo, firma, classe, ts from nodi where testo != '' order by id") if r[0] not in ricordi]
    if not righe:
        print("nessun ricordo nuovo")
        return
    testi = list(m["engrammi"])
    eid = {chiave(t): i for i, t in enumerate(testi)}
    tab = {k: 100 + i for i, k in enumerate(m["altri_parametri"])}
    n_e, n_a = len(testi), len(z["A"])
    firme_e = [[] for _ in testi]
    A, par_lista = [], list(z["P"])
    _inserisci(righe, eid, testi, firme_e, tab, A, par_lista, ricordi)
    _lega(A, par_lista, tab, legami, ricordi, np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)]))
    nuovi = testi[n_e:]
    V = np.concatenate([z["V"].astype(VTIPO), embed(nuovi).astype(VTIPO)]) if nuovi else z["V"].astype(VTIPO)
    F = np.concatenate([z["F"], np.stack([np.mean(x, 0) if x else np.zeros(51, np.float32) for x in firme_e[n_e:]])]) if nuovi else z["F"]
    A = np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)])
    sal = SA.aggiungi([(r[0], r[1]) for r in righe], embed, z)
    if os.path.exists(STATO):   # archi nuovi: stabilita' iniziale da firma e salienza del ricordo, nati oggi (vissuto)
        s = np.load(STATO)
        s0r = s0_ricordi({r[0]: r[2] for r in righe}, SA.ranghi(sal), [r[0] for r in righe])
        s0 = np.asarray([s0r[int(r)] for r in A[n_a:, 0]], np.float64)
        oggi = np.full(len(s0), float(LUX.orologio()))
        np.savez(STATO + ".tmp.npz", S=np.concatenate([s["S"], s0]), S0=np.concatenate([s["S0"], s0]), U=np.concatenate([s["U"], oggi]))
    np.savez(NPZ + ".tmp.npz", V=V, F=F, A=A, P=np.asarray(par_lista, np.int32), **sal)
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(META + ".tmp", "w"), ensure_ascii=False)
    os.replace(NPZ + ".tmp.npz", NPZ)
    if os.path.exists(STATO + ".tmp.npz"):
        os.replace(STATO + ".tmp.npz", STATO)
    os.replace(META + ".tmp", META)   # per ultimo: e' il segnale di ricarica del servizio
    print(f"{len(righe)} ricordi nuovi, {len(nuovi)} engrammi nuovi, {len(A) - n_a} archi nuovi")


class Lux:
    def __init__(self):
        self._apri(DIR)
        # 1.4.0: vettori L29 degli engrammi (vettori_l29.py), stesso spazio di addr-sem; per la via L29 serve lo
        # stato L29 del messaggio, che legge luxifer (35B, GPU): ancora non usati nel richiamo
        f = f"{DIR}/lux-l29.npz"
        self.L29, self.ha_l29 = (np.load(f)["L"], np.load(f)["presente"]) if os.path.exists(f) else (None, None)
        self.carica_stato()

    @classmethod
    def struttura(cls, cartella):
        """engrammi, archi e ricordi di una cartella, senza stato dei rinforzi (per leggere una versione precedente)"""
        L = cls.__new__(cls)
        L._apri(cartella)
        return L

    def _apri(self, cartella):
        z = np.load(f"{cartella}/lux.npz")
        self.V, self.F, self.A, self.P = z["V"].astype(VTIPO, copy=False), z["F"], z["A"], z["P"]
        m = json.load(open(f"{cartella}/lux-meta.json"))
        self.testi, self.altri, self.ricordi = m["engrammi"], m["altri_parametri"], {int(k): v for k, v in m["ricordi"].items()}
        self.chiavi = {chiave(t): i for i, t in enumerate(self.testi)}
        self.da_codice = {r["codice"]: n for n, r in self.ricordi.items()}
        self.vivi = self.A[:, 1] >= 0   # 1.11.0: posizione -1 = legame fra ricordi, fuori da ricomposizione e richiamo
        self.per_ricordo = {}
        self.per_engramma = {}
        self.coppie = {}   # 1.12.0: coppia di engrammi (non ordinata) -> ricordi che hanno quell'arco
        for j in np.nonzero(self.vivi)[0].tolist():
            r, _, a, b = self.A[j, :4].tolist()
            self.per_ricordo.setdefault(r, []).append(j)
            self.per_engramma.setdefault(a, set()).add(j)
            self.per_engramma.setdefault(b, set()).add(j)
            self.coppie.setdefault((min(a, b), max(a, b)), set()).add(r)
        self.pronti = {}   # 1.12.0: ricordo -> (spinta, ora) lasciata dalle consegne. ponytail: solo RAM, si perde al
        # riavvio del servizio (effetto di ore); su disco se servira' sopravvivere ai riavvii
        self.corregge, self.corretto_da = {}, {}   # correzione -> ricordo corretto, e al contrario
        for j in np.nonzero(~self.vivi)[0].tolist():
            r, _, _, _, p0, n = self.A[j].tolist()
            if n == 2 and param_testo(int(self.P[p0]), self.altri) == CORREGGE:
                o = self.da_codice[param_testo(int(self.P[p0 + 1]), self.altri)]
                self.corregge[r] = o
                self.corretto_da.setdefault(o, []).append(r)
        self.errati = set(self.corretto_da)

    # ---------- archi vivi (11/10): stabilita' FSRS per arco, come nel Lux originale ----------
    def carica_stato(self):
        """S (stabilita') e U (ultimo giorno vissuto) per arco. Al primo avvio: S0 da firma e salienza del ricordo
        (salienza.py, fino a 3x), U = oggi vissuto"""
        if os.path.exists(STATO):
            z = np.load(STATO)
            self.S, self.S0, self.U = z["S"], z["S0"], z["U"]
            return
        c = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
        firme = dict(c.execute("select id, firma from nodi"))
        s0 = s0_ricordi(firme, SA.ranghi(np.load(NPZ)), self.ricordi)
        self.S = np.asarray([s0[int(r)] for r in self.A[:, 0]], np.float64)
        self.S0 = self.S.copy()
        self.U = np.full(len(self.A), float(LUX.orologio()))

    def salva_stato(self):
        with lucchetto():
            np.savez(STATO + ".tmp.npz", S=self.S, S0=self.S0, U=self.U)
            os.replace(STATO + ".tmp.npz", STATO)

    def facilita_archi(self, oggi=None):
        """per arco: ritenzione R (cala se non si richiama) x crescita della stabilita' dalla nascita, in scala
        logaritmica fino al tetto FACILITA_MAX quando S = CRESCITA_PIENA x S0 (con FSRS un richiamo distanziato
        moltiplica S per ~5: il tetto arriva in 3-4 richiami). Appena nato = 1: la soglia tarata l'11/10 resta valida"""
        oggi = LUX.orologio() if oggi is None else oggi
        R = LUX.curva(np.maximum(oggi - self.U, 0.0), self.S)
        crescita = np.minimum(1.0, np.log(self.S / self.S0) / np.log(CRESCITA_PIENA))
        return R * (1 + (FACILITA_MAX - 1) * crescita)

    def facilita(self, oggi=None):
        """per ricordo: media della facilita' dei suoi archi -> moltiplica il punteggio del richiamo"""
        f = self.facilita_archi(oggi)[self.vivi]
        idx = np.unique(self.A[self.vivi, 0], return_inverse=True)
        media = np.bincount(idx[1], f) / np.bincount(idx[1])
        return dict(zip(idx[0].tolist(), media))

    def rinforza(self, nid, oggi=None):
        """richiamo riuscito del ricordo nid (consegnato all'agente): ogni suo arco cresce con FSRS (tanto piu' quanto stava
        svanendo; stesso giorno vissuto = crescita zero) e riparte da oggi. Salva lo stato."""
        oggi = LUX.orologio() if oggi is None else oggi
        js = self.per_ricordo.get(nid, [])
        R = LUX.curva(np.maximum(oggi - self.U[js], 0.0), self.S[js])
        self.S[js] = [LUX.cresci(float(s), float(r)) for s, r in zip(self.S[js], R)]
        self.U[js] = oggi
        self.salva_stato()

    def spinta(self, r, ora):
        """1.12.0: predisposizione del ricordo r all'ora (secondi di parete), dimezzata ogni PREDISPOSIZIONE_EMIVITA"""
        s, t = self.pronti.get(r, (0.0, ora))
        return s * 0.5 ** (max(0.0, ora - t) / PREDISPOSIZIONE_EMIVITA)

    def predisponi(self, nids, ora=None):
        """1.12.0: dopo una consegna, ogni ricordo che condivide engrammi (peso 1/(altri ricordi che li usano), effetto
        ventaglio di Anderson 1974) o archi (stessa coppia di engrammi, x PESO_COPPIA) coi ricordi consegnati riceve una
        spinta, divisa per sqrt(engrammi del ricordo) come in richiama; si somma a quella residua"""
        ora = time.time() if ora is None else ora
        spinte = {}
        for x in nids:
            js = self.per_ricordo.get(x, [])
            gruppi = [(1.0, {int(self.A[j, 0]) for j in self.per_engramma[e]}) for e in {int(v) for j in js for v in self.A[j, 2:4]}]
            gruppi += [(PESO_COPPIA, self.coppie[c]) for c in {tuple(sorted(int(v) for v in self.A[j, 2:4])) for j in js}
                       if c[0] != c[1]]   # l'arco su se stesso dei ricordi di un engramma solo non e' una relazione
            for peso, ric in gruppi:
                for r in ric:
                    spinte[r] = spinte.get(r, 0) + peso / max(1, len(ric) - 1)
        for r, s in spinte.items():
            if r not in nids:
                self.pronti[r] = (self.spinta(r, ora) + s / np.sqrt(self.ricordi[r]["n"]), ora)

    def consegna(self, testo, quanti=CONSEGNA_MAX, oggi=None, esclusi=(), ora=None):
        """L'UNICA porta per dare ricordi all'agente (richiamo automatico, 11/10): richiama, rinforza gli archi dei
        ricordi consegnati, restituisce [(id, testo ricomposto)]. Lista vuota = nessun turno del tool.
        esclusi = codici dei ricordi gia' consegnati nella conversazione: si passa al successivo sopra soglia.
        La pagina 3D e le prove usano richiama(), che non rinforza."""
        via = {self.da_codice[c] for c in esclusi if c in self.da_codice}   # gia' nel contesto della conversazione
        catene = []   # 1.11.0: un ricordo con le sue correzioni occupa un posto solo
        for nid, _ in self.richiama(testo, len(self.ricordi), oggi=oggi, ora=ora):
            k = self.catena(nid)
            if len(catene) == quanti:
                break
            if not via & set(k) and all(k[0] != c[0] for c in catene):
                catene.append(k)
        scelti = [n for k in catene for n in k]
        for nid in scelti:
            if nid not in self.errati:   # un ricordo corretto non si rinforza piu'
                self.rinforza(nid, oggi)
        self.predisponi(scelti, ora)
        return [(nid, self.ricordi[nid]["codice"], self.ricomponi(nid)) for nid in scelti]

    def catena(self, nid):
        """1.11.0: il ricordo originale e tutte le correzioni che lo seguono (ripensamenti compresi), dalla piu' vecchia"""
        while nid in self.corregge:
            nid = self.corregge[nid]
        k = [nid]
        for n in k:
            k += sorted(self.corretto_da.get(n, []))
        return k

    def risposta_tool(self, nids):
        """il testo che l'agente riceve nel tool memorinvolontaria (16/10): per ogni ricordo il numero (1°, 2°, ...),
        il codice sulla riga dopo, poi il testo nudo. 1.11.0: le correzioni seguono il loro originale con una lettera
        (1a°, 1b°), i ricordi corretti sono barrati (~~testo~~)"""
        righe, k, radice, lettere = [], 0, None, ""
        for n in nids:
            r = self.catena(n)[0]
            if r != radice:
                k, radice, lettere = k + 1, r, iter("abcdefghijklmnopqrstuvwxyz")
                et = f"{k}°"
            else:
                et = f"{k}{next(lettere)}°"
            t = self.ricomponi(n)
            righe.append(f"{et}\n{self.ricordi[n]['codice']}\n" + (f"~~{t}~~" if n in self.errati else t))
        return "\n".join(righe)

    def ricomponi(self, nid):
        arcs = sorted(self.per_ricordo.get(nid, []), key=lambda j: self.A[j, 1])
        info = self.ricordi[nid]
        pezzi = [("arco", param_testo(p, self.altri)) for p in info["testa"]]
        for k, j in enumerate(arcs):
            _, pos, a, b, p0, n = self.A[j]
            if k == 0:
                pezzi.append(("nodo", self.testi[a]))
            if pos == 0:
                continue
            pezzi += [("arco", param_testo(int(p), self.altri)) for p in self.P[p0:p0 + n]]
            pezzi.append(("nodo", self.testi[b]))
        pezzi += [("arco", param_testo(p, self.altri)) for p in info["coda"]]
        return unisci(pezzi)

    def accendi(self, testo):
        """innesco: via testuale (stesso engramma = 1) e via semantica (bge-m3, coseno sopra soglia riscalato 0-1)"""
        att = {}
        nodi = [t for k, t in T.taglia(testo) if k == "nodo"]
        if not nodi:
            return att
        for t in nodi:
            i = self.chiavi.get(chiave(t))
            if i is not None:
                att[i] = 1.0
        S = coseni(embed(nodi), self.V)
        for row in S:
            for i in np.where(row >= SOGLIA_SEM)[0]:
                att[int(i)] = max(att.get(int(i), 0), float((row[i] - SOGLIA_SEM) / (1 - SOGLIA_SEM)))
        return att

    def richiama(self, testo, quanti=3, soglia=SOGLIA_RICHIAMO, oggi=None, ora=None):
        """scelta: per ogni indice di ricordo la somma delle attivazioni dei suoi engrammi, pesate 1/log(1+ricordi che
        usano l'engramma) (gli engrammi comuni contano poco) e divise per sqrt(engrammi del ricordo) (i lunghi non vincono
        sempre), poi moltiplicate per la facilita' del ricordo (archi vivi). Tarato l'11/10 su 40 indizi: soglia 0.8, nessuna propagazione nella scelta (abbassava da 35 a 30).
        1.12.0: poi per la predisposizione lasciata dalle consegne (1 + spinta, fino a PREDISPOSIZIONE_MAX), solo sui
        ricordi che l'indizio ha gia' acceso."""
        punti = {}
        for i, a in self.accendi(testo).items():
            ric = {int(self.A[j, 0]) for j in self.per_engramma.get(i, ())}
            for r in ric:
                punti[r] = punti.get(r, 0) + a / np.log(1 + len(ric))
        fac = self.facilita(oggi)
        ora = time.time() if ora is None else ora
        for r in punti:
            punti[r] *= fac[r] / np.sqrt(self.ricordi[r]["n"]) * min(PREDISPOSIZIONE_MAX, 1 + self.spinta(r, ora))
        return [x for x in sorted(punti.items(), key=lambda x: -x[1])[:quanti] if x[1] >= soglia]


def prova():
    L = Lux()
    c = sqlite3.connect(f"file:{T.DB}?mode=ro", uri=True)
    orig = dict(c.execute("select id, testo from nodi where testo != ''"))
    norm = lambda s: "".join(T.FORMATO.sub("", s).split())
    ok = [nid for nid in L.ricordi if norm(L.ricomponi(nid)) == norm(orig[nid])]
    ok_min = [nid for nid in L.ricordi if norm(L.ricomponi(nid)).lower() == norm(orig[nid]).lower()]
    print(f"ricomposizione identica (spazi a parte): {len(ok)}/{len(L.ricordi)}, maiuscole a parte: {len(ok_min)}/{len(L.ricordi)}")
    random.seed(0)
    prove = random.sample([n for n in L.ricordi if L.ricordi[n]["n"] >= 6], 40)
    colpiti = 0
    for nid in prove:   # indizio parziale: due engrammi del ricordo, non vicini
        idx = sorted(L.per_ricordo[nid], key=lambda j: L.A[j, 1])
        e = [int(L.A[j, 3]) for j in idx]
        indizio = L.testi[e[1]] + ". " + L.testi[e[len(e) // 2 + 1]]
        r = L.richiama(indizio, 1, 0)
        colpiti += bool(r) and r[0][0] == nid
    print(f"richiamo da due engrammi del ricordo: {colpiti}/{len(prove)} al primo posto")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "costruisci":
        costruisci()
    elif cmd == "aggiungi":
        aggiungi()
    elif cmd == "prova":
        prova()
    elif cmd == "consegna":   # come la consegna vera: rinforza e scrive lux-stato.npz
        L = Lux()
        c = L.consegna(sys.argv[2])
        print(f"== ricordi {[nid for nid, _, _ in c]}\n{L.risposta_tool([nid for nid, _, _ in c])}")
    elif cmd == "correggi":
        print(correggi(sys.argv[2], sys.argv[3]))
    elif cmd == "richiama":
        L = Lux()
        for nid, p in L.richiama(sys.argv[2]):
            print(f"\n== ricordo {nid}  ({p:.2f})\n{L.ricomponi(nid)}")
