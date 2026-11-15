"""Lux degli engrammi: costanti, percorsi e funzioni pure comuni.
Parte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano
lux_engrammi, che riesporta tutto."""
import contextlib
import fcntl
import glob
import json
import os
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
VERSIONE = "1.25.0"   # 1.3.0: codice dei ricordi; 1.4.0: vettori L29 degli engrammi (lux-l29.npz, tolti 14/11: nessuno li leggeva); 1.5.0: aggiungi();
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
# 1.25.0 (l'utente 14/11, interfase 3-4, PIANO-INTERFASE-34-DIVISIONE-LUX.md): codice diviso in moduli; formato a blocchi
# (V, sal_F, C0 in lux-<nome>-<prima riga>.npy, A int32 su disco); contenuto identico alla 1.24.0 (da_precedente)
DIR = os.environ.get("LUX_DIR", f"/data/memoria-episodica-affettiva/engrammi/lux-{VERSIONE}")
PRECEDENTE = "/data/memoria-episodica-affettiva/engrammi/lux-1.24.0"   # da qui costruisci() riprende i vettori gia' calcolati, da_precedente() copia
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


# 1.25.0 (interfase 3-4 punto 3, l'utente 14/11): V e sal_F (73% di lux.npz, crescono solo in coda) stanno in blocchi
# lux-V-<prima riga>.npy e lux-salF-<prima riga>.npy, come C0 (carica alla nascita, "poi ferma"): un ricordo nuovo
# scrive tre blocchi piccoli invece di 78 MB; A su disco in int32 (in memoria int64 come prima). C cambia ogni notte su
# quasi tutti gli archi (98% diversi da C0 il 14/11): resta in lux.npz.
BLOCCHI = (("V", "lux-V"), ("sal_F", "lux-salF"), ("C0", "lux-C0"))


def _blocchi(cartella, nome):
    return sorted(glob.glob(f"{cartella}/{nome}-*.npy"))


def _righe(z):
    return {"V": len(z["F"]), "sal_F": len(z["sal_di"]), "C0": len(z["A"])}


def _righe_nei_blocchi(npz):
    """righe di V e sal_F gia' al sicuro nei blocchi: quelle che il lux.npz su disco conta (0 se non c'e' o se e' nel
    formato di prima, con V e sal_F dentro); i blocchi oltre sono avanzi di una scrittura interrotta"""
    if not os.path.exists(npz):
        return {k: 0 for k, _ in BLOCCHI}
    z = np.load(npz)
    return {k: 0 if k in z.files else n for k, n in _righe(z).items()}


def carica_npz(npz=None):
    """il contenuto di lux.npz come dizionario, coi blocchi di V e sal_F rimontati e A in int64 (1.25.0); legge anche
    il formato fino alla 1.24.0, tutto dentro lux.npz"""
    npz = npz or NPZ
    z = dict(np.load(npz))
    for k, nome in BLOCCHI:
        if k not in z:
            n = _righe(z)[k]
            pezzi = [np.load(b) for b in _blocchi(os.path.dirname(npz), nome)]
            if pezzi:   # niente blocchi: chiave assente come prima (C0 prima della 1.14.0)
                z[k] = np.concatenate(pezzi)[:n]
                assert len(z[k]) == n, f"{npz}: {k} ha {len(z[k])} righe nei blocchi, ne servono {n}"
    z["A"] = z["A"].astype(np.int64)
    return z


def salva_npz(z, npz=None):
    """scrive z (come da carica_npz): prima un blocco con le righe nuove di V e sal_F, poi lux.npz con os.replace.
    Le righe gia' nei blocchi non si riscrivono (crescono solo in coda)."""
    npz = npz or NPZ
    cartella = os.path.dirname(npz)
    gia = _righe_nei_blocchi(npz)
    for k, nome in BLOCCHI:
        for b in _blocchi(cartella, nome):   # avanzi di una scrittura interrotta
            if int(b.rsplit("-", 1)[1][:-4]) >= gia[k]:
                os.remove(b)
        if k in z and len(z[k]) > gia[k]:
            with open(f"{cartella}/{nome}.tmp", "wb") as f:   # fuori dal glob dei blocchi finche' non e' completo
                np.save(f, np.asarray(z[k][gia[k]:]))
            os.replace(f"{cartella}/{nome}.tmp", f"{cartella}/{nome}-{gia[k]:010d}.npy")
    resto = {k: v for k, v in z.items() if k not in dict(BLOCCHI)}
    np.savez(npz + ".tmp.npz", **{**resto, "A": np.asarray(z["A"], np.int32)})
    os.replace(npz + ".tmp.npz", npz)


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


def _umore():
    """1.18.0: ansia e tristezza dell'omeostato (z), lette senza toccare il file; 0 se manca"""
    try:
        st = json.load(open(OMEOSTATO))["stato"]
    except (OSError, ValueError, KeyError):
        return 0.0
    return float(np.clip(max(float(st.get("anxiety") or 0), float(st.get("sadness") or 0), 0.0) / UMORE_PIENO, 0, 1))


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
