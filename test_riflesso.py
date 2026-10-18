# Test dei freni del riflesso (issue #3 del repo pubblico): gira senza server, senza GPU, senza toccare il diario vero.
import threading
import time

import riflesso as R

diario = []
R._diario = diario.append
R.DIARIO = "/dev/null"

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
R._emo_del_ricordo = lambda c: (1, "fear")
colorati = []
R._colora_ricordo = lambda *a: colorati.append(a) or ["fear"]
corpo = lambda msgs: json.dumps({"messages": msgs}).encode()  # noqa: E731
R.Proxy._memoria(None, corpo([m("user", "guarda il mare"), m("assistant", "vectreflexstop"),
                              m("user", "e adesso?")]))
assert not colorati, "colorato con vectreflexstop negli ultimi messaggi"
assert "il mare" in json.dumps(json.loads(R.Proxy._memoria(None, corpo([m("user", "di nuovo il mare")]))))
assert colorati, "senza la parola il ricordo deve colorarsi"

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

print("test_riflesso: TUTTO VERDE")
