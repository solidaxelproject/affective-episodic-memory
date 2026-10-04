#!/usr/bin/env python3
"""
EAR, richiamo dei ricordi dalla TRASCRIZIONE (scelta di progetto): la trascrizione di Qwen3-ASR entra nel
canale MIRATO del riflesso, lo stesso del testo in ingresso: bge-m3 (:8094, CPU) su indice-mirato.npz, domanda
intera + distillata, soglia 0.50, regola del fuoriclasse (top1 < 0.60 senza stacco 0.05 = silenzio), freno 1 ora,
max 3 ricordi con griglia + 2 senza (questi entrano come testo).
Usa il codice di produzione (riflesso.Proxy._cand1_mirato) SENZA copiarlo: soglie e regole cambiano insieme.
Non inietta niente e non tocca il riflesso in corsa: restituisce i ricordi scelti. Vestizione e iniezione restano
del riflesso, da cablare quando EAR andra' in produzione (le frasi si decidono prima).
Il freno anti-ripetizione e' per processo: in produzione la chiamata va fatta DENTRO il riflesso, cosi' il freno
e' lo stesso del testo; da qui (prove) ogni lancio parte col freno vuoto.
Il diario va in ear/diario-richiamo-ear.jsonl, mai in quello del riflesso. Il DB si apre in sola lettura.
Uso (python di sistema, come il riflesso; serve solo l'embedder :8094 acceso):
  python3 richiamo_ear.py "testo trascritto"
  python3 richiamo_ear.py --cache [--held]     # tutte le trascrizioni di cache/asr-testo.jsonl (o solo held-out)
Da codice:  import richiamo_ear; con_griglia, senza_griglia = richiamo_ear.ricordi(trascrizione)
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import riflesso as R  # noqa: E402

EAR = os.path.dirname(os.path.abspath(__file__))
DIARIO_EAR = f"{EAR}/diario-richiamo-ear.jsonl"


def _diario_ear(voce):
    with open(DIARIO_EAR, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "via": "ear", **voce}, ensure_ascii=False) + "\n")


R._diario = _diario_ear          # _cand1_mirato scrive qui, non nel diario del riflesso


def ricordi(trascrizione):
    """trascrizione ASR -> ([(nid, cos)] con griglia, [(nid, cos)] senza griglia). Vuota o troppo corta: niente."""
    t = (trascrizione or "").strip()
    if not t or R.KILL_FRASE in t.lower():
        return [], []
    return R.Proxy._cand1_mirato(None, t)


def _testo_nodo(cdb, nid):
    r = cdb.execute("SELECT testo, emo_tag, ts FROM nodi WHERE id=?", (nid,)).fetchone()
    if not r:
        return "?"
    return f"{time.strftime('%d/%m', time.localtime(r[2]))}, {r[1]}: {' '.join(r[0].split())[:160]}"


def _stampa(cdb, testo, con_g, senza_g):
    print(f"\n» {testo}")
    if not con_g and not senza_g:
        print("   (nessun ricordo)")
    for nid, c in con_g:
        print(f"   griglia {nid} cos {c:.3f}  {_testo_nodo(cdb, nid)}")
    for nid, c in senza_g:
        print(f"   testo   {nid} cos {c:.3f}  {_testo_nodo(cdb, nid)}")


if __name__ == "__main__":
    cdb = sqlite3.connect(f"file:{R.DB}?mode=ro", uri=True)
    if sys.argv[1:2] == ["--cache"]:
        trasc = {}
        for r in open(f"{EAR}/cache/asr-testo.jsonl", encoding="utf-8"):
            d = json.loads(r); trasc[d["id"]] = d["trascritto"]
        if "--held" in sys.argv:
            held = {json.loads(r)["id"] for r in open(f"{EAR}/dati/manifest-emotivi.jsonl") if json.loads(r)["split"] == "held"}
            trasc = {k: v for k, v in trasc.items() if k in held}
        n_con = n_senza = n_vuoti = 0
        for cid, testo in trasc.items():
            con_g, senza_g = ricordi(testo)
            _stampa(cdb, f"{cid}: {testo}", con_g, senza_g)
            n_con += len(con_g); n_senza += len(senza_g); n_vuoti += not (con_g or senza_g)
        print(f"\n{len(trasc)} trascrizioni: {n_con} ricordi con griglia, {n_senza} senza, {n_vuoti} senza nessun ricordo")
    elif sys.argv[1:]:
        testo = " ".join(sys.argv[1:])
        _stampa(cdb, testo, *ricordi(testo))
    else:
        print(__doc__)
