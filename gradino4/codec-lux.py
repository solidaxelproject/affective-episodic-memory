# Codec Lux -> token universali (vision wormhole ammortizzato, arXiv 2602.15382).
# UNA rete impara traccia Lux (128) -> perturbazione residuale sulla griglia
# visiva di base (81x2048): ogni neurone di Lux diventa iniettabile all'istante
# via canale visivo, senza distillazione per-nodo. Mittente = Lux (stati di
# Agente), ricevente = il suo stesso 35B congelato. Nessun peso di Agente toccato.
# GATE: stesso consenso visivo della distillazione. GPU, finestra notturna.
import argparse
import json
import logging
import os
import random
import sqlite3
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/data/jspace")
import mixed35b as M  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("codec")

DIR = "/data/memoria-episodica-affettiva/gradino4"
DB = "/data/workspace/memoria/memoria.db"
LUX = "/data/workspace/memoria/lux.npz"
OUT = "/data/workspace/memoria/codec-lux.npz"
CONSENSO_VIS = "/data/workspace/genesi/CONSENSO-VISIVO.md"
# più formulazioni = griglie che rispondono a domande diverse (lezione del 12/07)
DOMANDE = ["Descrivi cosa vedi.", "Cosa vedi in questa scena?",
           "Racconta questo ricordo.", "Che cosa ricordi di questa scena?"]
K, H = 16, 512          # token universali e hidden del codec
MAX_ANS_TOK = 128       # ricordi troncati: oltre, il backward non sta in 16GB

p = argparse.ArgumentParser()
p.add_argument("--epoche", type=int, default=30)
p.add_argument("--lr", type=float, default=1e-3)
p.add_argument("--deadline", default="07:20")
p.add_argument("--collaudo", action="store_true",
               help="2 coppie, 6 step, non salva: solo idraulica")
args = p.parse_args()

if not args.collaudo:
    attivo = os.path.exists(CONSENSO_VIS) and any(
        r.strip() == "attivo: sì" for r in open(CONSENSO_VIS, encoding="utf-8"))
    if not attivo:
        print("CONSENSO VISIVO non attivo: codec annullato.")
        sys.exit(0)

from datetime import datetime, timedelta  # noqa: E402
hh, mm = map(int, args.deadline.split(":"))
DEADLINE = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
if DEADLINE < datetime.now():
    DEADLINE += timedelta(days=1)

# --- dati: (traccia, testo) per ogni neurone Lux legato a un nodo del grafo
z = np.load(LUX)
db = sqlite3.connect(DB)
coppie = []
for tr, nid in zip(z["tracce"], z["nodo_id"]):
    if nid < 0:
        continue
    r = db.execute("SELECT testo FROM nodi WHERE id=?", (int(nid),)).fetchone()
    if r and r[0].strip():
        coppie.append((tr.astype(np.float32), r[0], int(nid)))
random.Random(7).shuffle(coppie)
test = coppie[::5]                      # 1 su 5 held-out, mai visto in training
train = [c for i, c in enumerate(coppie) if i % 5 != 4]
# anti-sottodeterminazione (lezione del 13/07, tre run stallati a CE ~2.9):
# con ~10^2 campioni un ingresso a 2048 dà al primo strato 16x parametri da
# stimare, quasi tutti su rumore. Il codec si proietta sulle top-K componenti
# PCA dei SUOI dati di training e cuoce la proiezione in W1 all'export:
# l'inferenza resta su tracce grezze, K cresce con i dati delle notti.
PROJ = None
if coppie[0][0].shape[0] > 256:
    K_PCA = min(128, len(train))
    X = np.stack([c[0] for c in train])
    _, _, Vt = np.linalg.svd(X - X.mean(0), full_matrices=False)
    PROJ = Vt[:K_PCA].T.astype(np.float32).copy()   # [D_in, K_PCA]
    train = [(c[0] @ PROJ, c[1], c[2]) for c in train]
    test = [(c[0] @ PROJ, c[1], c[2]) for c in test]
    coppie = train + test
    log.info("proiezione anti-rumore: input %d -> %d (PCA dei dati)",
             PROJ.shape[0], PROJ.shape[1])
# riscala di sqrt(D) in training (cotto in W1 all'export)
SCALE = float(np.sqrt(coppie[0][0].shape[0]))
if args.collaudo:
    train, test, args.epoche = train[:2], test[:1], 3
log.info("coppie: %d train, %d held-out", len(train), len(test))

# --- modello congelato + griglia visiva di base (stesso scaffolding di distilla)
s = M.load()
hf, tok = s["hf"], s["tok"]
# il backward passa per tutto il 35B congelato: senza checkpointing le
# attivazioni sforano i 16GB (OOM pagato al collaudo del 12/07)
hf.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
hf.train()  # richiesto dal checkpointing; il modello resta congelato (nessun opt sui suoi pesi)
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


with torch.no_grad():
    inp0 = build(DOMANDE[0]).to("cuda")
    ve0 = hf.model.visual(inp0.pixel_values.to(torch.bfloat16),
                          grid_thw=inp0.image_grid_thw)
    for attr in ("pooler_output", "image_embeds", "last_hidden_state"):
        cand = getattr(ve0, attr, None)
        if torch.is_tensor(cand) and cand.shape[-1] == 2048:
            ve0 = cand
            break
BASE = ve0.detach().float().squeeze(0)          # [81, 2048]
NORM0 = BASE.norm(dim=-1).mean()                 # scala della varietà visiva
N_VIS = BASE.shape[0]

