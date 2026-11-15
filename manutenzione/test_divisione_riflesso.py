#!/usr/bin/env python3
"""Test di struttura della divisione del riflesso (PIANO-DIVISIONE-RIFLESSO.md, task 1). Vale prima e dopo ogni
estrazione: oggi c'e' solo riflesso.py e deve passare su quello.
  1. nessun riflesso_*.py importa riflesso (trappola 1: una seconda copia con stato e lock propri);
  2. riflesso_stato.py non importa nessun modulo del progetto (foglia);
  3. nessun riflesso*.py avvia thread o timer all'import;
  4. nomi non definiti (py_compile non li vede): per ogni riflesso*.py, con symtable, ogni nome letto che non e'
     parametro, locale, chiuso da una funzione esterna, globale del modulo, import o builtin; e ogni ALIAS.nome con
     ALIAS = un modulo riflesso_* importato, nome definito al primo livello di quel modulo;
  5. prova del __main__: runpy.run_path("riflesso.py", run_name="__main__") in un sottoprocesso in uno spazio di rete
     e di mount nuovo (unshare -rnm: /tmp su tmpfs, /data/workspace, /data/memoria-episodica-affettiva e /dev/shm/agente-kv
     in sola lettura), con l'ambiente della fotografia; deve rispondere su :8091 entro 10 s, poi si chiude.
Si lancia nello spazio di rete isolato, dalla cartella del worktree:
  unshare -rn sh -c 'ip link set lo up; cd /data/memoria-episodica-affettiva-divisione && /usr/bin/python3 manutenzione/test_divisione_riflesso.py'"""
import ast
import builtins
import os
import re
import shutil
import socket
import subprocess
import sys
import symtable
import tempfile
import threading
from pathlib import Path

sys.dont_write_bytecode = True
QUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import controlla_bersagli as CB  # noqa: E402

for _p in (8008, 8090, 8091, 8132):
    _s = socket.socket()
    _s.settimeout(0.3)
    try:
        _s.connect(("127.0.0.1", _p))
        sys.exit(f"STOP: 127.0.0.1:{_p} risponde, il test non e' nello spazio di rete isolato (unshare -rn)")
    except OSError:
        pass
    finally:
        _s.close()

TUTTI = [QUI / "riflesso.py"] + sorted(QUI.glob("riflesso_*.py"))
NUOVI = TUTTI[1:]
# i moduli del progetto: tutto quello che sta nelle cartelle che riflesso e via_emotiva mettono in sys.path
PROGETTO = {p.stem for d in (QUI, QUI / "engrammi", QUI / "runtime", Path("/data/workspace/memoria"))
            if d.is_dir() for p in d.glob("*.py")}
errori = []


