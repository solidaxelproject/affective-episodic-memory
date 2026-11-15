"""Lux degli engrammi: mixin Fonti della classe Lux: fiducia nei siti (1.24.0).
Parte di lux_engrammi.py (divisione del 14/11/2026, interfase 3-4 punto 1); i chiamanti importano
lux_engrammi, che riesporta tutto."""
import lux_base as B


class Fonti:
    def certo(self, sito):
        """D5 (13/11): certo quando la fiducia supera la soglia; un sito mai visto parte da FIDUCIA_W0"""
        return self.fiducia.get(B.chiave(sito), [B.FIDUCIA_W0])[0] >= B.FIDUCIA_CERTA

    def conferma(self, nid):
        """D2 (13/11): il ricordo nid viene da una fonte certa (l'utente o un sito certo): ogni ricordo di un ALTRO
        sito che dice la stessa cosa, non corretto e non gia' confermato, alza la fiducia del suo sito (Rescorla-Wagner).
        -> siti confermati"""
        r = self.ricordi.get(nid, {})
        miei = set(self.siti_di.get(nid, []))
        if r.get("fonte") != B.FONTE_CERTA and not any(self.certo(s) for s in miei):
            return []
        fatti = []
        candidati = {m for s, nids in self.ricordi_di_sito.items() if s not in miei for m in nids}
        for m in sorted(candidati - self.confermati - self.errati - {nid}):
            if not self._vicini(nid, m):
                continue
            for s in self.siti_di[m]:   # tutti i siti del ricordo confermato, tranne quelli della fonte
                if s in miei:
                    continue
                w = self.fiducia.setdefault(s, [B.FIDUCIA_W0, 0, 0])
                w[0] += B.FIDUCIA_G * (1 - w[0])
                w[1] += 1
                fatti.append(s)
            self.confermati.add(m)
        return fatti

    def smentisci(self, o):
        """D3 (13/11): il ricordo o e' stato corretto: la fiducia dei suoi siti scende subito. -> siti"""
        for s in self.siti_di.get(o, []):
            w = self.fiducia.setdefault(s, [B.FIDUCIA_W0, 0, 0])
            w[0] *= 1 - B.FIDUCIA_D
            w[2] += 1
        return self.siti_di.get(o, [])
