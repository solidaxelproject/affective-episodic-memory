#!/usr/bin/env python3
"""Modulo unico di steering (PIANO-MODULO-STEERING.md, l'utente 10/11/2026): la ricetta dei test (vettore di ogni
emozione, fasce di DOSI-EMOZIONI.md, diadi, dose -> strati per /control-vector relativo, L15-L31) in un posto solo,
senza torch. Lo usano le prove (sistema.py), la pagina del confronto, vettori_firma e, in fase 2, il riflesso.
I vettori: vettori-steering.npz (esporta_vettori_steering.py)."""
import json
import os

import numpy as np

O = os.environ.get("OUT_35B", "/data/jspace/out-occamy")
VETTORI = f"{O}/vettori-steering.npz"
QUI = os.path.dirname(os.path.abspath(__file__))
TABELLA = os.path.join(QUI, "engrammi", "DOSI-EMOZIONI.md")
EN = {x["it"]: x["en"] for x in json.load(open(os.path.join(QUI, "emozioni.json")))}
STRATI = list(range(15, 32))   # 26/10: si inietta fino a L31
# fonte di ogni emozione della ruota = quella delle prove che hanno dato la fascia (vettori_firma, 31/10); terrore e
# stupore: le scene proprie; vigilanza: sé-nuovo, quello della diade con attesa. Ordine = quello della pagina del
# confronto (prima le 16 con fascia), poi le 8 senza fascia.
FONTI = {**dict.fromkeys(["gioia", "fiducia", "paura", "sorpresa", "tristezza", "disgusto", "rabbia"], "sé-medio"),
         "attesa": "sé-nuovo", "vigilanza": "sé-nuovo", "serenità": "sé-esterno", "interesse": "sé-nuovo",
         **dict.fromkeys(["estasi", "ammirazione", "cordoglio"], "sé-interno"),
         **dict.fromkeys(["terrore", "stupore", "ribrezzo", "furia"], "sé-proprio"),
         **dict.fromkeys(["accettazione", "apprensione", "distrazione", "noia", "fastidio"], "sé-nuovo"),
         "malinconia": "sé-esterno"}
DIADI = {"terrore": "paura", "stupore": "sorpresa", "vigilanza": "attesa"}   # 30/10: vigilanza = diade con attesa
# 31/10 (l'utente, ruota di Plutchik): le 8 diadi fra primarie vicine, ognuna alla stessa posizione della sua fascia
RUOTA = {"amore": ("gioia", "fiducia"), "sottomissione": ("fiducia", "paura"), "soggezione": ("paura", "sorpresa"),
         "disapprovazione": ("sorpresa", "tristezza"), "rimorso": ("tristezza", "disgusto"),
         "disprezzo": ("disgusto", "rabbia"), "aggressività": ("rabbia", "attesa"), "ottimismo": ("attesa", "gioia")}
# 05/11: anche le diadi fra assi non contigui (a un petalo e a due), PIANO-DIADI-PURE.md sez. 1
DIADI_24 = [*RUOTA, "colpa", "curiosità", "disperazione", "incredulità", "invidia", "cinismo", "orgoglio", "speranza",
            "diletto", "nostalgia", "vergogna", "indignazione", "pessimismo", "morbosità", "dominanza", "ansia"]
_vettori, _norme = {}, {}


def _righe():
    for riga in open(TABELLA):
        c = [x.strip() for x in riga.split("|")[1:-1]]
        if len(c) >= 3:
            yield c


def fasce():
    """{emozione: (dmin, dmax)} da DOSI-EMOZIONI.md; per le diadi ogni estremo e' (secondaria, primaria)"""
    out = {}
    for c in _righe():
        if c[0] in FONTI and c[1] and c[2]:
            v = [tuple(float(x) for x in d.split("+")) for d in c[1:3]]
            out[c[0]] = (v[0], v[1]) if "+" in c[1] else (v[0][0], v[1][0])
    return out


