# Proposta: tabella delle emozioni della fase 2 (CC, 09/11/2026; DECISA dall'utente il 09/11: D1, D2, D3)

Per PIANO-LUX-FASI-v1.12.md, fase 2, punto 1: per ognuna delle 51 emozioni servono `carica` (impatto alla nascita) e
`sbiadimento` (velocita' propria, fissa). Base: la scheda del 16/10 accettata dall'utente (`salienza/emozioni-scienza.md`).
Valori NON misurati: sono un punto di partenza da tenere d'occhio nel rodaggio (punto 9).

## Le due grandezze

1. **Fattore alla nascita** (da 0.4 a 1.0). Oggi la carica di un arco e' la firma del suo ricordo (z, da circa -0.6 a
   3.9 nel Lux 1.13.0). Proposta: `carica alla nascita = fattore dell'emozione x firma`. Le emozioni ad alta
   attivazione fissano il ricordo di piu' (amigdala; Kensinger 2009, McGaugh 2004). Scala dalla colonna "impatto":
   molto alto 1.0, alto 0.8, medio 0.6, basso 0.4; "variabile" (nessun dato) 0.6.
2. **Sbiadimento per notte** (`carica_domani = carica_oggi x (1 - sbiadimento x freno)`, punto 4). Lo esprimo come
   EMIVITA: le notti in cui la carica si dimezza senza freno; con il freno (ripetizione, tema aperto, umore,
   importanza) si allunga. `sbiadimento = 1 - 0.5^(1/emivita)`.
   - rapida 30 notti; sbiadisce (negative) 90; sbiadisce meno per l'ansia, negative lente e senza dati 180;
     positive lente 365; colpa, vergogna e rimorso 3650 (quasi zero, come deciso il 17/10).
   - Perche' questi ordini di grandezza: il Fading Affect Bias si misura su settimane, mesi e anni, e l'affetto negativo
     sbiadisce piu' in fretta del positivo (Walker, Vogl e Thompson 1997; Walker, Skowronski e Thompson 2003; Ritchie
     e altri 2015, dieci culture). Le emozioni brevi come episodio (fastidio, noia, disgusto, sorpresa; Verduyn e
     Lavrijsen 2015) lasciano anche meno carica nel ricordo. Colpa e vergogna per un torto proprio non sbiadiscono
     (Aarhus 2026, preliminare). L'ansia frena lo sbiadimento (scheda del 16/10).

## Tabella

