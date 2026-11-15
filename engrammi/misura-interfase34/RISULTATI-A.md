# Misura del richiamo, parte A (interfase 3-4 punto 5, 14/11/2026)

Script: `misura.py`, dati: copia congelata del Lux 1.24.0 (697 ricordi), codice del ramo interfase34. Numeri in
`risultati-A.json`. Solo il recupero del ricordo giusto, senza modello.

## Indizi

- **libere** (14): frasi scritte a mano che parlano di un ricordo con parole diverse (taratura_soglia.py).
- **due engrammi** (40): due pezzi non vicini di un ricordo, come nella taratura.
- **frasi esatte** (40): una frase copiata dal ricordo.
- **negativi** (20): frasi senza un ricordo corrispondente.

## Risultati (primo posto / fra i primi 3)

| indizi | Lux | RAG (bge-m3, blocchi da 150 parole) | bm25 |
|---|---|---|---|
| libere | 0,64 / 0,86 | 0,71 / 1,00 | 0,79 / 1,00 |
| due engrammi | **0,78 / 0,88** | 0,17 / 0,28 | 0,70 / 0,82 |
| frasi esatte | **1,00 / 1,00** | 0,57 / 0,65 | 0,97 / 1,00 |

Soglia del Lux (0,2): nessuno dei 20 negativi passa; passano 14/14 libere, 26/40 due engrammi, 40/40 frasi esatte.
Un RAG non ha una soglia che separi "nessun ricordo" (il primo blocco esce sempre).

## Ablazioni (un meccanismo spento alla volta, primo posto)

| spento | libere | due engrammi | frasi esatte |
|---|---|---|---|
| niente (Lux intero) | 0,64 | 0,78 | 1,00 |
| facilita' (rinforzi FSRS) | 0,64 | 0,75 | 1,00 |
| predisposizione delle consegne | 0,64 | 0,78 | 1,00 |
| peso degli engrammi comuni (1/log) | **0,43** | 0,75 | **0,85** |
| divisione per la lunghezza | 0,71 | 0,75 | 0,97 |

## Cosa dicono

- Il Lux vince quando l'indizio contiene pezzi del ricordo (due engrammi, frasi esatte); sulle frasi libere vincono
  RAG e bm25, perche' il Lux accende solo engrammi simili oltre 0,8 di coseno.
- Il meccanismo che conta di piu' nel recupero e' il peso degli engrammi comuni. Facilita' e predisposizione
  cambiano poco su indizi presi a caso: lavorano sulla storia (cosa e' stato richiamato), che questa prova non misura.
- La soglia separa bene: zero falsi positivi.

## Limiti

14 frasi libere sono poche. Indizi di due tipi costruiti dal Lux stesso (favoriscono il Lux). Via emotiva, ponti,
ricombinazione, fonti e steering non entrano nel recupero puro: per loro serve la parte B col 35B (qualita' delle
risposte, coerenza nel tempo, effetto dello steering sul ragionamento), con compiti e metro da decidere con l'utente.
