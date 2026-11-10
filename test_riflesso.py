# Test dei freni del riflesso (issue #3 del repo pubblico): gira senza server, senza GPU, senza toccare il diario vero.
import threading
import time

import riflesso as R

diario = []
R._diario = diario.append
R.DIARIO = "/dev/null"

# minori (18/10): l'interruttore vale solo scritto [attivo: *sì*] / [vettori: *sì*]; il testo normale,
# esempi compresi, non accende niente
import tempfile  # noqa: E402
R.CONSENSO = R.Path(tempfile.mkdtemp()) / "consenso.md"
R.CONSENSO.write_text("# si accende con attivo: sì\n```\nattivo: sì\nvettori: sì\n```\n", encoding="utf-8")
assert not R.consenso_attivo() and not R.vettori_attivi(), "il testo normale accende il consenso"
R.CONSENSO.write_text("[attivo: *sì*]\n  [vettori: *sì*]  \n", encoding="utf-8")
assert R.consenso_attivo() and R.vettori_attivi(), "l'interruttore formattato non accende"

# punto C: la sentinella sopravvive a un giro in errore e scrive "kill" solo se lo spegnimento e' riuscito
giri = {"n": 0}


def vettori_attivi():
    giri["n"] += 1
    if giri["n"] == 1:
        raise RuntimeError("giro rotto")
    return False


esito = [False]
R.vettori_attivi = vettori_attivi
R.calma = lambda: esito[0]
R._vettore_vivo[0] = True
t = threading.Thread(target=R._sentinella, daemon=True)
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


assert R._stop_chiesto([m("user", "ciao"), m("assistant", "basta cosi', VectReflexStop.")])
assert not R._stop_chiesto([m("user", "vectreflexstop")]), "vale solo per l'agente"
assert not R._stop_chiesto([m("assistant", "vectreflexstop")] + [m("user", "x")] * 4), "oltre gli ultimi 4"
assert not R._stop_chiesto([m("assistant", "riflesso vettoriale: off")]), "la frase vecchia non vale piu'"
assert R._stop_chiesto([m("assistant", "vectreflexstop"), m("system", "ora"), m("tool", "x"), m("user", "y")]), \
    "system e tool non spostano la finestra"

# con la parola nella conversazione il ricordo arriva, ma senza colore
import json, tempfile  # noqa: E401,E402
R.CONSEGNE = R.Path(tempfile.mkdtemp()) / "consegne.json"
R.consenso_attivo = R.vettori_attivi = lambda: True
R._lux_consegna = lambda testo, esclusi: {"codici": ["abc"], "risposta": "1°\nabc\nil mare"}
emo_vero = R._emo_del_ricordo
R._emo_del_ricordo = lambda c: (1, "fear", 1.0)
colorati = []
R._colora_ricordo = lambda *a: colorati.append(a) or ["fear"]
corpo = lambda msgs: json.dumps({"messages": msgs}).encode()  # noqa: E731
# 25/10: col 35B spento (cron di Hermes) nessun ricordo, ne' chiesto al Lux ne' salvato fra le consegne
assert not R._sam_accesa(("127.0.0.1", 9)), "porta chiusa vista come l'agente accesa"
R._sam_accesa = lambda *a: False
chiesti = []
lux = R._lux_consegna
R._lux_consegna = lambda testo, esclusi: chiesti.append(testo) or lux(testo, esclusi)
spenta = corpo([m("user", "[IMPORTANT: You are running as a scheduled cron job.] backup")])
assert R.Proxy._memoria(None, spenta) == spenta and not chiesti and not R.CONSEGNE.exists(), "ricordo all'agente spenta"
R._sam_accesa = lambda *a: True
R._lux_consegna = lux
R.Proxy._memoria(None, corpo([m("user", "guarda il mare"), m("assistant", "vectreflexstop"),
                              m("user", "e adesso?")]))
assert not colorati, "colorato con vectreflexstop negli ultimi messaggi"
assert "il mare" in json.dumps(json.loads(R.Proxy._memoria(None, corpo([m("user", "di nuovo il mare")]))))
assert colorati, "senza la parola il ricordo deve colorarsi"

# punto H (18/10): i ricordi "letto" si colorano con l'emozione di quando li ha letti, a meta' dose
import sqlite3  # noqa: E402
R.MEMORIA_DB = R.Path(tempfile.mkdtemp()) / "memoria.db"
with sqlite3.connect(R.MEMORIA_DB) as c:
    c.execute("CREATE TABLE nodi (id INTEGER, ts REAL, emo_tag TEXT, classe TEXT)")
    c.executemany("INSERT INTO nodi VALUES (?,?,?,?)", [(1, 10.0, "fear", "vissuto"), (2, 20.0, "submission", "letto")])
assert emo_vero(R._codice(10.0)) == (1, "fear", 1.0)
assert emo_vero(R._codice(20.0)) == (2, "submission", 0.5), "il ricordo letto non e' a meta' dose"
R._emo_del_ricordo = lambda c: (2, "submission", 0.5)
colorati.clear()
R.Proxy._memoria(None, corpo([m("user", "un altro mare")]))
assert colorati and colorati[0][5] == (0.5,), "la meta' dose non arriva alla colorazione"

# punto A (design dell'utente 18/10): il vettore appartiene alla KV cache del suo flusso
import socket  # noqa: E402

