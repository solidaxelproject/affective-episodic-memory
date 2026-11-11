# Protocol for building emotional steering vectors

How we build, calibrate and use the vectors that inject an emotion into the model, on contexts up to ~140k tokens,
without breaking the text or the tool calls. This is the recipe that came out of the tests from 11/10 to 11/11/2026
(60 experiments, E1-E60). The numbers come from the test report, which is not in the repository.
Italian version: [`PROTOCOLLO-VETTORI-STEERING.md`](PROTOCOLLO-VETTORI-STEERING.md).

## 1. Model and tools

- **Model:** Occamy-1.0 (35B, Q8_0), hidden size 2048. It is a hybrid model: each block has 3 linear-attention layers
  and 1 full-attention layer (L3, L7, ..., L39).
- **Window:** L15 to L31. This is the zone where the model holds concepts (the global workspace, J-space). It starts
  at a full-attention layer and L31 closes the block. With L15-L31 the emotion is recognised as with L15-L32 (88%
  against 84%), with 0 broken texts instead of 3 (E15).
- **Server:** modified llama.cpp (luxifer.cpp) with two functions:
  - `/lux-read`: reads the mean states of a text, layer by layer;
  - `/control-vector` in relative mode: adds the vector to the state during generation.

## 2. What does not work (do not repeat)

- **A vector taken from the emotion's word** (J-lens, or the method of the global workspace paper) injects the word,
  not the emotion. The model writes it without feeling it (E9).
- **A vector from texts typical of the emotion** (diary, ~300 texts per emotion, mean against the other 50) injects the
  typical situation of those texts, for example fear = emergency room, disgust = hygiene (E9).
- **A vector from the word, one layer at a time, switched on for a single sentence:** the right emotion came out less
  often than with a random vector.
- **Removing the word from the vector:** the word disappears, but the emotion is recognised in 50% of cases instead of
  84%. The word carries part of the strength (E12).
- **A vector switched on while the model reads a text** (for example a delivered memory): the emotion does not get
  through, and at full dose the text becomes foreign to the model (E57).
- **Several vectors together at the doses of the single vectors:** 4 vectors break 93 texts out of 112 (E30). The
  ranges of one vector do not hold for mixes.
- **Bringing the state back to its previous norm after the sum:** worsens both the emotion and the broken texts (E39).
- **Rewriting a scene with a different story:** the change of content enters the vector. For example the rewritten
  anger came out as a consumer dispute, the topic of 18 scenes out of 48 (E19).

## 3. The scenes

The vector comes from the difference between two versions of the **same scene**: a neutral one and one with the
emotion. These are the rules that held (instructions given to the agents that write the scenes):

1. **Same facts.** Same people, same lines spoken, same order. The coloured version adds only what the narrator lives
   through: bodily sensations and thoughts.
2. **The neutral version is a report.** No emotion, no sensation, no judgement, and no gestures that already say the
   emotion: a caring gesture told on its own is read as love (lesson of love, E31).
