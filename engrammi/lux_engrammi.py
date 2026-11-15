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
# ruff: noqa: F821
# 14/11/2026 (l'utente, interfase 3-4 punto 1, PIANO-INTERFASE-34-DIVISIONE-LUX.md): il codice sta nei moduli lux_*.py;
# questo file li riesporta tutti (privati compresi) e tiene prova() e la riga di comando. Un'assegnazione da fuori
# (X.STATO = ..., X.PRECEDENTE = ...) va anche al modulo che possiede il nome: la vedono tutte le funzioni.
import random   # prova()
import sys
import types

import lux_base
import lux_ricombina
import lux_fonti
import lux_richiamo
import lux_costruzione
import lux_notte

MODULI = (lux_base, lux_ricombina, lux_fonti, lux_richiamo, lux_costruzione, lux_notte)
for _m in MODULI:
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__") and k not in {'RC', 'NO', 'CO', 'B', 'RI', 'FO'}})


class _Facciata(types.ModuleType):
    def __setattr__(self, nome, valore):
        for m in MODULI:
            if nome in vars(m):
                setattr(m, nome, valore)
        super().__setattr__(nome, valore)


if __name__ in sys.modules:   # assente se caricato con spec_from_file_location + exec_module
    sys.modules[__name__].__class__ = _Facciata


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