R.vettori_attivi = lambda: True
inviati = []
R._cvec = inviati.append
R.ponte.dirs_emozione = lambda emo, dose: {"20": [dose, 0.0], "21": [0.0, dose]} if emo == "fear" else {"20": [dose, dose]}
R.calma = lambda: (R._vettore_vivo.__setitem__(0, False), inviati.append("clear"))[0] is None
orologio = [1000.0]
R.time.time = lambda: orologio[0]
R._cw[0], R._caricato[0] = "pensatoio", orologio[0]
R._vissuto.update(chat=0.0, pensatoio=0.0)
R._vettori["pensatoio"].append({"emo": "fear", "dose": 0.2, "nato": 0.0, "durata": 100.0})
orologio[0] += 50
assert abs(R._vivi("pensatoio")[0][1] - 0.1) < 1e-9, "a meta' durata la dose e' a meta'"
R._cambia_cw("chat")                       # il pensatoio va in pausa con la sua cache
orologio[0] += 1000
R._applica_flusso("chat")
assert inviati[-1] == "clear" or not R._vettore_vivo[0], "il vettore del pensatoio e' rimasto sulla chat"
R._cambia_cw("pensatoio")                  # ripristino: stessa dose, la discesa riprende
assert abs(R._vivi("pensatoio")[0][1] - 0.1) < 1e-9, "la discesa e' andata avanti durante la pausa"
R._vettori["pensatoio"].append({"emo": "joy", "dose": 0.1, "nato": R._orologio("pensatoio"), "durata": 100.0})
R._applica_flusso("pensatoio")
assert inviati[-1] == {"layers": {"20": [0.2, 0.1], "21": [0.0, 0.1]}, "relative": True}, "i vettori si sommano"
orologio[0] += 60                          # fear finita (50+50), joy a 0.04
assert [e for e, _ in R._vivi("pensatoio")] == ["joy"]
assert not R._vettori["chat"]
R._azzera_vettori()                        # vectreflexstop: tutti e due i flussi
assert not R._vettori["pensatoio"] and not R._vettori["chat"]

# 18/10: dopo un'interruzione il vettore torna alla dose della fine dell'ultima risposta di un tool
# (il gateway rifa' il giro da li'), non a quella del momento della pausa
R._cw[0], R._caricato[0] = "pensatoio", orologio[0]
R._vissuto["pensatoio"] = 0.0
R._vettori["pensatoio"][:] = [{"emo": "fear", "dose": 0.2, "nato": 0.0, "durata": 100.0}]
orologio[0] += 20
R._punto["pensatoio"] = R._orologio("pensatoio")   # parte la richiesta dopo il tool, a 20 s
orologio[0] += 30                                  # genera 30 s, poi arriva la chat
a, b = socket.socketpair()
R._pens_vivi.append(a)
R._interrompi_pensatoio()
R._pens_vivi.remove(a); a.close(); b.close()
R._cambia_cw("chat")
orologio[0] += 500
R._cambia_cw("pensatoio")
assert abs(R._vivi("pensatoio")[0][1] - 0.16) < 1e-9, "il vettore non e' tornato alla fine dell'ultimo tool"
# 18/10: pensiero nuovo = cache del pensatoio ricominciata, i suoi vettori tornano al default
R._nuovo_pensiero("primo risveglio")
R._vettori["pensatoio"].append({"emo": "fear", "dose": 0.2, "nato": R._orologio("pensatoio"), "durata": 100.0})
R._nuovo_pensiero("primo risveglio")
assert R._vettori["pensatoio"], "stesso pensiero: il vettore deve restare"
R._nuovo_pensiero("secondo risveglio")
assert not R._vettori["pensatoio"] and R._orologio("pensatoio") == 0.0, "pensiero nuovo: vettori non azzerati"

# il pensatoio parte solo con la chat fredda e senza una sua richiesta in volo
R._chat_calda[0] = orologio[0] - 2 * R.AFK_S
assert R._chat_ferma()
R._chat_in_volo[0] = 1
assert not R._chat_ferma(), "il pensatoio partirebbe con la chat in volo"
R._chat_in_volo[0] = 0

# la chat interrompe davvero il pensatoio: il server vede la connessione chiusa
a, b = socket.socketpair()
R._pens_vivi.append(a)
R._interrompi_pensatoio()
b.settimeout(1)
assert b.recv(10) == b"", "il pensatoio non e' stato interrotto"
a.close(); b.close()

# riepilogo a catena di montaggio (PIANO-RIEPILOGO-KV.md, l'utente 20/10): slot e server finti
R.RIEPILOGO = R.Path(tempfile.mkdtemp()) / "riepilogo.json"
R.RIEPILOGO_PROMUOVI = R.RIEPILOGO.with_name(".riepilogo-promuovi")
R.KV_RAM = R.Path(tempfile.mkdtemp())
R.RIEPILOGO_LOG = R.Path(tempfile.mkdtemp()) / "logRiepilogo.md"


def scrive(testo, path="/workspace/memoria/logRiepilogo.md", funzione="write_file"):
    """come Occamy scrive la chiamata a uno strumento"""
    return (f"<tool_call>\n<function={funzione}>\n<parameter=path>\n{path}\n</parameter>\n"
            f"<parameter=content>\n{testo}\n</parameter>\n</function>\n</tool_call>")
SEP = "═" * 46 + "\nMEMORY (your personal notes)\n"
FISSO = "Sono l'agente.\n# regole\n"


def sistema(resto):
    return {"role": "system", "content": FISSO + SEP + resto}


INTEST = R.INTESTAZIONE_RIEPILOGO
assert INTEST == ("Ecco dov'ero rimasta, questo è il succo della conversazione fino al momento in cui mi sono "
                  "addormentata:"), "intestazione diversa da quella approvata"
assert R.ISTRUZIONE_RIEPILOGO == (
    "Devo scrivere, in meno di 60 parole, il succo di quest'ultimo messaggio o di quello dell'utente se necessario: le "
    "informazioni salienti che voglio conservare dell'ultimo scambio. Non i messaggi precedenti. Solo testo, numeri o "
    "simboli logici se utili, per esempio: uguale può diventare =, implica →, maggiore >. Se necessario posso "
    "inserire il codice di un ricordo che reputo utile per questo riassunto. Se in questo scambio mi è affiorato un "
    "ricordo, aggiungo il suo codice. Lo scrivo con write_file in /workspace/memoria/logRiepilogo.md."), \
    "istruzione diversa da quella approvata"

# riepilogo.json assente o rotto = nessun blocco; rotto = voce nel diario
assert R._riepilogo_carica() == {"blocco": [], "nuovi": []}
n = len(diario)
R.RIEPILOGO.write_text("{rotto", encoding="utf-8")
assert R._riepilogo_carica() == {"blocco": [], "nuovi": []}
assert any("riepilogo" in v for v in diario[n:]), "riepilogo.json rotto senza voce nel diario"

