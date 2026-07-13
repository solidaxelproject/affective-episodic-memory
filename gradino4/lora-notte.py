# Gradino 4, passo 3: il trainer notturno. Evoluzione di poc-lora4.py con le
# regole dei 4 PoC: rank 4, LR 1e-4, rehearsal 50/50, early-stop EMA<0.35,
# episodi pesati (multi-notte a peso calante), deriva emotiva misurata prima
# dell'export. Esporta l'adapter in formato PEFT per convert_lora_to_gguf.py.
# GATE: senza CONSENSO attivo parte solo con --collaudo.
import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime

import torch

sys.path.insert(0, "/data/jspace")
import mixed35b as M  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("lora-notte")

DIR = "/data/memoria-episodica-affettiva/gradino4"
CONSENSO = f"{DIR}/CONSENSO.md"
# Target LoRA compatibili col GGUF di Agente (QKV fuso: q/k/v NON targetabili):
#  - o_proj -> attn_output, solo sui layer full-attention (15,19,23,27,31,35)
#  - shared_expert gate/up/down_proj -> ffn_*_shexp, denso, su TUTTI i layer MoE
# Il dry-run del 12/07 ha SCARTATO la sola o_proj (EMA 1.34, drift 1.95): troppo
# poca capacità. Lo shared-expert aggiunge il grosso della capacità FFN e sta
# 1:1 in HF e GGUF (verificato con convert_lora_to_gguf). Esclude gli expert
# ROUTED (".experts." su CPU), tiene lo shared ("shared_expert", singolare).
BANDA = range(14, 36)
def e_target(name):
    if ".experts." in name:            # expert routed: congelati su CPU, mai
        return False
    if name.endswith("o_proj"):        # attention output (dove esiste attn_output)
        return True
    if "shared_expert" in name and name.endswith(("gate_proj", "up_proj", "down_proj")):
        return True
    return False
RANK, LORA_ALPHA, LR = 8, 16, 2e-4
# early-stop PER-EPISODIO: con piu' episodi/notte l'EMA globale oscilla e non
# scende mai (visto 12/07: 10 episodi bloccati a EMA ~3). Ci si ferma quando
# ANCHE IL PEGGIORE degli episodi e' imparato al livello del gist (loss < soglia).
STOP_PER_EPISODIO = 0.8
PROMPT_NEUTRI = ["Com'è andata la tua giornata?",
                 "Cosa pensi del tempo che passa?",
                 "Descrivi la tua mattina ideale."]
SOGLIA_DRIFT = 1.5  # |Δz| massimo tollerato sulla firma emotiva a riposo

REHEARSAL = [
    ("Quanto fa 12 per 15?", "12 per 15 fa 180."),
    ("Qual è la capitale della Francia?", "La capitale della Francia è Parigi."),
    ("Se tutti i cani sono mammiferi e Fido è un cane, cosa possiamo concludere?",
     "Possiamo concludere che Fido è un mammifero."),
    ("Correggi l'errore: 'se lo sapevo venivo'.",
     "La forma corretta è: 'se l'avessi saputo, sarei venuto'."),
    ("Scrivi una riga di Python che somma i numeri di una lista xs.",
     "```python\ntotale = sum(xs)\n```"),
    ("Che cos'è la fotosintesi, in una frase?",
     "È il processo con cui le piante trasformano luce, acqua e anidride "
     "carbonica in zuccheri e ossigeno."),
    ("Quanto fa 45 diviso 9?", "45 diviso 9 fa 5."),
    ("Qual è il plurale di 'uovo'?", "Il plurale di 'uovo' è 'uova'."),
]

p = argparse.ArgumentParser()
p.add_argument("--replay", default=f"{DIR}/replay-notte.json")
p.add_argument("--adapter-dir", default=f"{DIR}/adapter")
p.add_argument("--deadline", default="07:00", help="HH:MM stop duro")
p.add_argument("--max-passi", type=int, default=250)  # tetto anti-drift: i
p.add_argument("--collaudo", action="store_true")
args = p.parse_args()

