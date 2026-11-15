"""Lux degli engrammi: costruzione, versione dalla precedente, ricordi nuovi e correzioni.
Parte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano
lux_engrammi, che riesporta tutto."""
import lux_base as B
import fcntl
import json
import os
import shutil
import sys
import time
import numpy as np
import salienza as SA
import taglia as T
import lux as LUX   # solo le funzioni FSRS e l'orologio vissuto (lettura): il Lux originale non si tocca
from codice_ricordo import codice  # noqa: E402,F401  (B7, P4: un solo posto; lo usano anche servizio e test)
import lux_richiamo as RI


def pesi_archi(A, V, C):
    """1.16.0: peso di ogni arco nel suo ricordo. Centralita' di un engramma = coseno (negativi a zero) fra il suo vettore
    e il senso del ricordo (media normalizzata dei vettori dei suoi engrammi); dell'arco = media dei suoi due engrammi;
    W = (centralita' / media del ricordo) ^ CONTRASTO riportato a media 1, cosi' la carica media del ricordo non cambia.
    W = 1 per i ricordi di un arco solo, gli archi senza carica (correzioni) e i legami fra ricordi"""
    W = np.ones(len(A), np.float32)
    per = {}
    for j in np.nonzero((A[:, 1] >= 0) & C.any(1))[0].tolist():
        per.setdefault(int(A[j, 0]), []).append(j)
    for js in per.values():
        if len(js) < 2:
            continue
        e = sorted({int(v) for j in js for v in A[j, 2:4]})
        X = V[e].astype(np.float32)
        m = X.mean(0)
        c = dict(zip(e, np.clip(X @ (m / (np.linalg.norm(m) + 1e-9)), 0, None)))
        cj = np.asarray([(c[int(A[j, 2])] + c[int(A[j, 3])]) / 2 for j in js])
        if cj.mean() > 0:
            w = (cj / cj.mean()) ** B.CONTRASTO
            W[js] = np.maximum(w / w.mean(), 1e-3)   # mai zero: riconsolida divide per W
    return W


def contatori_iniziali(A, ricordi, n):
    """1.17.0: contatori dagli archi vivi dei ricordi esistenti, in ordine di tempo (giorno = giorno_di del ricordo)"""
    E = (np.full(n, -1, np.int32), np.full(n, -1, np.int32), np.zeros(n, np.int32))
    per = {}
    for j in np.nonzero(A[:, 1] >= 0)[0].tolist():
        per.setdefault(int(A[j, 0]), set()).update(int(v) for v in A[j, 2:4])
    for nid in sorted(per, key=lambda r: ricordi.get(r, {}).get("ts", 0)):
        d = B.giorno_di(ricordi.get(nid, {}).get("ts", 0), indietro=True)
        B._accendi_contatori(E, dict.fromkeys(per[nid], d))
    for x in E[:2]:
        x[x < 0] = 0
    return E


def param_id(testo, tab):
    """parametro -> intero: preposizioni = simbolo*8+articolo (0-71), gli altri (punteggiatura, congiunzioni, che) da 100 in su"""
    c = T.codice(testo)
    if c is not None:
        return c
    k = testo.lower()
    if k not in tab:
        tab[k] = 100 + len(tab)
    return tab[k]


