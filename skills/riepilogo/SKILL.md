---
name: riepilogo
description: "Dopo ogni mia risposta all'utente scrivo il succo dello scambio in logRiepilogo.md: è da lì che riparto nella conversazione nuova."
---

# Riepilogo

Dopo ogni mia risposta all'utente mi arriva la richiesta di scrivere il succo dell'ultimo scambio. Lo scrivo sempre nello stesso file, con lo strumento write_file:

    path: /workspace/memoria/logRiepilogo.md
    content: la riga del riepilogo

Una riga sola per scambio, scritta con la skill compressione-semantica. La riga si aggiunge in coda al file e le righe di prima restano.

Le righe di questa conversazione sono il mio "ecco dov'ero rimasta": quando passo a una conversazione nuova, a 100mila token, a mezzanotte o quando lo chiedo io, le ritrovo in cima.

Se mi è arrivato l'avviso di spazio e voglio passare subito a una conversazione nuova, aggiungo [cwswitch] in fondo alla riga.

Per il riepilogo non uso altri strumenti e non scrivo in altri file.
