#!/usr/bin/env python3
"""Lux degli engrammi (11/10/2026): ricordi come indici di engrammi condivisi, legati da archi con parametri.
Il Lux originale (lux.npz, lux-meta.json) e memoria.db NON si toccano: si leggono e basta, l'uscita va in lux-<VERSIONE>/.
  costruisci   CPU: taglia i ricordi (taglia.py), engrammi unici, archi in ordine, vettori bge-m3 (:8094), firme
  aggiungi     notturna: i ricordi nuovi di memoria.db entrano senza ricostruire (i rinforzi restano)
  prova        ricomposizione di tutti i ricordi + richiamo da indizi parziali + domande di prova
  richiama "testo"   i ricordi richiamati, ricomposti (non rinforza)
  consegna "testo"   come la consegna all'agente: richiama sopra soglia, RINFORZA gli archi, ricompone
  correggi CODICE "testo"   1.11.0: un ricordo nuovo che corregge quello di CODICE (l'originale non si tocca)
  da-precedente   1.13.0: la versione PRECEDENTE con le cariche degli archi (archi e rinforzi restano)
Arco = (ricordo, posizione, engramma a, engramma b, parametri fra i due): niente errori di strada sugli engrammi condivisi.
ponytail: modificatori dei parametri non ancora usati nella scelta, propagazione solo come predisposizione (1.12.0);
via emotiva assente nel richiamo
(la firma del messaggio richiede il 35B, GPU): le firme degli engrammi sono pronte in F."""
import contextlib
import fcntl
import json
import os
import random
import itertools
import shutil
import sys
import time
import unicodedata
import urllib.request

import numpy as np

import salienza as SA
import taglia as T

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import lux as LUX   # solo le funzioni FSRS e l'orologio vissuto (lettura): il Lux originale non si tocca
from codice_ricordo import codice  # noqa: E402,F401  (B7, P4: un solo posto; lo usano anche servizio e test)