def _inserisci(righe, eid, testi, C, tab, A, par_lista, ricordi):
    """taglia i ricordi (id, testo, firma, classe, ts[, campi]) e li aggiunge alle strutture: engrammi unici (chiave ->
    indice), archi in ordine (ricordo, posizione, a, b, primo parametro, n parametri) con la loro carica C (1.13.0),
    parametri; 1.20.0: testo, firma e i CAMPI (dict) restano in ricordi[nid]"""
    for nid, testo, firma, classe, ts, *campi in righe:
        pezzi = T.taglia(testo)
        f = B.carica(firma)
        nodi, legami, attesa = [], [], []
        for k, t in pezzi:
            if k == "arco":
                attesa.append(param_id(t, tab))
                continue
            kk = B.chiave(t)
            if kk not in eid:
                eid[kk] = len(testi)
                testi.append(t)
            nodi.append(eid[kk])
            legami.append(attesa)
            attesa = []
        ricordi[nid] = {"classe": classe, "codice": codice(ts), "n": len(nodi), "testa": legami[0] if legami else [], "coda": attesa}
        ricordi[nid]["ts"] = ts   # qlux (09/11): il momento per tutti, per la ricerca per data (prima solo correzioni)
        ricordi[nid].update(testo=testo, firma=B._firma(firma), **(campi[0] if campi else {}))
        for p in range(1, len(nodi)):
            A.append((nid, p, nodi[p - 1], nodi[p], len(par_lista), len(legami[p])))
            C.append(f)
            par_lista += legami[p]
        if len(nodi) == 1:   # ricordo di un engramma solo: arco su se stesso, cosi' l'indice lo trova
            A.append((nid, 0, nodi[0], nodi[0], len(par_lista), 0))
            C.append(f)


def _primo(A, nid):
    """primo engramma del ricordo nid negli archi A (array)"""
    r = A[(A[:, 0] == nid) & (A[:, 1] >= 0)]
    return int(r[r[:, 1].argmin(), 2])


def _lega(A, C, par_lista, tab, legami, ricordi, tutti):
    """1.11.0: archi fra ricordi (posizione -1) dal primo engramma della correzione al primo del ricordo corretto,
    parametri {corregge}{codice del corretto}; tutti = archi in cui cercare i primi engrammi. 1.13.0: carica zero"""
    for c, o in legami:
        A.append((c, -1, _primo(tutti, c), _primo(tutti, o), len(par_lista), 2))
        C.append(B.carica(None))
        par_lista += [param_id(B.CORREGGE, tab), param_id(ricordi[o]["codice"], tab)]


def _lega_siti(righe, A, C, par_lista, tab, eid, testi, tutti):
    """1.24.0 (D9, l'utente 13/11): il sito e' un engramma (testo = dominio) legato al primo engramma del ricordo da un arco
    a posizione -1 (fuori da ricomposizione e richiamo) con parametro {fonte}; carica zero. Un engramma con lo stesso
    testo (anche con altre maiuscole) si riusa. Ricordi senza archi vivi: niente legame"""
    for r in righe:
        if len(r) < 6 or not ((tutti[:, 0] == r[0]) & (tutti[:, 1] >= 0)).any():
            continue
        uno = {}
        for s in r[5].get("siti") or []:   # stessa chiave = un sito solo, col primo testo
            uno.setdefault(B.chiave(s), s)
        for k, s in uno.items():
            if k not in eid:
                eid[k] = len(testi)
                testi.append(s)
            A.append((r[0], -1, eid[k], _primo(tutti, r[0]), len(par_lista), 1))
            C.append(B.carica(None))
            par_lista.append(param_id(B.FONTE, tab))