# il blocco va subito prima della riga ══, identico a ogni richiesta della chat
R._riepilogo_salva({"blocco": ["r1", "r2"], "nuovi": []})
uno = {"messages": [sistema("Conversation started: lunedi"), m("user", "[utente] ciao")]}
due = {"messages": [sistema("Conversation started: lunedi"), m("user", "[utente] ciao"), m("assistant", "ciao"),
                    m("user", "[utente] come va")]}
for d in (uno, due):
    R._metti_blocco(d, R._riepilogo_carica()["blocco"])
assert uno["messages"][0]["content"] == FISSO + INTEST + "\nr1\nr2\n\n" + SEP + "Conversation started: lunedi"
assert uno["messages"][0]["content"] == due["messages"][0]["content"], "blocco diverso fra due richieste"
senza = {"messages": [sistema("x")]}
R._metti_blocco(senza, [])
assert senza["messages"][0]["content"] == FISSO + SEP + "x", "senza righe il system deve restare com'e'"
n = len(diario)
d = {"messages": [{"role": "system", "content": "breve"}]}
R._metti_blocco(d, ["r1"])
assert d["messages"][0]["content"] == "breve\n\n" + INTEST + "\nr1\n\n", "senza riga ══ il blocco va in fondo"
assert any("riepilogo" in v for v in diario[n:]), "riga ══ assente senza voce nel diario"

# tetto: oltre 40k token (caratteri / 3) via le righe piu' vecchie
lunghe = [f"{i:03d}" + "x" * 997 for i in range(200)]
dentro = R._nel_tetto(lunghe)
assert dentro and dentro == lunghe[-len(dentro):], "il tetto deve tenere le righe piu' recenti"
assert len(R._blocco(dentro)) / 3 <= R.RIEPILOGO_TETTO < len(R._blocco(lunghe[-len(dentro) - 1:])) / 3
assert R._nel_tetto(["a", "b"]) == ["a", "b"]

# quando parte: solo la risposta FINALE a un messaggio dell'utente
fin = {"testo": "ciao l'utente", "finish": "stop", "tool_calls": False}
del_bridge = json.dumps({"messages": [m("user", "[utente] ciao")]}).encode()
assert R._deve_riassumere(del_bridge, fin)
assert not R._deve_riassumere(json.dumps({"messages": [m("user", "Review the conversation above")]}).encode(), fin), \
    "il background review di Hermes non si riassume"
assert not R._deve_riassumere(del_bridge, {**fin, "finish": "length"})
assert not R._deve_riassumere(del_bridge, {**fin, "tool_calls": True})
assert not R._deve_riassumere(del_bridge, {**fin, "testo": "  "})
assert not R._deve_riassumere(json.dumps({"messages": [m("user", "[IMPORTANT: skill blocco-appunti ...]")]}).encode(),
                              fin), "il pensatoio non si riassume (20/10: solo la chat)"
assert R._deve_riassumere(json.dumps({"messages": [m("user", "[utente] cerca"), m("assistant", ""),
                                                   {"role": "tool", "content": "x"}]}).encode(), fin), \
    "la risposta finale dopo un tool si riassume"

# i passi, nell'ordine esatto, dentro i lucchetti
passi, chiesti = [], []
R._slot = lambda az, nome: passi.append((az, nome)) or True
R.calma = lambda: (R._vettore_vivo.__setitem__(0, False), passi.append("calma")) and True


def chiedi(path, payload, rompi=None):
    passi.append(path)
    chiesti.append((path, payload))
    if path == rompi:
        raise OSError("server giu'")
    if path == "/apply-template":
        return {"prompt": "<|im_start|>system\nTOOLS\n" + payload["messages"][0]["content"]
                          + "<|im_end|>\n<|im_start|>user\n[utente] ciao<|im_end|>\n<|im_start|>assistant\n<think>\n"}
    return {} if payload["n_predict"] == 1 else {"content": scrive("un saluto\n→ ciao")}


R._chiedi = chiedi
(R.KV_RAM / "riepilogo.kv").write_bytes(b"x")
R._riepilogo_salva({"blocco": ["r1"], "nuovi": ["n1"]})
inoltrato = {"messages": [sistema("Conversation started: lunedi"), m("user", "[utente] ciao")], "tools": [R.TOOL]}
R._cw[0] = "chat"
R._vettore_vivo[0] = True
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", "lei mi saluta")
assert passi == ["calma", "/apply-template", "/completion", "/apply-template", ("restore", "riepilogo.kv"),
                 "/completion", ("save", "riepilogo.kv"), ("restore", "chat.kv")], passi