def pure():
    """08/11 (l'utente "mancano le diadi pure"): {diade: (dmin, dmax)} dei vettori puri delle diadi (righe "(vettore puro)"
    di DOSI-EMOZIONI.md, fonte sé-proprio); con la fascia intensa la dose va dal minimo della base al massimo dell'intensa"""
    out = {}
    for c in _righe():
        if c[0].endswith(" (vettore puro)") and c[1] and c[2]:
            nome = c[0].removesuffix(" (vettore puro)")
            base = nome.removesuffix(" intensa")
            lo, hi = out.get(base, (float(c[1]), float(c[2])))
            out[base] = (lo, float(c[2])) if nome != base else (float(c[1]), max(hi, float(c[2])))
    return out


def diadi_pure():
    """05/11: {diade: raggiungibile?} delle diadi pure gia' provate (righe di DOSI-EMOZIONI.md coi nomi di RUOTA):
    range scritto = raggiungibile, range vuoto = inaccessibile; una diade senza riga non c'e' (nessun vertice)"""
    return {c[0].split(" (")[0]: bool(c[1] and c[2]) for c in _righe() if c[0].split(" (")[0] in DIADI_24}


def fonti():
    """{asse inglese: fonte} dei vettori in uso: le 24 della ruota + le diadi pure (sé-proprio)"""
    return {**{EN[e]: f for e, f in FONTI.items()}, **dict.fromkeys((EN[e] for e in pure()), "sé-proprio")}


def emo_dose(emo, dose):
    """stringa "a:da+b:db" di layers(); per le diadi dose = posizione 0-1 fra i due estremi del range"""
    if emo in pure():
        return emo, dose
    if emo in RUOTA:
        return "+".join(f"{x}:{lo + dose * (hi - lo):.5f}" for x in RUOTA[emo] for lo, hi in [fasce()[x]]), dose
    if emo not in DIADI:
        return emo, dose
    (s0, p0), (s1, p1) = fasce()[emo]
    return f"{DIADI[emo]}:{p0 + dose * (p1 - p0):.5f}+{emo}:{s0 + dose * (s1 - s0):.5f}", dose


def layers(fonte, norme, e, strati, dose):
    """{strato: lista} per /control-vector relativo. fonte = {asse inglese: {strato: vettore float32}}, norme uguali
    in forma, calcolate da torch (cosi' i conti escono identici al bit a quelli delle prove);
    e = "a" oppure "a:da+b:db" (27/10, l'utente: ognuno alla sua dose; senza ":" vale dose). La dose e' tarata in HF
    (h += dose*||h||*dir); il server relativo fa h += rms(h)*v, da qui sqrt(2048). Conti in float32 come torch."""
    parti = [(x.split(":")[0], np.float32((float(x.split(":")[1]) if ":" in x else dose) * np.sqrt(2048)))
             for x in e.split("+")]
    out = {}
    for l in strati:
        tot = 0
        for x, k in parti:
            tot = tot + k * fonte[EN[x]][l] / norme[EN[x]][l]
        out[str(l)] = tot.tolist()
    return out


def vettori():
    """({asse inglese: {strato: vettore}}, {asse: {strato: norma}}) dal npz (caricato una volta)"""
    if not _vettori:
        z = np.load(VETTORI)
        if json.loads(str(z["fonte"])) != fonti():   # una diade pura o una fonte nuova nella tabella
            raise RuntimeError(f"{VETTORI} non aggiornato: rilanciare esporta_vettori_steering.py")
        s = z["strati"].tolist()
        v = {a: dict(zip(s, z[a])) for a in z.files if a not in ("strati", "fonte") and not a.endswith("|norma")}
        _norme.update({a: dict(zip(s, z[f"{a}|norma"])) for a in v})
        _vettori.update(v)   # per ultimo: un altro thread vede o tutto o niente
    return _vettori, _norme


def strati(emo, dose):
    """la ricetta della pagina del confronto: emozione (semplice, diade, ruota, pura) e dose -> strati L15-L31"""
    e, d = emo_dose(emo, dose)
    return layers(*vettori(), e, STRATI, d)