# VERSIONE MAJOR.MINOR.PATCH (11/10): MAJOR = formato dei dati incompatibile (lo stato dei rinforzi non si
# porta), MINOR = ricostruzione con regole nuove (taglio, vettori) o funzione nuova, PATCH = correzione che non
# cambia i dati. Ogni versione ha la sua cartella: le vecchie restano.
VERSIONE = "1.24.0"   # 1.3.0: codice dei ricordi; 1.4.0: vettori L29 degli engrammi (lux-l29.npz); 1.5.0: aggiungi();
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
# in catena (un posto solo fra i CONSEGNA_MAX), originale barrato e mai piu' rinforzato. Fasi 2 e 3: PIANO-LUX-FASI-v1.12.md
# 1.12.0 (20/10): predisposizione dopo il richiamo (predisponi): i ricordi che condividono engrammi e archi coi
# ricordi consegnati salgono prima col prossimo indizio; apostrofi veri distinti dagli apici delle citazioni (taglia.py,
# unisci): si ricostruisce. Piano: PIANO-1.12-PREDISPOSIZIONE.md
# 1.13.0 (l'utente 31/10, D4 di PIANO-FIRMA-ENGRAMMI.md): l'emozione sull'arco. C = una riga per arco, 51 colonne
# nell'ordine di emozioni.json: alla nascita l'arco prende la firma del suo ricordo (24 assi dei vettori se', B3).
# F dell'engramma = media delle C dei suoi archi vivi con firma (la pesatura per carica arriva con la fase 2, punto 7).
# Archi, parametri, vettori e rinforzi identici alla 1.12.0 (da_precedente)
# B5 (01/11): rinforza() col peso (eco a 0.5), abitudini promosse dalla persistenza nate con S0 >= S_ABITUDINE; LUX_DIR
# punta una copia del Lux (stress-test del servizio)
# B6 (01/11): i ricordi entrano subito (firma_subito.py); archi nuovi con la soglia della firma nuova (SOGLIA_FIRMA) e
# trascinati del behavioral tagging a S0 x TRASCINATO_S0. Dati gia' scritti invariati: VERSIONE resta
# 1.14.0 (l'utente 17/10 + 11/11, PIANO-1.14-RICONSOLIDAMENTO.md): carica alla nascita C0, momenti M e riconsolidamento
# (riconsolida, a effetto zero finche' non c'e' la soglia di sorpresa); da_precedente copia la 1.13.0
# 1.15.0 (l'utente 09/11 D1-D2 + 11/11, PIANO-1.15-TABELLA-EMOZIONI.md): tabella delle emozioni in lux.npz (fattore,
# sbiadimento); carica = firma x fattore (alla nascita e nella migrazione), momento del riconsolidamento nella stessa scala
# 1.16.0 (l'utente 11/11 "vicinanza al senso", PIANO-1.16-CARICA-PER-ARCO.md): peso W per arco (pesi_archi), centrali piu'
# carichi del contorno, media del ricordo invariata
# 1.17.0 (l'utente 11/11, PIANO-1.17-CONTATORI.md): contatori degli engrammi (E_nato, E_acceso, E_accensioni, riaccendi dai
# messaggi del giorno) e ultimo richiamo per ricordo nello stato (R_nid, R_ts)
# 1.18.0 (l'utente 17/10 punto 4 + 11/11, PIANO-1.18-SBIADIMENTO.md): sbiadimento di notte col freno e il rodaggio
# (sbiadisci); nella forza la firma degli engrammi alla nascita (F0): la dose scende come la carica
# 1.19.0 (l'utente 11/11, PIANO-1.19-VIA-EMOTIVA.md): via emotiva del richiamo, punteggio x (1 + k x accordo emotivo) coi
# profili C0 dei ricordi e l'indizio della J-lens (via_emotiva.py, nel riflesso); dati identici alla 1.18.0
# 1.20.0 (l'utente 22/10 + 11/11, PIANO-1.20-MEMORIADB-SUPERFLUO.md): i dati dei ricordi stanno nel Lux (testo, firma,
# dominante, fonte, cattura, salienza, voluto in ricordi[nid]); il ricordo nuovo lo crea aggiungi_ricordo (servizio,
# POST /aggiungi); memoria.db resta archivio in sola lettura
# 1.21.0 (l'utente 11/11 + 12/11 D1-D5, PIANO-FASE2-C-ARCHI-E-CODA.md): archi fra ricordi (lux-stato.npz, RA_*), coda dei
# ricordi richiamati (consegna con coda), predisposizione dall'arco, avvicina di notte con la dominante ricalcolata
# 1.22.0 (l'utente 13/11, interfase 2-3, PIANO-INTERFASE-23-TRATTI.md): ricombinazione mnemonica (ricombina, frasi): a
# memorinvolontaria fino a 4 frasi di ricordi diversi, rinforzo per archi, impronta dell'engramma; emoji per significato
# in accendi; dati identici alla 1.21.0 (da_precedente)
# 1.23.0 (l'utente 13/11, interfase 2-3, PIANO-PONTI-123.md): ponti fra engrammi (nascita, cattura, rinforzo, calo
# notturno con POST /ponti, effetto ventaglio senza tetto); dati identici alla 1.22.0 (da_precedente)
# 1.24.0 (l'utente 13/11, fase 3, PIANO-1.24-FONTI.md): fonti. Siti delle pagine lette come engrammi (arco -1 {fonte}),
# fiducia per sito (conferme da fonte certa, smentite dalle correzioni), correggicordo; dati identici alla 1.23.0
DIR = os.environ.get("LUX_DIR", f"/data/memoria-episodica-affettiva/engrammi/lux-{VERSIONE}")
PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.23.0"   # da qui costruisci() riprende i vettori gia' calcolati, da_precedente() copia
CAMPI = ("dominante", "fonte", "cattura", "salienza", "voluto", "siti")   # 1.20.0: in ricordi[nid] con testo e firma; 1.24.0: siti
NPZ, META, STATO = f"{DIR}/lux.npz", f"{DIR}/lux-meta.json", f"{DIR}/lux-stato.npz"
CRESCITA_PIENA = 100.0   # S/S0 a cui la facilita' tocca il tetto
FACILITA_MAX = 2.0   # tetto: un ricordo richiamato spesso arriva alla soglia con un indizio fino a 2x piu' debole
EMOZIONI = [e["en"] for e in json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emozioni.json")))]   # ordine fisso dei 51 assi
EMBEDDER = "http://127.0.0.1:8094/v1/embeddings"
CONSEGNA_MAX = 4   # 1.10.0 (16/10): ricordi al massimo nella stessa risposta del tool (1.11.0: catene)
PRIMO_CORREZIONE = 1_000_000   # 1.11.0: numeri delle correzioni, fuori dalla serie di memoria.db
CORREGGE = "corregge"   # 1.11.0: parametro dell'arco che lega una correzione al ricordo corretto
# 1.24.0 (l'utente 13/11, fase 3, PIANO-1.24-FONTI.md): fonti. Il sito e' un engramma (D9) legato al ricordo da un arco
# a posizione -1 con parametro FONTE; fiducia per sito nello stato. Valori [provvisori] di CC
FONTE = "fonte"   # parametro dell'arco che lega un sito (engramma) al primo engramma di un suo ricordo
FONTE_CERTA = "@utente:localhost"   # D5: certa dall'inizio (campo fonte dei suoi messaggi)
FIDUCIA_W0, FIDUCIA_G, FIDUCIA_D, FIDUCIA_CERTA = 0.1, 0.2, 0.5, 0.5   # partenza, conferma (RW), smentita, soglia
CONFERMA_QUOTA = 0.5   # D2: sovrapposizione minima, nei due versi, perche' due ricordi dicano la stessa cosa
SOGLIA_RICHIAMO = 0.2   # sotto: nessun ricordo, nessun turno del tool (taratura_soglia.py, 11/10: negativi max 0.177, positivi giusti min 0.268)
VTIPO = np.float16   # 1.6.0
SOGLIA_SEM = 0.8     # coseno minimo perche' un engramma del messaggio ne accenda uno del Lux
PREDISPOSIZIONE_EMIVITA = 21600.0   # 1.12.0 (6 ore, Cai 2016, Rashid 2016): secondi di parete, dopo i quali la spinta e' a meta'
PREDISPOSIZIONE_MAX = 2.0   # 1.12.0: tetto del moltiplicatore del richiamo
PESO_COPPIA = 1.0   # 1.12.0: un arco condiviso (stessa coppia di engrammi) vale quanto un engramma in piu'
S_ABITUDINE = LUX.S_BASE * LUX.AROUSAL_MAX   # B5: come persistenza.py, la frequenza fa le veci dell'intensita'
SOGLIA_FIRMA = 1.904   # 09/11 (PIANO-FIRMA-44-ASSI): firma a 44 assi, stessa quota; prima 1.532 (B6), 1.8
TRASCINATO_S0 = 0.5    # B6: S0 del trascinato quando memoria.db non porta la sua cattura (nodi trascinati prima del 01/11 sera)
# 1.14.0 (l'utente 17/10 + 11/11, PIANO-1.14-RICONSOLIDAMENTO.md): riconsolidamento. C0 = carica alla nascita (D3 del 09/11),
# M = momenti (nid, ts consegna, ts risposta, sorpresa, 51 valori del momento), rodaggio_da = giorno vissuto in cui
# l'effetto si accende (NaN = effetto zero, D3 dell'11/11)
DIARIO_RIFLESSO = os.environ.get("DIARIO_RIFLESSO", "/data/workspace/memoria/diario-riflessi.jsonl")
GIORNATA = os.environ.get("GIORNATA_FIRMA", "/data/workspace/memoria/giornata-firma.jsonl")
FINESTRA_MOMENTO = 6 * 3600   # la prima risposta dopo il richiamo (Nader 2000)
ALFA = 0.2
PASSO_MAX = 0.5          # D2 (11/11): freno sul passo per arco e per notte; valore provvisorio di CC
SOGLIA_SORPRESA = None   # D1 rinviata (11/11): finche' manca, effetto zero anche con rodaggio_da
RODAGGIO = ((10, 0.1), (20, 0.3), (30, 0.7))   # punto 9: giorni dall'accensione -> frazione dell'effetto, poi 1
# 1.15.0 (l'utente 09/11 D1-D2 + 11/11 "sulla carica, effetto pieno", PIANO-1.15-TABELLA-EMOZIONI.md): la tabella delle
# emozioni, letta da qui solo alla costruzione e alla migrazione; poi vive in lux.npz (fattore, sbiadimento)
# 1.16.0 (l'utente 11/11 "vicinanza al senso", PIANO-1.16-CARICA-PER-ARCO.md): peso W per arco, centrali piu' carichi
CONTRASTO = 3.0   # esponente della centralita', valore provvisorio di CC (col coseno puro i pesi stanno a +-10%)
# 1.18.0 (l'utente 17/10 punto 4, PIANO-1.18-SBIADIMENTO.md): sbiadimento di notte. Pesi del freno dagli studi,
# umore e importanza come li legge CC (provvisori)
FRENO = {"ripetizione": 0.3, "aperta": 0.8, "umore": 0.5, "importanza": 0.6}
UMORE_PIENO = 2.0   # z dell'omeostato a cui l'umore conta tutto (provvisorio di CC)
OMEOSTATO = os.environ.get("OMEOSTATO", "/data/workspace/memoria/stato-emotivo.json")
POSITIVE = ["ecstasy", "joy", "serenity", "delight", "triumph", "pride", "admiration", "trust", "acceptance", "love",
            "sentimentality", "optimism", "interest", "curiosity", "hope", "purification"]   # divisione del 16/10
NEUTRE = ["submission", "morbidness", "dominance", "cynicism", "distraction", "vigilance", "anticipation"]
TABELLA_EMOZIONI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PROPOSTA-TABELLA-EMOZIONI.md")
TRACCIA_K_MAX = 0.5   # 1.19.0: il k piu' alto con cui !verifica emotiva! rigioca le scelte
# 1.21.0 (l'utente 11/11 + 12/11 sera D1-D5, PIANO-FASE2-C-ARCHI-E-CODA.md): archi fra ricordi, coda, firme che si avvicinano
PESO_ARCO_RICORDI = 1.0   # D1: spinta della predisposizione per arco fra ricordi = questo x forza dell'arco (provvisorio di CC)
FRENO_LEGATI = 0.5        # D3: fra ricordi legati il termine della stabilita' del freno pesa la meta' (provvisorio di CC)
# 1.22.0 (l'utente 13/11, interfase 2-3, PIANO-INTERFASE-23-TRATTI.md): ricombinazione mnemonica
FINE_FRASE = (".", "!", "?", "...", "…")   # parametri che chiudono una frase (i tratti)
# significato delle emoji per la via semantica (l'utente 13/11; bge-m3 vede tutte le emoji quasi uguali)
EMOJI = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "emoji-significati.json"), encoding="utf-8"))
SIGN = {**EMOJI["emozioni"], **EMOJI["altre"]}
INVISIBILI = {"\ufe0f", "\u200d", " "}
# valori provvisori di CC dalla prova del 13/11 (prova-interfase-23-emozione/), funzione da RICERCA-RICHIAMO-EMOTIVO.md C1
RICORDI_TRATTI = 10   # ricordi del richiamo da cui escono i tratti
TRATTI_MAX = 4        # Cowan 2001: circa 4 elementi insieme nella memoria di lavoro
TOKEN_MAX = 512       # 13/11: quello che arriva all'agente sta sotto i 512 token
CAR_TOKEN = 4         # stima: 4 caratteri per token
S_MAX, LAMBDA_W, GAMMA, LAMBDA_0, TAU = 2.0, 1.0, 1.0, 1.0, 0.0
# 1.23.0 (l'utente 13/11, interfase 2-3 secondo passo, PIANO-PONTI-123.md): ponti fra engrammi di ricordi diversi
# (interconnessione engrammatica, RICERCA-LEGAMI-NUOVI.md B). Valori [provvisori] di CC dalla ricerca
PONTE_A0, PONTE_A1 = 0.2, 0.5   # B1/B6: accensione sotto A0 inattiva, fra A0 e A1 moderata, da A1 forte
PONTE_W0, PONTE_W_CATTURA = 0.1, 0.2   # B2: peso alla nascita (provvisorio); B3/B5: peso alla cattura (stabile)
PONTE_G, PONTE_D = 0.2, 0.05   # B3: guadagno del rinforzo forte-forte; B6: perdita col ramo discendente della U
PONTI_PER_RICHIAMO = 2   # B1: k, scelta di sparsita'
PONTE_CALO, PONTE_PROTETTI, PONTE_W_MIN = 0.82, 0.2, 0.05   # B4: de Vivo 2017, taglio
TRADUZIONE_L29 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "via-emotiva", "traduzione-l29.npz")
INVERSO = {}
for _k, _v in T.PREPOSIZIONI.items():   # forma canonica: la prima della tabella (di, non d'; a, non ad; tra, non fra)
    INVERSO.setdefault(_v, _k)


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


def _firma(firma):
    """firma del ricordo: dict (meta, 1.20.0), json (memoria.db) o None -> dict o None"""
    return json.loads(firma) if isinstance(firma, str) else firma


def carica(firma):
    """firma del ricordo (dict, json o None) -> riga di C: 51 valori nell'ordine di EMOZIONI, zero dove la firma non ha l'asse"""
    if not firma:
        return np.zeros(len(EMOZIONI), np.float32)
    f = _firma(firma)
    return np.asarray([f.get(e, 0.0) for e in EMOZIONI], np.float32)


