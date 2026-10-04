#!/usr/bin/env python3
"""
EAR, pagella (piano EAR, EAR-PLAN.md). Venv di jspace, GPU (Occamy), a E8 in pausa.
Sulle 100 clip held-out (20 frasi mai viste x 5 voci emotive):
  - CE di Occamy sul testo vestito "...sto udendo" con la griglia EAR, con la griglia spenta (BASE) e con la
    griglia di un'ALTRA clip (gap = specificita'), come gradino4/valuta-e2e.py;
  - coseno fra par EAR e par dell'insegnante;
  - JEV: emozione scelta fra le 51 contro l'etichetta del WAV (mappa-emozioni.json) e contro emotion2vec, e dose;
  - --gen clip generate (greedy, 256 token) con sim e5-small contro il testo vero (soglia 0.87).
Uso: /data/jspace/venv/bin/python valuta-ear.py --pesi corse/ear-<tag>.pt --tag <tag> [--gen 14]
Esito in ear/corse/esito-valuta-ear-<tag>.json.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/data/jspace"); sys.path.insert(0, "/data/memoria-episodica-affettiva/gradino4"); sys.path.insert(0, "/data/memoria-episodica-affettiva/ear")
import ear_modello as E  # noqa: E402
from testa_nuova import Testa  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--pesi", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--gen", type=int, default=14)
args = ap.parse_args()

EAR, G4 = "/data/memoria-episodica-affettiva/ear", "/data/memoria-episodica-affettiva/gradino4"
FRASE, MAX_ANS_TOK, MAX_NEW = "...sto udendo", 256, 256
ENCODER, SOGLIA_SENSO = "intfloat/multilingual-e5-small", 0.87
ESITO_F = f"{EAR}/corse/esito-valuta-ear-{args.tag}.json"
import subprocess  # noqa: E402
if subprocess.run(["systemctl", "--user", "is-active", "addestra-e2e"], capture_output=True, text=True).stdout.strip() == "active":
    print("addestra-e2e (E8) e' ATTIVA: non parto."); sys.exit(1)

# --- modello EAR: struttura dall'insegnante, pesi dalla corsa
pe = torch.load(args.pesi, map_location="cpu", weights_only=False)
ins = torch.load(pe["insegnante"], map_location="cpu", weights_only=False)
e = ins["esito"]
from transformers import AutoModel, AutoTokenizer  # noqa: E402
lettore = AutoModel.from_pretrained(e["lettore"])
K = int(pe["K"])
model = E.CodecEAR(lettore, Testa(lettore.config.hidden_size, K, e["h"], e["strati"], e["teste"], e["dropout"]), K)
del lettore
model.load_state_dict(pe["stato"]); model = model.cuda().eval()
mu, sd = pe["mu"].float().cuda(), pe["sd"].float().cuda()
nomi, ancore, centro, bordo = E.carica_ancore("cuda")
mappa = json.load(open(E.MAPPA))

clip = [json.loads(r) for r in open(f"{EAR}/dati/manifest-emotivi.jsonl")]
held = [c for c in clip if c["split"] == "held"]
prob = {}
for r in open(f"{EAR}/cache/e2v-prob.jsonl"):
    d = json.loads(r); prob[d["id"]] = d["prob"]
trasc = E.carica_trascrizioni(f"{EAR}/cache/asr-testo.jsonl")     # l'ASR entra come testo
tok_l = AutoTokenizer.from_pretrained(e["lettore"])
pars, scelte = {}, {}
with torch.no_grad():
    for c in held:
        feats = {n: torch.from_numpy(np.load(f"{EAR}/cache/{n}/{c['id']}.npy").astype(np.float32)).unsqueeze(0).cuda() for n in E.INGRESSI}
        masks = {n: torch.ones(1, feats[n].shape[1], dtype=torch.long, device="cuda") for n in E.INGRESSI}
        p, j = model(*E.testo_e5(tok_l, [trasc[c["id"]]], "cuda"), feats, masks)
        pars[c["id"]] = (p[0] * sd + mu).view(K, 2048)
        scelte[c["id"]] = E.scegli(j[0], ancore, centro, bordo)

tok_e = AutoTokenizer.from_pretrained(ENCODER); enc = AutoModel.from_pretrained(ENCODER).eval()
def embed(t):
    inp = tok_e(["passage: " + t], truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        h = enc(**inp).last_hidden_state
    m = inp.attention_mask.unsqueeze(-1)
    return torch.nn.functional.normalize((h * m).sum(1) / m.sum(1), dim=-1)[0].numpy()

import mixed35b as M  # noqa: E402
import transformers  # noqa: E402
from PIL import Image  # noqa: E402
s = M.load(); hf, tok = s["hf"], s["tok"]; hf.eval()
proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID)
dummy = Image.new("RGB", (280, 280), "gray")
emb_layer = hf.get_input_embeddings(); img_tok = hf.config.image_token_id
ck = np.load(f"{G4}/codec-full-e2e.npz")
BASE = torch.from_numpy(ck["base"]).float().cuda(); POS = torch.from_numpy(ck["Wpos"]).float().cuda()
def build(answer=None):
    msgs = [{"role": "user", "content": [{"type": "image"}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True) + FRASE + "\n" + (answer or "")
    return proc(text=[text], images=[dummy], return_tensors="pt").to("cuda")
def ce_con(griglia, testo):
    tronco = tok.decode(tok(testo, add_special_tokens=False, return_tensors="pt").input_ids[0][:MAX_ANS_TOK])
    inputs = build(tronco)
    n_ans = tok(tronco, add_special_tokens=False, return_tensors="pt").input_ids.shape[1]
    labels = torch.full_like(inputs.input_ids, -100); labels[0, -n_ans:] = inputs.input_ids[0, -n_ans:]
    emb = emb_layer(inputs.input_ids).detach().clone(); emb[0, inputs.input_ids[0] == img_tok] = griglia.to(emb.dtype)
    with torch.no_grad():
        return hf(inputs_embeds=emb, attention_mask=inputs.attention_mask, labels=labels).loss.item()
def genera(griglia):
    inputs = build()
    emb = emb_layer(inputs.input_ids).detach().clone(); emb[0, inputs.input_ids[0] == img_tok] = griglia.to(emb.dtype)
    with torch.no_grad():
        out = hf.generate(inputs_embeds=emb, attention_mask=inputs.attention_mask, max_new_tokens=MAX_NEW, do_sample=False)
    return tok.decode(out[0], skip_special_tokens=True)

righe, t0 = [], time.time()
for n, c in enumerate(held):
    altro = next(x for x in held[n + 1:] + held[:n] if x["chiave_testo"] != c["chiave_testo"])   # un'altra frase
    ins_par = torch.from_numpy(np.load(f"{EAR}/insegnante/{c['chiave_testo']}.npy")).float().cuda()
    i_e, dose = scelte[c["id"]]
    b = E.bersaglio_jev(prob[c["id"]], nomi, ancore, mappa)[1]
    r = {"id": c["id"], "emozione_dataset": c["emozione_dataset"], "trascritto": trasc[c["id"]],
         "ce": ce_con(BASE + POS @ pars[c["id"]], c["testo"]), "ce_spenta": ce_con(BASE, c["testo"]),
         "ce_altro": ce_con(BASE + POS @ pars[altro["id"]], c["testo"]),
         "cos_insegnante": float(torch.nn.functional.cosine_similarity(pars[c["id"]].reshape(-1), ins_par.reshape(-1), dim=0)),
         "jev": nomi[i_e], "dose": round(dose, 4), "jev_e2v": nomi[b] if b >= 0 else None,
         "jev_ok_dataset": nomi[i_e] == mappa["dataset_a_emozione"].get(c["emozione_dataset"])}
    r["gap"] = r["ce_altro"] - r["ce"]
    righe.append(r)
    if (n + 1) % 20 == 0:
        print(f"  {n+1}/{len(held)}: CE {np.mean([x['ce'] for x in righe]):.4f} spenta {np.mean([x['ce_spenta'] for x in righe]):.4f} "
              f"gap {np.mean([x['gap'] for x in righe]):+.4f} ({time.time()-t0:.0f}s)", flush=True)
m = lambda k: float(np.mean([x[k] for x in righe]))  # noqa: E731
jev_e2v = [x["jev"] == x["jev_e2v"] for x in righe if x["jev_e2v"]]
print(f"\nPAGELLA EAR ({len(righe)} clip): CE {m('ce'):.4f} | spenta {m('ce_spenta'):.4f} | gap {m('gap'):+.4f} | "
      f"coseno insegnante {m('cos_insegnante'):.3f}")
print(f"JEV: giusta per l'etichetta del WAV {m('jev_ok_dataset'):.0%}, uguale a emotion2vec "
      f"{np.mean(jev_e2v) if jev_e2v else float('nan'):.0%}")
for em in sorted({x["emozione_dataset"] for x in righe}):
    sub = [x for x in righe if x["emozione_dataset"] == em]
    print(f"  {em}: CE {np.mean([x['ce'] for x in sub]):.4f}, JEV giusta {np.mean([x['jev_ok_dataset'] for x in sub]):.0%}")

casi = []
for c in held[:args.gen]:
    gen = genera(BASE + POS @ pars[c["id"]])
    sim = float(np.dot(embed(gen), embed(c["testo"])))
    casi.append({"id": c["id"], "sim": round(sim, 4), "testo": c["testo"], "generato": gen, "jev": scelte[c["id"]]})
    print(f"\n=== {c['id']} sim {sim:.3f} JEV {nomi[scelte[c['id']][0]]} ===\nVERO: {c['testo']}\nGEN:  {gen}", flush=True)
sopra = sum(x["sim"] > SOGLIA_SENSO for x in casi)
print(f"\nSENSO: {sopra}/{len(casi)} sopra {SOGLIA_SENSO}")
json.dump({"quando": time.strftime("%F %T"), "pesi": args.pesi, "ce": m("ce"), "ce_spenta": m("ce_spenta"), "gap": m("gap"),
           "cos_insegnante": m("cos_insegnante"), "jev_ok_dataset": m("jev_ok_dataset"),
           "jev_uguale_e2v": float(np.mean(jev_e2v)) if jev_e2v else None, "righe": righe, "gen": casi,
           "senso_sopra": int(sopra)}, open(ESITO_F, "w"), indent=1, ensure_ascii=False)
print(f"esito in {ESITO_F}")
