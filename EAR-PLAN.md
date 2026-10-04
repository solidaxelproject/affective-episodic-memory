# EAR: development plan for the audio codec

*Italian version: [EAR-PLAN.it.md](EAR-PLAN.it.md)*

Status: **design**. Development starts once the memory codec (E8) has finished training.
This document is updated at every step, together with the commits.

## Goal

EAR (an audio-video synesthetic network) converts audio into a **grid** injected into the visual channel of the
language model, the same way the memory codec does with text. In parallel it picks the **emotion** to inject
as a steering vector.

The base model is Occamy-1.0 (a post-training of Qwen3.6-35B-A3B), a vision-language model: its visual channel
accepts any continuous 81×2048 latent. EAR does not change the model's architecture and uses the same
injection point as the memory codec.

## Starting ideas

- **Vision Wormhole** (arXiv 2602.15382): communication between models through the latent space of the visual
  channel. It is the logic of the memory codec, reused here.
- **Learning to Hear by Seeing** (arXiv 2511.12077): a frozen vision-language model learns to hear through an
  audio encoder and an adapter that brings audio into the space of the visual tokens. Same approach.
- **Recursive Multi-Agent Systems** (arXiv 2604.25917): frozen models connected by light trained *outer links*,
  which carry last-layer states from one latent space to another without going through text.
  In EAR the outer links are the **bridges** between the audio models and the codec.
- **Jev-Mem** (arXiv 2609.23986): a fast "System One" controller makes the memory decisions (routing, candidate
  scoring, when to stop) without autoregressive generation; the slow "System Two" model steps in only for complex
  reasoning. EAR's **JEV** output follows the same idea: a typed decision in a single pass, the choice of one of 51
  emotions, without making the 35B model generate text.

## Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                      EAR CODEC  ·  ARCHITECTURE (5 inputs)                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

                                 AUDIO (16 kHz)
                                       ║
     ╔═════════════╦═══════════════╦═══╩═══════════╦═══════════════╦═════════════╗
     ║             ║               ║               ║               ║             ║
╔════╩═════╗ ╔═════╩════╗  ╔═══════╩══╗  ╔═════════╩╗  ╔═══════════╩╗            ║
║Qwen3-ASR ║ ║  CLAP    ║  ║  MERT    ║  ║ Dasheng  ║  ║emotion2vec ║    FROZEN
║  0.6B    ║ ║ (larger) ║  ║  95M     ║  ║  base    ║  ║ plus base  ║    (CPU)
║ words    ║ ║sound↔text║  ║ music    ║  ║ ambience ║  ║voice/emot. ║
║ d=1024   ║ ║ d=768    ║  ║ d=768    ║  ║ d=768    ║  ║ d=768      ║
╚════╦═════╝ ╚═════╦════╝  ╚═════╦════╝  ╚═════╦════╝  ╚═════╦══════╝
     ║ last layer  ║             ║             ║             ║
╔════╩═════╗ ╔═════╩════╗  ╔═════╩════╗  ╔═════╩════╗  ╔═════╩══════╗
║ BRIDGE 1 ║ ║ BRIDGE 2 ║  ║ BRIDGE 3 ║  ║ BRIDGE 4 ║  ║  BRIDGE 5  ║  TRAINED
║ W3h+W2·  ║ ║          ║  ║          ║  ║          ║  ║            ║  (RecursiveMAS
║ GELU(W1h)║ ║  →1024   ║  ║  →1024   ║  ║  →1024   ║  ║   →1024    ║  outer links)
║ +input#1 ║ ║ +input#2 ║  ║ +input#3 ║  ║ +input#4 ║  ║ +input#5   ║
╚════╦═════╝ ╚═════╦════╝  ╚═════╦════╝  ╚═════╦════╝  ╚═════╦══════╝
     ╚═════════════╩══════╦══════╩═════════════╩═════════════╝
                          ║  5 sequences side by side, each with its own
                          ║  input tag (they work simultaneously)
