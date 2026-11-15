"""Lux degli engrammi: lavori della notte: riaccensione, riconsolidamento, avvicinamento, ponti, sbiadimento.
Parte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano
lux_engrammi, che riesporta tutto."""
import lux_base as B
import json
import os
import numpy as np
import salienza as SA
import lux as LUX   # solo le funzioni FSRS e l'orologio vissuto (lettura): il Lux originale non si tocca
import lux_richiamo as RI


def _rodaggio(giorni):
    return next((f for g, f in B.RODAGGIO if giorni < g), 1.0)


def _voci(percorso):
    """righe json di un file (le rotte si saltano, file assente = nessuna)"""
    try:
        with open(percorso, encoding="utf-8") as f:
            righe = f.readlines()
    except FileNotFoundError:
        return []
    out = []
    for r in righe:
        try:
            out.append(json.loads(r))
        except ValueError:
            pass
    return out


def riconsolida(oggi=None):
    """1.14.0 (punto 6 di PIANO-LUX-FASI, PIANO-1.14-RICONSOLIDAMENTO.md): per ogni ricordo consegnato (diario del
    riflesso) non ancora in M, la prima risposta dell'agente dello stesso flusso entro FINESTRA_MOMENTO (registro di
    firma_subito) e' il momento. Riga in M sempre; con l'effetto acceso (rodaggio_da e SOGLIA_SORPRESA) e sorpresa sopra
    soglia la carica degli archi del ricordo si sposta verso il momento: passo = rodaggio x 0.2 / (1 + log(S/S0)) x
    (momento - C), somma della notte entro PASSO_MAX; F ricalcolata; S0 e S scalate come la stabilita' iniziale
    (punto 8). Tutto sotto lucchetto rileggendo i file dal disco; alla fine META toccato: il servizio ricarica.
    Correzioni, ricordi corretti e sconosciuti: solo M (D4)."""
    oggi = LUX.orologio() if oggi is None else oggi
    reg = {}
    for v in _voci(B.GIORNATA):   # il registro: l'ultima riga per (ts, testo) vale
        reg[(v.get("ts"), v.get("testo"))] = v
    agente = sorted((v for v in reg.values() if str(v.get("autore", "")).startswith("@agente") and not v.get("forzato")),
                 key=lambda v: v["ts"])
    cons = [(float(v["ts"]), int(n), v.get("flusso")) for v in _voci(B.DIARIO_RIFLESSO)
            if v.get("memorinvolontaria") and v.get("nid") for n in v["nid"]]
    n = len(B.EMOZIONI)
    with B.lucchetto():
        if not os.path.exists(B.STATO):   # Lux appena costruito: nessun rinforzo, niente da riconsolidare ancora
            return {"consegne": len(cons), "momenti": 0, "spostati": 0, "sorpresa_media": None, "effetto": 0.0}
        z, s = B.carica_npz(), dict(np.load(B.STATO))
        L = RI.Lux.struttura(B.DIR)
        M = z.get("M", np.zeros((0, 4 + n)))
        fatti = {(round(float(t), 3), int(r)) for r, t in M[:, :2]}
        da = float(z.get("rodaggio_da", np.nan))
        acceso = np.isfinite(da) and B.SOGLIA_SORPRESA is not None and oggi >= da
        fattore = _rodaggio(oggi - da) if acceso else 0.0
        nuove, passi = [], {}
        for tc, nid, fl in cons:
            if (round(tc, 3), nid) in fatti:
                continue
            r = next((v for v in agente if tc < v["ts"] <= tc + B.FINESTRA_MOMENTO
                      and (None in (fl, v.get("flusso")) or fl == v.get("flusso"))), None)   # voci di prima: senza flusso
            if r is None:   # nessuna risposta ancora: la notte dopo
                continue
            fatti.add((round(tc, 3), nid))
            m = np.asarray([r["firma"].get(e, np.nan) if r.get("firma") else np.nan for e in B.EMOZIONI], np.float64)
            mc = m * z["fattore"] if "fattore" in z else m   # 1.15.0: il momento nella scala della carica
            js = [j for j in L.per_ricordo.get(nid, ()) if L.C0[j].any()]
            k = ~np.isnan(m)
            rms = float(np.sqrt(np.mean((mc[k] - L.C[js[0]][k] / L.W[js[0]]) ** 2))) if js and k.any() else np.nan
            nuove.append([nid, tc, r["ts"], rms, *m])
            if acceso and js and nid not in L.errati and nid < B.PRIMO_CORREZIONE and rms >= B.SOGLIA_SORPRESA:
                for j in js:
                    alfa = B.ALFA / (1 + max(0.0, float(np.log(s["S"][j] / s["S0"][j]))))
                    passi[j] = passi.get(j, 0.0) + np.where(k, fattore * alfa * (np.nan_to_num(mc) * L.W[j] - L.C[j]), 0.0)
        if passi:
            _applica_passi(z, s, L, passi)
        if nuove:
            z["M"] = np.concatenate([M, np.asarray(nuove, np.float64)])
        if nuove or passi:
            B.salva_npz(z)   # prima M: dopo un crash qui la consegna non si rifa' (niente doppio passo)
            if passi:
                np.savez(B.STATO + ".tmp.npz", **s)
                os.replace(B.STATO + ".tmp.npz", B.STATO)
            os.utime(B.META)   # il servizio ricarica
    rms = [x[3] for x in nuove if not np.isnan(x[3])]
    return {"consegne": len(cons), "momenti": len(nuove), "spostati": len(passi),
            "sorpresa_media": round(float(np.mean(rms)), 3) if rms else None, "effetto": fattore}


