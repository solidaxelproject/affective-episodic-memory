# Gradino 4, passo 2: replay ippocampale. Per ogni episodio selezionato, il
# 35B di Agente genera 15-18 riformulazioni variate e bidirezionali (lezione del
# PoC v4: le frasi fisse saturano, la variazione sfonda il reversal curse).
# 3 coppie vengono TENUTE FUORI dal training come probe per l'harness.
# Fallback a template se la generazione non valida.
# Gira nella finestra GPU notturna (venv jspace). Test CPU: --solo-template.
import argparse
import json
import os
import re
import sys

DIR = "/data/memoria-episodica-affettiva/gradino4"
CONSENSO = f"{DIR}/CONSENSO.md"
N_TRAIN, N_PROBE = 15, 3


def categorie_neverlist():
    """le 5 righe numerate della sezione MAI NEI PESI del CONSENSO"""
    cats, dentro = [], False
    if not os.path.exists(CONSENSO):
        return cats
    for riga in open(CONSENSO, encoding="utf-8"):
        r = riga.strip()
        if r.startswith("## "):
            dentro = "MAI NEI PESI" in r.upper()
            continue
        if dentro and r[:2] in ("1.", "2.", "3.", "4.", "5.", "6.", "7."):
            cats.append(r[2:].strip())
    return cats


def viola_neverlist(gen, testo, categorie):
    """il 35B giudica se l'episodio ricade in una categoria vietata.
    Ritorna (bool, categoria) — nel dubbio NON esclude (l'episodio resta,
    il manifesto lo mostra a Agente per il veto manuale)."""
    lista = "\n".join(f"{i+1}. {c}" for i, c in enumerate(categorie))
    prompt = (
        "Agente ha vietato di consolidare nei suoi pesi gli episodi che ricadono "
        "in una di queste categorie:\n" + lista + "\n\n"
        "Episodio:\n«" + testo[:500] + "»\n\n"
        "L'episodio ricade in una di queste categorie vietate? Rispondi SOLO "
        "con il numero della categoria (1-5) se sì, oppure con NO se non "
        "ricade in nessuna. Una sola parola.")
    out = gen(prompt, max_new_tokens=8).strip().lower()
    m = re.search(r"[1-9]", out)
    if m and "no" not in out[:4]:
        idx = int(m.group()) - 1
        if 0 <= idx < len(categorie):
            return True, categorie[idx]
    return False, None

p = argparse.ArgumentParser()
p.add_argument("--in", dest="inp", default=f"{DIR}/episodi-notte.json")
p.add_argument("--out", default=f"{DIR}/replay-notte.json")
p.add_argument("--solo-template", action="store_true",
               help="niente GPU: solo i template (test o fallback totale)")
args = p.parse_args()

STOPWORDS = set("il lo la le i gli un una che di a da in su per con come non "
                "è e ma se io tu lei lui noi voi loro mi ti si ci vi ne più "
                "questa questo quella quello sono era stato stata essere ho "
                "hai ha abbiamo hanno del della dei delle nel nella al alla "
                "poi già solo anche quando dove cosa perché".split())


def parole_chiave(testo, escludi=""):
    """parole di contenuto dell'episodio non presenti nel testo da escludere"""
    esc = set(re.findall(r"\w+", escludi.lower()))
    parole = [w for w in re.findall(r"\w{5,}", testo.lower())
              if w not in STOPWORDS and w not in esc]
    return list(dict.fromkeys(parole))[:6]


