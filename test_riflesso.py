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
    "ricordo, aggiungo il suo codice."), "istruzione diversa da quella approvata"

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
    return {} if payload["n_predict"] == 1 else {"content": "un saluto\n→ ciao"}


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
               "n_predict": 160, "cache_prompt": True}, gen
assert R._riepilogo_carica() == {"blocco": ["r1"], "nuovi": ["n1", "un saluto → ciao"]}, "riga non aggiunta"
dopo = FISSO + INTEST + "\nn1\nun saluto → ciao\n\n"
tpl = chiesti[2][1]
assert tpl["tools"] == [R.TOOL] and tpl["messages"][0]["content"] == dopo + SEP + "Conversation started: lunedi"
assert chiesti[3][1] == {"prompt": "<|im_start|>system\nTOOLS\n" + dopo, "n_predict": 1, "cache_prompt": True}, \
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
(R.KV_RAM / "riepilogo.kv").unlink()
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
assert not R.RIEPILOGO_PROMUOVI.exists(), "flag non tolto"
assert not (R.KV_RAM / "riepilogo.kv").exists() and not (R.KV_RAM / "riepilogo.kv.ckpt").exists()
assert R._cw[0] == "chat"
passi.clear()
R._promuovi()
assert passi == [] and R._riepilogo_carica()["blocco"] == ["a", "b"], "senza flag non si promuove niente"
R.RIEPILOGO_PROMUOVI.write_text("")
R._promuovi()
assert passi == [], "con la chat nello slot e senza riepilogo.kv non si tocca lo slot (la chat vecchia si butta)"

print("test_riflesso: TUTTO VERDE")