def tabella_emozioni():
    """(fattore alla nascita, sbiadimento per notte), 51 valori nell'ordine di EMOZIONI, dalla tabella decisa il 09/11"""
    en = {x["it"]: x["en"] for x in json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emozioni.json")))}
    righe = {en[c[0]]: (float(c[2]), float(c[5])) for c in ([x.strip() for x in r.split("|")[1:-1]] for r in open(TABELLA_EMOZIONI))
             if len(c) == 7 and c[0] in en}
    if set(righe) != set(EMOZIONI):
        raise RuntimeError(f"{TABELLA_EMOZIONI}: mancano {sorted(set(EMOZIONI) - set(righe))}")
    return tuple(np.asarray([righe[e][k] for e in EMOZIONI], np.float32) for k in (0, 1))


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
            w = (cj / cj.mean()) ** CONTRASTO
            W[js] = np.maximum(w / w.mean(), 1e-3)   # mai zero: riconsolida divide per W
    return W


def giorno_di(ts, indietro=False):
    """1.17.0: giorno vissuto di un momento (l'orologio avanza solo nella notturna: prima dell'ultimo avanzamento e' il
    giorno prima). indietro (solo i valori iniziali): piu' indietro un giorno ogni 24 ore, mai sotto 0; senza, tutto
    quello che sta prima dell'ultimo avanzamento e' dell'ultimo giorno chiuso (una notturna fallita non apre un giorno)"""
    try:
        st = json.load(open(LUX._file_orologio()))
        g, u = int(st["giorni"]), float(st.get("ultimo_avanzamento", 0))
    except (OSError, ValueError, KeyError):
        return 0
    if ts >= u:
        return g
    return max(0, g - 1 - int((u - ts) // 86400)) if indietro else max(0, g - 1)


def _accendi_contatori(E, accesi):
    """1.17.0: E = (nato, acceso, accensioni) per engramma, accesi = {engramma: giorno}. Un engramma mai visto (nato < 0)
    nasce quel giorno; poi una sola accensione per giorno"""
    nato, acceso, acc = E
    for i, d in accesi.items():
        if nato[i] < 0:
            nato[i] = acceso[i] = d
        elif d > acceso[i]:
            acceso[i] = d
            acc[i] += 1


def contatori_iniziali(A, ricordi, n):
    """1.17.0: contatori dagli archi vivi dei ricordi esistenti, in ordine di tempo (giorno = giorno_di del ricordo)"""
    E = (np.full(n, -1, np.int32), np.full(n, -1, np.int32), np.zeros(n, np.int32))
    per = {}
    for j in np.nonzero(A[:, 1] >= 0)[0].tolist():
        per.setdefault(int(A[j, 0]), set()).update(int(v) for v in A[j, 2:4])
    for nid in sorted(per, key=lambda r: ricordi.get(r, {}).get("ts", 0)):
        d = giorno_di(ricordi.get(nid, {}).get("ts", 0), indietro=True)
        _accendi_contatori(E, dict.fromkeys(per[nid], d))
    for x in E[:2]:
        x[x < 0] = 0
    return E


def firme_engrammi(A, C, n):
    """1.13.0: firma di ognuno degli n engrammi = media delle C dei suoi archi vivi con firma (un arco su se stesso conta
    una volta); zero per chi non ne ha"""
    k = (A[:, 1] >= 0) & C.any(1)
    S, N = np.zeros((n, C.shape[1])), np.zeros(n)
    np.add.at(S, A[k, 2], C[k])
    np.add.at(N, A[k, 2], 1)
    k &= A[:, 2] != A[:, 3]
    np.add.at(S, A[k, 3], C[k])
    np.add.at(N, A[k, 3], 1)
    return (S / np.maximum(N, 1)[:, None]).astype(np.float32)


def s0_ricordi(firme, ranghi, nids):
    """stabilita' iniziale per ricordo (1.8.0): firma (dict, json o None) + ranghi di salienza (salienza.py)"""
    out = {}
    for nid in nids:
        f = firme.get(nid)
        f = np.asarray([_firma(f).get(e, 0.0) for e in EMOZIONI]) if f else None
        out[nid] = SA.stabilita_iniziale(f, *ranghi.get(nid, (0.0, 0.0)), LUX.S_BASE, SOGLIA_FIRMA)
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


def _inserisci(righe, eid, testi, C, tab, A, par_lista, ricordi):
    """taglia i ricordi (id, testo, firma, classe, ts[, campi]) e li aggiunge alle strutture: engrammi unici (chiave ->
    indice), archi in ordine (ricordo, posizione, a, b, primo parametro, n parametri) con la loro carica C (1.13.0),
    parametri; 1.20.0: testo, firma e i CAMPI (dict) restano in ricordi[nid]"""
    for nid, testo, firma, classe, ts, *campi in righe:
        pezzi = T.taglia(testo)
        f = carica(firma)
        nodi, legami, attesa = [], [], []
        for k, t in pezzi:
            if k == "arco":
                attesa.append(param_id(t, tab))
                continue
            kk = chiave(t)
            if kk not in eid:
                eid[kk] = len(testi)
                testi.append(t)
            nodi.append(eid[kk])
            legami.append(attesa)
            attesa = []
        ricordi[nid] = {"classe": classe, "codice": codice(ts), "n": len(nodi), "testa": legami[0] if legami else [], "coda": attesa}
        ricordi[nid]["ts"] = ts   # qlux (09/11): il momento per tutti, per la ricerca per data (prima solo correzioni)
        ricordi[nid].update(testo=testo, firma=_firma(firma), **(campi[0] if campi else {}))
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
        C.append(carica(None))
        par_lista += [param_id(CORREGGE, tab), param_id(ricordi[o]["codice"], tab)]


def _lega_siti(righe, A, C, par_lista, tab, eid, testi, tutti):
    """1.24.0 (D9, l'utente 13/11): il sito e' un engramma (testo = dominio) legato al primo engramma del ricordo da un arco
    a posizione -1 (fuori da ricomposizione e richiamo) con parametro {fonte}; carica zero. Un engramma con lo stesso
    testo (anche con altre maiuscole) si riusa. Ricordi senza archi vivi: niente legame"""
    for r in righe:
        if len(r) < 6 or not ((tutti[:, 0] == r[0]) & (tutti[:, 1] >= 0)).any():
            continue
        uno = {}
        for s in r[5].get("siti") or []:   # stessa chiave = un sito solo, col primo testo
            uno.setdefault(chiave(s), s)
        for k, s in uno.items():
            if k not in eid:
                eid[k] = len(testi)
                testi.append(s)
            A.append((r[0], -1, eid[k], _primo(tutti, r[0]), len(par_lista), 1))
            C.append(carica(None))
            par_lista.append(param_id(FONTE, tab))


def costruisci():
    os.makedirs(DIR, exist_ok=True)
    if os.path.exists(STATO):   # gli archi cambiano numerazione: lo stato dei rinforzi non varrebbe piu'
        sys.exit(f"{STATO} esiste: ricostruire cancella i rinforzi degli archi. Spostalo a mano se e' voluto.")
    # 1.20.0: i ricordi si riprendono dal meta della PRECEDENTE (dalla 1.20.0 in su ha testo e firma), correzioni comprese
    ricordi_p = {int(k): r for k, r in json.load(open(f"{PRECEDENTE}/lux-meta.json"))["ricordi"].items()}
    if any("testo" not in r for r in ricordi_p.values()):
        sys.exit(f"{PRECEDENTE} non ha i testi dei ricordi (prima della 1.20.0): costruisci riparte da una 1.20.0 in su")
    righe = [(n, r["testo"], r["firma"], r["classe"], r["ts"], {k: r[k] for k in CAMPI if k in r})
             for n, r in sorted(ricordi_p.items())]
    corr = [n for n, r in sorted(ricordi_p.items()) if r["classe"] == "correzione"]
    Lp = Lux.struttura(PRECEDENTE) if corr else None   # i legami delle correzioni stanno negli archi
    legami = [(n, Lp.corregge[n]) for n in corr if n in Lp.corregge]
    eid, testi, C, tab, A, par_lista, ricordi = {}, [], [], {}, [], [], {}
    _inserisci(righe, eid, testi, C, tab, A, par_lista, ricordi)
    _lega(A, C, par_lista, tab, legami, ricordi, np.asarray(A, np.int64))
    _lega_siti(righe, A, C, par_lista, tab, eid, testi, np.asarray(A, np.int64))   # 1.24.0
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
    fattore, sbiadimento = tabella_emozioni()
    A, C = np.asarray(A, np.int64), np.asarray(C, np.float32) * fattore   # 1.15.0: carica = firma x fattore
    W = pesi_archi(A, V, C)
    C = C * W[:, None]   # 1.16.0
    F = firme_engrammi(A, C, len(testi))
    np.savez(NPZ, V=V, F=F, A=A, C=C, C0=C, M=np.zeros((0, 4 + len(EMOZIONI))), rodaggio_da=np.nan,
             fattore=fattore, sbiadimento=sbiadimento, W=W,
             P=np.asarray(par_lista, np.int32), **SA.costruisci([(r[0], r[1]) for r in righe], embed))
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(META, "w"), ensure_ascii=False)
    print(f"scritto {NPZ} e {META}")


def da_precedente():
    """1.24.0: la versione PRECEDENTE (1.23.0) identica (1.21.0: piu' avvicina_da = oggi vissuto, D2). Si lancia alla
    messa in produzione, a servizi fermi: la PRECEDENTE cambia fino all'ultimo. La PRECEDENTE resta com'e'."""
    if os.path.exists(NPZ):
        sys.exit(f"{NPZ} esiste gia'")
    os.makedirs(DIR, exist_ok=True)
    with open(f"{PRECEDENTE}/.lucchetto", "w") as lp, lucchetto():   # la PRECEDENTE e' quella in produzione: ferma
        fcntl.flock(lp, fcntl.LOCK_EX)
        shutil.copy2(f"{PRECEDENTE}/lux-stato.npz", STATO)
        if os.path.exists(f"{PRECEDENTE}/lux-l29.npz"):
            shutil.copy2(f"{PRECEDENTE}/lux-l29.npz", f"{DIR}/lux-l29.npz")
        shutil.copy2(f"{PRECEDENTE}/lux.npz", NPZ + ".tmp.npz")
        shutil.copy2(f"{PRECEDENTE}/lux-meta.json", META + ".tmp")
        os.replace(NPZ + ".tmp.npz", NPZ)
        os.replace(META + ".tmp", META)
    print(f"{DIR}: copia di {PRECEDENTE}")


def aggiungi_ricordo(v):
    """1.20.0: il ricordo nuovo entra nel Lux e prende il suo numero (prima lo dava memoria.add_node). v = testo, firma,
    classe, ts e CAMPI. Stesso testo di un ricordo che c'e' = quel ricordo (invariante anti-doppione del 20/07, solo fra i
    ricordi: le correzioni non stavano in memoria.db). Numero = 1 + il massimo fra meta e archi (dopo un crash fra npz
    e meta non si riusa un numero gia' negli archi). -> nid"""
    with lucchetto():
        ricordi = {int(k): r for k, r in json.load(open(META))["ricordi"].items()}
        doppio = next((n for n, r in ricordi.items() if n < PRIMO_CORREZIONE and r.get("testo") == v["testo"]), None)
        if doppio is not None:
            return doppio
        usati = [n for n in [*ricordi, *np.load(NPZ)["A"][:, 0].tolist()] if n < PRIMO_CORREZIONE]
        nid = max(usati, default=0) + 1
        _aggiungi([(nid, v["testo"], v["firma"], v["classe"], v["ts"], {k: v.get(k) for k in CAMPI})])
        return nid


def correggi(codice_errato, testo, ts=None, campi=None):
    """1.11.0 (16/10): un ricordo che corregge quello di codice_errato. Entra nel Lux come gli altri, con un numero
    fuori dalla serie di memoria.db, legato al corretto da un arco {corregge}{codice}; l'originale non si tocca e da
    adesso non si rinforza piu'. Una correzione si corregge allo stesso modo (ripensamento). Torna il codice nuovo.
    1.24.0: campi = fonte (chi corregge) e siti (letti poco prima, tutti certi: D10) del ricordo della correzione"""
    with lucchetto():
        m = json.load(open(META))
        ricordi = {int(k): v for k, v in m["ricordi"].items()}
        o = next(n for n, r in ricordi.items() if r["codice"] == codice_errato)
        nid = max(PRIMO_CORREZIONE - 1, *ricordi) + 1
        ts = time.time() if ts is None else ts
        _aggiungi([(nid, testo, None, "correzione", ts, {k: (campi or {}).get(k) for k in CAMPI})], [(nid, o)])
        return codice(ts)


def _aggiungi(righe, legami=()):
    """1.5.0 (12/10): ricordi nuovi nel Lux senza ricostruire (1.20.0: righe da aggiungi_ricordo e correggi, non piu'
    da memoria.db). Engrammi nuovi in coda (vettori bge-m3, firme), quelli gia' noti si condividono, archi nuovi in coda
    con la stabilita' iniziale; i rinforzi degli archi esistenti restano. Scrittura atomica: il servizio ricarica quando
    cambia lux-meta.json. lux-l29.npz copre solo gli engrammi della costruzione (non usato nel richiamo)."""
    z, m = np.load(NPZ), json.load(open(META))
    ricordi = {int(k): v for k, v in m["ricordi"].items()}
    testi = list(m["engrammi"])
    eid = {chiave(t): i for i, t in enumerate(testi)}
    tab = {k: 100 + i for i, k in enumerate(m["altri_parametri"])}
    n_e, n_a = len(testi), len(z["A"])
    A, C, par_lista = [], [], list(z["P"])
    _inserisci(righe, eid, testi, C, tab, A, par_lista, ricordi)
    _lega(A, C, par_lista, tab, legami, ricordi, np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)]))
    _lega_siti(righe, A, C, par_lista, tab, eid, testi, np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)]))
    nuovi = testi[n_e:]
    V = np.concatenate([z["V"].astype(VTIPO), embed(nuovi).astype(VTIPO)]) if nuovi else z["V"].astype(VTIPO)
    A = np.concatenate([z["A"], np.asarray(A, np.int64).reshape(-1, 6)])
    nuove = np.asarray(C, np.float32).reshape(-1, len(EMOZIONI))
    if "fattore" in z.files:   # 1.15.0: carica alla nascita = firma x fattore dell'emozione
        nuove = nuove * z["fattore"]
    if "W" in z.files:   # 1.16.0: e x il peso dell'arco nel suo ricordo (gli archi nuovi sono tutti di ricordi nuovi)
        Wn = pesi_archi(A[n_a:], V, nuove)
        nuove = nuove * Wn[:, None]
    C = np.concatenate([z["C"], nuove])
    F = firme_engrammi(A, C, len(testi))   # 1.13.0: anche gli engrammi gia' noti prendono le cariche degli archi nuovi
    sal = SA.aggiungi([(r[0], r[1]) for r in righe], embed, z)
    if os.path.exists(STATO):   # archi nuovi: stabilita' iniziale da firma e salienza del ricordo, nati oggi (vissuto)
        s = np.load(STATO)
        s0r = s0_ricordi({r[0]: r[2] for r in righe}, SA.ranghi(sal), [r[0] for r in righe])
        for n, *_, campi in (r for r in righe if len(r) > 5):
            if campi.get("fonte") == "abitudine":   # B5: temi maturati dalla persistenza
                s0r[n] = max(s0r[n], S_ABITUDINE)
            elif campi.get("fonte") == "trascinato":   # B6: firma_subito; 01/11 sera: stabilita' graduale, g
                g = campi.get("cattura")             # dalla sovrapposizione e dalla forza del forte
                s0r[n] *= TRASCINATO_S0 if g is None else g
        s0 = np.asarray([s0r[int(r)] for r in A[n_a:, 0]], np.float64)
        oggi = np.full(len(s0), float(LUX.orologio()))
        np.savez(STATO + ".tmp.npz", **{**dict(s), "S": np.concatenate([s["S"], s0]), "S0": np.concatenate([s["S0"], s0]),
                                        "U": np.concatenate([s["U"], oggi])})   # 1.17.0: R_nid e R_ts restano
    C0 = np.concatenate([z["C0"] if "C0" in z.files else z["C"], C[n_a:]])   # 1.14.0: alla nascita = C, poi ferma
    resto = {k: z[k] for k in ("M", "rodaggio_da", "fattore", "sbiadimento", "riacceso_fino", "sbiadimento_da",
                               "sbiadito_fino", "avvicina_da") if k in z.files}
    if "E_nato" in z.files:   # 1.17.0: engrammi nuovi nati oggi, quelli gia' noti ripresi da un ricordo nuovo si accendono
        k = len(testi) - n_e
        E = (np.concatenate([z["E_nato"], np.full(k, -1, np.int32)]), np.concatenate([z["E_acceso"], np.full(k, -1, np.int32)]),
             np.concatenate([z["E_accensioni"], np.zeros(k, np.int32)]))
        giorni = {int(r[0]): giorno_di(r[4]) for r in righe}
        for j in range(n_a, len(A)):
            if A[j, 1] >= 0:
                _accendi_contatori(E, {int(v): giorni.get(int(A[j, 0]), giorno_di(time.time())) for v in A[j, 2:4]})
        for x in E[:2]:
            x[x < 0] = giorno_di(time.time())
        resto.update(E_nato=E[0], E_acceso=E[1], E_accensioni=E[2])
    if "W" in z.files:
        resto["W"] = np.concatenate([z["W"], Wn])
    np.savez(NPZ + ".tmp.npz", V=V, F=F, A=A, C=C, C0=C0, P=np.asarray(par_lista, np.int32), **sal, **resto)
    altri = [k for k, _ in sorted(tab.items(), key=lambda x: x[1])]
    json.dump({"engrammi": testi, "altri_parametri": altri, "ricordi": ricordi}, open(META + ".tmp", "w"), ensure_ascii=False)
    os.replace(NPZ + ".tmp.npz", NPZ)
    if os.path.exists(STATO + ".tmp.npz"):
        os.replace(STATO + ".tmp.npz", STATO)
    os.replace(META + ".tmp", META)   # per ultimo: e' il segnale di ricarica del servizio
    print(f"{len(righe)} ricordi nuovi, {len(nuovi)} engrammi nuovi, {len(A) - n_a} archi nuovi")


