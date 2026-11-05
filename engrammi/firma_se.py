#!/usr/bin/env python3
"""Firma nuova di un messaggio (PIANO-FIRMA-ENGRAMMI.md, B2, l'utente 31/10/2026).
Firma = per ognuno dei 24 assi della ruota, media sugli strati 15-31 del coseno fra il vettore se' dell'asse
(vettori-firma.pt, B1) e la differenza "messaggio letto dentro il contesto - contesto" (stessa idea della firma
differenziale di tagging35b, decisione 5-bis). Primo messaggio del giorno, senza contesto: messaggio - mu dello strato
(mu di popolazione, la calcola B3).
Due letture equivalenti:
  firma_server(contesto, messaggio)  dal server vivo (/lux-read di luxifer): per strato il contesto token per token
                                     (si toglie il primo, il pozzo dell'attenzione) e contesto + "\\n" + messaggio in
                                     media; somma del messaggio = differenza delle somme. 34 letture.
  firma_hf(s, contesto, messaggio)   col modello HF (mixed35b), un forward con tutti gli strati: per la rifirma (B3).
B5b (01/11): tutti gli strati in una decodifica ("layers" di /lux-read): 3 letture a firma invece di 34."""
import json
import urllib.request

import numpy as np
import torch

VETTORI = "/data/jspace/out-occamy/vettori-firma.pt"
STRATI = list(range(15, 32))
CTX_TOK = 320    # come tagging35b (MAX_TOK): ultimi 320 token del contesto, primi 320 del messaggio
MSG_TOK = 320
_v = {}


def vettori():
    """(assi, matrice [strato] -> [24 x 2048] unitaria)"""
    if not _v:
        d = torch.load(VETTORI, weights_only=False)
        _v["assi"] = d["assi"]
        _v["M"] = {l: np.stack([d["vettori"][a][l].numpy() for a in d["assi"]]).astype(np.float32) for l in STRATI}
    return _v["assi"], _v["M"]


def proietta(diff):
    """diff = {strato: vettore 2048} -> 24 valori (media sugli strati del coseno con ogni asse)"""
    _, M = vettori()
    out = np.zeros(len(M[STRATI[0]]), np.float64)
    for l in STRATI:
        d = np.asarray(diff[l], np.float64)
        n = np.linalg.norm(d)
        if not np.isfinite(n) or n < 1e-6:
            raise ValueError(f"differenza nulla o non finita allo strato {l}")
        out += M[l] @ d / n
    return out / len(STRATI)


# ---------- lettura dal server vivo ----------

