# Test dello step d (l'utente 12/11, PIANO-MEMORY-A-B-IMPLEMENTAZIONE.md): memory e user A/B. Senza server, senza GPU,
# senza toccare i file veri.
import json
import subprocess
import tempfile
from pathlib import Path

import riflesso_riepilogo as RP
import riflesso_cache as CA
import riflesso_stato as S
import riflesso_comune as C
import riflesso_vettore as VT

diario = []
C._diario = diario.append
T = Path(tempfile.mkdtemp())
RP.FISSA, RP.MEMORIA_B, RP.MASTER = T / "fissa.json", T / "memoria-b.json", T / "master.json"
RP.RIEPILOGO, RP.RIEPILOGO_LOG, RP.RIEPILOGO_PROMUOVI = T / "riepilogo.json", T / "log.md", T / "promuovi"
CA.KV_RAM = T / "kv"
CA.KV_RAM.mkdir()
VT.calma = lambda: True
S._vettore_vivo[0] = False

SEP = "═" * 46


def blocchi(mem, usr):
    """come li rende Hermes (memory_tool._render_block + system_prompt.py)"""
    out = []
    for nome, voci in (("MEMORY (your personal notes) [1% — 1/16,000 chars]", mem),
                       ("USER PROFILE (who the user is) [1% — 1/8,000 chars]", usr)):
        if voci:
            out.append(f"{SEP}\n{nome}\n{SEP}\n" + "\n§\n".join(voci))
    return "\n\n".join(out)


F = "Sono l'agente.\n\n## Skills (mandatory)\n- x\nOnly proceed without loading a skill if genuinely none are relevant " \
    "to the task.\n\n"
CODA = "Conversation started: Thursday, November 12, 2026\nModel: occamy"


def hermes(mem, usr, f=F):
    return f + blocchi(mem, usr) + "\n\n" + CODA


M0 = ["v1 hardware", "v2 ricerca", "v3 notturna a mezzanotte", "v4 metadati"]
U0 = ["u1 l'utente", "u2 orari 8-14"]

# _parti: F, A, T
f, a, t = RP._parti(hermes(M0, U0))
assert (f, a, t) == (F, blocchi(M0, U0), CODA), (f, a, t)
assert RP._parti("niente coda") is None
assert RP._parti(F + "\n\n" + CODA) == (F + "\n\n", "", CODA), "memory vuoto: A vuota"
assert RP._voci(blocchi(M0, U0)) == {"MEMORY": M0, "USER": U0}
assert RP._voci(blocchi([], U0)) == {"MEMORY": [], "USER": U0}, "blocco vuoto: riconosciuto dall'intestazione"

# _aggiornate: testi approvati dall'utente 12/11 sera, parola per parola
assert RP.TESTO_AGGIORNATE == "informazioni aggiornate" and RP.TESTO_OBSOLETE == "avviso! informazioni obsolete:"
B = blocchi(M0, U0)
assert RP._aggiornate(B, B) == "", "A = B: niente blocco"
cambiata = ["v1 hardware", "v2 ricerca", "v3 notturna alle 3:00", "v4 metadati"]
assert RP._aggiornate(blocchi(cambiata, U0), B) == "informazioni aggiornate\nMEMORY, voce 3\nv3 notturna alle 3:00\n\n"
assert RP._aggiornate(blocchi(M0 + ["v5 nuova"], ["u1 l'utente", "u2 orari 9-15"]), B) == (
    "informazioni aggiornate\nMEMORY, voce 5\nv5 nuova\nUSER, voce 2\nu2 orari 9-15\n\n"), "prima MEMORY poi USER"
assert RP._aggiornate(blocchi(["v1 hardware", "v3 notturna a mezzanotte", "v4 metadati"], U0), B) == (
    "informazioni aggiornate\navviso! informazioni obsolete:\nv2 ricerca\n\n"), "tolta: le posizioni scalano"
# il caso della revisione: tolta la 2 e cambiata la 3, difflib da' un solo replace [2,3] -> [3']
assert RP._aggiornate(blocchi(["v1 hardware", "v3 notturna alle 3:00", "v4 metadati"], U0), B) == (
    "informazioni aggiornate\nMEMORY, voce 2\nv3 notturna alle 3:00\navviso! informazioni obsolete:\nv2 ricerca\n\n")
assert RP._aggiornate(blocchi(["v4 metadati", "v1 hardware", "v2 ricerca", "v3 notturna a mezzanotte"], U0), B) == (
    ""), "spostata senza cambiare: niente blocco"
assert RP._aggiornate(B, F + B + "\n\n") == "", "la parte fissa nella base non conta"


def richiesta(sistema):
    return {"messages": [{"role": "system", "content": sistema}, {"role": "user", "content": "[utente] ciao"}],
            "tools": [{"type": "function", "function": {"name": "memory"}}]}