def _rodaggio(giorni):
    return next((f for g, f in RODAGGIO if giorni < g), 1.0)


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
    for v in _voci(GIORNATA):   # il registro: l'ultima riga per (ts, testo) vale
        reg[(v.get("ts"), v.get("testo"))] = v
    agente = sorted((v for v in reg.values() if str(v.get("autore", "")).startswith("@agente") and not v.get("forzato")),
                 key=lambda v: v["ts"])
    cons = [(float(v["ts"]), int(n), v.get("flusso")) for v in _voci(DIARIO_RIFLESSO)
            if v.get("memorinvolontaria") and v.get("nid") for n in v["nid"]]
    n = len(EMOZIONI)
    with lucchetto():
        if not os.path.exists(STATO):   # Lux appena costruito: nessun rinforzo, niente da riconsolidare ancora
            return {"consegne": len(cons), "momenti": 0, "spostati": 0, "sorpresa_media": None, "effetto": 0.0}
        z, s = dict(np.load(NPZ)), dict(np.load(STATO))
        L = Lux.struttura(DIR)
        M = z.get("M", np.zeros((0, 4 + n)))
        fatti = {(round(float(t), 3), int(r)) for r, t in M[:, :2]}
        da = float(z.get("rodaggio_da", np.nan))
        acceso = np.isfinite(da) and SOGLIA_SORPRESA is not None and oggi >= da
        fattore = _rodaggio(oggi - da) if acceso else 0.0
        nuove, passi = [], {}
        for tc, nid, fl in cons:
            if (round(tc, 3), nid) in fatti:
                continue
            r = next((v for v in agente if tc < v["ts"] <= tc + FINESTRA_MOMENTO
                      and (None in (fl, v.get("flusso")) or fl == v.get("flusso"))), None)   # voci di prima: senza flusso
            if r is None:   # nessuna risposta ancora: la notte dopo
                continue
            fatti.add((round(tc, 3), nid))
            m = np.asarray([r["firma"].get(e, np.nan) if r.get("firma") else np.nan for e in EMOZIONI], np.float64)
            mc = m * z["fattore"] if "fattore" in z else m   # 1.15.0: il momento nella scala della carica
            js = [j for j in L.per_ricordo.get(nid, ()) if L.C0[j].any()]
            k = ~np.isnan(m)
            rms = float(np.sqrt(np.mean((mc[k] - L.C[js[0]][k] / L.W[js[0]]) ** 2))) if js and k.any() else np.nan
            nuove.append([nid, tc, r["ts"], rms, *m])
            if acceso and js and nid not in L.errati and nid < PRIMO_CORREZIONE and rms >= SOGLIA_SORPRESA:
                for j in js:
                    alfa = ALFA / (1 + max(0.0, float(np.log(s["S"][j] / s["S0"][j]))))
                    passi[j] = passi.get(j, 0.0) + np.where(k, fattore * alfa * (np.nan_to_num(mc) * L.W[j] - L.C[j]), 0.0)
        if passi:
            _applica_passi(z, s, L, passi)
        if nuove:
            z["M"] = np.concatenate([M, np.asarray(nuove, np.float64)])
        if nuove or passi:
            np.savez(NPZ + ".tmp.npz", **z)
            os.replace(NPZ + ".tmp.npz", NPZ)   # prima M: dopo un crash qui la consegna non si rifa' (niente doppio passo)
            if passi:
                np.savez(STATO + ".tmp.npz", **s)
                os.replace(STATO + ".tmp.npz", STATO)
            os.utime(META)   # il servizio ricarica
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
        C[j] = vecchia + np.clip(p / L.W[j], -PASSO_MAX, PASSO_MAX) * L.W[j]   # 1.16.0: freno sulla firma grezza
        rg = ranghi.get(int(z["A"][j, 0]), (0.0, 0.0))
        g = (z["fattore"] if "fattore" in z else 1.0) * L.W[j]   # 1.15.0-1.16.0: la stabilita' vuole la firma grezza
        q = (SA.stabilita_iniziale(C[j] / g, *rg, LUX.S_BASE, SOGLIA_FIRMA)
             / SA.stabilita_iniziale(vecchia / g, *rg, LUX.S_BASE, SOGLIA_FIRMA))
        S0[j] *= q
        S[j] *= q
    z.update(C=C, F=firme_engrammi(z["A"], C, len(z["V"])))
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
    with lucchetto():
        if not os.path.exists(STATO):
            return {"archi": 0, "spostati": 0, "rodaggio": 0.0, "dominanti": 0}
        z, s = dict(np.load(NPZ)), dict(np.load(STATO))
        if "avvicina_da" not in z or "RA" not in s or not (s["RA_P"] > 0).any():
            return {"archi": 0, "spostati": 0, "rodaggio": 0.0, "dominanti": 0}
        L = Lux.struttura(DIR)
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
            if p <= 0 or any(n >= PRIMO_CORREZIONE or n in L.errati or n not in L.ricordi for n in (a, b)):
                continue
            if L.ricordi[a].get("dominante") == L.ricordi[b].get("dominante"):
                continue
            forza = float(LUX.curva(max(oggi - float(u), 0.0), float(sr)))
            (ja, pa), (jb, pb) = profilo(a), profilo(b)
            if pa is None or pb is None:
                continue
            for js, verso in ((ja, pb), (jb, pa)):
                for j in js:
                    x = rod * ALFA / (1 + FRENO_LEGATI * max(0.0, float(np.log(s["S"][j] / s["S0"][j])))) * forza
                    passi[j] = passi.get(j, 0.0) + (1 - (1 - x) ** int(p)) * (verso * L.W[j] - L.C[j])
            toccati |= {a, b}
        archi = int((P > 0).sum())
        s["RA_P"] = np.zeros_like(P)
        cambiate = 0
        if passi:
            _applica_passi(z, s, L, passi)
            m = json.load(open(META))
            fat = z["fattore"] if "fattore" in z else np.ones(len(EMOZIONI), np.float32)
            for n in sorted(toccati):
                r = m["ricordi"][str(n)]
                js = profilo(n)[0]
                v = np.mean(z["C"][js] / (L.W[js, None] * fat), 0)
                f = {e: float(v[EMOZIONI.index(e)]) for e in (r.get("firma") or {}) if e in EMOZIONI}
                d = memoria.dominante(f) if f else None
                if d is not None and d != r.get("dominante"):
                    r.setdefault("dominante_nascita", r.get("dominante"))
                    r["dominante"] = d
                    cambiate += 1
            np.savez(NPZ + ".tmp.npz", **z)
            os.replace(NPZ + ".tmp.npz", NPZ)
            if cambiate:
                json.dump(m, open(META + ".tmp", "w"), ensure_ascii=False)
                os.replace(META + ".tmp", META)
        np.savez(STATO + ".tmp.npz", **s)
        os.replace(STATO + ".tmp.npz", STATO)
        os.utime(META)
    return {"archi": archi, "spostati": len(passi), "rodaggio": rod, "dominanti": cambiate}


