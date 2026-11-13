# Test dei freni del riflesso (issue #3 del repo pubblico): gira senza server, senza GPU, senza toccare il diario vero.
import threading
import time

import riflesso as R
import riflesso_riepilogo as RP
import riflesso_cache as CA
import riflesso_memoria as M
import riflesso_via_emotiva as RVE
import riflesso_metadati as MD
import riflesso_vettore as VT
import riflesso_barra as B
import riflesso_firma as FI
import riflesso_stato as S
import riflesso_comune as C
RVE._via_emotiva = lambda *a: (None, None)   # 1.19.0: la via emotiva la prova engrammi/test_via_emotiva.py, mai la lente vera qui
RVE._leggi_risposta = lambda *a: None
if not R.os.path.exists(R.steering.VETTORI):   # repo pubblico e CI: i vettori di steering sono dati, qui vettori finti
    import numpy as np
    _g = np.random.default_rng(0)
    for _a in R.steering.EN.values():
        R.steering._vettori[_a] = {l: _g.standard_normal(2048).astype(np.float32) for l in R.steering.STRATI}
        R.steering._norme[_a] = {l: np.float32(1.0) for l in R.steering.STRATI}

diario = []
C._diario = diario.append
C.DIARIO = "/dev/null"

# minori (18/10): l'interruttore vale solo scritto [attivo: *sì*] / [vettori: *sì*]; il testo normale,
# esempi compresi, non accende niente
import tempfile  # noqa: E402
C.CONSENSO = R.Path(tempfile.mkdtemp()) / "consenso.md"
C.CONSENSO.write_text("# si accende con attivo: sì\n```\nattivo: sì\nvettori: sì\n```\n", encoding="utf-8")
assert not C.consenso_attivo() and not C.vettori_attivi(), "il testo normale accende il consenso"
C.CONSENSO.write_text("[attivo: *sì*]\n  [vettori: *sì*]  \n", encoding="utf-8")
assert C.consenso_attivo() and C.vettori_attivi(), "l'interruttore formattato non accende"

# punto C: la sentinella sopravvive a un giro in errore e scrive "kill" solo se lo spegnimento e' riuscito
giri = {"n": 0}


def vettori_attivi():
    giri["n"] += 1
    if giri["n"] == 1:
        raise RuntimeError("giro rotto")
    return False


esito = [False]
C.vettori_attivi = vettori_attivi
VT.calma = lambda: esito[0]
S._vettore_vivo[0] = True
t = threading.Thread(target=VT._sentinella, daemon=True)
t.start()
time.sleep(1.8)
assert t.is_alive(), "la sentinella e' morta dopo un giro in errore"
assert giri["n"] >= 2, "dopo l'errore non ha piu' controllato il consenso"
assert not any("kill" in v for v in diario), "kill scritto con lo spegnimento fallito"
esito[0] = True
time.sleep(0.8)
assert any("kill" in v for v in diario), "kill non scritto con lo spegnimento riuscito"

# punto E (18/10): la parola di emergenza e' "vectreflexstop", scritta dall'agente negli ultimi 4 messaggi
def m(ruolo, testo):
    return {"role": ruolo, "content": testo}


assert C._stop_chiesto([m("user", "ciao"), m("assistant", "basta cosi', VectReflexStop.")])
assert not C._stop_chiesto([m("user", "vectreflexstop")]), "vale solo per l'agente"
assert not C._stop_chiesto([m("assistant", "vectreflexstop")] + [m("user", "x")] * 4), "oltre gli ultimi 4"
assert not C._stop_chiesto([m("assistant", "riflesso vettoriale: off")]), "la frase vecchia non vale piu'"
assert C._stop_chiesto([m("assistant", "vectreflexstop"), m("system", "ora"), m("tool", "x"), m("user", "y")]), \
    "system e tool non spostano la finestra"

# con la parola nella conversazione il ricordo arriva, ma senza colore
import json, tempfile  # noqa: E401,E402
M.CONSEGNE = R.Path(tempfile.mkdtemp()) / "consegne.json"
C.consenso_attivo = C.vettori_attivi = lambda: True
M._lux_consegna = lambda testo, esclusi, emozione=None, coda=None, numero=None: {"codici": ["abc"], "risposta": "1°\nabc\nil mare",
                                                        "ricordi": [{"codice": "abc", "nid": 1, "dominante": "fear",
                                                                     "classe": "vissuto"}]}
emo_vero = VT._emo_del_ricordo
VT._emo_del_ricordo = lambda c: (1, "fear", 1.0)
VT._forza = lambda codice, emo: 1.13
colorati = []
corpo = lambda msgs: json.dumps({"messages": msgs}).encode()  # noqa: E731
# 25/10: col 35B spento (cron di Hermes) nessun ricordo, ne' chiesto al Lux ne' salvato fra le consegne
assert not M._sam_accesa(("127.0.0.1", 9)), "porta chiusa vista come l'agente accesa"
M._sam_accesa = lambda *a: False
chiesti = []
lux = M._lux_consegna
M._lux_consegna = lambda testo, esclusi, emozione=None, coda=None, numero=None: chiesti.append(testo) or lux(testo, esclusi)
spenta = corpo([m("user", "[IMPORTANT: You are running as a scheduled cron job.] backup")])
assert R.Proxy._memoria(None, spenta) == spenta and not chiesti and not M.CONSEGNE.exists(), "ricordo all'agente spenta"
M._sam_accesa = lambda *a: True
M._lux_consegna = lux
# 11/11: i cron di Hermes (flusso "altro") non ricevono ricordi: niente richiamo, niente consegna, niente vettore
chiesti.clear()
M._lux_consegna = lambda testo, esclusi, emozione=None, coda=None, numero=None: chiesti.append(testo) or lux(testo, esclusi)
cron = corpo([m("user", "[IMPORTANT: You are running as a scheduled cron job.] guarda il mare")])
fuori_c = {}
assert R.Proxy._memoria(None, cron, "altro", None, fuori_c) == cron and not chiesti and not fuori_c, "ricordo a un cron"
M._lux_consegna = lux


def memoria(msgs, *a):
    """PIANO-STEERING-RIFLESSO 7c (11/11): _memoria non accende niente, prepara il vettore del ricordo in fuori"""
    fuori = {}
    uscito = R.Proxy._memoria(None, corpo(msgs), *(a or ("chat",)), fuori=fuori)
    if fuori.get("vettore"):
        colorati.append(fuori["vettore"])
    return uscito


memoria([m("user", "guarda il mare"), m("assistant", "vectreflexstop"), m("user", "e adesso?")])
assert not colorati, "colorato con vectreflexstop negli ultimi messaggi"
assert "il mare" in json.dumps(json.loads(memoria([m("user", "di nuovo il mare")])))
assert colorati, "senza la parola il ricordo deve colorarsi"
emo, dose, strati = colorati[-1]
assert emo == "paura" and abs(dose - (0.036 + 0.009 * (1 - R.math.exp(-1)))) < 1e-9, (emo, dose)
assert strati == R.steering.strati("paura", dose), "il vettore non e' quello del modulo unico"
assert any(v.get("vettore") == ["paura", round(dose, 5)] for v in diario if isinstance(v, dict)), "vettore non a diario"

# punto 7b (11/11): D_e del punto 7 con soglia 0.5 e k 1.13 (provvisori), fasce di DOSI-EMOZIONI.md
F = R.steering.fasce()
assert VT._dose("fear", 0.49) is None, "sotto soglia niente vettore"
assert VT._dose("fear", None) is None and VT._dose("boredom", 2.0) is None and VT._dose("xyz", 2.0) is None
lo, hi = F["gioia"]
assert abs(VT._dose("joy", 100.0)[1] - hi) < 1e-9 and VT._dose("joy", 0.5)[1] > lo, "la dose resta nella fascia"
assert abs(VT._dose("joy", 1.13, 0.5)[1] - (lo + (hi - lo) * 0.5 * (1 - R.math.exp(-1)))) < 1e-9, "letto: meta' fascia"
pu = R.steering.pure()["amore"]
assert abs(VT._dose("love", 1.13)[1] - (pu[0] + (pu[1] - pu[0]) * (1 - R.math.exp(-1)))) < 1e-9, "diade pura"
assert abs(VT._dose("terror", 1.13)[1] - (1 - R.math.exp(-1))) < 1e-9, "terrore: posizione 0-1 per emo_dose"
VT._forza = lambda codice, emo: 0.2
colorati.clear()
memoria([m("user", "ancora il mare")])
assert not colorati, "S_e sotto soglia: niente vettore"
VT._forza = lambda codice, emo: 1.13

# punto H (18/10): i ricordi "letto" si colorano con l'emozione di quando li ha letti, a meta' dose
# Lux 1.20.0: nid, dominante e classe arrivano con la risposta di /consegna (prima da memoria.db)
assert emo_vero({"codice": "a", "nid": 1, "dominante": "fear", "classe": "vissuto"}) == (1, "fear", 1.0)
assert emo_vero({"codice": "b", "nid": 2, "dominante": "submission", "classe": "letto"}) == (2, "submission", 0.5), \
    "il ricordo letto non e' a meta' dose"
