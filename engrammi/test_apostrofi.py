#!/usr/bin/env python3
"""test degli apostrofi (Lux 1.12.0): taglio + ricomposizione restituiscono il testo, gli apici delle citazioni spariscono"""
import lux_engrammi as X

T = X.T


def giro(s):
    tab = {}
    pezzi = [(k, X.param_testo(X.param_id(t, tab), list(tab)) if k == "arco" else t) for k, t in T.taglia(s)]
    return X.unisci(pezzi)


UGUALI = ["L'amico dell'utente è arrivato dell'anno scorso.", "C'è un'altra cosa che non so.", "Dammi un po' di tempo.",
          "E' vero, perche' non c'e' piu' niente.", "L’amico c’è, un po’ stanco.", "Gliel'ho detto, me l'ha promesso.",
          "Sant'Antonio, all'una, nell'ottobre dell'86.", "Aspetta mezz'ora, poi nient'altro.",
          "Quest'anno è stato d'accordo con tutt'altro.", "Be', non so. Va' via. Fa' attenzione.",
          "That's the thread I'll carry, and it's hard to answer: I've crossed out the line.",
          "The books aren't here, we're late."]
for s in UGUALI:
    assert giro(s) == s, (s, giro(s))
assert giro("Mi ha detto 'ciao' e se n'è andata.") == "Mi ha detto ciao e se n'è andata."   # apici: via
assert giro("She said 'hello' and left.") == "She said hello and left."
assert giro("I still 'do' it.") == "I still do it."                                  # apice che spaCy non chiama PUNCT
assert giro("Concetti come 'dignità umana' e 'essere umano'.") == "Concetti come dignità umana e essere umano."
assert giro('Disse: "metto il vettore \'Speranza\' per ora".') == "Disse: metto il vettore 'Speranza' per ora."   # apici dentro "..."
assert giro("(\'everyone\') resta.") == "(everyone) resta."                         # apice dopo "(": non e' apostrofo
nodi = " ".join(t for k, t in T.taglia("perche' non so piu' cosa dire") if k == "nodo")
assert "perche'" in nodi and "piu'" in nodi                                   # apostrofi, non una citazione finta
print("test_apostrofi: ok")
