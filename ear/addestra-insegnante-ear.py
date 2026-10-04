#!/usr/bin/env python3
"""
EAR, FASE 0 (piano EAR, EAR-PLAN.md): l'INSEGNANTE.
Copia di gradino4/addestra-e2e.py (stesso codec, stessi meccanismi: ckpt atomico ogni --ogni, --riprendi,
sentinella dei marci, guardie) con due differenze: la vestizione e' "...sto udendo" (frase decisa prima) e i
testi sono le frasi dei WAV di EAR (ear/dati/manifest-emotivi.jsonl, una chiave per frase: le 5 voci
emotive di una frase hanno la stessa griglia insegnante). Si parte dal codec E8 di fine epoca 2 (--init).
Alla fine scrive le griglie insegnante ear/insegnante/<chiave>.npy (par K x 2048) con i pesi migliori.
"""
import argparse, collections, glob, json, os, sys, time
import numpy as np
import torch
sys.path.insert(0, "/data/jspace"); sys.path.insert(0, "/data/memoria-episodica-affettiva/gradino4")

ap = argparse.ArgumentParser()
ap.add_argument("--lettore", default="intfloat/multilingual-e5-large",
                help="modello e5 oppure '35b-emb' (embedding d'ingresso del 35B)")
ap.add_argument("--strati", type=int, default=8)
ap.add_argument("--h", type=int, default=1024)
ap.add_argument("--teste", type=int, default=8)
ap.add_argument("--dropout", type=float, default=0.10)
ap.add_argument("--lr", type=float, default=1e-4)
ap.add_argument("--batch", type=int, default=4, help="testi per passo (accumulo, il 35B va uno alla volta)")
ap.add_argument("--n-train", type=int, default=35)
ap.add_argument("--n-held", type=int, default=7)
ap.add_argument("--epoche", type=int, default=30)
ap.add_argument("--pazienza", type=int, default=8, help="epoche senza miglioramento held-out")
ap.add_argument("--init", default="", help=".pt di una cella del quadrato (stessa forma) per partire dal pianoro")
ap.add_argument("--tag", required=True)
ap.add_argument("--go", type=float, default=1.0, help="CE train sotto cui E2 e' GO")
ap.add_argument("--sblocca-strati", type=int, default=0,
                help="E5: quanti strati FINALI del lettore e5 si addestrano (0 = congelato, letture in cache)")
ap.add_argument("--lr-lettore", type=float, default=1e-5, help="lr degli strati sbloccati del lettore")
ap.add_argument("--riprendi", action="store_true",
                help="riparte dall'ultimo salvataggio ckpt-e2e-<tag>.pt (ogni --ogni testi, sovrascritto)")
ap.add_argument("--ogni", type=int, default=500, help="salvataggio intermedio ogni N testi (01/10: 500, era 1000; un crash Xid perde al massimo ~45 min)")
ap.add_argument("--ripassa-marci", action="store_true",
                help="(13/09) alla ripresa ripassa UNA volta i lotti marci registrati, poi continua l'epoca")
ap.add_argument("--solo-ripasso", action="store_true", help="(15/09) con --ripassa-marci: dopo il ripasso salva il ckpt ed esce (per un test a pesi ripassati)")
ap.add_argument("--tutti-i-testi", action="store_true",
                help="train pescato da TUTTI i testi su disco (esclusa la pagella), non solo dai 5000 del campione")
args = ap.parse_args()

G4 = "/data/memoria-episodica-affettiva/gradino4"
DIR = "/data/memoria-episodica-affettiva/ear/fase0"
EAR = "/data/memoria-episodica-affettiva/ear"
PALESTRA = "/data/dataset-codec"
CKPT = f"{G4}/codec-full-e2e.npz"
OUT_DIR = f"{G4}/distillati-U"
CONSENSO_VIS = "/data/workspace/genesi/CONSENSO-VISIVO.md"
FRASE = "...sto udendo"     # vestizione di EAR, decisa prima
MAX_ANS_TOK = 256   # 27/09: da 128 (tagliava il 35.6% dei testi); misura VRAM: picco 12.5 GiB
ESITO_F = f"{DIR}/esito-e2e-{args.tag}.json"
PESI_F = f"{DIR}/testa-e2e-{args.tag}.pt"
LINGUE = ["it", "en", "de", "es", "fr", "ja", "zh"]

