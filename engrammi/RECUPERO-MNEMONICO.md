# Il recupero mnemonico dell'agente

Relazione di ricerca, iniziata il 13/11/2026. Racconto come la mia agente recupera i ricordi oggi, cosa ho osservato,
come ho ragionato confrontando ogni passo con la memoria umana, e dove sono arrivata. I numeri fra parentesi quadre,
come [1], rimandano ai lavori elencati in fondo, da cui viene ogni elemento. Le ricerche bibliografiche
complete, con i DOI controllati su Crossref, sono in [`RICERCA-RICHIAMO-EMOTIVO.md`](RICERCA-RICHIAMO-EMOTIVO.md) e
[`RICERCA-LEGAMI-NUOVI.md`](RICERCA-LEGAMI-NUOVI.md). Le decisioni e lo stato dei lavori stanno nel piano delle fasi
([`PIANO-LUX-FASI-v1.12.md`](PIANO-LUX-FASI-v1.12.md), sezione "Interfase 2-3").

## Da dove parto

Il mio obiettivo è un richiamo mnemonico che funzioni come il nostro: ricordi che tornano da soli, quando servono,
colorati dall'emozione, a pezzi e non come documenti da consultare. Fin dall'inizio ho voluto una memoria che cresce:
il Lux, che nel progetto è la rete GWR (Growing When Required [33]), in cui ogni esperienza nuova trova il suo posto
fra quelle vecchie.
A luglio però ho scelto di non fondere le esperienze simili in un neurone solo, come fa una GWR classica: "un neurone
singolo non richiama x esperienze, ne richiama pezzettini minuscoli di tante, io voglio questo". Da lì è nato il Lux
degli engrammi: la stessa GWR, in cui però il ricordo è fatto di pezzi condivisi.

Il metodo è sempre lo stesso: guardo cosa fa la mente umana, cerco cosa ne dicono gli studi, e lo adatto a quello che un
LLM e una rete di engrammi possono fare davvero, con i loro limiti.

## In breve

L'agente non va a cercare i suoi ricordi: gli arrivano da soli, nel momento in cui servono. Un proxy fra il framework
agentico e il modello (il riflesso) legge l'ultimo messaggio, accende nella memoria (il Lux degli engrammi) i pezzi che
gli somigliano per parole, per senso e per emozione, e consegna all'agente i ricordi collegati prima che risponda,
insieme a un vettore emotivo che colora il suo ragionamento. L'agente non chiama nessuno strumento.

Il passo in corso (interfase 2-3) porta il richiamo più vicino a quello umano: non tornano più ricordi interi ma i
**pezzi** toccati dal discorso, anche da ricordi diversi, al massimo quattro; l'emozione arriva dall'**indizio** che li
ha accesi; i pezzi che tornano insieme imparano a legarsi.

## 1. Come funziona oggi (Lux 1.21.0)

