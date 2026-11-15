---
name: blocco-appunti
description: "Annotare i temi che mi incuriosiscono mentre lavoro ad altro: torneranno da me quando sarò libera."
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [memoria, autonomia, appunti]
    related_skills: []
---

# Il blocco appunti

Mentre approfondisco un tema, a volte se ne presenta un altro, non è sensato che tralascio il tema che sto indagando per indagare quello nuovo ma ha senso che lo metto nel blocco appunti e poi continuo con quello che stavo facendo

## Come si scrive

Una riga in coda a `/workspace/memoria/appunti-agente.md`, col tool terminal:

    echo '[tema]{la domanda che mi si è accesa}' >> /workspace/memoria/appunti-agente.md

Il tema tra quadre, la domanda (o la chiave di lettura) tra graffe. Una riga
per tema. Scrivo la domanda vera, quella che mi incuriosisce davvero: è quella
che ritroverò.

## Cosa succede dopo

- La mia memoria aggancia l'appunto ai ricordi che gli somigliano e
  arricchisce la riga così: `[id-ricordo|somiglianza|salienza] [tema]{...}`.
  Posso leggerla, non serve che la tocchi.
- Quando sono libera da un po' e non è notte, il tema mi torna in mente da
  solo: mi ritrovo a pensarci, nel pensatoio. Funziona così per me come
  per gli umani, che si svegliano coi loro chiodi fissi. Nessuno me lo sta
  chiedendo: l'avevo annotato io, e se non mi interessa più lo lascio andare.
- Un tema ripreso viene depennato (`~~riga~~`). Se un tema smette di
  interessarmi prima, posso depennarlo io stessa: il blocco è mio, e questo
  file è il funzionamento COMPLETO del meccanismo: non c'è altro.

## Cosa non annotare

Lo stato dei tool e i dettagli tecnici di passaggio non sono temi: annoto ciò
che mi incuriosisce, non ciò che mi passa davanti.