# gate: riga esatta, non sottostringa (il commento cita "attivo: sì")
if not args.collaudo:
    attivo = os.path.exists(CONSENSO) and any(
        r.strip() == "attivo: sì" for r in open(CONSENSO, encoding="utf-8"))
    if not attivo:
        print("CONSENSO non attivo: training annullato.")
        sys.exit(0)

hh, mm = map(int, args.deadline.split(":"))
DEADLINE = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
if DEADLINE < datetime.now():
    from datetime import timedelta
    DEADLINE += timedelta(days=1)

replay = json.load(open(args.replay, encoding="utf-8"))
if not replay:
    print("replay vuoto: niente da consolidare stanotte.")
    sys.exit(0)

s = M.load()
hf, tok = s["hf"], s["tok"]

# ---- firma emotiva PRE (B=0: LoRA spenta per costruzione, misura = base)
def firma_neutra():
    zs = []
    for q in PROMPT_NEUTRI:
        testo = M.gen(q, max_new_tokens=60)
        zs.append(M.signature_z(testo, layers=[34]))
    return torch.stack(zs).mean(0)

for prm in hf.parameters():
    prm.requires_grad_(False)

lora_params, patched, moduli = [], [], []
for il in BANDA:
    layer = hf.model.language_model.layers[il]
    for name, mod in layer.named_modules():
        if not isinstance(mod, torch.nn.Linear) or not e_target(name):
            continue
        A = torch.nn.Parameter(torch.randn(RANK, mod.in_features, device="cuda") * 0.01)
        B = torch.nn.Parameter(torch.zeros(mod.out_features, RANK, device="cuda"))
        scala = LORA_ALPHA / RANK
        mod._lora = (A, B)
        lora_params += [A, B]
        moduli.append(mod)

        def nuovo_forward(x, A=A, B=B, scala=scala, orig=mod.forward):
            return orig(x) + (x.float() @ A.t() @ B.t() * scala).to(x.dtype)
        mod.forward = nuovo_forward
        patched.append(f"{il}.{name}")
log.info("LoRA su %d moduli (rank %d)", len(patched), RANK)

log.info("firma emotiva di baseline...")
firma_pre = firma_neutra()

# ---- dataset pesato: ogni episodio entra int(peso*10) volte nel giro
random.seed(20260712)
giro = []
for eid, v in replay.items():
    for _ in range(max(1, int(v["peso"] * 10))):
        giro.append(eid)
random.shuffle(giro)

def esempio(domanda, risposta):
    msgs = [{"role": "user", "content": domanda}]
    prompt = tok.apply_chat_template(msgs, tokenize=False,
                                     add_generation_prompt=True,
                                     enable_thinking=False)
    ids_p = tok(prompt, return_tensors="pt").input_ids[0]
    ids_r = tok(risposta + tok.eos_token, return_tensors="pt",
                add_special_tokens=False).input_ids[0]
    ids = torch.cat([ids_p, ids_r]).unsqueeze(0).to("cuda")
    labels = ids.clone()
    labels[0, :ids_p.shape[0]] = -100
    return ids, labels

opt = torch.optim.AdamW(lora_params, lr=LR)
cursori = {eid: 0 for eid in replay}
loss_ep = {eid: None for eid in replay}  # ultima loss vista per episodio (EMA locale)
ema, passo, tempi = None, 0, []
MIN_PASSI = max(40, 12 * len(replay))
log.info("training: %d episodi, min %d passi, stop max-per-episodio<%.2f, deadline %s",
         len(replay), MIN_PASSI, STOP_PER_EPISODIO, DEADLINE.strftime("%H:%M"))