def pota_ponti():
    """1.23.0 (B4, PIANO-PONTI-123.md), di notte: 1. via i ponti provvisori (la marca decade, Frey e Morris 1997); 2-3. i
    ponti stabili non usati nel giorno perdono il 18% del peso, tranne il 20% piu' forte (de Vivo 2017); 4. via sotto
    PONTE_W_MIN. Niente tetto per engramma (l'utente 13/11 notte: nella mente non c'e', c'e' l'effetto ventaglio, gia' in
    _dai_ponti). "Usato" e' un segno (PO_US) che
    ricombina mette e la notte toglie (revisione 13/11: l'orologio vissuto avanza prima della notturna). Sotto
    lucchetto rileggendo dal disco; il servizio poi ricarica"""
    vuoto = {"ponti": 0, "provvisori": 0, "calati": 0, "tagliati": 0}
    with lucchetto():
        if not os.path.exists(STATO):
            return vuoto
        s = dict(np.load(STATO))
        if "PO" not in s or not len(s["PO"]):
            return vuoto
        W, ST, US = s["PO_W"].copy(), s["PO_ST"], s["PO_US"]
        tieni = ST == 1
        protetti = np.zeros(len(W), bool)   # revisione 13/11: per rango, col quantile i pesi uguali non calavano mai
        st = np.nonzero(tieni)[0]
        protetti[st[np.argsort(-W[st], kind="stable")[:int(np.ceil(PONTE_PROTETTI * len(st)))]]] = True
        calo = tieni & (US == 0) & ~protetti
        W[calo] *= PONTE_CALO
        forti = tieni & (W >= PONTE_W_MIN)
        s.update(PO=s["PO"][forti], PO_R=s["PO_R"][forti], PO_W=W[forti], PO_ST=ST[forti],
                 PO_US=np.zeros(int(forti.sum()), np.int8))
        np.savez(STATO + ".tmp.npz", **s)
        os.replace(STATO + ".tmp.npz", STATO)
    return {"ponti": int(forti.sum()), "provvisori": int((~tieni).sum()), "calati": int(calo.sum()),
            "tagliati": int((tieni & ~forti).sum())}


