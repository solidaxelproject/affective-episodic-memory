#!/usr/bin/env python3
"""Controllo statico dei bersagli dei test (PIANO-DIVISIONE-RIFLESSO.md, task 1, trappola 9): una sostituzione
`R.X = finto` dopo che X e' andato in un altro modulo crea solo un attributo nuovo, e il codice vero scriverebbe in
produzione senza errori. Con ast, nei 5 file di test, ogni assegnazione a `ALIAS.NOME...` (anche dentro un indice,
in una tupla o aumentata) deve avere NOME definito al primo livello del modulo di ALIAS.
  - `ALIAS.NOME = ...` (si sostituisce NOME): NOME definito nel modulo, senza eccezioni (anche R.VE = ...).
  - `ALIAS.NOME.x = ...` o `ALIAS.NOME[i] = ...`: NOME definito nel modulo, oppure un modulo esterno ammesso
    (time, ponte, steering, VE, os, json, math, Path): li' cambia l'oggetto esterno, uguale per tutti.
ALIAS = un `import modulo [as ALIAS]` del test il cui file sta nel worktree (cartella del test, radice, engrammi).
Letture (task 10, dopo il test rosso del task 8 su `riflesso._rimetti(...)`): se ALIAS e' riflesso o riflesso_*, ogni
lettura `ALIAS.NOME` (Load o del, chiamate comprese) deve avere NOME definito al primo livello di quel modulo (gli
import del primo livello contano: R.time, R.os, R.Path...). Anche nel codice dentro le stringhe dei test (il passo 15
di test_firma_subito.py lancia un sottoprocesso col codice in una stringa): ogni stringa che e' Python valido e importa
un modulo del worktree si controlla come un file a se', con gli stessi alias del file che la contiene piu' i suoi.
Si lancia PRIMA dei test a ogni estrazione: esce con 1 se un bersaglio non c'e', e allora i test non partono.
Uso: /usr/bin/python3 manutenzione/controlla_bersagli.py"""
import ast
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent.parent
TEST = ["test_riflesso.py", "test_kv_disco.py", "test_fonti_124.py", "test_qlux_riflesso.py", "_wt_test-riflesso-query.py", "engrammi/test_via_emotiva.py",
        "engrammi/_wt_test_firma_subito.py", "test-riflesso-query.py", "engrammi/test_firma_subito.py"]
ESTERNI = {"time", "ponte", "steering", "VE", "os", "json", "math", "Path"}


