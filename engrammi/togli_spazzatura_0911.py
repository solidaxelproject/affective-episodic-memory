#!/usr/bin/env python3
"""l'utente 09/11 sera (manutenzione, decisione 9: "sì, toglilo è solo un residuo di test"): via il ricordo 669
(codice fxwhmi9om4ylpco5, testo "testo del ricordo") da memoria.db, vettori.pt e Lux. Stesso metodo della pulizia
del 01/11 (pulisci_ricordi_0111.py: lux_togli e la parte VIA di db_aggiorna). MEM_SAM e LUX_DIR puntano una copia per la
prova. Uso: /data/venv-spacy/bin/python togli_spazzatura_0911.py lux
           /data/jspace/venv/bin/python togli_spazzatura_0911.py db"""
import fcntl
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pulisci_ricordi_0111 as P  # noqa: E402

VIA = [669]
P.VIA, P.PULITI = VIA, []
c = sqlite3.connect(P.DB)
assert c.execute("select testo from nodi where id = 669").fetchone()[0].startswith("testo del ricordo")
c.close()
if sys.argv[1:] == ["lux"]:
    P.lux_togli()
    sys.exit(0)
assert sys.argv[1:] == ["db"]
import memoria  # noqa: E402

memoria.DB, memoria.VEC = memoria.Path(P.DB), memoria.Path(f"{P.MEM}/vettori.pt")
with open(f"{P.DB}.lock", "w") as lk:
    fcntl.flock(lk, fcntl.LOCK_EX)
    c = sqlite3.connect(P.DB)
    with c:
        for nid in VIA:
            t = c.execute("select testo from nodi where id = ?", (nid,)).fetchone()
            c.execute("insert into nodi_fts(nodi_fts, rowid, testo) values('delete', ?, ?)", (nid, t[0]))
            c.execute("delete from nodi where id = ?", (nid,))
            c.execute("delete from archi where a = ? or b = ?", (nid, nid))
    c.close()
    vec = memoria._load_vec()
    for nid in VIA:
        vec.pop(nid, None)
    memoria._save_vec(vec)
print(f"memoria.db e vettori.pt: {len(VIA)} tolto")