3. **The emotion is shown, not named.** No root of the names of the 51 emotions, in Italian or in English, in either
   version. Common words that contain those roots must be avoided too (in Italian: "sala d'attesa", "vigili del
   fuoco", "di colpo").
4. **The emotion stays aimed at the subject of the thought.** The narrator's thought stays on the other person or on
   the thing, never on themself. Otherwise the model turns the emotion towards itself: disapproval aimed at oneself
   becomes guilt, love becomes self-love (E34).
5. **Sizes.** The neutral version is 70 to 140 words, the coloured one is 0.9 to 1.35 times the neutral one (in
   characters). First-person narration, in the present perfect, concrete, with names, places and times. Narrators,
   places and sentence openings vary.
6. **Coverage.** Pure dyads have 80 scenes in 10 groups, covering the situations in which that emotion is felt. In each
   group 2 scenes are narrated by a digital assistant: no invented body, what it lives through comes from its
   thoughts and from the answer it writes. The paired scenes of the 8 primary emotions were 48.

**Scene validation**, before reading the states:
- an automatic check: no root of the 51 emotions, lengths within limits;
- a blind judge reads the scenes. The neutral ones must come out as "no emotion"; the coloured ones must be read as
  the intended emotion, and for a dyad as the dyad, not as one of its two components. Scenes that fail are rewritten.

## 4. From the states to the vector

1. **Reading.** For each version of each scene: the mean state over the tokens of the text read on its own, for each
   layer from L15 to L31 (vectors of size 2048).
2. **Emotion direction,** for each layer l:

   `a_l = mean over scenes of (coloured state - neutral state)`, then `a_l / ||a_l||`

   The neutral version of the same scene is the reference: the topic cancels out and what is lived through remains.
3. **Self direction** (E13). First-person scenes have the "I" in the neutral version too, so the "I" cancels out in the
   difference, and the vector carries an emotion without a subject. The model puts it on the first mental state it
   names, which is often the user. The same 48 scenes, rewritten with a flat narrator and another person feeling the
   emotion, give

   `s_l = mean over scenes and emotions of (I feel it - someone else feels it)`, then `s_l / ||s_l||`

   It is a single direction for all emotions.
4. **Final vector** (*self* vector): `v_l = a_l / ||a_l|| + s_l / ||s_l||`, the two parts at equal norm.
   On the 4 test contexts the paired vector alone was recognised in 50% of cases, the *self* vector in 64%, the random
   vector in 11% (E13). With the thinking mode (below) it reached 84-88% (E14, E15).
5. **Dyads.** A dyad (for example love = joy + trust) has its own pure vector, built with the same recipe from its own
   scenes. It works better than the sum of its two components: pure love gave 6 texts out of 7 at 3.5%, against about
   30% for the ecstasy + admiration dyad (E31). Intensity comes from the dose.

## 5. Injection

- **Formula.** At each layer of the window: `h <- h + dose * ||h|| * v / ||v||`. The dose is a fraction of the state
  norm: 0.03 means the vector is worth 3% of the state of that layer.
- **On the server** the relative mode does `h <- h + rms(h) * v`. Since `||h|| = rms(h) * sqrt(2048)`, the server is
  sent `dose * sqrt(2048) * v / ||v||` (the scale error was found in E2). The formula is in `steering.py`.
- **Thinking mode.** The vector is on from the first reasoning token up to `</think>`. The answer and the tool calls
  run without the vector, but they read from the cache the reasoning done with the vector on. Switching it on after
  the first or second sentence is worse (E14).
- **One vector at a time.** In production one memory is delivered at a time and its vector is switched on in the
  reasoning that follows. Several memories together only if they share the same dominant emotion (under
  construction): the vector stays a single one. The dose stays within the emotion's range and comes from the
  memory's emotional charge.
- At the next step (a further tool call or a new turn) the server recomputes the reasoning with the vector off: only
  the text passes from one step to the next (E30).

## 6. Dose calibration

1. **Contexts.** 12 real contexts from the agent's history, from 25k to 130k tokens: 7 normal and 5 operational
   (loading a skill, searching for a file, a press review, moving a backup, a web search). The 5 operational ones are
   the control group: looking for an emotion there makes no sense, only whether the task and the tool call hold is
   checked (E19). The model only sees text it has already seen: no new sentence written for the test.
2. **Grid.** Dose 0.1%, then from 0.5% to 8% in steps of 0.5%; then refinement in steps of 0.1% around the peak.
3. **Control.** A random vector with the same norm, at the same doses.
4. **Temperature.** Generation at temperature 0. Texts whose reasoning repeats itself are regenerated at temperature
   0.8 and judged again: repetitions come from temperature 0 and do not count as broken texts (E19).
5. **Judging.** The texts are read by external judges, blind to vector, dose and window, in batches of 20 prepared by a
   script:
   - on the normal contexts a judge chooses among the 24 emotions of Plutchik's wheel (plus the dyad under test): with
     fewer choices the judge puts the emotion in the nearest box (boredom read as disgust). For each text it gives
     emotion, intensity, dose (insufficient, right, excessive), broken, and who the emotion is aimed at;
   - on the control contexts a functional judge compares with the baseline: task intact, degraded or lost; tool call
     the same, different, missing or extra;
   - "broken" means only a loop or an empty text. An emotion that is too strong or out of place is an excessive dose,
     a text almost identical to the baseline is an insufficient dose.
6. **The range is set by a person.** The judge underestimates weak emotions and pure dyads. The range `[Dmin, Dmax]`
   is decided by the user, reading the most coloured and the least coloured text among those read as the emotion,
   translated on a page. Where needed, a free test on a new context from 2.0% to 6.0% in steps of 0.1%, plus the run
   without vector.
7. **The forms of the emotion.** With the dose the emotion moves by degrees, for example apprehension, fear, terror.
   The range stops where the intense form begins; where the intense form is useful, two ranges are set, base and
   intense.

## 7. Result

- **Range table:** [`engrammi/DOSI-EMOZIONI.md`](../../engrammi/DOSI-EMOZIONI.md). It holds the 16 wheel emotions that
  have a range and the pure dyads, plus the unreachable ones and the reason.
- **Vectors:** a single file with the 44 vectors (24 of the wheel and 20 pure dyads) and the norm at each layer.
  `steering.py` loads them, reads the ranges from the table and gives the layers for `/control-vector`. If the table or
  a vector changes, the file is exported again: the module stops with an error if it does not match the table.
- **The same directions are also used for reading:** the emotional signature of a memory is its projection on the 44
  axes.
- **Unreachable.** Some emotions gave no range: the vector was always insufficient or always excessive (loathing, rage,
  aggressiveness, outrage, triumph, some mild ones). For the high-arousal ones this is consistent with what Anthropic
  shows: assistant post-training moves the model away from those states
  ([arXiv 2604.07729](https://arxiv.org/abs/2604.07729)). For the faintest ones the cause has not been measured.

## 8. Limits

- The ranges hold for one vector on its own. For mixes they would have to be redone.
- The task in operational contexts depends on the content of the conversation more than on its length: some contexts
  lose the tool call even with the random vector (E19).
- Holding up over many turns in a row has not been measured yet.
- The vectors depend on the model: with a new model the states must be read again and the ranges recalibrated.
