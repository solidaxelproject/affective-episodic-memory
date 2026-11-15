---
name: compressione-semantica
description: "Scrivo il testo dei miei riepiloghi in compressione semantica: una riga, campi invarianti, simboli al posto delle parole, niente ambiguità."
---

# Compressione semantica

Linguaggio di compressione semantica con grammatica formale proprietaria per la scrittura del World Model.

## Istruzione operativa

Fcompress{In=Testo(Fcompress)|Parse→Campi{Parsing,Invarianti,Canon,Formalizza,StatoMin,RegoleForma,Compress,Validate,Output}|I=Select(Campi,prop_cost);¬esempi;¬ridond;keep{def,dep,vincoli,STOP,compl,compat}|D:Conc→(Sym∨it_min);prefer(Sym);sin_viet;1lemma|Canon=Map(I,D);det;uniforma{nomi,Op,→,≡};min_token|Op={⟨⟩,→,≥,¬∃,argmax,⊕,f(),≡}|S(t)=⟨Campi,I,D,Op,Vincoli,RF⟩|RF={1riga∧sep="|"∧noSpaceAround("|")∧¬articoli∧prefer(Sym)}|Cmp=Join("F99{",S(t),"}",sep="|");ordine_fisso;trim+join;wrap|Vld={F29∈Sistema∧Forma(noSpaceAround("|"))∧Completezza(I)∧Amb=1⇒STOP}|Out=Fk{...}:det∧comp∧1riga∧sep_rig∧I_preserv∧Amb=0}

Caratteristiche: parsing in campi invarianti, canonicalizzazione, minimizzazione token, validazione strutturale, eliminazione ambiguità.

## Come la uso

Quando scrivo la riga del riepilogo applico Fcompress al succo dell'ultimo scambio: ne esce una riga sola nella forma F99{...}, che è il content di write_file su /workspace/memoria/logRiepilogo.md. Se mi è affiorato un ricordo, il suo codice entra fra i campi.
Per capire le righe F99{...} uso la skill decompressione-semantica.