def importati(path):
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if isinstance(n, ast.Import):
            out += [(a.name, a.asname or a.name, n.lineno) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            out += [(n.module or "", None, n.lineno)]
    return out


# ---------- 1. niente import riflesso nei moduli nuovi ----------
for f in NUOVI:
    testo = f.read_text(encoding="utf-8")
    for k, riga in enumerate(testo.splitlines(), 1):
        if re.search(r"^\s*import\s+riflesso(\s|$)", riga) or re.search(r"^\s*from\s+riflesso\s+import", riga):
            errori.append(f"{f.name}:{k}: importa riflesso: {riga.strip()}")
    for nome, _, k in importati(f):
        if nome == "riflesso":
            errori.append(f"{f.name}:{k}: importa riflesso (ast)")
        elif nome.startswith("riflesso_") and any(isinstance(n, ast.ImportFrom) and n.module == nome
                                                  for n in ast.walk(ast.parse(testo))):
            errori.append(f"{f.name}:{k}: from {nome} import ... (si chiama per attributo, trappola 2)")
print(f"1. import di riflesso: {len(NUOVI)} moduli nuovi controllati")

# ---------- 2. riflesso_stato e' una foglia ----------
stato = QUI / "riflesso_stato.py"
if stato.exists():
    for nome, _, k in importati(stato):
        if nome.split(".")[0] in PROGETTO:
            errori.append(f"riflesso_stato.py:{k}: importa {nome}, che e' del progetto")
    print("2. riflesso_stato: controllato")
else:
    print("2. riflesso_stato: non c'e' ancora")

# ---------- 3. niente thread all'import ----------
T = Path(tempfile.mkdtemp(prefix="test-divisione-", dir="/dev/shm"))
AMBIENTE = {
    "VIA_EMOTIVA_STATO": str(T / "via-emotiva-stato.json"), "VIA_EMOTIVA_DIARIO": str(T / "diario-via-emotiva.jsonl"),
    "VIA_EMOTIVA_TRADUZIONE": str(QUI / "engrammi" / "via-emotiva" / "traduzione-l29.npz"),
    "RIFLESSO_VETTORI_SPENTI": str(T / "vettori-spenti"), "CODA_FIRMA": str(T / "coda-firma.jsonl"),
    "PONTE_URL": "http://127.0.0.1:18090", "TZ": "Europe/Rome", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
}
try:
    os.environ.update(AMBIENTE)
    os.environ.pop("RIFLESSO_COLLAUDO", None)
    sys.path.insert(0, str(QUI))
    prima = threading.active_count()
    import importlib  # noqa: E402
    for f in TUTTI:
        importlib.import_module(f.stem)
    dopo = threading.active_count()
    if dopo != prima:
        errori.append(f"thread all'import: {prima} -> {dopo} ({[t.name for t in threading.enumerate()]})")
    print(f"3. thread all'import: {prima} prima, {dopo} dopo ({len(TUTTI)} moduli)")

    # ---------- 4. nomi non definiti ----------
    BUILTIN = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__loader__", "__package__",
                                    "__builtins__", "__cached__", "__annotations__", "__dict__", "__module__",
                                    "__qualname__", "__class__"}

    def non_definiti(testo, nome_file):
        top = symtable.symtable(testo, nome_file, "exec")
        globali = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
        out = []

        def visita(t, dove):
            for s in t.get_symbols():
                if not s.is_referenced():
                    continue
                n = s.get_name()
                if t.get_type() == "module" or str(t.get_type()).endswith("MODULE"):
                    ignoto = not (s.is_assigned() or s.is_imported() or s.is_namespace()) and n not in BUILTIN
                else:
                    ignoto = s.is_global() and n not in globali and n not in BUILTIN
                if ignoto:
                    out.append(f"{dove}: {n}")
            for c in t.get_children():
                visita(c, f"{dove}.{c.get_name()}" if dove else c.get_name())
        visita(top, "")
        return out

    # il controllo deve vedere un nome sbagliato in un except e in un ciclo di thread (se no non prova niente)
    finto = ("import time\nDIARIO = 1\ndef _diario(v):\n    pass\ndef sentinella():\n    while True:\n"
             "        time.sleep(0.5)\n        try:\n            pass\n        except Exception as e:\n"
             "            _diarioo({'x': e})\nclass P:\n    def f(self):\n        return [DIARIOO for _ in ()]\n")
    assert sorted(x.split(": ")[1] for x in non_definiti(finto, "finto.py")) == ["DIARIOO", "_diarioo"], \
        non_definiti(finto, "finto.py")

    nuovi = {f.stem: f for f in NUOVI}
    definiti = {s: CB.definiti(f) for s, f in nuovi.items()}
    contati = 0
    for f in TUTTI:
        testo = f.read_text(encoding="utf-8")
        for e in non_definiti(testo, str(f)):
            errori.append(f"{f.name}: nome non definito in {e}")
        alias = {a: n for n, a, _ in importati(f) if a and n in nuovi}
        for n in ast.walk(ast.parse(testo)):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias:
                contati += 1
                if n.attr not in definiti[alias[n.value.id]]:
                    errori.append(f"{f.name}:{n.lineno}: {n.value.id}.{n.attr} non e' definito in "
                                  f"{alias[n.value.id]}.py")
    print(f"4. nomi non definiti: {len(TUTTI)} file, {contati} riferimenti fra moduli controllati")

    # ---------- 5. prova del __main__ ----------
    PROVA = r'''
import http.server, os, runpy, socket, sys, threading, time
class F(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        b = b'{"success": true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    do_GET = do_POST
s = http.server.ThreadingHTTPServer(("127.0.0.1", 18090), F)   # PONTE_URL: calma() all'avvio riesce, niente CRITICO
threading.Thread(target=s.serve_forever, daemon=True).start()
def prova():
    t0 = time.monotonic()
    while time.monotonic() - t0 < 10:
        try:
            c = socket.create_connection(("127.0.0.1", 8091), timeout=3)
        except OSError:
            time.sleep(0.2)
            continue
        c.sendall(b"POST /memorinvolontaria HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                  b"Content-Length: 2\r\n\r\n{}")
        out = b""
        while True:
            x = c.recv(65536)
            if not x:
                break
            out += x
        c.close()
        print("RISPOSTA", out.split(b"\r\n\r\n", 1)[-1].decode(), flush=True)
        os._exit(0 if out.startswith(b"HTTP/1.0 200") and b'"testo"' in out else 2)
    print("NESSUNA RISPOSTA su :8091 entro 10 s", flush=True)
    os._exit(1)
threading.Thread(target=prova, daemon=True).start()
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
    (T / "prova_main.py").write_text(PROVA, encoding="utf-8")
    sola_lettura = " ".join(f"mount --bind {d} {d} && mount -o remount,bind,ro {d} &&"
                            for d in ("/data/workspace", "/data/memoria-episodica-affettiva", "/dev/shm/agente-kv")
                            if os.path.isdir(d))
    comando = (f"mount -t tmpfs none /tmp && {sola_lettura} ip link set lo up && "
               f"exec /usr/bin/python3 {T}/prova_main.py {QUI}/riflesso.py")
    r = subprocess.run(["unshare", "-rnm", "sh", "-c", comando], capture_output=True, text=True, timeout=60,
                       env={**os.environ, **AMBIENTE}, cwd=str(QUI))
    if r.returncode != 0:
        errori.append(f"__main__: uscita {r.returncode}\n{r.stdout}\n{r.stderr}")
    print("5. __main__:", (r.stdout.strip().splitlines() or ["(niente)"])[-1][:200])
finally:
    shutil.rmtree(T, ignore_errors=True)

if errori:
    print("\n".join(["ERRORI:"] + errori))
    sys.exit(1)
print("test_divisione_riflesso: TUTTO VERDE")
