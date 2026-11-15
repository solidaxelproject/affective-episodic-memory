#!/usr/bin/env python3
"""Divisione di engrammi/lux_engrammi.py in moduli (interfase 3-4 punto 1, PIANO-INTERFASE-34-DIVISIONE-LUX.md).

Il testo delle funzioni si sposta com'e'; cambiano solo i riferimenti a nomi che vivono in un altro modulo, che
diventano attributi (`B.SOGLIA`, `R.Lux`): cosi' una sostituzione da fuori (X.STATO = ...) inoltrata al proprietario
la vedono tutti. Gli import (np, os, T, LUX, codice...) si ripetono in ogni modulo che li usa.
Si ferma se un modulo dipende da uno che viene dopo nell'ordine (ciclo).
Uso: python3 sposta_lux.py CARTELLA_ENGRAMMI   (riscrive lux_engrammi.py e crea i moduli)
"""
import ast
import sys

ORDINE = ["lux_base", "lux_ricombina", "lux_fonti", "lux_richiamo", "lux_costruzione", "lux_notte"]
ALIAS = {"lux_base": "B", "lux_ricombina": "RC", "lux_fonti": "FO", "lux_richiamo": "RI",
         "lux_costruzione": "CO", "lux_notte": "NO"}
DESCR = {
    "lux_base": "costanti, percorsi e funzioni pure comuni",
    "lux_ricombina": "mixin Ricombina della classe Lux: la ricombinazione mnemonica (1.22.0) e i ponti (1.23.0)",
    "lux_fonti": "mixin Fonti della classe Lux: fiducia nei siti (1.24.0)",
    "lux_richiamo": "la classe Lux: apertura, stato, predisposizione, consegna, richiamo, forza, ricomposizione",
    "lux_costruzione": "costruzione, versione dalla precedente, ricordi nuovi e correzioni",
    "lux_notte": "lavori della notte: riaccensione, riconsolidamento, avvicinamento, ponti, sbiadimento",
}
FUNZIONI = {
    "lux_costruzione": ["pesi_archi", "contatori_iniziali", "param_id", "_inserisci", "_primo", "_lega", "_lega_siti",
                        "costruisci", "da_precedente", "aggiungi_ricordo", "correggi", "_aggiungi"],
    "lux_notte": ["_rodaggio", "_voci", "riconsolida", "_applica_passi", "avvicina", "pota_ponti", "riaccendi",
                  "freno_archi", "sbiadisci"],
}
METODI = {
    "lux_ricombina": ("Ricombina", ["_guida", "_dai_ponti", "_aggiorna_ponti", "_nascite", "_attivazione", "ricombina"]),
    "lux_fonti": ("Fonti", ["certo", "conferma", "smentisci"]),
}
FACCIATA = ["prova"]   # restano in lux_engrammi.py, col blocco __main__


def colonna(riga, col_byte):
    return len(riga.encode()[:col_byte].decode())