assert emo_vero({"codice": "c", "nid": None, "dominante": None, "classe": None}) == (None, None, 1.0), "ricordo ignoto"
VT._emo_del_ricordo = lambda c: (2, "submission", 0.5)
colorati.clear()
memoria([m("user", "un altro mare")])
assert colorati and colorati[0][:2] == VT._dose("submission", 1.13, 0.5)[:2], "la meta' dose non arriva al vettore"

# fase 2 step b (l'utente 09/11 + 11/11): piu' ricordi della stessa dominante, un vettore solo, quello a f massima
tre = [{"codice": "b2", "nid": 12, "dominante": "fear", "classe": "letto"},   # il vincitore (a1) non e' il primo
       {"codice": "a1", "nid": 11, "dominante": "fear", "classe": "vissuto"},
       {"codice": "c3", "nid": 13, "dominante": "fear", "classe": "vissuto"},
       {"codice": "d4", "nid": 14, "dominante": "fear", "classe": "vissuto"}]
lux_prima = M._lux_consegna
M._lux_consegna = lambda testo, esclusi, emozione=None, coda=None, numero=None: {"codici": [x["codice"] for x in tre],
                                                        "risposta": "1°\na1\nil faro", "ricordi": tre}
VT._emo_del_ricordo, finto = emo_vero, VT._emo_del_ricordo
forze = {"a1": 1.13, "b2": 9.0, "c3": None, "d4": 0.2}   # letto a meta' fascia, forza ignota, sotto soglia
VT._forza = lambda codice, emo: forze[codice]
colorati.clear()
n0 = len(diario)
memoria([m("user", "il faro di notte")])
assert len(colorati) == 1 and colorati[0][:2] == VT._dose("fear", 1.13)[:2], ("non e' il vettore a f massima", colorati)
assert any(v.get(R.FO.TOOL_RICORDO) == ["b2", "a1", "c3", "d4"] and v.get("nid") == [12, 11, 13, 14]
           for v in diario[n0:] if isinstance(v, dict)), "codici e nid della consegna non a diario"
VT._emo_del_ricordo, VT._forza = finto, (lambda codice, emo: 1.13)
M._lux_consegna = lux_prima

# 1.21.0 (l'utente 11/11 punti 3-4): la coda dei ricordi richiamati sta nella voce della conversazione, va al Lux a ogni
# lettura nuova, chi c'era tiene l'ora del suo recupero, dopo 30 minuti esce
mandate = []


numeri = []   # 1.22.0: il numero della ricombinazione nella conversazione


def lux_con_coda(testo, esclusi, emozione=None, coda=None, numero=None):
    mandate.append(coda)
    numeri.append(numero)
    k = f"q{len(mandate)}"
    return {"codici": [k], "risposta": f"1°\n{k}\nil porto", "coda": None if coda is None else ["q2", "q3"] if coda == [] else coda[1:] + ["q9"],
            "ricordi": [{"codice": k, "nid": 20 + len(mandate), "dominante": "fear", "classe": "vissuto"}],
            "impronta": {"fear": 1.5}}


M._lux_consegna = lux_con_coda
orologio_m = [5000.0]
tempo_vero, M.time.time = M.time.time, lambda: orologio_m[0]
porto = [m("user", "il porto di sera")]
memoria(porto)
assert mandate == [[]], mandate
assert M._voce_conv(porto)["coda"] == [["q2", 5000.0], ["q3", 5000.0]], M._voce_conv(porto)
assert "q1" not in M._esclusi_chat[0], "1.22.0: il ricordo di un tratto resta chiedibile intero con qlux"
riga = [x for x in diario if x.get("memorinvolontaria")][-1]
assert riga["tratti"] is True and riga["impronta"] == {"fear": 1.5}, riga   # 1.22.0: per barra-prefill
orologio_m[0] += 600
porto += [m("assistant", "si'"), m("user", "e il faro lontano?")]
memoria(porto)
assert mandate[-1] == ["q2", "q3"], mandate
assert M._voce_conv(porto)["coda"] == [["q3", 5000.0], ["q9", 5600.0]], "l'ora del recupero non e' rimasta"
orologio_m[0] = 5000.0 + M.CODA_DURATA + 1          # q3 scaduta, q9 no
porto += [m("assistant", "si'"), m("user", "e le barche ferme?")]
memoria(porto)
assert mandate[-1] == ["q9"], ("la coda non e' scaduta dopo 30 minuti", mandate)
C.consenso_attivo = lambda: False                   # consenso spento: niente coda (step b)
porto += [m("assistant", "si'"), m("user", "e il molo?")]
memoria(porto)
assert mandate[-1] is None, mandate
assert numeri == [1, 2, 3, 4], numeri   # 1.22.0: N-esima ricombinazione (a consenso spento la voce non entra)
C.consenso_attivo = lambda: True
M.time.time, M._lux_consegna = tempo_vero, lux_prima

# punto A (design dell'utente 18/10): il vettore appartiene alla KV cache del suo flusso
import socket  # noqa: E402

C.vettori_attivi = lambda: True
inviati = []
VT._cvec = inviati.append
R.ponte.dirs_emozione = lambda emo, dose: {"20": [dose, 0.0], "21": [0.0, dose]} if emo == "fear" else {"20": [dose, dose]}
VT.calma = lambda: (S._vettore_vivo.__setitem__(0, False), inviati.append("clear"))[0] is None
orologio = [1000.0]
R.time.time = lambda: orologio[0]
S._cw[0], S._caricato[0] = "pensatoio", orologio[0]
S._vissuto.update(chat=0.0, pensatoio=0.0)
S._vettori["pensatoio"].append({"emo": "fear", "dose": 0.2, "nato": 0.0, "durata": 100.0})
orologio[0] += 50
assert abs(VT._vivi("pensatoio")[0][1] - 0.1) < 1e-9, "a meta' durata la dose e' a meta'"
CA._cambia_cw("chat")                       # il pensatoio va in pausa con la sua cache
orologio[0] += 1000
VT._applica_flusso("chat")
assert inviati[-1] == "clear" or not S._vettore_vivo[0], "il vettore del pensatoio e' rimasto sulla chat"
CA._cambia_cw("pensatoio")                  # ripristino: stessa dose, la discesa riprende
assert abs(VT._vivi("pensatoio")[0][1] - 0.1) < 1e-9, "la discesa e' andata avanti durante la pausa"
S._vettori["pensatoio"].append({"emo": "joy", "dose": 0.1, "nato": VT._orologio("pensatoio"), "durata": 100.0})
VT._applica_flusso("pensatoio")
assert inviati[-1] == {"layers": {"20": [0.2, 0.1], "21": [0.0, 0.1]}, "relative": True}, "i vettori si sommano"
orologio[0] += 60                          # fear finita (50+50), joy a 0.04
assert [e for e, _ in VT._vivi("pensatoio")] == ["joy"]
assert not S._vettori["chat"]
VT._azzera_vettori()                        # vectreflexstop: tutti e due i flussi
assert not S._vettori["pensatoio"] and not S._vettori["chat"]

# 18/10: dopo un'interruzione il vettore torna alla dose della fine dell'ultima risposta di un tool
# (il gateway rifa' il giro da li'), non a quella del momento della pausa
S._cw[0], S._caricato[0] = "pensatoio", orologio[0]
S._vissuto["pensatoio"] = 0.0
S._vettori["pensatoio"][:] = [{"emo": "fear", "dose": 0.2, "nato": 0.0, "durata": 100.0}]
orologio[0] += 20
S._punto["pensatoio"] = VT._orologio("pensatoio")   # parte la richiesta dopo il tool, a 20 s
orologio[0] += 30                                  # genera 30 s, poi arriva la chat
a, b = socket.socketpair()
S._pens_vivi.append(a)
CA._interrompi_pensatoio()
S._pens_vivi.remove(a); a.close(); b.close()
CA._cambia_cw("chat")
orologio[0] += 500
CA._cambia_cw("pensatoio")
assert abs(VT._vivi("pensatoio")[0][1] - 0.16) < 1e-9, "il vettore non e' tornato alla fine dell'ultimo tool"
# 18/10: pensiero nuovo = cache del pensatoio ricominciata, i suoi vettori tornano al default
CA._nuovo_pensiero("primo risveglio")
S._vettori["pensatoio"].append({"emo": "fear", "dose": 0.2, "nato": VT._orologio("pensatoio"), "durata": 100.0})
CA._nuovo_pensiero("primo risveglio")
assert S._vettori["pensatoio"], "stesso pensiero: il vettore deve restare"
CA._nuovo_pensiero("secondo risveglio")
assert not S._vettori["pensatoio"] and VT._orologio("pensatoio") == 0.0, "pensiero nuovo: vettori non azzerati"

# il pensatoio parte solo con la chat fredda e senza una sua richiesta in volo
S._chat_calda[0] = orologio[0] - 2 * CA.AFK_S
assert CA._chat_ferma()
S._chat_in_volo[0] = 1
assert not CA._chat_ferma(), "il pensatoio partirebbe con la chat in volo"
S._chat_in_volo[0] = 0

# la chat interrompe davvero il pensatoio: il server vede la connessione chiusa
a, b = socket.socketpair()
S._pens_vivi.append(a)
CA._interrompi_pensatoio()
b.settimeout(1)
assert b.recv(10) == b"", "il pensatoio non e' stato interrotto"
a.close(); b.close()

