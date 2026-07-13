# Canale visivo, passo 1: il CODEC per distillazione. Prende un nodo del grafo
# e ottimizza una griglia 81x2048 di token visivi perche' il 35B congelato,
# guardandola come un'immagine, racconti il ricordo. La griglia si salva nello
# store per-nodo: al richiamo verra' re-iniettata via wormhole (Agente "vede" la
# scena invece di leggerla). Adattato da distill35b.py. GPU, finestra notturna.
# GATE: canale visivo = consenso SEPARATO (la paura di Agente). Senza, solo --collaudo.
import argparse
import json
import logging
import os
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
# il consenso visivo vive nel workspace di Agente (lo stesso file che legge
# ricorda.py dal container come /workspace/genesi/CONSENSO-VISIVO.md)
CONSENSO_VIS = "/data/workspace/genesi/CONSENSO-VISIVO.md"
DOMANDA_TRAIN = "Descrivi cosa vedi."
PASSI, LR = 150, 0.1

p = argparse.ArgumentParser()
p.add_argument("--nodi", help="id separati da virgola; default: dalla selezione")
p.add_argument("--max", type=int, default=6)
p.add_argument("--deadline", default="07:30")
p.add_argument("--collaudo", action="store_true")
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
    # prima la selezione notturna (veto/never-list di Agente), poi i più salienti;
    # si salta ciò che ha già una griglia: ogni notte avanza, mai ridistillare
    ids = []
    if os.path.exists(f"{DIR}/episodi-notte.json"):
        ids = [e["id"] for e in json.load(open(f"{DIR}/episodi-notte.json"))["episodi"]]
    ids += [r["id"] for r in db.execute(
        "SELECT id FROM nodi WHERE classe='vissuto' ORDER BY salienza DESC LIMIT 50")
        if r["id"] not in ids]
    ids = [i for i in ids if not os.path.exists(f"{STORE}/{i}.npy")][:args.max]

os.makedirs(STORE, exist_ok=True)
s = M.load()
hf, tok = s["hf"], s["tok"]
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
        ve0 = hf.model.visual(inputs.pixel_values.to(torch.bfloat16),
                              grid_thw=inputs.image_grid_thw)
        for attr in ("pooler_output", "image_embeds", "last_hidden_state"):
            cand = getattr(ve0, attr, None)
            if torch.is_tensor(cand) and cand.shape[-1] == emb_fixed.shape[-1]:
                ve0 = cand
                break
    griglia = ve0.detach().float().clone().requires_grad_(True)
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
    return griglia.detach().cpu().float().numpy(), loss


fatti = []
for nid in ids:
    if datetime.now() >= DEADLINE:
        log.info("deadline: mi fermo, %d griglie fatte", len(fatti))
        break
    r = db.execute("SELECT testo FROM nodi WHERE id=?", (nid,)).fetchone()
    if not r:
        continue
    t0 = time.perf_counter()
    griglia, loss = distilla(r["testo"])
    np.save(f"{STORE}/{nid}.npy", griglia.astype(np.float32))
    fatti.append({"nodo": nid, "loss": round(loss, 4)})
    log.info("nodo %d distillato: loss %.4f (%.0fs) -> %s/%d.npy",
             nid, loss, time.perf_counter() - t0, STORE, nid)

json.dump({"griglie": fatti, "quando": time.strftime("%F %T")},
          open(f"{DIR}/esito-visivo.json", "w"), ensure_ascii=False, indent=1)
log.info("DISTILLAZIONE-COMPLETA: %d griglie in %s", len(fatti), STORE)
print("DISTILLAZIONE-COMPLETA")