def _applica_passi(z, s, L, passi):
    """passi {arco: spostamento della carica} con il tetto PASSO_MAX sulla firma grezza; F ricalcolata, S0 e S scalate
    come la stabilita' iniziale (punto 8). Da riconsolida (1.14.0) e avvicina (1.21.0); z e s cambiano sul posto"""
    C, S, S0 = z["C"].copy(), s["S"].copy(), s["S0"].copy()
    ranghi = SA.ranghi(z)
    for j, p in passi.items():
        vecchia = C[j].copy()
        C[j] = vecchia + np.clip(p / L.W[j], -B.PASSO_MAX, B.PASSO_MAX) * L.W[j]   # 1.16.0: freno sulla firma grezza
        rg = ranghi.get(int(z["A"][j, 0]), (0.0, 0.0))
        g = (z["fattore"] if "fattore" in z else 1.0) * L.W[j]   # 1.15.0-1.16.0: la stabilita' vuole la firma grezza
        q = (SA.stabilita_iniziale(C[j] / g, *rg, LUX.S_BASE, B.SOGLIA_FIRMA)
             / SA.stabilita_iniziale(vecchia / g, *rg, LUX.S_BASE, B.SOGLIA_FIRMA))
        S0[j] *= q
        S[j] *= q
    z.update(C=C, F=B.firme_engrammi(z["A"], C, len(z["V"])))
    s.update(S=S, S0=S0)


def avvicina(oggi=None):
    """1.21.0 (l'utente 11/11 punto 2 + 12/11 D2, D3, D5): per ogni arco fra ricordi con co-selezioni non ancora lavorate
    (RA_P) fra due ricordi veri con dominanti diverse, la carica di ognuno si sposta verso il profilo dell'altro (media
    di C/W sui suoi archi con C0): x = rodaggio x ALFA / (1 + FRENO_LEGATI x log(S/S0)) x forza dell'arco,
    q = 1 - (1 - x)^P, passo = q x (profilo dell'altro x W - C), tetto PASSO_MAX (_applica_passi). Poi (D5) la
    dominante dei ricordi toccati si ricalcola dalla carica (firma_ora, memoria.dominante); la prima volta che cambia
    resta dominante_nascita. RA_P si azzera su tutti gli archi: le co-selezioni di oggi sono consumate anche quando
    l'arco non sposta niente (stessa dominante, correzioni), cosi' non si accumulano per una notte futura. Sotto lucchetto rileggendo dal disco; META toccato: il servizio ricarica"""
    import memoria   # dominante, CON_VETTORE, PETALO (sys.path ha gia' /data/memoria-episodica-affettiva)
    oggi = LUX.orologio() if oggi is None else oggi
    with B.lucchetto():
        if not os.path.exists(B.STATO):
            return {"archi": 0, "spostati": 0, "rodaggio": 0.0, "dominanti": 0}
        z, s = B.carica_npz(), dict(np.load(B.STATO))
        if "avvicina_da" not in z or "RA" not in s or not (s["RA_P"] > 0).any():
            return {"archi": 0, "spostati": 0, "rodaggio": 0.0, "dominanti": 0}
        L = RI.Lux.struttura(B.DIR)
        rod = _rodaggio(oggi - float(z["avvicina_da"]))
        prof = {}

        def profilo(n):
            if n not in prof:
                js = [j for j in L.per_ricordo.get(n, ()) if L.C0[j].any()]
                prof[n] = (js, np.mean(L.C[js] / L.W[js, None], 0) if js else None)
            return prof[n]

        passi, toccati = {}, set()
        P = s["RA_P"]
        for (a, b), sr, u, p in zip(s["RA"].tolist(), s["RA_S"], s["RA_U"], P):
            if p <= 0 or any(n >= B.PRIMO_CORREZIONE or n in L.errati or n not in L.ricordi for n in (a, b)):
                continue
            if L.ricordi[a].get("dominante") == L.ricordi[b].get("dominante"):
                continue
            forza = float(LUX.curva(max(oggi - float(u), 0.0), float(sr)))
            (ja, pa), (jb, pb) = profilo(a), profilo(b)
            if pa is None or pb is None:
                continue
            for js, verso in ((ja, pb), (jb, pa)):
                for j in js:
                    x = rod * B.ALFA / (1 + B.FRENO_LEGATI * max(0.0, float(np.log(s["S"][j] / s["S0"][j])))) * forza
                    passi[j] = passi.get(j, 0.0) + (1 - (1 - x) ** int(p)) * (verso * L.W[j] - L.C[j])
            toccati |= {a, b}
        archi = int((P > 0).sum())
        s["RA_P"] = np.zeros_like(P)
        cambiate = 0
        if passi:
            _applica_passi(z, s, L, passi)
            m = json.load(open(B.META))
            fat = z["fattore"] if "fattore" in z else np.ones(len(B.EMOZIONI), np.float32)
            for n in sorted(toccati):
                r = m["ricordi"][str(n)]
                js = profilo(n)[0]
                v = np.mean(z["C"][js] / (L.W[js, None] * fat), 0)
                f = {e: float(v[B.EMOZIONI.index(e)]) for e in (r.get("firma") or {}) if e in B.EMOZIONI}
                d = memoria.dominante(f) if f else None
                if d is not None and d != r.get("dominante"):
                    r.setdefault("dominante_nascita", r.get("dominante"))
                    r["dominante"] = d
                    cambiate += 1
            B.salva_npz(z)
            if cambiate:
                json.dump(m, open(B.META + ".tmp", "w"), ensure_ascii=False)
                os.replace(B.META + ".tmp", B.META)
        np.savez(B.STATO + ".tmp.npz", **s)
        os.replace(B.STATO + ".tmp.npz", B.STATO)
        os.utime(B.META)
    return {"archi": archi, "spostati": len(passi), "rodaggio": rod, "dominanti": cambiate}


