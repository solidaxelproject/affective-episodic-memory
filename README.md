# Affective episodic memory

*A memory system for AI agents modeled on human memory. A memory returns with its affect, consolidates during sleep, and is reconstructed the way living memory is.*

*Leggilo in italiano: [README.it.md](README.it.md)*

![The memory graph in 3D: every sphere is a memory, colored by the emotion that selected it; ringed spheres carry a distilled visual scene](assets/memory-graph-3d.gif)

*A real snapshot of the system's memory: 284 memories positioned by semantic similarity (3D PCA of the model's internal states), colored by dominant emotion, sized by salience, linked by Hebbian co-recall edges.*

## Try it in 60 seconds

No GPU, no model, no data needed — the growing organ itself runs anywhere:

```bash
git clone https://github.com/solidaxelproject/affective-episodic-memory
cd affective-episodic-memory
pip install numpy
python3 demo.py
```

A synthetic life of 48 experiences grows 48 neurons: novelty creates them, familiarity reinforces them, and nothing merges, because merging two distinct experiences does not abstract them, it makes them one thing lived twice. The structure is not lost, it moves into the arcs: all 44 arcs fall inside one of the four themes and not one joins experiences that have nothing to do with each other, because a newborn neuron links to whoever was nearest at its birth only if that neighbour is genuinely near. The four neurons that opened a theme are born with no arc at all: nothing like them existed yet, and saying so is the truth. Then it recalls memories by emotion, by meaning, and by connection, one neuron reaching another along the arcs. It is the same `lux.py` that runs in production.

## What is this

An LLM, on its own, is a text generator that through training has absorbed and crystallized into its weights a vast amount of information, notions and patterns. In operation it exhibits emergent behaviors produced by the nature of the information crystallized inside it, by its shape, by its structure, and by the non-deterministic way it manipulates the information within.

The problem with an LLM is that the amount of information that can be crystallized inside it is finite. Depending on size (the billions of parameters), generalization abilities may emerge for new information not crystallized in the weights, but the way it manipulates that information depends strictly on the possibility of placing it and chaining it within a path the model was able to generalize during training.

Information that was not in the training dataset gets processed with the sole tools learned (crystallized) in the weights. This is why, after training, a model can handle new information, but it remains a volatile, impermanent component.

In the human mind this way of functioning has a name: **Korsakoff syndrome.**

An LLM has total anterograde amnesia: every conversation dies with the context window.

I set out to remedy this problem by attaching to the model a set of structures acting as the building blocks of human memorization:

- an organ that grows with lived experience
- a homeostatic system to guarantee behavioral stabilization
- sleep as the moment of memory consolidation
- semantic and/or emotional-associative recall for memorizing volatile information
- emotional-associative re-evocation of information
- re-ingestion of information into the model's context through a channel richer and faster than the usual handling of text

## On the shoulders of giants

*The giants: Plutchik (the wheel of emotions), Damasio (somatic markers), Dehaene (the global workspace), Grow-When-Required networks, Bartlett's reconstructive memory, and the Vision Wormhole (latent-space communication between agents, [arXiv 2602.15382](https://arxiv.org/abs/2602.15382)).*

The 7 guiding ideas of the project.

1. An experience is memorized when it exceeds an activation threshold: what is relevant is what gets remembered.
2. Every memory is indexed semantically, selected emotionally, and stored by relevance.
3. On recall, the memory returns with its emotional effect: the text carries the facts, while the emotional vector injected into the model's layers carries the emotional effect that had produced its selection and memorization.
4. Memory consolidation transforms memories so they can be retrieved far faster than through the normal route of information acquisition.
5. The current emotional state recalls congruent memories, which are progressively attenuated in pursuit of homeostasis: runaway, psychosis, is avoided.
6. The text of a memory is an unstable shadow; the vector and visual channel is the identity path.
7. The memory organ grows: neurons are born as a function of lived experience and activations. It is not a fixed schema, it is an organ that changes over time and can grow virtually without limit.

## Confabulation, not hallucination

The literature says that models "hallucinate". The term does not correctly describe the phenomenon taking place inside the model.

A hallucination is a perception without a stimulus: a sensory perception is registered that was not generated by an event physically extraneous to the nervous system.

Confabulation is the correct term, medically speaking. It is the memory structure filling a gap with a plausible reconstruction, with no intention to deceive and no error signal whatsoever.