def costruisci():
    os.makedirs(B.DIR, exist_ok=True)
    if os.path.exists(B.STATO):   # gli archi cambiano numerazione: lo stato dei rinforzi non varrebbe piu'
        sys.exit(f"{B.STATO} esiste: ricostruire cancella i rinforzi degli archi. Spostalo a mano se e' voluto.")
    # 1.20.0: i ricordi si riprendono dal meta della PRECEDENTE (dalla 1.20.0 in su ha testo e firma), correzioni comprese
    ricordi_p = {int(k): r for k, r in json.load(open(f"{B.PRECEDENTE}/lux-meta.json"))["ricordi"].items()}
    if any("testo" not in r for r in ricordi_p.values()):
        sys.exit(f"{B.PRECEDENTE} non ha i testi dei ricordi (prima della 1.20.0): costruisci riparte da una 1.20.0 in su")
    righe = [(n, r["testo"], r["firma"], r["classe"], r["ts"], {k: r[k] for k in B.CAMPI if k in r})
             for n, r in sorted(ricordi_p.items())]
    corr = [n for n, r in sorted(ricordi_p.items()) if r["classe"] == "correzione"]
    Lp = RI.Lux.struttura(B.PRECEDENTE) if corr else None   # i legami delle correzioni stanno negli archi
    legami = [(n, Lp.corregge[n]) for n in corr if n in Lp.corregge]
    eid, testi, C, tab, A, par_lista, ricordi = {}, [], [], {}, [], [], {}
    _inserisci(righe, eid, testi, C, tab, A, par_lista, ricordi)
    _lega(A, C, par_lista, tab, legami, ricordi, np.asarray(A, np.int64))
    _lega_siti(righe, A, C, par_lista, tab, eid, testi, np.asarray(A, np.int64))   # 1.24.0
    print(f"{len(righe)} ricordi -> {len(testi)} engrammi unici, {len(A)} archi, {len(tab)} parametri non preposizione", flush=True)
    V = np.zeros((len(testi), 1024), B.VTIPO)
    vecchi = {}
    if os.path.exists(f"{B.PRECEDENTE}/lux.npz"):
        zp, mp = B.carica_npz(f"{B.PRECEDENTE}/lux.npz"), json.load(open(f"{B.PRECEDENTE}/lux-meta.json"))
        vecchi = {t: j for j, t in enumerate(mp["engrammi"])}
        for i, t in enumerate(testi):
            if t in vecchi:
                V[i] = zp["V"][vecchi[t]]
    nuovi = [i for i, t in enumerate(testi) if t not in vecchi]
    print(f"vettori: {len(testi) - len(nuovi)} ripresi da {B.PRECEDENTE}, {len(nuovi)} da calcolare", flush=True)
    if nuovi:
        V[nuovi] = B.embed([testi[i] for i in nuovi]).astype(B.VTIPO)
    fattore, sbiadimento = B.tabella_emozioni()
    A, C = np.asarray(A, np.int64), np.asarray(C, np.float32) * fattore   # 1.15.0: carica = firma x fattore
    W = pesi_archi(A, V, C)
    C = C * W[:, None]   # 1.16.0
    F = B.firme_engrammi(A, C, len(testi))
    B.salva_npz(dict(V=V, F=F, A=A, C=C, C0=C, M=np.zeros((0, 4 + len(B.EMOZIONI))), rodaggio_da=np.nan,
                     fattore=fattore, sbiadimento=sbiadimento, W=W,
                     P=np.asarray(par_lista, np.int32), **SA.costruisci([(r[0], r[1]) for r in righe], B.embed)))
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(B.META, "w"), ensure_ascii=False)
    print(f"scritto {B.NPZ} e {B.META}")


def da_precedente():
    """1.24.0: la versione PRECEDENTE (1.23.0) identica (1.21.0: piu' avvicina_da = oggi vissuto, D2). Si lancia alla
    messa in produzione, a servizi fermi: la PRECEDENTE cambia fino all'ultimo. La PRECEDENTE resta com'e'."""
    if os.path.exists(B.NPZ):
        sys.exit(f"{B.NPZ} esiste gia'")
    os.makedirs(B.DIR, exist_ok=True)
    with open(f"{B.PRECEDENTE}/.lucchetto", "w") as lp, B.lucchetto():   # la PRECEDENTE e' quella in produzione: ferma
        fcntl.flock(lp, fcntl.LOCK_EX)
        shutil.copy2(f"{B.PRECEDENTE}/lux-stato.npz", B.STATO)
        shutil.copy2(f"{B.PRECEDENTE}/lux-meta.json", B.META + ".tmp")
        B.salva_npz(B.carica_npz(f"{B.PRECEDENTE}/lux.npz"))   # 1.25.0: anche dal formato di prima (V dentro lux.npz)
        os.replace(B.META + ".tmp", B.META)
    print(f"{B.DIR}: copia di {B.PRECEDENTE}")