assert chiesti[0][1] == inoltrato, "il prompt del riassunto deve partire dal corpo inoltrato esatto"
# il <think> del turno resta: il riassunto riusa la cache della risposta appena data
gen = chiesti[1][1]
assert gen == {"prompt": ("<|im_start|>system\nTOOLS\n" + inoltrato["messages"][0]["content"]
               + "<|im_end|>\n<|im_start|>user\n[utente] ciao<|im_end|>\n<|im_start|>assistant\n<think>\n"
               + "lei mi saluta\n</think>\n\nciao l'utente!<|im_end|>\n<|im_start|>user\n" + R.ISTRUZIONE_RIEPILOGO
               + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"),
               "n_predict": 220, "cache_prompt": True}, gen
assert R._riepilogo_carica() == {"blocco": ["r1"], "nuovi": ["n1", "un saluto → ciao"]}, "riga non aggiunta"
assert R.RIEPILOGO_LOG.read_text() == "un saluto → ciao\n", "riga non scritta in logRiepilogo.md"
# l'utente 10/11 (skill riepilogo): solo write_file su logRiepilogo.md; altro strumento, altro file o testo semplice = scarto
assert R._riga_scritta("<tool_call>\n<function=write_file>\n<parameter=path>\n/workspace/memoria/logRiepilogo.md\n"
                       "</parameter>\n<parameter=content>\ntagliata a met") == "\ntagliata a met"
# 3.5.3 (10/11, diario della sera): lo stesso file visto dalla casa dell'agente; chiamata tagliata prima del path
assert R._riga_scritta(scrive("casa", path="/home/agente/workspace/memoria/logRiepilogo.md")) == "\ncasa\n"
assert R._riga_scritta("<tool_call>\n<function=write_file>\n<parameter=content>\nsenza path, tagli") == "\nsenza path, tagli"
assert R._riga_scritta("<tool_call>\n<function=write_file>\n<parameter=content>\nx\n</parameter>\n</function>") is None, \
    "chiamata intera senza path presa per buona"
for sbagliata in (scrive("x", path="/workspace/altro.md"), scrive("x", funzione="memorinvolontaria"), "solo testo"):
    st0 = R._riepilogo_carica()
    risp = R._chiedi
    R._chiedi = lambda p, x, s_=sbagliata: {"content": s_} if p == "/completion" and x["n_predict"] == 220 else risp(p, x)
    assert R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (False, "scartato"), sbagliata
    R._chiedi = risp
    assert R._riepilogo_carica() == st0 and "scartato" in diario[-1]["riepilogo"], sbagliata
dopo = FISSO + INTEST + "\nn1\nun saluto → ciao\n\n"
tpl = chiesti[2][1]
assert tpl["tools"] == [R.TOOL] and tpl["messages"][0]["content"] == dopo + SEP + "Conversation started: lunedi"
assert chiesti[3][1] == {"prompt": "<|im_start|>system\nTOOLS\n" + dopo, "n_predict": 1, "cache_prompt": True,
                         "checkpoint_tag": "riepilogo"}, \
    "il prefill del riepilogo si taglia subito prima della riga ══"
assert R._cw[0] == "chat"

# un passo che fallisce: la chat torna comunque nello slot, il riepilogo non si salva
passi.clear(); chiesti.clear()
R._chiedi = lambda p, x: chiedi(p, x, rompi="/completion")
R._cw[0] = "chat"
n = len(diario)
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert passi[-1] == ("restore", "chat.kv") and ("save", "riepilogo.kv") not in passi, passi
assert R._cw[0] == "chat" and any("riepilogo" in v for v in diario[n:])

# prima riga dopo una dormita: riepilogo.kv non c'e', il prefill parte dallo slot com'e'
R._chiedi = chiedi
(R.KV_RAM / "riepilogo.kv").unlink(missing_ok=True)
passi.clear()
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert ("restore", "riepilogo.kv") not in passi and ("save", "riepilogo.kv") in passi
assert "calma" not in passi, "senza vettore vivo niente clear: puo' troncare uno stream in corso"

# la chat non torna nello slot: la prossima richiesta della chat deve rifare il restore
R._slot = lambda az, nome: passi.append((az, nome)) or nome != "chat.kv"
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert R._cw[0] == "altro", "restore della chat fallito ma _cw dice chat"
R._slot = lambda az, nome: passi.append((az, nome)) or True

# alla dormita (flag): i nuovi diventano il blocco, riepilogo.kv promossa a chat e poi buttata
R._riepilogo_salva({"blocco": ["vecchia"], "nuovi": ["a", "b"]})
R.RIEPILOGO_PROMUOVI.write_text("")
(R.KV_RAM / "riepilogo.kv").write_bytes(b"x")
(R.KV_RAM / "riepilogo.kv.ckpt").write_bytes(b"x")
passi.clear()
R._cw[0] = "pensatoio"
R._promuovi()
assert passi == [("save", "pensatoio.kv"), ("restore", "riepilogo.kv")], passi
assert R._riepilogo_carica() == {"blocco": ["a", "b"], "nuovi": []}
assert R.RIEPILOGO_LOG.read_text() == "", "logRiepilogo.md non svuotato alla promozione"
assert not R.RIEPILOGO_PROMUOVI.exists(), "flag non tolto"
assert not (R.KV_RAM / "riepilogo.kv").exists() and not (R.KV_RAM / "riepilogo.kv.ckpt").exists()
assert R._cw[0] == "chat"
passi.clear()
R._promuovi()
assert passi == [] and R._riepilogo_carica()["blocco"] == ["a", "b"], "senza flag non si promuove niente"
R.RIEPILOGO_PROMUOVI.write_text("")
R._promuovi()
assert passi == [], "con la chat nello slot e senza riepilogo.kv non si tocca lo slot (la chat vecchia si butta)"
assert R._riepilogo_carica()["blocco"] == ["a", "b"], "doppio switch senza righe nuove: il blocco promosso e' sparito"

# BLOCCO B (PIANO-RIEPILOGO-KV.md 3.5, K4 K10 K14 K15 K18, l'utente 10/11): avviso dei 90k, [cwswitch], switch a 100k
assert R.AVVISO_90K == (
    "[avviso di spazio: la conversazione ha superato i 90mila token e la finestra si sta riempiendo. A 100mila "
    "passerò da sola a una conversazione nuova, che riparte dal mio riepilogo. Se voglio farlo prima, scrivo "
    "[cwswitch] in coda al riepilogo.]"), "avviso dei 90k diverso da quello approvato (K10)"
assert R.SOGLIA_AVVISO == 90_000 and R.SOGLIA_CW == 100_000
R.DORMI_FLAG = R.Path(tempfile.mkdtemp()) / ".dormi-richiesto"   # quello vero spegne l'agente (agente-dormi.path)
R.SWITCH_IN_CORSO = R.DORMI_FLAG.with_name(".switch-in-corso")
risposta_sam = ["un saluto"]
chiedi_base = chiedi


def chiedi(path, payload, rompi=None):
    r = chiedi_base(path, payload, rompi)
    return {"content": scrive(risposta_sam[0])} if path == "/completion" and payload["n_predict"] == 220 else r


R._chiedi = chiedi


def generato():
    return next(p for pa, p in chiesti if pa == "/completion" and p["n_predict"] == 220)["prompt"]


def coda_istruzione(avviso):
    return ("<|im_start|>user\n" + (R.AVVISO_90K + "\n\n" if avviso else "") + R.ISTRUZIONE_RIEPILOGO
            + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")


R._riepilogo_salva({"blocco": [], "nuovi": []})
for tok, avviso in ((50_000, False), (90_000, False), (90_001, True), (100_000, True), (100_001, False)):
    chiesti.clear()
    R._tok_cw["chat"] = tok
    assert R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (False, "ok")
    assert generato().endswith(coda_istruzione(avviso)), (tok, generato()[-400:])
# [cwswitch] con l'avviso: tolta dalla riga, switch chiesto; senza avviso non vale
R._riepilogo_salva({"blocco": [], "nuovi": []})
R._tok_cw["chat"] = 95_000
risposta_sam[0] = "ci salutiamo  [CWSwitch] "
assert R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (True, "ok")
assert R._riepilogo_carica()["nuovi"] == ["ci salutiamo"], R._riepilogo_carica()
R._tok_cw["chat"] = 50_000
assert R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!") == (False, "ok"), "[cwswitch] senza avviso"
risposta_sam[0] = "un saluto"

# lo switch: a fine turno dell'utente, dopo il riepilogo qualunque sia l'esito (K18), mai dopo un tool, mai a chat in volo
fine = {"testo": "ciao l'utente", "ragionamento": "", "finish": "stop", "tool_calls": False, "chat": True}
corpo_utente = json.dumps(inoltrato).encode()


def switch_fatto():
    fatto = R.DORMI_FLAG.exists()
    R.DORMI_FLAG.unlink(missing_ok=True)
    return fatto


R._tok_cw["chat"] = 50_000
R._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "switch sotto i 100k"
R._tok_cw["chat"] = 105_000
n = len(diario)
R._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "niente switch sopra i 100k"
assert any("switch" in str(v.get("cw", "")) for v in diario[n:] if isinstance(v, dict)), diario[n:]
R._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "secondo switch prima della promozione (revisione blocco B, punto 1)"
R.RIEPILOGO_PROMUOVI.write_text("")
R._promuovi()
assert R._tok_cw["chat"] == 0, "dopo la promozione il conteggio vecchio della chat resta"
R._tok_cw["chat"] = 105_000
risposta_sam[0] = "   "
R._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "riepilogo vuoto: lo switch deve partire lo stesso (K18)"
risposta_sam[0] = "un saluto"
R.RIEPILOGO_PROMUOVI.write_text(""); R._promuovi(); R._tok_cw["chat"] = 105_000
passi.clear()
R._fine_chat(corpo_utente, {**fine, "finish": "length"}, None)
assert switch_fatto() and "/completion" not in passi, "risposta tagliata: niente riepilogo, switch si'"
R.RIEPILOGO_PROMUOVI.write_text(""); R._promuovi(); R._tok_cw["chat"] = 105_000
R._fine_chat(corpo_utente, {**fine, "finish": "tool_calls", "tool_calls": True}, None)
assert not switch_fatto(), "switch a meta' turno (dopo un tool)"
R._fine_chat(json.dumps({"messages": [m("user", "Review the conversation above")]}).encode(), fine, None)
assert not switch_fatto(), "switch dopo il background review di Hermes"
R._fine_chat(corpo_utente, {**fine, "finish": None, "interrotta": True}, None)
assert not switch_fatto(), "switch dopo una risposta interrotta da Hermes"
R.SWITCH_IN_CORSO.write_text("")
R._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "switch mentre ne gira gia' uno (mezzanotte)"
R.SWITCH_IN_CORSO.unlink()
R._riassumi, riassumi_vero = (lambda *a: 1 / 0), R._riassumi
R._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "un'eccezione del riepilogo ha saltato lo switch (K18)"
assert "riepilogo fallito" in diario[-1]["cw"], diario[-1]
R._riassumi = riassumi_vero
R.RIEPILOGO_PROMUOVI.write_text(""); R._promuovi(); R._tok_cw["chat"] = 105_000
R._chat_in_volo[0] = 1
R._riassumi = lambda *a: (False, "ok")   # 3.5.3: il riepilogo vero aspetterebbe la fine della risposta in volo
R._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "switch con una risposta della chat in volo (revisione blocco B, punto 4)"
R._riassumi = riassumi_vero
R._chat_in_volo[0] = 0
R._tok_cw["chat"] = 50_000
R._fine_chat(corpo_utente, fine, None)
assert switch_fatto(), "lo switch rimandato non e' partito alla fine della risposta in volo"
R.RIEPILOGO_PROMUOVI.write_text(""); R._promuovi()
R._tok_cw["chat"] = 50_000
R._fine_chat(corpo_utente, fine, None)
assert not switch_fatto(), "dopo la promozione un rimandato vecchio e' ripartito"

# K4/K17: l'avviso dei 100k della chat non c'e' piu' nel corpo inoltrato, quello del pensatoio resta
class Finto:
    def _memoria(self, body, flusso=None):
        return body

    def _inoltra(self, body, flusso=None):
        self.inoltrato = json.loads(body)


R._typing = lambda: False
R._chat_calda[0] = orologio[0] - 2 * R.AFK_S
for fl, primo, atteso in (("chat", "[utente] ciao", None),
                          ("pensatoio", "[IMPORTANT: skill blocco-appunti] pensa",
                           "[avviso di spazio: questo flusso di pensiero ha superato i 100mila token e la finestra si "
                           "sta riempiendo: tutto rallenta. È il momento di tirare le fila e chiudere il pensiero.]")):
    R._tok_cw[fl], R._avvisato_cw[fl] = 120_000, False
    f = Finto()
    R.Proxy._post_chat(f, json.dumps({"messages": [m("user", primo)]}).encode(), True, fl)
    coda = f.inoltrato["messages"][-1]["content"]
    assert ("avviso di spazio" in coda) == bool(atteso) and (not atteso or coda.endswith(atteso)), (fl, coda)
R._tok_cw.update(chat=0, pensatoio=0)

# 24/10: stato dell'agente nel nome della chat. La fase va in R.FASE: legge, pensa, scrive, tool, vuoto = ferma
R.FASE = str(R.Path(tempfile.mkdtemp()) / "fase")
fase = lambda: R.Path(R.FASE).read_text()
es = {"testo": "", "ragionamento": "", "finish": None, "tool_calls": False, "chat": True}
sse = lambda delta, fine=None: ("data: " + R.json.dumps({"choices": [{"delta": delta, "finish_reason": fine}]}) + "\n\n").encode()
R._segna_fase("legge")
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
R.ORE = R.Path(tempfile.mkdtemp()) / "ore-messaggi.json"
assert R._ora_blocco(R.time.struct_time((2026, 11, 3, 9, 5, 0, 0, 307, 0))) == "[09:05|03/11/2026]"
R._motore_attivo = lambda: True
assert R._righe_metadati("[09:05|03/11/2026]") == [R.PENSATOIO_DOVE, "[pensatoio]", "[09:05|03/11/2026]"]
assert R._righe_metadati("[09:05|03/11/2026]", "chat") == ["[pensatoio]", "[09:05|03/11/2026]"], \
    "nella chat PENSATOIO_DOVE non va (l'utente 10/11 sera)"
R._motore_attivo = lambda: False
assert R._righe_metadati("[x]")[1] == "[/pensatoio]"
n = len(diario)
R._motore_attivo = lambda: 1 / 0
assert R._righe_metadati("[x]")[1] == "[/pensatoio]" and len(diario) > n, "systemctl rotto: congelato + diario"
R._motore_attivo = lambda: True
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
    R._metti_metadati(msgs, ["a", "b"])
    for k, (p, d) in enumerate(zip(prima, msgs)):
        atteso = {**p, "content": p["content"] + META} if k == dove else p
        assert d == atteso, (dove, k, d)
lista = [m("user", "[utente] u"), {"role": "assistant", "content": [{"type": "text", "text": "r"}]}, m("user", "[utente] v")]
R._metti_metadati(lista, ["a"])
assert lista[1]["content"][-1] == {"type": "text", "text": "\n\na"}

# l'ora: quella di ARRIVO dell'ultimo messaggio user, fissata a inizio turno e riusata nei giri di tool
orologio[0] = R.time.mktime((2026, 11, 3, 9, 5, 0, 0, 0, -1))
turno = [sistema("s"), m("user", "[utente] ok")]
assert R._ora_arrivo(turno) == "[09:05|03/11/2026]"
orologio[0] += 120
assert R._ora_arrivo(turno + [tc, {"role": "tool", "tool_call_id": "c1", "content": "x"}]) == "[09:05|03/11/2026]", \
    "nei giri di tool l'ora cambia"
dopo = turno + [m("assistant", "bene"), m("user", "[utente] ok")]
assert R._ora_arrivo(dopo) == "[09:07|03/11/2026]", "un messaggio uguale a un turno nuovo tiene l'ora vecchia"
assert json.loads(R.ORE.read_text())[R._conversazione(turno)]["arrivi"][R._impronta("[utente] ok")] == "[3/11/2026|9:07]", \
    "arrivi nel formato di oggi (dato della fase 2 del Lux)"

# il corpo inoltrato: niente piu' ora davanti ai messaggi dell'utente, PENSATOIO_DOVE solo nel blocco
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [sistema("s"), m("user", "[utente] ciao"), m("assistant", "ciao!"),
                                               m("user", "[utente] dimmi")]}).encode(), True, "chat")