# chat, primo avvio: niente B e niente base -> B = la A di questa sessione, l'agente non vede cambiare niente
RP._riepilogo_salva({"blocco": ["r1"], "nuovi": []})
d = richiesta(hermes(M0, U0))
h = RP._metti_fissa(d, ["r1"])
BLOCCO = RP.INTESTAZIONE_RIEPILOGO + "\nr1\n\n"
assert d["messages"][0]["content"] == F + B + "\n\n" + BLOCCO + CODA, d["messages"][0]["content"]
assert h["system"] == hermes(M0, U0) and h["tools"] == ["memory"]
assert RP._b_carica() == B and RP._fissa_carica()["chat"] == F + B + "\n\n"
# l'agente cambia la voce 3 durante la sessione: Hermes tiene la copia congelata, il system non cambia
d2 = richiesta(hermes(M0, U0))
RP._metti_fissa(d2, ["r1"])
assert d2["messages"][0]["content"] == d["messages"][0]["content"], "system diverso fra due richieste"
# sessione nuova (A con la voce cambiata), base della chat con B: le informazioni dopo il riepilogo, identiche sempre
A1 = blocchi(cambiata, U0)
for _ in (1, 2):
    d3 = richiesta(F + A1 + "\n\n" + CODA)
    RP._metti_fissa(d3, ["r1"])
    assert d3["messages"][0]["content"] == (F + B + "\n\n" + BLOCCO + "informazioni aggiornate\nMEMORY, voce 3\n"
                                            "v3 notturna alle 3:00\n\n" + CODA), d3["messages"][0]["content"]
# (base col layout vecchio: riepilogo-fissa.json si toglie alla messa in produzione, piano punto 2)
RP._fissa_salva({"chat": F + B + "\n\n", "riepilogo": None, "elenco": None})
# skill cambiate in Hermes: resta la base della cache, una voce nel diario
n = len(diario)
F2 = F.replace("- x", "- y")
d5 = richiesta(hermes(M0, U0, F2))
RP._metti_fissa(d5, [])
RP._metti_fissa(richiesta(hermes(M0, U0, F2)), [])
assert d5["messages"][0]["content"] == F + B + "\n\n" + CODA
assert sum("parte fissa" in str(v) for v in diario[n:]) == 1

# _riassumi: la CW del riepilogo = parte fissa + B (file) + righe + coda; base rifatta e master.json scritto
passi, chiesti = [], []


def chiedi(path, x):
    chiesti.append((path, x))
    if path == "/apply-template":
        msgs = x["messages"]
        return {"prompt": "<|im_start|>system\nTOOLS\n" + msgs[0]["content"] + "<|im_end|>\n<|im_start|>user\n"
                + msgs[-1]["content"] + "<|im_end|>\n<|im_start|>assistant\n<think>\n"}
    if x.get("n_predict") == 220:
        return {"content": "<tool_call>\n<function=write_file>\n<parameter=path>\n/workspace/memoria/logRiepilogo.md\n"
                           "</parameter>\n<parameter=content>\nriga nuova\n</parameter>\n</function>\n</tool_call>"}
    return {"content": ""}


C._chiedi = chiedi
CA._slot = lambda az, nome: passi.append((az, nome)) or True
S._cw[0] = "chat"
S._tok_cw["chat"] = 10_000
RP._riepilogo_salva({"blocco": ["r1"], "nuovi": []})
RP._fissa_salva({"chat": F + B + "\n\n", "riepilogo": None, "elenco": None})
inoltrato = richiesta(F + B + "\n\n" + BLOCCO + CODA)
assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao l'utente!",
                    hermes={"system": F + A1 + "\n\n" + CODA, "tools": ["memory"]}) == (False, "ok"), diario[-3:]
tpl = [x for p, x in chiesti if p == "/apply-template"][-1]
assert tpl["messages"][0]["content"] == F + B + "\n\n" + RP.INTESTAZIONE_RIEPILOGO + "\nriga nuova\n\n" + CODA, tpl
comp = [x for p, x in chiesti if p == "/completion" and x.get("n_predict") == 1]
assert comp[0]["prompt"] == "<|im_start|>system\nTOOLS\n" + F + B + "\n\n" and comp[0]["checkpoint_tag"] == "sistema"
assert comp[1]["prompt"] == comp[0]["prompt"] + RP.INTESTAZIONE_RIEPILOGO + "\nriga nuova\n\n"
assert RP._fissa_carica()["riepilogo"] == F + B + "\n\n"
assert json.loads(RP.MASTER.read_text()) == {"fissa": F, "coda": CODA, "tools": inoltrato["tools"]}
# senza il system originale di Hermes il riepilogo salta (quello inoltrato ha B e le informazioni al posto di A)
n = len(diario)
assert RP._riassumi(json.dumps(inoltrato).encode(), "ciao")[1] == "fallito"
assert any("Hermes" in str(v) for v in diario[n:])