# riepilogo a catena di montaggio (PIANO-RIEPILOGO-KV.md, l'utente 20/10): slot e server finti
RP.RIEPILOGO = R.Path(tempfile.mkdtemp()) / "riepilogo.json"
RP.RIEPILOGO_PROMUOVI = RP.RIEPILOGO.with_name(".riepilogo-promuovi")
CA.KV_RAM = R.Path(tempfile.mkdtemp())
RP.RIEPILOGO_LOG = R.Path(tempfile.mkdtemp()) / "logRiepilogo.md"
RP.FISSA = R.Path(tempfile.mkdtemp()) / "riepilogo-fissa.json"   # R6: mai quello vero


def scrive(testo, path="/workspace/memoria/logRiepilogo.md", funzione="write_file"):
    """come Occamy scrive la chiamata a uno strumento"""
    return (f"<tool_call>\n<function={funzione}>\n<parameter=path>\n{path}\n</parameter>\n"
            f"<parameter=content>\n{testo}\n</parameter>\n</function>\n</tool_call>")
SEP = "═" * 46 + "\nMEMORY (your personal notes)\n"
FISSO = "Sono l'agente.\n# regole\n"


def sistema(resto):
    return {"role": "system", "content": FISSO + SEP + resto}


INTEST = RP.INTESTAZIONE_RIEPILOGO
assert INTEST == ("Ecco dov'ero rimasta, questo è il succo della conversazione fino al momento in cui mi sono "
                  "addormentata:"), "intestazione diversa da quella approvata"
assert RP.ISTRUZIONE_RIEPILOGO == (
    "Devo scrivere, in meno di 60 parole, il succo di quest'ultimo messaggio o di quello dell'utente se necessario: le "
    "informazioni salienti che voglio conservare dell'ultimo scambio. Non i messaggi precedenti. Solo testo, numeri o "
    "simboli logici se utili, per esempio: uguale può diventare =, implica →, maggiore >. Se necessario posso "
    "inserire il codice di un ricordo che reputo utile per questo riassunto. Se in questo scambio mi è affiorato un "
    "ricordo, aggiungo il suo codice. Lo scrivo con write_file in /workspace/memoria/logRiepilogo.md."), \
    "istruzione diversa da quella approvata"

# riepilogo.json assente o rotto = nessun blocco; rotto = voce nel diario
assert RP._riepilogo_carica() == {"blocco": [], "nuovi": []}
n = len(diario)
RP.RIEPILOGO.write_text("{rotto", encoding="utf-8")
assert RP._riepilogo_carica() == {"blocco": [], "nuovi": []}
assert any("riepilogo" in v for v in diario[n:]), "riepilogo.json rotto senza voce nel diario"

# il blocco va subito prima della riga ══, identico a ogni richiesta della chat
RP._riepilogo_salva({"blocco": ["r1", "r2"], "nuovi": []})
uno = {"messages": [sistema("Conversation started: lunedi"), m("user", "[utente] ciao")]}
due = {"messages": [sistema("Conversation started: lunedi"), m("user", "[utente] ciao"), m("assistant", "ciao"),
                    m("user", "[utente] come va")]}
for d in (uno, due):
    RP._metti_blocco(d, RP._riepilogo_carica()["blocco"])
assert uno["messages"][0]["content"] == FISSO + INTEST + "\nr1\nr2\n\n" + SEP + "Conversation started: lunedi"
assert uno["messages"][0]["content"] == due["messages"][0]["content"], "blocco diverso fra due richieste"
senza = {"messages": [sistema("x")]}
RP._metti_blocco(senza, [])
assert senza["messages"][0]["content"] == FISSO + SEP + "x", "senza righe il system deve restare com'e'"
n = len(diario)
d = {"messages": [{"role": "system", "content": "breve"}]}
RP._metti_blocco(d, ["r1"])
assert d["messages"][0]["content"] == "breve\n\n" + INTEST + "\nr1\n\n", "senza riga ══ il blocco va in fondo"
assert any("riepilogo" in v for v in diario[n:]), "riga ══ assente senza voce nel diario"

# tetto: oltre 40k token (caratteri / 3) via le righe piu' vecchie
lunghe = [f"{i:03d}" + "x" * 997 for i in range(200)]
dentro = RP._nel_tetto(lunghe)
assert dentro and dentro == lunghe[-len(dentro):], "il tetto deve tenere le righe piu' recenti"
assert len(RP._blocco(dentro)) / 3 <= RP.RIEPILOGO_TETTO < len(RP._blocco(lunghe[-len(dentro) - 1:])) / 3
assert RP._nel_tetto(["a", "b"]) == ["a", "b"]

# quando parte: solo la risposta FINALE a un messaggio dell'utente
fin = {"testo": "ciao l'utente", "finish": "stop", "tool_calls": False}
del_bridge = json.dumps({"messages": [m("user", "[utente] ciao")]}).encode()
assert RP._deve_riassumere(del_bridge, fin)
assert not RP._deve_riassumere(json.dumps({"messages": [m("user", "Review the conversation above")]}).encode(), fin), \
    "il background review di Hermes non si riassume"
assert not RP._deve_riassumere(del_bridge, {**fin, "finish": "length"})
assert not RP._deve_riassumere(del_bridge, {**fin, "tool_calls": True})
assert not RP._deve_riassumere(del_bridge, {**fin, "testo": "  "})
assert not RP._deve_riassumere(json.dumps({"messages": [m("user", "[IMPORTANT: skill blocco-appunti ...]")]}).encode(),
                              fin), "il pensatoio non si riassume (20/10: solo la chat)"
assert RP._deve_riassumere(json.dumps({"messages": [m("user", "[utente] cerca"), m("assistant", ""),
                                                   {"role": "tool", "content": "x"}]}).encode(), fin), \
    "la risposta finale dopo un tool si riassume"

# i passi, nell'ordine esatto, dentro i lucchetti
passi, chiesti = [], []
CA._slot = lambda az, nome: passi.append((az, nome)) or True
VT.calma = lambda: (S._vettore_vivo.__setitem__(0, False), passi.append("calma")) and True


def chiedi(path, payload, rompi=None):
    passi.append(path)
    chiesti.append((path, payload))
    if path == rompi:
        raise OSError("server giu'")
    if path == "/apply-template":
        return {"prompt": "<|im_start|>system\nTOOLS\n" + payload["messages"][0]["content"]
                          + "<|im_end|>\n<|im_start|>user\n[utente] ciao<|im_end|>\n<|im_start|>assistant\n<think>\n"}
    return {} if payload["n_predict"] == 1 else {"content": scrive("un saluto\n→ ciao")}


C._chiedi = chiedi
(CA.KV_RAM / "riepilogo.kv").write_bytes(b"x")
RP._riepilogo_salva({"blocco": ["r1"], "nuovi": ["n1"]})
inoltrato = {"messages": [sistema("Conversation started: lunedi"), m("user", "[utente] ciao")], "tools": [M.TOOL]}
S._cw[0] = "chat"
S._vettore_vivo[0] = True
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", "lei mi saluta")
assert passi == ["calma", "/apply-template", "/completion", "/apply-template", ("restore", "riepilogo.kv"),
                 "/completion", ("save", "riepilogo.kv"), ("restore", "chat.kv")], passi
