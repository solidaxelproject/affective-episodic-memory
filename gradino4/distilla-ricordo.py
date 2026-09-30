# Canale visivo, passo 1: il CODEC per distillazione. Prende un nodo del grafo
# e ottimizza una griglia 81x2048 di token visivi perche' il 35B congelato,
# guardandola come un'immagine, racconti il ricordo. La griglia si salva nello
# store per-nodo: al richiamo verra' re-iniettata via wormhole (l'agente "vede" la
# scena invece di leggerla). Adattato da distill35b.py. GPU, finestra notturna.
# GATE: canale visivo = consenso SEPARATO (la paura dell'agente). Senza, solo --collaudo.
import argparse
import difflib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/data/jspace")
import mixed35b as M  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("distilla")

DIR = "/data/memoria-episodica-affettiva/gradino4"
DB = "/data/workspace/memoria/memoria.db"
STORE = "/data/workspace/memoria/griglie"  # <node_id>.npy
# il consenso visivo vive nel workspace dell'agente (lo stesso file che legge
# ricorda.py dal container come /workspace/genesi/CONSENSO-VISIVO.md)
CONSENSO_VIS = "/data/workspace/genesi/CONSENSO-VISIVO.md"
DOMANDA_TRAIN = os.environ.get("DOMANDA_TRAIN", "Questo mi ricorda...")
PASSI, LR = int(os.environ.get("PASSI", "150")), 0.1

p = argparse.ArgumentParser()
p.add_argument("--nodi", help="id separati da virgola; default: dalla selezione")
p.add_argument("--max", type=int, default=6)
p.add_argument("--deadline", default="07:30")
p.add_argument("--collaudo", action="store_true")
p.add_argument("--verifica", action="store_true",
               help="dopo l'addestramento genera il richiamo, confronta col ricordo, "
                    "aggancia la nuova solo se fedele (backup della vecchia). Per la "
                    "ri-campagna con nuova domanda trigger.")
args = p.parse_args()

# gate: riga esatta, non sottostringa (il commento cita "attivo: sì")
if not args.collaudo:
    attivo = os.path.exists(CONSENSO_VIS) and any(
        r.strip() == "attivo: sì" for r in open(CONSENSO_VIS, encoding="utf-8"))
    if not attivo:
        print("CONSENSO VISIVO non attivo: distillazione annullata.")
        sys.exit(0)

from datetime import datetime, timedelta  # noqa: E402
hh, mm = map(int, args.deadline.split(":"))
DEADLINE = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
if DEADLINE < datetime.now():
    DEADLINE += timedelta(days=1)

# --- quali nodi
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
if args.nodi:
    ids = [int(x) for x in args.nodi.split(",")]
else:
    # prima la selezione notturna (veto/never-list dell'agente), poi i ricordi SCELTI
    # dall'agente (voluto=1) davanti ai più salienti; si salta ciò che ha già una
    # griglia: ogni notte avanza, mai ridistillare
    ids = []
    if os.path.exists(f"{DIR}/episodi-notte.json"):
        ids = [e["id"] for e in json.load(open(f"{DIR}/episodi-notte.json"))["episodi"]]
    ids += [r["id"] for r in db.execute(
        "SELECT id FROM nodi WHERE classe='vissuto' ORDER BY voluto DESC, salienza DESC LIMIT 50")
        if r["id"] not in ids]
    ids = [i for i in ids if not os.path.exists(f"{STORE}/{i}.npy")][:args.max]

os.makedirs(STORE, exist_ok=True)
s = M.load()
hf, tok = s["hf"], s["tok"]
# I nodi sono cresciuti (2756 caratteri contro gli 831 dell'ultima griglia
# riuscita) e il backward tiene le attivazioni di tutti i 41 layer: senza
# checkpointing servirebbero decine di GB e va in OOM da tre notti (griglie
# ferme al 14/07). Stessa ricetta di codec-lux.py: il modello resta congelato,
# l'ottimizzatore tocca solo la griglia.
hf.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
hf.train()
import transformers  # noqa: E402
proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID)
from PIL import Image  # noqa: E402
dummy = Image.new("RGB", (280, 280), "gray")
emb_layer = hf.get_input_embeddings()
img_tok = hf.config.image_token_id


def build(question, answer=None):
    msgs = [{"role": "user", "content": [
        {"type": "image"}, {"type": "text", "text": question}]}]
    text = proc.apply_chat_template(msgs, tokenize=False,
                                    add_generation_prompt=True,
                                    enable_thinking=False)
    if answer is not None:
        text = text + answer
    return proc(text=[text], images=[dummy], return_tensors="pt")


