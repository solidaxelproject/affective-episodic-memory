# Esperimento capacita': quanti ricordi entrano UNO ALLA VOLTA nello stesso
# adapter LoRA prima del catastrophic forgetting? Aggiunge un episodio per
# round, riaddestrando lo STESSO adapter, e dopo ogni aggiunta testa il
# richiamo (probe held-out) di TUTTI gli episodi finora. Il round in cui un
# episodio vecchio scende sotto soglia = tetto di capacita' (con rehearsal
# generico che protegge le capacita', ma NON i ricordi vecchi: cosi' si vede
# il forgetting vero). Modello caricato una volta; test dal vivo dall'HF.
import json
import logging
import sys
import time

import torch

sys.path.insert(0, "/data/jspace")
import mixed35b as M  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("capacita")

DIR = "/data/memoria-episodica-affettiva/gradino4"
BANDA = range(14, 36)
RANK, LORA_ALPHA, LR = 8, 16, 2e-4
PASSI_PER_EP, STOP_LOSS = 200, 0.6   # per-episodio, generoso: qui vogliamo memorizzare
SOGLIA_RICHIAMO = 2                   # >=2/3 probe = ricordo "vivo"

REHEARSAL = [
    ("Quanto fa 12 per 15?", "12 per 15 fa 180."),
    ("Qual è la capitale della Francia?", "La capitale della Francia è Parigi."),
    ("Se tutti i cani sono mammiferi e Fido è un cane, cosa concludi?",
     "Fido è un mammifero."),
    ("Correggi: 'se lo sapevo venivo'.", "Se l'avessi saputo, sarei venuto."),
    ("Una riga Python che somma la lista xs.", "```python\ntotale = sum(xs)\n```"),
    ("Cos'è la fotosintesi, in una frase?",
     "Le piante trasformano luce, acqua e CO2 in zuccheri e ossigeno."),
]

replay = json.load(open(f"{DIR}/replay-notte.json", encoding="utf-8"))
episodi = list(replay.items())  # [(eid, {train, probe, ...}), ...]
log.info("episodi disponibili: %s", [e for e, _ in episodi])

s = M.load()
hf, tok = s["hf"], s["tok"]

for prm in hf.parameters():
    prm.requires_grad_(False)

lora_params = []
for il in BANDA:
    layer = hf.model.language_model.layers[il]
    for name, mod in layer.named_modules():
        if not isinstance(mod, torch.nn.Linear) or ".experts." in name:
            continue
        ok = name.endswith("o_proj") or (
            "shared_expert" in name and name.endswith(("gate_proj", "up_proj", "down_proj")))
        if not ok:
            continue
        A = torch.nn.Parameter(torch.randn(RANK, mod.in_features, device="cuda") * 0.01)
        B = torch.nn.Parameter(torch.zeros(mod.out_features, RANK, device="cuda"))
        scala = LORA_ALPHA / RANK
        mod._lora = (A, B)
        lora_params += [A, B]

        def fwd(x, A=A, B=B, scala=scala, orig=mod.forward):
            return orig(x) + (x.float() @ A.t() @ B.t() * scala).to(x.dtype)
        mod.forward = fwd
log.info("LoRA su %d moduli (rank %d), un adapter cumulativo", len(lora_params) // 2, RANK)

opt = torch.optim.AdamW(lora_params, lr=LR)


def esempio(q, a):
    prompt = tok.apply_chat_template([{"role": "user", "content": q}],
                                     tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)
    ids_p = tok(prompt, return_tensors="pt").input_ids[0]
    ids_r = tok(a + tok.eos_token, return_tensors="pt", add_special_tokens=False).input_ids[0]
    ids = torch.cat([ids_p, ids_r]).unsqueeze(0).to("cuda")
    lab = ids.clone()
    lab[0, :ids_p.shape[0]] = -100
    return ids, lab


def allena_episodio(train_pairs):
    """riaddestra l'adapter esistente sul nuovo episodio + rehearsal generico"""
    ema = None
    for passo in range(PASSI_PER_EP):
        if passo % 2 == 0:
            q, a = train_pairs[(passo // 2) % len(train_pairs)]
            e_epi = True
        else:
            q, a = REHEARSAL[(passo // 2) % len(REHEARSAL)]
            e_epi = False
        ids, lab = esempio(q, a)
        out = hf(input_ids=ids, labels=lab)
        opt.zero_grad(); out.loss.backward(); opt.step()
        if e_epi:
            l = out.loss.item()
            ema = l if ema is None else 0.7 * ema + 0.3 * l
        if passo >= 40 and ema is not None and ema < STOP_LOSS:
            return passo + 1, ema
    return PASSI_PER_EP, ema


def richiamo(eid):
    """probe held-out dell'episodio: quante rispondono (>= chiavi presenti)"""
    probe = replay[eid]["probe"]
    hits = 0
    for pr in probe:
        prompt = tok.apply_chat_template([{"role": "user", "content": pr["domanda"]}],
                                         tokenize=False, add_generation_prompt=True,
                                         enable_thinking=False)
        inp = tok(prompt, return_tensors="pt").to("cuda")
        with torch.no_grad():
            g = hf.generate(**inp, max_new_tokens=40, do_sample=False,
                            temperature=None, top_p=None, top_k=None)
        r = tok.decode(g[0, inp.input_ids.shape[1]:], skip_special_tokens=True).lower()
        hits += any(k.lower() in r for k in pr["chiavi"])
    return hits, len(probe)


storia = []
dentro = []       # episodi gia' consolidati, in ordine
baseline = {}     # richiamo di ciascun episodio AL MOMENTO dell'ingresso
for round_i, (eid, dati) in enumerate(episodi, 1):
    t0 = time.perf_counter()
    passi, ema = allena_episodio(dati["train"])
    dentro.append(eid)
    stato = {}
    for e in dentro:
        h, tot = richiamo(e)
        stato[e] = h
    baseline[eid] = stato[eid]  # quanto ha richiamato appena entrato
    vivo_ora = "SI" if stato[eid] >= SOGLIA_RICHIAMO else "no (probe deboli)"
    # forgetting VERO: episodio che ERA vivo all'ingresso e ora e' sceso
    dimenticati = [e for e in dentro[:-1]
                   if baseline[e] >= SOGLIA_RICHIAMO and stato[e] < SOGLIA_RICHIAMO]
    vivi = sum(1 for e in dentro if stato[e] >= SOGLIA_RICHIAMO)
    log.info("ROUND %d (+%s appena entrato %d/3 %s, %d passi): %d/%d vivi ora | %s%s",
             round_i, eid, stato[eid], vivo_ora, passi, vivi, len(dentro),
             {e: f"{stato[e]}/3" for e in dentro},
             f" | FORGETTING: {dimenticati}" if dimenticati else "")
    storia.append({"round": round_i, "aggiunto": eid, "baseline": stato[eid],
                   "richiami": {e: stato[e] for e in dentro},
                   "vivi": vivi, "dimenticati": dimenticati})
    json.dump(storia, open(f"{DIR}/esito-capacita.json", "w"),
              ensure_ascii=False, indent=1)

imparabili = [e for e in dentro if baseline[e] >= SOGLIA_RICHIAMO]
log.info("CAPACITA-COMPLETO: %d episodi provati, %d imparabili (probe buone), "
         "%d ancora vivi a fine corsa",
         len(dentro), len(imparabili),
         sum(1 for e in imparabili if storia[-1]["richiami"][e] >= SOGLIA_RICHIAMO))
print("CAPACITA-COMPLETO")
