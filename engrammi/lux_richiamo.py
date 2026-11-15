"""Lux degli engrammi: la classe Lux: apertura, stato, predisposizione, consegna, richiamo, forza, ricomposizione.
Parte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano
lux_engrammi, che riesporta tutto."""
import lux_base as B
import json
import os
import itertools
import time
import numpy as np
import salienza as SA
import taglia as T
import lux as LUX   # solo le funzioni FSRS e l'orologio vissuto (lettura): il Lux originale non si tocca
import lux_ricombina as RC
import lux_fonti as FO


class Lux(RC.Ricombina, FO.Fonti):
    def __init__(self):
        self._apri(B.DIR)
        self.carica_stato()

    @classmethod
    def struttura(cls, cartella):
        """engrammi, archi e ricordi di una cartella, senza stato dei rinforzi (per leggere una versione precedente)"""
        L = cls.__new__(cls)
        L._apri(cartella)
        return L

    def _apri(self, cartella):
        z = B.carica_npz(f"{cartella}/lux.npz")
        self.V, self.F, self.A, self.C, self.P = z["V"].astype(B.VTIPO, copy=False), z["F"], z["A"], z["C"], z["P"]
        self.C0 = z["C0"] if "C0" in z else self.C   # una versione di prima della 1.14.0
        self.W = z["W"] if "W" in z else np.ones(len(self.A), np.float32)   # prima della 1.16.0
        self.fattore = z["fattore"] if "fattore" in z else np.ones(self.C.shape[1], np.float32)   # 1.21.0: firma_ora
        # 1.18.0 (l'utente 11/11, "stessa proporzione"): nella forza la firma degli engrammi alla nascita, cosi' la dose scende
        # come la carica (D3 del 09/11) e non col quadrato (con F sbiadirebbero carica e firma insieme)
        self.F0 = B.firme_engrammi(self.A, self.C0, len(self.V))
        m = json.load(open(f"{cartella}/lux-meta.json"))
        self.testi, self.altri, self.ricordi = m["engrammi"], m["altri_parametri"], {int(k): v for k, v in m["ricordi"].items()}
        self.chiavi = {B.chiave(t): i for i, t in enumerate(self.testi)}
        self.da_codice = {r["codice"]: n for n, r in self.ricordi.items()}
        self._Vs = None   # 1.22.0: via semantica con le emoji per significato (_vs)
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
        self.fan = np.asarray([max(1, len(self.per_engramma.get(i, ()))) for i in range(len(self.V))])   # 1.22.0
        nC = np.linalg.norm(self.C, axis=1)
        self.normC = float(np.median(nC[nC > 0])) if (nC > 0).any() else 1.0   # 1.22.0: scala delle cariche
        self.pronti = {}   # 1.12.0: ricordo -> (spinta, ora) lasciata dalle consegne. ponytail: solo RAM, si perde al
        # riavvio del servizio (effetto di ore); su disco se servira' sopravvivere ai riavvii
        self.corregge, self.corretto_da = {}, {}   # correzione -> ricordo corretto, e al contrario
        self.siti_di, self.ricordi_di_sito = {}, {}   # 1.24.0: ricordo -> siti (chiave del dominio), e al contrario
        for j in np.nonzero(~self.vivi)[0].tolist():
            r, _, a, _, p0, n = self.A[j].tolist()
            if n == 2 and B.param_testo(int(self.P[p0]), self.altri) == B.CORREGGE:
                o = self.da_codice[B.param_testo(int(self.P[p0 + 1]), self.altri)]
                self.corregge[r] = o
                self.corretto_da.setdefault(o, []).append(r)
            elif n == 1 and B.param_testo(int(self.P[p0]), self.altri) == B.FONTE:
                s = B.chiave(self.testi[a])
                self.siti_di.setdefault(r, []).append(s)
                self.ricordi_di_sito.setdefault(s, set()).add(r)
        self.errati = set(self.corretto_da)
        # 1.19.0 (l'utente 11/11, PIANO-1.19-VIA-EMOTIVA): profilo emotivo del ricordo = C0 medio per arco, z sulla
        # popolazione dei ricordi (come T1e: i numeri decisi sono misurati su C0)
        rid = self.A[self.vivi, 0].astype(np.int64)   # 1.24.0: solo archi vivi (gli archi dei siti non diluiscono)
        self.prof_nid = np.unique(rid)
        k = np.searchsorted(self.prof_nid, rid)
        somma = np.zeros((len(self.prof_nid), self.C0.shape[1]))
        np.add.at(somma, k, self.C0[self.vivi])
        prof = somma / np.bincount(k)[:, None]
        self.profz = (prof - prof.mean(0)) / (prof.std(0) + 1e-9)

    # ---------- archi vivi (11/10): stabilita' FSRS per arco, come nel Lux originale ----------
    def carica_stato(self):
        """S (stabilita') e U (ultimo giorno vissuto) per arco. Al primo avvio: S0 da firma e salienza del ricordo
        (salienza.py, fino a 3x), U = oggi vissuto"""
        self.R = {}   # 1.17.0: ultimo richiamo (ts della consegna) per ricordo
        self.archi_ric = {}   # 1.21.0: (a, b) radici, a < b -> [S, U giorno vissuto, co-selezioni, non lavorate]
        self.ponti = {}   # 1.23.0: (a, b) engrammi, a < b -> [peso, stabile, usato oggi, ricordo di a, ricordo di b]
        self.fiducia = {}   # 1.24.0: sito -> [fiducia, conferme, correzioni]
        self.confermati = set()   # 1.24.0: ricordi di siti gia' confermati (una conferma per ricordo)
        if os.path.exists(B.STATO):
            z = np.load(B.STATO)
            self.S, self.S0, self.U = z["S"], z["S0"], z["U"]
            if "R_nid" in z:
                self.R = dict(zip(z["R_nid"].tolist(), z["R_ts"].tolist()))
            if "PO" in z:
                self.ponti = {(a, b): [w, st, us, ra, rb] for (a, b), w, st, us, (ra, rb) in
                              zip(z["PO"].tolist(), z["PO_W"].tolist(), z["PO_ST"].tolist(), z["PO_US"].tolist(),
                                  z["PO_R"].tolist())}
            if "FO" in z:
                self.fiducia = {s: [w, int(c), int(x)] for s, w, c, x in
                                zip(z["FO"].tolist(), z["FO_W"].tolist(), z["FO_C"].tolist(), z["FO_X"].tolist())}
                self.confermati = set(z["FO_OK"].tolist())
            if "RA" in z:
                self.archi_ric = {(a, b): [s_, u, n, p] for (a, b), s_, u, n, p in
                                  zip(z["RA"].tolist(), z["RA_S"].tolist(), z["RA_U"].tolist(), z["RA_N"].tolist(),
                                      z["RA_P"].tolist())}
            return
        firme = {n: r.get("firma") for n, r in self.ricordi.items()}   # 1.20.0: dal meta
        s0 = B.s0_ricordi(firme, SA.ranghi(B.carica_npz()), self.ricordi)
        self.S = np.asarray([s0[int(r)] for r in self.A[:, 0]], np.float64)
        self.S0 = self.S.copy()
        self.U = np.full(len(self.A), float(LUX.orologio()))

    def salva_stato(self):
        with B.lucchetto():
            S, S0, U = self.S, self.S0, self.U
            if os.path.exists(B.STATO):   # 1.13.0: aggiungi ha messo archi nuovi dopo la lettura di questo Lux: restano
                d = np.load(B.STATO)
                if len(d["S"]) > len(S):
                    S, S0, U = (np.concatenate([x, d[k][len(x):]]) for x, k in ((S, "S"), (S0, "S0"), (U, "U")))
            ra = sorted(self.archi_ric.items())
            po = sorted(self.ponti.items())
            np.savez(B.STATO + ".tmp.npz", S=S, S0=S0, U=U, R_nid=np.asarray(list(self.R), np.int64),
                     R_ts=np.asarray(list(self.R.values()), np.float64),
                     RA=np.asarray([k for k, _ in ra], np.int64).reshape(-1, 2),
                     **{f"RA_{c}": np.asarray([v[i] for _, v in ra], t) for i, (c, t) in
                        enumerate((("S", np.float64), ("U", np.float64), ("N", np.int64), ("P", np.int64)))},
                     PO=np.asarray([k for k, _ in po], np.int64).reshape(-1, 2),   # 1.23.0: i ponti
                     PO_R=np.asarray([v[3:5] for _, v in po], np.int64).reshape(-1, 2),
                     **{f"PO_{c}": np.asarray([v[i] for _, v in po], t) for i, (c, t) in
                        enumerate((("W", np.float64), ("ST", np.int8), ("US", np.int8)))},
                     FO=np.asarray(list(self.fiducia), dtype=str),   # 1.24.0: la fiducia dei siti
                     **{f"FO_{c}": np.asarray([v[i] for v in self.fiducia.values()], t) for i, (c, t) in
                        enumerate((("W", np.float64), ("C", np.int64), ("X", np.int64)))},
                     FO_OK=np.asarray(sorted(self.confermati), np.int64))
            os.replace(B.STATO + ".tmp.npz", B.STATO)

    def facilita_archi(self, oggi=None):
        """per arco: ritenzione R (cala se non si richiama) x crescita della stabilita' dalla nascita, in scala
        logaritmica fino al tetto FACILITA_MAX quando S = CRESCITA_PIENA x S0 (con FSRS un richiamo distanziato
        moltiplica S per ~5: il tetto arriva in 3-4 richiami). Appena nato = 1: la soglia tarata l'11/10 resta valida"""
        oggi = LUX.orologio() if oggi is None else oggi
        R = LUX.curva(np.maximum(oggi - self.U, 0.0), self.S)
        crescita = np.minimum(1.0, np.log(self.S / self.S0) / np.log(B.CRESCITA_PIENA))
        return R * (1 + (B.FACILITA_MAX - 1) * crescita)

    def facilita(self, oggi=None):
        """per ricordo: media della facilita' dei suoi archi -> moltiplica il punteggio del richiamo"""
        f = self.facilita_archi(oggi)[self.vivi]
        idx = np.unique(self.A[self.vivi, 0], return_inverse=True)
        media = np.bincount(idx[1], f) / np.bincount(idx[1])
        return dict(zip(idx[0].tolist(), media))

    def rinforza(self, nid, oggi=None, peso=1.0):
        """richiamo riuscito del ricordo nid (consegnato all'agente): ogni suo arco cresce con FSRS (tanto piu' quanto stava
        svanendo; stesso giorno vissuto = crescita zero) e riparte da oggi. Salva lo stato. peso < 1: eco (B5)"""
        self.rinforza_archi(self.per_ricordo.get(nid, []), oggi, peso)

    def rinforza_archi(self, js, oggi=None, peso=1.0):
        """1.22.0 (l'utente 13/11, D1 di PIANO-INTERFASE-23-TRATTI.md): richiamo riuscito degli archi js (i tratti arrivati
        all'agente): crescono con FSRS e ripartono da oggi. Salva lo stato"""
        oggi = LUX.orologio() if oggi is None else oggi
        js = list(js)
        R = LUX.curva(np.maximum(oggi - self.U[js], 0.0), self.S[js])
        self.S[js] = [LUX.cresci(float(s), float(r), peso) for s, r in zip(self.S[js], R)]
        self.U[js] = oggi
        self.salva_stato()

    def spinta(self, r, ora):
        """1.12.0: predisposizione del ricordo r all'ora (secondi di parete), dimezzata ogni PREDISPOSIZIONE_EMIVITA"""
        s, t = self.pronti.get(r, (0.0, ora))
        return s * 0.5 ** (max(0.0, ora - t) / B.PREDISPOSIZIONE_EMIVITA)

    def predisponi(self, nids, ora=None, oggi=None):
        """1.12.0: dopo una consegna, ogni ricordo che condivide engrammi (peso 1/(altri ricordi che li usano), effetto
        ventaglio di Anderson 1974) o archi (stessa coppia di engrammi, x PESO_COPPIA) coi ricordi consegnati riceve una
        spinta, divisa per sqrt(engrammi del ricordo) come in richiama; si somma a quella residua"""
        ora = time.time() if ora is None else ora
        spinte = {}
        for x in nids:
            js = self.per_ricordo.get(x, [])
            gruppi = [(1.0, {int(self.A[j, 0]) for j in self.per_engramma[e]}) for e in {int(v) for j in js for v in self.A[j, 2:4]}]
            gruppi += [(B.PESO_COPPIA, self.coppie[c]) for c in {tuple(sorted(int(v) for v in self.A[j, 2:4])) for j in js}
                       if c[0] != c[1]]   # l'arco su se stesso dei ricordi di un engramma solo non e' una relazione
            for peso, ric in gruppi:
                for r in ric:
                    spinte[r] = spinte.get(r, 0) + peso / max(1, len(ric) - 1)
        # 1.21.0 (l'utente 12/11 D1, "l'arco li fa tornare in mente insieme"): l'altro capo di un arco fra ricordi
        oggi = LUX.orologio() if oggi is None else oggi
        radici = {self.catena(x)[0] for x in nids}
        for (a, b), (sr, u, _, _) in self.archi_ric.items():
            for x, y in ((a, b), (b, a)):
                if x in radici and y not in radici and y in self.ricordi:
                    spinte[y] = spinte.get(y, 0) + B.PESO_ARCO_RICORDI * float(LUX.curva(max(oggi - u, 0.0), sr))
        for r, s in spinte.items():
            if r not in nids:
                self.pronti[r] = (self.spinta(r, ora) + s / np.sqrt(self.ricordi[r]["n"]), ora)

    def _catene(self, scelta, via, quanti, stessa=True):
        """1.11.0: un ricordo con le sue correzioni occupa un posto solo. Fase 2 step b (l'utente 09/11 + 11/11,
        PIANO-FASE2-B-STESSA-FIRMA.md): dopo la prima entrano solo le catene con la stessa dominante dell'originale
        (un vettore solo); gli altri restano fuori, non consegnati ne' rinforzati. Senza dominante: da solo.
        1.21.0: stessa=False = senza la regola (la selezione da cui nascono gli archi e la coda)"""
        catene = []
        for nid in scelta:
            k = self.catena(nid)
            if len(catene) >= quanti:
                break
            d = self.ricordi[k[0]].get("dominante")
            if (not via & set(k) and all(k[0] != c[0] for c in catene)
                    and (not stessa or not catene or (d is not None and d == self.ricordi[catene[0][0]].get("dominante")))):
                catene.append(k)
        return catene

    def _coseleziona(self, radici, oggi):
        """1.21.0: arco fra ogni coppia di ricordi della stessa selezione; nasce con S_BASE, poi cresce con FSRS come gli
        archi degli engrammi (stesso giorno vissuto = crescita zero)"""
        for a, b in itertools.combinations(sorted(set(radici)), 2):
            v = self.archi_ric.get((a, b))
            if v is None:
                self.archi_ric[(a, b)] = [LUX.S_BASE, oggi, 1, 1]
            else:
                v[0] = LUX.cresci(v[0], float(LUX.curva(max(oggi - v[1], 0.0), v[0])))
                v[1], v[2], v[3] = oggi, v[2] + 1, v[3] + 1

    def firma_ora(self, nid):
        """1.21.0 (D5): la firma di adesso, dalla carica (media di C/(fattore x W) sugli archi con C0), sugli assi della
        firma della nascita; None senza firma o senza archi"""
        js = [j for j in self.per_ricordo.get(nid, ()) if self.C0[j].any()]
        f = self.ricordi.get(nid, {}).get("firma")
        if not js or not f:
            return None
        v = np.mean(self.C[js] / (self.W[js, None] * self.fattore), 0)
        return {e: float(v[B.EMOZIONI.index(e)]) for e in f if e in B.EMOZIONI}

    def _rango(self, nid):
        """1.21.0 (D4): (classe, intensita') per la coda: negativa 2 > neutra 1 > positiva 0, poi il valore della
        dominante nella firma di adesso. Senza dominante o firma: neutra, intensita' 0"""
        d = self.ricordi.get(nid, {}).get("dominante")
        f = self.firma_ora(nid)
        if d is None or not f:
            return (1, 0.0)
        return (0 if d in B.POSITIVE else 1 if d in B.NEUTRE else 2, f.get(d, 0.0))

    def consegna(self, testo, quanti=B.CONSEGNA_MAX, oggi=None, esclusi=(), ora=None, soglia=B.SOGLIA_RICHIAMO, da=None, a=None,
                 emozione=None, traccia=None, coda=None):
        """L'UNICA porta per dare ricordi all'agente (richiamo automatico, l'utente 11/10): richiama, rinforza gli archi dei
        ricordi consegnati, restituisce [(id, testo ricomposto)]. Lista vuota = nessun turno del tool.
        esclusi = codici dei ricordi gia' consegnati nella conversazione: si passa al successivo sopra soglia.
        La pagina 3D e le prove usano richiama(), che non rinforza.
        qlux (09/11): soglia (0 = il piu' vicino), finestra [da, a) sul momento del ricordo; con la finestra e
        nessun ricordo acceso dal testo, quelli della finestra in ordine di facilita'.
        1.19.0: emozione = indizio emotivo della via emotiva (richiama); traccia (dict) riceve i candidati con parole e
        senso e accordo separati, e "senza" = i ricordi che la consegna avrebbe dato senza emozione.
        1.21.0 (PIANO-FASE2-C-ARCHI-E-CODA.md): coda = codici in coda (lista del chiamante, la aggiorna sul posto).
        La selezione (le prime quanti catene, senza la regola della firma) entra in coda (in_coda, D4); si consegna la
        testa con quelli della coda e del richiamo che hanno la sua dominante; fra i ricordi della selezione nascono
        o si rinforzano gli archi fra ricordi. coda=None: come lo step b, nessun arco (qlux, consenso spento)"""
        via = {self.da_codice[c] for c in esclusi if c in self.da_codice}   # gia' nel contesto della conversazione
        scelta = [n for n, _ in self.richiama(testo, len(self.ricordi), soglia, oggi=oggi, ora=ora, emozione=emozione,
                                              traccia=traccia)]
        if da is not None:
            nella = {n for n, r in self.ricordi.items() if da <= r.get("ts", -1) < a}
            fac = self.facilita(oggi)
            accesi = [n for n in scelta if n in nella]   # poi, in coda, il resto della finestra (gli esclusi li salta il giro sotto)
            scelta = accesi + sorted(nella - set(accesi), key=lambda n: -fac.get(n, 0))
        da_coda = []
        if coda is None:
            catene = self._catene(scelta, via, quanti)
        else:
            oggi_v = LUX.orologio() if oggi is None else oggi
            vecchi = list(dict.fromkeys(self.catena(self.da_codice[c])[0] for c in coda
                                        if c in self.da_codice and c not in esclusi))
            vecchi = [r for r in vecchi if not via & set(self.catena(r))]
            via = via | {n for r in vecchi for n in self.catena(r)}   # chi e' in coda non si riseleziona
            selezione = [k[0] for k in self._catene(scelta, via, quanti, stessa=False)]
            q = B.in_coda(vecchi, selezione, lambda a, b: self._rango(a) > self._rango(b))
            gruppo = q[:1]
            d0 = self.ricordi[q[0]].get("dominante") if q else None
            if d0 is not None:
                gruppo += [r for r in q[1:] if self.ricordi[r].get("dominante") == d0][:quanti - 1]
                presi = via | {n for r in q for n in self.catena(r)}
                for nid in scelta:   # step b: anche piu' in basso nel richiamo, con la stessa dominante
                    k = self.catena(nid)
                    if len(gruppo) >= quanti:
                        break
                    if not presi & set(k) and self.ricordi[k[0]].get("dominante") == d0:
                        gruppo.append(k[0])
                        presi |= set(k)
            self._coseleziona(set(selezione) | {r for r in gruppo if r not in vecchi}, oggi_v)
            catene = [self.catena(r) for r in gruppo]
            da_coda = [r for r in gruppo if r in vecchi]
            coda[:] = [self.ricordi[r]["codice"] for r in q if r not in gruppo]
        if traccia is not None and emozione and da is None:
            senza = [n for n, p, _ in traccia.get("candidati", []) if p >= soglia]
            traccia["senza"] = [n for k in self._catene(senza, via, quanti) for n in k]
            traccia["da_coda"] = da_coda
        scelti = [n for k in catene for n in k]
        if traccia is not None and emozione and da is None:   # l'emozione ha fatto superare la soglia
            ps = {n: p for n, p, _ in traccia.get("candidati", [])}
            traccia["oltre_soglia"] = any(ps.get(n, soglia) < soglia for n in scelti)
            # revisione 11/11: nel diario solo chi potrebbe essere scelto rigiocando k fino a TRACCIA_K_MAX
            traccia["candidati"] = [x for x in traccia.get("candidati", []) if x[1] * (1 + B.TRACCIA_K_MAX) >= soglia]
        t = ora if ora is not None and np.isfinite(ora) else time.time()
        for nid in scelti:   # 1.17.0: ultimo richiamo, salvato col rinforzo
            self.R[nid] = t
        if any(n in self.errati for n in scelti) or coda is not None:   # 1.21.0: anche gli archi fra ricordi
            self.salva_stato()
        for nid in scelti:
            if nid not in self.errati:   # un ricordo corretto non si rinforza piu'
                self.rinforza(nid, oggi)
        self.predisponi(scelti, ora, oggi)
        return [(nid, self.ricordi[nid]["codice"], self.ricomponi(nid)) for nid in scelti]

    def catena(self, nid):
        """1.11.0: il ricordo originale e tutte le correzioni che lo seguono (ripensamenti compresi), dalla piu' vecchia"""
        while nid in self.corregge:
            nid = self.corregge[nid]
        k = [nid]
        for n in k:
            k += sorted(self.corretto_da.get(n, []))
        return k

    def forza(self, nid, emo):
        """S_e del punto 7 di PIANO-LUX-FASI (l'utente 24/10 + 09/11; PIANO-STEERING-RIFLESSO punto 7a, 11/11): per ogni
        engramma i del ricordo w_i = somma delle cariche (emozione emo, inglese) dei suoi archi che lo toccano,
        S_e = sum(w_i x F_i,e) / sum(w0_i), w0 dalle cariche alla nascita C0 (1.14.0).
        None = ricordo o emozione sconosciuti, ricordo senza firma"""
        if emo not in B.EMOZIONI:
            return None
        e = B.EMOZIONI.index(emo)
        r = self.ricordi.get(nid, {})
        if "dominante_nascita" in r and emo != r["dominante_nascita"]:   # 1.21.0 (D5): emozione presa dopo la nascita, la carica di adesso
            w = {}
            for j in self.per_ricordo.get(nid, ()):
                if self.C0[j].any():
                    for i in {int(self.A[j, 2]), int(self.A[j, 3])}:
                        w[i] = w.get(i, 0.0) + float(self.C[j, e])
            tot = sum(w.values())
            return sum(wi * float(self.F[i, e]) for i, wi in w.items()) / tot if tot > 0 else None
        w, w0 = {}, 0.0
        for j in self.per_ricordo.get(nid, ()):
            if self.C0[j].any():
                for i in {int(self.A[j, 2]), int(self.A[j, 3])}:
                    w[i] = w.get(i, 0.0) + float(self.C[j, e])
                    w0 += float(self.C0[j, e])
        return sum(wi * float(self.F0[i, e]) for i, wi in w.items()) / w0 if w0 > 0 else None

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

    def ricordo(self, cod):
        """1.20.0: il ricordo di codice cod (testo, firma, classe, CAMPI, nid) o None; per riflesso e barra-prefill,
        che prima lo cercavano in memoria.db"""
        n = self.da_codice.get(cod)
        return None if n is None else {**self.ricordi[n], "nid": n}

    def ricomponi(self, nid):
        arcs = sorted(self.per_ricordo.get(nid, []), key=lambda j: self.A[j, 1])
        info = self.ricordi[nid]
        pezzi = [("arco", B.param_testo(p, self.altri)) for p in info["testa"]]
        for k, j in enumerate(arcs):
            _, pos, a, b, p0, n = self.A[j]
            if k == 0:
                pezzi.append(("nodo", self.testi[a]))
            if pos == 0:
                continue
            pezzi += [("arco", B.param_testo(int(p), self.altri)) for p in self.P[p0:p0 + n]]
            pezzi.append(("nodo", self.testi[b]))
        pezzi += [("arco", B.param_testo(p, self.altri)) for p in info["coda"]]
        return B.unisci(pezzi)

    def frasi(self, nid):
        """1.22.0 (l'utente 13/11, interfase 2-3): il ricordo diviso in frasi [(testo, archi, engrammi scritti nella
        frase)]. Una frase finisce col parametro di fine frase compreso; l'arco che lo porta va alla frase dopo (porta la
        sua prima parola; la sua parola di partenza resta della frase prima). Una frase senza lettere (numero di elenco
        "2.", emoji sola) si unisce alla frase dopo, o alla prima se e' l'ultima; una che comincia con un segno che si
        attacca (":D") alla frase prima. Unite di seguito ridanno ricomponi(nid)"""
        info, out = self.ricordi[nid], []
        pezzi, js, eng = [("arco", B.param_testo(p, self.altri)) for p in info["testa"]], [], set()
        for k, j in enumerate(sorted(self.per_ricordo.get(nid, []), key=lambda j: self.A[j, 1])):
            _, pos, a, b, p0, n = self.A[j].tolist()
            js.append(j)
            if k == 0:
                pezzi.append(("nodo", self.testi[a]))
                eng.add(a)
            if pos == 0:
                continue
            ps, fine = [B.param_testo(int(p), self.altri) for p in self.P[p0:p0 + n]], False
            for i, t in enumerate(ps):
                pezzi.append(("arco", t))
                fine = fine or t in B.FINE_FRASE
                dopo = ps[i + 1] if i + 1 < len(ps) else self.testi[b]
                # revisione 13/11: i segni che si attaccano (!) ... ;) e un engramma che e' solo un punto restano con la
                # fine della frase
                if fine and len(js) > 1 and not (dopo in ",.;:!?)…" or dopo.startswith("...")):
                    out.append((B.unisci(pezzi), js[:-1], eng))
                    pezzi, js, eng, fine = [], [j], set(), False
            pezzi.append(("nodo", self.testi[b]))
            eng.add(b)
        pezzi += [("arco", B.param_testo(p, self.altri)) for p in info["coda"]]
        if any(k == "nodo" for k, _ in pezzi) or not out:
            out.append((B.unisci(pezzi), js, eng))
        else:   # dopo l'ultimo punto solo parametri (una parentesi): restano attaccati all'ultima frase
            out[-1] = (B.unisci([("nodo", out[-1][0]), *pezzi]), out[-1][1] + js, out[-1][2])
        unite = []
        for t, js, eng in out:
            # ":D" dopo un punto va con la frase prima; una frase senza lettere va con questa
            if unite and (t.startswith(tuple(",.;:!?)…")) or not any(c.isalpha() for c in unite[-1][0])):
                t0, js0, eng0 = unite.pop()
                t, js, eng = B.unisci([("nodo", t0), ("nodo", t)]), js0 + js, eng0 | eng
            unite.append((t, js, eng))
        if len(unite) > 1 and not any(c.isalpha() for c in unite[-1][0]):
            t1, js1, eng1 = unite.pop()
            t0, js0, eng0 = unite.pop()
            unite.append((B.unisci([("nodo", t0), ("nodo", t1)]), js0 + js1, eng0 | eng1))
        return unite







    def _vs(self):
        """1.22.0: vettori della via semantica, con gli engrammi-emoji rifatti sul loro significato (zero se non ne
        hanno); calcolati al primo accendi, non all'avvio (l'embedder puo' non esserci ancora)"""
        if self._Vs is None:
            Vs = self.V.copy()
            em = [i for i, t in enumerate(self.testi) if B.e_emoji(t)]
            con = [(i, g) for i in em for g in [B.significato(self.testi[i])] if g]
            if con:
                Vs[[i for i, _ in con]] = B.embed([g for _, g in con]).astype(B.VTIPO)
            Vs[[i for i in em if B.significato(self.testi[i]) is None]] = 0
            self._Vs = Vs
        return self._Vs

    def accendi(self, testo):
        """innesco: via testuale (stesso engramma = 1) e via semantica (bge-m3, coseno sopra soglia riscalato 0-1)"""
        att = {}
        nodi = [t for k, t in T.taglia(testo) if k == "nodo"]
        if not nodi:
            return att
        for t in nodi:
            i = self.chiavi.get(B.chiave(t))
            if i is not None:
                att[i] = 1.0
        q = [B.significato(t) if B.e_emoji(t) else t for t in nodi]   # 1.22.0: le emoji per significato
        idx = [k for k, v in enumerate(q) if v]
        if not idx:
            return att
        S = B.coseni(B.embed([q[k] for k in idx]), self._vs())
        for row in S:
            for i in np.where(row >= B.SOGLIA_SEM)[0]:
                att[int(i)] = max(att.get(int(i), 0), float((row[i] - B.SOGLIA_SEM) / (1 - B.SOGLIA_SEM)))
        return att

    def sovrapposizione(self, testo, nid):
        """B6 (l'utente 01/11 sera, cattura nel behavioral tagging): engrammi del testo (n) e quanti coincidono con gli
        engrammi del ricordo nid (presi), con la regola di accendi: stessa chiave o coseno bge-m3 >= SOGLIA_SEM"""
        nodi = [t for k, t in T.taglia(testo) if k == "nodo"]
        mio = sorted({int(e) for j in self.per_ricordo.get(nid, []) for e in self.A[j, 2:4]})
        if not nodi or not mio:
            return len(nodi), 0
        S = B.coseni(B.embed(nodi), self.V[mio])
        presi = sum(self.chiavi.get(B.chiave(t)) in mio or bool((row >= B.SOGLIA_SEM).any()) for t, row in zip(nodi, S))
        return len(nodi), int(presi)

    def _engrammi(self, nid):
        return sorted({int(e) for j in self.per_ricordo.get(nid, []) for e in self.A[j, 2:4]})

    def _vicini(self, nid, m):
        """1.24.0 (D2): i ricordi nid e m dicono la stessa cosa: nei due versi almeno CONFERMA_QUOTA dei loro engrammi
        ha un compagno nell'altro (stesso engramma o coseno bge-m3 >= SOGLIA_SEM, la regola di accendi). Tutti e due
        sono gia' nel Lux: niente embedder"""
        a, b = self._engrammi(nid), self._engrammi(m)
        if not a or not b:
            return False
        S = B.coseni(self.V[a].astype(np.float32), self.V[b]) >= B.SOGLIA_SEM
        return min(S.any(1).mean(), S.any(0).mean()) >= B.CONFERMA_QUOTA




    def accordi(self, nids, emozione):
        """1.19.0: accordo emotivo dei ricordi nids con l'indizio (emozione = {"assi": nomi inglesi, "q": vettore di
        lunghezza 1}) = coseno fra il profilo del ricordo sugli stessi assi e q"""
        cols = [B.EMOZIONI.index(a) for a in emozione["assi"]]
        Z = self.profz[np.searchsorted(self.prof_nid, np.asarray(nids, np.int64))][:, cols]
        Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9
        return Z @ np.asarray(emozione["q"], np.float64)

    def richiama(self, testo, quanti=3, soglia=B.SOGLIA_RICHIAMO, oggi=None, ora=None, emozione=None, traccia=None, att=None):
        """scelta: per ogni indice di ricordo la somma delle attivazioni dei suoi engrammi, pesate 1/log(1+ricordi che
        usano l'engramma) (gli engrammi comuni contano poco) e divise per sqrt(engrammi del ricordo) (i lunghi non vincono
        sempre), poi moltiplicate per la facilita' del ricordo (archi vivi). Tarato l'11/10 su 40 indizi: soglia 0.8, nessuna propagazione nella scelta (abbassava da 35 a 30).
        1.12.0: poi per la predisposizione lasciata dalle consegne (1 + spinta, fino a PREDISPOSIZIONE_MAX), solo sui
        ricordi che l'indizio ha gia' acceso."""
        punti = {}
        for i, a in (self.accendi(testo) if att is None else att).items():   # 1.22.0: att gia' calcolata
            ric = {int(self.A[j, 0]) for j in self.per_engramma.get(i, ())}
            for r in ric:
                punti[r] = punti.get(r, 0) + a / np.log(1 + len(ric))
        fac = self.facilita(oggi)
        ora = time.time() if ora is None else ora
        for r in punti:
            punti[r] *= fac[r] / np.sqrt(self.ricordi[r]["n"]) * min(B.PREDISPOSIZIONE_MAX, 1 + self.spinta(r, ora))
        if emozione and punti:
            # 1.19.0 (11/11): punteggio x (1 + k x accordo emotivo), solo sui ricordi gia' accesi da parole e
            # senso: l'emozione puo' far superare la soglia a quelli, da sola non ne accende nessuno
            nids = list(punti)
            acc = self.accordi(nids, emozione)
            if traccia is not None:
                traccia["candidati"] = sorted(([n, float(punti[n]), float(a)] for n, a in zip(nids, acc)),
                                              key=lambda x: -x[1])
            for n, a in zip(nids, acc):
                punti[n] *= max(0.0, 1 + float(emozione["k"]) * float(a))
        return [x for x in sorted(punti.items(), key=lambda x: -x[1])[:quanti] if x[1] >= soglia]