def definiti(path):
    """i nomi definiti al primo livello di un modulo (anche dentro if/try/with/for del primo livello)"""
    nomi = set()

    def bersagli(t):
        if isinstance(t, ast.Name):
            nomi.add(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for x in t.elts:
                bersagli(x)
        elif isinstance(t, ast.Starred):
            bersagli(t.value)

    def blocco(corpo):
        for s in corpo:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nomi.add(s.name)
            elif isinstance(s, ast.Assign):
                for t in s.targets:
                    bersagli(t)
            elif isinstance(s, (ast.AnnAssign, ast.AugAssign)):
                bersagli(s.target)
            elif isinstance(s, (ast.Import, ast.ImportFrom)):
                for a in s.names:
                    nomi.add((a.asname or a.name).split(".")[0])
            elif isinstance(s, (ast.For, ast.AsyncFor)):
                bersagli(s.target)
                blocco(s.body + s.orelse)
            elif isinstance(s, (ast.With, ast.AsyncWith)):
                for w in s.items:
                    if w.optional_vars is not None:
                        bersagli(w.optional_vars)
                blocco(s.body)
            elif isinstance(s, ast.If):
                blocco(s.body + s.orelse)
            elif isinstance(s, ast.While):
                blocco(s.body + s.orelse)
            elif isinstance(s, ast.Try) or type(s).__name__ == "TryStar":
                blocco(s.body + s.orelse + s.finalbody)
                for h in s.handlers:
                    if h.name:
                        nomi.add(h.name)
                    blocco(h.body)
        # gli operatori tricheco del primo livello
        for n in ast.walk(ast.Module(body=[s for s in corpo if not isinstance(
                s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[])):
            if isinstance(n, ast.NamedExpr):
                bersagli(n.target)

    blocco(ast.parse(path.read_text(encoding="utf-8"), str(path)).body)
    return nomi


def alias_dei_moduli(albero, cartella):
    """{ALIAS: file del modulo} per gli import del test che stanno nel worktree"""
    dove = [cartella, QUI, QUI / "engrammi"]
    alias = {}
    for n in ast.walk(albero):
        if isinstance(n, ast.Import):
            for a in n.names:
                f = next((d / (a.name.replace(".", "/") + ".py") for d in dove
                          if (d / (a.name.replace(".", "/") + ".py")).exists()), None)
                if f and "." not in a.name:
                    alias[a.asname or a.name] = f
    return alias


def catena(t):
    """(ALIAS, NOME, profondo) di un bersaglio ALIAS.NOME[...][.x], o None"""
    profondo = False
    while isinstance(t, (ast.Attribute, ast.Subscript)):
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
            return t.value.id, t.attr, profondo
        profondo = True
        t = t.value
    return None


def bersagli_di(n):
    if isinstance(n, ast.Assign):
        ts = n.targets
    elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
        ts = [n.target]
    elif isinstance(n, (ast.For, ast.AsyncFor)):
        ts = [n.target]
    elif isinstance(n, (ast.With, ast.AsyncWith)):
        ts = [w.optional_vars for w in n.items if w.optional_vars is not None]
    else:
        return []
    out = []

    def apri(t):
        if isinstance(t, (ast.Tuple, ast.List)):
            for x in t.elts:
                apri(x)
        elif isinstance(t, ast.Starred):
            apri(t.value)
        else:
            out.append(t)
    for t in ts:
        apri(t)
    return out


def e_riflesso(f):
    return f.name == "riflesso.py" or (f.name.startswith("riflesso_") and f.suffix == ".py")


def codici_in_stringa(albero, cartella):
    """gli alberi del codice Python dentro le stringhe del test che importa moduli del worktree"""
    out = []
    for n in ast.walk(albero):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "import" in n.value:
            try:
                dentro = ast.parse(n.value)
            except SyntaxError:
                continue
            if alias_dei_moduli(dentro, cartella):
                out.append((n.lineno, dentro))
    return out


def controlla_albero(rel, albero, alias, cache, errori, base=0):
    contati = 0

    def definiti_di(f):
        if f not in cache:
            cache[f] = definiti(f)
        return cache[f]

    for n in ast.walk(albero):
        for t in bersagli_di(n):
            c = catena(t)
            if not c or c[0] not in alias:
                continue
            a, nome, profondo = c
            f = alias[a]
            contati += 1
            if nome in definiti_di(f) or (profondo and nome in ESTERNI):
                continue
            errori.append(f"{rel}:{base + n.lineno}: {a}.{nome} non e' definito al primo livello di {f.name}")
        if (isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Load, ast.Del)) and isinstance(n.value, ast.Name)
                and n.value.id in alias and e_riflesso(alias[n.value.id])):
            f = alias[n.value.id]
            contati += 1
            if n.attr not in definiti_di(f):
                errori.append(f"{rel}:{base + n.lineno}: lettura {n.value.id}.{n.attr}: non e' definito al primo "
                              f"livello di {f.name}")
    return contati


def controlla(file_test):
    errori, contati = [], 0
    for rel in file_test:
        p = QUI / rel
        if not p.exists():
            if Path(rel).name.startswith("_wt_"):   # 12/11: le copie _wt_ esistono solo nel worktree
                continue
            errori.append(f"{rel}: file mancante")
            continue
        albero = ast.parse(p.read_text(encoding="utf-8"), str(p))
        alias = alias_dei_moduli(albero, p.parent)
        cache = {}
        contati += controlla_albero(rel, albero, alias, cache, errori)
        for riga, dentro in codici_in_stringa(albero, p.parent):
            contati += controlla_albero(rel, dentro, {**alias, **alias_dei_moduli(dentro, p.parent)}, cache, errori,
                                        base=riga - 1)
    return errori, contati


if __name__ == "__main__":
    errori, contati = controlla(TEST)
    for e in errori:
        print("BERSAGLIO MANCANTE", e)
    print(f"controlla_bersagli: {contati} bersagli in {len(TEST)} file, {len(errori)} errori")
    sys.exit(1 if errori else 0)
