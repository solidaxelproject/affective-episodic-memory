#!/usr/bin/env python3
"""test di misura_engrammi (Fase 1 del piano di refactoring Lux + richiamo): niente GPU, niente rete"""
import numpy as np

from misura_engrammi import archi, spezza

# "Aa bb. Cc dd. Ee" tokenizzato con gli spazi in testa, come fa il tokenizer di Qwen
TESTO = "Aa bb. Cc dd. Ee"
OFFS = [(0, 2), (2, 5), (5, 6), (6, 9), (9, 12), (12, 13), (13, 16)]

assert spezza(TESTO, OFFS, "frase") == [(1, 3), (3, 6), (6, 7)]
assert spezza(TESTO, OFFS, "frase60") == [(1, 7)]       # nessuna frase arriva a 60 caratteri
assert spezza(TESTO, OFFS, "tok16") == [(1, 7)]
assert spezza(TESTO, OFFS, "tok32") == [(1, 7)]
assert spezza(TESTO, OFFS, "intero") == [(1, 7)]
assert spezza("A", [(0, 1)], "frase") == []              # solo il pozzo dell'attenzione: niente frammenti
assert spezza(TESTO, OFFS * 3, "tok16") == [(1, 17), (17, 21)]

V = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.6, 0.8]])
assert archi(V, np.array([1, 2, 1, 3]), 0.9, 3) == {(0, 1)}           # ricordi diversi, stesso senso: un arco
assert archi(V[:2], np.array([1, 1]), 0.9, 3) == set()                 # stesso ricordo: nessun arco
assert archi(V, np.array([1, 2, 3, 4]), 0.5, 1) == {(0, 1), (2, 3)}  # k=1: solo il piu' simile di ognuno, 0-3 (0.6) cade
print("test_engrammi: ok")
