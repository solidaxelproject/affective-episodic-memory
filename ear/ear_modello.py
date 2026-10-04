# EAR: il MODELLO (ponti + codec a 5 ingressi + uscita JEV), condiviso fra addestra-ear.py e valuta-ear.py,
# come gradino4/testa_nuova.py per il codec dei ricordi. Piano: EAR-PLAN.md.
#   ingresso TESTO: la trascrizione di Qwen3-ASR (scelta di progetto: l'ASR si aggancia via testo, non
#     con un ponte neurale) entra nel lettore e5 come il testo di E8 ("passage: ..."), strati 1-11 congelati
#   4 ingressi neurali (ultimo layer di CLAP, MERT, Dasheng, emotion2vec, dalla cache di estrai-ear.py)
#   -> 4 PONTI R(h) = W3 h + W2 GELU(W1 h) + etichetta d'ingresso (outer link di RecursiveMAS, arXiv 2604.25917)
#   -> testo e audio insieme negli strati 12-24 del lettore e5 (inizio della parte scongelata del codec E8)
#   -> testa Perceiver (testa_nuova.Testa, 8 domande) -> USCITA 1: par K x 2048 (griglia = BASE + POS @ par)
#                                                    -> USCITA 2: JEV, vettore 2048 confrontato con 51 ancore
import json

import numpy as np
import torch
from torch import nn

INGRESSI = ["clap", "mert", "dasheng", "e2v"]     # neurali; l'ASR entra come testo
D_ING = {"clap": 768, "mert": 768, "dasheng": 768, "e2v": 768}
MAX_TESTO = 256            # token e5 della trascrizione: 256 + 4 x 64 audio = 512 del lettore
PRIMO_STRATO = 11          # indice 0-based: lo strato 12 di 24 (codec E8: 13 strati scongelati = 12..24)
EMOCVEC = "/data/memoria-episodica-affettiva/emo-cvec-v2.npz"
MAPPA = "/data/memoria-episodica-affettiva/ear/mappa-emozioni.json"


class Ponte(nn.Module):
    """Outer link: ramo lineare (porta lo spazio d -> 1024) + ramo GELU che corregge la differenza.
    L'ingresso arriva standardizzato (mu/sd per modello, buffer salvati col modello)."""

    def __init__(self, d, d_out=1024):
        super().__init__()
        self.W1 = nn.Linear(d, d_out)
        self.W2 = nn.Linear(d_out, d_out)
        self.W3 = nn.Linear(d, d_out, bias=False)
        self.etichetta = nn.Parameter(torch.zeros(d_out))
        self.register_buffer("mu", torch.zeros(d))
        self.register_buffer("sd", torch.ones(d))
        nn.init.zeros_(self.W2.weight); nn.init.zeros_(self.W2.bias)   # all'inizio conta solo il ramo lineare

    def forward(self, h):
        h = (h - self.mu) / self.sd
        return self.W3(h) + self.W2(nn.functional.gelu(self.W1(h))) + self.etichetta


class CodecEAR(nn.Module):
    def __init__(self, lettore, testa, k):
        super().__init__()
        self.config = lettore.config
        self.embeddings = lettore.embeddings                                     # congelati (come in E8)
        self.bassi = nn.ModuleList(list(lettore.encoder.layer)[:PRIMO_STRATO])   # congelati (come in E8)
        self.strati = nn.ModuleList(list(lettore.encoder.layer)[PRIMO_STRATO:])
        self.ponti = nn.ModuleDict({n: Ponte(D_ING[n], lettore.config.hidden_size) for n in INGRESSI})
        self.testa = testa
        self.k = k
        h = testa.query.shape[1]
        self.jev = nn.Sequential(nn.LayerNorm(h), nn.Linear(h, h), nn.GELU(), nn.Linear(h, 2048))

    def train(self, mode=True):
        """la parte congelata del lettore resta sempre in eval (niente dropout sul testo prima dello strato 12)"""
        super().train(mode)
        self.embeddings.eval(); self.bassi.eval()
        return self

    def forward(self, ids, mask_t, feats, masks):
        """ids, mask_t: (B, T_t) token e5 della trascrizione ASR; feats[n]: (B, T_n, d_n), masks[n]: (B, T_n)
        1 = token vero. -> par standardizzato (B, K*2048), jev (B, 2048)"""
        from transformers.masking_utils import create_bidirectional_mask
        with torch.no_grad():                    # parte congelata: il testo fino allo strato 11
            h = self.embeddings(input_ids=ids)
            mt4 = create_bidirectional_mask(config=self.config, inputs_embeds=h, attention_mask=mask_t)
            for s in self.bassi:
                h = s(h, mt4)
        x = torch.cat([h] + [self.ponti[n](feats[n]) for n in INGRESSI], 1)
        m = torch.cat([mask_t] + [masks[n] for n in INGRESSI], 1)
        m4 = create_bidirectional_mask(config=self.config, inputs_embeds=x, attention_mask=m)
        for s in self.strati:
            x = s(x, m4)
        t = self.testa
        q = t.query.unsqueeze(0).expand(x.shape[0], -1, -1)
        z = t.blocco(q, t.adatta(x), memory_key_padding_mask=(m == 0))
        return t.fuori(z).reshape(x.shape[0], -1), self.jev(z.mean(1))


