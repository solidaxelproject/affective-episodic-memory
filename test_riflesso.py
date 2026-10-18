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

print("test_riflesso: TUTTO VERDE")
