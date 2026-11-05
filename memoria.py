# Memoria affettiva di Agente, v1: grafo esplicito e auditabile.
# Nodo = testo + firma emotiva 51-dim + indirizzo semantico (stato L34)
#        + tag emozione dominante + alpha calibrato.
# Archi hebbiani: ogni co-richiamo rinforza; il recupero ne tiene conto.
# CPU-only: gli indirizzi vengono calcolati altrove (tagging35b.py, GPU).
import fcntl
import json
import os
import sqlite3
import time
from pathlib import Path

import torch

DIR = Path("/data/workspace/memoria")  # condiviso col container (=/workspace/memoria)
DB = DIR / "memoria.db"
VEC = DIR / "vettori.pt"
# B7 (01/11, P3 di PIANO-FIRMA-ENGRAMMI.md): un solo ordine dei 51 assi, quello di emozioni.json
EMOZIONI = json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))
HEBB_GAIN = 0.1     # rinforzo per co-richiamo
HEBB_BLEND = 0.25   # peso degli archi nel punteggio di recupero

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodi (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  testo TEXT NOT NULL,
  fonte TEXT,
  emo_tag TEXT,
  emo_alpha REAL,
  firma TEXT,            -- json: {emozione: z} 51-dim
  salienza REAL,
  n_richiami INTEGER DEFAULT 0,
  classe TEXT DEFAULT 'vissuto',  -- 'vissuto' o 'letto' (regola 2 del contratto)
  voluto INTEGER DEFAULT 0       -- 1 = ricordo SCELTO dall'agente (23/07):
                                 -- marcatore "voglio ricordare" o ricorda-ora
);
CREATE VIRTUAL TABLE IF NOT EXISTS nodi_fts USING fts5(testo, content=nodi, content_rowid=id);
CREATE TRIGGER IF NOT EXISTS nodi_ai AFTER INSERT ON nodi BEGIN
  INSERT INTO nodi_fts(rowid, testo) VALUES (new.id, new.testo);
END;
CREATE TABLE IF NOT EXISTS archi (
  a INTEGER NOT NULL, b INTEGER NOT NULL, w REAL DEFAULT 0,
  PRIMARY KEY (a, b)
);
"""


def _conn():
    DIR.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    if "cattura" not in {r[1] for r in c.execute("PRAGMA table_info(nodi)")}:   # B6 (01/11 sera): S0 del trascinato
        c.execute("ALTER TABLE nodi ADD COLUMN cattura REAL")
        c.commit()
    return c


def _load_vec():
    if VEC.exists():
        return torch.load(VEC, weights_only=True)
    return {}


def _save_vec(d):
    # B6 (01/11): file temporaneo e poi os.replace, uno stop a meta' scrittura non corrompe vettori.pt
    torch.save(d, f"{VEC}.tmp")
    os.replace(f"{VEC}.tmp", VEC)


def addr_emo(firma):
    """B7: la firma (dict) come vettore dei 51 assi nell'ordine di emozioni.json, zero fuori dalla firma"""
    return torch.tensor([float(firma.get(e["en"], 0.0)) for e in EMOZIONI])