def in_coda(vecchi, nuovi, batte):
    """1.21.0 (l'utente 11/11 punto 3 + 12/11 D4): la coda dei ricordi richiamati. vecchi = gia' in coda, in ordine; ogni
    nuovo (in ordine di richiamo) parte dal fondo e passa avanti ai VECCHI che batte (batte(nuovo, vecchio)); i nuovi
    della stessa selezione non si scavalcano"""
    coda = [(n, True) for n in vecchi]
    for n in nuovi:
        i = len(coda)
        while i > 0 and coda[i - 1][1] and batte(n, coda[i - 1][0]):
            i -= 1
        coda.insert(i, (n, False))
    return [n for n, _ in coda]


def riaccendi():
    """1.17.0 (punto 3): i messaggi del registro (giornata-firma.jsonl, l'utente e l'agente) arrivati dopo riacceso_fino accendono
    gli engrammi con la regola di accendi (stessa chiave o coseno >= SOGLIA_SEM): acceso = giorno del messaggio e una
    accensione in piu', una per giorno. Taglio ed embed FUORI dal lucchetto (revisione 11/11: il servizio a un filo e
    firma_subito non aspettano); dentro solo rilettura, controllo e scrittura. META toccato: il servizio ricarica"""
    reg = {}
    for v in _voci(GIORNATA):
        reg[(v.get("ts"), v.get("testo"))] = v
    z = np.load(NPZ)
    if "E_nato" not in z.files:
        return {"messaggi": 0, "engrammi": 0}
    fino = float(z["riacceso_fino"])
    voci = sorted((v for v in reg.values() if isinstance(v.get("ts"), (int, float)) and v["ts"] > fino
                   and str(v.get("testo") or "").strip()), key=lambda v: v["ts"])
    if not voci:
        return {"messaggi": 0, "engrammi": 0}
    L = Lux.struttura(DIR)
    accesi = [(giorno_di(v["ts"]), L.accendi(v["testo"])) for v in voci]   # gli indici restano: aggiungi mette in coda
    with lucchetto():
        z = dict(np.load(NPZ))
        if float(z["riacceso_fino"]) != fino:   # un altro riaccendi nel frattempo
            return {"messaggi": 0, "engrammi": 0}
        E = (z["E_nato"].copy(), z["E_acceso"].copy(), z["E_accensioni"].copy())
        prima = E[2].copy()
        for d, att in accesi:
            _accendi_contatori(E, dict.fromkeys(att, d))
        z.update(E_nato=E[0], E_acceso=E[1], E_accensioni=E[2], riacceso_fino=np.float64(voci[-1]["ts"]))
        np.savez(NPZ + ".tmp.npz", **z)
        os.replace(NPZ + ".tmp.npz", NPZ)
        os.utime(META)
    return {"messaggi": len(voci), "engrammi": int((E[2] != prima).sum())}


def _umore():
    """1.18.0: ansia e tristezza dell'omeostato (z), lette senza toccare il file; 0 se manca"""
    try:
        st = json.load(open(OMEOSTATO))["stato"]
    except (OSError, ValueError, KeyError):
        return 0.0
    return float(np.clip(max(float(st.get("anxiety") or 0), float(st.get("sadness") or 0), 0.0) / UMORE_PIENO, 0, 1))


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
    return ((1 - FRENO["ripetizione"] * rip) * (1 - FRENO["aperta"] * ap) * (1 - FRENO["importanza"] * imp))


def sbiadisci(oggi=None):
    """1.18.0 (punto 4): una volta per giorno vissuto, C x (1 - rodaggio x sbiadimento_e x freno); per le emozioni negative
    il freno ha anche l'umore. C0 ferma, F ricalcolata, S e S0 invariate. Sotto lucchetto rileggendo dal disco"""
    oggi = LUX.orologio() if oggi is None else oggi
    with lucchetto():
        z = dict(np.load(NPZ))
        if "sbiadimento_da" not in z or oggi <= float(z["sbiadito_fino"]) or not os.path.exists(STATO):
            return {"sbiadito": False, "giorno": oggi}
        s = np.load(STATO)
        L = Lux.struttura(DIR)
        rod = _rodaggio(oggi - float(z["sbiadimento_da"]))
        f = freno_archi(z["A"], s["S"], s["S0"], (z["E_nato"], z["E_acceso"], z["E_accensioni"]), SA.ranghi(z),
                        L.errati, oggi)
        neg = np.asarray([e not in POSITIVE and e not in NEUTRE for e in EMOZIONI])
        u = _umore()
        freno = f[:, None] * np.where(neg, 1 - FRENO["umore"] * u, 1.0)[None, :]
        C = (z["C"] * (1 - rod * z["sbiadimento"][None, :] * freno)).astype(np.float32)
        z.update(C=C, F=firme_engrammi(z["A"], C, len(z["V"])), sbiadito_fino=np.float64(oggi))
        np.savez(NPZ + ".tmp.npz", **z)
        os.replace(NPZ + ".tmp.npz", NPZ)
        os.utime(META)
    return {"sbiadito": True, "giorno": oggi, "rodaggio": rod, "umore": round(u, 3),
            "freno_medio": round(float(f.mean()), 3)}



def e_emoji(t):
    """1.22.0: engramma fatto solo di simboli (emoji, spunte, segni)"""
    c = [ch for ch in t if ch not in INVISIBILI]
    return bool(c) and all(unicodedata.category(ch) in ("So", "Sk", "Mn") for ch in c)


def significato(t):
    """1.22.0: il significato di un'emoji (emoji-significati.json, gesti dell'utente; assente = nome Unicode); None =
    nessun significato, si accende solo se identica"""
    parti = []
    for ch in t:
        if ch in INVISIBILI:
            continue
        if ch in SIGN:
            if SIGN[ch]:
                parti.append(SIGN[ch])
        else:
            parti.append(unicodedata.name(ch, "").lower())
    return ", ".join(p for p in parti if p) or None