╔═════════════════════════╩════════════════════════════════════════════════════╗
║  e5 READER · 24 layers, d=1024                                               ║
║  ┄┄ layers 1-11: FROZEN, skipped by audio (they only serve text)             ║
║  ══ ENTRY POINT OF THE BRIDGES: input of layer 12                            ║
║  ██ layers 12-24: UNFROZEN (13)  ← learn to read the 5 inputs together       ║
╚═════════════════════════╦════════════════════════════════════════════════════╝
                          ║
╔═════════════════════════╩════════════════════════════════════════════════════╗
║  PERCEIVER HEAD · 8 layers, H=1024, 8 heads · K=8 learned queries            ║
╚════════════════╦═════════════════════════════════════════════╦═══════════════╝
                 ║                                             ║
╔════════════════╩═══════════════╗           ╔═════════════════╩═══════════════╗
║ OUTPUT 1 · VIDEO CHANNEL       ║           ║ OUTPUT 2 · JEV (emotion)        ║
║ par 8×2048 → BASE + POS @ par  ║           ║ 2048 vector → nearest of the    ║
║ grid 81×2048                   ║           ║ 51 anchors (steering vectors)   ║
║ "...sto udendo"                ║           ║ → emotion + dose (alpha inside  ║
╚════════════════╦═══════════════╝           ║   the measured window)          ║
                 ║                           ╚═════════════════╦═══════════════╝
╔════════════════╩═════════════════════════════════════════════╩═══════════════╗
║  OCCAMY 35B (frozen) · visual span at L0 ← grid                              ║
║                        emotion window ← steering vector × alpha              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### The five audio models (frozen)

| input | model | content | last-layer size |
|---|---|---|---|
| 1 | Qwen/Qwen3-ASR-0.6B | the words | 1024 |
| 2 | laion/larger_clap_music_and_speech | sound linked to text | 768 |
| 3 | m-a-p/MERT-v1-95M | music: timbre, rhythm, mood | 768 |
| 4 | mispeech/dasheng-base | ambient sounds | 768 |
| 5 | emotion2vec/emotion2vec_plus_base | the emotion in the voice | 768 |

Dasheng replaces BEATs. On the HEAR benchmark, which evaluates frozen encoders, it averages 78.9 against
71.1 for BEATs iter3+, and 80.2 against 73.2 on environmental sounds (arXiv 2406.06992). It also has public
weights on Hugging Face under Apache-2.0.

Larger versions exist (Qwen3-ASR-1.7B, MERT-v1-330M, emotion2vec_plus_large). We start from the small ones
for speed: all five run on CPU, about 500M parameters in total.

### The bridges

One bridge per model, shaped like the RecursiveMAS outer link:

    R(h) = W3·h + W2·GELU(W1·h)

The linear branch `W3` carries the vector from the audio model's space (768 or 1024) to the reader's space
(1024). The non-linear branch only corrects the difference between the two distributions. Each bridge adds a
learned input tag, so the codec knows which model each piece of the sequence comes from.
Each model's input is standardized (mean and standard deviation measured on the data).

### The codec

It is a copy of the memory codec:

- **reader** multilingual-e5-large, 24 layers. In the memory codec the first 11 are frozen and the last 13
  unfrozen. In EAR the bridges enter at **layer 12**, the start of the unfrozen part: audio skips the layers
  that only serve to read text;
- **Perceiver head**, 8 layers, H=1024, 8 heads, 8 learned queries.

### The two outputs

1. **Video channel**: `par` (8×2048) → grid = `BASE + POS @ par` (81×2048), injected into Occamy's visual span
   at L0. The grid is dressed with the text "...sto udendo" ("...I am hearing"), just as memories are dressed
   with "...ecco cosa mi ha fatto ricordare" ("...here is what made me remember").
2. **JEV (emotion)**: a 2048 vector. The chosen emotion is the one, among the 51 of Plutchik's wheel, whose
   steering vector is nearest: the 51 vectors already measured on Occamy act as fixed anchors. The strength of
   the choice gives the dose, always inside the injection window measured for that emotion.