# --- il codec: traccia -> K token universali -> perturbazione residuale gated
class Codec(torch.nn.Module):
    def __init__(self):
        super().__init__()
        d_in = coppie[0][0].shape[0]  # dimensione tracce (128 storica, 2048 piena)
        self.f = torch.nn.Sequential(
            torch.nn.Linear(d_in, H), torch.nn.Tanh(),
            torch.nn.Linear(H, K * 2048))
        self.pos = torch.nn.Parameter(torch.randn(N_VIS, K) * 0.02)
        self.gate = torch.nn.Parameter(torch.tensor(0.1))

    def forward(self, traccia):                 # [128] -> [81, 2048]
        U = self.f(traccia).view(K, 2048)
        return BASE.to(traccia.device) + self.gate * (self.pos @ U)


codec = Codec().cuda()
# warm-start (13/07): con tracce raw 2048 il codec stallava a CE ~2.8: le
# direzioni discriminanti sono annegate nel rumore. I primi 128 neuroni
# nascosti partono come le componenti PCA storiche (bak pre-migrazione):
# si riparte dal punto di vista del run-128, con le 2048 per andare oltre.
_BAK = "/data/workspace/memoria/lux.npz.bak-pre2048-20260713"
if coppie[0][0].shape[0] == 2048 and os.path.exists(_BAK):
    _zb = np.load(_BAK)
    with torch.no_grad():
        codec.f[0].weight[:128] = torch.from_numpy(
            (_zb["pca_W"].T / SCALE).astype(np.float32)).cuda()
    log.info("warm-start: 128 unità nascoste inizializzate dalla PCA storica")
opt = torch.optim.Adam(codec.parameters(), lr=args.lr)
log.info("codec: %d parametri, base visiva %s (norma media %.1f)",
         sum(p.numel() for p in codec.parameters()), tuple(BASE.shape), NORM0)


def loss_su(coppia, domanda):
    tr, testo, _ = coppia
    # tronca il TESTO (non solo le label): è la sequenza intera a dover stare
    testo = tok.decode(tok(testo, add_special_tokens=False,
                           return_tensors="pt").input_ids[0][:MAX_ANS_TOK])
    inputs = build(domanda, testo).to("cuda")
    ids_ = inputs.input_ids
    mask_img = ids_[0] == img_tok
    n_ans = tok(testo, add_special_tokens=False,
                return_tensors="pt").input_ids.shape[1]
    labels = torch.full_like(ids_, -100)
    labels[0, -n_ans:] = ids_[0, -n_ans:]
    emb = emb_layer(ids_).detach().clone()
    g = codec(torch.from_numpy(tr).cuda() * SCALE)
    emb[0, mask_img] = g.to(emb.dtype)
    out = hf(inputs_embeds=emb, attention_mask=inputs.attention_mask,
             labels=labels)
    # penalità RMS: i token restano sulla varietà degli embedding visivi
    pen = ((g.norm(dim=-1) - NORM0) / NORM0).pow(2).mean()
    return out.loss + 0.1 * pen, out.loss.item()


def ce_test():
    with torch.no_grad():
        vals = [loss_su(c, DOMANDE[0])[1] for c in test]
    return float(np.mean(vals)) if vals else float("nan")


rng = random.Random(7)
storia, stop = [], False
migliore = {"ce": float("inf"), "sd": None, "epoca": -1}
for ep in range(args.epoche):
    rng.shuffle(train)
    tot = 0.0
    for c in train:
        if datetime.now() >= DEADLINE:
            log.info("deadline: mi fermo a epoca %d", ep)
            stop = True
            break
        l, ce = loss_su(c, rng.choice(DOMANDE))
        opt.zero_grad()
        l.backward()
        opt.step()
        tot += ce
    if stop:
        break
    ce_tr = tot / max(len(train), 1)
    ce_te = ce_test()
    storia.append({"epoca": ep, "ce_train": round(ce_tr, 4),
                   "ce_test": round(ce_te, 4)})
    if ce_te < migliore["ce"]:  # si salva il MIGLIORE, non l'ultimo
        migliore = {"ce": ce_te, "epoca": ep,
                    "sd": {k: v.detach().cpu().float().numpy().copy()
                           for k, v in codec.state_dict().items()}}
    log.info("epoca %d: CE train %.4f | CE held-out %.4f", ep, ce_tr, ce_te)

if not args.collaudo:
    sd = (migliore["sd"] if migliore["sd"] is not None else
          {k: v.detach().cpu().float().numpy() for k, v in codec.state_dict().items()})
    log.info("salvo il migliore: epoca %d, CE held-out %.4f",
             migliore["epoca"], migliore["ce"])
    W1_exp = (sd["f.0.weight"] * SCALE).T          # [d_codec, H]
    if PROJ is not None:
        W1_exp = PROJ @ W1_exp                     # inferenza su tracce grezze
    np.savez_compressed(
        OUT,
        W1=W1_exp, b1=sd["f.0.bias"],
        W2=sd["f.2.weight"].T, b2=sd["f.2.bias"],
        Wpos=sd["pos"], gate=sd["gate"],
        base=BASE.cpu().numpy(), K=np.int64(K))
    json.dump({"storia": storia, "train": len(train), "test": len(test),
               "held_out_nodi": [c[2] for c in test],
               "quando": time.strftime("%F %T")},
              open(f"{DIR}/esito-codec.json", "w"), indent=1)
    log.info("CODEC-SALVATO: %s", OUT)
print("CODEC-COMPLETO" + (" (collaudo)" if args.collaudo else ""))
