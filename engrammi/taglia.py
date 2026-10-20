#!/usr/bin/env python3
"""Taglio deterministico di un ricordo in engrammi (D1, 11/10/2026).
Per ogni proposizione: il soggetto e' un engramma, il resto (verbo + complementi) un altro.
Congiunzioni e punteggiatura fra pezzi diventano etichette d'arco, scritte {e}, {:}; gli engrammi fra quadre.
Un complemento di un nome si stacca: [la casa][di][mattoni rossi]; un nome proprio si stacca dal suo verbo:
[visitando][Parigi] (11/10).
ponytail: regole sulle dipendenze di spaCy it_core_news_lg
Lingue (15/10): ogni frase va allo spaCy della sua lingua. Riconoscitore lingua-py ristretto a italiano e
inglese; una frase passa all'inglese solo con sicurezza > SICUREZZA_LINGUA (gli italiani usano parole straniere:
"ok" resta italiano). Un testo senza frasi inglesi si taglia intero come prima, quindi i ricordi italiani non cambiano.
Inglese: stesse idee con le etichette di en_core_web_lg (prep/pobj al posto di case, "that"/"which"/"who" come "che").
Le preposizioni inglesi sono parametri d'arco ma non hanno il codice compatto delle italiane (finiscono fra gli altri
parametri, da 100 in su): ricomponendo restano inglesi. Altre lingue: si aggiungono a LINGUE quando servira'."""
import re
import sqlite3
import sys

import spacy

DB = "/data/workspace/memoria/memoria.db"
SOGG = {"nsubj", "nsubj:pass", "csubj", "nsubjpass", "csubjpass"}   # gli ultimi due: etichette inglesi
ABBREV = {"art.", "artt.", "n.", "nn.", "p.", "pp.", "pag.", "cap.", "vol.", "fig.", "par.", "co.", "c.", "lett.", "no.", "v.", "es.", "ca.", "nr.", "al."}


@spacy.Language.component("fine_frase")
def fine_frase(doc):
    """"Punto B. 3 righe": spaCy legge "B." come abbreviazione e non chiude la frase. Un token che finisce col punto,
    seguito da un numero, chiude la frase, tranne le abbreviazioni che vogliono un numero dopo (art. 2, p. 15)"""
    for t in doc[:-1]:
        if t.text.endswith(".") and len(t) > 1 and t.lower_ not in ABBREV and doc[t.i + 1].like_num:
            doc[t.i + 1].is_sent_start = True
    return doc


nlp = spacy.load("it_core_news_lg")   # il piccolo sbaglia le categorie (es. "cosciente" come verbo)
nlp.add_pipe("fine_frase", before="parser")
SICUREZZA_LINGUA = 0.9
_nlp_en = _rivelatore = None


def nlp_en():
    global _nlp_en
    if _nlp_en is None:
        _nlp_en = spacy.load("en_core_web_lg")
    return _nlp_en


def rivelatore():
    global _rivelatore
    if _rivelatore is None:
        from lingua import Language, LanguageDetectorBuilder
        _rivelatore = (LanguageDetectorBuilder.from_languages(Language.ITALIAN, Language.ENGLISH).build(), Language.ENGLISH)
    return _rivelatore


FRASE = re.compile(r"(?<=[.!?])\s+|\n+")


def per_lingua(testo):
    """testo -> [(lingua, pezzo di testo)]: frasi consecutive della stessa lingua insieme, separatori compresi"""
    d, EN = rivelatore()
    parti, inizio = [], 0
    for m in FRASE.finditer(testo):
        parti.append(testo[inizio:m.end()]); inizio = m.end()
    parti.append(testo[inizio:])
    # sicura: inglese sopra SICUREZZA_LINGUA, italiana sotto 0.5 o sotto le 3 parole; in mezzo (es. "It has a
    # reputation for:" a 0.81) prende la lingua della frase sicura piu' vicina, prima la precedente
    conf = [d.compute_language_confidence(x, EN) if x.strip() and len(x.split()) >= 3 else None for x in parti]
    sicura = ["en" if c is not None and c > SICUREZZA_LINGUA else "it" if c is not None and c < 0.5 or c is None and x.strip() else None
              for c, x in zip(conf, parti)]
    lingue = []
    for k, (c, x) in enumerate(zip(conf, parti)):
        if sicura[k] or not x.strip():
            lingue.append(sicura[k] or (lingue[-1] if lingue else "it"))
            continue
        prima = next((sicura[j] for j in range(k - 1, -1, -1) if sicura[j]), None)
        dopo = next((sicura[j] for j in range(k + 1, len(parti)) if sicura[j]), None)
        lingue.append(prima or dopo or "it")
    out = []
    for x, lingua in zip(parti, lingue):
        if out and out[-1][0] == lingua:
            out[-1] = (lingua, out[-1][1] + x)
        else:
            out.append((lingua, x))
    return out