def pota_ponti():
    """1.23.0 (B4, PIANO-PONTI-123.md), di notte: 1. via i ponti provvisori (la marca decade, Frey e Morris 1997); 2-3. i
    ponti stabili non usati nel giorno perdono il 18% del peso, tranne il 20% piu' forte (de Vivo 2017); 4. via sotto
    PONTE_W_MIN. Niente tetto per engramma (l'utente 13/11 notte: nella mente non c'e', c'e' l'effetto ventaglio, gia' in
    _dai_ponti). "Usato" e' un segno (PO_US) che
    ricombina mette e la notte toglie (revisione 13/11: l'orologio vissuto avanza prima della notturna). Sotto
    lucchetto rileggendo dal disco; il servizio poi ricarica"""
    vuoto = {"ponti": 0, "provvisori": 0, "calati": 0, "tagliati": 0}
    with B.lucchetto():
        if not os.path.exists(B.STATO):
            return vuoto
        s = dict(np.load(B.STATO))
        if "PO" not in s or not len(s["PO"]):
            return vuoto
        W, ST, US = s["PO_W"].copy(), s["PO_ST"], s["PO_US"]
        tieni = ST == 1
        protetti = np.zeros(len(W), bool)   # revisione 13/11: per rango, col quantile i pesi uguali non calavano mai
        st = np.nonzero(tieni)[0]
        protetti[st[np.argsort(-W[st], kind="stable")[:int(np.ceil(B.PONTE_PROTETTI * len(st)))]]] = True
        calo = tieni & (US == 0) & ~protetti
        W[calo] *= B.PONTE_CALO
        forti = tieni & (W >= B.PONTE_W_MIN)
        s.update(PO=s["PO"][forti], PO_R=s["PO_R"][forti], PO_W=W[forti], PO_ST=ST[forti],
                 PO_US=np.zeros(int(forti.sum()), np.int8))
        np.savez(B.STATO + ".tmp.npz", **s)
        os.replace(B.STATO + ".tmp.npz", B.STATO)
    return {"ponti": int(forti.sum()), "provvisori": int((~tieni).sum()), "calati": int(calo.sum()),
            "tagliati": int((tieni & ~forti).sum())}


