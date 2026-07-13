# CLI di richiamo dalla memoria affettiva. CPU-only, istantaneo.
# Uso: recall.py --emo gioia [-k 3]        richiamo per emozione
#      recall.py --testo "backup" [-k 3]   richiamo per contenuto
#      recall.py --stats
import argparse
import json
import sys

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import memoria

p = argparse.ArgumentParser()
p.add_argument("--emo")
p.add_argument("--testo")
p.add_argument("-k", type=int, default=3)
p.add_argument("--stats", action="store_true")
p.add_argument("--json", action="store_true")
args = p.parse_args()

if args.stats:
    print(json.dumps(memoria.stats(), ensure_ascii=False, indent=1))
    sys.exit(0)

if args.emo:
    out = memoria.recall(args.emo, mode="emotiva", k=args.k)
elif args.testo:
    out = memoria.recall(args.testo, mode="testo", k=args.k)
else:
    p.error("serve --emo, --testo o --stats")

if args.json:
    print(json.dumps(out, ensure_ascii=False, indent=1))
else:
    for r in out:
        print(f"[{r['score']:.3f}] ({r['emo_tag']} α{r['emo_alpha']}) {r['testo']}")