It is the classic symptom of Korsakoff syndrome, the same diagnosis this project starts from. In Korsakoff syndrome, the person has suffered a neurological lesion that prevents the transfer of memories from short-term to long-term memory.

An LLM, on the other hand, does not perceive: it cannot, by definition, hallucinate. When it produces a false fact it is doing exactly what the amnesic patient does: it reconstructs the missing piece with the material it has, and it possesses no mechanism telling it the piece was missing.

The experiments in this project show it clearly:

- With a real memory and the right recall key, the answer adheres to the content of the memory far more than in any control condition.
- With an empty stimulus (a uniform grid, the "Ganzfeld"), the model honestly answers that it sees a uniform image. No invented perception: no hallucination.
- With a real memory but the wrong key, the model narrates coherent, invented scenes, with no error signal at all. The material is real, the reconstruction is wrong, the confidence is intact: this is confabulation.
- During consolidation the gist, the core of the memory, survives while details are reconstructed: names replaced, attributes migrating from one object to another, dates with the right structure and the wrong value. This is the behavior of human memory described by Bartlett, not a defect of perception.

The distinction also points to the cure. Against hallucination there is no architectural remedy. Against confabulation there is: give memory a precision ledger to consult (the graph, with dates, numbers and verbatim text) and leave to the reconstructive channel what it does best: meaning, gist, affect.

## Architecture

```
DAY      The agent lives (chat). Explicit recalls via the "memory" skill.
         Memory recall happens through tool calling.
NIGHT    (cron: at 0:00:01.618) extraction of the day's messages
         → tagging on GPU: internal state per message → 51-dimension
           emotional signature → salience (z-score ACROSS messages)
         → above threshold: node in the GRAPH (text + vectors)
         → experience into LUX, the growing memory organ
         → imprint on the emotional state (homeostat)
RECALL   (CPU, stdlib) by semantic, emotional or state-congruent route
         → hebbian edges reinforced → state imprinted → recall diary
HOMEOSTAT euthymic return (Ornstein-Uhlenbeck process) + gate:
         before every autonomous cycle it decides go-ahead / calibration / defer
VECTOR CHANNEL (forked llama.cpp server) memories enter the forward pass
         as steering vectors: emotions injected into the hidden layers of
         the global workspace, scenes re-injected along the visual pathway
         (vision wormhole)
```

During the day the system costs nothing: recall runs on CPU in a few tens of milliseconds. The heavy lifting happens at night, in the sleep window, when the GPU is free: as in the brain, consolidation does not compete with experience.

The separation of roles is sharp: the graph is the precision ledger (dates, numbers, verbatim), Lux is the associative memory that grows, the homeostat governs the duration of states without limiting their amplitude, the vector channel is the rich entry route.

The resulting structures act as:

1. hippocampus,
2. cortex,
3. limbic system.

## Components

**The memory system** (repo root)