ms = f.inoltrato["messages"]
# l'utente 10/11 sera: nella chat il blocco (stato del pensatoio + ora) all'INIZIO del suo ultimo messaggio
assert ms[3]["content"] == "[pensatoio]\n" + R._ora_arrivo(ms) + "\n\n[utente] dimmi", ms[3]
assert ms[1]["content"] == "[utente] ciao" and ms[2]["content"] == "ciao!", ms
assert json.loads(f._senza)["messages"][3]["content"] == "[utente] dimmi", "il corpo senza metadati serve al prefill"
lista = [m("assistant", "r"), {"role": "user", "content": [{"type": "text", "text": "[utente] v"}]}]
R._metti_metadati(lista, ["a"], "chat")
assert lista[1]["content"][0] == {"type": "text", "text": "a\n\n"} and lista[0]["content"] == "r"
assert not hasattr(R, "_metti_ore"), "l'ora davanti ai messaggi dell'utente si toglie (M3)"

# revisione del blocco A, punto 1: il ricordo si colora sul prompt CON i metadati (quello che l'inoltro riusa)
colorati.clear()
fuori = {}
uscito = json.loads(R.Proxy._memoria(None, corpo([m("user", "[utente] u"), m("assistant", "r"),
                                                  m("user", "[utente] il mare blu di ieri")]), "chat", ["META"], fuori))