FORMATO = re.compile(r"\*\*|__|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)|`|^#+\s*", re.M)   # grassetto, corsivo, codice, titoli


VIRGOLETTE = {'"', "'", "“", "”", "«", "»", "‘", "’"}
APICI = ("'", "’", "‘")   # 1.12.0: le virgolette semplici, che sono anche apostrofi


PROCLITICI = {"mi", "ti", "ci", "vi", "si", "lo", "la", "li", "le", "gli", "ne"}


def proclitico(t):
    """pronome atono STACCATO davanti al verbo ("mi dai"), non attaccato in coda ("fidarmi dei")"""
    return t.lower_ in PROCLITICI and "Yes" in t.morph.get("Clitic") and (t.i == 0 or t.doc[t.i - 1].whitespace_ != "")


def legame_en(t):
    """come legame, in inglese: punteggiatura, congiunzioni, preposizioni (prep, agent), "that"/"which"/"who" come il "che" italiano"""
    if t.is_upper and len(t) > 1 and t.is_alpha:
        return False
    if t.pos_ == "ADP" and t.dep_ in ("prep", "agent", "dative"):
        return True
    if t.lower_ in ("that", "which", "who") and (t.pos_ == "SCONJ" or t.tag_ in ("WDT", "WP")):
        return True
    return (t.dep_ == "cc" or t.is_punct) and t.text != "/" and t.text not in VIRGOLETTE


def apostrofo(t):
    """1.12.0 (20/10): apostrofo vero, non apice: attaccato alla parola prima (troncamenti, accenti scritti con
    l'apostrofo, genitivo inglese: po', perche', be', students'), cioe' subito dopo una lettera o una cifra. Un apice dopo
    uno spazio o un segno apre una citazione, il segno dopo la chiude"""
    p = t.doc[t.i - 1]
    return t.text in APICI and t.i > t.sent.start and not p.whitespace_ and p.text[-1:].isalnum()


def legame(t):
    """parole che diventano parametro dell'arco: punteggiatura, congiunzioni, "che" relativo o subordinante"""
    if t.doc.lang_ == "en":
        return legame_en(t)
    if t.is_upper and len(t) > 1 and t.is_alpha:   # parola in maiuscolo = enfasi, resta engramma (es. {QUANDO})
        return False
    if t.lower_ == "come":   # "come" = parametro di somiglianza (≈), tranne nelle domande (11/10):
        return t.head.pos_ not in ("VERB", "AUX")   # "come stai", "non so come fare" dipendono da un verbo
    if t.i > 0 and proclitico(t.doc[t.i - 1]):   # dopo "mi/ti/ci..." staccato e' un verbo: "mi dai"
        return False
    if t.lower_ in ("d'", "d’"):   # 1.12.0: d'accordo, d'altronde restano nell'engramma (come parametro: "di")
        return False
    if t.dep_ == "mark" and t.pos_ == "ADP":   # preposizione prima di un infinito: parametro anche lei ({∈}[partire])
        return parametro(t.text) is not None
    if t.dep_ in ("case", "fixed"):   # solo le preposizioni proprie, anche articolate; improprie e locuzioni restano nell'engramma
        return parametro(t.text) is not None and t.dep_ == "case" and not any(c.dep_ == "fixed" for c in t.children)
    # is_punct viene dal testo, non dall'analisi: i "..." spaCy non li etichetta sempre come punct
    return (t.dep_ == "cc" or t.is_punct) and t.text != "/" and t.text not in VIRGOLETTE or t.lower_ == "che" and (
        "Rel" in t.morph.get("PronType") or t.pos_ == "SCONJ")