def legati(nodo):
    """Nomi legati nello scope di una funzione/lambda (parametri, assegnazioni, import, def annidate)."""
    a = nodo.args
    nomi = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    nomi |= {x.arg for x in (a.vararg, a.kwarg) if x}
    corpo = nodo.body if isinstance(nodo.body, list) else [nodo.body]
    pila = list(corpo)
    while pila:
        n = pila.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomi.add(n.name)
            continue
        if isinstance(n, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            nomi.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            nomi |= {(x.asname or x.name).split(".")[0] for x in n.names}
        elif isinstance(n, ast.ExceptHandler) and n.name:
            nomi.add(n.name)
        pila.extend(ast.iter_child_nodes(n))
    return nomi


def comp_legati(nodo):
    nomi = set()
    for g in nodo.generators:
        nomi |= {n.id for n in ast.walk(g.target) if isinstance(n, ast.Name)}
    return nomi


def nomi_liberi(nodo):
    """(Name, ) caricati che non sono legati in una funzione/lambda/comprensione che li racchiude."""
    out = []

    def visita(n, scope):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list + n.args.defaults + [x for x in n.args.kw_defaults if x]:
                visita(d, scope)
            interno = scope | legati(n)
            for c in n.body:
                visita(c, interno)
            return
        if isinstance(n, ast.Lambda):
            for d in n.args.defaults:
                visita(d, scope)
            visita(n.body, scope | legati(n))
            return
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            interno = scope | comp_legati(n)
            for i, g in enumerate(n.generators):
                visita(g.iter, scope if i == 0 else interno)
                for c in g.ifs:
                    visita(c, interno)
            for c in ([n.key, n.value] if isinstance(n, ast.DictComp) else [n.elt]):
                visita(c, interno)
            return
        if isinstance(n, ast.ClassDef):
            for b in n.bases + n.decorator_list:
                visita(b, scope)
            for c in n.body:
                visita(c, scope)
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in scope:
            out.append(n)
        for c in ast.iter_child_nodes(n):
            visita(c, scope)

    visita(nodo, set())
    return out


def main():
    eng = sys.argv[1]
    src = open(f"{eng}/lux_engrammi.py").read()
    righe = src.split("\n")
    albero = ast.parse(src)
    corpo = albero.body

    # pezzi di primo livello con i commenti che li precedono
    pezzi = []
    fine_prec = corpo[0].end_lineno   # docstring del modulo
    for n in corpo[1:]:
        inizio = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
        su = inizio
        while su - 1 > fine_prec and righe[su - 2].strip().startswith("#"):
            su -= 1
        pezzi.append((n, su, n.end_lineno))
        fine_prec = n.end_lineno

    proprietario, importati, testo_import = {}, set(), []
    destinazione = {}
    lux_cls = None
    for n, su, giu in pezzi:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            nomi = [(x.asname or x.name).split(".")[0] for x in n.names]
            importati |= set(nomi)
            testo_import.append((set(nomi), "\n".join(righe[su - 1:giu])))
            destinazione[id(n)] = "lux_base"
            continue
        if isinstance(n, ast.If) and getattr(n.test, "left", None) and getattr(n.test.left, "id", "") == "__name__":
            destinazione[id(n)] = "facciata"
            continue
        if isinstance(n, ast.ClassDef) and n.name == "Lux":
            lux_cls = n
            destinazione[id(n)] = "lux_richiamo"
            proprietario["Lux"] = "lux_richiamo"
            continue
        if isinstance(n, ast.FunctionDef):
            m = next((k for k, v in FUNZIONI.items() if n.name in v), "facciata" if n.name in FACCIATA else "lux_base")
            destinazione[id(n)] = m
            if m != "facciata":
                proprietario[n.name] = m
            continue
        destinazione[id(n)] = "lux_base"
        for t in ast.walk(n):
            if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                proprietario.setdefault(t.id, "lux_base")
    for m, (cls, metodi) in METODI.items():
        proprietario[cls] = m

    usati = set()
    for n in ast.walk(albero):
        if isinstance(n, ast.Name):
            usati.add(n.id)
        elif isinstance(n, ast.arg):
            usati.add(n.arg)
    assert not usati & set(ALIAS.values()), f"alias gia' usati nel file: {usati & set(ALIAS.values())}"

    # metodi della classe Lux che vanno nei mixin
    metodo_mod = {name: m for m, (_, ms) in METODI.items() for name in ms}
    blocchi_metodi = {m: [] for m in METODI}
    tolti_da_lux = []
    fine_prec = lux_cls.body[0].end_lineno if isinstance(lux_cls.body[0], ast.Expr) else lux_cls.lineno
    for f in lux_cls.body:
        inizio = min([f.lineno] + [d.lineno for d in getattr(f, "decorator_list", [])])
        su = inizio
        while su - 1 > fine_prec and righe[su - 2].strip().startswith("#"):
            su -= 1
        if isinstance(f, ast.FunctionDef) and f.name in metodo_mod:
            blocchi_metodi[metodo_mod[f.name]].append((f, su, f.end_lineno))
            tolti_da_lux.append((su, f.end_lineno))
        fine_prec = f.end_lineno
    assert sum(len(v) for v in blocchi_metodi.values()) == len(metodo_mod), "metodo non trovato"

    def riscrivi(nodo, su, giu, mod, salta=()):
        """testo delle righe su..giu con i nomi di altri moduli qualificati; dipendenze trovate"""
        sost, dip = {}, set()
        for nm in nomi_liberi(nodo):
            prop = proprietario.get(nm.id)
            if nm.id in importati or prop is None or prop == mod:
                continue
            if any(a <= nm.lineno <= b for a, b in salta):
                continue
            dip.add(prop)
            sost.setdefault(nm.lineno, []).append((nm.col_offset, nm.id, ALIAS[prop]))
        out = []
        for i in range(su, giu + 1):
            if any(a <= i <= b for a, b in salta):
                continue
            r = righe[i - 1]
            for col, nome, al in sorted(sost.get(i, []), reverse=True):
                c = colonna(r, col)
                assert r[c:c + len(nome)] == nome, (i, r, nome)
                r = r[:c] + f"{al}." + r[c:]
            out.append(r)
        return "\n".join(out), dip

    testi = {m: [] for m in ORDINE + ["facciata"]}
    dipende = {m: set() for m in ORDINE + ["facciata"]}
    for n, su, giu in pezzi:
        m = destinazione[id(n)]
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            testi["lux_base"].append((su, giu, "\n".join(righe[su - 1:giu])))   # in base nell'ordine di prima (sys.path prima di lux)
            continue
        if m == "facciata":
            testi[m].append((su, giu, "\n".join(righe[su - 1:giu])))
            continue
        salta = tolti_da_lux if n is lux_cls else ()
        t, dip = riscrivi(n, su, giu, m, salta)
        if n is lux_cls:
            t = t.replace("class Lux:", "class Lux(RC.Ricombina, FO.Fonti):", 1)
            dip |= {"lux_ricombina", "lux_fonti"}
        testi[m].append((su, giu, t))
        dipende[m] |= dip
    for m, blocchi in blocchi_metodi.items():
        for f, su, giu in blocchi:
            t, dip = riscrivi(f, su, giu, m)
            testi[m].append((su, giu, t))
            dipende[m] |= dip

    errori = []
    for m in ORDINE:
        for d in dipende[m]:
            if ORDINE.index(d) >= ORDINE.index(m):
                errori.append(f"{m} dipende da {d}")
    if errori:
        sys.exit("CICLI:\n" + "\n".join(sorted(errori)))

    def import_usati(testo):
        try:
            nomi = {n.id for n in ast.walk(ast.parse(testo)) if isinstance(n, ast.Name)}
        except SyntaxError:
            nomi = importati
        return [t for ns, t in testo_import if ns & nomi]

    def unisci_pezzi(lista, rientro=""):
        out, prec = [], None
        for su, giu, testo in lista:
            if prec is not None:
                vuote = righe[prec:su - 1]
                out.append("\n" * (len(vuote) + 1) if all(not r.strip() for r in vuote) and prec < su
                           else "\n\n\n" if not rientro else "\n\n")
            out.append(testo)
            prec = giu
        return "".join(out)

    intest = '"""Lux degli engrammi: {d}.\nParte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano\nlux_engrammi, che riesporta tutto."""'
    for m in ORDINE:
        corpo_m = unisci_pezzi(testi[m])
        if m in METODI:
            corpo_m = f"class {METODI[m][0]}:\n" + unisci_pezzi(testi[m], "    ")
        if m == "lux_base":
            imp = []
        else:
            imp = (["import lux_base as B"] if "lux_base" in dipende[m] else []) + import_usati(corpo_m)
            imp += [f"import {d} as {ALIAS[d]}" for d in ORDINE if d in dipende[m] and d != "lux_base"]
        testo = intest.format(d=DESCR[m]) + "\n" + ("\n".join(imp) + "\n\n\n" if imp else "") + corpo_m + "\n"
        open(f"{eng}/{m}.py", "w").write(testo)

    doc = "\n".join(righe[:corpo[0].end_lineno])
    facciata = f'''{doc}
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
    globals().update({{k: v for k, v in vars(_m).items() if not k.startswith("__") and k not in {set(ALIAS.values())!r}}})


class _Facciata(types.ModuleType):
    def __setattr__(self, nome, valore):
        for m in MODULI:
            if nome in vars(m):
                setattr(m, nome, valore)
        super().__setattr__(nome, valore)


if __name__ in sys.modules:   # assente se caricato con spec_from_file_location + exec_module
    sys.modules[__name__].__class__ = _Facciata


''' + unisci_pezzi(testi["facciata"]) + "\n"
    open(f"{eng}/lux_engrammi.py", "w").write(facciata)
    for m in ORDINE:
        print(m, "dipende da", sorted(dipende[m]))


if __name__ == "__main__":
    main()