def riaccendi():
    """1.17.0 (punto 3): i messaggi del registro (giornata-firma.jsonl, l'utente e l'agente) arrivati dopo riacceso_fino accendono
    gli engrammi con la regola di accendi (stessa chiave o coseno >= SOGLIA_SEM): acceso = giorno del messaggio e una
    accensione in piu', una per giorno. Taglio ed embed FUORI dal lucchetto (revisione 11/11: il servizio a un filo e
    firma_subito non aspettano); dentro solo rilettura, controllo e scrittura. META toccato: il servizio ricarica"""
    reg = {}
    for v in _voci(B.GIORNATA):
        reg[(v.get("ts"), v.get("testo"))] = v
    z = B.carica_npz()
    if "E_nato" not in z:
        return {"messaggi": 0, "engrammi": 0}
    fino = float(z["riacceso_fino"])
    voci = sorted((v for v in reg.values() if isinstance(v.get("ts"), (int, float)) and v["ts"] > fino
                   and str(v.get("testo") or "").strip()), key=lambda v: v["ts"])
    if not voci:
        return {"messaggi": 0, "engrammi": 0}
    L = RI.Lux.struttura(B.DIR)
    accesi = [(B.giorno_di(v["ts"]), L.accendi(v["testo"])) for v in voci]   # gli indici restano: aggiungi mette in coda
    with B.lucchetto():
        z = B.carica_npz()
        if float(z["riacceso_fino"]) != fino:   # un altro riaccendi nel frattempo
            return {"messaggi": 0, "engrammi": 0}
        E = (z["E_nato"].copy(), z["E_acceso"].copy(), z["E_accensioni"].copy())
        prima = E[2].copy()
        for d, att in accesi:
            B._accendi_contatori(E, dict.fromkeys(att, d))
        z.update(E_nato=E[0], E_acceso=E[1], E_accensioni=E[2], riacceso_fino=np.float64(voci[-1]["ts"]))
        B.salva_npz(z)
        os.utime(B.META)
    return {"messaggi": len(voci), "engrammi": int((E[2] != prima).sum())}


def freno_archi(A, S, S0, E, ranghi, errati, oggi):
    """1.18.0: le tre parti del freno che non dipendono dall'emozione, per arco, fra 0 e 1"""
    rip = np.clip(np.log(np.maximum(np.divide(S, S0, out=np.ones_like(S, dtype=np.float64), where=S0 > 0), 1.0))
                  / np.log(100.0), 0, 1)
    nato, acceso, acc = (x.astype(np.float64) for x in E)
    im = np.where(acc > 0, (acceso - nato) / np.maximum(acc, 1), 0.0)
    t = np.maximum(oggi - acceso, 0.0)
    ap_e = np.where(im + t > 0, im / np.maximum(im + t, 1e-9), 0.0)
    ap = (ap_e[A[:, 2]] + ap_e[A[:, 3]]) / 2
    ap[np.isin(A[:, 0], list(errati))] = 0.0   # ricordo corretto: scopo raggiunto
    imp = np.asarray([np.mean(ranghi.get(int(r), (0.0, 0.0))) for r in A[:, 0]])
    return ((1 - B.FRENO["ripetizione"] * rip) * (1 - B.FRENO["aperta"] * ap) * (1 - B.FRENO["importanza"] * imp))


def sbiadisci(oggi=None):
    """1.18.0 (punto 4): una volta per giorno vissuto, C x (1 - rodaggio x sbiadimento_e x freno); per le emozioni negative
    il freno ha anche l'umore. C0 ferma, F ricalcolata, S e S0 invariate. Sotto lucchetto rileggendo dal disco"""
    oggi = LUX.orologio() if oggi is None else oggi
    with B.lucchetto():
        z = B.carica_npz()
        if "sbiadimento_da" not in z or oggi <= float(z["sbiadito_fino"]) or not os.path.exists(B.STATO):
            return {"sbiadito": False, "giorno": oggi}
        s = np.load(B.STATO)
        L = RI.Lux.struttura(B.DIR)
        rod = _rodaggio(oggi - float(z["sbiadimento_da"]))
        f = freno_archi(z["A"], s["S"], s["S0"], (z["E_nato"], z["E_acceso"], z["E_accensioni"]), SA.ranghi(z),
                        L.errati, oggi)
        neg = np.asarray([e not in B.POSITIVE and e not in B.NEUTRE for e in B.EMOZIONI])
        u = B._umore()
        freno = f[:, None] * np.where(neg, 1 - B.FRENO["umore"] * u, 1.0)[None, :]
        C = (z["C"] * (1 - rod * z["sbiadimento"][None, :] * freno)).astype(np.float32)
        z.update(C=C, F=B.firme_engrammi(z["A"], C, len(z["V"])), sbiadito_fino=np.float64(oggi))
        B.salva_npz(z)
        os.utime(B.META)
    return {"sbiadito": True, "giorno": oggi, "rodaggio": rod, "umore": round(u, 3),
            "freno_medio": round(float(f.mean()), 3)}
