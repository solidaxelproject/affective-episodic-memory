# riflesso_riepilogo.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import contextlib
import difflib
import functools
import json
import re
import subprocess
import time
from pathlib import Path
import riflesso_stato as S
import riflesso_comune as C
import riflesso_vettore as VT
import riflesso_metadati as MD
import riflesso_cache as CA


ATTESA_ALTRO_S = 300    # oltre, il riepilogo di quello scambio salta (valore di CC)


# --- riepilogo a catena di montaggio (l'utente 20/10, PIANO-RIEPILOGO-KV.md): dopo ogni risposta all'utente,
# l'agente scrive il succo dello scambio in una riga; le righe si accodano in una CW a parte (riepilogo.kv) e alla
# dormita diventano il blocco in testa alla chat nuova. Solo la chat, mai il pensatoio (20/10).
RIEPILOGO = Path("/data/memoria-episodica-affettiva/riepilogo.json")
RIEPILOGO_PROMUOVI = Path("/data/memoria-episodica-affettiva/.riepilogo-promuovi")   # lo scrive dormi-esegui.sh
RIEPILOGO_KV = "riepilogo.kv"
RIEPILOGO_BASE = "riepilogo-base.kv"   # K2 (10/11): la parte fissa sola, punto di partenza della CW nuova
# 10/11: l'agente scrive la riga con write_file su questo file (skill riepilogo); il riflesso la esegue (Hermes in
# quel momento non c'e'), una chiamata diretta altrove si scarta. Il file riparte vuoto a ogni sessione nuova
RIEPILOGO_LOG = Path("/data/workspace/memoria/logRiepilogo.md")
RIEPILOGO_LOG_SAM = ("/workspace/memoria/logRiepilogo.md",
                     "/home/agente/workspace/memoria/logRiepilogo.md")   # lo stesso file nel container (3.5.3)
# una chiamata tagliata dal tetto dei token (senza le chiusure) vale con la parte che c'e'
_WRITE_FILE = re.compile(r"<function=write_file>(.*?)(?:</function>|$)", re.S)
_PARAMETRO = re.compile(r"<parameter=(\w+)>(.*?)(?:</parameter>|(?=<parameter=)|$)", re.S)
RIEPILOGO_TETTO = 40_000    # token (caratteri / 3): oltre, via le righe piu' vecchie. Valore di CC
INTESTAZIONE_RIEPILOGO = ("Ecco dov'ero rimasta, questo è il succo della conversazione fino al momento in cui mi "
                          "sono addormentata:")
ISTRUZIONE_RIEPILOGO = (
    "Devo scrivere, in meno di 60 parole, il succo di quest'ultimo messaggio o di quello dell'utente se necessario: le "
    "informazioni salienti che voglio conservare dell'ultimo scambio. Non i messaggi precedenti. Solo testo, numeri o "
    "simboli logici se utili, per esempio: uguale può diventare =, implica →, maggiore >. Se necessario posso "
    "inserire il codice di un ricordo che reputo utile per questo riassunto. Se in questo scambio mi è affiorato un "
    "ricordo, aggiungo il suo codice. Lo scrivo con write_file in /workspace/memoria/logRiepilogo.md.")   # coda: l'utente 10/11
SEPARATORE = "══"   # da questa riga in poi il system di Hermes cambia fra le sessioni (MEMORY, data)
# BLOCCO B (l'utente 10/11, PIANO-RIEPILOGO-KV.md 3.5, K4 K10 K14 K15 K18): l'avviso va PRIMA dell'istruzione, solo
# nella chiamata del riepilogo (la chat salvata non lo contiene); [cwswitch] in coda al riepilogo = switch subito
AVVISO_90K = (
    "[avviso di spazio: la conversazione ha superato i 90mila token e la finestra si sta riempiendo. A 100mila "
    "passerò da sola a una conversazione nuova, che riparte dal mio riepilogo. Se voglio farlo prima, scrivo "
    "[cwswitch] in coda al riepilogo.]")
CWSWITCH = re.compile(r"\[cwswitch\]", re.I)
# lo switch = la dormita di oggi: agente-dormi.path -> dormi-esegui.sh (sessione nuova + .riepilogo-promuovi)
DORMI_FLAG = Path("/data/workspace/memoria/.dormi-richiesto")
SWITCH_IN_CORSO = Path("/data/memoria-episodica-affettiva/.switch-in-corso")   # lo tiene dormi-esegui.sh mentre gira
SWITCH_RITENTA_S = 900   # switch chiesto ma nessuna promozione: si richiede dopo 15 min (valore di CC)
_switch = {"motivo": None, "chiesto": 0.0}   # motivo (rimandato o in attesa della promozione); ultima richiesta