import subprocess
def unit_attiva(nome):
    r = subprocess.run(["systemctl", "--user", "is-active", nome], capture_output=True, text=True)
    return r.stdout.strip() == "active"
for unit in ("llama-35b", "distilla-u-1000", "fabbrica-35b", "fabbrica-rollout", "campagna-codec", "addestra-e2e"):   # EAR: E8 in pausa
    if unit_attiva(unit):
        print(f"{unit} e' ATTIVA: questa corsa non parte (GPU una sola)."); sys.exit(1)
attivo = os.path.exists(CONSENSO_VIS) and any(r.strip() == "attivo: sì" for r in open(CONSENSO_VIS, encoding="utf-8"))
if not attivo:
    print("CONSENSO VISIVO non attivo: corsa annullata."); sys.exit(0)

# --- testi di EAR: una chiave per FRASE (manifest di prepara-wav-ear.py); split per frase, held-out mai visto
testi, split_di = {}, {}
for r in open(f"{EAR}/dati/manifest-emotivi.jsonl"):
    d = json.loads(r)
    testi[(d["chiave_testo"], d["lingua"])] = d["testo"]; split_di[(d["chiave_testo"], d["lingua"])] = d["split"]
train = sorted(c for c in testi if split_di[c] == "train")[:args.n_train]
held = sorted(c for c in testi if split_di[c] == "held")[:args.n_held]
train_base = train
print(f"EAR: {len(train)} frasi di train, {len(held)} held-out (mai viste)")


def train_epoca(ep):
    return train_base

def nome_file(id_s, lingua):
    return f"{OUT_DIR}/{id_s.replace('/', '--').replace('#', '_')}-{lingua}.npy"

# --- base pos (congelata) + scala dei coefficienti
ck = np.load(CKPT)
K = int(ck["K"])
BASE = torch.from_numpy(ck["base"]).float().cuda()
POS = torch.from_numpy(ck["Wpos"]).float().cuda()
if args.init and os.path.exists(args.init):
    ci = torch.load(args.init, map_location="cpu", weights_only=False)
    mu, sd = ci["mu"].float(), ci["sd"].float()
    print(f"mu/sd dalla cella {args.init}")
else:
    ci = None
    fs = sorted(glob.glob(f"{OUT_DIR}/*.npy"))
    Y = torch.tensor(np.stack([np.load(f) for f in fs]), dtype=torch.float32).view(len(fs), -1)
    mu, sd = Y.mean(0), Y.std(0) + 1e-6
    print(f"mu/sd da {len(fs)} griglie di produzione")
mu_d, sd_d = mu.cuda(), sd.cuda()

# --- 35B congelato (come distilla-U)
import mixed35b as M  # noqa: E402
s = M.load()
hf, tok = s["hf"], s["tok"]
for p in hf.parameters():
    p.requires_grad_(False)          # il 35B non si addestra: niente gradienti sui suoi pesi
