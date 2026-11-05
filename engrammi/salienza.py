"""salienza del ricordo (l'utente 16/10/2026, Lux 1.8.0): distintivita' e riferimento a se' entrano nella stabilita' iniziale.
1.8.1: i dati stanno dentro lux.npz con gli engrammi e gli archi (chiavi sal_*), niente file a parte.
1.9.0: se' coi vettori centrati: prima di ogni confronto si toglie la frase media dei ricordi (sal_mu), la parte
comune a tutte le frasi che avvicinava al centroide i testi vaghi ("👍"). Provata su 150 situazioni (prove/se_v2.py):
eccezioni da 27 a 10; il confronto con le 12 frasi una per una (esemplari) peggiorava ed e' scartato.
Formula D2, provata su 100 situazioni inventate (salienza/prove/, annotazioni.md):
  S0 = S_BASE * (E + (3 - E) * (1 - 1/M)),  M = (1 + 0.5*h(dist)*(E-1)/2) * (1 + 0.5*h(se)),  h(x) = max(0, 2x-1)
  E = clip(firma/1.8, 1, 3) come prima; dist e se' sono ranghi 0-1 sui ricordi veri.
dist = 1 - somiglianza col ricordo piu' simile fra tutti gli altri (media sulle frasi del coseno migliore), rango dentro
la classe di lunghezza in frasi (1, 2-3, 4-8, 9+). se' = media sulle frasi del coseno col centroide delle 12 frasi di
riferimento (riferimenti.json, privato), vettori centrati, rango sui ricordi fuori dalle 12.
ponytail: alla notturna dist e se' dei ricordi vecchi non si ricalcolano quando ne arrivano di simili (come le firme
degli engrammi); i ranghi dei nuovi si prendono sulla distribuzione esistente; sal_mu resta quella della costruzione."""
import json
import re

import numpy as np

RIFERIMENTI = "/data/memoria-episodica-affettiva/engrammi/salienza/riferimenti.json"
CLASSI = [2, 4, 9]   # confini delle classi di lunghezza in frasi


def frasi_di(t):
    fr = [s.strip(" *-#>|") for s in re.split(r"(?<=[.!?])\s+|\n+", t)]
    return [s for s in fr if len(s) >= 15] or [t.strip()[:500]]


def centrati(V, mu):
    V = V.astype(np.float32) - mu
    return V / np.linalg.norm(V, axis=-1, keepdims=True)


def rango(x, base):
    return float((base < x).mean() + 0.5 * (base == x).mean()) if len(base) else 0.5


def stabilita_iniziale(firma, dist, se, s_base, soglia=1.8):
    """firma = vettore dei 51 assi (o None), dist e se' = ranghi 0-1; soglia = quella della firma (B6: 1.532 coi
    vettori se', lux_engrammi.SOGLIA_FIRMA)"""
    E = float(np.clip(np.max(firma) / soglia, 1, 3)) if firma is not None else 1.0
    h = lambda x: max(0.0, 2 * x - 1)
    M = (1 + .5 * h(dist) * (E - 1) / 2) * (1 + .5 * h(se))
    return s_base * (E + (3 - E) * (1 - 1 / M))


def _grezzi(Fq, dq, F, di, n, escludi_se):
    """distintivita' grezza dei ricordi di Fq (frasi, ricordo di ogni frase dq) contro i ricordi di F/di (n ricordi);
    escludi_se: confrontare ogni ricordo anche con se stesso va evitato quando Fq e' dentro F"""
    out = {}
    for k in np.unique(dq):
        Q = Fq[dq == k].astype(np.float32)
        S = np.concatenate([Q @ F[i:i + 65536].astype(np.float32).T for i in range(0, len(F), 65536)], axis=1)
        best = np.full((len(Q), n), -1.0, np.float32)
        np.maximum.at(best.T, di, S.T)
        if escludi_se:
            best[:, k] = -1.0
        out[int(k)] = 1 - float(best.mean(0).max()) if n > 1 else 1.0
    return out


