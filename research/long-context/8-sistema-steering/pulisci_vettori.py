#!/usr/bin/env python3
"""Vettori appaiati PULITI (21/10, solo processore). Due proiezioni, layer per layer:
1. via la PAROLA (ablazione del paper workspace): le K parole che il vettore "dice" letto con la J-lens
   (readout W_U g J_l v) hanno ognuna il suo J-lens vector a_t = J_l^T (g * W_U[t]); si toglie dal vettore lo spazio
   che generano (base ortonormale, QR). Due giri: dopo il primo affiorano sinonimi e traduzioni.
2. via la LINGUA: direzione italiano -> inglese = media dei J-lens vector di parole funzione inglesi meno quella delle
   italiane (" the", " of"... contro " il", " di"...); il 17% dei punti buoni su C4 passava all'inglese.
Uscite: out-occamy/vettori-appaiati-puliti.pt (solo parola) e vettori-appaiati-puliti-lingua.pt (parola + lingua),
e per ogni emozione: quanta norma resta, cosa dice il vettore dopo, se il lettore delle scene lo riconosce ancora."""
import sys

import numpy as np
import torch
import transformers
from safetensors import safe_open

HF = "/data/jspace/hf/hub/models--Accio-Lab--occamy-1.0/snapshots/72ca96031d8d11650882b5fae8dad88412a76155"
O = "/data/jspace/out-occamy"
D = "/data/memoria-episodica-affettiva/research/long-context/8-sistema-steering"
LAYER = list(range(15, 33))
K, GIRI = 25, 2
EN_F = [" the", " of", " and", " to", " is", " that", " it", " not", " with", " this", " I", " you", " what", " but"]
IT_F = [" il", " di", " e", " a", " è", " che", " lo", " non", " con", " questo", " io", " tu", " cosa", " ma"]

tok = transformers.AutoTokenizer.from_pretrained(HF)
J = torch.load(f"{O}/lente35b-18layer.pt", weights_only=False, map_location="cpu")["J"]
with safe_open(f"{HF}/model-00012-of-00013.safetensors", "pt") as f:
    g = 1.0 + f.get_tensor("model.language_model.norm.weight").float()
    W = f.get_tensor("lm_head.weight").float()
Wg = W * g                                    # righe g * W_U[t]
NOME = sys.argv[1] if len(sys.argv) > 1 else "vettori-appaiati"   # 21/10: anche vettori-se (emozione + sé)
src = torch.load(f"{O}/{NOME}.pt", weights_only=False)
V = src["vettori"]
lettore = np.load(f"{D}/lettore.npz")
EMO = list(V)


def un_token(parole):
    ids = [tok(p, add_special_tokens=False).input_ids for p in parole]
    return [i[0] for i in ids if len(i) == 1]


def dice(v, l, k=8):
    return [tok.decode([i]).strip() for i in (Wg @ (J[l].float() @ v)).topk(k).indices.tolist()]


def via(v, A):
    Q, _ = torch.linalg.qr(A)
    return v - Q @ (Q.T @ v)


lingua = {}
for l in LAYER:
    Jl = J[l].float()
    en = (Jl.T @ Wg[un_token(EN_F)].T).mean(1)
    it = (Jl.T @ Wg[un_token(IT_F)].T).mean(1)
    lingua[l] = (en - it) / (en - it).norm()

puliti, puliti_l = {}, {}
for e in EMO:
    puliti[e], puliti_l[e] = {}, {}
    for l in LAYER:
        v = V[e][l].float()
        w = v.clone()
        for _ in range(GIRI):
            top = (Wg @ (J[l].float() @ w)).topk(K).indices
            w = via(w, J[l].float().T @ Wg[top].T)
        puliti[e][l] = w
        puliti_l[e][l] = via(w, lingua[l][:, None])
    j = LAYER.index(24)
    s = lambda x: x.numpy() @ lettore["W"][j] + lettore["B"][j]
    r_prima = int((s(V[e][24].float()) > s(V[e][24].float())[EMO.index(e)]).sum()) + 1
    r_dopo = int((s(puliti_l[e][24]) > s(puliti_l[e][24])[EMO.index(e)]).sum()) + 1
    print(f"\n## {e}: norma rimasta a L24 {puliti_l[e][24].norm() / V[e][24].float().norm():.2f}, "
          f"lettore delle scene: rango {r_prima} prima, {r_dopo} dopo")
    print("  prima:", " | ".join(dice(V[e][24].float(), 24)))
    print("  dopo: ", " | ".join(dice(puliti_l[e][24], 24)))

meta = {k: v for k, v in src.items() if k != "vettori"}
torch.save({**meta, "vettori": puliti, "pulizia": f"via la parola: {GIRI} giri x {K} J-lens vector"},
           f"{O}/{NOME}-puliti.pt")
torch.save({**meta, "vettori": puliti_l, "pulizia": f"via la parola ({GIRI}x{K}) e la lingua it->en"},
           f"{O}/{NOME}-puliti-lingua.pt")
print(f"\nscritti {NOME}-puliti.pt e {NOME}-puliti-lingua.pt")