assert chiesti[0][1] == inoltrato, "il prompt del riassunto deve partire dal corpo inoltrato esatto"
# il <think> del turno resta: il riassunto riusa la cache della risposta appena data
gen = chiesti[1][1]
assert gen == {"prompt": ("<|im_start|>system\nTOOLS\n" + inoltrato["messages"][0]["content"]
               + "<|im_end|>\n<|im_start|>user\n[utente] ciao<|im_end|>\n<|im_start|>assistant\n<think>\n"
               + "lei mi saluta\n</think>\n\nciao l'utente!<|im_end|>\n<|im_start|>user\n" + RP.ISTRUZIONE_RIEPILOGO
               + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"),
               "n_predict": 220, "cache_prompt": True}, gen
assert RP._riepilogo_carica() == {"blocco": ["r1"], "nuovi": ["n1", "un saluto → ciao"]}, "riga non aggiunta"
assert RP.RIEPILOGO_LOG.read_text() == "un saluto → ciao\n", "riga non scritta in logRiepilogo.md"
# l'utente 10/11 (skill riepilogo): solo write_file su logRiepilogo.md; altro strumento, altro file o testo semplice = scarto
assert RP._riga_scritta("<tool_call>\n<function=write_file>\n<parameter=path>\n/workspace/memoria/logRiepilogo.md\n"
                       "</parameter>\n<parameter=content>\ntagliata a met") == "\ntagliata a met"
# 3.5.3 (10/11, diario della sera): lo stesso file visto dalla casa dell'agente; chiamata tagliata prima del path
assert RP._riga_scritta(scrive("casa", path="/home/agente/workspace/memoria/logRiepilogo.md")) == "\ncasa\n"
assert RP._riga_scritta("<tool_call>\n<function=write_file>\n<parameter=content>\nsenza path, tagli") == "\nsenza path, tagli"
assert RP._riga_scritta("<tool_call>\n<function=write_file>\n<parameter=content>\nx\n</parameter>\n</function>") is None, \
    "chiamata intera senza path presa per buona"
for sbagliata in (scrive("x", path="/workspace/altro.md"), scrive("x", funzione="memorinvolontaria"), "solo testo"):
    st0 = RP._riepilogo_carica()
    risp = C._chiedi
    C._chiedi = lambda p, x, s_=sbagliata: {"content": s_} if p == "/completion" and x["n_predict"] == 220 else risp(p, x)
    assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (False, "scartato"), sbagliata
    C._chiedi = risp
    assert RP._riepilogo_carica() == st0 and "scartato" in diario[-1]["riepilogo"], sbagliata
dopo = FISSO + INTEST + "\nn1\nun saluto → ciao\n\n"
tpl = chiesti[2][1]
assert tpl["tools"] == [M.TOOL] and tpl["messages"][0]["content"] == dopo + SEP + "Conversation started: lunedi"
assert chiesti[3][1] == {"prompt": "<|im_start|>system\nTOOLS\n" + dopo, "n_predict": 1, "cache_prompt": True,
                         "checkpoint_tag": "riepilogo"}, \
    "il prefill del riepilogo si taglia subito prima della riga ══"
assert S._cw[0] == "chat"

# un passo che fallisce: la chat torna comunque nello slot, il riepilogo non si salva
passi.clear(); chiesti.clear()
C._chiedi = lambda p, x: chiedi(p, x, rompi="/completion")
S._cw[0] = "chat"
n = len(diario)
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert passi[-1] == ("restore", "chat.kv") and ("save", "riepilogo.kv") not in passi, passi
assert S._cw[0] == "chat" and any("riepilogo" in v for v in diario[n:])

# prima riga dopo una dormita: riepilogo.kv non c'e', il prefill parte dallo slot com'e'
C._chiedi = chiedi
(CA.KV_RAM / "riepilogo.kv").unlink(missing_ok=True)
passi.clear()
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert ("restore", "riepilogo.kv") not in passi and ("save", "riepilogo.kv") in passi
assert "calma" not in passi, "senza vettore vivo niente clear: puo' troncare uno stream in corso"

# la chat non torna nello slot: la prossima richiesta della chat deve rifare il restore
CA._slot = lambda az, nome: passi.append((az, nome)) or nome != "chat.kv"
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert S._cw[0] == "altro", "restore della chat fallito ma _cw dice chat"
CA._slot = lambda az, nome: passi.append((az, nome)) or True

# alla dormita (flag): i nuovi diventano il blocco, riepilogo.kv promossa a chat e poi buttata
RP._riepilogo_salva({"blocco": ["vecchia"], "nuovi": ["a", "b"]})
RP.RIEPILOGO_PROMUOVI.write_text("")
(CA.KV_RAM / "riepilogo.kv").write_bytes(b"x")
(CA.KV_RAM / "riepilogo.kv.ckpt").write_bytes(b"x")
passi.clear()
S._cw[0] = "pensatoio"
RP._promuovi()
assert passi == [("save", "pensatoio.kv"), ("restore", "riepilogo.kv")], passi
assert RP._riepilogo_carica() == {"blocco": ["a", "b"], "nuovi": []}
assert RP.RIEPILOGO_LOG.read_text() == "", "logRiepilogo.md non svuotato alla promozione"
assert not RP.RIEPILOGO_PROMUOVI.exists(), "flag non tolto"
assert not (CA.KV_RAM / "riepilogo.kv").exists() and not (CA.KV_RAM / "riepilogo.kv.ckpt").exists()
assert S._cw[0] == "chat"
passi.clear()
RP._promuovi()
assert passi == [] and RP._riepilogo_carica()["blocco"] == ["a", "b"], "senza flag non si promuove niente"
RP.RIEPILOGO_PROMUOVI.write_text("")
RP._promuovi()
assert passi == [], "con la chat nello slot e senza riepilogo.kv non si tocca lo slot (la chat vecchia si butta)"
assert RP._riepilogo_carica()["blocco"] == ["a", "b"], "doppio switch senza righe nuove: il blocco promosso e' sparito"

# BLOCCO B (PIANO-RIEPILOGO-KV.md 3.5, K4 K10 K14 K15 K18, l'utente 10/11): avviso dei 90k, [cwswitch], switch a 100k
assert RP.AVVISO_90K == (
    "[avviso di spazio: la conversazione ha superato i 90mila token e la finestra si sta riempiendo. A 100mila "
    "passerò da sola a una conversazione nuova, che riparte dal mio riepilogo. Se voglio farlo prima, scrivo "
    "[cwswitch] in coda al riepilogo.]"), "avviso dei 90k diverso da quello approvato (K10)"
assert S.SOGLIA_AVVISO == 90_000 and S.SOGLIA_CW == 100_000
RP.DORMI_FLAG = R.Path(tempfile.mkdtemp()) / ".dormi-richiesto"   # quello vero spegne l'agente (agente-dormi.path)
RP.SWITCH_IN_CORSO = RP.DORMI_FLAG.with_name(".switch-in-corso")
risposta_sam = ["un saluto"]
chiedi_base = chiedi


def chiedi(path, payload, rompi=None):
    r = chiedi_base(path, payload, rompi)
    return {"content": scrive(risposta_sam[0])} if path == "/completion" and payload["n_predict"] == 220 else r


C._chiedi = chiedi


def generato():
    return next(p for pa, p in chiesti if pa == "/completion" and p["n_predict"] == 220)["prompt"]


def coda_istruzione(avviso):
    return ("<|im_start|>user\n" + (RP.AVVISO_90K + "\n\n" if avviso else "") + RP.ISTRUZIONE_RIEPILOGO
            + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")


RP._riepilogo_salva({"blocco": [], "nuovi": []})
for tok, avviso in ((50_000, False), (90_000, False), (90_001, True), (100_000, True), (100_001, False)):
    chiesti.clear()
    S._tok_cw["chat"] = tok
    assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (False, "ok")
    assert generato().endswith(coda_istruzione(avviso)), (tok, generato()[-400:])
# [cwswitch] con l'avviso: tolta dalla riga, switch chiesto; senza avviso non vale
RP._riepilogo_salva({"blocco": [], "nuovi": []})
S._tok_cw["chat"] = 95_000
risposta_sam[0] = "ci salutiamo  [CWSwitch] "
assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (True, "ok")
assert RP._riepilogo_carica()["nuovi"] == ["ci salutiamo"], RP._riepilogo_carica()
S._tok_cw["chat"] = 50_000
assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (False, "ok"), "[cwswitch] senza avviso"
risposta_sam[0] = "un saluto"

# lo switch: a fine turno dell'utente, dopo il riepilogo qualunque sia l'esito (K18), mai dopo un tool, mai a chat in volo
fine = {"testo": "ciao l'utente", "ragionamento": "", "finish": "stop", "tool_calls": False, "chat": True}
corpo_utente = json.dumps(inoltrato).encode()


def switch_fatto():
    fatto = RP.DORMI_FLAG.exists()
    RP.DORMI_FLAG.unlink(missing_ok=True)
    return fatto


S._tok_cw["chat"] = 50_000
RP._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "switch sotto i 100k"
S._tok_cw["chat"] = 105_000
n = len(diario)
RP._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "niente switch sopra i 100k"
assert any("switch" in str(v.get("cw", "")) for v in diario[n:] if isinstance(v, dict)), diario[n:]
RP._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "secondo switch prima della promozione (revisione blocco B, punto 1)"
RP.RIEPILOGO_PROMUOVI.write_text("")
RP._promuovi()
assert S._tok_cw["chat"] == 0, "dopo la promozione il conteggio vecchio della chat resta"
S._tok_cw["chat"] = 105_000
risposta_sam[0] = "   "
RP._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "riepilogo vuoto: lo switch deve partire lo stesso (K18)"
risposta_sam[0] = "un saluto"
RP.RIEPILOGO_PROMUOVI.write_text(""); RP._promuovi(); S._tok_cw["chat"] = 105_000
passi.clear()
RP._fine_chat(corpo_utente, {**fine, "finish": "length"}, None)
assert switch_fatto() and "/completion" not in passi, "risposta tagliata: niente riepilogo, switch si'"
RP.RIEPILOGO_PROMUOVI.write_text(""); RP._promuovi(); S._tok_cw["chat"] = 105_000
RP._fine_chat(corpo_utente, {**fine, "finish": "tool_calls", "tool_calls": True}, None)
assert not switch_fatto(), "switch a meta' turno (dopo un tool)"
RP._fine_chat(json.dumps({"messages": [m("user", "Review the conversation above")]}).encode(), fine, None)
assert not switch_fatto(), "switch dopo il background review di Hermes"
RP._fine_chat(corpo_utente, {**fine, "finish": None, "interrotta": True}, None)
assert not switch_fatto(), "switch dopo una risposta interrotta da Hermes"
RP.SWITCH_IN_CORSO.write_text("")
RP._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "switch mentre ne gira gia' uno (mezzanotte)"
RP.SWITCH_IN_CORSO.unlink()
RP._riassumi, riassumi_vero = (lambda *a: 1 / 0), RP._riassumi
RP._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "un'eccezione del riepilogo ha saltato lo switch (K18)"
assert "riepilogo fallito" in diario[-1]["cw"], diario[-1]
RP._riassumi = riassumi_vero
RP.RIEPILOGO_PROMUOVI.write_text(""); RP._promuovi(); S._tok_cw["chat"] = 105_000
S._chat_in_volo[0] = 1
RP._riassumi = lambda *a: (False, "ok")   # 3.5.3: il riepilogo vero aspetterebbe la fine della risposta in volo
RP._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "switch con una risposta della chat in volo (revisione blocco B, punto 4)"
RP._riassumi = riassumi_vero
S._chat_in_volo[0] = 0
S._tok_cw["chat"] = 50_000
RP._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "lo switch rimandato non e' partito alla fine della risposta in volo"
RP.RIEPILOGO_PROMUOVI.write_text(""); RP._promuovi()
S._tok_cw["chat"] = 50_000
RP._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "dopo la promozione un rimandato vecchio e' ripartito"

# K4/K17: l'avviso dei 100k della chat non c'e' piu' nel corpo inoltrato, quello del pensatoio resta
class Finto:
    def _memoria(self, body, flusso=None):
        return body

    def _inoltra(self, body, flusso=None, vettore=None):
        self.inoltrato = json.loads(body)
        self.vettore = vettore


CA._typing = lambda: False
S._chat_calda[0] = orologio[0] - 2 * CA.AFK_S
for fl, primo, atteso in (("chat", "[utente] ciao", None),
                          ("pensatoio", "[IMPORTANT: skill blocco-appunti] pensa",
                           "[avviso di spazio: questo flusso di pensiero ha superato i 100mila token e la finestra si "
                           "sta riempiendo: tutto rallenta. È il momento di tirare le fila e chiudere il pensiero.]")):
    S._tok_cw[fl], S._avvisato_cw[fl] = 120_000, False
    f = Finto()
    R.Proxy._post_chat(f, json.dumps({"messages": [m("user", primo)]}).encode(), True, fl)
    coda = f.inoltrato["messages"][-1]["content"]
    assert ("avviso di spazio" in coda) == bool(atteso) and (not atteso or coda.endswith(atteso)), (fl, coda)
S._tok_cw.update(chat=0, pensatoio=0)

# 24/10: stato dell'agente nel nome della chat. La fase va in R.FASE: legge, pensa, scrive, tool, vuoto = ferma
B.FASE = str(R.Path(tempfile.mkdtemp()) / "fase")
fase = lambda: R.Path(B.FASE).read_text()
es = {"testo": "", "ragionamento": "", "finish": None, "tool_calls": False, "chat": True}
sse = lambda delta, fine=None: ("data: " + R.json.dumps({"choices": [{"delta": delta, "finish_reason": fine}]}) + "\n\n").encode()
B._segna_fase("legge")
assert fase() == "legge"
R._tee_sse(b"", sse({"reasoning_content": "hm"}), None, es)
assert fase() == "pensa", fase()
R._tee_sse(b"", sse({"content": "Ciao"}), None, es)
assert fase() == "scrive", fase()
R._tee_sse(b"", sse({"tool_calls": [{"index": 0}]}), None, es)
assert fase() == "tool", fase()
R._tee_sse(b"", b"data: {rotto\n\n", None, es)
assert fase() == "tool", "un chunk rotto ha cambiato la fase"
es["chat"] = False
R._tee_sse(b"", sse({"content": "x"}), None, es)
assert fase() == "tool", "una richiesta che non e' della chat ha cambiato la fase"

# BLOCCO A (PIANO-RIEPILOGO-KV.md 3.5, M1-M4 K5 K6, l'utente 10/11): blocco metadati in coda all'ultima risposta dell'agente
MD.ORE = R.Path(tempfile.mkdtemp()) / "ore-messaggi.json"
assert C._ora_blocco(R.time.struct_time((2026, 11, 3, 9, 5, 0, 0, 307, 0))) == "[09:05|03/11/2026]"
MD._motore_attivo = lambda: True
assert MD._righe_metadati("[09:05|03/11/2026]") == [MD.PENSATOIO_DOVE, "[pensatoio]", "[09:05|03/11/2026]"]
assert MD._righe_metadati("[09:05|03/11/2026]", "chat") == ["[pensatoio]", "[09:05|03/11/2026]"], \
    "nella chat PENSATOIO_DOVE non va (l'utente 10/11 sera)"
MD._motore_attivo = lambda: False
assert MD._righe_metadati("[x]")[1] == "[/pensatoio]"
n = len(diario)
MD._motore_attivo = lambda: 1 / 0
assert MD._righe_metadati("[x]")[1] == "[/pensatoio]" and len(diario) > n, "systemctl rotto: congelato + diario"
MD._motore_attivo = lambda: True
META = "\n\n" + "\n".join(["a", "b"])
tc = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
                                                          "function": {"name": "read_file", "arguments": "{}"}}]}