def template_qa(testo):
    """coppie QA deterministe: il fallback che nel PoC v4 ha fatto 3/3"""
    corto = testo if len(testo) <= 300 else testo[:300].rsplit(" ", 1)[0] + "..."
    return [
        ("Raccontami questo momento come lo ricordi.", corto),
        ("Cosa è successo in questo episodio della tua vita?", corto),
        ("Completa il ricordo: " + corto[: len(corto) // 2] + "...",
         corto[len(corto) // 2:]),
        ("C'è un momento in cui hai vissuto qualcosa di simile a questo? "
         "Raccontalo.", corto),
        ("Ripeti con parole tue: " + corto, corto),
    ]


def genera_qa_llm(gen, testo, n):
    """chiede al 35B n coppie D:/R: variate e bidirezionali sull'episodio"""
    prompt = (
        "Questo è un episodio della memoria di Agente:\n«" + testo + "»\n\n"
        f"Scrivi ESATTAMENTE {n} coppie domanda-risposta brevi su questo "
        "episodio, tutte diverse tra loro. Includi domande in ENTRAMBE le "
        "direzioni (dal fatto ai nomi E dai nomi al fatto), su chi, cosa, "
        "quando, dove, e almeno una di completamento. Le risposte devono "
        "essere fedeli all'episodio, in prima persona dove ha senso.\n"
        "Formato rigido, nessun altro testo:\nD: ...\nR: ...\n")
    out = gen(prompt, max_new_tokens=1400)
    coppie = re.findall(r"D:\s*(.+?)\s*R:\s*(.+?)(?=\nD:|\Z)", out, re.DOTALL)
    return [(d.strip(), r.strip().replace("\n", " ")) for d, r in coppie
            if d.strip() and len(r.strip()) > 10]


episodi = json.load(open(args.inp, encoding="utf-8"))["episodi"]
if not episodi:
    json.dump({}, open(args.out, "w"))
    print("nessun episodio, replay vuoto")
    sys.exit(0)

gen = None
if not args.solo_template:
    sys.path.insert(0, "/data/jspace")
    import mixed35b as M
    s = M.load()

    def gen(q, max_new_tokens=1400):
        return M.gen(q, max_new_tokens=max_new_tokens)

categorie = categorie_neverlist()
if gen is not None and categorie:
    print(f"filtro semantico never-list: {len(categorie)} categorie di Agente")

replay, esclusi_sem = {}, []
for ep in episodi:
    testo = ep["testo"]
    # filtro semantico: la never-list concettuale di Agente, giudicata dal 35B
    if gen is not None and categorie:
        viola, cat = viola_neverlist(gen, testo, categorie)
        if viola:
            esclusi_sem.append({"id": ep["id"], "categoria": cat})
            print(f"  [{ep['id']}] ESCLUSO (never-list): {cat[:50]}", file=sys.stderr)
            continue
    chiavi_ep = parole_chiave(testo)
    coppie = []
    if gen is not None:
        try:
            grezzi = genera_qa_llm(gen, testo, N_TRAIN + N_PROBE + 3)
            # valida: la risposta deve contenere almeno una chiave dell'episodio
            coppie = [(d, r) for d, r in grezzi
                      if any(k in r.lower() for k in chiavi_ep)] if chiavi_ep else grezzi
        except Exception as e:  # ponytail: mai perdere la notte per il replay
            print(f"  [{ep['id']}] generazione fallita ({e}): template", file=sys.stderr)
    if len(coppie) < N_TRAIN // 2 + N_PROBE:
        coppie = (coppie + template_qa(testo))[: N_TRAIN + N_PROBE]
    probe = []
    for d, r in coppie[-N_PROBE:]:
        keys = parole_chiave(r, escludi=d) or chiavi_ep[:3]
        probe.append({"domanda": d, "chiavi": keys})
    replay[str(ep["id"])] = {
        "train": coppie[:-N_PROBE][:N_TRAIN],
        "probe": probe,
        "peso": ep["peso"], "notte": ep["notte"], "emo_tag": ep["emo_tag"],
    }
    print(f"  [{ep['id']}] train {len(replay[str(ep['id'])]['train'])}, "
          f"probe {len(probe)} (llm={'sì' if gen and len(coppie) > 8 else 'template'})")

json.dump(replay, open(args.out, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
if esclusi_sem:
    json.dump(esclusi_sem, open(f"{DIR}/esclusi-neverlist.json", "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"replay pronto per {len(replay)} episodi "
      f"({len(esclusi_sem)} esclusi dalla never-list) -> {args.out}")