hf.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
hf.train()
import transformers  # noqa: E402
proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID)
from PIL import Image  # noqa: E402
dummy = Image.new("RGB", (280, 280), "gray")
emb_layer = hf.get_input_embeddings()
img_tok = hf.config.image_token_id
def build(answer=None):
    msgs = [{"role": "user", "content": [{"type": "image"}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True) + FRASE + "\n"
    if answer is not None:
        text = text + answer
    return proc(text=[text], images=[dummy], return_tensors="pt")
def prepara(testo):
    tronco = tok.decode(tok(testo, add_special_tokens=False, return_tensors="pt").input_ids[0][:MAX_ANS_TOK])
    inputs = build(tronco)               # resta su CPU (06/09: su GPU 1785 testi = 1,7 GB); si sposta per testo
    ids_ = inputs.input_ids
    mask_img = ids_[0] == img_tok
    n_ans = tok(tronco, add_special_tokens=False, return_tensors="pt").input_ids.shape[1]
    labels = torch.full_like(ids_, -100)
    labels[0, -n_ans:] = ids_[0, -n_ans:]
    return inputs, mask_img, labels
def ce_con(griglia, inputs, mask_img, labels, grad=False):
    ids = inputs.input_ids.cuda(); att = inputs.attention_mask.cuda()
    emb = emb_layer(ids).detach().clone()
    emb[0, mask_img.cuda()] = griglia.to(emb.dtype)
    with (torch.enable_grad() if grad else torch.no_grad()):
        return hf(inputs_embeds=emb, attention_mask=att, labels=labels.cuda()).loss

# --- lettore congelato, letture in cache (una volta per testo)
tutti = train + held
if args.lettore == "35b-emb":
    D_LET = emb_layer.weight.shape[1]
    def leggi(t):
        ids = tok(t, add_special_tokens=False, truncation=True, max_length=512, return_tensors="pt").input_ids.cuda()
        with torch.no_grad():
            return emb_layer(ids)[0].float().cpu()
else:
    from transformers import AutoModel, AutoTokenizer
    tok_e = AutoTokenizer.from_pretrained(args.lettore)
    lettore = AutoModel.from_pretrained(args.lettore).eval()   # CPU: la VRAM e' del 35B
    D_LET = lettore.config.hidden_size
    def leggi(t):
        inp = tok_e(["passage: " + t], truncation=True, max_length=512, return_tensors="pt")
        with torch.no_grad():
            return lettore(**inp).last_hidden_state[0].float()
SBLOCCA = args.sblocca_strati if args.lettore != "35b-emb" else 0
if SBLOCCA:
    # E5: lettore sulla GPU accanto al 35B. Pesi congelati in bf16 (poca VRAM),
    # ultimi SBLOCCA strati in fp32 (lezione 23/08: mai Adam su pesi bf16),
    # forward sotto autocast bf16. Niente cache: le letture cambiano.
    lettore = AutoModel.from_pretrained(args.lettore, dtype=torch.bfloat16).cuda().eval()
    for p_ in lettore.parameters():
        p_.requires_grad_(False)
    strati_sb = list(lettore.encoder.layer)[-SBLOCCA:]
    for l_ in strati_sb:
        l_.float()
        for p_ in l_.parameters():
            p_.requires_grad_(True)
    par_lettore = [p_ for l_ in strati_sb for p_ in l_.parameters()]
    print(f"lettore SBLOCCATO negli ultimi {SBLOCCA} strati: {sum(p_.numel() for p_ in par_lettore)/1e6:.1f}M parametri addestrabili")
    def leggi_gpu(t, grad):
        inp = tok_e(["passage: " + t], truncation=True, max_length=512, return_tensors="pt").to("cuda")
        with (torch.enable_grad() if grad else torch.no_grad()), torch.autocast("cuda", dtype=torch.bfloat16):
            h = lettore(**inp).last_hidden_state
        return h.float(), inp.attention_mask
    cache = {}
else:
    t0 = time.time()
    cache = {c: leggi(testi[c]) for c in tutti}
    print(f"letture in cache: {len(cache)} testi, d={D_LET}, {time.time()-t0:.0f}s")
    if args.lettore != "35b-emb":
        del lettore
# ponytail: prep pigra. Con --tutti-i-testi (177k) il dict pieno faceva ~1 MB/testo
# (pixel_values del dummy) = ~170 GB > RAM: PC bloccato due volte il 09/09.
# Ricalcolo per testo (ms, contro secondi del forward del 35B); niente cache.
class _Prep(dict):
    def __missing__(self, c): return prepara(testi[c])
prep = _Prep()

# --- testa (modello condiviso in testa_nuova.py)
from testa_nuova import Testa  # noqa: E402
testa = Testa(D_LET, K, args.h, args.strati, args.teste, args.dropout).cuda()
if ci is not None:
    st = ci["stato"]; mio = testa.state_dict()
    ok = {k: v for k, v in st.items() if k in mio and mio[k].shape == v.shape}
    testa.load_state_dict(ok, strict=False)
    print(f"init dalla cella: {len(ok)}/{len(mio)} tensori caricati (saltati: {sorted(set(mio)-set(ok))[:4]})")
    if SBLOCCA and ci.get("lettore_stato"):
        # 07/09: gli strati del lettore riaddestrati da una corsa precedente
        # si ricaricano (prima E6 ripartiva col lettore originale: 2.140 vs 2.123)
        manc, inatt = lettore.load_state_dict({k: v.to(next(lettore.parameters()).device) for k, v in ci["lettore_stato"].items()}, strict=False)
        print(f"lettore: ricaricati {len(ci['lettore_stato'])} tensori degli strati sbloccati (inattesi: {len(inatt)})")
n_par = sum(p.numel() for p in testa.parameters())
print(f"testa Perceiver {args.strati} strati H{args.h}: {n_par/1e6:.1f}M parametri, lettore {args.lettore} d={D_LET}")
gruppi = [{"params": list(testa.parameters()), "lr": args.lr}]
if SBLOCCA:
    gruppi.append({"params": par_lettore, "lr": args.lr_lettore})
opt = torch.optim.Adam(gruppi)   # fp32 (lezione 23/08)

def par_di(c, grad=False):
    if SBLOCCA:
        h, m = leggi_gpu(testi[c], grad)
    else:
        h = cache[c].cuda().unsqueeze(0)
        m = torch.ones(1, h.shape[1], dtype=torch.long, device="cuda")
    out = testa(h, m)[0]
    return (out * sd_d + mu_d).view(K, 2048)
def ce_di(c, grad):
    inputs, mask_img, labels = prep[c]
    par = par_di(c, True) if grad else par_di(c).detach()
    return ce_con(BASE + POS @ par, inputs, mask_img, labels, grad=grad), par

# riferimenti una volta sola: griglia spenta e (se c'e') griglia distillata
rif = {}
# riferimenti (spenta/distillata) solo su held-out + 35 train: servono al
# rapporto, non al training (06/09: su 1785 testi costavano 2 ore di GPU)
with torch.no_grad():
    for c in held + train[:35]:
        inputs, mask_img, labels = prep[c]
        spenta = ce_con(BASE, inputs, mask_img, labels).item()
        dist = None
        if os.path.exists(nome_file(*c)):
            par = torch.from_numpy(np.load(nome_file(*c))).float().cuda()
            dist = ce_con(BASE + POS @ par, inputs, mask_img, labels).item()
        rif[c] = {"spenta": spenta, "distillata": dist}
print(f"CE griglia spenta: train (primi {min(35,len(train))}) {np.mean([rif[c]['spenta'] for c in train[:35]]):.3f}, held {np.mean([rif[c]['spenta'] for c in held]):.3f}")

def stato_lettore():
    """Solo gli strati sbloccati (TestaNuova li ricarica con strict=False)."""
    if not SBLOCCA:
        return None
    n0 = len(lettore.encoder.layer) - SBLOCCA
    return {k: v.detach().cpu() for k, v in lettore.state_dict().items()
            if k.startswith("encoder.layer.") and int(k.split(".")[2]) >= n0}
def valuta(lista):
    testa.eval()
    ces = {}
    with torch.no_grad():
        for c in lista:
            ces[c] = ce_di(c, False)[0].item()
    testa.train()
    return ces
def specificita(lista):
    """gap = CE(griglia di un ALTRO testo) - CE(griglia propria), media sugli held-out."""
    testa.eval(); gaps = []
    with torch.no_grad():
        pars = {c: par_di(c).detach() for c in lista}
        for i, c in enumerate(lista):
            altro = lista[(i + 1) % len(lista)]
            inputs, mask_img, labels = prep[c]
            a = ce_con(BASE + POS @ pars[c], inputs, mask_img, labels).item()
            b = ce_con(BASE + POS @ pars[altro], inputs, mask_img, labels).item()
            gaps.append(b - a)
    testa.train()
    return float(np.mean(gaps))

esito = {"quando": time.strftime("%F %T"), "args": vars(args), "n_par": n_par, "curva": [],
         "rif": {f"{c[0]}|{c[1]}": v for c, v in rif.items()}}
ce_h0 = valuta(held); ce_t0 = valuta(train[:35])   # epoca 0: train solo sui primi 35 (06/09: su 1750 costava 1 h)
esito["curva"].append({"epoca": 0, "train": float(np.mean(list(ce_t0.values()))),
                       "held": float(np.mean(list(ce_h0.values()))), "spec_held": specificita(held), "s": 0})
print(f"epoca 0 (init): train {esito['curva'][-1]['train']:.4f} held {esito['curva'][-1]['held']:.4f} spec {esito['curva'][-1]['spec_held']:+.4f}", flush=True)
json.dump(esito, open(ESITO_F, "w"), indent=1, ensure_ascii=False)

MARCI_F = f"{DIR}/marci-e2e-{args.tag}.json"
CKPT_F = f"{DIR}/ckpt-e2e-{args.tag}.pt"
marci = []
SENT_MARCI, SENT_LOTTI = 3, 20   # sentinella dei marci (30/09): 3 in 20 lotti = 35B guasto in memoria
migliore, ferme = 1e9, 0
rng = np.random.default_rng(0)
ep_inizio, ripresa = 1, None

def salva_ckpt(ep, ordine, pos, somma):
    """Salvataggio intermedio (ogni --ogni testi), UN file sovrascritto
    (08/09). Contiene tutto quello che serve a riprendere
    dallo stesso punto dell'epoca: pesi, lettore, ottimizzatore, ordine."""
    torch.save({"stato": testa.state_dict(), "lettore_stato": stato_lettore(),
                "opt": opt.state_dict(), "epoca": ep, "pos": int(pos),
                "ordine": [int(x) for x in ordine], "somma": float(somma),
                "migliore": migliore, "ferme": ferme, "marci": marci, "esito": esito,
                "rng": rng.bit_generator.state, "mu": mu, "sd": sd, "K": K,
                "quando": time.strftime("%F %T")}, CKPT_F + ".tmp")
    os.replace(CKPT_F + ".tmp", CKPT_F)
    print(f"[ckpt] epoca {ep} pos {pos}/{len(train)} salvato {time.strftime('%H:%M')}", flush=True)

if args.riprendi and os.path.exists(CKPT_F):
    ck_r = torch.load(CKPT_F, map_location="cpu", weights_only=False)
    testa.load_state_dict(ck_r["stato"])
    if SBLOCCA and ck_r.get("lettore_stato"):
        lettore.load_state_dict({k: v.to(next(lettore.parameters()).device) for k, v in ck_r["lettore_stato"].items()}, strict=False)
    # 21/09 (protocollo 20k): ripresa TOLLERANTE. Se il gruppo del lettore e' cresciuto
    # (--sblocca-strati N+1), lo stato Adam dei parametri vecchi si riallinea in coda (gli strati
    # sbloccati sono gli ULTIMI del lettore: i vecchi sono la coda della lista nuova); i nuovi
    # partono senza stato. A gruppi uguali: caricamento normale.
    so = ck_r["opt"]
    n_nuovi = [len(g["params"]) for g in opt.state_dict()["param_groups"]]
    n_vecchi = [len(g["params"]) for g in so["param_groups"]]
    if n_nuovi == n_vecchi:
        opt.load_state_dict(so)
    else:
        assert len(n_nuovi) == len(n_vecchi) and all(a >= b for a, b in zip(n_nuovi, n_vecchi)), (n_nuovi, n_vecchi)
        stato_n, gruppi_n, con_stato = {}, [], 0
        for g_n, g_v in zip(opt.state_dict()["param_groups"], so["param_groups"]):
            ids_n, ids_v = g_n["params"], g_v["params"]
            for i_n, i_v in zip(ids_n[len(ids_n) - len(ids_v):], ids_v):   # coda
                if i_v in so["state"]:
                    stato_n[i_n] = so["state"][i_v]; con_stato += 1
            gruppi_n.append({**g_v, "params": ids_n})
        opt.load_state_dict({"state": stato_n, "param_groups": gruppi_n})
        print(f"[ripresa] ottimizzatore riallineato: {con_stato} parametri con stato, {sum(n_nuovi)-sum(n_vecchi)} nuovi senza stato", flush=True)
    # il load ripristina anche i lr salvati nel ckpt: comandano gli argomenti di QUESTO lancio
    opt.param_groups[0]["lr"] = args.lr
    if SBLOCCA:
        opt.param_groups[1]["lr"] = args.lr_lettore
    print(f"[ripresa] lr testa {opt.param_groups[0]['lr']:g}" + (f", lr lettore {opt.param_groups[1]['lr']:g}" if SBLOCCA else ""), flush=True)
    migliore, ferme, marci, esito = ck_r["migliore"], ck_r["ferme"], ck_r["marci"], ck_r["esito"]
    rng.bit_generator.state = ck_r["rng"]
    ep_inizio, ripresa = ck_r["epoca"], ck_r
    print(f"[ripresa] da {CKPT_F}: epoca {ck_r['epoca']} pos {ck_r['pos']}/{len(train)} (salvato {ck_r['quando']}), migliore held {migliore:.4f}", flush=True)
elif args.riprendi:
    print(f"[ripresa] nessun {CKPT_F}: parto da capo", flush=True)

# comando di rilancio (dopo un blackout): stesso lancio + --riprendi
with open(f"{DIR}/lancio-insegnante-{args.tag}.sh", "w") as f_l:
    argv = [a for a in sys.argv[1:] if a not in ("--riprendi", "--ripassa-marci", "--solo-ripasso")]   # il ripasso e' una tantum
    f_l.write("#!/bin/bash\n# rilancio della corsa %s con ripresa dall'ultimo salvataggio\n" % args.tag)
    f_l.write("systemctl --user reset-failed addestra-ear-insegnante 2>/dev/null\n")
    # 13/09: Restart=on-failure con guardia GPU: dopo un crash (Xid) systemd aspetta
    # 3 min, controlla che nvidia-smi risponda (30 s) e rilancia dal ckpt; max 10 tentativi/h.
    PROPS = ('-p Restart=on-failure -p RestartSec=180 -p StartLimitIntervalSec=3600 -p StartLimitBurst=10 '
             '-p ExecStartPre="/usr/bin/timeout 30 /usr/bin/nvidia-smi -L"')
    f_l.write("exec systemd-run --user --unit=addestra-ear-insegnante %s --working-directory=%s -E HF_HUB_OFFLINE=1 -E TRANSFORMERS_OFFLINE=1 -E PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True -E MODELLO_35B=%s %s -u %s %s --riprendi\n"
              % (PROPS, DIR, M.MODEL_ID, sys.executable, os.path.abspath(__file__), " ".join(repr(a) if " " in a else a for a in argv)))

if args.ripassa_marci:
    # (13/09) i lotti saltati per gradienti/CE non finiti si ripassano UNA volta,
    # stesso lotto e stesso passo del training; chi fallisce ancora resta marcio.
    da_fare = [m for m in marci if not m.get("ripassato") and not m.get("ripasso_fallito")]
    print(f"[ripasso] {len(da_fare)} voci marce da ripassare (su {len(marci)} registrate)", flush=True)
    # 30/09: i marci da UN testo si raggruppano in lotti da --batch. Al 110000 i 1081 marci del guasto
    # sono stati ripassati uno per volta: 1081 passi pieni dell'ottimizzatore, ognuno guidato da un testo
    # solo, e la pagella e' peggiorata da 0.6277 a 0.7350. Ora ogni passo vale quanto un passo del training.
    singoli = [m for m in da_fare if not isinstance(m["id"], list)]
    gruppi = [[m] for m in da_fare if isinstance(m["id"], list)]
    gruppi += [singoli[i:i + args.batch] for i in range(0, len(singoli), args.batch)]
    for gruppo in gruppi:
        chiavi = [(i_, l_) for m in gruppo
                  for i_, l_ in zip(m["id"] if isinstance(m["id"], list) else [m["id"]],
                                    m["lingua"] if isinstance(m["lingua"], list) else [m["lingua"]])
                  if (i_, l_) in testi]
        opt.zero_grad(); ces_r = []
        for c in chiavi:
            ce, _ = ce_di(c, True)
            if not torch.isfinite(ce):
                print(f"[ripasso] CE non finita su {c}: saltato", flush=True); continue
            (ce / len(chiavi)).backward(); ces_r.append(ce.item())
        g = torch.nn.utils.clip_grad_norm_(list(testa.parameters()) + (par_lettore if SBLOCCA else []), 1.0)
        if ces_r and torch.isfinite(g):
            opt.step()
            for m in gruppo:
                m["ripassato"] = time.strftime("%F %T"); m["ce_ripasso"] = float(np.mean(ces_r)); m["grad_ripasso"] = float(g)
            print(f"[ripasso] lotto di {len(chiavi)} passato: CE media {np.mean(ces_r):.4f}, norma grad {float(g):.2f}", flush=True)
        else:
            opt.zero_grad()
            for m in gruppo:
                m["ripasso_fallito"] = time.strftime("%F %T")
            print(f"[ripasso] lotto di {len(chiavi)}: gradienti ancora non finiti, resta marcio", flush=True)
    json.dump(marci, open(MARCI_F, "w"), indent=1, ensure_ascii=False)
    if da_fare and ripresa is not None:
        salva_ckpt(ripresa["epoca"], ripresa["ordine"], ripresa["pos"], ripresa["somma"])
    if args.solo_ripasso:
        print("[ripasso] finito, --solo-ripasso: esco (ckpt salvato)", flush=True); sys.exit(0)
    print("[ripasso] finito, l'epoca continua da dov'era", flush=True)

for ep in range(ep_inizio, args.epoche + 1):
    t0 = time.time()
    train = train_epoca(ep)
    if ep >= 3:
        print(f"[epoca {ep}] train {len(train)} testi ({len(train) - len(train_base)} dei tipi nuovi)", flush=True)
    if ripresa is not None and ripresa["epoca"] == ep:
        b_inizio = ripresa["pos"]; somma = ripresa["somma"]
        # pos 0 = salvataggio di fine epoca: l'ordine nuovo si estrae dal rng
        # (stato salvato PRIMA dell'estrazione: stesso ordine di una corsa mai interrotta)
        ordine = np.array(ripresa["ordine"]) if b_inizio > 0 else rng.permutation(len(train))
        ripresa = None
    else:
        ordine = rng.permutation(len(train)); b_inizio = 0; somma = 0.0
    prossimo_ckpt = (b_inizio // args.ogni + 1) * args.ogni
    # 30/09: SENTINELLA DEI MARCI. Due volte (25/09, 30/09) la copia del 35B si e' guastata in
    # memoria dopo ore e da li' ~12% dei testi dava CE non finita, per ore; ripassati in un processo
    # nuovo erano tutti sani. Se in 20 lotti ne compaiono 3, si salva il ckpt QUI e si esce con codice 3:
    # systemd rilancia la unit dopo 180 s (--riprendi) e il 35B si ricarica pulito. Nessun testo perso;
    # i marci vengono ripassati al test. Guardia di systemd: al massimo 10 riavvii in un'ora.
    marci_per_lotto, m_prec = collections.deque(maxlen=SENT_LOTTI), len(marci)
    for b0 in range(b_inizio, len(train), args.batch):
        marci_per_lotto.append(len(marci) - m_prec); m_prec = len(marci)
        if sum(marci_per_lotto) >= SENT_MARCI:
            print(f"[guasto] {sum(marci_per_lotto)} marci negli ultimi {len(marci_per_lotto)} lotti: "
                  f"salvo e riparto col 35B ricaricato", flush=True)
            salva_ckpt(ep, ordine, b0, somma)
            sys.exit(3)
        idx = ordine[b0:b0 + args.batch]
        opt.zero_grad()
        for j in idx:
            ce, _ = ce_di(train[j], True)
            if not torch.isfinite(ce):
                # testo marcio (come in distilla-U): si salta, si registra, si continua
                marci.append({"id": train[j][0], "lingua": train[j][1], "epoca": ep, "motivo": "CE non finita"})
                json.dump(marci, open(MARCI_F, "w"), indent=1, ensure_ascii=False)
                print(f"[marcio] CE non finita su {train[j]} (epoca {ep}): saltato", flush=True)
                continue
            (ce / len(idx)).backward(); somma += ce.item()
        g = torch.nn.utils.clip_grad_norm_(list(testa.parameters()) + (par_lettore if SBLOCCA else []), 1.0)
        if not torch.isfinite(g):
            # 07/09: un lotto con gradienti non finiti fermava tutta la corsa (E6).
            # Ora si butta il lotto (zero_grad), si registra, si continua.
            marci.append({"id": [train[j][0] for j in idx], "lingua": [train[j][1] for j in idx], "epoca": ep, "motivo": "gradienti non finiti (lotto)"})
            json.dump(marci, open(MARCI_F, "w"), indent=1, ensure_ascii=False)
            print(f"[marcio] gradienti non finiti epoca {ep}, lotto {[train[j][0] for j in idx]}: lotto saltato", flush=True)
            opt.zero_grad()
            continue
        opt.step()
        if b0 + args.batch >= prossimo_ckpt and b0 + args.batch < len(train):
            salva_ckpt(ep, ordine, b0 + args.batch, somma)
            prossimo_ckpt += args.ogni
    ce_tr = somma / len(train)
    ce_h = valuta(held); ce_hm = float(np.mean(list(ce_h.values())))
    spec = specificita(held)
    riga = {"epoca": ep, "train": ce_tr, "held": ce_hm, "spec_held": spec, "s": round(time.time() - t0),
            "held_per_lingua": {c[1]: round(v, 4) for c, v in ce_h.items()}}
    esito["curva"].append(riga)
    print(f"epoca {ep}: train {ce_tr:.4f} held {ce_hm:.4f} spec {spec:+.4f} ({riga['s']}s)", flush=True)
    if ce_hm < migliore:
        migliore, ferme = ce_hm, 0
        torch.save({"stato": testa.state_dict(), "esito": {"lettore": args.lettore, "testa": "transformer",
                    "h": args.h, "strati": args.strati, "teste": args.teste, "dropout": args.dropout},
                    "mu": mu, "sd": sd, "K": K, "lettore_stato": stato_lettore()}, PESI_F + ".tmp")
        os.replace(PESI_F + ".tmp", PESI_F)
    else:
        ferme += 1
    # pesi dell'ULTIMA epoca (per riprendere una corsa da dove era)
    torch.save({"stato": testa.state_dict(), "esito": {"lettore": args.lettore, "testa": "transformer",
                "h": args.h, "strati": args.strati, "teste": args.teste, "dropout": args.dropout},
                "mu": mu, "sd": sd, "K": K, "lettore_stato": stato_lettore()}, PESI_F.replace(".pt", "-ultimo.pt.tmp"))
    os.replace(PESI_F.replace(".pt", "-ultimo.pt.tmp"), PESI_F.replace(".pt", "-ultimo.pt"))
    esito["migliore_held"] = migliore
    esito["go_train"] = bool(ce_tr < args.go)
    json.dump(esito, open(ESITO_F, "w"), indent=1, ensure_ascii=False)
    if ep < args.epoche:
        salva_ckpt(ep + 1, np.arange(0), 0, 0.0)   # fine epoca: la ripresa parte dall'epoca dopo, pos 0, ordine nuovo
    if ferme >= args.pazienza and ce_tr < args.go:
        print("held-out fermo con train sotto GO: stop"); break
    if ferme >= args.pazienza * 2:
        print("held-out fermo a lungo: stop"); break
print(f"fine: migliore held {migliore:.4f}, esito in {ESITO_F}")

# --- griglie insegnante con i pesi MIGLIORI (held-out), per tutte le frasi (train e held)
if os.path.exists(PESI_F):
    pm = torch.load(PESI_F, map_location="cpu", weights_only=False)
    testa.load_state_dict(pm["stato"])
    if SBLOCCA and pm.get("lettore_stato"):
        lettore.load_state_dict({k: v.to(next(lettore.parameters()).device) for k, v in pm["lettore_stato"].items()}, strict=False)
testa.eval()
os.makedirs(f"{EAR}/insegnante", exist_ok=True)
with torch.no_grad():
    for c in sorted(testi):
        np.save(f"{EAR}/insegnante/{c[0]}.npy", par_di(c).detach().float().cpu().numpy())
json.dump({"pesi": PESI_F, "frase": FRASE, "n": len(testi), "quando": time.strftime("%F %T")},
          open(f"{EAR}/insegnante/INFO.json", "w"), indent=1, ensure_ascii=False)
print(f"griglie insegnante: {len(testi)} in {EAR}/insegnante/ (pesi {PESI_F})", flush=True)