for msgs, dove in (([sistema("s"), m("user", "[utente] ciao"), m("assistant", "ciao!"), m("user", "[utente] come va")], 2),
                   ([sistema("s"), m("user", "[utente] u"), m("assistant", "r"), m("user", "[utente] v"), tc,
                     {"role": "tool", "tool_call_id": "c1", "content": "x"}], 2),
                   ([sistema("s"), m("user", "[IMPORTANT: cron] pensa")], 1),
                   ([sistema("s"), m("user", "[IMPORTANT: cron] pensa"), tc,
                     {"role": "tool", "tool_call_id": "c1", "content": "x"}], 1)):
    prima = json.loads(json.dumps(msgs))
    MD._metti_metadati(msgs, ["a", "b"])
    for k, (p, d) in enumerate(zip(prima, msgs)):
        atteso = {**p, "content": p["content"] + META} if k == dove else p
        assert d == atteso, (dove, k, d)
lista = [m("user", "[utente] u"), {"role": "assistant", "content": [{"type": "text", "text": "r"}]}, m("user", "[utente] v")]
MD._metti_metadati(lista, ["a"])
assert lista[1]["content"][-1] == {"type": "text", "text": "\n\na"}

# l'ora: quella di ARRIVO dell'ultimo messaggio user, fissata a inizio turno e riusata nei giri di tool
orologio[0] = R.time.mktime((2026, 11, 3, 9, 5, 0, 0, 0, -1))
turno = [sistema("s"), m("user", "[utente] ok")]
assert MD._ora_arrivo(turno) == "[09:05|03/11/2026]"
orologio[0] += 120
assert MD._ora_arrivo(turno + [tc, {"role": "tool", "tool_call_id": "c1", "content": "x"}]) == "[09:05|03/11/2026]", \
    "nei giri di tool l'ora cambia"
dopo = turno + [m("assistant", "bene"), m("user", "[utente] ok")]
assert MD._ora_arrivo(dopo) == "[09:07|03/11/2026]", "un messaggio uguale a un turno nuovo tiene l'ora vecchia"
assert json.loads(MD.ORE.read_text())[C._conversazione(turno)]["arrivi"][C._impronta("[utente] ok")] == "[3/11/2026|9:07]", \
    "arrivi nel formato di oggi (dato della fase 2 del Lux)"

# il corpo inoltrato: niente piu' ora davanti ai messaggi dell'utente, PENSATOIO_DOVE solo nel blocco
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [sistema("s"), m("user", "[utente] ciao"), m("assistant", "ciao!"),
                                               m("user", "[utente] dimmi")]}).encode(), True, "chat")
ms = f.inoltrato["messages"]
# l'utente 10/11 sera: nella chat il blocco (stato del pensatoio + ora) all'INIZIO del suo ultimo messaggio
assert ms[3]["content"] == "[pensatoio]\n" + MD._ora_arrivo(ms) + "\n\n[utente] dimmi", ms[3]
assert ms[1]["content"] == "[utente] ciao" and ms[2]["content"] == "ciao!", ms
assert json.loads(f._senza)["messages"][3]["content"] == "[utente] dimmi", "il corpo senza metadati serve al prefill"
lista = [m("assistant", "r"), {"role": "user", "content": [{"type": "text", "text": "[utente] v"}]}]
MD._metti_metadati(lista, ["a"], "chat")
assert lista[1]["content"][0] == {"type": "text", "text": "a\n\n"} and lista[0]["content"] == "r"
assert not hasattr(R, "_metti_ore"), "l'ora davanti ai messaggi dell'utente si toglie (M3)"

# revisione del blocco A, punto 1: il ricordo si colora sul prompt CON i metadati (quello che l'inoltro riusa)
colorati.clear()
fuori = {}
uscito = json.loads(R.Proxy._memoria(None, corpo([m("user", "[utente] u"), m("assistant", "r"),
                                                  m("user", "[utente] il mare blu di ieri")]), "chat", ["META"], fuori))
assert fuori.get("vettore"), "il vettore del ricordo non e' passato all'inoltro"
assert next(v for v in reversed(diario) if isinstance(v, dict) and "memorinvolontaria" in v)["flusso"] == "chat", \
    "1.14.0: il flusso della consegna serve al riconsolidamento"
assert uscito["messages"][2]["content"] == "META\n\n[utente] il mare blu di ieri" \
    and json.loads(fuori["senza"])["messages"][2]["content"] == "[utente] il mare blu di ieri"
fuori = {}
M._sam_accesa = lambda *a: False
assert json.loads(R.Proxy._memoria(None, corpo([m("user", "[utente] x")]), "chat", ["META"], fuori))["messages"][0][
    "content"] == "META\n\n[utente] x" and "senza" in fuori, "all'agente spenta i metadati non ci sono"
