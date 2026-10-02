# Richiami del giorno -> Lux (30/09, PIANO-PERSISTENZA-LUX.md, fase 1, punto F).
# I richiami della vita quotidiana passano dal GRAFO (riflesso.richiama, runtime/ricorda.py),
# non da Lux: senza questo passaggio nessun ricordo richiamato di giorno stabilizzerebbe il suo
# neurone, e l'oblio di Lux vedrebbe solo il tagging. Qui ogni richiamo del giorno diventa una
# riattivazione vissuta del neurone che contiene quel nodo (mappa nodo -> neurone di lux-meta.json):
# attivazioni +1, ultimo_uso = ora del richiamo, rinforza() (stabilita' secondo la spaziatura).
# Fonti: diario-richiami.jsonl (ricorda.py, campo "risultati") e diario-riflessi.jsonl (riflesso,
# campo "nid", scritto dal 30/09; le righe piu' vecchie hanno solo il testo e si saltano).
# Un marcatore evita di contare due volte lo stesso richiamo. Primo giro senza marcatore: si parte
# da ADESSO (la storia di luglio e' gia' dentro le attivazioni e nella stabilita' iniziale).
# Uso (notte-memoria.sh, PRIMA del tagging): venv/bin/python sincronizza-richiami.py [--dry]
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/data/memoria-episodica-affettiva")
import lux as L  # noqa: E402

MEM = Path("/data/workspace/memoria")
DIARI = ((MEM / "diario-richiami.jsonl", "risultati"), (MEM / "diario-riflessi.jsonl", "nid"))
MARCATORE = MEM / ".ultima-sincronia-richiami"


def richiami_dal(t0):
    """[(ts, [nodi])] di tutti i diari dopo t0, in ordine di tempo"""
    out = []
    for path, campo in DIARI:
        if not path.exists():
            continue
        for riga in open(path, encoding="utf-8"):
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            nodi = d.get(campo)
            if d.get("ts", 0) > t0 and isinstance(nodi, list) and nodi:
                out.append((float(d["ts"]), [int(n) for n in nodi]))
    return sorted(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry", action="store_true", help="resoconto senza scrivere")
    a = p.parse_args()
    adesso = time.time()
    try:
        t0 = float(MARCATORE.read_text().strip())
    except (OSError, ValueError):
        t0 = adesso
        print("primo giro: nessun marcatore, parto da adesso")
    eventi = richiami_dal(t0)
    g = L.Lux()
    neurone_di = {}
    for uid, nodi in g.nodi.items():
        for n in nodi:
            neurone_di[int(n)] = uid
    riga = {str(u): i for i, u in enumerate(g.ids)}
    toccati, senza = {}, 0
    for ts, nodi in eventi:
        for n in set(nodi):
            uid = neurone_di.get(n)
            if uid is None or uid not in riga:
                senza += 1          # nodo "letto" o mai entrato in Lux
                continue
            i = riga[uid]
            g.attivazioni[i] += 1
            g.ultimo_uso[i] = max(g.ultimo_uso[i], ts)
            toccati[i] = toccati.get(i, 0) + 1
    s_prima = {i: float(g.stabilita[i]) for i in toccati}
    for i in toccati:               # una riattivazione vissuta per neurone per notte
        g.rinforza(i)
    print(f"richiami dal {time.strftime('%d/%m %H:%M', time.localtime(t0))}: {len(eventi)} eventi, "
          f"{len(toccati)} neuroni rinforzati, {senza} nodi senza neurone")
    for i in sorted(toccati, key=lambda j: -toccati[j])[:10]:
        print(f"  neurone {g.ids[i]}: {toccati[i]} richiami, S {s_prima[i]:.1f} -> {g.stabilita[i]:.1f}")
    if a.dry:
        print("DRY: niente scritto")
        return
    if toccati:
        g.salva()
    MARCATORE.write_text(f"{adesso}\n")
    print("SINCRONIA-COMPLETA")


if __name__ == "__main__":
    main()