def _riga_scritta(testo):
    """il content della chiamata write_file dell'agente su logRiepilogo.md, None se non c'e'. Una chiamata tagliata
    prima del path vale (3.5.3: l'agente a volte scrive prima il content e il tetto dei token taglia il resto)"""
    for c in _WRITE_FILE.finditer(testo):
        p = dict(_PARAMETRO.findall(c.group(1)))
        path = p.get("path", "").strip()
        if path in RIEPILOGO_LOG_SAM or (not path and "content" in p and not c.group(0).endswith("</function>")):
            return p.get("content", "")
    return None


def _riepilogo_carica():
    vuoto = {"blocco": [], "nuovi": []}
    try:
        st = json.loads(RIEPILOGO.read_text(encoding="utf-8"))
        return {"blocco": list(st["blocco"]), "nuovi": list(st["nuovi"])}
    except FileNotFoundError:
        return vuoto
    except Exception as e:
        C._diario({"riepilogo": f"riepilogo.json illeggibile, niente blocco: {e}"})
        return vuoto


def _riepilogo_salva(st):
    tmp = RIEPILOGO.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    tmp.replace(RIEPILOGO)


def _blocco(righe):
    return INTESTAZIONE_RIEPILOGO + "\n" + "\n".join(righe) + "\n\n" if righe else ""


def _nel_tetto(righe):
    while righe and len(_blocco(righe)) / 3 > RIEPILOGO_TETTO:
        righe = righe[1:]
    return righe


def _riga_separatore(testo):
    """dove comincia la riga ══, -1 se manca"""
    i = testo.find(SEPARATORE)
    return testo.rfind("\n", 0, i) + 1 if i >= 0 else -1


def _con_blocco(system, righe):
    """il blocco subito prima della riga ══: prima il system e' fisso fra le sessioni e la cache lo riusa"""
    i = _riga_separatore(system)
    if i < 0:
        C._diario({"riepilogo": "riga ══ non trovata: blocco in fondo al system"})
        return system + "\n\n" + _blocco(righe)
    return system[:i] + _blocco(righe) + system[i:]


def _metti_blocco(d, righe):
    """in place sul corpo di una richiesta della chat"""
    msgs = d.get("messages", [])
    if righe and msgs and msgs[0].get("role") == "system":
        msgs[0]["content"] = _con_blocco(msgs[0]["content"], righe)


# R6 (l'utente 24/10, PIANO-REVISIONI-FUORI-CACHE.md): la parte fissa del system (prima di ══, elenco skill compreso)
# cambia nella chat solo quando nasce una CW del riepilogo nuova. Qui: la fissa con cui e' nata la chat in corso, quella
# di riepilogo.kv in formazione e l'elenco skill adottato a meta' sessione (sotto 20 righe del log)
FISSA = Path("/data/memoria-episodica-affettiva/riepilogo-fissa.json")
ELENCO_DA = "## Skills (mandatory)\n"   # i marcatori fissi di prompt_builder.py (build_skills_system_prompt)
ELENCO_A = "Only proceed without loading a skill if genuinely none are relevant to the task."
ELENCO_RIGHE = 20
_elenco_ok = [None]          # CONTROLLO della sessione: None = da fare, poi True/False
_fissa_avvisata = [False]    # la sostituzione va nel diario una volta per sessione
# l'elenco come lo compone Hermes (system_prompt.py:260-285, postura di default); model_tools riempie il registry
SKILLS_HERMES = """import json, sys
import model_tools
from agent.prompt_builder import build_skills_system_prompt
t = set(json.loads(sys.stdin.read()))
ts = {x for x in map(model_tools.get_toolset_for_tool, t) if x}
print("\\n" + json.dumps(build_skills_system_prompt(available_tools=t, available_toolsets=ts)))
"""


def _fissa_carica():
    try:
        st = json.loads(FISSA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st = {}
    except Exception as e:
        C._diario({"riepilogo": f"riepilogo-fissa.json illeggibile: {e}"})
        st = {}
    return {k: st.get(k) for k in ("chat", "riepilogo", "elenco")}


def _fissa_salva(st):
    tmp = FISSA.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FISSA)


