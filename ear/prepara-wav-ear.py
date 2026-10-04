#!/usr/bin/env python3
"""
EAR, passo 1: manifest dei 1000 WAV emotivi (/data/codec_training/emotion_wavs, 200 frasi italiane
x 5 voci: arrabbiata, calma, eccitata, felice, triste; scelta per il primo giro).
Scrive ear/dati/manifest-emotivi.jsonl, una riga per clip:
  {id, wav, testo, chiave_testo, emozione_dataset, lingua, split}
Split PER FRASE (le 5 voci di una frase stanno tutte dallo stesso lato): 20 frasi held-out = 100 clip
mai viste da nessuna fase. Seme fisso. Non carica modelli, non tocca la GPU.
Uso: python3 prepara-wav-ear.py
"""
import json
import os
import random

SORG = "/data/codec_training/emotion_wavs"
EAR = "/data/memoria-episodica-affettiva/ear"
N_HELD_FRASI = 20
SEME = 404

man = json.load(open(f"{SORG}/manifest.json"))
frasi = sorted({r["text_id"] for r in man})
held = set(random.Random(SEME).sample(frasi, N_HELD_FRASI))
os.makedirs(f"{EAR}/dati", exist_ok=True)
n = {"train": 0, "held": 0}
with open(f"{EAR}/dati/manifest-emotivi.jsonl", "w") as f:
    for r in man:
        wav = f"{SORG}/{r['file']}"
        assert os.path.exists(wav), wav
        split = "held" if r["text_id"] in held else "train"
        n[split] += 1
        f.write(json.dumps({"id": f"emo-{r['file'][:-4]}", "wav": wav, "testo": r["text"],
                            "chiave_testo": f"emo-t{r['text_id']:03d}", "emozione_dataset": r["emotion"],
                            "lingua": "it", "split": split}, ensure_ascii=False) + "\n")
json.dump({"seme": SEME, "frasi_held": sorted(held), "clip": n}, open(f"{EAR}/dati/split-emotivi.json", "w"), indent=1)
print(f"manifest: {sum(n.values())} clip ({n['train']} train, {n['held']} held-out), {len(frasi)} frasi, {len(held)} held-out")