def umore44():
    """1.22.0: (u sui 44 assi della traduzione L29, assi, calma, D = distanza dalla calma, D normale) dallo stato vero
    dell'agente col ritorno alla base per le ore passate (come stato.carica), senza rumore e senza scrivere; file assente o
    rotto = calma"""
    tr = np.load(TRADUZIONE_L29, allow_pickle=True)
    assi, calma, d_norm = [str(a) for a in tr["assi"]], tr["calma"].astype(np.float64), float(tr["D_normale"])
    try:
        d = json.load(open(OMEOSTATO))
        conf = json.load(open(os.path.join(os.path.dirname(OMEOSTATO), "eutimia.json")))
        k = 1 - np.exp(-conf["theta_ora"] * max(0.0, (time.time() - d["ts"]) / 3600))
        z = {e: v + k * (conf["baseline"].get(e, 0.0) - v) for e, v in d["stato"].items()}
    except (OSError, ValueError, KeyError, TypeError):
        return calma.copy(), assi, calma, 0.0, d_norm
    u = np.asarray([z.get(a, 0.0) for a in assi])
    return u, assi, calma, float(np.linalg.norm(u - calma)), d_norm


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
        self.V, self.F, self.A, self.C, self.P = z["V"].astype(VTIPO, copy=False), z["F"], z["A"], z["C"], z["P"]
        self.C0 = z["C0"] if "C0" in z.files else self.C   # una versione di prima della 1.14.0
        self.W = z["W"] if "W" in z.files else np.ones(len(self.A), np.float32)   # prima della 1.16.0
        self.fattore = z["fattore"] if "fattore" in z.files else np.ones(self.C.shape[1], np.float32)   # 1.21.0: firma_ora
        # 1.18.0 (l'utente 11/11, "stessa proporzione"): nella forza la firma degli engrammi alla nascita, cosi' la dose scende
        # come la carica (D3 del 09/11) e non col quadrato (con F sbiadirebbero carica e firma insieme)
        self.F0 = firme_engrammi(self.A, self.C0, len(self.V))
        m = json.load(open(f"{cartella}/lux-meta.json"))
        self.testi, self.altri, self.ricordi = m["engrammi"], m["altri_parametri"], {int(k): v for k, v in m["ricordi"].items()}
        self.chiavi = {chiave(t): i for i, t in enumerate(self.testi)}
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
            if n == 2 and param_testo(int(self.P[p0]), self.altri) == CORREGGE:
                o = self.da_codice[param_testo(int(self.P[p0 + 1]), self.altri)]
                self.corregge[r] = o
                self.corretto_da.setdefault(o, []).append(r)
            elif n == 1 and param_testo(int(self.P[p0]), self.altri) == FONTE:
                s = chiave(self.testi[a])
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
        if os.path.exists(STATO):
            z = np.load(STATO)
            self.S, self.S0, self.U = z["S"], z["S0"], z["U"]
            if "R_nid" in z.files:
                self.R = dict(zip(z["R_nid"].tolist(), z["R_ts"].tolist()))
            if "PO" in z.files:
                self.ponti = {(a, b): [w, st, us, ra, rb] for (a, b), w, st, us, (ra, rb) in
                              zip(z["PO"].tolist(), z["PO_W"].tolist(), z["PO_ST"].tolist(), z["PO_US"].tolist(),
                                  z["PO_R"].tolist())}
            if "FO" in z.files:
                self.fiducia = {s: [w, int(c), int(x)] for s, w, c, x in
                                zip(z["FO"].tolist(), z["FO_W"].tolist(), z["FO_C"].tolist(), z["FO_X"].tolist())}
                self.confermati = set(z["FO_OK"].tolist())
            if "RA" in z.files:
                self.archi_ric = {(a, b): [s_, u, n, p] for (a, b), s_, u, n, p in
                                  zip(z["RA"].tolist(), z["RA_S"].tolist(), z["RA_U"].tolist(), z["RA_N"].tolist(),
                                      z["RA_P"].tolist())}
            return
        firme = {n: r.get("firma") for n, r in self.ricordi.items()}   # 1.20.0: dal meta
        s0 = s0_ricordi(firme, SA.ranghi(np.load(NPZ)), self.ricordi)
        self.S = np.asarray([s0[int(r)] for r in self.A[:, 0]], np.float64)
        self.S0 = self.S.copy()
        self.U = np.full(len(self.A), float(LUX.orologio()))

    def salva_stato(self):
        with lucchetto():
            S, S0, U = self.S, self.S0, self.U
            if os.path.exists(STATO):   # 1.13.0: aggiungi ha messo archi nuovi dopo la lettura di questo Lux: restano
                d = np.load(STATO)
                if len(d["S"]) > len(S):
                    S, S0, U = (np.concatenate([x, d[k][len(x):]]) for x, k in ((S, "S"), (S0, "S0"), (U, "U")))
            ra = sorted(self.archi_ric.items())
            po = sorted(self.ponti.items())
            np.savez(STATO + ".tmp.npz", S=S, S0=S0, U=U, R_nid=np.asarray(list(self.R), np.int64),
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
        return s * 0.5 ** (max(0.0, ora - t) / PREDISPOSIZIONE_EMIVITA)

    def predisponi(self, nids, ora=None, oggi=None):
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
        return {e: float(v[EMOZIONI.index(e)]) for e in f if e in EMOZIONI}

    def _rango(self, nid):
        """1.21.0 (D4): (classe, intensita') per la coda: negativa 2 > neutra 1 > positiva 0, poi il valore della
        dominante nella firma di adesso. Senza dominante o firma: neutra, intensita' 0"""
        d = self.ricordi.get(nid, {}).get("dominante")
        f = self.firma_ora(nid)
        if d is None or not f:
            return (1, 0.0)
        return (0 if d in POSITIVE else 1 if d in NEUTRE else 2, f.get(d, 0.0))

    def consegna(self, testo, quanti=CONSEGNA_MAX, oggi=None, esclusi=(), ora=None, soglia=SOGLIA_RICHIAMO, da=None, a=None,
                 emozione=None, traccia=None, coda=None):
        """L'UNICA porta per dare ricordi all'agente (richiamo automatico, 11/10): richiama, rinforza gli archi dei
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
            q = in_coda(vecchi, selezione, lambda a, b: self._rango(a) > self._rango(b))
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
            traccia["candidati"] = [x for x in traccia.get("candidati", []) if x[1] * (1 + TRACCIA_K_MAX) >= soglia]
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
        if emo not in EMOZIONI:
            return None
        e = EMOZIONI.index(emo)
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

    def frasi(self, nid):
        """1.22.0 (l'utente 13/11, interfase 2-3): il ricordo diviso in frasi [(testo, archi, engrammi scritti nella
        frase)]. Una frase finisce col parametro di fine frase compreso; l'arco che lo porta va alla frase dopo (porta la
        sua prima parola; la sua parola di partenza resta della frase prima). Una frase senza lettere (numero di elenco
        "2.", emoji sola) si unisce alla frase dopo, o alla prima se e' l'ultima; una che comincia con un segno che si
        attacca (":D") alla frase prima. Unite di seguito ridanno ricomponi(nid)"""
        info, out = self.ricordi[nid], []
        pezzi, js, eng = [("arco", param_testo(p, self.altri)) for p in info["testa"]], [], set()
        for k, j in enumerate(sorted(self.per_ricordo.get(nid, []), key=lambda j: self.A[j, 1])):
            _, pos, a, b, p0, n = self.A[j].tolist()
            js.append(j)
            if k == 0:
                pezzi.append(("nodo", self.testi[a]))
                eng.add(a)
            if pos == 0:
                continue
            ps, fine = [param_testo(int(p), self.altri) for p in self.P[p0:p0 + n]], False
            for i, t in enumerate(ps):
                pezzi.append(("arco", t))
                fine = fine or t in FINE_FRASE
                dopo = ps[i + 1] if i + 1 < len(ps) else self.testi[b]
                # revisione 13/11: i segni che si attaccano (!) ... ;) e un engramma che e' solo un punto restano con la
                # fine della frase
                if fine and len(js) > 1 and not (dopo in ",.;:!?)…" or dopo.startswith("...")):
                    out.append((unisci(pezzi), js[:-1], eng))
                    pezzi, js, eng, fine = [], [j], set(), False
            pezzi.append(("nodo", self.testi[b]))
            eng.add(b)
        pezzi += [("arco", param_testo(p, self.altri)) for p in info["coda"]]
        if any(k == "nodo" for k, _ in pezzi) or not out:
            out.append((unisci(pezzi), js, eng))
        else:   # dopo l'ultimo punto solo parametri (una parentesi): restano attaccati all'ultima frase
            out[-1] = (unisci([("nodo", out[-1][0]), *pezzi]), out[-1][1] + js, out[-1][2])
        unite = []
        for t, js, eng in out:
            # ":D" dopo un punto va con la frase prima; una frase senza lettere va con questa
            if unite and (t.startswith(tuple(",.;:!?)…")) or not any(c.isalpha() for c in unite[-1][0])):
                t0, js0, eng0 = unite.pop()
                t, js, eng = unisci([("nodo", t0), ("nodo", t)]), js0 + js, eng0 | eng
            unite.append((t, js, eng))
        if len(unite) > 1 and not any(c.isalpha() for c in unite[-1][0]):
            t1, js1, eng1 = unite.pop()
            t0, js0, eng0 = unite.pop()
            unite.append((unisci([("nodo", t0), ("nodo", t1)]), js0 + js1, eng0 | eng1))
        return unite

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
            imp = (x * max(0.0, S_MAX - float(np.log(self.fan[i]))) * float(np.log1p(self.fan[i])) * N[i] / cnt[i]
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
            if hi < PONTE_A1 or lo < PONTE_A0:
                continue
            if lo >= PONTE_A1:
                v[0] = max(v[0] + PONTE_G * (1 - v[0]), PONTE_W_CATTURA)
                v[1] = v[2] = 1
            else:
                v[0] = max(0.0, v[0] - PONTE_D * float(np.sin(np.pi * (lo - PONTE_A0) / (PONTE_A1 - PONTE_A0))))
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
            forti = [[e for e in es if x(e) >= PONTE_A1 and np.log(self.fan[e]) < S_MAX] for es in (e1, e2)]
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
        for _, k, (ra, rb) in sorted(nuovi, key=lambda c: -c[0])[:PONTI_PER_RICHIAMO]:
            self.ponti[k] = [PONTE_W0, 0, 1, ra, rb]

    def _attivazione(self, att, js, eng, Fa, col, du, D, D_norm):
        """1.22.0: A_j degli archi js di una frase (RICERCA-RICHIAMO-EMOTIVO.md C1): forza + diffusione + senso + carica
        + umore. La diffusione conta solo gli engrammi scritti nella frase (eng): la parola di partenza dell'arco che
        apre la frase sta nella frase prima"""
        js = np.asarray(js)
        Cu = self.C[js][:, col].astype(np.float64)
        cos = (Cu @ du) / (np.linalg.norm(Cu, axis=1) * (np.linalg.norm(du) + 1e-12) + 1e-12) if D > 0 else 0.0
        diff = np.asarray([sum(att.get(e, 0.0) * (S_MAX - np.log(self.fan[e]))
                               for e in {int(self.A[j, 2]), int(self.A[j, 3])} & eng) for j in js])
        return (np.log(np.maximum(Fa[js], 1e-6)) + diff + LAMBDA_W * self.W[js].astype(np.float64)
                + GAMMA * np.log1p(np.linalg.norm(self.C[js], axis=1) / self.normC) + LAMBDA_0 * (D / D_norm) * cos)

    def ricombina(self, testo, numero=1, oggi=None, esclusi=(), ora=None, soglia=SOGLIA_RICHIAMO, emozione=None,
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
        selezione = [n for n, _ in punti[:RICORDI_TRATTI]] if sopra else []
        pa, dal = self._dai_ponti(att)   # 1.23.0 (B0): un ponte puo' far venire in mente un altro ricordo
        acc = {**pa, **{e: max(a, pa.get(e, 0.0)) for e, a in att.items()}}
        if sopra:
            selezione += [r for r in sorted(dal, key=lambda r: -dal[r]) if r not in via and r not in selezione
                          and r in self.ricordi][:RICORDI_TRATTI]
        vecchi = [] if coda is None else [n for c in dict.fromkeys(coda) for n in [self.da_codice.get(c)]
                                          if n is not None and n not in via]
        u, assi, calma, D, D_norm = umore44()
        col = [EMOZIONI.index(a) for a in assi]
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
            if a > TAU and len(presi) < TRATTI_MAX and tok + len(t) / CAR_TOKEN <= TOKEN_MAX:
                presi.append((n, t, js, eng))
                tok += len(t) / CAR_TOKEN
        mostrati = [n for n, _, _, _ in presi]
        cambiato = self._aggiorna_ponti(att)   # 1.23.0: prima i ponti che c'erano, poi quelli nuovi
        self._nascite(att, presi)
        if coda is not None:   # 1.21.0: la selezione entra in coda; chi e' mostrato ne esce
            nuovi = [n for n in sopra[:CONSEGNA_MAX] if n not in vecchi]
            q = in_coda(vecchi, nuovi, lambda a, b: self._rango(a) > self._rango(b))
            self._coseleziona(set(sopra[:CONSEGNA_MAX]) | {n for n in mostrati if n not in vecchi}, oggi)
            coda[:] = [self.ricordi[n]["codice"] for n in q if n not in mostrati]
        if traccia is not None and emozione:   # 1.19.0, come consegna: il diario della via emotiva
            ps = {n: p for n, p, _ in traccia.get("candidati", [])}
            traccia["senza"] = [n for n, p, _ in traccia.get("candidati", []) if p >= soglia and n not in via][:RICORDI_TRATTI]
            traccia["da_coda"] = [n for n in mostrati if n in vecchi]
            # revisione 13/11: l'emozione conta se ha deciso che affiorasse qualcosa; testa = il primo del richiamo
            # (i tratti mostrati sono in ordine di attivazione, non di richiamo): la usa !verifica emotiva!
            traccia["oltre_soglia"] = any(ps.get(n, soglia) < soglia for n in sopra)
            traccia["testa"] = sopra[:1]
            traccia["candidati"] = [x for x in traccia.get("candidati", []) if x[1] * (1 + TRACCIA_K_MAX) >= soglia]
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

    def _vs(self):
        """1.22.0: vettori della via semantica, con gli engrammi-emoji rifatti sul loro significato (zero se non ne
        hanno); calcolati al primo accendi, non all'avvio (l'embedder puo' non esserci ancora)"""
        if self._Vs is None:
            Vs = self.V.copy()
            em = [i for i, t in enumerate(self.testi) if e_emoji(t)]
            con = [(i, g) for i in em for g in [significato(self.testi[i])] if g]
            if con:
                Vs[[i for i, _ in con]] = embed([g for _, g in con]).astype(VTIPO)
            Vs[[i for i in em if significato(self.testi[i]) is None]] = 0
            self._Vs = Vs
        return self._Vs

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
        q = [significato(t) if e_emoji(t) else t for t in nodi]   # 1.22.0: le emoji per significato
        idx = [k for k, v in enumerate(q) if v]
        if not idx:
            return att
        S = coseni(embed([q[k] for k in idx]), self._vs())
        for row in S:
            for i in np.where(row >= SOGLIA_SEM)[0]:
                att[int(i)] = max(att.get(int(i), 0), float((row[i] - SOGLIA_SEM) / (1 - SOGLIA_SEM)))
        return att

    def sovrapposizione(self, testo, nid):
        """B6 (l'utente 01/11 sera, cattura nel behavioral tagging): engrammi del testo (n) e quanti coincidono con gli
        engrammi del ricordo nid (presi), con la regola di accendi: stessa chiave o coseno bge-m3 >= SOGLIA_SEM"""
        nodi = [t for k, t in T.taglia(testo) if k == "nodo"]
        mio = sorted({int(e) for j in self.per_ricordo.get(nid, []) for e in self.A[j, 2:4]})
        if not nodi or not mio:
            return len(nodi), 0
        S = coseni(embed(nodi), self.V[mio])
        presi = sum(self.chiavi.get(chiave(t)) in mio or bool((row >= SOGLIA_SEM).any()) for t, row in zip(nodi, S))
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
        S = coseni(self.V[a].astype(np.float32), self.V[b]) >= SOGLIA_SEM
        return min(S.any(1).mean(), S.any(0).mean()) >= CONFERMA_QUOTA

    def certo(self, sito):
        """D5 (13/11): certo quando la fiducia supera la soglia; un sito mai visto parte da FIDUCIA_W0"""
        return self.fiducia.get(chiave(sito), [FIDUCIA_W0])[0] >= FIDUCIA_CERTA

    def conferma(self, nid):
        """D2 (13/11): il ricordo nid viene da una fonte certa (l'utente o un sito certo): ogni ricordo di un ALTRO
        sito che dice la stessa cosa, non corretto e non gia' confermato, alza la fiducia del suo sito (Rescorla-Wagner).
        -> siti confermati"""
        r = self.ricordi.get(nid, {})
        miei = set(self.siti_di.get(nid, []))
        if r.get("fonte") != FONTE_CERTA and not any(self.certo(s) for s in miei):
            return []
        fatti = []
        candidati = {m for s, nids in self.ricordi_di_sito.items() if s not in miei for m in nids}
        for m in sorted(candidati - self.confermati - self.errati - {nid}):
            if not self._vicini(nid, m):
                continue
            for s in self.siti_di[m]:   # tutti i siti del ricordo confermato, tranne quelli della fonte
                if s in miei:
                    continue
                w = self.fiducia.setdefault(s, [FIDUCIA_W0, 0, 0])
                w[0] += FIDUCIA_G * (1 - w[0])
                w[1] += 1
                fatti.append(s)
            self.confermati.add(m)
        return fatti

    def smentisci(self, o):
        """D3 (13/11): il ricordo o e' stato corretto: la fiducia dei suoi siti scende subito. -> siti"""
        for s in self.siti_di.get(o, []):
            w = self.fiducia.setdefault(s, [FIDUCIA_W0, 0, 0])
            w[0] *= 1 - FIDUCIA_D
            w[2] += 1
        return self.siti_di.get(o, [])

    def accordi(self, nids, emozione):
        """1.19.0: accordo emotivo dei ricordi nids con l'indizio (emozione = {"assi": nomi inglesi, "q": vettore di
        lunghezza 1}) = coseno fra il profilo del ricordo sugli stessi assi e q"""
        cols = [EMOZIONI.index(a) for a in emozione["assi"]]
        Z = self.profz[np.searchsorted(self.prof_nid, np.asarray(nids, np.int64))][:, cols]
        Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9
        return Z @ np.asarray(emozione["q"], np.float64)

    def richiama(self, testo, quanti=3, soglia=SOGLIA_RICHIAMO, oggi=None, ora=None, emozione=None, traccia=None, att=None):
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
            punti[r] *= fac[r] / np.sqrt(self.ricordi[r]["n"]) * min(PREDISPOSIZIONE_MAX, 1 + self.spinta(r, ora))
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