M._sam_accesa = lambda *a: True
# pensatoio e cron: l'ora di arrivo resta in memoria, ore-messaggi.json e' della chat
prima_ore = MD.ORE.read_text()
assert MD._ora_arrivo([m("user", "[IMPORTANT: cron] pensa")], False) == C._ora_blocco(R.time.localtime(orologio[0]))
assert MD.ORE.read_text() == prima_ore, "il pensatoio ha scritto in ore-messaggi.json"

# l'utente 10/11 sera: le copie del blocco che l'agente scrive in fondo alle sue risposte spariscono dalla storia
for x, y in (("bene.\n\n[/pensatoio]\n[20:15|10/11/2026]", "bene."), ("ok [pensatoio]", "ok"),
             ("il [pensatoio] e' una stanza", "il [pensatoio] e' una stanza"), ("niente", "niente")):
    assert C._senza_imitati(x) == y, (x, C._senza_imitati(x))
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [m("user", "[utente] a"), m("assistant", "b\n\n[/pensatoio]\n[20:15|10/11/2026]"),
                                               m("user", "[utente] c")]}).encode(), True, "chat")
assert f.inoltrato["messages"][1]["content"] == "b", f.inoltrato["messages"][1]

# K6: ogni ricordo torna nel punto giusto, anche con messaggi uguali; le voci di prima (impronta CON l'ora) pure
M.CONSEGNE.unlink(missing_ok=True)
conv = [sistema("s"), m("user", "[utente] ok"), m("assistant", "a"), m("user", "[utente] ok"), m("assistant", "b"),
        m("user", "[utente] ok")]
voce = {"dopo": C._impronta("[utente] ok"), "indice": 3, "codici": ["c3"], "risposta": "3°\nc3\nricordo"}
x = json.loads(json.dumps(conv))
M._rimetti(x, [voce])
assert x[4]["role"] == "assistant" and x[4]["tool_calls"] and x[5]["role"] == "tool" and x[6]["content"] == "b", x
MD.ORE.write_text(json.dumps({C._conversazione(conv): {"visti": [], "ore": {C._impronta("[utente] ok"): "[3/11/2026|9:05]"}}}))
vecchia = {"dopo": C._impronta("[3/11/2026|9:05] [utente] ok"), "codici": ["cv"], "risposta": "1°\ncv\nvecchio"}
x = json.loads(json.dumps(conv))
M._rimetti(x, [vecchia])
assert sum(1 for y in x if y.get("role") == "tool") == 1, "la voce salvata con l'ora non si ritrova"
chiave_vecchia = C._impronta("[3/11/2026|9:05] [utente] ok")
M.CONSEGNE.write_text(json.dumps({chiave_vecchia: {"ts": 1.0, "voci": [vecchia]}}))
assert M._voci(conv) == [vecchia], "la conversazione salvata con l'ora nella chiave non si ritrova"
tutte = {f"k{i}": {"ts": float(i), "voci": []} for i in range(S.CONSEGNE_MAX + 5)}
tutte["chat"] = {"ts": 0.0, "voci": []}
M._consegne_salva(tutte, tieni="chat")
assert "chat" in M._consegne_carica(), "la conversazione della chat in corso buttata fuori dal tetto"

# prefill anticipato (solo chat): dopo il riepilogo e il restore della chat, tre /completion fino alla fine della
# risposta (cresta, protetta), fino a prima dell'ora, fino alla fine; il template vede un user "." dopo
passi.clear(); chiesti.clear()
risposta_sam[0] = "un saluto"
S._cw[0] = "chat"
senza = {"messages": [sistema("s"), m("user", "[utente] ciao")], "tools": [M.TOOL]}
ora = "[09:07|03/11/2026]"
righe = ["[pensatoio]", ora]


def chiedi2(path, payload, rompi=None):
    if path == "/apply-template" and payload["messages"][-1] == {"role": "user", "content": "."} \
            and len(payload["messages"]) > 2:
        passi.append("anticipo")
        chiesti.append((path, payload))
        testo = "".join(f"<|im_start|>{x['role']}\n{x['content']}<|im_end|>\n" for x in payload["messages"])
        return {"prompt": testo + "<|im_start|>assistant\n"}
    return chiedi(path, payload, rompi)


C._chiedi = chiedi2
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", "", json.dumps(senza).encode())
i = passi.index(("restore", "chat.kv"))
assert passi[i + 1:] == ["anticipo", "/completion"], passi
tpl = [x for pa, x in chiesti if pa == "/apply-template" and len(x["messages"]) > 2][-1]
assert tpl["messages"] == senza["messages"] + [{"role": "assistant", "content": "ciao l'utente!"},
                                               {"role": "user", "content": "."}] and tpl["tools"] == [M.TOOL], tpl
a = [p for pa, p in chiesti if pa == "/completion"][-1]
assert a["prompt"].endswith("<|im_start|>assistant\nciao l'utente!<|im_end|>\n") and a["checkpoint_tag"] == "cresta" \
    and a["n_predict"] == 1, a
# niente prefill anticipato con la chat arrivata durante il riepilogo o con la chat non rimessa nello slot
# (3.5.3: con una chat gia' in volo il riepilogo aspetta)
for volo, slot_ok in ((1, True), (0, False)):
    passi.clear()
    S._chat_in_volo[0] = 0
    CA._slot = lambda az, nome: passi.append((az, nome)) or (nome == "chat.kv" and S._chat_in_volo.__setitem__(0, volo)) \
        or slot_ok or nome != "chat.kv"
    RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", "", json.dumps(senza).encode())
    assert "anticipo" not in passi, (volo, slot_ok, passi)
S._chat_in_volo[0] = 0
CA._slot = lambda az, nome: passi.append((az, nome)) or True

# K2: la CW del riepilogo nuova parte da una cache BASE (solo la parte fissa), rifatta solo se la parte fissa cambia;
# ogni riga del riepilogo si prefilla col checkpoint protetto "riepilogo" (K3)
for f_ in CA.KV_RAM.glob("riepilogo*"):
    f_.unlink()
C._chiedi = chiedi
passi.clear(); chiesti.clear()
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
comp = [p for pa, p in chiesti if pa == "/completion" and p["n_predict"] == 1]
assert comp[0] == {"prompt": "<|im_start|>system\nTOOLS\n" + FISSO, "n_predict": 1, "cache_prompt": True,
                   "checkpoint_tag": "sistema"}, comp[0]
assert comp[1]["checkpoint_tag"] == "riepilogo" and comp[1]["prompt"].startswith(comp[0]["prompt"] + INTEST), comp[1]
assert ("save", "riepilogo-base.kv") in passi and ("save", "riepilogo.kv") in passi
(CA.KV_RAM / "riepilogo-base.kv").write_bytes(b"x")
(CA.KV_RAM / "riepilogo.kv").unlink(missing_ok=True)
passi.clear(); chiesti.clear()
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert ("restore", "riepilogo-base.kv") in passi and ("save", "riepilogo-base.kv") not in passi, passi
(CA.KV_RAM / "riepilogo.kv").unlink(missing_ok=True)
C._chiedi = lambda p, x: ({"prompt": r["prompt"].replace("TOOLS", "ALTRI")} if "prompt" in (r := chiedi(p, x)) else r)
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
C._chiedi = chiedi
assert passi.count(("save", "riepilogo-base.kv")) == 1, "parte fissa cambiata (tools): la base si rifa'"

# 10/11: il riepilogo non tocca lo slot finche' una richiesta estranea (cron, servizi di Hermes) lo usa
passi.clear()
S._altro_in_volo[0] = 1
assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", scadenza=orologio[0] - 1) == (False, "fallito")
assert passi == [], "riepilogo con una richiesta estranea nello slot"
dormi_vero = R.time.sleep   # 12/11: le due sostituzioni qui sotto si rimettono subito: time.sleep e' di tutto il processo
# e la sentinella (thread avviato in testa) lo chiama a ogni giro; lasciata, azzerava _chat_in_volo durante il punto 3b
# dello switch rimandato (test instabile sulla CI del 12/11)
R.time.sleep = lambda x: S._altro_in_volo.__setitem__(0, 0)   # la richiesta estranea finisce mentre aspetta
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
R.time.sleep = dormi_vero
assert ("restore", "chat.kv") in passi and S._altro_in_volo[0] == 0
S._cw[0] = "pensatoio"
interrotti = []
CA._interrompi_pensatoio = lambda: interrotti.append(1)
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert interrotti, "il riepilogo deve interrompere il pensatoio come la chat"
S._cw[0] = "chat"

import types  # noqa: E402

# revisione 3.5.3 (10/11), punto 2: il riepilogo aspetta anche la chat in volo e il salvataggio della sua cache
passi.clear()
S._chat_in_volo[0] = 1
S._salva_ultimo[0] = types.SimpleNamespace(join=lambda: passi.append("join"))
R.time.sleep = lambda x: S._chat_in_volo.__setitem__(0, 0)
RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
R.time.sleep = dormi_vero
assert S._chat_in_volo[0] == 0 and passi[0] == "join" and ("restore", "chat.kv") in passi, passi
S._salva_ultimo[0] = None

