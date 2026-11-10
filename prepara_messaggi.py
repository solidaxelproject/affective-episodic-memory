"""Preparazione dei messaggi e impronta sull'omeostato, senza modello (manutenzione 10/11).
Erano in tagging35b.py, che carica torch, mixed35b e la J-lens: firma_subito e la rifirma ne usano solo queste
funzioni. tagging35b.py le importa da qui."""
import json
import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("tagger")

CTX_MAX = 1200        # caratteri di contesto per la lettura differenziale

ARTEFATTI = ("Cronjob Response:", "⚡ Interrupting", "📚 Reading skill",
             "* 📚", "⚠", "```",
             "[CONTEXT COMPACTION", "Operation interrupted:")   # 01/11: riassunto e interruzioni di Hermes


# ---------- preparazione messaggi (pura, testabile senza GPU) ----------

def pulisci(testo):
    """Via i blocchi di reasoning e gli artefatti di sistema; None = scarta."""
    testo = re.sub(r"💭 \*\*Reasoning:\*\*\s*```.*?```", "", testo,
                   flags=re.DOTALL).strip()
    if not testo or any(testo.startswith(a) for a in ARTEFATTI):
        return None
    return testo


def carica_messaggi(path):
    out = []
    for riga in open(path):
        if not riga.strip():
            continue
        m = json.loads(riga)
        t = pulisci(m["testo"])
        if t and len(t.strip()) >= 15:
            m["testo"] = t.strip()
            out.append(m)
    return out


def dedup(msgs):
    """DECISO DALL'AGENTE il 12/07: stesso incipit nella finestra = una esperienza."""
    visti, uniq = set(), []
    for m in msgs:
        k = (m.get("autore", ""), m["testo"][:200])
        if k not in visti:
            visti.add(k)
            uniq.append(m)
    if len(uniq) < len(msgs):
        log.info("dedup: %d messaggi ripetuti collassati", len(msgs) - len(uniq))
    return uniq


def contesto_di(precedenti):
    """gli ultimi CTX_MAX caratteri della giornata prima di questo messaggio"""
    testo = "\n".join(t for t in precedenti)
    return testo[-CTX_MAX:] if testo else ""


def imprimi_omeostato(firme_salvate):
    """v2: imprimono TUTTI i nodi salvati, forzati compresi (fix del bug v1)"""
    sys.path.insert(0, "/data/workspace/memoria")
    import stato as omeostato
    omeostato.imprimi(firme_salvate)
    log.info("stato impresso dalla giornata: %s", omeostato.descrivi())
