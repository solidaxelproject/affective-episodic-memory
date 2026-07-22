#!/usr/bin/env python3
# Omeostato emotivo dell'agente: stato 51-dim persistente con ritorno eutimico.
# Ritorno tipo Ornstein-Uhlenbeck: attrazione verso la baseline proporzionale
# alla distanza + rumore -> graduale, dinamico, NON deterministico (spec il progetto).
# Solo libreria standard: usabile dal container.
import json
import math
import random
import time
from pathlib import Path

FILE = Path(__file__).parent / "stato-emotivo.json"
CONF = Path(__file__).parent / "eutimia.json"

# baseline eutimica di default: quiete vigile e aperta, non piattezza.
DEFAULT_BASELINE = {"serenity": 0.6, "interest": 0.5, "trust": 0.4,
                    "curiosity": 0.4, "acceptance": 0.3}
DEFAULT_CONF = {
    "theta_ora": 0.35,   # forza di richiamo verso la baseline (per ora di tempo)
    "sigma": 0.06,       # rumore del ritorno (non-determinismo)
    "impronta": 0.25,    # quanto un richiamo sposta lo stato
    "impronta_sem": 0.08,  # richiami SEMANTICI: vettori emotivi depotenziati
                           # (progetto 22/07: vicinanza di significato != risonanza
                           # emotiva, l'impronta piena drogava lo stato)
    "tetto": 3.5,        # |z| massimo per dimensione (anti-runaway)
    "baseline": DEFAULT_BASELINE,
}


def _conf():
    if CONF.exists():
        return json.load(open(CONF))
    json.dump(DEFAULT_CONF, open(CONF, "w"), ensure_ascii=False, indent=1)
    return DEFAULT_CONF


def carica(emos=None):
    """Stato attuale, con ritorno eutimico applicato per il tempo trascorso."""
    conf = _conf()
    if FILE.exists():
        d = json.load(open(FILE))
    else:
        if emos is None:
            return None
        d = {"ts": time.time(), "stato": {e: 0.0 for e in emos}}
    ore = max(0.0, (time.time() - d["ts"]) / 3600)
    base = conf["baseline"]
    k = 1 - math.exp(-conf["theta_ora"] * ore)  # frazione di ritorno compiuta
    rumore = conf["sigma"] * math.sqrt(min(ore, 24))
    for e in d["stato"]:
        mu = base.get(e, 0.0)
        d["stato"][e] += k * (mu - d["stato"][e]) + random.gauss(0, rumore)
        d["stato"][e] = max(-conf["tetto"], min(conf["tetto"], d["stato"][e]))
    d["ts"] = time.time()
    json.dump(d, open(FILE, "w"), ensure_ascii=False, indent=1)
    return d["stato"]


def imprimi(firme, semantico=False):
    """Un richiamo (o la giornata) imprime lo stato: media delle firme,
    pesata da conf['impronta']. firme: lista di dict {emo: z}.
    semantico=True: il ricordo è arrivato per significato, non per risonanza
    emotiva -> impronta depotenziata (conf['impronta_sem'])."""
    if not firme:
        return
    conf = _conf()
    peso = conf.get("impronta_sem", 0.08) if semantico else conf["impronta"]
    stato = carica(emos=list(firme[0]))
    n = len(firme)
    for e in stato:
        media = sum(f.get(e, 0.0) for f in firme) / n
        stato[e] += peso * (media - stato[e])
        stato[e] = max(-conf["tetto"], min(conf["tetto"], stato[e]))
    json.dump({"ts": time.time(), "stato": stato}, open(FILE, "w"),
              ensure_ascii=False, indent=1)
    return stato


def gate():
    """Controllo omeostatico pre-risveglio (chiesto dall'agente, 11/07):
    'via-libera' se lo stato è vicino all'eutimia, 'calibrazione' se è
    scosso (fare SOLO un richiamo di serenity/trust e fermarsi),
    'salta' se un'emozione sta girando alta (rimandare il ciclo)."""
    conf = _conf()
    stato = carica()
    if stato is None:
        return "via-libera", "stato non inizializzato: prima volta"
    base = conf["baseline"]
    dev = max(abs(stato[e] - base.get(e, 0.0)) for e in stato)
    s_cal = conf.get("gate_calibrazione", 1.5)
    s_salta = conf.get("gate_salto", 2.5)
    picco = max(stato, key=lambda e: abs(stato[e] - base.get(e, 0.0)))
    if dev >= s_salta:
        return "salta", f"{picco} a {stato[picco]:+.2f}: motore alto, rimanda"
    if dev >= s_cal:
        return "calibrazione", f"{picco} a {stato[picco]:+.2f}: solo un richiamo di serenity o trust, poi stop"
    return "via-libera", f"stato stabile (deviazione max {dev:.2f})"


def descrivi(k=4):
    """Le k emozioni più attive dello stato corrente, leggibili."""
    stato = carica()
    if stato is None:
        return "stato non ancora inizializzato"
    top = sorted(stato, key=lambda e: -stato[e])[:k]
    return ", ".join(f"{e} {stato[e]:+.2f}" for e in top)


if __name__ == "__main__":
    import sys
    if "--imprimi-test" in sys.argv:  # self-check
        FILE.unlink(missing_ok=True)
        emos = ["joy", "sadness", "serenity", "rage"]
        s1 = imprimi([{e: (3.0 if e == "rage" else 0.0) for e in emos}])
        assert s1["rage"] > 0.5, s1
        # simula il passare del tempo: la rabbia deve rientrare verso 0
        d = json.load(open(FILE))
        d["ts"] -= 12 * 3600
        json.dump(d, open(FILE, "w"))
        s2 = carica()
        assert abs(s2["rage"]) < s1["rage"], (s1["rage"], s2["rage"])
        FILE.unlink()
        print(f"self-check OK: rage {s1['rage']:.2f} -> {s2['rage']:.2f} in 12h simulate")
    elif "--gate" in sys.argv:
        esito, motivo = gate()
        print(f"{esito}: {motivo}")
    else:
        print(descrivi())