# punto 1: in chat il blocco sta in testa all'ultimo user, il background review di Hermes non e' un turno dell'utente
TESTA = "[/pensatoio]\n[20:15|10/11/2026]\n\n"
review = [m("user", "[utente] ciao"), m("assistant", "ciao!"), m("user", "Review the conversation above")]
review_senza = json.dumps({"messages": review}).encode()
review_con = json.dumps({"messages": review[:2] + [m("user", TESTA + review[2]["content"])]}).encode()
utente_con = json.loads(corpo_utente)
utente_con["messages"][-1]["content"] = TESTA + utente_con["messages"][-1]["content"]
utente_con = json.dumps(utente_con).encode()
RP.RIEPILOGO_PROMUOVI.unlink(missing_ok=True); RP._switch.update(motivo=None, chiesto=0.0)
S._tok_cw["chat"] = 105_000
chiesti.clear()
RP._fine_chat(review_con, fine, None, review_senza)
assert not switch_fatto() and not chiesti, "background review col blocco in testa preso per un turno dell'utente"
S._tok_cw["chat"] = 50_000
RP._fine_chat(utente_con, fine, None, corpo_utente)
assert any(p == "/completion" for p, _ in chiesti), "turno dell'utente col blocco in testa: niente riepilogo"

# punto 3a: [cwswitch] vale anche fuori dalla write_file (l'avviso dice "in coda al riepilogo")
S._tok_cw["chat"] = 95_000
for gen, atteso in ((scrive("ci vediamo") + "\n[cwswitch]", (True, "ok")), ("niente file [cwswitch]", (True, "scartato"))):
    C._chiedi = lambda p, x, g=gen: {"content": g} if p == "/completion" and x["n_predict"] == 220 else chiedi_base(p, x)
    assert RP._riassumi(corpo_utente, "ciao l'utente!") == atteso, gen
assert RP._riepilogo_carica()["nuovi"][-1] == "ci vediamo", RP._riepilogo_carica()
C._chiedi = chiedi

# punto 3b: lo switch rimandato (chat in volo) parte alla fine della richiesta dopo, anche se e' il review
S._tok_cw["chat"] = 105_000
S._chat_in_volo[0] = 1
RP._riassumi = lambda *a: (False, "ok")
RP._fine_chat(corpo_utente, fine, None)
assert not switch_fatto()
RP._riassumi = riassumi_vero
S._chat_in_volo[0] = 0
RP._fine_chat(review_con, {**fine, "tool_calls": True}, None, review_senza)
assert not switch_fatto(), "switch rimandato partito a meta' di un giro di tool"
RP._fine_chat(review_con, fine, None, review_senza)
assert switch_fatto(), "switch rimandato fermo dopo il background review"

# punto 9: rotazione fallita (nessuna promozione): dopo 15 min si richiede anche lo switch chiesto con [cwswitch]
S._tok_cw["chat"] = 50_000
orologio[0] += RP.SWITCH_RITENTA_S + 1
RP._fine_chat(review_con, fine, None, review_senza)
assert switch_fatto(), "rotazione fallita: lo switch non si richiede piu'"
RP.RIEPILOGO_PROMUOVI.write_text(""); RP._promuovi()
assert RP._switch["motivo"] is None

# punto 5: le copie imitate si tolgono anche se l'ora di arrivo non si legge
ora_vera, MD._ora_arrivo = MD._ora_arrivo, lambda *a: 1 / 0
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [m("user", "[utente] a"), m("assistant", "b\n\n[/pensatoio]\n[20:15|10/11/2026]"),
                                               m("user", "[utente] c")]}).encode(), True, "chat")
assert f.inoltrato["messages"][1]["content"] == "b", f.inoltrato["messages"][1]
MD._ora_arrivo = ora_vera

# punto 6: nella coda di firma la risposta dell'agente senza le copie del blocco
FI.CODA_FIRMA = str(R.Path(tempfile.mkdtemp()) / "coda.jsonl")
FI._accoda_firma("chat", "[utente] a", 1.0, {**fine, "testo": "bene.\n\n[/pensatoio]\n[20:15|10/11/2026]"})
assert json.loads(R.Path(FI.CODA_FIRMA).read_text().splitlines()[-1])["testo"] == "bene.", R.Path(FI.CODA_FIRMA).read_text()
assert json.loads(R.Path(FI.CODA_FIRMA).read_text().splitlines()[-1])["flusso"] == "chat"

# punto 7: in ore-messaggi.json (dato della fase 2) solo i messaggi dell'utente, mai il review o il memory flush
prima_ore = MD.ORE.read_text()
MD._ora_arrivo(review)
assert MD.ORE.read_text() == prima_ore, "il background review e' finito in ore-messaggi.json"

# R6 (l'utente 24/10, PIANO-REVISIONI-FUORI-CACHE.md): la parte fissa del system (skill comprese) cambia nella chat
# solo quando nasce una CW del riepilogo nuova; il riepilogo in formazione prende l'elenco nuovo solo sotto 20 righe
RP.FISSA.unlink(missing_ok=True)
assert RP._fissa_carica() == {"chat": None, "riepilogo": None, "elenco": None}, "file assente: tutto None"
RP.FISSA.write_text("{rotto", encoding="utf-8")
assert RP._fissa_carica() == {"chat": None, "riepilogo": None, "elenco": None}
ELENCO_V = RP.ELENCO_DA + "\n<available_skills>\n    - vecchia\n</available_skills>\n\n" + RP.ELENCO_A
ELENCO_N = RP.ELENCO_DA + "\n<available_skills>\n    - nuova\n</available_skills>\n\n" + RP.ELENCO_A
FV, FN = (f"Sono l'agente.\n\n{e}\n\n# regole\n" for e in (ELENCO_V, ELENCO_N))
CODA_H = SEP + "Conversation started: martedi"
assert RP._elenco(FV + CODA_H) == ELENCO_V and RP._elenco("niente skill") is None
assert RP._fissa(FV + CODA_H) == FV and RP._fissa("breve") is None

# a. promozione: la chat nuova nasce da riepilogo.kv, quindi ha la sua parte fissa; senza riepilogo.kv quella di Hermes
for kv, restore, attesa in ((True, True, FN), (False, True, None), (True, False, None)):
    RP._fissa_salva({"chat": FV, "riepilogo": FN, "elenco": ELENCO_N})
    RP._elenco_ok[0] = True
    RP._riepilogo_salva({"blocco": [], "nuovi": ["a"]})
    RP.RIEPILOGO_PROMUOVI.write_text("")
    if kv:
        (CA.KV_RAM / "riepilogo.kv").write_bytes(b"x")
    CA._slot = lambda az, nome, ok=restore: passi.append((az, nome)) or ok
    S._cw[0] = "chat"
    RP._promuovi()
    assert RP._fissa_carica() == {"chat": attesa, "riepilogo": None, "elenco": None}, (kv, restore, RP._fissa_carica())
    assert RP._elenco_ok[0] is None, "il CONTROLLO va rifatto nella sessione nuova"
CA._slot = lambda az, nome: passi.append((az, nome)) or True

# b. chat: la parte fissa di Hermes (skill nuove) sostituita da quella della cache, poi il blocco al suo posto
RP._riepilogo_salva({"blocco": ["r1"], "nuovi": []})
RP._fissa_salva({"chat": FV, "riepilogo": None, "elenco": None})
S._cw[0] = "chat"
n = len(diario)
for volta in (1, 2):
    f = Finto()
    R.Proxy._post_chat(f, json.dumps({"messages": [sis := {"role": "system", "content": FN + CODA_H},
                                                   m("user", "[utente] ciao")], "tools": [M.TOOL]}).encode(), True, "chat")
    assert f.inoltrato["messages"][0]["content"] == FV + INTEST + "\nr1\n\n" + CODA_H, f.inoltrato["messages"][0]
    assert f._hermes == {"system": FN + CODA_H, "tools": [M.TOOL["function"]["name"]]}, f._hermes
assert sum("parte fissa" in str(v.get("riepilogo", "")) for v in diario[n:] if isinstance(v, dict)) == 1, \
    "la sostituzione va nel diario una volta per sessione"
for fissa, h in ((FV, "breve"), (None, FN + CODA_H)):
    RP._fissa_salva({"chat": fissa, "riepilogo": None, "elenco": None})
    RP._riepilogo_salva({"blocco": [], "nuovi": []})
    f = Finto()
    R.Proxy._post_chat(f, json.dumps({"messages": [{"role": "system", "content": h},
                                                   m("user", "[utente] ciao")]}).encode(), True, "chat")
    assert f.inoltrato["messages"][0]["content"] == h, (fissa, f.inoltrato["messages"][0])

# c. _riassumi: il prompt della chat dal corpo inoltrato, il system del riepilogo dal system ORIGINALE di Hermes;
# fissa_riepilogo scritta solo dopo la save riuscita; parte fissa cambiata = niente restore di riepilogo.kv (M3)
RP._riepilogo_salva({"blocco": ["r1"], "nuovi": ["n1"]})
RP._fissa_salva({"chat": FV, "riepilogo": FV, "elenco": None})
(CA.KV_RAM / "riepilogo.kv").write_bytes(b"x")
S._tok_cw["chat"] = 50_000
risposta_sam[0] = "un saluto"
inoltrato_v = {"messages": [{"role": "system", "content": FV + INTEST + "\nr1\n\n" + CODA_H}, m("user", "[utente] ciao")],
               "tools": [M.TOOL]}