def aggiungi_ricordo(v):
    """1.20.0: il ricordo nuovo entra nel Lux e prende il suo numero (prima lo dava memoria.add_node). v = testo, firma,
    classe, ts e CAMPI. Stesso testo di un ricordo che c'e' = quel ricordo (invariante anti-doppione del 20/07, solo fra i
    ricordi: le correzioni non stavano in memoria.db). Numero = 1 + il massimo fra meta e archi (dopo un crash fra npz
    e meta non si riusa un numero gia' negli archi). -> nid"""
    with B.lucchetto():
        ricordi = {int(k): r for k, r in json.load(open(B.META))["ricordi"].items()}
        doppio = next((n for n, r in ricordi.items() if n < B.PRIMO_CORREZIONE and r.get("testo") == v["testo"]), None)
        if doppio is not None:
            return doppio
        usati = [n for n in [*ricordi, *B.carica_npz()["A"][:, 0].tolist()] if n < B.PRIMO_CORREZIONE]
        nid = max(usati, default=0) + 1
        _aggiungi([(nid, v["testo"], v["firma"], v["classe"], v["ts"], {k: v.get(k) for k in B.CAMPI})])
        return nid


def correggi(codice_errato, testo, ts=None, campi=None):
    """1.11.0 (16/10): un ricordo che corregge quello di codice_errato. Entra nel Lux come gli altri, con un numero
    fuori dalla serie di memoria.db, legato al corretto da un arco {corregge}{codice}; l'originale non si tocca e da
    adesso non si rinforza piu'. Una correzione si corregge allo stesso modo (ripensamento). Torna il codice nuovo.
    1.24.0: campi = fonte (chi corregge) e siti (letti poco prima, tutti certi: D10) del ricordo della correzione"""
    with B.lucchetto():
        m = json.load(open(B.META))
        ricordi = {int(k): v for k, v in m["ricordi"].items()}
        o = next(n for n, r in ricordi.items() if r["codice"] == codice_errato)
        nid = max(B.PRIMO_CORREZIONE - 1, *ricordi) + 1
        ts = time.time() if ts is None else ts
        _aggiungi([(nid, testo, None, "correzione", ts, {k: (campi or {}).get(k) for k in B.CAMPI})], [(nid, o)])
        return codice(ts)