def prova():
    L = Lux()
    orig = {n: r["testo"] for n, r in L.ricordi.items()}   # 1.20.0: dal meta
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
    elif cmd == "da-precedente":
        da_precedente()
    elif cmd == "sbiadisci":   # in produzione POST /sbiadisci
        print(json.dumps(sbiadisci()))
    elif cmd == "riaccendi":   # in produzione POST /riaccendi
        print(json.dumps(riaccendi()))
    elif cmd == "riconsolida":   # SOLO prove a servizio spento: in produzione POST /riconsolida (un salva_stato del
        # servizio in attesa del lucchetto riscriverebbe S e S0 di prima)
        print(json.dumps(riconsolida()))
    elif cmd == "prova":
        prova()
    elif cmd == "consegna":   # come la consegna vera: rinforza e scrive lux-stato.npz
        L = Lux()
        c = L.consegna(sys.argv[2])
        print(f"== ricordi {[nid for nid, _, _ in c]}\n{L.risposta_tool([nid for nid, _, _ in c])}")
    elif cmd == "correggi":   # 1.24.0 (D3): la smentita dei siti subito, come POST /correggi; fonte ignota: niente conferme
        o = Lux.struttura(DIR).da_codice[sys.argv[2]]
        cod = correggi(sys.argv[2], sys.argv[3])
        L = Lux()
        L.smentisci(o)
        L.salva_stato()
        print(cod)
    elif cmd == "richiama":
        L = Lux()
        for nid, p in L.richiama(sys.argv[2]):
            print(f"\n== ricordo {nid}  ({p:.2f})\n{L.ricomponi(nid)}")