# promozione: la chat nuova prende la base di riepilogo.kv (con B vecchio), le informazioni contro quella
RP.RIEPILOGO_PROMUOVI.write_text("")
(CA.KV_RAM / "riepilogo.kv").write_bytes(b"x")
RP._promuovi()
assert RP._fissa_carica()["chat"] == F + B + "\n\n"

# notturna (POST /memoria-b): B = A resa da Hermes, base rifatta, la chat al riparo prima, poi slot "altro"
A2 = blocchi(cambiata + ["v5"], U0)
corse = []


def run(cmd, **k):
    corse.append(cmd[:3])
    if cmd[:2] == ["docker", "exec"] and fermo[0]:
        raise subprocess.CalledProcessError(1, cmd)
    return subprocess.CompletedProcess(cmd, 0, "log di avvio\n" + json.dumps(A2) + "\n", "")


fermo = [False]
RP.subprocess.run = run
passi.clear(); chiesti.clear()
for x in CA.KV_RAM.glob("riepilogo-base*"):
    x.unlink()
S._cw[0] = "chat"
assert RP.rifai_master() == "B aggiornato, base rifatta"
assert RP._b_carica() == A2
assert passi[0] == ("save", "chat.kv") and ("save", "riepilogo-base.kv") in passi and S._cw[0] == "altro", passi
comp = [x for p, x in chiesti if p == "/completion"]
assert comp == [{"prompt": "<|im_start|>system\nTOOLS\n" + F + A2 + "\n\n", "n_predict": 1, "cache_prompt": True,
                 "checkpoint_tag": "sistema"}], comp
# la base rifatta di notte e' quella che il primo riepilogo del giorno dopo riusa (stessa impronta: niente prefill)
passi.clear(); chiesti.clear()
(CA.KV_RAM / "riepilogo-base.kv").write_bytes(b"x")
RP._riepilogo_salva({"blocco": ["r1"], "nuovi": []})
S._cw[0] = "chat"
RP._riassumi(json.dumps(richiesta(F + B + "\n\n" + BLOCCO + CODA)).encode(), "ciao l'utente!",
             hermes={"system": F + A2 + "\n\n" + CODA, "tools": ["memory"]})
assert ("restore", "riepilogo-base.kv") in passi and ("save", "riepilogo-base.kv") not in passi, passi
# container fermo: ripiego sul volume
fermo[0] = True
corse.clear()
assert RP._b_da_hermes() == A2 and corse[-1] == ["docker", "run", "--rm"], corse
def scade(cmd, **k):
    if cmd[:2] == ["docker", "exec"]:
        raise subprocess.TimeoutExpired(cmd, 60)
    return subprocess.CompletedProcess(cmd, 1, "", "volume non trovato")


RP.subprocess.run = scade   # exec scaduto a meta' dello stop: ripiego; ripiego fallito: lo stderr nell'errore
try:
    RP._b_da_hermes()
    raise AssertionError("docker run fallito senza errore")
except RuntimeError as e:
    assert "volume non trovato" in str(e), e

# revisione del codice 12/11
# 1. Hermes senza memory (load_from_disk fallito): niente "tutto obsoleto", e al primo avvio nessun B vuoto salvato
RP._fissa_salva({"chat": F + B + "\n\n", "riepilogo": None, "elenco": None})
d = richiesta(F + "\n\n" + CODA)
RP._metti_fissa(d, [])
assert d["messages"][0]["content"] == F + B + "\n\n" + CODA, d["messages"][0]["content"]
RP.MEMORIA_B.unlink()
RP.FISSA.unlink()
d = richiesta(F + "\n\n" + CODA)
RP._metti_fissa(d, [])
assert d["messages"][0]["content"] == F + "\n\n" + CODA and not RP.MEMORIA_B.exists()
# 3. system senza la coda con la base nuova: mai MEMORY due volte
RP._fissa_salva({"chat": F + B + "\n\n", "riepilogo": None, "elenco": None})
d = richiesta(F + B)
RP._metti_fissa(d, [])
assert d["messages"][0]["content"] == F + B, d["messages"][0]["content"]
# 7. un errore nella base: il system di Hermes resta e il riepilogo ha comunque l'originale
RP._b_salva(B)
RP.FISSA.unlink()
salva_vero = RP._fissa_salva
RP._fissa_salva = lambda st: 1 / 0
d = richiesta(hermes(M0, U0))
h = RP._metti_fissa(d, ["r1"])
RP._fissa_salva = salva_vero
assert h["system"] == hermes(M0, U0) and RP.INTESTAZIONE_RIEPILOGO in d["messages"][0]["content"]
assert any("base non messa" in str(v) for v in diario[-3:])
print("test_memoria_ab: TUTTO VERDE")