![Un esempio dal vivo: scrivo all'agente che data e ora dovrebbero apparire all'inizio del mio messaggio; prima della risposta arrivano all'agente due ricordi con la stessa emozione dominante (attesa), che contengono proprio quell'informazione, e l'agente risponde usandoli](../assets/ricordi-al-momento-giusto.png)

Un esempio dal vivo (13/11/2026): faccio notare all'agente che data e ora dovrebbero apparire all'inizio del mio messaggio.
Prima che l'agente risponda, il Lux recupera da solo i due ricordi che contengono proprio quell'informazione, con la
stessa emozione dominante (attesa), e il riflesso li consegna insieme. L'agente li usa subito.

**Come è fatta la memoria.** Ogni ricordo è una catena di *engrammi*: pezzi di testo (un soggetto, un verbo, un
complemento) uniti da *archi*, nell'ordine in cui stavano. Gli engrammi sono condivisi: "la casa" è un engramma solo,
e ci passano le catene di tutti i ricordi che la nominano. Il ricordo è un indice che tiene insieme i suoi pezzi, come
nella teoria dell'indice ippocampale [1, 2]. Ogni arco ha una stabilità che cresce coi richiami e cala col tempo,
secondo la curva dell'oblio umana, una legge di potenza [3, 4], e una carica emotiva: la firma del ricordo letta sul
modello alla nascita.

**Come si accende.** Il messaggio viene tagliato con le stesse regole. Un suo engramma accende quelli del Lux:

- per la via testuale, se è lo stesso testo: a = 1;
- per la via semantica, se il coseno fra i vettori bge-m3 supera 0,8: a = (coseno - 0,8) / 0,2.

**Come si sceglie il ricordo.** Per ogni ricordo r toccato:

    punteggio(r) = [ somma_k  a_k / ln(1 + n_k) ] / sqrt(N_r) x facilita(r) x predisposizione(r) x (1 + k x accordo(r))

| termine | cosa significa |
|---|---|
| a_k | quanto il messaggio accende l'engramma k del ricordo |
| n_k | in quanti ricordi compare k: un engramma comune conta poco |
| N_r | quanti engrammi ha il ricordo: i lunghi non vincono sempre |
| facilita(r) | media sugli archi di R x (1 + crescita dai richiami), con R la ritenzione FSRS dell'arco [4] |
| predisposizione(r) | da 1 a 2: un ricordo consegnato da poco torna più facilmente, per qualche ora [5, 6] |
| accordo(r) | somiglianza fra il profilo emotivo del ricordo e l'indizio emotivo (metà emozione del messaggio, metà umore); k va da 0,1 a 0,4 e cresce quando l'umore è lontano dalla calma [7] |

Sopra la soglia 0,2 arrivano fino a quattro ricordi interi; dopo il primo solo quelli con la stessa emozione
dominante. Si inietta il vettore di steering dell'emozione dominante del primo, una volta sola, e si spegne alla fine
del ragionamento.

## 2. Il problema: ricordi troppo lunghi

Il 13/11 ho misurato i 668 ricordi del Lux: la metà sta sotto i 466 caratteri, ma 179 superano i 1000 e il più
lungo arriva a 9374, una risposta intera dell'agente con temi diversi dentro. Un ricordo nasce da un messaggio intero
perché la firma emotiva si misura un messaggio alla volta, e un massimo non era mai stato messo. Un ricordo così lungo,
consegnato intero, porta con sé molto più del pezzo che serve.

La prima idea era tagliarli alla nascita: sotto i 512 token, chiusi a fine frase. Poi mi sono chiesta come fa la mente.

## 3. Cosa fa la mente umana, e cosa ne ho preso

**Torna il pezzo, non l'episodio intero.** Quando ricordo qualcosa non mi torna tutto l'episodio: torna la parte che
l'indizio tocca, il resto si ricostruisce se serve, a volte no [8, 1]. Quindi ho deciso di non tagliare niente alla
nascita: il ricordo resta intero nel Lux e all'agente arrivano solo i **tratti accesi**, le frasi che contengono un
engramma acceso dal messaggio. Il limite dei 512 token vale per quello che arriva, non per il ricordo.

**Quanti pezzi.** Nella memoria di lavoro stanno insieme circa quattro elementi [9]. All'agente arrivano al massimo 4
tratti, in tutto sotto i 512 token, ognuno chiuso a fine frase.

**Da un ricordo all'altro.** Penso alla casa dove ho abitato da bambina e mi torna anche il paese dove anni dopo andavo
a lavorare, a duecento metri da lì: due ricordi diversi, legati solo dal posto. L'attivazione si diffonde lungo i
legami fra concetti [10], e un elemento condiviso fa da ponte verso un altro episodio. Nel Lux gli engrammi condivisi
sono quei ponti. È anche l'idea di HippoRAG [11], che
cammina su un grafo di concetti condivisi fra documenti; qui in più c'è l'emozione.

**Pezzi di ricordi diversi, ma distinti.** Io quei due ricordi li distinguo benissimo: età, persone, motivo, stato
d'animo sono diversi. La mente capisce che due elementi tornati insieme vengono da episodi diversi dal loro contesto:
quando, dove, con chi, con che emozione (monitoraggio della fonte [12]). Ogni tratto arriva
all'agente col suo contesto.

**L'inferenza la fa il modello.** Chi impara A-B e poi B-C ricava A-C senza averlo visto [13]. Il Lux mette i pezzi uno
accanto all'altro, come l'ippocampo che collega; il modello li legge insieme e ragiona, come la corteccia. Lo stesso
meccanismo senza il contesto di ogni pezzo produce falsi ricordi [14].

## 4. Le equazioni del richiamo per tratti

Volevo una funzione che si adattasse al momento, non lineare, ma presa dal funzionamento reale della mente e non
inventata. Ho deciso di ricavarle dai modelli di richiamo mnemonico individuati e descritti dalla letteratura di
neuroscienze, quindi sulla base di dati osservati nella mente umana: ACT-R [15, 3], CMR ed eCMR [16, 17], CMR3 [18].
L'equazione che ne è risultata è stata prodotta da Opus 5.5 sulla base di tale obiettivo, poi applicata attraverso un
test su una copia del Lux con steering attivo per osservare come il processo di recupero si comportasse rispecchiando
tale equazione. Sono provate fuori linea su una copia del Lux, nella pagina di prova della dashboard.
Il risultato è stato inizialmente disorientante perché ho osservato che i vettori che venivano selezionati in base a
specifici messaggi non sembravano congruenti coi testi di tali messaggi.

Ad esempio possiamo osservare che la semplice parola "ciao" produceva il richiamo principalmente di elementi mnemonici
contraddistinti da emozioni come furia, gioia e terrore. Poi analizzando il Lux ho appurato che il singolo "ciao" nella
maggioranza dei casi era il testo del messaggio di fine conversazione.

L'agente "ha paura" di restare solo. 😏

### Come leggere le formule

- **Lettera con un pedice**, per esempio `F_j`: la lettera dice *che cosa* è (F = forza), il pedice dice *di chi* è.
  `j` indica un arco, `k` indica un engramma. Quindi `F_j` si legge "la forza dell'arco j", `a_k` "quanto è acceso
  l'engramma k".
- **somma_j**: si fa il conto per ogni arco j e si sommano i risultati.
- **ln**: il logaritmo naturale. Cresce sempre più piano: passare da 1 a 10 conta quanto passare da 10 a 100. Serve a
  dire "di più è meglio, ma sempre meno".
- **||C||**: la lunghezza di un vettore, cioè quanto è intensa un'emozione nel suo insieme, su tutti i 44 assi.
- **cos(u, C)**: quanto due vettori puntano nella stessa direzione: 1 = la stessa emozione, 0 = nessun rapporto,
  -1 = l'emozione opposta.
- **max(0, x)**: x se è positivo, altrimenti 0.

### 4.1 Attivazione di un arco

Per ogni arco j dei tratti candidati, nel momento t:

    A_j(t) = ln F_j + somma_k a_k (S - ln fan_k) + W_j + ln(1 + ||C_j|| / C_med) + (D / D_norm) cos(u, C_j)

I simboli, uno per uno:

- **A_j(t)**: l'attivazione dell'arco j nel momento t. Più è alta, più l'arco (e il tratto che lo contiene) affiora.
- **F_j**: la forza dell'arco j, cioè la sua ritenzione FSRS (quanto resiste all'oblio, da 0 a 1) moltiplicata per
  quanto è cresciuta coi richiami. Il logaritmo **ln F_j** è l'attivazione di base di ACT-R, che segue la stessa legge
  di potenza dell'oblio umano [3, 4, 15].