hermes = {"system": FN + CODA_H, "tools": ["memorinvolontaria"]}
passi.clear(); chiesti.clear()
S._cw[0] = "chat"
assert RP._riassumi(json.dumps(inoltrato_v).encode(), "ciao l'utente!", hermes=hermes) == (False, "ok")
assert chiesti[0][1] == inoltrato_v, "il prompt del riassunto deve partire dal corpo inoltrato esatto"
assert chiesti[2][1]["messages"][0]["content"] == FN + INTEST + "\nn1\nun saluto\n\n" + CODA_H, chiesti[2][1]
assert ("restore", "riepilogo.kv") not in passi and ("save", "riepilogo-base.kv") in passi, passi
assert RP._fissa_carica()["riepilogo"] == FN
CA._slot = lambda az, nome: passi.append((az, nome)) or nome != "riepilogo.kv"
RP._riassumi(json.dumps(inoltrato_v).encode(), "ciao l'utente!", hermes={**hermes, "system": FV + CODA_H})
assert RP._fissa_carica()["riepilogo"] == FN, "save fallita: fissa_riepilogo cambiata lo stesso"
CA._slot = lambda az, nome: passi.append((az, nome)) or True
passi.clear()
RP._riassumi(json.dumps(inoltrato_v).encode(), "ciao l'utente!", hermes=hermes)
assert ("restore", "riepilogo.kv") in passi, "parte fissa uguale: riepilogo.kv va riusata"

# d. elenco nuovo a meta' sessione: CONTROLLO alla prima chiamata, poi adottato solo sotto 20 righe
uscite, chiamate = [], []


def skills_finto(tools):
    chiamate.append(tools)
    u = uscite.pop(0)
    if isinstance(u, Exception):
        raise u
    return u


RP._skills_da_hermes = skills_finto
hermes = {"system": FV + CODA_H, "tools": ["skill_view"]}
RP._fissa_salva({"chat": None, "riepilogo": None, "elenco": None})
RP._riepilogo_salva({"blocco": [], "nuovi": ["x"] * 19})
RP._elenco_ok[0] = None
uscite[:] = [OSError("docker giu'"), ELENCO_V, ELENCO_V, ELENCO_N]
assert RP._elenco_hermes(hermes) is None and RP._elenco_ok[0] is None, "docker giu' non deve spegnere il CONTROLLO"
assert RP._elenco_hermes(hermes) is None and RP._elenco_ok[0] is True, "CONTROLLO riuscito"
assert RP._elenco_hermes(hermes) is None, "elenco uguale: niente da cambiare"
assert RP._elenco_hermes(hermes) == ELENCO_N and chiamate[-1] == ["skill_view"]
passi.clear(); chiesti.clear()
RP._riassumi(json.dumps(inoltrato_v).encode(), "ciao l'utente!", hermes=hermes, elenco=ELENCO_N)
assert RP._fissa_carica()["elenco"] == ELENCO_N and RP._fissa_carica()["riepilogo"] == FN
assert chiesti[2][1]["messages"][0]["content"].startswith(FN + INTEST), chiesti[2][1]
RP._riepilogo_salva({"blocco": [], "nuovi": ["x"] * 20})
n = len(chiamate)
assert RP._elenco_hermes(hermes) is None and len(chiamate) == n, "da 20 righe in su niente docker exec"
chiesti.clear()
RP._riassumi(json.dumps(inoltrato_v).encode(), "ciao l'utente!", hermes=hermes)
assert chiesti[2][1]["messages"][0]["content"].startswith(FN + INTEST), "riga 21: l'elenco adottato deve restare"
RP._fissa_salva({"chat": None, "riepilogo": None, "elenco": None})
RP._riepilogo_salva({"blocco": [], "nuovi": []})
RP._elenco_ok[0] = None
uscite[:] = [ELENCO_N]
n = len(diario)
assert RP._elenco_hermes(hermes) is None and RP._elenco_ok[0] is False, "CONTROLLO fallito: la funzione si spegne"
assert any("elenco" in str(v.get("riepilogo", "")) for v in diario[n:] if isinstance(v, dict))
n = len(chiamate)
assert RP._elenco_hermes(hermes) is None and len(chiamate) == n, "spenta: niente piu' docker exec"
RP._elenco_ok[0] = None
assert RP._elenco_hermes({"system": "senza marcatori" + CODA_H, "tools": []}) is None and len(chiamate) == n
assert RP._elenco_hermes(None) is None and len(chiamate) == n

# _fine_chat: l'elenco di Hermes e il system originale arrivano a _riassumi
presi = []
riassumi_vero, elenco_vero = RP._riassumi, RP._elenco_hermes
RP._riassumi = lambda *a, **k: presi.append(k) or (False, "ok")
RP._elenco_hermes = lambda h: ELENCO_N
S._tok_cw["chat"] = 50_000
RP._fine_chat(corpo_utente, fine, None, None, hermes)
assert presi == [{"hermes": hermes, "elenco": ELENCO_N}], presi
RP._elenco_hermes = lambda h: 1 / 0
presi.clear()
RP._fine_chat(corpo_utente, fine, None, None, hermes)
assert presi == [{"hermes": hermes, "elenco": None}], "elenco rotto: il riepilogo deve partire lo stesso"
RP._riassumi, RP._elenco_hermes = riassumi_vero, elenco_vero

# prima richiesta dopo la dormita: promozione e parte fissa nella stessa richiesta
RP._fissa_salva({"chat": FV, "riepilogo": FN, "elenco": None})
RP._riepilogo_salva({"blocco": ["vecchia"], "nuovi": ["p1"]})
RP.RIEPILOGO_PROMUOVI.write_text("")
(CA.KV_RAM / "riepilogo.kv").write_bytes(b"x")
S._cw[0] = "chat"
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [{"role": "system", "content": FV + CODA_H},
                                               m("user", "[utente] ciao")]}).encode(), True, "chat")
assert f.inoltrato["messages"][0]["content"] == FN + INTEST + "\np1\n\n" + CODA_H, f.inoltrato["messages"][0]
assert f._hermes["system"] == FV + CODA_H

# PIANO-STEERING-RIFLESSO 7d (11/11): _inoltra fa il prefill del corpo finale SENZA vettore, poi accende il vettore
# del ricordo e chiede a luxifer di spegnerlo a </think>; a fine stream calma()
import http.server as HS  # noqa: E402
import io  # noqa: E402
arrivati, chiuso = [], []


class Monte(HS.BaseHTTPRequestHandler):
    def do_POST(self):
        arrivati.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        chiuso.append(S._vettore_lock.locked())
        b = b'data: {"choices":[{"delta":{"content":"ciao"},"finish_reason":"stop"}]}\n\n'
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


monte = HS.HTTPServer(("127.0.0.1", 0), Monte)
threading.Thread(target=monte.serve_forever, daemon=True).start()
S.UPSTREAM = monte.server_address
passi = []
R.ponte.post = lambda path, d, timeout=600: passi.append((path, d, S._vettore_vivo[0])) or \
    (200, {"prompt": "PROMPT"} if path == "/apply-template" else {})
VT._cvec = lambda d: passi.append(("cvec", d))
VT.calma = lambda: (S._vettore_vivo.__setitem__(0, False), passi.append("calma"))
S._vettori["chat"].clear()
CA._salva_kv = lambda: None


def proxy():
    p = R.Proxy.__new__(R.Proxy)
    p.command, p.path, p.headers, p.wfile = "POST", "/v1/chat/completions", {}, io.BytesIO()
    p.send_response = p.send_header = lambda *a: None
    p.end_headers = p.send_error = lambda *a: None
    return p


V = R.steering.strati("paura", 0.04)
S._vettore_vivo[0] = False
corpo_v = {"messages": [m("user", "[utente] il mare")], "tools": [{"t": 1}], "stream": True}
proxy()._inoltra(json.dumps(corpo_v).encode(), "chat", ("paura", 0.04, V))
assert [x[0] if isinstance(x, tuple) else x for x in passi] == ["/apply-template", "/completion", "cvec", "calma"], passi
assert passi[0][1] == corpo_v and not passi[0][2], passi[0]
assert passi[1][1] == {"prompt": "PROMPT", "n_predict": 1, "cache_prompt": True} and not passi[1][2], "prefill col vettore"
assert passi[2][1] == {"layers": V, "relative": True}
assert arrivati[-1] == {**corpo_v, "reasoning_control": True, "cvec_solo_ragionamento": True}, arrivati[-1]
assert chiuso[-1] and not S._vettore_lock.locked(), "il lucchetto va tenuto per tutto lo stream e lasciato dopo"
passi.clear()
proxy()._inoltra(json.dumps(corpo_v).encode(), "chat")
assert not passi and arrivati[-1] == corpo_v, "senza vettore il corpo passa com'era"
assert not chiuso[-1], "senza vettore il lucchetto non si tiene durante lo stream"
S._cw[0] = "chat"
proxy()._inoltra(json.dumps(corpo_v).encode(), "pensatoio", ("paura", 0.04, V))
assert "cvec" not in [x[0] for x in passi if isinstance(x, tuple)], "pensatoio senza slot: niente vettore"
monte.shutdown()
# revisione 11/11: il watchdog rimandato di un ricordo vecchio non spegne il vettore di quello dopo
passi.clear()
S._vettore_vivo[0], S._vettore_di[0] = True, object()
VT._scaduto(object())
assert "calma" not in passi, "il watchdog vecchio ha spento il vettore nuovo"

print("test_riflesso: TUTTO VERDE")
