#!/usr/bin/env python3
"""!verifica emotiva! (VERIFICA-VIA-EMOTIVA.md, l'utente 11/11): legge il diario delle letture della via emotiva (1.19.0)
e il Lux, e per ogni decisione della tabella mette i dati veri accanto al valore deciso. Sola lettura.
Le scelte si RIGIOCANO con altri k e a: dai candidati salvati (parole e senso) e dai profili del Lux; i ricordi gia'
nella conversazione non sono nel diario, quindi il rigiocato e' il primo candidato sopra soglia (lo dice "uguale_al_vero").
  --ricordi-nuovi: accordo della traduzione sui ricordi nati dopo l'addestramento (legge /lux-read del 35B, sola lettura)
Uso: cd engrammi && /data/venv-spacy/bin/python verifica_via_emotiva.py [--ricordi-nuovi]"""
import json
import os
import sys

import numpy as np

import lux_engrammi as LE
import via_emotiva as VE


def un(v):
    return v / (np.linalg.norm(v) + 1e-9)


def carica_diario():
    righe = []
    for r in open(VE.DIARIO, encoding="utf-8"):
        try:
            righe.append(json.loads(r))
        except ValueError:
            pass
    return righe


def scegli(cand, acc, k, soglia):
    tot = [(n, p * max(0.0, 1 + k * a)) for (n, p, _), a in zip(cand, acc)]
    tot = [x for x in tot if x[1] >= soglia]
    return max(tot, key=lambda x: x[1])[0] if tot else None