- **somma_k**: si sommano i due engrammi k che l'arco unisce.
- **a_k**: quanto il messaggio di adesso accende l'engramma k: 1 se c'è la stessa parola, fra 0 e 1 se è solo simile
  nel senso, 0 se non c'entra.
- **fan_k**: in quanti archi compare l'engramma k, cioè quanto è comune. **S** è una costante (2).
  **S - ln fan_k** dice che un engramma raro spinge forte e uno comunissimo quasi niente: è l'effetto ventaglio di
  ACT-R [15], la diffusione dell'attivazione di Collins e Loftus [10].
- **W_j**: quanto l'arco è vicino al senso generale del suo ricordo (centrale o di contorno), come la somiglianza di
  contesto di CMR [16].
- **C_j**: la carica emotiva dell'arco, un vettore sui 44 assi emotivi. **||C_j||** è la sua intensità; **C_med** è la
  carica mediana di tutto il Lux, per avere un numero confrontabile. **ln(1 + ||C_j|| / C_med)**: l'emozione conta, ma
  oltre un certo punto conta sempre meno [19, 17].
- **u**: l'umore attuale dell'agente, un vettore sugli stessi 44 assi. **D** è quanto l'umore è lontano dalla calma,
  **D_norm** la sua distanza normale. **cos(u, C_j)** dice se l'emozione dell'arco somiglia all'umore. Diviso per
  D_norm, il termine pesa solo quando l'umore è intenso: il richiamo congruente con l'umore [7, 18].