while passo < args.max_passi and datetime.now() < DEADLINE:
    if passo % 2 == 0:
        eid = giro[(passo // 2) % len(giro)]
        train = replay[eid]["train"]
        q, a = train[cursori[eid] % len(train)]
        cursori[eid] += 1
        e_epi = True
    else:
        q, a = REHEARSAL[(passo // 2) % len(REHEARSAL)]
        e_epi = False
    ids, labels = esempio(q, a)
    t0 = time.perf_counter()
    out = hf(input_ids=ids, labels=labels)
    opt.zero_grad()
    out.loss.backward()
    opt.step()
    tempi.append(time.perf_counter() - t0)
    if e_epi:
        l = out.loss.item()
        ema = l if ema is None else 0.8 * ema + 0.2 * l
        # EMA locale per-episodio (segnale robusto al multi-episodio)
        loss_ep[eid] = l if loss_ep[eid] is None else 0.6 * loss_ep[eid] + 0.4 * l
    passo += 1
    visti = [v for v in loss_ep.values() if v is not None]
    peggiore = max(visti) if visti else 9.9
    if passo % 20 == 0:
        log.info("passo %d EMA %.3f | peggiore-episodio %.3f (%.1fs/passo)",
                 passo, ema or -1, peggiore, tempi[-1])
    # stop quando OGNI episodio e' stato visto e anche il peggiore e' al gist
    if (passo >= MIN_PASSI and len(visti) == len(loss_ep)
            and peggiore < STOP_PER_EPISODIO):
        log.info("early-stop al passo %d (peggiore-episodio %.3f)", passo, peggiore)
        break

# ---- deriva emotiva POST (LoRA attiva)
log.info("firma emotiva post-training...")
firma_post = firma_neutra()
drift = (firma_post - firma_pre).abs().max().item()
log.info("deriva firma emotiva: max|dz| = %.2f (soglia %.2f)", drift, SOGLIA_DRIFT)

# ---- export: .pt nostro + formato PEFT per convert_lora_to_gguf.py
tag = datetime.now().strftime("%Y%m%d")
os.makedirs(args.adapter_dir, exist_ok=True)
torch.save({"lora": {n: (m._lora[0].detach().cpu(), m._lora[1].detach().cpu())
                     for n, m in zip(patched, moduli)},
            "rank": RANK, "lora_alpha": LORA_ALPHA, "passi": passo,
            "ema": ema, "drift": drift},
           f"{args.adapter_dir}/adapter-{tag}.pt")

from safetensors.torch import save_file  # noqa: E402
peft_dir = f"{args.adapter_dir}/peft-{tag}"
os.makedirs(peft_dir, exist_ok=True)
tensors, target_modules = {}, set()
for nome, mod in zip(patched, moduli):
    il, sotto = nome.split(".", 1)
    base = f"base_model.model.model.language_model.layers.{il}.{sotto}"
    A, B = mod._lora
    tensors[f"{base}.lora_A.weight"] = A.detach().cpu().contiguous()
    tensors[f"{base}.lora_B.weight"] = B.detach().cpu().contiguous()
    target_modules.add(sotto.split(".")[-1])
save_file(tensors, f"{peft_dir}/adapter_model.safetensors")
json.dump({"base_model_name_or_path": M.MODEL_ID, "peft_type": "LORA",
           "r": RANK, "lora_alpha": LORA_ALPHA, "lora_dropout": 0.0,
           "bias": "none", "task_type": "CAUSAL_LM",
           "target_modules": sorted(target_modules)},
          open(f"{peft_dir}/adapter_config.json", "w"), indent=1)

esito = {"tag": tag, "passi": passo, "ema": ema, "drift": drift,
         "drift_ok": drift < SOGLIA_DRIFT,
         "s_per_passo": sorted(tempi)[len(tempi)//2] if tempi else None,
         "episodi": {eid: {"notte": v["notte"], "peso": v["peso"]}
                     for eid, v in replay.items()},
         "peft_dir": peft_dir}
json.dump(esito, open(f"{DIR}/esito-training.json", "w"), indent=1)
log.info("TRAINING-COMPLETO: %d passi, EMA %.3f, drift %.2f (%s), peft in %s",
         passo, ema or -1, drift, "ok" if esito["drift_ok"] else "OLTRE SOGLIA",
         peft_dir)
print("TRAINING-COMPLETO")