def main():
    tr = VE.traduzione()
    if not os.path.exists(VE.DIARIO):
        print(f"il diario {VE.DIARIO} non c'e' ancora: nessuna lettura in produzione")
        return
    righe = carica_diario()
    errori = [r for r in righe if "errore" in r]
    letture = [r for r in righe if "lettura" in r]
    fonti = [r for r in letture if "candidati" in r]
    out = {"righe": len(righe), "errori": len(errori), "letture_per_chi": {}, "letture_per_flusso": {}}
    for r in letture:
        out["letture_per_chi"][r["chi"]] = out["letture_per_chi"].get(r["chi"], 0) + 1
        out["letture_per_flusso"][r["flusso"]] = out["letture_per_flusso"].get(r["flusso"], 0) + 1
    if letture:
        out["dal"], out["al"] = letture[0]["ts"], letture[-1]["ts"]
    calma = tr["calma"]
    # impronta p = 0.12: l'umore vero lettura per lettura
    U = np.array([r["umore_dopo"] for r in letture]) if letture else np.zeros((0, 44))
    if len(U) > 1:
        out["impronta"] = {"deciso": VE.IMPRONTA,
                           "umore_uguale_alla_lettura_dopo": round(float(np.mean([un(a - calma) @ un(b - calma)
                                                                                  for a, b in zip(U[:-1], U[1:])])), 3),
                           "distanza_media_dalla_calma": round(float(np.linalg.norm(U - calma, axis=1).mean()), 3),
                           "letture_al_tetto": int((np.abs(U) >= 3.5 - 1e-6).any(1).sum())}
    # intensita': il valore normale di D
    D = [r["D"] for r in fonti]
    if D:
        out["intensita"] = {"D_normale_in_uso": round(float(tr["D_normale"]), 4), "D_mediana_vera": round(float(np.median(D)), 4),
                            "D_percentili_10_90": [round(float(x), 3) for x in np.percentile(D, [10, 90])],
                            "k_usati_percentili_10_50_90": [round(float(x), 3) for x in np.percentile([r["k"] for r in fonti], [10, 50, 90])]}
    # riparazione: periodi di letture negative di fila
    periodi = []
    serie = [r["riparazione"]["di_fila"] for r in letture]
    for a, b in zip(serie, serie[1:] + [0]):
        if a > 0 and b == 0:
            periodi.append(a)
    out["riparazione"] = {"soglia_in_uso": round(float(tr["ripara_soglia"]), 4), "di_fila_per_accendere": VE.RIPARA_DI_FILA,
                          "periodi_negativi": len(periodi), "lunghezza_mediana": float(np.median(periodi)) if periodi else 0,
                          "periodi_che_accendono": sum(p >= VE.RIPARA_DI_FILA for p in periodi),
                          "fonti_con_riparazione_accesa": sum(r["riparazione"]["accesa"] for r in fonti),
                          "negativita_percentili_50_75_90": [round(float(x), 4) for x in
                                                             np.percentile([r["negativita"] for r in letture], [50, 75, 90])]
                          if letture else []}
    # soglia: consegne arrivate solo per l'emozione
    out["oltre_soglia"] = {"consegne": sum(bool(r.get("scelto")) for r in fonti),
                           "solo_per_emozione": sum(bool(r.get("oltre_soglia")) for r in fonti)}
    # rigiocare k e a
    if fonti:
        L = LE.Lux()
        soglia = LE.SOGLIA_RICHIAMO
        casi = []
        for r in fonti:
            cand = [c for c in r["candidati"] if int(c[0]) in set(L.prof_nid.tolist())]
            if cand:
                casi.append((r, cand))
        uguali, per_k, per_a = 0, {}, {}
        for r, cand in casi:
            acc = [c[2] for c in cand]
            vero = (r.get("scelto") or [None])[0]
            x = scegli(cand, acc, r["k"], soglia)
            uguali += (L.catena(int(x))[0] if x is not None else None) == vero
        for k in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
            cambi = sum(scegli(c, [x[2] for x in c], k, soglia) != scegli(c, [x[2] for x in c], 0.0, soglia) for _, c in casi)
            per_k[str(k)] = round(cambi / len(casi), 3) if casi else None
        for a in (0.0, 0.25, 0.5, 0.75, 1.0):
            cambi = 0
            for r, cand in casi:
                u = np.array(r["umore_prima"]) - calma
                if r["riparazione"]["accesa"]:
                    u = np.zeros(44)
                    u[tr["pos"]] = 1.0
                q = un(a * un(np.array(r["lettura"])) + (1 - a) * un(u))
                acc = L.accordi([int(c[0]) for c in cand], {"assi": tr["assi"], "q": q})
                cambi += scegli(cand, acc, r["k"], soglia) != scegli(cand, acc, 0.0, soglia)
            per_a[str(a)] = round(cambi / len(casi), 3) if casi else None
        out["rigiocato"] = {"fonti": len(casi), "uguale_al_vero": uguali,
                            "scelta_cambiata_dall_emozione_per_k": per_k, "per_a_col_k_vero": per_a,
                            "per_flusso_cambiata_k_vero": {
                                f: round(float(np.mean([scegli(c, [x[2] for x in c], r["k"], soglia) !=
                                                        scegli(c, [x[2] for x in c], 0.0, soglia)
                                                        for r, c in casi if r["flusso"] == f])), 3)
                                for f in {r["flusso"] for r, _ in casi}}}
    if "--ricordi-nuovi" in sys.argv:
        L = LE.Lux()
        nato = os.path.getmtime(VE.TRADUZIONE)
        testi = {}
        for n, m in json.load(open(LE.META))["ricordi"].items():   # 1.20.0: dal meta del Lux (prima memoria.db)
            if m["classe"] != "correzione" and float(m["ts"]) > nato and (m.get("testo") or "").strip():
                testi[int(n)] = m["testo"]
        nuovi = [int(n) for n in L.prof_nid if int(n) in testi]   # nati dopo l'addestramento
        if len(nuovi) >= 10:
            Z = np.array([VE.leggi(testi[n])[0] for n in nuovi])
            cols = [LE.EMOZIONI.index(a) for a in tr["assi"]]
            P = L.profz[np.searchsorted(L.prof_nid, nuovi)][:, cols]
            c = [np.corrcoef(Z[:, j], P[:, j])[0, 1] for j in range(44)]
            out["traduzione_sui_ricordi_nuovi"] = {"ricordi": len(nuovi), "accordo": round(float(np.nanmean(c)), 3),
                                                   "deciso": 0.69, "rifare_sotto": 0.6}
        else:
            out["traduzione_sui_ricordi_nuovi"] = {"ricordi": len(nuovi), "nota": "meno di 10 ricordi nuovi: presto"}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