def costruisci(righe, embed):
    """righe = [(id, testo)] di tutti i ricordi -> array sal_* da salvare in lux.npz: frasi (float16), ranghi e grezzi"""
    rif = {int(k): v for k, v in json.load(open(RIFERIMENTI)).items()}
    ids = np.array([r[0] for r in righe], np.int64)
    fr = [frasi_di(t) for _, t in righe]
    di = np.concatenate([[k] * len(f) for k, f in enumerate(fr)]).astype(np.int64)
    F = embed([s for f in fr for s in f]).astype(np.float16)
    mu = F.astype(np.float32).mean(0)   # la frase media dei ricordi
    cen = centrati(embed(list(rif.values())), mu).mean(0)
    cen /= np.linalg.norm(cen)
    n = len(ids)
    g = _grezzi(F, di, F, di, n, True)
    dist_raw = np.array([g[k] for k in range(n)])
    se_raw = np.bincount(di, weights=centrati(F, mu) @ cen, minlength=n) / np.bincount(di, minlength=n)
    nf = np.array([len(f) for f in fr])
    cl, fuori = np.digitize(nf, CLASSI), ~np.isin(ids, list(rif))   # dist: stessa classe di lunghezza; se': fuori dalle 12
    return _prefisso(dict(F=F, di=di, ids=ids, mu=mu, cen=cen, dist_raw=dist_raw, se_raw=se_raw, nf=nf, rif=np.array(sorted(rif)),
                          dist=np.array([rango(dist_raw[k], dist_raw[cl == cl[k]]) for k in range(n)]),
                          se=np.array([rango(se_raw[k], se_raw[fuori]) for k in range(n)])))


def _prefisso(d):
    return {"sal_" + k: v for k, v in d.items()}


def _senza(lux):
    return {k[4:]: lux[k] for k in lux.files if k.startswith("sal_")} if hasattr(lux, "files") else \
        {k[4:]: v for k, v in lux.items() if k.startswith("sal_")}


def aggiungi(righe, embed, lux):
    """ricordi nuovi [(id, testo)] in coda: grezzi contro tutti (vecchi + nuovi), ranghi sulla distribuzione
    esistente; i valori dei vecchi restano. lux = lux.npz aperto; torna gli array sal_* aggiornati."""
    z = _senza(lux)
    n0 = len(z["ids"])
    fr = [frasi_di(t) for _, t in righe]
    Fn = embed([s for f in fr for s in f]).astype(np.float16)
    dn = np.concatenate([[n0 + k] * len(f) for k, f in enumerate(fr)]).astype(np.int64)
    F, di = np.concatenate([z["F"], Fn]), np.concatenate([z["di"], dn])
    ids = np.concatenate([z["ids"], [r[0] for r in righe]]).astype(np.int64)
    g = _grezzi(Fn, dn, F, di, len(ids), True)
    dist_raw = np.concatenate([z["dist_raw"], [g[n0 + k] for k in range(len(righe))]])
    se_raw = np.concatenate([z["se_raw"], np.bincount(dn - n0, weights=centrati(Fn, z["mu"]) @ z["cen"], minlength=len(righe))
                             / np.bincount(dn - n0, minlength=len(righe))])
    nf = np.concatenate([z["nf"], [len(f) for f in fr]])
    cl = np.digitize(nf, CLASSI)
    se_base = z["se_raw"][~np.isin(z["ids"], z["rif"])]
    dist = [rango(dist_raw[k], z["dist_raw"][cl[:n0] == cl[k]]) for k in range(n0, len(ids))]
    se = [rango(se_raw[k], se_base) for k in range(n0, len(ids))]
    z.update(F=F, di=di, ids=ids, dist_raw=dist_raw, se_raw=se_raw, nf=nf,
             dist=np.concatenate([z["dist"], dist]), se=np.concatenate([z["se"], se]))
    return _prefisso(z)


def ranghi(lux):
    """id ricordo -> (dist, se'); lux = lux.npz aperto o dizionario di array"""
    z = _senza(lux)
    return {int(i): (float(d), float(s)) for i, d, s in zip(z["ids"], z["dist"], z["se"])}


if __name__ == "__main__":   # controllo della formula: i casi limite che la prova ha fissato
    B = 1.0
    assert stabilita_iniziale(None, 1, 1, B) == 1 + 2 * (1 - 1 / 1.5)          # neutro: solo il se' conta
    assert stabilita_iniziale(np.array([1.0]), 1, 0, B) == 1.0                 # neutro distintivo: niente premio
    assert stabilita_iniziale(np.array([5.4]), 1, 1, B) == 3.0                 # massimo = tetto, mai oltre
    assert stabilita_iniziale(np.array([3.6]), 0, 0, B) == 2.0                 # sotto la mediana: nessuna penalita'
    a, b = stabilita_iniziale(np.array([5.0]), 1, 1, B), stabilita_iniziale(np.array([4.0]), 1, 1, B)
    assert 3 > a > b, (a, b)                                                    # niente appiattimento sul tetto
    assert rango(2, np.array([1, 2, 3])) == 0.5
    print("salienza: controlli ok")