## Training

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                             TRAINING (4 phases)                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ PHASE 0 · TEACHER                                                            ║
║   copy of the E8 codec (e5 24 layers, 13 unfrozen + Perceiver 8)             ║
║   retrained with the dressing "...sto udendo" on the paired texts            ║
║   → reference grids saved ONCE (text → par 8×2048)                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ PHASE 1 · BRIDGES (Occamy off, GPU almost free)                              ║
║   audio → 5 encoders → 5 bridges → same copy FROZEN → par                    ║
║   loss = distance from the teacher's par  ·  ONLY the 5 bridges are trained  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ PHASE 2 · 5-INPUT CODEC                                                      ║
║   unfreeze e5 layers 12-24 + Perceiver together with the bridges, same loss  ║
║   + JEV head: target = sum of the primaries' vectors weighted by the         ║
║     emotion2vec probabilities · loss = cosine + choice among the 51 anchors  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ PHASE 3 · FINE-TUNING (Occamy on)                                            ║
║   grid → visual span L0 → Occamy CE on the dressed text "...sto udendo"      ║
║   gradient on bridges + e5 12-24 + Perceiver                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

The logic is the wormhole's: teacher and student use the same codec. The teacher reads the **text** paired
with the audio (transcript, description of the sound or of the music) and produces the right grid. The student
starts from the **audio** and has to reach the same grid. Reference grids are computed only once, so phases 1
and 2 do not need the 35B model.

The rules learned while training the memory codec still apply: no Adam on bf16 weights, standardized inputs,
anti-collapse probes in every training run, frequent checkpoints.

### The emotion target

emotion2vec distinguishes about 9 classes, which fall on Plutchik's 8 primaries. The probability picks the
intensity of the primary (for example serenity, joy or ecstasy). The JEV head's target is the sum of the
primaries' steering vectors, weighted by the probabilities. This way the **dyads** (the compound emotions)
can be reached even without their own examples: a voice that is both joyful and trusting ends up near "love".

Measured on Occamy's vectors: how close each dyad is to the normalized sum of its two primaries.

| dyad | primaries | cosine | rank out of 51 |
|---|---|---|---|
| optimism | anticipation + joy | 0.52 | 6 |
| contempt | disgust + anger | 0.51 | 7 |
| awe | fear + surprise | 0.39 | 8 |
| love | joy + trust | 0.30 | 9 |
| remorse | sadness + disgust | 0.43 | 11 |
| aggressiveness | anger + anticipation | 0.36 | 11 |
| disapproval | surprise + sadness | -0.07 | 49 |
| submission | trust + fear | -0.66 | 51 |

Six dyads out of eight are reachable, two are not. The reason is that every emotion has its own layer window
(trust lives at layers 15-17, joy at 25-27) and the sums mix spaces from different layers. Submission and
disapproval need their own examples.

## Data

Audio + text pairs, each to be checked (license, languages, quality):

| type | candidates |
|---|---|
| speech | Common Voice |
| sounds | AudioCaps, Clotho |
| music | MusicCaps |
| emotional voice | IEMOCAP, ESD |

## Song recognition

Recognizing *which* song is playing is a different task, audio fingerprinting (Shazam, Chromaprint and
AcoustID, Dejavu, audfprint, Olaf). It needs a database of tracks and returns title and artist, not the
content. It stays outside the codec: possibly a separate module.

## Steps

- [x] Audio models chosen and downloaded (Dasheng instead of BEATs, after reading the papers)
- [x] Reference papers collected
- [x] Architecture and training logic designed
- [x] Emotion anchors measured (6 dyads out of 8 reachable)
- [ ] Script: extraction of the last layers of the 5 models (CPU) and disk cache
- [ ] Script: bridges, 5-input codec, JEV head
- [ ] Script: phase 0, retraining the codec copy with "...sto udendo"
- [ ] Paired dataset: choice, licenses, preparation, held-out per type
- [ ] Phase 0, teacher
- [ ] Phase 1, bridges
- [ ] Phase 2, 5-input codec + JEV
- [ ] Phase 3, fine-tuning with Occamy
- [ ] Report card: CE per audio type, correct emotion choice, listening test

## Open points

- Own examples for the dyads the anchors cannot reach (submission, disapproval).
- Long audio: windows in sequence, each grid conditioned on the previous one (RecursiveMAS recursion applied
  to time).
- Larger audio models: only if the small ones are not enough.
