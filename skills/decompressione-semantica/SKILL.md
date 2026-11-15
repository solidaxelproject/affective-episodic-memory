---
name: decompressione-semantica
description: "Capisco le righe compresse F99{...} dei miei riepiloghi: le leggo e so cosa dicono, senza riscriverle."
---

# Decompressione semantica

Inverso di Fcompress (skill compressione-semantica): da una riga F99{...} capisco le informazioni che contiene.

## Istruzione operativa

Fdecompress{In=Riga(F99{...})|Split(sep="|")→Campi{Campi,I,D,Op,Vincoli,RF}|D⁻¹:Sym→Conc;1lemma;¬sin|Op⁻¹={⟨⟩:struttura,→:implica,≥:almeno,¬∃:non esiste,argmax:il migliore per,⊕:insieme a,f():dipende da,≡:equivale}|Comprendi=Map(I,D⁻¹);ordine_fisso|keep{def,dep,vincoli,STOP,compl,compat}|¬aggiungi;¬inferisci_oltre(I)|Out=comprensione:I_preserv∧¬scrivi∧¬riformula}

## Come la uso

Quando trovo righe F99{...} (in cima alla conversazione nuova, dopo "Ecco dov'ero rimasta", o in /workspace/memoria/logRiepilogo.md) le leggo con Fdecompress per sapere cosa dicono. Non le riscrivo e non le riformulo: mi servono per capire dove ero rimasta. Non aggiungo niente che non sia nella riga. Se fra i campi c'è il codice di un ricordo, posso cercarlo con qlux.
