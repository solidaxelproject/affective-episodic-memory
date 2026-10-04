#!/usr/bin/env python3
"""
EAR, fasi 1-2-3 (piano EAR, EAR-PLAN.md). Venv di jspace. Legge la cache di estrai-ear.py
e le griglie dell'insegnante (fase 0, addestra-insegnante-ear.py).
Ingressi: la trascrizione di Qwen3-ASR come TESTO nel lettore e5 (cache/asr-testo.jsonl, scelta di
progetto) + 4 ingressi neurali (CLAP, MERT, Dasheng, emotion2vec) attraverso i loro ponti.
  --fase 1  solo i 4 PONTI; codec (strati e5 12-24 + Perceiver) congelato, copia dell'insegnante.
            loss = MSE + 0.5*(1 - coseno) fra par dello studente e par dell'insegnante (standardizzati).
  --fase 2  ponti + strati e5 12-24 (fp32) + Perceiver + testa JEV.
            loss JEV = (1 - coseno verso il bersaglio emotion2vec) + CE sulle 51 ancore (temperatura 10).
  --fase 3  come la 2 + Occamy acceso: CE sul testo vestito "...sto udendo" con la griglia nello span visivo
            (stessa catena di gradino4/addestra-e2e.py: build/prepara/ce_con).
Adam fp32 (lezione 23/08), ingressi standardizzati (mu/sd dei ponti misurati sul train), spie anti-collasso
a ogni epoca, ckpt atomico (ear/corse/ckpt-ear-<tag>.pt) ogni --ogni clip e a fine epoca, --riprendi.
Pesi migliori sull'held-out in ear/corse/ear-<tag>.pt. Esito in ear/corse/esito-ear-<tag>.json.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/data/jspace"); sys.path.insert(0, "/data/memoria-episodica-affettiva/gradino4"); sys.path.insert(0, "/data/memoria-episodica-affettiva/ear")
import ear_modello as E  # noqa: E402
from testa_nuova import Testa  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--fase", type=int, choices=[1, 2, 3], required=True)
ap.add_argument("--insegnante", required=True, help="pesi della fase 0 (ear/fase0/testa-e2e-<tag>.pt)")
ap.add_argument("--init", default="", help="pesi EAR di una fase precedente (ear/corse/ear-<tag>.pt)")
ap.add_argument("--tag", required=True)
ap.add_argument("--lr", type=float, default=1e-4, help="ponti, Perceiver, JEV")
ap.add_argument("--lr-lettore", type=float, default=1e-5, help="strati e5 12-24 (fasi 2-3)")
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--epoche", type=int, default=30)
ap.add_argument("--pazienza", type=int, default=5)
ap.add_argument("--peso-jev", type=float, default=0.5)
ap.add_argument("--peso-par", type=float, default=1.0, help="fase 3: peso della loss verso l'insegnante accanto alla CE")
ap.add_argument("--ogni", type=int, default=500, help="ckpt ogni N clip")
ap.add_argument("--n-train", type=int, default=0, help="0 = tutte (per il collaudo: 10)")
ap.add_argument("--riprendi", action="store_true")
args = ap.parse_args()

EAR = os.environ.get("EAR_DIR", "/data/memoria-episodica-affettiva/ear")   # EAR_DIR: solo per la prova a secco
PROVA = os.environ.get("EAR_PROVA") == "1"   # prova a secco su CPU: lettore XLM-R minuscolo a pesi casuali
G4 = "/data/memoria-episodica-affettiva/gradino4"
OUT = f"{EAR}/corse"
FRASE = "...sto udendo"          # frase decisa prima, come tutte quelle che il modello vede
MAX_ANS_TOK = 256
CONSENSO_VIS = "/data/workspace/genesi/CONSENSO-VISIVO.md"
os.makedirs(OUT, exist_ok=True)
CKPT_F, PESI_F, ESITO_F = f"{OUT}/ckpt-ear-{args.tag}.pt", f"{OUT}/ear-{args.tag}.pt", f"{OUT}/esito-ear-{args.tag}.json"

def unit_attiva(nome):
    return subprocess.run(["systemctl", "--user", "is-active", nome], capture_output=True, text=True).stdout.strip() == "active"
for unit in ("addestra-e2e", "addestra-ear-insegnante", "llama-35b"):
    if unit_attiva(unit) and not PROVA:
        print(f"{unit} e' ATTIVA: la GPU e' una sola, non parto."); sys.exit(1)
if args.fase == 3 and not (os.path.exists(CONSENSO_VIS) and any(r.strip() == "attivo: sì" for r in open(CONSENSO_VIS, encoding="utf-8"))):
    print("CONSENSO VISIVO non attivo: la fase 3 inietta nel canale visivo, non parto."); sys.exit(0)
dev = "cpu" if PROVA else "cuda"

# --- dati: clip, trascrizioni ASR, cache dei 4 modelli neurali, griglie insegnante, probabilita' emotion2vec
clip = [json.loads(r) for r in open(f"{EAR}/dati/manifest-emotivi.jsonl")]
prob = {}
for r in open(f"{EAR}/cache/e2v-prob.jsonl"):
    d = json.loads(r); prob[d["id"]] = d["prob"]          # l'ultima riga per id vince (collaudi ripetuti)
feat = {c["id"]: {n: torch.from_numpy(np.load(f"{EAR}/cache/{n}/{c['id']}.npy").astype(np.float32)) for n in E.INGRESSI} for c in clip}
trasc = E.carica_trascrizioni(f"{EAR}/cache/asr-testo.jsonl")
manca = [c["id"] for c in clip if c["id"] not in trasc]
if manca:
    print(f"trascrizione ASR mancante per {len(manca)} clip (es. {manca[:3]}): rilancia estrai-ear.py --modelli asr"); sys.exit(1)
train = [c for c in clip if c["split"] == "train"]
held = [c for c in clip if c["split"] == "held"]
if args.n_train:
    train = train[:args.n_train]
print(f"EAR fase {args.fase}: {len(train)} clip train, {len(held)} held-out")

# --- codec dell'insegnante: lettore e5 (+ strati riaddestrati), Perceiver, mu/sd/K
ins = torch.load(args.insegnante, map_location="cpu", weights_only=False)
e = ins["esito"]
from transformers import AutoModel, AutoTokenizer  # noqa: E402
tok_e = AutoTokenizer.from_pretrained(e["lettore"])
if PROVA:
    from transformers import XLMRobertaConfig, XLMRobertaModel
    lettore = XLMRobertaModel(XLMRobertaConfig(hidden_size=1024, num_hidden_layers=24, num_attention_heads=16, intermediate_size=64, vocab_size=10))
else:
    lettore = AutoModel.from_pretrained(e["lettore"])
if ins.get("lettore_stato"):
    lettore.load_state_dict(ins["lettore_stato"], strict=False)
testa = Testa(lettore.config.hidden_size, int(ins["K"]), e["h"], e["strati"], e["teste"], e["dropout"])
testa.load_state_dict(ins["stato"])
K = int(ins["K"]); mu_c, sd_c = ins["mu"].float(), ins["sd"].float()
model = E.CodecEAR(lettore, testa, K)
lettore_vocab = lettore.config.vocab_size
del lettore
if args.init:
    st = torch.load(args.init, map_location="cpu", weights_only=False)["stato"]
    print("init EAR:", model.load_state_dict(st, strict=False))
else:
    # standardizzazione degli ingressi: mu/sd per modello sui token del train
    for n in E.INGRESSI:
        X = torch.cat([feat[c["id"]][n] for c in train])
        model.ponti[n].mu.copy_(X.mean(0)); model.ponti[n].sd.copy_(X.std(0) + 1e-5)
model = model.to(dev)
tgt = {c["chiave_testo"]: ((torch.from_numpy(np.load(f"{EAR}/insegnante/{c['chiave_testo']}.npy")).float().reshape(-1) - mu_c) / sd_c)
       for c in clip}
nomi, ancore, centro, bordo = E.carica_ancore(dev)
mappa = json.load(open(E.MAPPA))
bers = {c["id"]: E.bersaglio_jev(prob[c["id"]], nomi, ancore, mappa) for c in clip}

# --- cosa si addestra in questa fase
for p in model.parameters():
    p.requires_grad_(False)
allenati = [model.ponti]
if args.fase >= 2:
    allenati += [model.testa, model.jev]
for mod in allenati:
    for p in mod.parameters():
        p.requires_grad_(True)
gruppi = [{"params": [p for mod in allenati for p in mod.parameters()], "lr": args.lr}]
if args.fase >= 2:
    for p in model.strati.parameters():
        p.requires_grad_(True)
    gruppi.append({"params": list(model.strati.parameters()), "lr": args.lr_lettore})
opt = torch.optim.Adam(gruppi)   # tutto fp32
print(f"parametri addestrabili: {sum(p.numel() for g in gruppi for p in g['params'])/1e6:.1f}M")


def lotto(cs):
    """clip -> ids/mask della trascrizione + feats/masks paddati sul lotto."""
    ids, mask_t = E.testo_e5(tok_e, [trasc[c["id"]] for c in cs], dev)
    if PROVA:
        ids = ids % lettore_vocab          # lettore finto minuscolo: id ridotti al suo vocabolario
    feats, masks = {}, {}
    for n in E.INGRESSI:
        L = max(feat[c["id"]][n].shape[0] for c in cs)
        x = torch.zeros(len(cs), L, E.D_ING[n]); m = torch.zeros(len(cs), L, dtype=torch.long)
        for i, c in enumerate(cs):
            h = feat[c["id"]][n]; x[i, :len(h)] = h; m[i, :len(h)] = 1
        feats[n], masks[n] = x.to(dev), m.to(dev)
    return ids, mask_t, feats, masks


def loss_par(p, t):
    return torch.nn.functional.mse_loss(p, t) + 0.5 * (1 - torch.nn.functional.cosine_similarity(p, t, dim=-1).mean())


def loss_jev(j, cs):
    vs = [(i, bers[c["id"]]) for i, c in enumerate(cs) if bers[c["id"]][0] is not None]
    if not vs:
        return torch.zeros((), device=dev)
    idx = torch.tensor([i for i, _ in vs], device=dev)
    v = torch.stack([b[0] for _, b in vs]).to(dev); top = torch.tensor([b[1] for _, b in vs], device=dev)
    jj = torch.nn.functional.normalize(j[idx], dim=-1)
    return (1 - (jj * v).sum(-1)).mean() + torch.nn.functional.cross_entropy(10 * jj @ ancore.T, top)


# --- fase 3: Occamy (stessa catena di gradino4/addestra-e2e.py)
if args.fase == 3:
    import mixed35b as M  # noqa: E402
    import transformers  # noqa: E402
    from PIL import Image  # noqa: E402
    s = M.load(); hf, tok = s["hf"], s["tok"]
    for p in hf.parameters():
        p.requires_grad_(False)
    hf.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False}); hf.train()
    proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID)
    dummy = Image.new("RGB", (280, 280), "gray")
    emb_layer = hf.get_input_embeddings(); img_tok = hf.config.image_token_id
    ck = np.load(f"{G4}/codec-full-e2e.npz")
    BASE = torch.from_numpy(ck["base"]).float().to(dev); POS = torch.from_numpy(ck["Wpos"]).float().to(dev)
    mu_d, sd_d = mu_c.to(dev), sd_c.to(dev)

    def prepara(testo):
        tronco = tok.decode(tok(testo, add_special_tokens=False, return_tensors="pt").input_ids[0][:MAX_ANS_TOK])
        msgs = [{"role": "user", "content": [{"type": "image"}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True) + FRASE + "\n" + tronco
        inputs = proc(text=[text], images=[dummy], return_tensors="pt")
        n_ans = tok(tronco, add_special_tokens=False, return_tensors="pt").input_ids.shape[1]
        labels = torch.full_like(inputs.input_ids, -100); labels[0, -n_ans:] = inputs.input_ids[0, -n_ans:]
        return inputs, inputs.input_ids[0] == img_tok, labels

    def ce_con(griglia, inputs, mask_img, labels):
        ids = inputs.input_ids.to(dev)
        emb = emb_layer(ids).detach().clone(); emb[0, mask_img.to(dev)] = griglia.to(emb.dtype)
        return hf(inputs_embeds=emb, attention_mask=inputs.attention_mask.to(dev), labels=labels.to(dev)).loss

    def ce_clip(c, par_std):
        par = (par_std * sd_d + mu_d).view(K, 2048)
        return ce_con(BASE + POS @ par, *prepara(c["testo"]))


def valuta():
    model.eval(); r = {"par": [], "cos": [], "jev_e2v": [], "jev_dataset": [], "ce": []}
    pars = []
    with torch.no_grad():
        for i in range(0, len(held), args.batch):
            cs = held[i:i + args.batch]
            p, j = model(*lotto(cs))
            t = torch.stack([tgt[c["chiave_testo"]] for c in cs]).to(dev)
            r["par"].append(loss_par(p, t).item())
            r["cos"] += torch.nn.functional.cosine_similarity(p, t, dim=-1).tolist()
            pars.append(p)
            for k, c in enumerate(cs):
                scelta, _ = E.scegli(j[k], ancore, centro, bordo)
                if bers[c["id"]][1] >= 0:
                    r["jev_e2v"].append(scelta == bers[c["id"]][1])
                r["jev_dataset"].append(nomi[scelta] == mappa["dataset_a_emozione"].get(c["emozione_dataset"]))
                if args.fase == 3:
                    r["ce"].append(ce_clip(c, p[k]).item())
    P = torch.cat(pars)
    pn = torch.nn.functional.normalize(P, dim=-1)
    T_ = torch.stack([tgt[c["chiave_testo"]] for c in held]).to(dev)
    out = {"loss_par": float(np.mean(r["par"])), "cos_insegnante": float(np.mean(r["cos"])),
           "jev_acc_e2v": float(np.mean(r["jev_e2v"])) if r["jev_e2v"] else None,
           "jev_acc_dataset": float(np.mean(r["jev_dataset"])),
           # spie anti-collasso: varianza fra clip (studente vs insegnante) e coseno medio fra clip diverse
           "var_fra_clip": float(P.var(0).mean()), "var_insegnante": float(T_.var(0).mean()),
           "cos_fra_clip": float(((pn @ pn.T).sum() - len(pn)) / (len(pn) * (len(pn) - 1)))}
    if r["ce"]:
        out["ce_held"] = float(np.mean(r["ce"]))
    if out["var_fra_clip"] < 0.05 * out["var_insegnante"]:
        print("[spia] COLLASSO: le uscite delle clip sono quasi tutte uguali", flush=True)
    model.train(); return out


esito = {"args": vars(args), "quando": time.strftime("%F %T"), "curva": []}
migliore, ferme, ep0, pos0 = 1e9, 0, 1, 0
rng = np.random.default_rng(0)


def salva_ckpt(ep, pos, ordine):
    torch.save({"stato": model.state_dict(), "opt": opt.state_dict(), "epoca": ep, "pos": pos, "ordine": list(map(int, ordine)),
                "migliore": migliore, "ferme": ferme, "esito": esito, "rng": rng.bit_generator.state}, CKPT_F + ".tmp")
    os.replace(CKPT_F + ".tmp", CKPT_F)
    print(f"[ckpt] fase {args.fase} epoca {ep} pos {pos}/{len(train)} salvato {time.strftime('%H:%M')}", flush=True)


ripresa = None
if args.riprendi and os.path.exists(CKPT_F):
    ripresa = torch.load(CKPT_F, map_location="cpu", weights_only=False)
    model.load_state_dict(ripresa["stato"]); opt.load_state_dict(ripresa["opt"])
    for g, lr in zip(opt.param_groups, [args.lr, args.lr_lettore]):
        g["lr"] = lr
    migliore, ferme, esito = ripresa["migliore"], ripresa["ferme"], ripresa["esito"]
    rng.bit_generator.state = ripresa["rng"]; ep0 = ripresa["epoca"]
    print(f"[ripresa] epoca {ep0} pos {ripresa['pos']}", flush=True)
else:
    v0 = valuta(); esito["curva"].append({"epoca": 0, **v0}); print(f"epoca 0: {v0}", flush=True)

model.train()
if args.fase == 1:
    model.strati.eval(); model.testa.eval()      # congelati: niente dropout
for ep in range(ep0, args.epoche + 1):
    t0 = time.time()
    if ripresa is not None and ripresa["epoca"] == ep and ripresa["pos"] > 0:
        ordine, b_in = np.array(ripresa["ordine"]), ripresa["pos"]
    else:
        ordine, b_in = rng.permutation(len(train)), 0
    ripresa = None
    somma, n_ok, prossimo = 0.0, 0, (b_in // args.ogni + 1) * args.ogni
    for b0 in range(b_in, len(train), args.batch):
        cs = [train[j] for j in ordine[b0:b0 + args.batch]]
        opt.zero_grad()
        # fase 3: una clip per forward/backward (il grafo di Occamy per 8 clip insieme non sta in VRAM),
        # gradienti accumulati sul lotto come in addestra-e2e.py. Fasi 1-2: il lotto intero in un colpo.
        sottolotti = [[c] for c in cs] if args.fase == 3 else [cs]
        tot, ok = 0.0, True
        for sl in sottolotti:
            p, j = model(*lotto(sl))
            t = torch.stack([tgt[c["chiave_testo"]] for c in sl]).to(dev)
            loss = (args.peso_par if args.fase == 3 else 1.0) * loss_par(p, t)
            if args.fase >= 2:
                loss = loss + args.peso_jev * loss_jev(j, sl)
            if args.fase == 3:
                loss = loss + ce_clip(sl[0], p[0])
            if not torch.isfinite(loss):
                print(f"[marcio] loss non finita su {[c['id'] for c in sl]}: saltato", flush=True); ok = False; continue
            (loss * len(sl) / len(cs)).backward(); tot += loss.item() * len(sl) / len(cs)
        g = torch.nn.utils.clip_grad_norm_([p_ for gr in gruppi for p_ in gr["params"]], 1.0)
        if not torch.isfinite(g) or (not ok and args.fase < 3):
            print("[marcio] gradienti non finiti: lotto saltato", flush=True); opt.zero_grad(); continue
        opt.step(); somma += tot; n_ok += 1
        if b0 + args.batch >= prossimo and b0 + args.batch < len(train):
            salva_ckpt(ep, b0 + args.batch, ordine); prossimo += args.ogni
    v = valuta()
    riga = {"epoca": ep, "train": somma / max(n_ok, 1), **v, "s": round(time.time() - t0)}
    esito["curva"].append(riga)
    print(f"epoca {ep}: " + " ".join(f"{k} {x:.4f}" if isinstance(x, float) else f"{k} {x}" for k, x in riga.items() if k != "epoca"), flush=True)
    metro = v.get("ce_held", v["loss_par"]) if args.fase == 3 else v["loss_par"] + (args.peso_jev * (1 - (v["jev_acc_e2v"] or 0)) if args.fase == 2 else 0)
    if metro < migliore:
        migliore, ferme = metro, 0
        torch.save({"stato": model.state_dict(), "fase": args.fase, "insegnante": args.insegnante, "K": K,
                    "mu": mu_c, "sd": sd_c, "esito": riga}, PESI_F + ".tmp")
        os.replace(PESI_F + ".tmp", PESI_F)
    else:
        ferme += 1
    esito["migliore"] = migliore
    json.dump(esito, open(ESITO_F, "w"), indent=1, ensure_ascii=False)
    salva_ckpt(ep + 1, 0, [])
    if ferme >= args.pazienza:
        print(f"held-out fermo da {ferme} epoche: stop"); break
print(f"fine fase {args.fase}: migliore {migliore:.4f}, pesi {PESI_F}")