def proposizioni(sent):
    """teste di proposizione: la radice, ogni altro verbo (anche infinito: [imparano][dal leggere ...]) e i nomi coordinati"""
    if sent.doc.lang_ == "en":   # in inglese la copula e' la testa ("is" ccomp): verbi e ausiliari che non fanno da aux
        return [sent.root] + [t for t in sent if t is not sent.root and (
            t.pos_ in ("VERB", "AUX") and t.dep_ not in ("aux", "auxpass") or (t.dep_ == "conj" and t.head.pos_ in ("NOUN", "PROPN") and t.pos_ in ("NOUN", "PROPN")))]
    return [sent.root] + [t for t in sent if t is not sent.root and (
        t.pos_ == "VERB" or any(c.dep_ == "cop" for c in t.children) or (t.dep_ == "conj" and t.head.pos_ in ("NOUN", "PROPN") and t.pos_ in ("NOUN", "PROPN")))]


def sottoalbero(t, teste):
    """sottoalbero di t senza entrare nelle proposizioni che contiene"""
    yield t
    for c in t.children:
        if c not in teste:
            yield from sottoalbero(c, teste)


CODICE = re.compile(r"```[\s\S]*?```|`[^`\n]+`")


def _segnaposto(k):
    """0 -> CODICEXA, 1 -> CODICEXB ...: solo lettere maiuscole, spaCy lo tiene come una parola"""
    s = ""
    while True:
        s = chr(65 + k % 26) + s
        k = k // 26 - 1
        if k < 0:
            return "CODICEX" + s


def taglia(testo):
    """testo -> lista di pezzi in ordine: ("nodo", testo) o ("arco", parametro).
    Il codice fra virgolette inverse e' un engramma intero (11/10: "rm ~/vecchio-driver.run" spezzato
    sembrava cancellare la home): si sostituisce con un segnaposto prima del taglio e si rimette dopo."""
    codici = {}

    def via(m):
        k = _segnaposto(len(codici))
        codici[k] = m.group(0).strip("`").strip()
        return f" {k} "
    t = CODICE.sub(via, testo)
    blocchi = per_lingua(t)
    if all(lg == "it" for lg, _ in blocchi):
        pezzi = _taglia(t)   # come prima: un ricordo italiano si taglia intero
    else:
        pezzi = [p for lg, x in blocchi for p in _taglia(x, nlp_en() if lg == "en" else nlp)]
    if not codici:
        return pezzi
    rimetti = re.compile("|".join(sorted(codici, key=len, reverse=True)))
    out = []
    for k, x in pezzi:
        if k == "nodo" and rimetti.search(x):
            parti = [p.strip() for p in re.split("(" + rimetti.pattern + ")", x) if p.strip()]
            out += [("nodo", codici.get(p, p)) for p in parti]   # il codice e' un engramma a se'
        else:
            out.append((k, x))
    return out