def distilla(ricordo):
    inputs = build(DOMANDA_TRAIN, ricordo).to("cuda")
    ids_ = inputs.input_ids
    mask_img = ids_[0] == img_tok
    ans_ids = tok(ricordo, return_tensors="pt").input_ids[0]
    n_ans = ans_ids.shape[0]
    labels = torch.full_like(ids_, -100)
    labels[0, -n_ans:] = ids_[0, -n_ans:]
    emb_fixed = emb_layer(ids_).detach()
    with torch.no_grad():
        hf.model.visual.to("cuda")
        ve0 = hf.model.visual(inputs.pixel_values.to(torch.bfloat16),
                              grid_thw=inputs.image_grid_thw)
        for attr in ("pooler_output", "image_embeds", "last_hidden_state"):
            cand = getattr(ve0, attr, None)
            if torch.is_tensor(cand) and cand.shape[-1] == emb_fixed.shape[-1]:
                ve0 = cand
                break
    griglia = ve0.detach().float().clone().requires_grad_(True)
    # la tower serve solo a inizializzare ve0: i PASSI vanno di inputs_embeds e
    # non la toccano, ma i suoi ~850 MB in VRAM fanno la differenza fra il
    # backward che ci sta e l'OOM per 20 MiB (blackout del 16/07).
    hf.model.visual.to("cpu")
    torch.cuda.empty_cache()
    opt = torch.optim.Adam([griglia], lr=LR)
    loss = None
    for step in range(PASSI):
        emb = emb_fixed.clone()
        emb[0, mask_img] = griglia.to(emb.dtype)
        out = hf(inputs_embeds=emb, attention_mask=inputs.attention_mask, labels=labels)
        opt.zero_grad()
        out.loss.backward()
        opt.step()
        loss = out.loss.item()
        if step % 10 == 0 or step == PASSI - 1:
            log.info("   epoca %3d/%d  loss %.4f", step, PASSI, loss)
        if step % 25 == 0 or step == PASSI - 1:
            # per il visore live (griglia-live.py): la griglia mentre prende forma
            np.save(f"{STORE}/.live-griglia.npy", griglia.detach().cpu().float().numpy())
        if step >= 20 and loss < 0.005:   # early-stop: convergiuta, non sprecare passi
            log.info("   early-stop epoca %d, loss %.4f (salto i passi restanti)", step, loss)
            break
    return griglia.detach().cpu().float().numpy(), loss


def verifica_output(griglia_np, memoria):
    """TEST OUTPUT a ogni griglia (scelta di progetto): un forward, conta quanti
    token del ricordo sono l'argmax delle predizioni. ~1.0 = la generazione
    riprodurrebbe il ricordo fedele. Usa il forward dell'addestramento (che
    funziona): niente hf.generate, niente bug di device."""
    import torch as _t
    inputs = build(DOMANDA_TRAIN, memoria).to("cuda")
    ids_ = inputs.input_ids
    mask_img = (ids_[0] == img_tok)
    n_ans = tok(memoria, return_tensors="pt").input_ids[0].shape[0]
    emb = emb_layer(ids_).detach().clone()
    emb[0, mask_img] = _t.tensor(griglia_np, dtype=emb.dtype, device="cuda")
    with _t.no_grad():
        logits = hf(inputs_embeds=emb, attention_mask=inputs.attention_mask).logits[0]
    pred = logits[-n_ans - 1:-1].argmax(-1)
    true = ids_[0, -n_ans:]
    return (pred == true).float().mean().item()


def genera(griglia_np, question, max_new=140):
    """Richiama: inietta la griglia e genera col modello GIÀ caricato (niente
    llama-server). Serve alla --verifica per il confronto col ricordo vero."""
    import torch as _t
    inputs = build(question).to("cuda")           # senza answer = prompt di generazione
    ids_ = inputs.input_ids
    mask_img = (ids_[0] == img_tok)
    emb = emb_layer(ids_).detach().clone()
    emb[0, mask_img] = _t.tensor(griglia_np, dtype=emb.dtype, device="cuda")
    with _t.no_grad():
        gen = hf.generate(inputs_embeds=emb, attention_mask=inputs.attention_mask,
                          max_new_tokens=max_new, do_sample=False)
    return tok.decode(gen[0], skip_special_tokens=True).strip()


def _norm(s):
    return " ".join(s.split()).lower()


fatti = []
for nid in ids:
    if datetime.now() >= DEADLINE:
        log.info("deadline: mi fermo, %d griglie fatte", len(fatti))
        break
    r = db.execute("SELECT testo FROM nodi WHERE id=?", (nid,)).fetchone()
    if not r:
        continue
    t0 = time.perf_counter()
    if not args.verifica:
        griglia, loss = distilla(r["testo"])
        np.save(f"{STORE}/{nid}.npy", griglia.astype(np.float32))
        fatti.append({"nodo": nid, "loss": round(loss, 4)})
        log.info("nodo %d distillato: loss %.4f (%.0fs) -> %s/%d.npy",
                 nid, loss, time.perf_counter() - t0, STORE, nid)
        continue
    # --- ri-campagna: addestra, aggancia solo se la loss è bassa (la griglia
    # riproduce il ricordo). Il richiamo via HF.generate ha un bug di device sul
    # modello mixed GPU/CPU; il confronto VERO si fa dopo, col 35B su, via ponte.
    memoria = r["testo"]
    old = f"{STORE}/{nid}.npy"
    bak = f"{old}.bak-descrivi"
    if os.path.exists(old) and not os.path.exists(bak):
        shutil.copy(old, bak)                     # backup della vecchia, una volta sola
    griglia, loss = distilla(memoria)             # in memoria, NON ancora salvata
    match = verifica_output(griglia, memoria)     # TEST OUTPUT: token del ricordo che sono argmax
    ok = match >= 0.98                            # >=98% -> la generazione riproduce il ricordo
    if ok:
        np.save(old, griglia.astype(np.float32))  # aggancia la nuova SOLO se l'output è fedele
        stato = "NUOVA agganciata"
    else:
        stato = "nuova SCARTATA (output non fedele), tengo la vecchia"
    fatti.append({"nodo": nid, "loss": round(loss, 4), "match": round(match, 4), "ok": ok})
    log.info("nodo %d: loss %.4f, OUTPUT-match %.1f%%, %.0fs -> %s",
             nid, loss, match * 100, time.perf_counter() - t0, stato)

json.dump({"griglie": fatti, "quando": time.strftime("%F %T")},
          open(f"{DIR}/esito-visivo.json", "w"), ensure_ascii=False, indent=1)
log.info("DISTILLAZIONE-COMPLETA: %d griglie in %s", len(fatti), STORE)
print("DISTILLAZIONE-COMPLETA")
