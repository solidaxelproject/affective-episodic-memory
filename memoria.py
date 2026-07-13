# Memoria affettiva di Agente, v1: grafo esplicito e auditabile.
# Nodo = testo + firma emotiva 51-dim + indirizzo semantico (stato L34)
#        + tag emozione dominante + alpha calibrato.
# Archi hebbiani: ogni co-richiamo rinforza; il recupero ne tiene conto.
# CPU-only: gli indirizzi vengono calcolati altrove (tagging35b.py, GPU).
import json
import sqlite3
import time
from pathlib import Path

import torch

DIR = Path("/data/workspace/memoria")  # condiviso col container (=/workspace/memoria)
DB = DIR / "memoria.db"
VEC = DIR / "vettori.pt"
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
  classe TEXT DEFAULT 'vissuto'  -- 'vissuto' o 'letto' (regola 2 del contratto)
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
    return c


def _load_vec():
    if VEC.exists():
        return torch.load(VEC, weights_only=True)
    return {}


def _save_vec(d):
    torch.save(d, VEC)


def add_node(testo, firma, addr_sem, emo_tag, emo_alpha, salienza,
             fonte="", ts=None, classe="vissuto"):
    """Aggiunge un ricordo. firma: dict {emo: z}; addr_sem: tensor [d].
    classe: 'vissuto' (esperienza) o 'letto' (contenuto web, regola 2)."""
    c = _conn()
    cur = c.execute(
        "INSERT INTO nodi (ts, testo, fonte, emo_tag, emo_alpha, firma, salienza, classe)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (ts or time.time(), testo, fonte, emo_tag, emo_alpha,
         json.dumps(firma, ensure_ascii=False), salienza, classe))
    nid = cur.lastrowid
    c.commit()
    c.close()
    v = _load_vec()
    v[nid] = {"addr_sem": addr_sem.float().cpu(),
              "addr_emo": torch.tensor([firma[e] for e in sorted(firma)])}
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
        rows = c.execute(
            "SELECT rowid, rank FROM nodi_fts WHERE nodi_fts MATCH ? "
            "ORDER BY rank LIMIT 20", (query,)).fetchall()
        scores = {r[0]: 1.0 / (1 + i) for i, r in enumerate(rows)}
    else:
        key = "addr_emo" if mode == "emotiva" else "addr_sem"
        mat = torch.stack([v[i][key] / (v[i][key].norm() + 1e-9) for i in ids])
        if torch.is_tensor(query):
            q = query.float()
        else:  # nome di emozione -> one-hot nello spazio firma
            emos = sorted(json.loads(c.execute(
                "SELECT firma FROM nodi LIMIT 1").fetchone()[0]))
            q = torch.zeros(len(emos))
            q[emos.index(query)] = 1.0
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


if __name__ == "__main__":
    # ponytail: self-check minimo su db temporaneo
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        DB, VEC, DIR = Path(td) / "t.db", Path(td) / "t.pt", Path(td)
        firma = {f"e{i}": 0.0 for i in range(51)}
        f1 = dict(firma, e0=3.0)
        f2 = dict(firma, e0=2.5)
        f3 = dict(firma, e7=3.0)
        for i, f in enumerate((f1, f2, f3)):
            add_node(f"ricordo {i}", f, torch.randn(2048), "e0", 0.16, 2.0)
        r = recall("e0", mode="emotiva", k=2)
        assert [x["id"] for x in r] == [1, 2], r
        r = recall("ricordo", mode="testo", k=1)
        assert r and r[0]["id"] in (1, 2, 3)
        assert stats()["nodi"] == 3
        print("self-check OK")