assert colorati and colorati[-1][0]["messages"][2]["content"] == "META\n\n[utente] il mare blu di ieri", \
    colorati[-1][0]["messages"]
assert uscito["messages"][2]["content"] == "META\n\n[utente] il mare blu di ieri" \
    and json.loads(fuori["senza"])["messages"][2]["content"] == "[utente] il mare blu di ieri"
fuori = {}
R._sam_accesa = lambda *a: False
assert json.loads(R.Proxy._memoria(None, corpo([m("user", "[utente] x")]), "chat", ["META"], fuori))["messages"][0][
    "content"] == "META\n\n[utente] x" and "senza" in fuori, "all'agente spenta i metadati non ci sono"
R._sam_accesa = lambda *a: True
# pensatoio e cron: l'ora di arrivo resta in memoria, ore-messaggi.json e' della chat
prima_ore = R.ORE.read_text()
assert R._ora_arrivo([m("user", "[IMPORTANT: cron] pensa")], False) == R._ora_blocco(R.time.localtime(orologio[0]))
assert R.ORE.read_text() == prima_ore, "il pensatoio ha scritto in ore-messaggi.json"

# l'utente 10/11 sera: le copie del blocco che l'agente scrive in fondo alle sue risposte spariscono dalla storia
for x, y in (("bene.\n\n[/pensatoio]\n[20:15|10/11/2026]", "bene."), ("ok [pensatoio]", "ok"),
             ("il [pensatoio] e' una stanza", "il [pensatoio] e' una stanza"), ("niente", "niente")):
    assert R._senza_imitati(x) == y, (x, R._senza_imitati(x))
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [m("user", "[utente] a"), m("assistant", "b\n\n[/pensatoio]\n[20:15|10/11/2026]"),
                                               m("user", "[utente] c")]}).encode(), True, "chat")