def _post(url, path, body, timeout=120):
    r = urllib.request.Request(url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.load(f)


def tokens(url, testo):
    return _post(url, "/tokenize", {"content": testo})["tokens"]


def _taglia(url, testo, n, coda):
    """al massimo n token: gli ultimi (coda) o i primi; si torna al testo con /detokenize"""
    t = tokens(url, testo)
    if len(t) <= n:
        return testo
    return _post(url, "/detokenize", {"tokens": t[-n:] if coda else t[:n]})["content"]


def _primo_intero(url, contesto):
    """01/11 (B3): il primo token del contesto (il pozzo) si rilegge da solo; un carattere scritto in piu' token
    (un'emoji come 🔐 = 3 pezzi di byte) non si rilegge: si toglie dall'inizio. 1 voce su 1662 nella rifirma."""
    while contesto:
        t = tokens(url, contesto)[:1]
        if tokens(url, _post(url, "/detokenize", {"tokens": t})["content"]) == t:
            return contesto
        contesto = contesto[1:].lstrip()
    return contesto


def _somme(url, testo, n_atteso):
    """somma di ogni strato 15-31 sui token del testo, in doppia precisione e in una sola decodifica ("layers" e
    "somme" di luxifer, B5b): la firma sottrae somme grandi, dalle medie float32 l'arrotondamento si vedeva (2.5e-4)"""
    r = _post(url, "/lux-read", {"content": testo, "layer": STRATI[0], "layers": STRATI[1:], "somme": True})
    if "sums" not in r:
        raise RuntimeError("il server non da' le somme di piu' strati (\"layers\" e \"somme\" di /lux-read)")
    if n_atteso is not None and r["n_tokens"] != n_atteso:
        raise ValueError(f"token letti {r['n_tokens']}, attesi {n_atteso}")
    return {l: np.asarray(r["sums"][str(l)], np.float64) for l in STRATI}, r["n_tokens"]


def firma_server(contesto, messaggio, url, mu=None):
    """24 valori dal server vivo, 3 letture (B5b): contesto + messaggio, contesto, primo token del contesto (il pozzo,
    fuori dalla media del contesto come in tagging35b). Somma del messaggio = differenza delle somme.
    Contesto vuoto -> messaggio - mu (mu = {strato: vettore}, da B3). Ogni errore solleva: mai una firma a meta'."""
    messaggio = _taglia(url, messaggio, MSG_TOK, coda=False)
    if not contesto:
        if mu is None:
            raise ValueError("senza contesto serve mu (statistiche di B3)")
        m, n = _somme(url, messaggio, None)
        return proietta({l: m[l] / n - np.asarray(mu[l], np.float64) for l in STRATI})
    contesto = _taglia(url, contesto, CTX_TOK, coda=True).rstrip()   # spazio finale + "\n" = un token solo: niente prefisso
    contesto = _primo_intero(url, contesto)
    if not contesto:
        return firma_server("", messaggio, url, mu)
    unito = contesto + "\n" + messaggio
    tc, tu = tokens(url, contesto), tokens(url, unito)
    if tu[:len(tc)] != tc or len(tu) <= len(tc):
        raise ValueError("i token del contesto non sono un prefisso di quelli di contesto + messaggio")
    pozzo = _post(url, "/detokenize", {"tokens": tc[:1]})["content"]
    if tokens(url, pozzo) != tc[:1]:
        raise ValueError("il primo token del contesto non si rilegge da solo")
    su, _ = _somme(url, unito, len(tu))
    sc, _ = _somme(url, contesto, len(tc))
    h0, _ = _somme(url, pozzo, 1)
    diff = {}
    for l in STRATI:
        h_msg = (su[l] - sc[l]) / (len(tu) - len(tc))
        h_ctx = (sc[l] - h0[l]) / (len(tc) - 1) if len(tc) > 1 else h0[l]
        diff[l] = h_msg - h_ctx
    return proietta(diff)


def _firma_per_strato(contesto, messaggio, url, mu=None):
    """la firma di B2, uno strato per chiamata (34 letture, ~71 s): resta solo per il test di equivalenza di B5b"""
    messaggio = _taglia(url, messaggio, MSG_TOK, coda=False)
    diff = {}
    if not contesto:
        if mu is None:
            raise ValueError("senza contesto serve mu (statistiche di B3)")
        for l in STRATI:
            r = _post(url, "/lux-read", {"content": messaggio, "layer": l})
            diff[l] = np.asarray(r["mean"], np.float64) - np.asarray(mu[l], np.float64)
        return proietta(diff)
    contesto = _taglia(url, contesto, CTX_TOK, coda=True).rstrip()   # spazio finale + "\n" = un token solo: niente prefisso
    unito = contesto + "\n" + messaggio
    tc, tu = tokens(url, contesto), tokens(url, unito)
    if tu[:len(tc)] != tc or len(tu) <= len(tc) + 0:
        raise ValueError("i token del contesto non sono un prefisso di quelli di contesto + messaggio")
    for l in STRATI:
        c = _post(url, "/lux-read", {"content": contesto, "layer": l, "per_token": True})
        u = _post(url, "/lux-read", {"content": unito, "layer": l})
        if c["n_tokens"] != len(tc) or u["n_tokens"] != len(tu):
            raise ValueError(f"strato {l}: token letti {c['n_tokens']}/{u['n_tokens']}, attesi {len(tc)}/{len(tu)}")
        S = np.asarray(c["states"], np.float64)
        somma_msg = np.asarray(u["mean"], np.float64) * len(tu) - S.sum(0)
        h_msg = somma_msg / (len(tu) - len(tc))
        h_ctx = S[1:].mean(0) if len(S) > 1 else S[0]   # il primo token (pozzo) fuori dalla media del contesto
        diff[l] = h_msg - h_ctx
    return proietta(diff)


# ---------- lettura col modello HF (B3) ----------

def firma_hf(s, contesto, messaggio, mu=None):
    """stessa firma col modello HF (s = mixed35b.load()); stessi testi tagliati e uniti come firma_server"""
    from jlens.hooks import ActivationRecorder
    tok = s["model"].tokenizer
    im = tok(messaggio, add_special_tokens=False).input_ids[:MSG_TOK]
    messaggio = tok.decode(im)
    if not contesto:
        if mu is None:
            raise ValueError("senza contesto serve mu (statistiche di B3)")
        ids = torch.tensor([tok(messaggio, add_special_tokens=False).input_ids], device=s["model"].input_device)
        with torch.no_grad(), ActivationRecorder(s["model"].layers, at=STRATI) as rec:
            s["model"].forward(ids)
        return proietta({l: rec.activations[l][0].float().cpu().numpy().mean(0) - np.asarray(mu[l]) for l in STRATI})
    ic = tok(contesto, add_special_tokens=False).input_ids[-CTX_TOK:]
    contesto = tok.decode(ic).rstrip()
    tc = tok(contesto, add_special_tokens=False).input_ids
    tu = tok(contesto + "\n" + messaggio, add_special_tokens=False).input_ids
    if tu[:len(tc)] != tc:
        raise ValueError("i token del contesto non sono un prefisso di quelli di contesto + messaggio")
    ids = torch.tensor([tu], device=s["model"].input_device)
    with torch.no_grad(), ActivationRecorder(s["model"].layers, at=STRATI) as rec:
        s["model"].forward(ids)
    diff = {}
    for l in STRATI:
        h = rec.activations[l][0].float().cpu().numpy().astype(np.float64)
        diff[l] = h[len(tc):].mean(0) - (h[1:len(tc)].mean(0) if len(tc) > 1 else h[0])
    return proietta(diff)