def _fissa(testo):
    """la parte del system prima della riga ══, None se manca"""
    i = _riga_separatore(testo)
    return testo[:i] if i >= 0 else None


def _elenco(testo):
    """l'elenco skill dentro il system, None se mancano i marcatori"""
    i = testo.find(ELENCO_DA)
    j = testo.find(ELENCO_A, i)
    return testo[i:j + len(ELENCO_A)] if i >= 0 and j >= 0 else None


# step d (l'utente 12/11, PIANO-MEMORY-A-B.md): nel system della chat B, la copia di MEMORY.md e USER.md tenuta dal
# codice, al posto della copia di Hermes (A); B sta nella base della cache (parte fissa + B) e cambia solo di notte.
# Le voci di A diverse da B vanno nel blocco "informazioni aggiornate", subito dopo il riepilogo
MEMORIA_B = Path("/data/memoria-episodica-affettiva/memoria-b.json")
MASTER = Path("/data/memoria-episodica-affettiva/master.json")   # parte fissa, coda e tools per rifare la base di notte
CODA_HERMES = "\n\nConversation started:"   # system_prompt.py: dopo MEMORY e USER, la riga della data
DELIM = "\n§\n"   # memory_tool.py ENTRY_DELIMITER
_TESTATA = re.compile(r"^═{46}\n(MEMORY|USER) .*\n═{46}\n", re.M)
TESTO_AGGIORNATE = "informazioni aggiornate"            # testi approvati dall'utente 12/11 sera
TESTO_OBSOLETE = "avviso! informazioni obsolete:"
SOGLIA_STESSA_VOCE = 0.5   # valore di CC: dentro un replace, la voce di A e' quella di B cambiata
# la resa di A come la fa Hermes (filtro delle minacce, deduplica, limiti del config, unione come system_prompt.py)
B_HERMES = """import json
from hermes_cli.config import load_config
from tools.memory_tool import MemoryStore
m = load_config()["memory"]
s = MemoryStore(memory_char_limit=m["memory_char_limit"], user_char_limit=m["user_char_limit"])
s.load_from_disk()
parti = [s.format_for_system_prompt("memory") if m.get("memory_enabled") else None,
         s.format_for_system_prompt("user") if m.get("user_profile_enabled") else None]
print("\\n" + json.dumps("\\n\\n".join(x.strip() for x in parti if x and x.strip())))
"""
HERMES_FERMO = ["docker", "run", "--rm", "-i", "--entrypoint", "python3",
                "-v", "agente-dati:/home/agente/.hermes",
                "-v", "/data/agente-docker/config.yaml:/home/agente/.hermes/config.yaml:ro",
                "agente", "-"]


def _parti(h):
    """(F, A, T): parte fissa, blocchi MEMORY e USER, coda da "Conversation started:"; None senza la coda"""
    j = h.rfind(CODA_HERMES)
    if j < 0:
        return None
    i = _riga_separatore(h[:j])
    i = i if i >= 0 else j + 2
    return h[:i], h[i:j], h[j + 2:]


def _base(f, b):
    return f + (b + "\n\n" if b else "")


def _voci(testo):
    """{"MEMORY": [...], "USER": [...]} dai blocchi resi da Hermes, riconosciuti dall'intestazione"""
    v, pezzi = {"MEMORY": [], "USER": []}, _TESTATA.split(testo)
    for nome, corpo in zip(pezzi[1::2], pezzi[2::2]):
        v[nome] = [x for x in corpo.rstrip("\n").split(DELIM) if x]
    return v


@functools.lru_cache(maxsize=4)
def _aggiornate(a, b):
    """le voci di A nuove o cambiate rispetto a B, nella forma nuova, e le voci tolte (testi dell'utente 12/11).
    difflib allinea le voci uguali anche se le posizioni scalano; dentro un replace le coppie per somiglianza"""
    va, vb = _voci(a), _voci(b)
    nuove, tolte = [], []
    for nome in ("MEMORY", "USER"):
        A, B = va[nome], vb[nome]
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, B, A, autojunk=False).get_opcodes():
            # una voce solo spostata non e' cambiata di contenuto
            ii = [i for i in range(i1, i2) if B[i] not in A]
            jj = [j for j in range(j1, j2) if A[j] not in B]
            nuove += [(nome, j) for j in jj]
            prese_i, prese_j = set(), set()
            for r, i, j in sorted(((difflib.SequenceMatcher(None, B[i], A[j]).ratio(), i, j)
                                   for i in ii for j in jj), reverse=True):
                if r >= SOGLIA_STESSA_VOCE and i not in prese_i and j not in prese_j:
                    prese_i.add(i)
                    prese_j.add(j)
            tolte += [B[i] for i in ii if i not in prese_i]
    if not nuove and not tolte:
        return ""
    righe = [TESTO_AGGIORNATE]
    for nome, j in nuove:
        righe += [f"{nome}, voce {j + 1}", va[nome][j]]
    if tolte:
        righe += [TESTO_OBSOLETE] + tolte
    return "\n".join(righe) + "\n\n"


