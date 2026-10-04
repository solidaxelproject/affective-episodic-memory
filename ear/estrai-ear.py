#!/usr/bin/env python3
"""
EAR, passo 2: trascrizione ASR + estrazione dell'ultimo layer dei 4 modelli audio congelati, una clip alla volta, su disco.
Gira nel venv SEPARATO /data/ear-venv (transformers 4.57.6, qwen_asr, funasr, nnAudio): il venv di
jspace (training E8) non si tocca. Un modello per volta (poca memoria), riprende da dove era: salta le clip
gia' fatte per quel modello.
  asr      Qwen3-ASR-1.7B, SOLO la trascrizione in ear/cache/asr-testo.jsonl: entra nel codec come TESTO
           (lettore e5) e serve al recupero dei ricordi (bge-m3, canale mirato). Scelta di progetto.
Uscite dei 4 modelli in ear/cache/<modello>/<id>.npy, float16, forma (T, d) con T <= --max-token (media a finestre):
  clap     laion/larger_clap_music_and_speech, ultimo stato dell'encoder audio (d=768)
  mert     m-a-p/MERT-v1-95M, ultimo layer (d=768, audio a 24 kHz)
  dasheng  mispeech/dasheng-base, ultimo layer (d=768)
  e2v      emotion2vec_plus_base, feature a livello di frame (d=768)
In piu': ear/cache/e2v-prob.jsonl (probabilita' delle 9 classi: bersaglio del JEV).
Uso (a training del codec dei ricordi in pausa: la GPU e' una sola):
  /data/ear-venv/bin/python estrai-ear.py --prova 2        # collaudo: 2 clip, stampa le forme
  /data/ear-venv/bin/python estrai-ear.py                  # tutte
  opzioni: --modelli asr,clap,...  --dev cuda|cpu  --max-token 64
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch
import torchaudio

ap = argparse.ArgumentParser()
ap.add_argument("--modelli", default="asr,clap,mert,dasheng,e2v")
ap.add_argument("--dev", default="cuda" if torch.cuda.is_available() else "cpu")
ap.add_argument("--max-token", type=int, default=64, help="token per ingresso: 4 x 64 = 256, + 256 di testo = 512 del lettore")
ap.add_argument("--prova", type=int, default=0, help="solo le prime N clip, stampa le forme")
args = ap.parse_args()

EAR = "/data/memoria-episodica-affettiva/ear"
HF = "/data/jspace/hf/hub"
ASR_PATH = "/data/models/Qwen3-ASR-1.7B"


def snap(repo):
    d = f"{HF}/models--{repo.replace('/', '--')}/snapshots"
    return f"{d}/{sorted(os.listdir(d))[-1]}"


def unit_attiva(nome):
    import subprocess
    return subprocess.run(["systemctl", "--user", "is-active", nome], capture_output=True, text=True).stdout.strip() == "active"


if args.dev == "cuda" and unit_attiva("addestra-e2e"):
    print("addestra-e2e (E8) e' ATTIVA: la GPU e' sua. Metti E8 in pausa o usa --dev cpu."); sys.exit(1)

clip = [json.loads(r) for r in open(f"{EAR}/dati/manifest-emotivi.jsonl")]
if args.prova:
    clip = clip[:args.prova]
_audio = {}


def audio(c, sr):
    """WAV mono float32 ricampionato a sr (i WAV sorgente sono a 24 kHz)."""
    k = (c["id"], sr)
    if k not in _audio:
        x, s0 = sf.read(c["wav"], dtype="float32")
        if x.ndim > 1:
            x = x.mean(1)
        if s0 != sr:
            x = torchaudio.functional.resample(torch.from_numpy(x).unsqueeze(0), s0, sr).squeeze(0).numpy()
        _audio[k] = x
    return _audio[k]


def riduci(h, n):
    """(T, d) -> (<=n, d): media a finestre contigue (adaptive avg pool sul tempo)."""
    h = h.float()
    if h.shape[0] <= n:
        return h
    return torch.nn.functional.adaptive_avg_pool1d(h.T.unsqueeze(0), n)[0].T


def salva(nome, c, h):
    h = riduci(h.detach().cpu(), args.max_token)
    assert torch.isfinite(h).all(), (nome, c["id"])
    np.save(f"{EAR}/cache/{nome}/{c['id']}.npy", h.numpy().astype(np.float16))
    if args.prova:
        print(f"  {nome} {c['id']}: {tuple(h.shape)}  media {h.mean():+.3f} dev {h.std():.3f}")


def da_fare(nome):
    if nome == "asr":                      # l'ASR scrive solo la trascrizione
        f = f"{EAR}/cache/asr-testo.jsonl"
        fatti = {json.loads(r)["id"] for r in open(f, encoding="utf-8")} if os.path.exists(f) else set()
        return [c for c in clip if args.prova or c["id"] not in fatti]
    os.makedirs(f"{EAR}/cache/{nome}", exist_ok=True)
    return [c for c in clip if args.prova or not os.path.exists(f"{EAR}/cache/{nome}/{c['id']}.npy")]


def giro(nome, carica, estrai):
    lista = da_fare(nome)
    if not lista:
        print(f"{nome}: gia' fatto"); return
    t0 = time.time()
    m = carica()
    for i, c in enumerate(lista):
        with torch.no_grad():
            h = estrai(m, c)
            if h is not None:
                salva(nome, c, h)
        if (i + 1) % 50 == 0:
            print(f"  {nome}: {i+1}/{len(lista)} ({time.time()-t0:.0f}s)", flush=True)
    print(f"{nome}: {len(lista)} clip in {time.time()-t0:.0f}s", flush=True)
    del m
    if args.dev == "cuda":
        torch.cuda.empty_cache()


# --- 1. Qwen3-ASR-1.7B: SOLO la trascrizione (va nel codec come testo, niente ponte neurale)
def carica_asr():
    from qwen_asr.core.transformers_backend.configuration_qwen3_asr import Qwen3ASRConfig
    from qwen_asr.core.transformers_backend.modeling_qwen3_asr import Qwen3ASRForConditionalGeneration
    from qwen_asr.core.transformers_backend.processing_qwen3_asr import Qwen3ASRProcessor
    cfg = Qwen3ASRConfig.from_pretrained(ASR_PATH)
    dt = torch.float16 if args.dev == "cuda" else torch.float32
    asr = Qwen3ASRForConditionalGeneration.from_pretrained(ASR_PATH, config=cfg, dtype=dt).to(args.dev).eval()
    return asr, Qwen3ASRProcessor.from_pretrained(ASR_PATH)


def estrai_asr(m, c):
    asr, proc = m
    prompt = proc.apply_chat_template([{"role": "system", "content": ""}, {"role": "user", "content": [{"type": "audio", "audio": ""}]}],
                                      add_generation_prompt=True, tokenize=False)
    inp = proc(text=[prompt], audio=[audio(c, 16000)], return_tensors="pt", padding=True)
    inp = {k: (v.to(args.dev).to(asr.dtype) if v.is_floating_point() else v.to(args.dev)) for k, v in inp.items()}
    out = asr.generate(**inp, max_new_tokens=128, do_sample=False)
    testo = proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    with open(f"{EAR}/cache/asr-testo.jsonl", "a") as f:
        f.write(json.dumps({"id": c["id"], "trascritto": testo, "vero": c["testo"]}, ensure_ascii=False) + "\n")
    if args.prova:
        print(f"  asr testo: {testo!r}")
    return None


# --- 2. CLAP (48 kHz): ultimo stato dell'encoder audio HTSAT, appiattito in sequenza (T, 768)
def carica_clap():
    from transformers import ClapModel, ClapProcessor
    p = snap("laion/larger_clap_music_and_speech")
    return ClapModel.from_pretrained(p).to(args.dev).eval(), ClapProcessor.from_pretrained(p)


def estrai_clap(m, c):
    model, proc = m
    inp = proc(audios=[audio(c, 48000)], sampling_rate=48000, return_tensors="pt").to(args.dev)
    out = model.audio_model(input_features=inp["input_features"], is_longer=inp.get("is_longer"))
    h = out.last_hidden_state[0]
    if h.dim() == 3:                       # (768, f, t) -> (f*t, 768)
        h = h.flatten(1).T
    return h if h.shape[-1] == 768 else h.T


# --- 3. MERT-v1-95M (24 kHz): ultimo layer (T, 768)
def carica_mert():
    from transformers import AutoModel, Wav2Vec2FeatureExtractor
    p = snap("m-a-p/MERT-v1-95M")
    return AutoModel.from_pretrained(p, trust_remote_code=True).to(args.dev).eval(), Wav2Vec2FeatureExtractor.from_pretrained(p, trust_remote_code=True)


def estrai_mert(m, c):
    model, fe = m
    inp = fe(audio(c, fe.sampling_rate), sampling_rate=fe.sampling_rate, return_tensors="pt").to(args.dev)
    return model(**inp).last_hidden_state[0]


# --- 4. Dasheng-base (16 kHz): ultimo layer (T, 768)
def carica_dasheng():
    from transformers import AutoFeatureExtractor, AutoModel
    p = snap("mispeech/dasheng-base")
    return AutoModel.from_pretrained(p, trust_remote_code=True).to(args.dev).eval(), AutoFeatureExtractor.from_pretrained(p, trust_remote_code=True)


def estrai_dasheng(m, c):
    model, fe = m
    inp = fe(audio(c, 16000), sampling_rate=16000, return_tensors="pt")
    return model(inp["input_values"].to(args.dev)).hidden_states[0]


# --- 5. emotion2vec_plus_base (16 kHz, FunASR): frame (T, 768) + probabilita' delle 9 classi
def carica_e2v():
    from funasr import AutoModel
    return AutoModel(model=snap("emotion2vec/emotion2vec_plus_base"), device=args.dev, disable_update=True)


def estrai_e2v(m, c):
    x = audio(c, 16000)
    fr = m.generate(x, fs=16000, granularity="frame", extract_embedding=True)[0]
    ut = m.generate(x, fs=16000, granularity="utterance", extract_embedding=False)[0]
    with open(f"{EAR}/cache/e2v-prob.jsonl", "a") as f:
        f.write(json.dumps({"id": c["id"], "etichette": ut["labels"], "prob": [float(s) for s in ut["scores"]]}, ensure_ascii=False) + "\n")
    if args.prova:
        print(f"  e2v: {max(zip(ut['scores'], ut['labels']))}")
    return torch.as_tensor(np.asarray(fr["feats"]))


GIRI = {"asr": (carica_asr, estrai_asr), "clap": (carica_clap, estrai_clap), "mert": (carica_mert, estrai_mert),
        "dasheng": (carica_dasheng, estrai_dasheng), "e2v": (carica_e2v, estrai_e2v)}
print(f"EAR estrazione: {len(clip)} clip, modelli {args.modelli}, dev {args.dev}, max {args.max_token} token")
for nome in args.modelli.split(","):
    giro(nome, *GIRI[nome])
print("fine")
