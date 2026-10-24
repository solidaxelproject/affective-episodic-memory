#!/usr/bin/env python3
"""Passo 2 (solo processore): cosa "dice" ogni vettore letto con la J-lens del paper (readout W_U g J_l v).
Se fra le prime parole c'e' la parola dell'emozione, iniettarlo porta la PAROLA (spazio verbalizzabile del paper)."""
import json
import sys

import numpy as np
import torch
import transformers
from safetensors import safe_open

HF = "/data/jspace/hf/hub/models--Accio-Lab--occamy-1.0/snapshots/72ca96031d8d11650882b5fae8dad88412a76155"
O = "/data/jspace/out-occamy"
tok = transformers.AutoTokenizer.from_pretrained(HF)
J = torch.load(f"{O}/lente35b-18layer.pt", weights_only=False, map_location="cpu")["J"]
with safe_open(f"{HF}/model-00012-of-00013.safetensors", "pt") as f:
    g = 1.0 + f.get_tensor("model.language_model.norm.weight").float()
    W = f.get_tensor("lm_head.weight").float()
V2 = np.load("/data/memoria-episodica-affettiva/emo-cvec-v2.npz")
N2 = [str(n) for n in V2["nomi"]]
fonti = {"diario": torch.load(f"{O}/emovec-it.pt", weights_only=False)["vettori"],
         "paper": torch.load(f"{O}/vettori-paper.pt", weights_only=False)["vettori"],
         "appaiati": torch.load(f"{O}/vettori-appaiati.pt", weights_only=False)["vettori"]}
IT = {x["en"]: x["it"] for x in json.load(open("/data/memoria-episodica-affettiva/emozioni.json"))}
EMO = sys.argv[1:] or ["joy", "sadness", "anger", "fear", "trust", "disgust", "surprise", "serenity"]


def legge(v, l, k=12):
    z = W @ (g * (J[l].float() @ v.float()))
    return [tok.decode([i]).strip() for i in z.topk(k).indices.tolist()]


for e in EMO:
    print(f"\n## {e} ({IT[e]})")
    for l in (21, 24, 29):
        for nome, F in fonti.items():
            print(f"  L{l} {nome:7s}", " | ".join(legge(F[e][l], l)))
        i = N2.index(e)
        if l in V2["layers"][i]:
            print(f"  L{l} v2     ", " | ".join(legge(torch.tensor(V2["dirs"][i, list(V2["layers"][i]).index(l)]), l)))
