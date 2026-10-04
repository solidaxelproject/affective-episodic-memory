# Comandi EAR (training del canale audio)

Piano: EAR-PLAN.it.md nel repo. Tutto si lancia nella **pausa di fine epoca 2** di E8, GPU libera.
Un passo per volta. Cartella: `/data/memoria-episodica-affettiva/ear`.

## 0. Pausa di E8 a fine epoca 2

L'ordine `pausa` dice al protocollo: al test di fine epoca 2 (punto ep3-0) fai test e pagelle come sempre,
poi **non** rilanciare il training. Si piazza dalla dashboard (API `/api/ordine`, tipo `pausa`,
`al_punto` = `ep3-0`). Ripresa di E8, quando vuoi: `training`.

## 1. Manifest (già fatto il 04/10)

```
cd /data/memoria-episodica-affettiva/ear
python3 prepara-wav-ear.py
```
1000 clip, 900 train e 100 held-out (20 frasi mai viste, le 5 voci di ogni frase dallo stesso lato).

## 2. Trascrizione ASR + estrazione dai 4 modelli (venv separato ear-venv)

Prima la mappa delle emozioni: `mappa-emozioni.json` è una PROPOSTA, i valori vanno confermati.

Collaudo su 2 clip (stampa forme, trascrizione e emozione):
```
cd /data/memoria-episodica-affettiva/ear
/data/ear-venv/bin/python estrai-ear.py --prova 2
```
Tutte (riprende da dove era se si interrompe):
```
/data/ear-venv/bin/python estrai-ear.py
```
Uscite: `cache/asr-testo.jsonl` (trascrizioni: entrano nel codec come TESTO, niente ponte per l'ASR),
`cache/<modello>/<id>.npy` per CLAP, MERT, Dasheng, emotion2vec, `cache/e2v-prob.jsonl`.
Dopo il collaudo: `rm cache/asr-testo.jsonl cache/e2v-prob.jsonl` prima del giro completo (le righe di prova
non fanno danno, vince l'ultima, ma il file resta pulito).

## 2b. Ricordi richiamati dalle trascrizioni (canale mirato, solo lettura)

Dopo l'estrazione, per vedere quali ricordi evoca ogni trascrizione (serve solo l'embedder :8094, niente GPU):
```
cd /data/memoria-episodica-affettiva/ear
python3 richiamo_ear.py --cache --held          # le 100 clip held-out; senza --held tutte
python3 richiamo_ear.py "una frase qualsiasi"   # una frase a mano
```
Non inietta niente. Diario in `diario-richiamo-ear.jsonl`.

## 3. Fase 0, l'insegnante (codec E8 con "...sto udendo")

```
cd /data/memoria-episodica-affettiva/ear
MODELLO_35B=Accio-Lab/occamy-1.0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  /data/jspace/venv/bin/python -u addestra-insegnante-ear.py \
  --init /data/memoria-episodica-affettiva/gradino4/test-pagella/testa-e2e-e8-ep3-0.pt \
  --strati 8 --h 1024 --teste 8 --dropout 0.10 --lr 3e-05 --lr-lettore 1e-05 --sblocca-strati 13 \
  --batch 8 --n-train 1000 --n-held 20 --epoche 10 --pazienza 3 --tag ear-ins1 2>&1 | tee fase0/log-ear-ins1.txt
```
I pesi di partenza sono quelli del test di fine epoca 2 (ep3-0), estratti dal protocollo; se il riordino
non li ha ancora spostati sono in `gradino4/testa-e2e-e8-ep3-0.pt`.
Alla fine: `insegnante/emo-tNNN.npy` (200 griglie) e `fase0/testa-e2e-ear-ins1.pt`.
Riga di controllo all'avvio: `CE griglia spenta` (cambia rispetto a E8: la frase è diversa).

## 4. Fase 1, i ponti (Occamy spento)

Collaudo su 10 clip:
```
/data/jspace/venv/bin/python -u addestra-ear.py --fase 1 --insegnante fase0/testa-e2e-ear-ins1.pt \
  --tag ear-f1-prova --n-train 10 --epoche 1
```
Corsa vera:
```
/data/jspace/venv/bin/python -u addestra-ear.py --fase 1 --insegnante fase0/testa-e2e-ear-ins1.pt \
  --tag ear-f1 --epoche 30 2>&1 | tee corse/log-ear-f1.txt
```

## 5. Fase 2, codec a 5 ingressi (testo ASR + 4 neurali) + JEV

```
/data/jspace/venv/bin/python -u addestra-ear.py --fase 2 --insegnante fase0/testa-e2e-ear-ins1.pt \
  --init corse/ear-ear-f1.pt --tag ear-f2 --epoche 30 2>&1 | tee corse/log-ear-f2.txt
```

## 6. Fase 3, rifinitura con Occamy

```
MODELLO_35B=Accio-Lab/occamy-1.0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  /data/jspace/venv/bin/python -u addestra-ear.py --fase 3 --insegnante fase0/testa-e2e-ear-ins1.pt \
  --init corse/ear-ear-f2.pt --tag ear-f3 --epoche 5 --pazienza 2 2>&1 | tee corse/log-ear-f3.txt
```
~100 minuti per epoca (900 clip, ritmo di E8).

## 7. Pagella

```
MODELLO_35B=Accio-Lab/occamy-1.0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /data/jspace/venv/bin/python -u valuta-ear.py --pesi corse/ear-ear-f3.pt --tag ear-f3 --gen 14 \
  2>&1 | tee corse/log-valuta-ear-f3.txt
```
Si può fare anche dopo la fase 2 (`--pesi corse/ear-ear-f2.pt`).

## 8. Ripresa di E8

```
training
```

## Ripresa dopo un'interruzione

Ogni corsa salva un ckpt ogni 500 clip e a fine epoca: stesso comando + `--riprendi`.

## Spie

- `[spia] COLLASSO`: le uscite delle clip sono quasi tutte uguali (varianza fra clip sotto il 5% di quella
  dell'insegnante). Normale nelle prime letture della fase 1, non dopo.
- `[marcio]`: loss o gradienti non finiti, il lotto si salta.
