# Refactoring della notturna: cose da gestire

Lista dei cablaggi da aggiungere alla notturna quando ci lavoreremo (l'utente 16-17/10/2026). Niente e' ancora nel codice
della notturna. La notturna di oggi e' `/data/memoria-episodica-affettiva/notte-memoria.sh`, in quest'ordine:
estrai-matrix.py -> sincronizza-richiami.py -> run-tagging.sh (tagging35b.py) -> lux.avanza_orologio() ->
memoria.consolida_notte() -> lux_engrammi.py aggiungi.

## Da rivedere (16/10)
- Le funzioni attuali (fusione in schemi `lux.consolida()`, potatura `lux.pota()`, `memoria.consolida_notte()`)
  potrebbero non essere coerenti col funzionamento della memoria umana e andare deprecate. Per ora restano.

## Da aggiungere (fase 2 della 1.11, PIANO-LUX-FASI-v1.12.md)
1. ~~Frequenza di richiamo~~ TOLTA (l'utente 17/10, doppione di R). Resta per ricordo l'**ultimo richiamo**
   `[g/m/aaaa|h:mm]`, scritto alla consegna (non di notte).
2. **Sbiadimento per arco** (`sbiadisci`, dopo `aggiungi`): carica_domani = carica_oggi x (1 - sbiadimento x freno),
   freno = prodotto di (1 - peso x modificatore) per ripetizione, aperta, umore, importanza.
3. **Riaccensione degli engrammi**: `nato_U`, `acceso_U` e `accensioni` per engramma (ritmo = intervallo medio), dagli engrammi dei messaggi del giorno
   (soglia SOGLIA_SEM 0.8). Servono ad "aperta".
4. **Riconsolidamento** (`riconsolida`, dopo `aggiungi`): la carica si sposta verso la firma del momento del richiamo, SOLO se la differenza supera la soglia di sorpresa.
5. **Firma del momento**: il tagging scrive nel diario la firma della prima risposta dell'agente dopo ogni ricordo consegnato.
6. Rodaggio di 30 giorni e copia dello stato del Lux prima di ogni notte.

## Dati che la notturna puo' usare
- Ora di arrivo di OGNI messaggio dell'utente (riflesso.py, 17/10): `workspace/memoria/ore-messaggi.json`, chiave
  `arrivi` per conversazione (l'agente ne vede una ogni 5, chiave `ore`).