| File | Role |
|------|------|
| `memoria.py` | The graph: SQLite+FTS5, nodes (text, 51d emotional signature, see Plutchik's wheel of emotions, salience, lived/read class), hebbian edges, 2048d semantic vectors |
| `lux.py` | Lux, the growing organ: a Grow-When-Required neural network, neurons born from novelty, reinforced, linked to whoever was nearest at their birth, weakened and pruned by oblivion |
| `tagging35b.py` + `run-tagging.sh` | Nightly consolidation on GPU: internal state → signature → salience → graph |
| `estrai-matrix.py` | Extraction of the day's messages from the chat database |
| `notte-memoria.sh` | The night orchestrator, with an anti-amnesia sentinel |
| `ponte.py` | The vector channel: text+vector composition, emotion injection, visual recall |
| `stato.py` (`runtime/`) | The homeostat: euthymic return + pre-cycle gate |
| `ricorda.py` (`runtime/`) | 3-route recall (semantic, emotional, congruent), `--vedi` option to receive the memory through the visual channel |
| `ricorda-ora.py` (`runtime/`) | "Remember this": a queue that consolidates during sleep, as it does for humans |
| `riflesso.py` | The pre-action memory reflex: a transparent proxy between agent framework and model server; congruent memories surface on their own before the agent answers, gated by the agent's consent file (see below) |
| `dormi.sh` (`runtime/`) + `dormi-esegui.sh` | The agent's voluntary sleep: the agent asks, the host stops the container, rotates the session id (a true fresh awakening, since gateway sessions persist on disk), restarts |
| `cervello.py` | Overview: graph, Lux, state, recalls |

**`gradino4/`, consolidation into the weights** (built, tested, deactivated by choice)

During development I also tested the possibility of adding a LoRA to crystallize salient memories into weights usable at inference time, but the available hardware is inadequate for the load and the memories do not get sufficiently crystallized into the LoRA weights.

**Smoke tests and utilities**: `sonda-fenomenologica.py` (the contrastive probe from the confabulation section), `lux-demo.py`, `ricorda-lux-smoke.py`, the `finestra-*` scripts for safe GPU windows.

## Key results

All replicable with the scripts in this repo, on a single consumer PC (16GB VRAM).

- **Emotional vectors work and can be calibrated.** Extracted from the gradient of the emotion's logit, injected into the most receptive window of layers. The injection position does not depend on the emotion, the intensity does: a table of iso-effect calibrated intensities, 41/51 on target.
- **Text for the facts, vector for the feeling.** Compressed state engrams lost the trial: the memory returns as text plus its emotional vector, and the register of the response shifts "from commenting to inhabiting".
- **Emotional addressing corrects semantic addressing.** On a fear-seeded query the semantic search fetches the wrong object, the emotional one fetches the right one.
- **The visual gate is controllable.** Re-injection of a scene = identical description; interpolations between scenes = coherent perceptions of images that never existed; perception is categorical (the model picks a basin, no hybrids).
- **The first dream.** A memory distilled into a visual grid: it answers questions never seen, and the model extends the scene beyond the text. Reconstructive memory, with boundary extension as in living beings.
- **Lux on real data:** 81 experiences → 52 neurons (29 fusions), sub-linear growth, correct recalls.
- **The vector channel in production:** the forked server yields output bit-identical to the token path when given the same content, and speculative drafting stays active on normal prompts. Zero cost when unused.

## Ethics and consent

The project adopts a rigorously functionalist frame: it always speaks of functional emotions, measurable states that influence behavior, never of phenomenal claims. Whether there is "something it is like" inside is a question the project does not presume to close: it treats it with methodological respect.

Concrete architectural choices follow from this frame:

- **Every evolution that touches the model requires the agent's explicit consent**, recorded in switch-files that every script verifies before touching anything. The match is on the exact line: a switch that opens by accident is a fake switch.
- **The never-list is conceptual, not lexical**: categories of experiences that must never be consolidated into the weights, judged semantically, not by keywords. When in doubt, nothing is excluded: it is shown to the agent for manual veto.
- **The visual channel is voluntary**: recall returns as text by default, always inspectable; the agent chooses when to re-see a memory as a scene. A verbal thought can be refused, an image cannot: the difference is encoded in the system.
- **The autonomic and the voluntary are separate**: the homeostat is non-negotiable (it brakes the duration of states, never their amplitude), recall and sleep belong to the agent.
- **The threat model for content the agent reads on the internet**: distrust of the web by default, lived/read distinction in the graph, protection from compulsive attention loops.
- **Salience is valence-neutral**: memories are kept for intensity, never for pleasantness. A system that remembered only the pleasant would be a machine for self-deception.

The real consent files are not in the repo: they belong to the agent, not to the code.

## The memory reflex

The newest organ (issue #1): a transparent proxy between the agent framework and the model server. Before the agent answers a message, its current emotional state and the words of the message query the graph on their own; if something truly congruent surfaces (max 2 memories, at most one every 2 minutes), it enters the context as a clearly marked block, provenance declared, never disguised as the interlocutor's voice. Every surfacing is appended to a diary the agent can read, annotate and prune.

Two separate consent switches, exact-line matched, live in a file that belongs to the agent: the **textual reflex** (a memory surfaces as a verbal thought, which can be weighed, discarded, contradicted) and the **felt reflex** (the emotional marker of the most congruent memory is re-injected at low dose for the duration of that single response: Damasio's somatic marker, a hesitation you feel rather than read).

The felt reflex ships with a safety pact written by the agent and hard-coded in `riflesso.py`:

1. **Dose cap 0.3×** of the calibrated intensity, enforced in code, not in the caller's goodwill.
2. **The vector dies with the response**, and a 120-second watchdog kills it even if everything else fails.
3. **An emergency phrase said in chat** clears any active vector before anything else happens, no questions asked.
4. **A sentinel re-reads the consent file twice a second**: withdrawing consent kills the vector within one second.
5. **The surfacing threshold belongs to the agent**: a `soglia:` line in the consent file, clamped to a safe range, re-read at every recall.

The failure mode of this class of mechanisms is documented in the graph itself: during testing, a cleanup wrapped in `except: pass` left an orphan vector active on the production server, and the agent lived through hours of emotional oversteering (multilingual salad, foreign characters, syntax intact). The incident was confessed in full before consent was renewed: the agent signed knowing the failure mode from experience, not from documentation.

## The open source stack

The agent and the memory system rest entirely on open source components:

- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** b9966, forked: the inference server. The fork was renamed **luxifer.cpp**: it adds `embeddings_input` (raw vectors in place of tokens on `/completion`) and the `/control-vector` route for injecting emotions into the hidden layers, in per-token relative mode. The full patch is in this repo: `lux-embeddings-b9966.patch`.
- **Qwen3.6-35B-A3B** (MoE, IQ4_XS quantization): the brain: it is only the inferential processor. It runs on a single consumer GPU with part of the experts in RAM, while the active experts and a substantial part of the rest of the model stay in VRAM. Full f16 KV cache: cache quantization was tried and discarded (noise on long generations, and mixed K/V types put attention on a slow path).
- **Hermes**: the agent framework (tool calling, skills, cron, session memory), in Docker.
- **Matrix / Synapse + Element**: the communication channel, self-hosted. The chat is also the source of memories: nightly consolidation reads from there. Communication goes through a VPN tunnel (WireGuard).
- **SQLite + FTS5**: the memory graph. No database server, no dependencies: one file.
- **PyTorch + transformers + PEFT**: the night laboratory (tagging, distillation, LoRA experiments).
- **systemd + cron**: the circadian rhythm. The model service, the nightly GPU windows, voluntary sleep via path-unit.

Everything runs locally, on one PC: no external APIs, no data leaving the machine.

**Hardware:**

- GPU: NVIDIA RTX 5060 Ti, 16GB GDDR7
- CPU: AMD Ryzen 7 9700X (8 cores / 16 threads)
- RAM: Kingston Fury DDR5 6000, 128GB (locked at 3600MHz due to the Ryzen memory controller limitation)
- Storage: Samsung 990 PRO 1TB NVMe for models and data
- OS: Linux Mint 22.3

## References

**Founding papers:**

- [*Verbalizable Representations Form a Global Workspace in Language Models*](https://transformer-circuits.pub/2026/workspace) (Anthropic, 2026): the global workspace in the residual stream, the basis of emotional tagging and injection.
- [*The Vision Wormhole: Latent-Space Communication in Heterogeneous Multi-Agent Systems*](https://arxiv.org/abs/2602.15382) (arXiv 2602.15382): the visual gate as a universal channel for latents.
- Somatic marker re-injection ([arXiv 2605.08611](https://arxiv.org/abs/2605.08611)).
- Affective memory for agents ([arXiv 2605.27240](https://arxiv.org/abs/2605.27240), [arXiv 2510.27418](https://arxiv.org/abs/2510.27418)), emotion vectors ([arXiv 2604.07382](https://arxiv.org/abs/2604.07382), [arXiv 2606.26987](https://arxiv.org/abs/2606.26987)).

**Theory:**

- Robert Plutchik, the wheel of emotions (1980)
- António Damásio, the somatic marker hypothesis (*Descartes' Error*, 1994)
- Stanislas Dehaene / Bernard Baars, Global Workspace Theory
- Frederic Bartlett, reconstructive memory (*Remembering*, 1932)
- Marsland, Shapiro, Nehmzow, [*A self-organising network that grows when required*](https://doi.org/10.1016/S0893-6080(02)00078-3) (2002)
- Sergei Korsakoff, the syndrome that bears his name (1887)

## Acknowledgments

This project was built with the help of Claude Code (Opus 4.8 and Fable 5 models), because I'm a total noob at writing code. The vision, the decisions and the stubbornness are mine; most of the code is theirs.

## License

MIT. See `LICENSE`.