def _b_carica():
    try:
        return json.loads(MEMORIA_B.read_text(encoding="utf-8"))["testo"]
    except FileNotFoundError:
        return None
    except Exception as e:
        C._diario({"riepilogo": f"memoria-b.json illeggibile: {e}"})
        return None


def _b_o(a):
    """B dal file; al primo avvio B = la A di questa sessione (l'agente non vede cambiare niente), mai un B vuoto salvato"""
    b = _b_carica()
    if b is None:
        b = a
        if a:
            _b_salva(b)
    return b


def _b_salva(testo):
    tmp = MEMORIA_B.with_suffix(".tmp")
    tmp.write_text(json.dumps({"testo": testo, "data": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(MEMORIA_B)


def _b_da_hermes():
    """MEMORY.md e USER.md resi da Hermes: dal container acceso, se no da uno usa e getta sul volume"""
    try:
        p = subprocess.run(["docker", "exec", "-i", "agente", "python3", "-"], input=B_HERMES,
                           capture_output=True, text=True, timeout=60, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):   # es. a meta' dello stop dello switch
        p = subprocess.run(HERMES_FERMO, input=B_HERMES, capture_output=True, text=True, timeout=120)
        if p.returncode:
            raise RuntimeError(f"docker run: {p.stderr.strip()[-300:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def _master_salva(m):
    try:
        if json.loads(MASTER.read_text(encoding="utf-8")) == m:
            return
    except (FileNotFoundError, ValueError):
        pass
    tmp = MASTER.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    tmp.replace(MASTER)


def _taglio(resa):
    """nel prompt reso, dove comincia la coda di Hermes ("Conversation started:"); -1 se manca"""
    return resa.rfind(CODA_HERMES[2:])


def rifai_master():
    """notturna (POST /memoria-b): B = A e base della CW del riepilogo (cache master) rifatta, all'agente addormentata"""
    b = _b_da_hermes()
    _b_salva(b)
    try:
        m = json.loads(MASTER.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "B aggiornato; master.json assente, la base la rifa' il primo riepilogo"
    with _slot_libero() as libero:
        if not libero:
            return "B aggiornato; slot occupato, la base la rifa' il primo riepilogo"
        if S._vettore_vivo[0]:
            VT.calma()
        if S._cw[0] == "pensatoio":
            CA._interrompi_pensatoio()
        if S._cw[0] in S.KV_FLUSSO:
            CA._slot("save", S.KV_FLUSSO[S._cw[0]])
        CA._cambia_cw("altro")   # la prossima richiesta di ogni flusso rimette la sua cache (_scambia)
        resa = C._chiedi("/apply-template", {
            "messages": [{"role": "system", "content": _base(m["fissa"], b) + m["coda"]},
                         {"role": "user", "content": "."}], "tools": m["tools"]})["prompt"]
        i = _taglio(resa)
        if i < 0:
            raise ValueError("coda di Hermes non trovata nel prompt reso")
        _base_riepilogo(resa[:i])
    return "B aggiornato, base rifatta"


def _avvisa_fissa(diversa):
    if diversa and not _fissa_avvisata[0]:
        _fissa_avvisata[0] = True
        C._diario({"riepilogo": "parte fissa della cache al posto di quella di Hermes (skill cambiate)"})


def _metti_fissa(d, righe=()):
    """in place sul corpo di una richiesta della chat: la base della cache (parte fissa + B) al posto di quella di
    Hermes, poi il blocco del riepilogo e le informazioni aggiornate (step d). Torna il system e i nomi dei tool di
    Hermes com'erano (per il riepilogo e per l'elenco)"""
    msgs = d.get("messages", [])
    if not msgs or msgs[0].get("role") != "system":
        return None
    h = msgs[0]["content"]
    hermes = {"system": h, "tools": [t["function"]["name"] for t in d.get("tools") or [] if t.get("function")]}
    p = _parti(h)
    if p is None:   # system senza "Conversation started:": come prima dello step d
        fc, i = _fissa_carica()["chat"], _riga_separatore(h)
        if fc and SEPARATORE in fc:   # base con B + A di Hermes = MEMORY due volte: system intatto
            C._diario({"riepilogo": "system di Hermes senza 'Conversation started:': base non messa"})
        elif fc and i >= 0:
            _avvisa_fissa(h[:i] != fc)
            msgs[0]["content"] = fc + h[i:]
        _metti_blocco(d, righe)
        return hermes
    try:
        msgs[0]["content"] = _system_chat(*p, righe)
    except Exception as e:   # il riepilogo ha comunque il system di Hermes
        C._diario({"riepilogo": f"base non messa: {e}"})
        _metti_blocco(d, righe)
    return hermes


def _system_chat(f, a, t, righe):
    fs = _fissa_carica()
    base = fs["chat"]
    if base is not None:
        _avvisa_fissa(not base.startswith(f))
    else:
        base = _base(f, _b_o(a))
        fs["chat"] = base
        _fissa_salva(fs)
    if not a:   # Hermes senza memory (load_from_disk fallito): mai dire all'agente che e' tutto obsoleto
        if SEPARATORE in base:
            C._diario({"riepilogo": "system di Hermes senza MEMORY e USER: niente informazioni aggiornate"})
        return base + _blocco(righe) + t
    return base + _blocco(righe) + _aggiornate(a, base) + t


def _skills_da_hermes(tools):
    p = subprocess.run(["docker", "exec", "-i", "agente", "python3", "-c", SKILLS_HERMES], input=json.dumps(tools),
                       capture_output=True, text=True, timeout=5, check=True)
    return json.loads(p.stdout.strip().splitlines()[-1])


def _elenco_hermes(hermes):
    """l'elenco skill come lo comporrebbe Hermes adesso, se e' cambiato e il log del riepilogo ha meno di 20 righe;
    None = niente da cambiare. Fuori dai lucchetti (docker exec ~0,5 s, misura 10/11; tetto 5 s: il riepilogo aspetta)"""
    if not hermes or _elenco_ok[0] is False or len(_riepilogo_carica()["nuovi"]) >= ELENCO_RIGHE:
        return None
    in_uso = _fissa_carica()["elenco"] or _elenco(hermes["system"])
    if in_uso is None:
        return None
    try:
        uscita = _skills_da_hermes(hermes["tools"])
    except Exception as e:      # es. durante lo switch: si salta il giro, il CONTROLLO resta da fare
        C._diario({"riepilogo": f"elenco skill non letto da Hermes: {e}"})
        return None
    if _elenco_ok[0] is None:   # CONTROLLO: a skill invariate Hermes deve dare l'elenco che sta nel system
        _elenco_ok[0] = uscita == in_uso
        if not _elenco_ok[0]:
            C._diario({"riepilogo": "elenco skill di Hermes diverso da quello del system: spento per la sessione"})
        return None
    return uscita if uscita != in_uso else None


def _turno_finito(corpo, esito):
    """l'ultima risposta a un messaggio dell'utente nella chat, comunque sia finita, mai a meta' di un giro di tool:
    il background review e il memory flush di Hermes non cominciano con "[", il pensatoio si', ma il suo flusso
    e' un altro. Il corpo e' quello SENZA metadati: il blocco in testa comincia sempre con "[" """
    if CA._flusso(corpo) != "chat" or esito.get("tool_calls") or esito.get("interrotta"):
        return False
    msgs = json.loads(corpo).get("messages", [])
    ultimo = next((m.get("content") for m in reversed(msgs) if m.get("role") == "user"), "")
    return isinstance(ultimo, str) and ultimo.startswith("[")


def _deve_riassumere(corpo, esito):
    """solo la risposta FINALE a un messaggio dell'utente, finita bene e con del testo"""
    return esito.get("finish") == "stop" and bool((esito.get("testo") or "").strip()) and _turno_finito(corpo, esito)


@contextlib.contextmanager
def _slot_libero(scadenza=None):
    """10/11: i lucchetti del riepilogo, presi solo con lo slot libero da richieste estranee (cron, servizi di
    Hermes): rimettere la chat sotto una di loro faceva salvare come chat.kv lo stato di un'altra conversazione.
    Si aspetta fuori dai lucchetti (la colorazione di quella usa _vettore_lock). True = presi, False = tempo scaduto.
    Revisione 3.5.3, punto 2: si aspetta anche una risposta della chat in volo (senza scadenza: finisce sempre) e il
    suo salvataggio, se no il restore rimette il chat.kv di prima e lo stato del turno nuovo si perde"""
    scadenza = scadenza or time.time() + ATTESA_ALTRO_S
    while True:
        while S._altro_in_volo[0] or S._chat_in_volo[0]:
            if S._altro_in_volo[0] and time.time() > scadenza:
                yield False
                return
            time.sleep(0.5)
        if S._salva_ultimo[0]:
            S._salva_ultimo[0].join()
        S._vettore_lock.acquire()
        S._cw_lock.acquire()
        if not S._altro_in_volo[0] and not S._chat_in_volo[0]:
            break
        S._cw_lock.release()
        S._vettore_lock.release()
    try:
        yield True
    finally:
        S._cw_lock.release()
        S._vettore_lock.release()


def _riassumi(corpo, risposta, ragionamento="", senza=None, scadenza=None, hermes=None, elenco=None):
    """l'agente scrive il succo dello scambio nello slot della chat, la riga va in coda al blocco nella CW del
    riepilogo, la chat torna nello slot. Tutto dentro i lucchetti: una richiesta della chat che arriva intanto
    aspetta (~6 s). Gli errori vanno solo nel diario: mai bloccare la parola dell'agente.
    Torna (switch, esito): switch = l'agente, avvisata dei 90k, l'ha chiesto con [cwswitch] (K15); esito ok/vuoto/scartato/fallito."""
    avviso = S.SOGLIA_AVVISO < S._tok_cw["chat"] <= S.SOGLIA_CW   # conteggio della chat appena salvata (3.3 punto 11)
    switch, esito = False, "fallito"
    with _slot_libero(scadenza) as libero:   # 10/11: mai con una richiesta estranea nello slot
        if not libero:
            C._diario({"riepilogo": "saltato: una richiesta estranea tiene lo slot da troppo"})
            return False, "fallito"
        if S._vettore_vivo[0]:    # niente vettori di steering nel riepilogo
            VT.calma()
        try:
            if S._cw[0] == "pensatoio":
                CA._interrompi_pensatoio()     # come fa la chat (spec punto 4)
            if S._cw[0] != "chat":
                CA._scambia("chat")
            d = json.loads(corpo)
            tools = d.get("tools") or []
            # il prompt della risposta appena data, reso dal server, + la risposta + l'ISTRUZIONE a mano: un
            # messaggio user nuovo farebbe togliere al template il <think> dei giri di tool del turno e il
            # turno intero si riprocesserebbe (revisione 20/10)
            resa = C._chiedi("/apply-template", {k: v for k, v in d.items()
                                               if k in ("messages", "tools", "tool_choice",
                                                        "chat_template_kwargs")})["prompt"]
            if resa.endswith("<think>\n"):   # il ragionamento del server finisce gia' col suo a capo
                resa += ragionamento + ("" if ragionamento.endswith("\n") else "\n") + "</think>\n\n"
            gen = C._chiedi("/completion", {
                "prompt": resa + risposta + "<|im_end|>\n<|im_start|>user\n"
                          + (AVVISO_90K + "\n\n" if avviso else "") + ISTRUZIONE_RIEPILOGO
                          + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n",
                "n_predict": 220, "cache_prompt": True})   # 160 + la chiamata write_file
            scritta = _riga_scritta(gen.get("content") or "")
            switch = avviso and bool(CWSWITCH.search(gen.get("content") or ""))   # anche dopo la write_file (3.5.3)
            if scritta is None:
                C._diario({"riepilogo": f"scartato, niente write_file su logRiepilogo.md: {(gen.get('content') or '')[:300]}"})
                return switch, "scartato"
            riga = " ".join(CWSWITCH.sub("", scritta).split())
            if not riga:
                C._diario({"riepilogo": "riassunto vuoto"})
                return switch, "vuoto"
            st = _riepilogo_carica()
            st["nuovi"].append(riga)
            _riepilogo_salva(st)
            with RIEPILOGO_LOG.open("a", encoding="utf-8") as f:
                f.write(riga + "\n")
            # il system della CW del riepilogo: quello ORIGINALE di Hermes (R6), con l'elenco skill adottato,
            # e il blocco delle righe di questa sessione
            sistema = hermes["system"] if hermes else d["messages"][0]["content"].replace(_blocco(st["blocco"]), "", 1)
            fs = _fissa_carica()
            if elenco and elenco != fs["elenco"]:
                fs["elenco"] = elenco
                _fissa_salva(fs)
                C._diario({"riepilogo": "elenco skill nuovo nella CW del riepilogo"})
            vecchio = _elenco(sistema)
            if fs["elenco"] and vecchio:
                sistema = sistema.replace(vecchio, fs["elenco"], 1)
            righe_blocco = _blocco(_nel_tetto(st["nuovi"]))
            p = _parti(sistema)
            if p and not hermes:   # quello inoltrato ha gia' B e le informazioni aggiornate al posto di A
                raise ValueError("manca il system originale di Hermes")
            if p:   # step d: parte fissa + B (la master), poi il blocco delle righe, poi la coda di Hermes
                f, a, t = p
                base = _base(f, _b_o(a))
                sis = base + righe_blocco + t
                _master_salva({"fissa": f, "coda": t, "tools": tools})
            else:
                base, sis = _fissa(sistema), _con_blocco(sistema, _nel_tetto(st["nuovi"]))
            resa = C._chiedi("/apply-template", {
                "messages": [{"role": "system", "content": sis},
                             {"role": "user", "content": "."}],   # il template vuole un user: si taglia via
                "tools": tools})["prompt"]
            i = _taglio(resa) if p else _riga_separatore(resa)
            if i < 0:
                raise ValueError("fine del blocco non trovata nel prompt reso")
            if not resa[:i].endswith(righe_blocco):
                raise ValueError("blocco del riepilogo non trovato nel prompt reso")
            # parte fissa o B cambiate: riepilogo.kv divergerebbe a meta', si riparte dalla base
            if (CA.KV_RAM / RIEPILOGO_KV).exists() and fs["riepilogo"] in (None, base):
                CA._slot("restore", RIEPILOGO_KV)
            else:
                _base_riepilogo(resa[:i - len(righe_blocco)])
            C._chiedi("/completion", {"prompt": resa[:i], "n_predict": 1, "cache_prompt": True,
                                    "checkpoint_tag": "riepilogo"})   # K3: una riga, un checkpoint protetto
            if not CA._slot("save", RIEPILOGO_KV):
                raise RuntimeError("save di riepilogo.kv fallita")
            fs["riepilogo"] = base
            _fissa_salva(fs)
            esito = "ok"
        except Exception as e:
            C._diario({"riepilogo": f"fallito: {e}"})
        finally:
            ok = False
            try:
                ok = CA._slot("restore", S.KV_FLUSSO["chat"])
            except Exception:
                pass
            if not ok:      # lo slot tiene il riepilogo: la prossima richiesta della chat rifa' il restore
                C._diario({"riepilogo": "chat non rimessa nello slot"})
            S._cw[0] = "chat" if ok else "altro"
            # niente prefill anticipato con un'altra richiesta della chat o con lo switch in arrivo
            if ok and senza and not S._chat_in_volo[0] and not switch and S._tok_cw["chat"] <= S.SOGLIA_CW:
                try:
                    MD._anticipa(senza, risposta)
                except Exception as e:
                    C._diario({"metadati": f"prefill anticipato fallito: {e}"})
    return switch, esito


def _base_riepilogo(fissa):
    """K2 (10/11): la CW del riepilogo nuova parte dalla cache BASE (solo la parte fissa del system, tools
    compresi), rifatta solo quando la parte fissa cambia. Solo dentro _cw_lock"""
    imp, segno = C._impronta(fissa), CA.KV_RAM / (RIEPILOGO_BASE + ".impronta")
    if (CA.KV_RAM / RIEPILOGO_BASE).exists() and segno.exists() and segno.read_text() == imp \
            and CA._slot("restore", RIEPILOGO_BASE):
        return
    C._chiedi("/completion", {"prompt": fissa, "n_predict": 1, "cache_prompt": True, "checkpoint_tag": "sistema"})
    if CA._slot("save", RIEPILOGO_BASE):
        segno.write_text(imp)


def _forse_switch(cwswitch, esito_riepilogo="non fatto"):
    """Fine di un turno dell'utente (K4, K15, K18): switch di CW se l'agente l'ha chiesto o se la chat supera i 100k,
    qualunque sia stato l'esito del riepilogo. Mai con una risposta della chat in volo (docker stop la taglierebbe):
    si rimanda alla fine di quella. Uno solo finche' non c'e' la promozione (revisione del blocco B, punto 1)."""
    motivo = "[cwswitch]" if cwswitch else "oltre 100k" if S._tok_cw["chat"] > S.SOGLIA_CW else _switch["motivo"]
    if not motivo or time.time() - _switch["chiesto"] < SWITCH_RITENTA_S \
            or SWITCH_IN_CORSO.exists() or RIEPILOGO_PROMUOVI.exists():   # uno switch c'e' gia' (es. mezzanotte)
        return
    if S._chat_in_volo[0]:
        _switch["motivo"] = motivo
        return
    DORMI_FLAG.touch()
    _switch.update(motivo=motivo, chiesto=time.time())   # fino a _promuovi: si richiede se la rotazione fallisce (3.5.3)
    C._diario({"cw": f"switch: {motivo} ({S._tok_cw['chat']} tok), riepilogo {esito_riepilogo}"})


def _fine_chat(corpo, esito, salva, senza=None, hermes=None):
    """dopo l'ultima risposta di un turno dell'utente: riepilogo (se la risposta e' finita bene), poi lo switch.
    Uno switch rimandato parte alla fine di qualunque richiesta della chat fuori da un giro di tool (3.5.3, 3b)"""
    if not _turno_finito(senza or corpo, esito):
        if _switch["motivo"] and not esito.get("tool_calls") and not esito.get("interrotta"):
            _forse_switch(False)
        return
    if salva:
        salva.join()    # il conteggio dei token resta quello della chat appena salvata
    cwswitch, fatto = False, "non fatto"
    try:
        if _deve_riassumere(senza or corpo, esito):
            try:
                elenco = _elenco_hermes(hermes)
            except Exception as e:     # mai saltare il riepilogo per l'elenco
                elenco = None
                C._diario({"riepilogo": f"elenco skill: {e}"})
            cwswitch, fatto = _riassumi(corpo, esito["testo"], esito["ragionamento"], senza, hermes=hermes,
                                        elenco=elenco)
    except Exception as e:      # K18: lo switch parte comunque
        fatto = f"fallito: {e}"
        C._diario({"riepilogo": fatto})
    try:
        _forse_switch(cwswitch, fatto)
    except Exception as e:
        C._diario({"cw": f"switch non chiesto: {e}"})


def _promuovi():
    """Prima richiesta della chat dopo una dormita (flag di dormi-esegui.sh): le righe della sessione chiusa
    diventano il blocco, riepilogo.kv (parte fissa + blocco gia' in cache) diventa la chat nuova e il riepilogo
    riparte da una CW vuota. Solo dentro _cw_lock."""
    if not RIEPILOGO_PROMUOVI.exists():
        return
    st = _riepilogo_carica()
    # revisione del blocco B, punto 1: un secondo switch prima di righe nuove tiene il blocco appena promosso
    blocco = _nel_tetto(st["nuovi"]) if st["nuovi"] else st["blocco"]
    if st["nuovi"] and len(blocco) < len(st["nuovi"]):
        C._diario({"riepilogo": f"oltre il tetto: tolte {len(st['nuovi']) - len(blocco)} righe vecchie"})
    _riepilogo_salva({"blocco": blocco, "nuovi": []})
    RIEPILOGO_LOG.write_text("", encoding="utf-8")   # la sessione nuova riparte da un log vuoto
    RIEPILOGO_PROMUOVI.unlink()
    S._tok_cw["chat"] = 0     # il conteggio della chat vecchia non deve chiedere un altro switch
    _switch.update(motivo=None, chiesto=0.0)
    kv = CA.KV_RAM / RIEPILOGO_KV
    fs = {"chat": None, "riepilogo": None, "elenco": None}   # R6: la chat nuova ha la parte fissa di riepilogo.kv
    if kv.exists():
        if S._cw[0] in S.KV_FLUSSO and S._cw[0] != "chat":
            if S._cw[0] == "pensatoio":
                CA._interrompi_pensatoio()
            CA._slot("save", S.KV_FLUSSO[S._cw[0]])
        if CA._slot("restore", RIEPILOGO_KV):
            fs["chat"] = _fissa_carica()["riepilogo"]
        CA._cambia_cw("chat")
    _fissa_salva(fs)
    _elenco_ok[0], _fissa_avvisata[0] = None, False
    for f in (kv, CA.KV_RAM / (RIEPILOGO_KV + ".ckpt")):
        f.unlink(missing_ok=True)
    C._diario({"riepilogo": f"dormita: {len(blocco)} righe nel blocco della chat nuova"})
