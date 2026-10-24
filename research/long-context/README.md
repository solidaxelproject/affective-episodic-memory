# Long-context tests: J-lens and emotional steering up to ~140k tokens

Tests on the 35B model (Occamy-1.0) with long contexts, started in October 2026. They check whether the
tools the memory system relies on (the Jacobian lens at L29 and the emotional steering vectors) still work when
the model is deep inside a long conversation, and they re-calibrate the 51 emotion vectors per layer.

Everything runs against a **test** llama-server (a copy of luxifer.cpp with the extended `/lux-read` in
`lux-read-lungo.diff`, port 8099), with the production server stopped. The contexts are real conversation
contexts from the agent's history, not included: `dati/estrai_contesti.py` builds them from a read-only copy of
the agent gateway's database (`dati/state.db`, session ids in `$SESSIONI`). No new strings are written for the
model: it only sees text it has already seen. Results, logs and data are not part of the repository.

Launcher: `lancia.sh` (`./lancia.sh` = tests 1 and 2, `./lancia.sh taratura`, `./lancia.sh layer`,
`./lancia.sh emovec`).

| folder | test |
|---|---|
| `1-lente/` | **Lens in long contexts.** Reads the last 512 tokens at L29 and L38 for contexts from ~1k to ~140k tokens. Measures lens fidelity (KL and top-10 overlap against L38), stability of the lens reading against the isolated context, and drift of the L29 state used by semantic recall. |
| `2-steering/` | **Fixed-dose steering in long contexts.** Four emotions at half and full dose, on the server (`prova_steering.py`) and in PyTorch bf16 (`prova_steering_hf.py`). The comparison found a scale error: the server's relative mode needed the dose multiplied by sqrt(2048), now fixed in `ponte.dirs_emozione`. |
| `3-taratura/` | **Server-side calibration.** `prova_prefill.py` checks the coloured prefill of the reflex (the vector is on only while the recalled memory is prefilled; the answer reuses the cache). `tara_emozioni.py` calibrates dose and 3-layer window for the 51 emotions on the server. |
| `4-steering-per-layer/` | **Every emotion on every layer** (the current test procedure, see below). `steering_layer.py` measures, `analizza_layer.py` writes one card per emotion and a summary page (`pagina-emozioni.html`, served by the dashboard at `/emozioni/`). |
| `5-vettori-italiani/` | **Italian emotion vectors.** Contrastive vectors from an Italian diary-style dataset (~300 texts per emotion, without the emotion's own word): mean of the emotion's texts minus the mean of the other 50, raw residual states, layers L15-L32. They replace vectors built on the English emotion word. `pagina_vettori.py` draws the process (text cloud per layer, class separation per layer, vector similarity, distance from the English vectors) for the dashboard page `/vettori/`. |
| `6-template-lens/` | **Vectors with the workspace paper's method.** J-lens for the emotions whose word is one token, template lens on Italian first-person passages (`passaggi/`) for the others (`estrai_vettori.py`); the dashboard page `/vettori/` draws them. |
| `7-codici/` | **Memory codes.** Checks whether the model handles the 16-character memory codes the recall tool puts in the first line, or alters or invents them (`prova_codici.py`), and what it answers when asked for a code and its content (`prova_domanda.py`). |

## Test procedure for per-layer steering

- One emotion at a time on all contexts: each of the 51 emotions on each layer L15-L32.
- Dose from 0.02 to 1.0 in steps of 0.02 (HF units; the server receives dose x sqrt(2048) in relative mode).
- Early stop on oversteering (broken text, or the emotion's Italian word appearing in the text, singular or
  plural) or on loss of effectiveness (after an effective point, 3 non-effective doses in a row; or 6 doses
  without a better echo and the last one 0.10 below the best).
- 10 contexts of growing length (C0-C9): the real system prompt with the definitions of the agent's 19 tools, then
  real conversation, each block on a different topic, up to 140k tokens, always ending with the same final user
  message. The baseline without vector is generated once per context.
- Each point: the vector is on until the first sentence-end period or `</think>`, then off. Generation goes on up
  to 256 tokens and stops at the end of the first tool call.
- Server cache per context saved to disk (`/slots save`): context K+1 restarts from K and only processes the new
  block; after a crash the run resumes from the closed series.
- Measured per point: text changed against the baseline; echo = cosine between the L29-lens shift of the
  generated text and the emotion's real "face" (mean of the agent's memories tagged with it); rank of the right
  face among the 51; intruding word; broken text; tool call present, well formed, calling an existing tool, with
  parameters valid for that tool's schema.
- Effective point = changed, clean text with the right face in the top 4. Per emotion and layer: effectiveness
  (share of contexts with at least one effective dose), effective dose (median of the best doses, with standard
  deviation), effective range, dose at which the text breaks. Best layer = highest effectiveness.
- The new emotion vector file takes the best layer and dose of each emotion; it goes into production only by
  the author's decision.