assert f.inoltrato["messages"][1]["content"] == "b", f.inoltrato["messages"][1]

# K6: ogni ricordo torna nel punto giusto, anche con messaggi uguali; le voci di prima (impronta CON l'ora) pure
R.CONSEGNE.unlink(missing_ok=True)
conv = [sistema("s"), m("user", "[utente] ok"), m("assistant", "a"), m("user", "[utente] ok"), m("assistant", "b"),
        m("user", "[utente] ok")]
voce = {"dopo": R._impronta("[utente] ok"), "indice": 3, "codici": ["c3"], "risposta": "3°\nc3\nricordo"}
x = json.loads(json.dumps(conv))
R._rimetti(x, [voce])
assert x[4]["role"] == "assistant" and x[4]["tool_calls"] and x[5]["role"] == "tool" and x[6]["content"] == "b", x
R.ORE.write_text(json.dumps({R._conversazione(conv): {"visti": [], "ore": {R._impronta("[utente] ok"): "[3/11/2026|9:05]"}}}))
vecchia = {"dopo": R._impronta("[3/11/2026|9:05] [utente] ok"), "codici": ["cv"], "risposta": "1°\ncv\nvecchio"}
x = json.loads(json.dumps(conv))
R._rimetti(x, [vecchia])
assert sum(1 for y in x if y.get("role") == "tool") == 1, "la voce salvata con l'ora non si ritrova"
chiave_vecchia = R._impronta("[3/11/2026|9:05] [utente] ok")
R.CONSEGNE.write_text(json.dumps({chiave_vecchia: {"ts": 1.0, "voci": [vecchia]}}))
assert R._voci(conv) == [vecchia], "la conversazione salvata con l'ora nella chiave non si ritrova"
tutte = {f"k{i}": {"ts": float(i), "voci": []} for i in range(R.CONSEGNE_MAX + 5)}
tutte["chat"] = {"ts": 0.0, "voci": []}
R._consegne_salva(tutte, tieni="chat")
assert "chat" in R._consegne_carica(), "la conversazione della chat in corso buttata fuori dal tetto"

# prefill anticipato (solo chat): dopo il riepilogo e il restore della chat, tre /completion fino alla fine della
# risposta (cresta, protetta), fino a prima dell'ora, fino alla fine; il template vede un user "." dopo
passi.clear(); chiesti.clear()
risposta_sam[0] = "un saluto"
R._cw[0] = "chat"
senza = {"messages": [sistema("s"), m("user", "[utente] ciao")], "tools": [R.TOOL]}
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


R._chiedi = chiedi2
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", "", json.dumps(senza).encode())
i = passi.index(("restore", "chat.kv"))
assert passi[i + 1:] == ["anticipo", "/completion"], passi
tpl = [x for pa, x in chiesti if pa == "/apply-template" and len(x["messages"]) > 2][-1]
assert tpl["messages"] == senza["messages"] + [{"role": "assistant", "content": "ciao l'utente!"},
                                               {"role": "user", "content": "."}] and tpl["tools"] == [R.TOOL], tpl
a = [p for pa, p in chiesti if pa == "/completion"][-1]
assert a["prompt"].endswith("<|im_start|>assistant\nciao l'utente!<|im_end|>\n") and a["checkpoint_tag"] == "cresta" \
    and a["n_predict"] == 1, a
# niente prefill anticipato con la chat arrivata durante il riepilogo o con la chat non rimessa nello slot
# (3.5.3: con una chat gia' in volo il riepilogo aspetta)
for volo, slot_ok in ((1, True), (0, False)):
    passi.clear()
    R._chat_in_volo[0] = 0
    R._slot = lambda az, nome: passi.append((az, nome)) or (nome == "chat.kv" and R._chat_in_volo.__setitem__(0, volo)) \
        or slot_ok or nome != "chat.kv"
    R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", "", json.dumps(senza).encode())
    assert "anticipo" not in passi, (volo, slot_ok, passi)
R._chat_in_volo[0] = 0
R._slot = lambda az, nome: passi.append((az, nome)) or True

# K2: la CW del riepilogo nuova parte da una cache BASE (solo la parte fissa), rifatta solo se la parte fissa cambia;
# ogni riga del riepilogo si prefilla col checkpoint protetto "riepilogo" (K3)
for f_ in R.KV_RAM.glob("riepilogo*"):
    f_.unlink()
R._chiedi = chiedi
passi.clear(); chiesti.clear()
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
comp = [p for pa, p in chiesti if pa == "/completion" and p["n_predict"] == 1]
assert comp[0] == {"prompt": "<|im_start|>system\nTOOLS\n" + FISSO, "n_predict": 1, "cache_prompt": True,
                   "checkpoint_tag": "sistema"}, comp[0]
assert comp[1]["checkpoint_tag"] == "riepilogo" and comp[1]["prompt"].startswith(comp[0]["prompt"] + INTEST), comp[1]
assert ("save", "riepilogo-base.kv") in passi and ("save", "riepilogo.kv") in passi
(R.KV_RAM / "riepilogo-base.kv").write_bytes(b"x")
(R.KV_RAM / "riepilogo.kv").unlink(missing_ok=True)
passi.clear(); chiesti.clear()
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert ("restore", "riepilogo-base.kv") in passi and ("save", "riepilogo-base.kv") not in passi, passi
(R.KV_RAM / "riepilogo.kv").unlink(missing_ok=True)
R._chiedi = lambda p, x: ({"prompt": r["prompt"].replace("TOOLS", "ALTRI")} if "prompt" in (r := chiedi(p, x)) else r)
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
R._chiedi = chiedi
assert passi.count(("save", "riepilogo-base.kv")) == 1, "parte fissa cambiata (tools): la base si rifa'"