| emozione | impatto | fattore alla nascita | sbiadimento (scheda 16/10) | emivita (notti) | sbiadimento per notte | fonte |
|---|---|---|---|---|---|---|
| estasi | molto alto | 1.0 | lenta | 365 | 0.00190 | S |
| gioia | alto | 0.8 | lenta | 365 | 0.00190 | M |
| serenità | basso | 0.4 | lenta | 365 | 0.00190 | S |
| diletto | medio | 0.6 | lenta | 365 | 0.00190 | S |
| trionfo | alto | 0.8 | lenta | 365 | 0.00190 | S |
| orgoglio | medio | 0.6 | lenta | 365 | 0.00190 | M |
| ammirazione | medio | 0.6 | lenta | 365 | 0.00190 | M |
| fiducia | basso | 0.4 | lenta | 365 | 0.00190 | S |
| accettazione | basso | 0.4 | lenta | 365 | 0.00190 | S |
| amore | alto | 0.8 | lenta | 365 | 0.00190 | S |
| nostalgia | medio | 0.6 | lenta | 365 | 0.00190 | S |
| terrore | molto alto | 1.0 | sbiadisce | 90 | 0.00767 | S |
| paura | alto | 0.8 | sbiadisce | 90 | 0.00767 | M |
| apprensione | basso | 0.4 | sbiadisce meno (l'ansia frena) | 180 | 0.00384 | S |
| ansia | medio | 0.6 | sbiadisce meno (l'ansia frena) | 180 | 0.00384 | M |
| sottomissione | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| soggezione | alto | 0.8 | nessun dato | 180 | 0.00384 | S |
| stupore | alto | 0.8 | nessun dato | 180 | 0.00384 | S |
| sorpresa | alto | 0.8 | rapida | 30 | 0.02284 | M |
| distrazione | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| sgomento | alto | 0.8 | rapida | 30 | 0.02284 | S |
| cordoglio | alto | 0.8 | lenta (negativa) | 180 | 0.00384 | S |
| tristezza | medio | 0.6 | lenta (negativa) | 180 | 0.00384 | M |
| malinconia | basso | 0.4 | lenta (negativa) | 180 | 0.00384 | S |
| disperazione | alto | 0.8 | sbiadisce | 90 | 0.00767 | M |
| rimorso | medio | 0.6 | non sbiadisce, può crescere | 3650 | 0.00019 | S |
| colpa | medio | 0.6 | non sbiadisce, può crescere | 3650 | 0.00019 | M |
| vergogna | alto | 0.8 | non sbiadisce, può crescere | 3650 | 0.00019 | M |
| disapprovazione | medio | 0.6 | sbiadisce | 90 | 0.00767 | S* |
| ribrezzo | alto | 0.8 | rapida | 30 | 0.02284 | S |
| disgusto | alto | 0.8 | rapida | 30 | 0.02284 | M |
| noia | basso | 0.4 | rapida | 30 | 0.02284 | M |
| disprezzo | medio | 0.6 | sbiadisce | 90 | 0.00767 | S |
| morbosità | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| furia | molto alto | 1.0 | sbiadisce | 90 | 0.00767 | S |
| rabbia | alto | 0.8 | sbiadisce | 90 | 0.00767 | M |
| fastidio | basso | 0.4 | rapida | 30 | 0.02284 | M |
| aggressività | alto | 0.8 | sbiadisce | 90 | 0.00767 | S |
| indignazione | alto | 0.8 | sbiadisce | 90 | 0.00767 | S |
| dominanza | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| invidia | medio | 0.6 | sbiadisce | 90 | 0.00767 | S |
| gelosia | alto | 0.8 | sbiadisce | 90 | 0.00767 | M |
| cinismo | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| vigilanza | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| attesa | variabile | 0.6 | nessun dato | 180 | 0.00384 | solo attivazione |
| interesse | medio | 0.6 | lenta | 365 | 0.00190 | S |
| curiosità | medio | 0.6 | lenta | 365 | 0.00190 | S |
| ottimismo | medio | 0.6 | lenta | 365 | 0.00190 | S |
| speranza | medio | 0.6 | lenta | 365 | 0.00190 | M |
| pessimismo | medio | 0.6 | sbiadisce | 90 | 0.00767 | S |
| purificazione | medio | 0.6 | lenta | 365 | 0.00190 | S |

Fonte: M = misurato su quell'emozione, S = ricavato da un'emozione vicina (scheda del 16/10); S* = la disapprovazione
manca nella scheda, ricavata da sorpresa + tristezza (impatto medio, negativa).

## Un problema della funzione dose (punto 7), da sapere prima di decidere

`S_e = somma(w_i x F_i,e) / somma(w_i)` e' una media pesata: se tutte le cariche di un'emozione si moltiplicano per lo
stesso numero, S_e non cambia. Quindi, con la formula com'e':
- il fattore alla nascita non cambia la dose di quell'emozione;
- lo sbiadimento uguale per tutti gli archi non la cambia neppure: un ricordo vecchio colora quanto uno fresco,
  contro quello che il punto 7 vuole ("un ricordo vecchio colora meno di uno fresco").
Cambiano solo i pesi relativi fra gli engrammi, dove il freno e' diverso da arco ad arco.
Correzione proposta: dividere per le cariche ALLA NASCITA, `S_e = somma(w_i x F_i,e) / somma(w0_i)`. Da fresco
S_e e' uguale a oggi; quando la carica sbiadisce, S_e scende nella stessa proporzione e la dose con lei.

## Decisioni (dell'utente)

- D1. DECISA (09/11: "ok"): fattore alla nascita 1.0 / 0.8 / 0.6 / 0.4 (molto alto / alto / medio / basso), variabile 0.6.
- D2. DECISA (09/11: "vanno bene anche le emivite"): 30 / 90 / 180 / 365 / 3650 notti.
- D3. DECISA (09/11: "si'"): la media della dose si divide per le cariche ALLA NASCITA (w0). Serve la
  carica alla nascita di ogni arco nel Lux (`C0` accanto a `C` in lux.npz), scritta da `aggiungi` e mai toccata dopo.