def _aggiungi(righe, legami=()):
    """1.5.0 (12/10): ricordi nuovi nel Lux senza ricostruire (1.20.0: righe da aggiungi_ricordo e correggi, non piu'
    da memoria.db). Engrammi nuovi in coda (vettori bge-m3, firme), quelli gia' noti si condividono, archi nuovi in coda
    con la stabilita' iniziale; i rinforzi degli archi esistenti restano. Scrittura atomica: il servizio ricarica quando
    cambia lux-meta.json."""
    z, m = B.carica_npz(), json.load(open(B.META))
    ricordi = {int(k): v for k, v in m["ricordi"].items()}
    testi = list(m["engrammi"])
    eid = {B.chiave(t): i for i, t in enumerate(testi)}
    tab = {k: 100 + i for i, k in enumerate(m["altri_parametri"])}
    n_e, n_a = len(testi), len(z["A"])
    A, C, par_lista = [], [], list(z["P"])
    _inserisci(righe, eid, testi, C, tab, A, par_lista, ricordi)
    _lega(A, C, par_lista, tab, legami, ricordi, np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)]))
    _lega_siti(righe, A, C, par_lista, tab, eid, testi, np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)]))
    nuovi = testi[n_e:]
    V = np.concatenate([z["V"].astype(B.VTIPO), B.embed(nuovi).astype(B.VTIPO)]) if nuovi else z["V"].astype(B.VTIPO)
    A = np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)])
    nuove = np.asarray(C, np.float32).reshape(-1, len(B.EMOZIONI))
    if "fattore" in z:   # 1.15.0: carica alla nascita = firma x fattore dell'emozione
        nuove = nuove * z["fattore"]
    if "W" in z:   # 1.16.0: e x il peso dell'arco nel suo ricordo (gli archi nuovi sono tutti di ricordi nuovi)
        Wn = pesi_archi(A[n_a:], V, nuove)
        nuove = nuove * Wn[:, None]
    C = np.concatenate([z["C"], nuove])
    F = B.firme_engrammi(A, C, len(testi))   # 1.13.0: anche gli engrammi gia' noti prendono le cariche degli archi nuovi
    sal = SA.aggiungi([(r[0], r[1]) for r in righe], B.embed, z)
    if os.path.exists(B.STATO):   # archi nuovi: stabilita' iniziale da firma e salienza del ricordo, nati oggi (vissuto)
        s = np.load(B.STATO)
        s0r = B.s0_ricordi({r[0]: r[2] for r in righe}, SA.ranghi(sal), [r[0] for r in righe])
        for n, *_, campi in (r for r in righe if len(r) > 5):
            if campi.get("fonte") == "abitudine":   # B5: temi maturati dalla persistenza
                s0r[n] = max(s0r[n], B.S_ABITUDINE)
            elif campi.get("fonte") == "trascinato":   # B6: firma_subito; 01/11 sera: stabilita' graduale, g
                g = campi.get("cattura")             # dalla sovrapposizione e dalla forza del forte
                s0r[n] *= B.TRASCINATO_S0 if g is None else g
        s0 = np.asarray([s0r[int(r)] for r in A[n_a:, 0]], np.float64)
        oggi = np.full(len(s0), float(LUX.orologio()))
        np.savez(B.STATO + ".tmp.npz", **{**dict(s), "S": np.concatenate([s["S"], s0]), "S0": np.concatenate([s["S0"], s0]),
                                        "U": np.concatenate([s["U"], oggi])})   # 1.17.0: R_nid e R_ts restano
    C0 = np.concatenate([z["C0"] if "C0" in z else z["C"], C[n_a:]])   # 1.14.0: alla nascita = C, poi ferma
    resto = {k: z[k] for k in ("M", "rodaggio_da", "fattore", "sbiadimento", "riacceso_fino", "sbiadimento_da",
                               "sbiadito_fino", "avvicina_da") if k in z}
    if "E_nato" in z:   # 1.17.0: engrammi nuovi nati oggi, quelli gia' noti ripresi da un ricordo nuovo si accendono
        k = len(testi) - n_e
        E = (np.concatenate([z["E_nato"], np.full(k, -1, np.int32)]), np.concatenate([z["E_acceso"], np.full(k, -1, np.int32)]),
             np.concatenate([z["E_accensioni"], np.zeros(k, np.int32)]))
        giorni = {int(r[0]): B.giorno_di(r[4]) for r in righe}
        for j in range(n_a, len(A)):
            if A[j, 1] >= 0:
                B._accendi_contatori(E, {int(v): giorni.get(int(A[j, 0]), B.giorno_di(time.time())) for v in A[j, 2:4]})
        for x in E[:2]:
            x[x < 0] = B.giorno_di(time.time())
        resto.update(E_nato=E[0], E_acceso=E[1], E_accensioni=E[2])
    if "W" in z:
        resto["W"] = np.concatenate([z["W"], Wn])
    scritto = dict(V=V, F=F, A=A, C=C, C0=C0, P=np.asarray(par_lista, np.int32), **sal, **resto)
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(B.META + ".tmp", "w"), ensure_ascii=False)
    B.salva_npz(scritto)   # 1.25.0: V e sal_F solo le righe nuove, in un blocco
    if os.path.exists(B.STATO + ".tmp.npz"):
        os.replace(B.STATO + ".tmp.npz", B.STATO)
    os.replace(B.META + ".tmp", B.META)   # per ultimo: e' il segnale di ricarica del servizio
    print(f"{len(righe)} ricordi nuovi, {len(nuovi)} engrammi nuovi, {len(A) - n_a} archi nuovi")