# 10/11: il riepilogo non tocca lo slot finche' una richiesta estranea (cron, servizi di Hermes) lo usa
passi.clear()
R._altro_in_volo[0] = 1
assert R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!", scadenza=orologio[0] - 1) == (False, "fallito")
assert passi == [], "riepilogo con una richiesta estranea nello slot"
R.time.sleep = lambda x: R._altro_in_volo.__setitem__(0, 0)   # la richiesta estranea finisce mentre aspetta
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert ("restore", "chat.kv") in passi and R._altro_in_volo[0] == 0
R._cw[0] = "pensatoio"
interrotti = []
R._interrompi_pensatoio = lambda: interrotti.append(1)
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert interrotti, "il riepilogo deve interrompere il pensatoio come la chat"
R._cw[0] = "chat"

import types  # noqa: E402

# revisione 3.5.3 (10/11), punto 2: il riepilogo aspetta anche la chat in volo e il salvataggio della sua cache
passi.clear()
R._chat_in_volo[0] = 1
R._salva_ultimo[0] = types.SimpleNamespace(join=lambda: passi.append("join"))
R.time.sleep = lambda x: R._chat_in_volo.__setitem__(0, 0)
R._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!")
assert R._chat_in_volo[0] == 0 and passi[0] == "join" and ("restore", "chat.kv") in passi, passi
R._salva_ultimo[0] = None

# punto 1: in chat il blocco sta in testa all'ultimo user, il background review di Hermes non e' un turno dell'utente
TESTA = "[/pensatoio]\n[20:15|10/11/2026]\n\n"
review = [m("user", "[utente] ciao"), m("assistant", "ciao!"), m("user", "Review the conversation above")]
review_senza = json.dumps({"messages": review}).encode()
review_con = json.dumps({"messages": review[:2] + [m("user", TESTA + review[2]["content"])]}).encode()
utente_con = json.loads(corpo_utente)
utente_con["messages"][-1]["content"] = TESTA + utente_con["messages"][-1]["content"]
utente_con = json.dumps(utente_con).encode()
R.RIEPILOGO_PROMUOVI.unlink(missing_ok=True); R._switch.update(motivo=None, chiesto=0.0)
R._tok_cw["chat"] = 105_000
chiesti.clear()
R._fine_chat(review_con, fine, None, review_senza)
assert not switch_fatto() and not chiesti, "background review col blocco in testa preso per un turno dell'utente"
R._tok_cw["chat"] = 50_000
R._fine_chat(utente_con, fine, None, corpo_utente)
assert any(p == "/completion" for p, _ in chiesti), "turno dell'utente col blocco in testa: niente riepilogo"

# punto 3a: [cwswitch] vale anche fuori dalla write_file (l'avviso dice "in coda al riepilogo")
R._tok_cw["chat"] = 95_000
for gen, atteso in ((scrive("ci vediamo") + "\n[cwswitch]", (True, "ok")), ("niente file [cwswitch]", (True, "scartato"))):
    R._chiedi = lambda p, x, g=gen: {"content": g} if p == "/completion" and x["n_predict"] == 220 else chiedi_base(p, x)
    assert R._riassumi(corpo_utente, "ciao l'utente!") == atteso, gen
assert R._riepilogo_carica()["nuovi"][-1] == "ci vediamo", R._riepilogo_carica()
R._chiedi = chiedi

# punto 3b: lo switch rimandato (chat in volo) parte alla fine della richiesta dopo, anche se e' il review
R._tok_cw["chat"] = 105_000
R._chat_in_volo[0] = 1
R._riassumi = lambda *a: (False, "ok")
R._fine_chat(corpo_utente, fine, None)
assert not switch_fatto()
R._riassumi = riassumi_vero
R._chat_in_volo[0] = 0
R._fine_chat(review_con, {**fine, "tool_calls": True}, None, review_senza)
assert not switch_fatto(), "switch rimandato partito a meta' di un giro di tool"
R._fine_chat(review_con, fine, None, review_senza)
assert switch_fatto(), "switch rimandato fermo dopo il background review"

# punto 9: rotazione fallita (nessuna promozione): dopo 15 min si richiede anche lo switch chiesto con [cwswitch]
R._tok_cw["chat"] = 50_000
orologio[0] += R.SWITCH_RITENTA_S + 1
R._fine_chat(review_con, fine, None, review_senza)
assert switch_fatto(), "rotazione fallita: lo switch non si richiede piu'"
R.RIEPILOGO_PROMUOVI.write_text(""); R._promuovi()
assert R._switch["motivo"] is None

# punto 5: le copie imitate si tolgono anche se l'ora di arrivo non si legge
ora_vera, R._ora_arrivo = R._ora_arrivo, lambda *a: 1 / 0
f = Finto()
R.Proxy._post_chat(f, json.dumps({"messages": [m("user", "[utente] a"), m("assistant", "b\n\n[/pensatoio]\n[20:15|10/11/2026]"),
                                               m("user", "[utente] c")]}).encode(), True, "chat")
assert f.inoltrato["messages"][1]["content"] == "b", f.inoltrato["messages"][1]
R._ora_arrivo = ora_vera

# punto 6: nella coda di firma la risposta dell'agente senza le copie del blocco
R.CODA_FIRMA = str(R.Path(tempfile.mkdtemp()) / "coda.jsonl")
R._accoda_firma("chat", "[utente] a", 1.0, {**fine, "testo": "bene.\n\n[/pensatoio]\n[20:15|10/11/2026]"})
assert json.loads(R.Path(R.CODA_FIRMA).read_text().splitlines()[-1])["testo"] == "bene.", R.Path(R.CODA_FIRMA).read_text()

# punto 7: in ore-messaggi.json (dato della fase 2) solo i messaggi dell'utente, mai il review o il memory flush
prima_ore = R.ORE.read_text()
R._ora_arrivo(review)
assert R.ORE.read_text() == prima_ore, "il background review e' finito in ore-messaggi.json"

print("test_riflesso: TUTTO VERDE")