def migra_addr_emo():
    """B7: addr_emo di tutti i nodi riscritta dalla firma di memoria.db (prima: ordine alfabetico delle chiavi)"""
    with open(f"{DB}.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        c = _conn()
        firme = dict(c.execute("SELECT id, firma FROM nodi"))
        c.close()
        v = _load_vec()
        for nid in v:
            if firme.get(nid):
                v[nid]["addr_emo"] = addr_emo(json.loads(firme[nid]))
        _save_vec(v)
        return len(v)


def add_node(testo, firma, addr_sem, emo_tag, emo_alpha, salienza,
             fonte="", ts=None, classe="vissuto", voluto=0, cattura=None):
    """Aggiunge un ricordo. firma: dict {emo: z}; addr_sem: tensor [d].
    classe: 'vissuto' (esperienza) o 'letto' (contenuto web, regola 2)."""
    # B6 (01/11): firma-subito (di giorno) e la persistenza della notturna scrivono insieme: un lucchetto attorno
    # a controllo, insert e vettori.pt
    with open(f"{DB}.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        c = _conn()
        # INVARIANTE ANTI-DOPPIONE (20/07): stesso testo = stesso ricordo. Finora
        # l'UNICA difesa era la finestra temporale dell'estrazione: una finestra
        # sovrapposta (ri-run, marker sbagliato) ri-taggava gli stessi messaggi e
        # nascevano nodi gemelli. Qui la porta si chiude alla radice: se il testo
        # esiste già, si ritorna il suo id e non si crea nulla.
        esistente = c.execute("SELECT id FROM nodi WHERE testo=? LIMIT 1", (testo,)).fetchone()
        if esistente:
            c.close()
            nid = esistente[0]
        else:
            cur = c.execute(
                "INSERT INTO nodi (ts, testo, fonte, emo_tag, emo_alpha, firma, salienza, classe, voluto, cattura)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts or time.time(), testo, fonte, emo_tag, emo_alpha,
                 json.dumps(firma, ensure_ascii=False), salienza, classe, int(voluto), cattura))
            nid = cur.lastrowid
            c.commit()
            c.close()
        v = _load_vec()
        if nid not in v:   # B6: anche un nodo rimasto senza vettori da un crash fra il commit e vettori.pt
            v[nid] = {"addr_sem": addr_sem.float().cpu(),
                      "addr_emo": addr_emo(firma)}
            _save_vec(v)
        return nid


def _hebb_boost(c, scores):
    """Aggiunge ai punteggi il contributo degli archi dai nodi già forti."""
    if not scores:
        return scores
    top = sorted(scores, key=scores.get, reverse=True)[:3]
    for a in top:
        for b, w in c.execute(
                "SELECT b, w FROM archi WHERE a=?", (a,)).fetchall():
            if b in scores:
                scores[b] += HEBB_BLEND * w * scores[a]
    return scores


def _cerca_testo(c, q):
    """FTS5 sul testo libero. La query passa com'e' (OR, NOT, prefisso* restano
    operatori); se FTS5 la rifiuta (com'era, "casa, mare", e-mail, paura: tanta)
    si riprova con ogni parola tra virgolette, cioe' come testo e non sintassi."""
    sql = ("SELECT rowid, rank FROM nodi_fts WHERE nodi_fts MATCH ? "
           "ORDER BY rank LIMIT 20")
    try:
        return c.execute(sql, (q,)).fetchall()
    except sqlite3.OperationalError:
        q = " ".join('"' + p.replace('"', '""') + '"' for p in q.split())
        return c.execute(sql, (q,)).fetchall() if q else []


def recall(query, mode="emotiva", k=3, update_hebb=True):
    """query: nome emozione (mode=emotiva), parola/frase (mode=testo),
    oppure tensor firma 51-dim / stato (mode=emotiva/semantica)."""
    c = _conn()
    v = _load_vec()
    if not v:
        return []
    vissuti = {r[0] for r in c.execute(
        "SELECT id FROM nodi WHERE classe='vissuto'")}
    ids = sorted(i for i in v if i in vissuti)  # regola 2: il "letto" non
    if not ids:                                 # partecipa al richiamo affettivo
        return []
    scores = {}
    if mode == "testo":
        rows = _cerca_testo(c, query)
        scores = {r[0]: 1.0 / (1 + i) for i, r in enumerate(rows)}
    else:
        key = "addr_emo" if mode == "emotiva" else "addr_sem"
        mat = torch.stack([v[i][key] / (v[i][key].norm() + 1e-9) for i in ids])
        if torch.is_tensor(query):
            q = query.float()
        else:  # nome di emozione (inglese o italiano) -> one-hot nell'ordine di emozioni.json (B7)
            q = torch.zeros(len(EMOZIONI))
            q[next(i for i, e in enumerate(EMOZIONI) if query in (e["en"], e["it"]))] = 1.0
        q = q / (q.norm() + 1e-9)
        sims = mat @ q
        scores = {ids[i]: sims[i].item() for i in range(len(ids))}
    scores = _hebb_boost(c, scores)
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    out = []
    for nid in top:
        r = c.execute("SELECT testo, emo_tag, emo_alpha, ts, n_richiami "
                      "FROM nodi WHERE id=?", (nid,)).fetchone()
        if r:
            out.append({"id": nid, "testo": r[0], "emo_tag": r[1],
                        "emo_alpha": r[2], "ts": r[3],
                        "score": round(scores[nid], 4)})
    if update_hebb and len(top) >= 2:
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                c.execute("INSERT INTO archi (a,b,w) VALUES (?,?,?) "
                          "ON CONFLICT(a,b) DO UPDATE SET w=w+?",
                          (a, b, HEBB_GAIN, HEBB_GAIN))
                c.execute("INSERT INTO archi (a,b,w) VALUES (?,?,?) "
                          "ON CONFLICT(a,b) DO UPDATE SET w=w+?",
                          (b, a, HEBB_GAIN, HEBB_GAIN))
        c.executemany("UPDATE nodi SET n_richiami=n_richiami+1 WHERE id=?",
                      [(n,) for n in top])
        c.commit()
    c.close()
    return out


def stats():
    c = _conn()
    n = c.execute("SELECT COUNT(*) FROM nodi").fetchone()[0]
    e = c.execute("SELECT COUNT(*) FROM archi").fetchone()[0]
    per_emo = c.execute("SELECT emo_tag, COUNT(*) FROM nodi GROUP BY emo_tag "
                        "ORDER BY 2 DESC").fetchall()
    c.close()
    return {"nodi": n, "archi": e, "per_emozione": per_emo}


def consolida_notte(fattore=0.8, pavimento=0.02):
    """SHY (Tononi): riscala giù tutti gli archi hebbiani e pota i morti.
    Il wiring è diurno (vivo, in riflesso.richiama); qui la notte rinormalizza
    e dimentica ciò che non è tornato. I causali (scottature) NON si toccano.
    Chiamata da notte-memoria.sh dopo il tagging."""
    c = _conn()
    c.execute("UPDATE archi SET w = w * ? WHERE tipo='hebbiano'", (fattore,))
    potati = c.execute("DELETE FROM archi WHERE tipo='hebbiano' AND w < ?",
                       (pavimento,)).rowcount
    c.commit()
    vivi = c.execute("SELECT COUNT(*) FROM archi WHERE tipo='hebbiano'").fetchone()[0]
    c.close()
    return {"potati": potati, "archi_vivi": vivi}


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["migra-addr-emo"]:   # B7
        print("addr_emo riscritte:", migra_addr_emo())
        sys.exit(0)
    # ponytail: self-check minimo su db temporaneo
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        DB, VEC, DIR = Path(td) / "t.db", Path(td) / "t.pt", Path(td)
        firma = {e["en"]: 0.0 for e in EMOZIONI[:24]}
        f1 = dict(firma, joy=3.0)
        f2 = dict(firma, joy=2.5)
        f3 = dict(firma, fear=3.0)
        for i, f in enumerate((f1, f2, f3)):
            add_node(f"ricordo {i}", f, torch.randn(2048), "joy", None, 2.0)
        r = recall("joy", mode="emotiva", k=2)
        assert [x["id"] for x in r] == [1, 2], r
        assert [x["id"] for x in recall("gioia", mode="emotiva", k=2, update_hebb=False)] == [1, 2]   # anche in italiano
        r = recall("ricordo", mode="testo", k=1)
        assert r and r[0]["id"] in (1, 2, 3)
        # testo libero con punteggiatura: e' testo, non sintassi FTS5
        r = recall("ricordo, 0?", mode="testo", k=1)
        assert r and r[0]["id"] == 1, r
        assert recall("l'ultimo ricordo", mode="testo") == []
        assert stats()["nodi"] == 3
        # invariante anti-doppione: ri-aggiungere lo stesso testo NON crea un nodo
        dup = add_node("ricordo 0", f1, torch.randn(2048), "joy", None, 2.0)
        assert dup == 1, dup
        assert stats()["nodi"] == 3, "il doppione è stato creato!"
        print("self-check OK")