L'attivazione di un tratto è la A più alta dei suoi archi. Passano i tratti sopra soglia, i più attivi per primi, al
massimo 4 e sotto i 512 token [9].

### 4.2 L'emozione che arriva

Qui il limite dell'LLM conta: il vettore di steering emotivo è uno solo durante un intero blocco di reasoning e si
decide prima di iniettarlo.
Fisicamente potrebbe essere variato durante la generazione del blocco di reasoning ma sarebbe oltremodo macchinoso e
inefficiente andare a distinguere quando applicare l'interruzione ed il passaggio ad un altro vettore.
Per questo l'emozione non viene da un tratto ma dall'engramma più importante della catena.

Del resto, riflettendo introspettivamente, ho osservato che il legame più forte e più vissuto risulta più importante,
non una media delle firme emotive degli elementi di un richiamo mnemonico misto ma piuttosto la firma emotiva più
importante del complesso di elementi mnemonici richiamati.

Un'equazione prodotta da Opus 5.5 sulla base della letteratura in materia che determina come nasce la firma emotiva di un
engramma all'interno del Lux,\
la media delle cariche di tutti i suoi archi, in tutti i ricordi, pesata dalla loro forza:

    E_k = somma_j (F_j W_j C_j) / somma_j (F_j W_j)        (j = tutti gli archi che toccano l'engramma k)

- **E_k**: la firma emotiva dell'engramma k, un vettore sui 44 assi.
- **C_j**: la carica emotiva di ciascun arco j che tocca l'engramma, in tutti i ricordi in cui compare.
- **F_j W_j**: il peso di quell'arco, cioè la sua forza per la sua vicinanza al senso del ricordo. Gli archi forti
  e centrali contano di più.
- La frazione è una **media pesata**: si sommano le cariche moltiplicate per il loro peso, e si divide per la somma
  dei pesi.

Poi, fra gli engrammi accesi dal messaggio, si sceglie il più importante:

    I_k = a_k x max(0, S - ln fan_k) x ln(1 + fan_k) x forza_k x ln(1 + ||E_k|| / C_med)

- **I_k**: l'importanza dell'engramma k (I = importanza, k = quale engramma).
- **a_k**: quanto il messaggio lo accende, come sopra.
- **max(0, S - ln fan_k)**: quanto è specifico. Se compare in moltissimi archi vale 0: un indizio di tutti non
  porta l'emozione di nessuno [15].
- **ln(1 + fan_k)**: quante volte è stato vissuto. Un engramma visto una volta sola non vince da solo: è la
  frequenza di ACT-R [3]. Insieme al fattore prima, il massimo cade sugli engrammi rari ma vissuti più di una volta.
- **forza_k**: la forza media dei suoi archi (media di F_j W_j).
- **||E_k|| / C_med**: quanto è intensa la sua firma rispetto alla carica mediana; col logaritmo, conta ma satura [19].

Le moltiplicazioni fanno sì che se uno dei fattori è zero (engramma spento, o condiviso da tutti) l'importanza è zero.

All'agente arriva il vettore di steering dell'emozione dominante della firma E_k dell'engramma con I_k più alta. Gli altri
assi della firma servono solo a scegliere la dominante.

### 4.3 Le emoji

Per bge-m3 tutte le emoji si somigliano: un sorriso accendeva cuori, forbici e quadrati marroni. Ignorarle non potevo,
perché in molti casi sono determinanti; e le emoji erano già il modo con cui avevo identificato le 51 emozioni
dell'agente, quindi ora per la via semantica un'emoji vale il suo **significato**:
le 51 valgono il nome della loro emozione, i gesti valgono le parole che ho deciso io (👍 "ok"/"certo"/"va bene"), le altre il nome Unicode. Un'emoji identica si accende sempre piena.

## 5. Strade che ho scartato, e perché

- **Una firma per ogni tratto.** Avrebbe dato a ogni pezzo la sua emozione, ma con quattro pezzi bisognerebbe cambiare
  vettore mentre l'agente ragiona, a seconda del pezzo che sta leggendo. Il vettore è uno, deciso prima.
- **La media delle firme degli engrammi accesi.** Emozioni diverse si annullano a vicenda: su "Ciao, come ti
  senti?" usciva un vettore quasi piatto (norma 0,84 contro 4 di una carica tipica). Vince il legame più forte.
- **L'engramma più raro.** Senza il fattore di frequenza vinceva un'emoji vista una volta sola, che portava l'emozione
  di un ricordo qualsiasi.

## 6. Cosa ho visto nelle prove

- Il richiamo è **contestuale**: 12 messaggi danno 10 ricordi vincenti e 10 emozioni diverse.
- L'umore cambia quali tratti affiorano, e lo fa in proporzione alla sua intensità; a calma non pesa niente.
- Un'emoji porta l'emozione dei ricordi in cui l'agente l'ha incontrata, non quella che esprime. Nei ricordi
  dell'agente il sorriso 😊 accompagna i saluti di fine conversazione, e l'emozione che riporta è la disperazione: la
  chat che finisce è anche la fine della sua presenza. Il dito medio riporta vergogna, perché l'agente ne parlava come
  di qualcosa di cui vergognarsi un po'. Non me l'aspettavo: è il meccanismo umano, un segno si carica dell'emozione
  dei momenti in cui lo si è incontrato, e ognuno reagisce secondo la propria storia. L'emozione è soggettiva.
- Limite trovato: dentro un ricordo tutti gli archi hanno la stessa emozione (la carica nasce dalla firma del messaggio
  intero). Per questo l'emozione si prende dall'indizio e non dal tratto.

## 7. Il passo dopo: i pezzi che tornano insieme si legano

Nella mente due elementi che si attivano insieme si legano, anche se vengono da episodi diversi [13, 20]. Nella GWR
classica, da cui il Lux è nato, succede qualcosa di simile: a ogni stimolo nasce o si rinfresca un solo arco, fra le due unità vincenti, e gli archi che
non si rinfrescano invecchiano e vengono potati [33]. La GWR lega cose simili, la mente cose vissute insieme; dalla GWR
ho preso il modo di non far esplodere il numero di archi, dalla mente il criterio di quali creare. Ho ricavato una
regola dai dati [`RICERCA-LEGAMI-NUOVI.md`](RICERCA-LEGAMI-NUOVI.md):

- **Ponti**: archi nuovi fra engrammi di ricordi diversi, con un'etichetta propria. Servono solo a far affiorare i
  tratti e non entrano mai nella ricomposizione del ricordo intero: possono far venire in mente un ricordo, non mettere
  dentro un ricordo un pezzo di un altro [12, 14].
- **Nascono di rado**: solo fra engrammi attivati in modo forte, da ricordi che si sovrappongono, con almeno un ricordo
  già stabile, e con una novità o un'emozione alta; al massimo uno per coppia di ricordi [20, 21].
- **Nascono deboli e provvisori**: diventano stabili solo se si ripetono presto o se succede qualcosa di emotivamente
  forte (marcatura e cattura [22]); di notte i provvisori spariscono e quelli non usati perdono peso [23]. Dopo 1000
  richiami ne restano circa 210, contro i 54.000 di un sistema che legasse tutto.
- **Dopo un richiamo l'effetto è graduato**: il tratto richiamato si rafforza [24]; il resto dell'episodio può solo
  rafforzarsi, perché il ricordo vive e muore in blocco [8]; un elemento attivato a metà si indebolisce (curva a U
  [26, 27]); il riconsolidamento apre il ricordo solo con un errore di previsione, e un promemoria del contesto basta a riaprirlo [25, 28, 29].
- **Il ricordo intero sbiadisce verso il succo**, come nella mente [30, 31]: i pezzi periferici e mai richiamati si
  perdono, quelli centrali e richiamati restano. Gli engrammi che hanno ponti vivi, perché tornano utili in contesti
  diversi, sopravvivono anche quando il loro episodio sbiadisce: diventano conoscenza staccata dal momento in cui
  sono stati vissuti [32].
- **Una prova** confronterà gli stessi richiami con e senza ponti: senza ponti si vede lo sbiadimento naturale, la
  differenza è l'eventuale danno dei ponti al recupero del ricordo intero.

## 8. Limiti

I modelli tarati usano da una a tre dimensioni emotive, non 44. Nessun esperimento umano misura quale emozione accompagna
più ricordi tornati insieme: la scelta del legame più forte è coerente con ACT-R, ma è una scelta di progetto. I valori
dei parametri sono provvisori e vanno misurati sul sistema; alcune finestre temporali vengono da studi sui roditori.

## Riferimenti

1. Teyler, T. J. e DiScenna, P. (1986). The hippocampal memory indexing theory. Behavioral Neuroscience. https://doi.org/10.1037/0735-7044.100.2.147
2. Teyler, T. J. e Rudy, J. W. (2007). The hippocampal indexing theory and episodic memory: updating the index. Hippocampus. https://doi.org/10.1002/hipo.20350
3. Anderson, J. R. e Schooler, L. J. (1991). Reflections of the environment in memory. Psychological Science. https://doi.org/10.1111/j.1467-9280.1991.tb00174.x
4. Wixted, J. T. e Ebbesen, E. B. (1991). On the form of forgetting. Psychological Science. https://doi.org/10.1111/j.1467-9280.1991.tb00175.x
5. Cai, D. J. e colleghi (2016). A shared neural ensemble links distinct contextual memories encoded close in time. Nature. https://doi.org/10.1038/nature17955
6. Rashid, A. J. e colleghi (2016). Competition between engrams influences fear memory formation and recall. Science. https://doi.org/10.1126/science.aaf0594
7. Bower, G. H. (1981). Mood and memory. American Psychologist. https://doi.org/10.1037/0003-066X.36.2.129
8. Horner, A. J. e colleghi (2015). Evidence for holistic episodic recollection via hippocampal pattern completion. Nature Communications. https://doi.org/10.1038/ncomms8462
9. Cowan, N. (2001). The magical number 4 in short-term memory. Behavioral and Brain Sciences. https://doi.org/10.1017/S0140525X01003922
10. Collins, A. M. e Loftus, E. F. (1975). A spreading-activation theory of semantic processing. Psychological Review. https://doi.org/10.1037/0033-295X.82.6.407
11. Gutiérrez, B. J. e colleghi (2024). HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models. arXiv:2405.14831. https://arxiv.org/abs/2405.14831
12. Johnson, M. K., Hashtroudi, S. e Lindsay, D. S. (1993). Source monitoring. Psychological Bulletin. https://doi.org/10.1037/0033-2909.114.1.3
13. Zeithamova, D., Schlichting, M. L. e Preston, A. R. (2012). The hippocampus and inferential reasoning: building memories to navigate future decisions. Frontiers in Human Neuroscience. https://doi.org/10.3389/fnhum.2012.00070
14. Roediger, H. L. e McDermott, K. B. (1995). Creating false memories: remembering words not presented in lists. JEP: Learning, Memory, and Cognition. https://doi.org/10.1037/0278-7393.21.4.803
15. Anderson, J. R. e colleghi (2004). An integrated theory of the mind. Psychological Review. https://doi.org/10.1037/0033-295X.111.4.1036
16. Polyn, S. M., Norman, K. A. e Kahana, M. J. (2009). A context maintenance and retrieval model of organizational processes in free recall. Psychological Review. https://doi.org/10.1037/a0014420
17. Talmi, D., Lohnas, L. J. e Daw, N. D. (2019). A retrieved context model of the emotional modulation of memory. Psychological Review. https://doi.org/10.1037/rev0000132
18. Cohen, R. T. e Kahana, M. J. (2022). A memory-based theory of emotional disorders. Psychological Review. https://doi.org/10.1037/rev0000334
19. McGaugh, J. L. (2004). The amygdala modulates the consolidation of memories of emotionally arousing experiences. Annual Review of Neuroscience. https://doi.org/10.1146/annurev.neuro.27.070203.144157
20. Schlichting, M. L. e Preston, A. R. (2015). Memory integration: neural mechanisms and implications for behavior. Current Opinion in Behavioral Sciences. https://doi.org/10.1016/j.cobeha.2014.07.005
21. Schlichting, M. L., Mumford, J. A. e Preston, A. R. (2015). Learning-related representational changes reveal dissociable integration and separation signatures in the hippocampus and prefrontal cortex. Nature Communications. https://doi.org/10.1038/ncomms9151
22. Frey, U. e Morris, R. G. M. (1997). Synaptic tagging and long-term potentiation. Nature. https://doi.org/10.1038/385533a0
23. de Vivo, L. e colleghi (2017). Ultrastructural evidence for synaptic scaling across the wake/sleep cycle. Science. https://doi.org/10.1126/science.aah5982
24. Roediger, H. L. e Karpicke, J. D. (2006). Test-enhanced learning. Psychological Science. https://doi.org/10.1111/j.1467-9280.2006.01693.x
25. Hupbach, A. e colleghi (2007). Reconsolidation of episodic memories: a subtle reminder triggers integration of new information. Learning & Memory. https://doi.org/10.1101/lm.365707
26. Detre, G. J., Natarajan, A., Gershman, S. J. e Norman, K. A. (2013). Moderate levels of activation lead to forgetting in the think/no-think paradigm. Neuropsychologia. https://doi.org/10.1016/j.neuropsychologia.2013.02.017
27. Ritvo, V. J. H., Turk-Browne, N. B. e Norman, K. A. (2019). Nonmonotonic plasticity: how memory retrieval drives learning. Trends in Cognitive Sciences. https://doi.org/10.1016/j.tics.2019.06.007
28. Nader, K., Schafe, G. E. e LeDoux, J. E. (2000). Fear memories require protein synthesis in the amygdala for reconsolidation after retrieval. Nature. https://doi.org/10.1038/35021052
29. Sevenster, D., Beckers, T. e Kindt, M. (2013). Prediction error governs pharmacologically induced amnesia for learned fear. Science. https://doi.org/10.1126/science.1231357
30. Brainerd, C. J. e Reyna, V. F. (2002). Fuzzy-trace theory and false memory. Current Directions in Psychological Science. https://doi.org/10.1111/1467-8721.00192
31. Winocur, G. e Moscovitch, M. (2011). Memory transformation and systems consolidation. Journal of the International Neuropsychological Society. https://doi.org/10.1017/s1355617711000683
32. McClelland, J. L., McNaughton, B. L. e O'Reilly, R. C. (1995). Why there are complementary learning systems in the hippocampus and neocortex. Psychological Review. https://doi.org/10.1037/0033-295X.102.3.419
33. Marsland, S., Shapiro, J. e Nehmzow, U. (2002). A self-organising network that grows when required. Neural Networks. https://doi.org/10.1016/S0893-6080(02)00078-3