def carica_trascrizioni(path):
    """ear/cache/asr-testo.jsonl -> {id clip: trascrizione}; l'ultima riga per id vince (collaudi ripetuti)."""
    out = {}
    for r in open(path, encoding="utf-8"):
        d = json.loads(r); out[d["id"]] = d["trascritto"]
    return out


def testo_e5(tok, testi, dev="cpu"):
    """trascrizioni -> ids, mask paddati sul lotto, stesso formato del lettore di E8 ("passage: " + testo)."""
    inp = tok(["passage: " + t for t in testi], truncation=True, max_length=MAX_TESTO, padding=True, return_tensors="pt")
    return inp.input_ids.to(dev), inp.attention_mask.to(dev)


def carica_ancore(dev="cpu"):
    """51 ancore JEV: media normalizzata delle 3 direzioni di steering di ogni emozione (Occamy, emo-cvec-v2).
    Ritorna nomi, ancore (51, 2048), centro, bordo (per la dose, stessa scala di ponte.dirs_emozione)."""
    z = np.load(EMOCVEC, allow_pickle=True)
    a = torch.tensor(z["dirs"].mean(1), dtype=torch.float32)
    return [str(n) for n in z["nomi"]], nn.functional.normalize(a, dim=-1).to(dev), z["centro"], z["bordo"]


def bersaglio_jev(prob, nomi, ancore, mappa=None):
    """prob: 9 probabilita' emotion2vec -> (vettore bersaglio 2048 normalizzato o None, indice dell'emozione
    principale fra le 51 o -1). Somma delle ancore delle primarie (all'intensita' data dalla probabilita'),
    pesata con le probabilita'. Neutro/altro/sconosciuto non portano emozione (mappa-emozioni.json)."""
    mappa = mappa or json.load(open(MAPPA))
    s1, s2 = mappa["soglie_intensita"]
    v, top, top_p = torch.zeros(ancore.shape[1]), -1, 0.0
    for cl, p in zip(mappa["e2v_classi"], prob):
        prim = mappa["e2v_a_primaria"].get(cl)
        if not prim or p <= 0:
            continue
        nome = mappa["intensita"][prim][0 if p < s1 else 1 if p < s2 else 2]
        i = nomi.index(nome)
        v = v + p * ancore[i].cpu()
        if p > top_p:
            top, top_p = i, p
    if top < 0:
        return None, -1
    return nn.functional.normalize(v, dim=0), top


def scegli(jev, ancore, centro, bordo):
    """Uscita JEV -> (indice emozione, dose). Dose = coseno riportato fra centro/4 e 0.75*bordo
    (estremi delle dosi di jspace/sweep-visivo.py), quindi sempre dentro la finestra misurata."""
    cos = nn.functional.normalize(jev, dim=-1) @ ancore.T
    i = int(cos.argmax())
    c = float(cos[i].clamp(0, 1))
    lo, hi = float(centro[i]) / 4, 0.75 * float(bordo[i])
    return i, lo + c * (hi - lo)