def _taglia(testo, modello=None):
    out = []
    for sent in (modello or nlp)(FORMATO.sub("", testo)).sents:   # la formattazione si elimina (11/10)
        teste = proposizioni(sent)
        padrone = {}
        for t in sent:   # ogni token va alla testa di proposizione piu' vicina risalendo l'albero
            x = t
            while x not in teste and x.head is not x:
                x = x.head
            padrone[t.i] = x.i if x in teste else sent.root.i
        for t in sent:   # il soggetto fa gruppo a se'
            if t.dep_ in SOGG:
                for s in sottoalbero(t, teste):
                    padrone[s.i] = ("S", t.i)
        prof = lambda t: len(list(t.ancestors))
        for t in sorted(sent, key=prof):   # complemento di un nome: dal piu' esterno al piu' interno
            if any(c.dep_ == "case" for c in t.children) and t not in teste or t.dep_ == "pobj" and t not in teste \
                    or t.dep_ == "nmod" and t.head.pos_ in ("NOUN", "PROPN", "PRON") \
                    or t.pos_ == "PROPN" and t.head.pos_ in ("VERB", "AUX") and t.dep_ not in SOGG \
                    and not t.dep_.startswith(("flat", "compound")):   # [visitando][Parigi]
                for s in sottoalbero(t, teste):
                    padrone[s.i] = ("N", t.i)

        dentro = None
        for t in sent:   # le virgolette delimitano un engramma: il citato e' un pezzo solo, le virgolette spariscono
            doppia = dentro is not None and t.doc[dentro].text not in APICI
            if t.text in APICI and doppia:   # 1.12.0: apice dentro "...": resta testo della citazione
                padrone[t.i] = ("Q", dentro)
            elif apostrofo(t) and dentro is None:   # 1.12.0: resta con la parola prima
                padrone[t.i] = padrone[t.i - 1]
            elif t.text in VIRGOLETTE and (t.pos_ == "PUNCT" or t.text in APICI):   # 1.12.0: un apice isolato e'
                # sempre un apice, anche se spaCy lo prende per preposizione o verbo ('essere umano', I still 'do' it)
                dentro = None if dentro is not None else t.i
                padrone[t.i] = "via"
            elif dentro is not None:
                padrone[t.i] = ("Q", dentro)
        corrente, buf = None, []
        for t in sent:
            if padrone[t.i] == "via":
                if buf:
                    out.append(("nodo", "".join(buf).strip()))
                    buf = []
                corrente = None
                continue
            if legame(t) and not isinstance(padrone[t.i], tuple) or legame(t) and padrone[t.i][0] != "Q":
                if buf:
                    out.append(("nodo", "".join(buf).strip()))
                    buf = []
                if t.dep_ == "fixed" and out and out[-1][0] == "arco":   # "davanti a" = un parametro solo
                    out[-1] = ("arco", out[-1][1] + " " + t.text)
                else:
                    out.append(("arco", t.text))
                corrente = None
                continue
            k = padrone[t.i]
            if k != corrente and buf:
                out.append(("nodo", "".join(buf).strip()))
                buf = []
            corrente = k
            buf.append(t.text_with_ws)
        if buf:
            out.append(("nodo", "".join(buf).strip()))
    return [p for p in out if p[1]]


# preposizioni -> simbolo, articoli -> numero (11/10). Nel Lux il parametro e' un intero: indice del simbolo * 8 + articolo
SIMBOLI = ["∈", "→", "←", "⊂", "∧", "⊤", "⇒", "↔", "≈"]
ARTICOLI = {"": 0, "il": 1, "lo": 2, "la": 3, "l'": 4, "i": 5, "gli": 6, "le": 7}
BASI = {"di": "∈", "d'": "∈", "a": "→", "ad": "→", "da": "←", "in": "⊂", "con": "∧", "su": "⊤", "per": "⇒", "tra": "↔", "fra": "↔",
        "come": "≈"}
_TRONCHE = {"di": "de", "a": "a", "da": "da", "in": "ne", "su": "su", "con": "co"}   # del, al, dal, nel, sul, col
PREPOSIZIONI = {b: (BASI[b], 0) for b in BASI}
for b, r in _TRONCHE.items():
    for art, n in ARTICOLI.items():
        if n == 1:
            PREPOSIZIONI[r + "l"] = (BASI[b], n)
        elif n == 5:
            PREPOSIZIONI[r + "i"] = (BASI[b], n)
        elif n == 6:
            PREPOSIZIONI[r + "gli"] = (BASI[b], n)   # degli, agli, negli
        elif n == 4:
            PREPOSIZIONI[r + "ll'"] = (BASI[b], n)
        elif n:
            PREPOSIZIONI[r + "l" + art] = (BASI[b], n)


def parametro(testo):
    """testo del legame -> (simbolo, articolo) se e' una preposizione nota, altrimenti None"""
    return PREPOSIZIONI.get(testo.lower().replace("’", "'"))


def codice(testo):
    """intero del parametro per il Lux, o None"""
    p = parametro(testo)
    return SIMBOLI.index(p[0]) * 8 + p[1] if p else None


def mostra(pezzi):
    def arco(t):
        p = parametro(t)
        return f"{{{p[0]}{p[1] or ''}}}" if p else f"{{{t}}}"
    return "".join(f"[{t}]" if k == "nodo" else arco(t) for k, t in pezzi)


if __name__ == "__main__":
    nid = int(sys.argv[1])
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    testo = c.execute("select testo from nodi where id=?", (nid,)).fetchone()[0]
    print(testo, "\n")
    print(mostra(taglia(testo)))
