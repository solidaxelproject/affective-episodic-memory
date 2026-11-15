"""Lux degli engrammi: mixin Ricombina della classe Lux: la ricombinazione mnemonica (1.22.0) e i ponti (1.23.0).
Parte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano
lux_engrammi, che riesporta tutto."""
import lux_base as B
import itertools
import time
import numpy as np
import lux as LUX   # solo le funzioni FSRS e l'orologio vissuto (lettura): il Lux originale non si tocca


class Ricombina:
    def _guida(self, att, Fa, col):
        """1.22.0 (l'utente 13/11, prova v2b + ritocco): (engramma, firma sui 44 assi, firma nella scala delle firme dei
        ricordi) dell'engramma acceso piu' importante, o (None, None, None). Firma = cariche di tutti i suoi archi vivi
        pesate da F x W; importanza = acceso x max(0, S_MAX - ln fan) x ln(1 + fan) x forza media dei suoi archi x
        ln(1 + ||firma|| / normC). La seconda firma toglie fattore e W dalle cariche (come firma_ora): e' l'impronta
        sull'omeostato (l'utente 13/11 sera: una ricombinazione imprime solo l'emozione del vettore)"""
        k = self.vivi & self.C.any(1)
        w = (Fa * self.W)[k].astype(np.float64)
        C, a, b = self.C[k][:, col].astype(np.float64), self.A[k, 2], self.A[k, 3]
        Cz = C / (self.W[k, None].astype(np.float64) * self.fattore[col] + 1e-12)
        n = len(self.V)
        S, Sz, N, cnt = np.zeros((n, len(col))), np.zeros((n, len(col))), np.zeros(n), np.zeros(n)
        d = a != b   # un arco su se stesso conta una volta
        for idx, m in ((a, slice(None)), (b[d], d)):
            np.add.at(S, idx, C[m] * w[m][:, None])
            np.add.at(Sz, idx, Cz[m] * w[m][:, None])
            np.add.at(N, idx, w[m])
            np.add.at(cnt, idx, 1)
        meglio, imp_max = None, 0.0
        for i, x in att.items():
            if N[i] <= 0:
                continue
            f = S[i] / N[i]
            imp = (x * max(0.0, B.S_MAX - float(np.log(self.fan[i]))) * float(np.log1p(self.fan[i])) * N[i] / cnt[i]
                   * float(np.log1p(np.linalg.norm(f) / self.normC)))
            if imp > imp_max:
                meglio, imp_max = (i, f, Sz[i] / N[i]), imp
        return meglio or (None, None, None)

    def _dai_ponti(self, att):
        """1.23.0 (B0): ({engramma: attivazione}, {ricordo: attivazione}) che arrivano dai ponti all'altra parte. Per ogni
        ponte con un capo acceso: acceso x peso / ponti di quel capo (effetto ventaglio, Anderson 1974), tetto 1; il
        ricordo e' quello dell'altro capo dove il ponte e' nato (revisione 13/11: non tutti i ricordi dell'engramma).
        Serve solo all'affioramento: ricomponi e frasi non vedono i ponti"""
        grado, pa, dal = {}, {}, {}
        for a, b in self.ponti:
            grado[a], grado[b] = grado.get(a, 0) + 1, grado.get(b, 0) + 1
        for (a, b), (w, _, _, ra, rb) in self.ponti.items():
            for x, y, ry in ((a, b, rb), (b, a, ra)):
                if x in att:
                    v = min(1.0, att[x]) * w / grado[x]
                    pa[y] = min(1.0, pa.get(y, 0.0) + v)
                    dal[ry] = max(dal.get(ry, 0.0), v)
        return pa, dal

    def _aggiorna_ponti(self, att):
        """1.23.0 (B3, B6): i ponti con tutti e due i capi forti (accensione >= PONTE_A1) si rinforzano, w += G (1 - w),
        e se provvisori diventano stabili (cattura, Frey e Morris 1997) con peso almeno PONTE_W_CATTURA; con un capo forte
        e l'altro moderato (PONTE_A0 <= x < PONTE_A1) perdono w -= D sin(pi (x - A0) / (A1 - A0)) (ramo discendente della
        U, Ritvo 2019). x = accensione dal messaggio, mai quella dai ponti (niente ponti che si rinforzano da soli).
        ponytail: niente cattura per evento emotivo (B3 b) ne' bonus emotivo notturno (B4.2): i dati non danno la misura.
        Torna True se qualcosa e' cambiato"""
        cambiato = False
        for (a, b), v in self.ponti.items():
            lo, hi = sorted((min(1.0, att.get(a, 0.0)), min(1.0, att.get(b, 0.0))))
            if hi < B.PONTE_A1 or lo < B.PONTE_A0:
                continue
            if lo >= B.PONTE_A1:
                v[0] = max(v[0] + B.PONTE_G * (1 - v[0]), B.PONTE_W_CATTURA)
                v[1] = v[2] = 1
            else:
                v[0] = max(0.0, v[0] - B.PONTE_D * float(np.sin(np.pi * (lo - B.PONTE_A0) / (B.PONTE_A1 - B.PONTE_A0))))
            cambiato = True
        return cambiato

    def _nascite(self, att, presi):
        """1.23.0 (B1, B2): ponti nuovi fra i ricordi dei tratti mostrati. Per ogni coppia di ricordi, se almeno uno e'
        stabile (S medio dei suoi archi sopra la mediana dei ricordi), la coppia di engrammi (uno per tratto) con
        accensione piu' alta (prodotto), entrambi forti (>= PONTE_A1), non comuni (ln fan < S_MAX: un engramma comune
        non da' diffusione, revisione 13/11), non gia' legati da un arco o da un ponte, e nuovi (nessun ricordo li
        contiene tutti e due) o con carica alta (||C|| medio di uno dei due ricordi sopra la media). Ne nascono al
        massimo PONTI_PER_RICHIAMO, provvisori, peso PONTE_W0"""
        if len(presi) < 2:
            return
        x = lambda e: min(1.0, att.get(e, 0.0))   # noqa: E731
        ric = lambda e: {int(self.A[j, 0]) for j in self.per_engramma.get(e, ())}   # noqa: E731
        idx = np.unique(self.A[self.vivi, 0], return_inverse=True)
        sm = dict(zip(idx[0].tolist(), np.bincount(idx[1], self.S[self.vivi]) / np.bincount(idx[1])))
        cm = dict(zip(idx[0].tolist(), np.bincount(idx[1], np.linalg.norm(self.C[self.vivi], axis=1)) / np.bincount(idx[1])))
        s_med, c_med = float(np.median(list(sm.values()))), float(np.mean(list(cm.values())))
        nuovi = []
        for (n1, _, _, e1), (n2, _, _, e2) in itertools.combinations(presi, 2):
            if max(sm.get(n1, 0), sm.get(n2, 0)) <= s_med:
                continue
            alta = max(cm.get(n1, 0), cm.get(n2, 0)) > c_med
            forti = [[e for e in es if x(e) >= B.PONTE_A1 and np.log(self.fan[e]) < B.S_MAX] for es in (e1, e2)]
            meglio = None
            for a in forti[0]:
                for b in forti[1]:
                    k = (min(a, b), max(a, b))
                    if a == b or k in self.ponti or k in self.coppie or not (alta or not ric(a) & ric(b)):
                        continue
                    if meglio is None or x(a) * x(b) > meglio[0]:
                        meglio = (x(a) * x(b), k, (n1, n2) if k[0] == a else (n2, n1))
            if meglio:
                nuovi.append(meglio)
        nuovi = list({k: (p, k, r) for p, k, r in sorted(nuovi, key=lambda c: c[0])}.values())   # una k, un posto
        for _, k, (ra, rb) in sorted(nuovi, key=lambda c: -c[0])[:B.PONTI_PER_RICHIAMO]:
            self.ponti[k] = [B.PONTE_W0, 0, 1, ra, rb]

    def _attivazione(self, att, js, eng, Fa, col, du, D, D_norm):
        """1.22.0: A_j degli archi js di una frase (RICERCA-RICHIAMO-EMOTIVO.md C1): forza + diffusione + senso + carica
        + umore. La diffusione conta solo gli engrammi scritti nella frase (eng): la parola di partenza dell'arco che
        apre la frase sta nella frase prima"""
        js = np.asarray(js)
        Cu = self.C[js][:, col].astype(np.float64)
        cos = (Cu @ du) / (np.linalg.norm(Cu, axis=1) * (np.linalg.norm(du) + 1e-12) + 1e-12) if D > 0 else 0.0
        diff = np.asarray([sum(att.get(e, 0.0) * (B.S_MAX - np.log(self.fan[e]))
                               for e in {int(self.A[j, 2]), int(self.A[j, 3])} & eng) for j in js])
        return (np.log(np.maximum(Fa[js], 1e-6)) + diff + B.LAMBDA_W * self.W[js].astype(np.float64)
                + B.GAMMA * np.log1p(np.linalg.norm(self.C[js], axis=1) / self.normC) + B.LAMBDA_0 * (D / D_norm) * cos)

    def ricombina(self, testo, numero=1, oggi=None, esclusi=(), ora=None, soglia=B.SOGLIA_RICHIAMO, emozione=None,
                  traccia=None, coda=None):
        """1.22.0 (l'utente 13/11, interfase 2-3, PIANO-INTERFASE-23-TRATTI.md): la ricombinazione mnemonica di
        memorinvolontaria. Candidati = ricordi in coda + i primi RICORDI_TRATTI del richiamo, se almeno uno passa la
        soglia (senza esclusi e ricordi corretti); di ognuno la frase accesa piu' attiva (A_j); affiorano i tratti sopra
        TAU, i piu' attivi prima, al massimo TRATTI_MAX e TOKEN_MAX. Rinforza solo gli archi dei tratti (D1). Coda e archi fra ricordi come
        la 1.21.0. Torna None (niente) o {"risposta", "nid", "codici", "archi", "dominante", "impronta"}: dominante =
        quella dell'engramma acceso piu' importante (il vettore), impronta = la sua firma per l'omeostato"""
        oggi = LUX.orologio() if oggi is None else oggi
        ora = time.time() if ora is None else ora
        via = {self.da_codice[c] for c in esclusi if c in self.da_codice} | self.errati
        att = self.accendi(testo)
        punti = [(n, p) for n, p in self.richiama(testo, len(self.ricordi), 0.0, oggi=oggi, ora=ora, emozione=emozione,
                                                   traccia=traccia, att=att) if n not in via]
        # la soglia decide SE affiora qualcosa (come prima); se si', i tratti escono dai primi RICORDI_TRATTI anche sotto
        # soglia (come la prova del 13/11): pezzi di ricordi piu' deboli si ricombinano con quello che ha passato la soglia
        sopra = [n for n, p in punti if p >= soglia]
        selezione = [n for n, _ in punti[:B.RICORDI_TRATTI]] if sopra else []
        pa, dal = self._dai_ponti(att)   # 1.23.0 (B0): un ponte puo' far venire in mente un altro ricordo
        acc = {**pa, **{e: max(a, pa.get(e, 0.0)) for e, a in att.items()}}
        if sopra:
            selezione += [r for r in sorted(dal, key=lambda r: -dal[r]) if r not in via and r not in selezione
                          and r in self.ricordi][:B.RICORDI_TRATTI]
        vecchi = [] if coda is None else [n for c in dict.fromkeys(coda) for n in [self.da_codice.get(c)]
                                          if n is not None and n not in via]
        u, assi, calma, D, D_norm = B.umore44()
        col = [B.EMOZIONI.index(a) for a in assi]
        Fa = self.facilita_archi(oggi)
        cand = []
        for n in dict.fromkeys(vecchi + selezione):
            meglio = None
            for t, js, eng in self.frasi(n):
                # revisione 13/11: un ricordo in coda e' gia' stato richiamato, la sua frase piu' attiva entra anche se il
                # messaggio nuovo non ne accende nessuna parola (senza, la coda non usciva quasi mai: 6 su 236)
                if js and (n in vecchi or eng & acc.keys()):
                    a = float(self._attivazione(acc, js, eng, Fa, col, u - calma, D, D_norm).max())
                    if meglio is None or a > meglio[0]:
                        meglio = (a, n, " ".join(t.split()), js, eng)   # un tratto per riga: niente a capo dentro
            if meglio:
                cand.append(meglio)
        presi, tok = [], 0.0
        for a, n, t, js, eng in sorted(cand, key=lambda c: -c[0]):
            if a > B.TAU and len(presi) < B.TRATTI_MAX and tok + len(t) / B.CAR_TOKEN <= B.TOKEN_MAX:
                presi.append((n, t, js, eng))
                tok += len(t) / B.CAR_TOKEN
        mostrati = [n for n, _, _, _ in presi]
        cambiato = self._aggiorna_ponti(att)   # 1.23.0: prima i ponti che c'erano, poi quelli nuovi
        self._nascite(att, presi)
        if coda is not None:   # 1.21.0: la selezione entra in coda; chi e' mostrato ne esce
            nuovi = [n for n in sopra[:B.CONSEGNA_MAX] if n not in vecchi]
            q = B.in_coda(vecchi, nuovi, lambda a, b: self._rango(a) > self._rango(b))
            self._coseleziona(set(sopra[:B.CONSEGNA_MAX]) | {n for n in mostrati if n not in vecchi}, oggi)
            coda[:] = [self.ricordi[n]["codice"] for n in q if n not in mostrati]
        if traccia is not None and emozione:   # 1.19.0, come consegna: il diario della via emotiva
            ps = {n: p for n, p, _ in traccia.get("candidati", [])}
            traccia["senza"] = [n for n, p, _ in traccia.get("candidati", []) if p >= soglia and n not in via][:B.RICORDI_TRATTI]
            traccia["da_coda"] = [n for n in mostrati if n in vecchi]
            # revisione 13/11: l'emozione conta se ha deciso che affiorasse qualcosa; testa = il primo del richiamo
            # (i tratti mostrati sono in ordine di attivazione, non di richiamo): la usa !verifica emotiva!
            traccia["oltre_soglia"] = any(ps.get(n, soglia) < soglia for n in sopra)
            traccia["testa"] = sopra[:1]
            traccia["candidati"] = [x for x in traccia.get("candidati", []) if x[1] * (1 + B.TRACCIA_K_MAX) >= soglia]
        if not presi:
            if coda is not None or cambiato:   # 1.23.0: anche i ponti cambiati (revisione 13/11)
                self.salva_stato()
            return None
        for n in mostrati:   # 1.17.0: ultimo richiamo
            self.R[n] = ora
        archi = [j for _, _, js, _ in presi for j in js]
        self.rinforza_archi(archi, oggi)   # D1: solo i tratti; salva lo stato (anche coda e archi fra ricordi)
        self.predisponi(mostrati, ora, oggi)
        _, firma, fz = self._guida(att, Fa, col)
        return {"risposta": "\n".join([f"{numero}° ricombinazione mnemonica"] + [t for _, t, _, _ in presi]),
                "nid": mostrati, "codici": [self.ricordi[n]["codice"] for n in mostrati], "archi": archi,
                "dominante": None if firma is None else assi[int(np.argmax(firma))],
                "impronta": None if fz is None else {e: float(v) for e, v in zip(assi, fz)}}
