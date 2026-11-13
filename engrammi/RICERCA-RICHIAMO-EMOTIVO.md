# Ricerca: quale emozione accompagna i frammenti richiamati insieme

Data: 13/11/2026. Tutti i DOI di questo rapporto sono stati controllati uno per uno sull'archivio Crossref (titolo, primo autore, anno, rivista corrispondono). I valori numerici dei parametri marcati "da verificare sul testo" li riporto a memoria: la fonte è giusta, il numero esatto va riletto nel paper prima di usarlo in una pagina pubblica.

Regola di lettura: il comportamento umano misurato guida la funzione. Ogni termine della funzione proposta in C viene da un modello o da un effetto misurato elencato in A e B.

---

## A. I modelli

### A1. ACT-R: memoria dichiarativa

Fonti: Anderson et al. 2004, https://doi.org/10.1037/0033-295X.111.4.1036 ; Anderson e Schooler 1991, https://doi.org/10.1111/j.1467-9280.1991.tb00174.x ; Anderson e Reder 1999, https://doi.org/10.1037/0096-3445.128.2.186 ; Pavlik e Anderson 2005, https://doi.org/10.1207/s15516709cog0000_14

**Attivazione di un pezzo di memoria i**

A_i = B_i + Σ_j W_j · S_ji + ε

**Attivazione di base (base-level)**

B_i = ln( Σ_{k=1..n} t_k^(-d) )

- t_k: tempo trascorso dalla k-esima esposizione o richiamo.
- d: decadimento. Valore standard 0.5. Viene da Anderson e Schooler 1991: la probabilità che un'informazione serva di nuovo nell'ambiente (titoli di giornale, email, parlato ai bambini) segue una legge di potenza nel tempo e nella frequenza. La memoria umana ricalca quella statistica.
- Spiega insieme tre cose: più ripetizioni = più forza (somma), recenza (t piccoli pesano molto), oblio a potenza (legge di Wixted, vedi B).

**Estensione di Pavlik e Anderson 2005 (effetto spaziatura)**

d_k = c · e^(m_{k-1}) + a

Il decadimento di ogni traccia dipende dall'attivazione che il pezzo aveva quando è stato ripassato: ripassare un ricordo già forte serve poco e decade in fretta, ripassare un ricordo debilitato rende di più. Valori tarati su apprendimento di vocaboli giapponese-inglese, circa c = 0.2 e a = 0.18 (da verificare sul testo). È l'analogo psicologico di ciò che FSRS fa con la stabilità S.

**Attivazione diffusa dagli indizi**

S_ji = S − ln(fan_j)

- j: un elemento del contesto attuale (indizio), W_j la sua attenzione (in ACT-R la somma dei W vale circa 1, divisa fra gli indizi).
- fan_j: quanti fatti sono collegati all'indizio j. Più un indizio è condiviso, meno attiva ciascun fatto. È il fan effect, misurato in Anderson e Reder 1999 con tempi di riconoscimento che crescono di decine di millisecondi per ogni fatto in più associato a un concetto.
- S: forza associativa massima, parametro libero, nei modelli tipici fra 1.5 e 3 (da verificare per il singolo modello).

**Probabilità di richiamo (logistica con soglia e rumore)**

P(richiamo) = 1 / (1 + e^(−(A_i − τ)/s))

- τ: soglia di richiamo. Sotto la soglia il pezzo non affiora (ricordo "sulla punta della lingua").
- s: scala del rumore logistico ε; valori usati nei modelli fra 0.2 e 0.5.

**Latenza**

T = F · e^(−A_i)

Più il pezzo è attivo, più arriva in fretta. F è un fattore di scala tarato caso per caso.

**Scelta fra concorrenti.** In ACT-R viene recuperato il pezzo con l'attivazione più alta dopo il rumore: è già un "vincitore prende tutto" con rumore logistico, che equivale a una regola softmax (Luce) sulle attivazioni con temperatura proporzionale a s.

**Estensioni emotive.** Juvina, Larue e Hough 2018, https://doi.org/10.1016/j.cogsys.2017.06.002 , aggiungono a ACT-R un termine di valutazione (valenza e arousal) che entra nell'attivazione: i pezzi con carica affettiva più alta sono più attivi. Esistono anche lavori con un substrato fisiologico (ACT-R/Φ, Dancy e colleghi), non verificati qui.

**Cosa spiega:** frequenza, recenza, oblio a potenza, spaziatura, fan effect, soglia, tempi di risposta.
**Cosa non spiega:** da solo non ha un umore che cambia i ricordi; l'emozione entra solo come aggiunta.

---

### A2. TCM e CMR: il contesto che deriva

Fonti: Howard e Kahana 2002, https://doi.org/10.1006/jmps.2001.1388 ; Sederberg, Howard e Kahana 2008, https://doi.org/10.1037/a0013396 ; Polyn, Norman e Kahana 2009, https://doi.org/10.1037/a0014420 ; Lohnas, Polyn e Kahana 2015, https://doi.org/10.1037/a0039036

**Evoluzione del contesto**

c_i = ρ_i · c_{i−1} + β · c^IN_i

- c: vettore di contesto (stato mentale lento).
- c^IN: contesto richiamato dall'elemento appena visto o ricordato, c^IN = M^FC f_i.
- β: velocità di deriva (β_enc alla codifica, β_rec al richiamo).
- ρ_i è scelto in modo che ||c_i|| = 1: ρ_i = sqrt(1 + β²[(c_{i−1}·c^IN)² − 1]) − β (c_{i−1}·c^IN).

**Associazioni (apprendimento hebbiano)**

ΔM^FC = γ_FC · c_i f_iᵀ ; ΔM^CF = φ_i · γ_CF · f_i c_iᵀ

φ_i = φ_s · e^(−φ_d (i−1)) + 1 è il guadagno "primacy": i primi elementi vengono codificati più forte.

**Attivazione degli elementi dal contesto attuale**

a = M^CF · c_t

**Competizione al richiamo.** Polyn 2009 usa accumulatori che competono con inibizione laterale (leaky competing accumulators): vince il primo che passa la soglia. Le versioni successive (Lohnas 2015 e seguenti) usano la regola di Luce con esponente:

P(i) = (1 − P_stop) · a_i^τ / Σ_k a_k^τ

L'esponente τ rende la scelta non lineare: piccole differenze di somiglianza diventano grandi differenze di probabilità.

**Cosa spiega:** recenza, contiguità temporale (dopo un elemento si ricorda il vicino nella lista), raggruppamento per categoria e per fonte, intrusioni da liste precedenti.
**Cosa non spiega:** consolidamento a lungo termine, oblio su anni (lavora in minuti).

---

### A3. eCMR: l'emozione come parte del contesto

Fonte: Talmi, Lohnas e Daw 2019, https://doi.org/10.1037/rev0000132 ; rassegna di base Talmi 2013, https://doi.org/10.1177/0963721413498893

Due aggiunte a CMR.

1. **L'emozione è una dimensione del contesto.** Ogni elemento ha una componente emotiva (emotivo / neutro). Gli elementi emotivi si legano a un "contesto emotivo" comune. Al richiamo, ricordare un elemento emotivo riporta quel contesto e favorisce altri elementi emotivi: si raggruppano.
2. **Più attenzione alla codifica.** Gli elementi emotivi hanno un guadagno di apprendimento maggiore nella matrice M^CF: φ_emot > 1 moltiplica la forza dell'associazione contesto → elemento.

Effetto chiave riprodotto: il vantaggio della memoria emotiva compare nelle liste miste (emotivi e neutri insieme) e quasi sparisce nelle liste pure. Quindi il vantaggio emotivo è soprattutto **competitivo**: emerge quando gli elementi devono battersi per lo stesso indizio. È esattamente la situazione dei 10 frammenti che affiorano insieme.

**Non spiega:** la differenza fra valenza positiva e negativa (nel modello del 2019 l'emozione è una sola dimensione), l'umore che dura nel tempo.

---

### A4. CMR3: umore, valenza, disturbi emotivi

Fonte: Cohen e Kahana 2022, https://doi.org/10.1037/rev0000334

- Il contesto emotivo ha valenza: componenti separate per negativo, positivo e neutro.
- L'umore è il contesto emotivo corrente: deriva lento con la stessa equazione c_i = ρ c_{i−1} + β c^IN, con un β emotivo separato.
- Ogni ricordo richiamato riporta la sua emozione e sposta l'umore: un ricordo negativo richiamato porta l'umore verso il negativo, che a sua volta favorisce altri ricordi negativi. Questo circolo spiega in un unico modello il richiamo congruente con l'umore, la memoria dipendente dall'umore, la persistenza dell'umore negativo e i ricordi intrusivi.
- Scelta: regola di Luce con esponente, come in CMR.

**Cosa implica per noi:** la somiglianza fra umore attuale u(t) e carica dell'arco C entra nell'attivazione come somiglianza di contesto, e il richiamo aggiorna l'umore.

**Non spiega:** l'attenuazione notturna differenziale (fading affect bias), il riconsolidamento della carica.

---

### A5. Attivazione diffusa semantica

Fonte: Collins e Loftus 1975, https://doi.org/10.1037/0033-295X.82.6.407

La memoria è una rete di concetti. Un concetto attivato propaga attivazione ai vicini, l'attivazione si attenua con la distanza e si somma quando arriva da più strade. Un nodo raggiunto da più indizi insieme supera la soglia prima. È il fondamento concettuale di S_ji di ACT-R. È un modello qualitativo: niente parametri tarati.

---

### A6. Recupero competitivo e oblio indotto dal recupero

Fonti: Anderson, Bjork e Bjork 1994, https://doi.org/10.1037/0278-7393.20.5.1063 ; meta-analisi Murayama et al. 2014, https://doi.org/10.1037/a0037505 ; Mather e Sutherland 2011, https://doi.org/10.1177/1745691611400234

- **Oblio indotto dal recupero (RIF).** Ripassare alcuni elementi di una categoria peggiora il richiamo successivo degli altri elementi della stessa categoria. Nel paradigma originale il calo è dell'ordine di una decina di punti percentuali sugli elementi forti non ripassati. La meta-analisi di Murayama trova un effetto medio piccolo-moderato e robusto (valore preciso da verificare sul testo). Interpretazione di Anderson: inibizione attiva dei concorrenti.
- **Competizione distorta dall'arousal (ABC, Mather e Sutherland).** L'arousal non rafforza tutto: rafforza ciò che già ha priorità alta (saliente o rilevante per lo scopo) e indebolisce ciò che ha priorità bassa. In termini di modello: l'arousal rende la competizione più ripida, un "vincitore prende tutto" più netto.
- **Regola di Luce (1959, libro, nessun DOI):** P(i) = v_i / Σ v_k. Con v = e^(A/θ) diventa la softmax. Con θ → 0 diventa il massimo puro.

---

### A7. Indice ippocampale, completamento e separazione

Fonti: Teyler e DiScenna 1986, https://doi.org/10.1037/0735-7044.100.2.147 ; Teyler e Rudy 2007, https://doi.org/10.1002/hipo.20350 ; Yassa e Stark 2011, https://doi.org/10.1016/j.tins.2011.06.006 ; Nadel e Moscovitch 1997, https://doi.org/10.1016/S0959-4388(97)80010-4

- L'ippocampo non conserva il ricordo: conserva un **indice** che punta ai pezzi sparsi in corteccia. Un indizio parziale riattiva l'indice e l'indice riattiva tutti i pezzi (completamento). È esattamente la struttura engramma condiviso + arco + catena.
- **Separazione dei pattern:** due esperienze simili (stesso paese, due epoche) ricevono indici diversi per non confondersi. **Completamento:** un indizio condiviso (il paese) tende a riattivare l'indice più forte. Yassa e Stark descrivono il passaggio fra i due regimi come non lineare: sotto una certa somiglianza dell'indizio prevale la separazione, sopra prevale il completamento verso la traccia dominante.
- Teoria delle tracce multiple (Nadel e Moscovitch): ogni rievocazione crea una nuova traccia; i ricordi molto rievocati hanno molte tracce. Coerente con la somma di ACT-R.

---

## B. Effetti umani misurati

| Effetto | Cosa si misura | Fonte | Cosa implica per la funzione |
|---|---|---|---|
| Modulazione dell'amigdala alla codifica | Arousal e noradrenalina rafforzano il consolidamento; i ricordi emotivi resistono di più a distanza di giorni che a pochi minuti | McGaugh 2004, https://doi.org/10.1146/annurev.neuro.27.070203.144157 ; Cahill e McGaugh 1998, https://doi.org/10.1016/S0166-2236(97)01214-9 ; Sharot e Phelps 2004, https://doi.org/10.3758/CABN.4.3.294 | Un termine che premia l'intensità di C alla codifica, e che pesa di più col passare del tempo |
| Rete della codifica emotiva | Meta-analisi fMRI: amigdala, ippocampo e corteccia prefrontale predicono il ricordo successivo degli stimoli emotivi | Murty et al. 2010, https://doi.org/10.1016/j.neuropsychologia.2010.07.030 ; Ritchey, Dolcos e Cabeza 2008, https://doi.org/10.1093/cercor/bhm262 | Conferma che il vantaggio nasce alla codifica, quindi va scritto sull'arco, non calcolato solo al richiamo |
| Oblio lento dei ricordi emotivi | La traccia emotiva si dimentica più lentamente perché l'amigdala lega elemento ed emozione | Yonelinas e Ritchey 2015, https://doi.org/10.1016/j.tics.2015.02.009 | L'intensità di C dovrebbe rallentare il calo di R (oppure entrare come termine additivo) |
| Curva a U rovesciata dell'arousal | Prestazione massima ad arousal intermedio, sui topi | Yerkes e Dodson 1908, https://doi.org/10.1002/cne.920180503 | Pertinenza debole per la memoria a lungo termine: nei dati umani di McGaugh e Cahill l'effetto dell'arousal sul ricordo è quasi monotono. Uso consigliato: una saturazione (log), non una U |
| Fading affect bias | L'affetto negativo legato a un ricordo si attenua più in fretta di quello positivo; osservato in diari autobiografici su mesi e anni, in molte culture | Walker, Skowronski e Thompson 2003, https://doi.org/10.1037/1089-2680.7.2.203 ; Walker e Skowronski 2009, https://doi.org/10.1002/acp.1614 | Il sistema lo ha già (sbiadimento notturno più rapido del negativo). Nota importante: sbiadisce l'**affetto**, la **memoria** del fatto invece resta (Yonelinas e Ritchey) |
| Richiamo congruente con l'umore | Si ricordano meglio i contenuti con la stessa valenza dell'umore attuale; effetto robusto nelle persone depresse per il materiale negativo e nei non depressi per il positivo | Bower 1981, https://doi.org/10.1037/0003-066X.36.2.129 ; meta-analisi Matt, Vázquez e Campbell 1992, https://doi.org/10.1016/0272-7358(92)90116-P | Termine di somiglianza fra u(t) e C_j, con segno |
| Memoria dipendente dall'umore | Si ricorda meglio quando l'umore al richiamo è uguale a quello alla codifica, anche per materiale neutro; effetto fragile, compare con umori intensi e stabili e con richiamo libero (generato dall'interno) | Eich 1995, https://doi.org/10.1111/j.1467-9280.1995.tb00309.x ; meta-analisi Ucros 1989, https://doi.org/10.1080/02699938908408077 | Il peso del termine di umore deve crescere con l'intensità dell'umore (D): con umore calmo quasi nullo |
| Memoria dipendente dal contesto ambientale | Liste imparate sott'acqua o a terra: ricordo migliore nello stesso ambiente; meta-analisi: effetto piccolo ma affidabile, ridotto quando si immagina il contesto originale | Godden e Baddeley 1975, https://doi.org/10.1111/j.2044-8295.1975.tb01468.x ; Smith e Vela 2001, https://doi.org/10.3758/BF03196157 | Il luogo è un indizio vero: giustifica l'attivazione diffusa dall'engramma "paese" |
| Legge della potenza dell'oblio | La ritenzione cala come una potenza del tempo, meglio di un esponenziale | Wixted e Ebbesen 1991, https://doi.org/10.1111/j.1467-9280.1991.tb00175.x ; Wixted 2004, https://doi.org/10.1146/annurev.psych.55.090902.141555 | B di ACT-R e R(t) di FSRS sono entrambi a potenza: compatibili |
| Riconsolidamento | Un ricordo richiamato torna labile; se in quella finestra si blocca la sintesi proteica nell'amigdala, la paura condizionata si perde (ratti) | Nader, Schafe e LeDoux 2000, https://doi.org/10.1038/35021052 | Dopo il richiamo l'arco vincente può aggiornare la sua C verso l'umore attuale (piccolo passo) |
| Indice ippocampale | Vedi A7 | Teyler e DiScenna 1986; Teyler e Rudy 2007 | Engramma condiviso = elemento corticale; arco/catena = indice |
| Separazione e completamento | Vedi A7 | Yassa e Stark 2011 | Con indizio condiviso vince la traccia più forte; non lineare |
| Monitoraggio della fonte | Le persone attribuiscono un ricordo a una fonte giudicando le sue caratteristiche (dettagli percettivi, contesto, emozione); errori quando le caratteristiche si somigliano | Johnson, Hashtroudi e Lindsay 1993, https://doi.org/10.1037/0033-2909.114.1.3 | L'emozione iniettata deve venire da UN arco identificabile: mescolare cariche di ricordi diversi produce un affetto senza fonte |
| Inferenza associativa / integrazione | Ricordi che condividono un elemento (A-B, B-C) vengono integrati dall'ippocampo e permettono di inferire A-C | Zeithamova, Schlichting e Preston 2012, https://doi.org/10.3389/fnhum.2012.00070 | L'engramma condiviso lega i due ricordi: affiorano insieme anche se l'indizio tocca solo il luogo |
| Falsi ricordi DRM | Dopo una lista di parole associate (letto, sonno, sogno...) la parola critica non presentata ("dormire") viene ricordata quasi quanto quelle presentate, con alta sicurezza | Roediger e McDermott 1995, https://doi.org/10.1037/0278-7393.21.4.803 | L'attivazione convergente su un nodo condiviso lo fa affiorare: un engramma toccato da molti archi va trattato con il fan, altrimenti domina tutto |
| Reminiscence bump | Gli adulti anziani ricordano di più eventi fra circa 10 e 30 anni di età | Rubin, Rahhal e Poon 1998, https://doi.org/10.3758/BF03211366 | Marginale qui; l'esempio dell'infanzia si spiega già con ripetizione e carica |
| Vantaggio emotivo competitivo | Il vantaggio dei ricordi emotivi è grande nelle liste miste e piccolo nelle pure | Talmi, Lohnas e Daw 2019 | La carica conta soprattutto quando più archi competono: va dentro la competizione |

---

## C. Proposta di funzione

### C1. Attivazione dell'arco j al momento t

A_j(t) = B_j(t) + Σ_k a_k · (S_max − ln fan_k) + λ_W · W_j + γ · ln(1 + κ · ||C_j(t)||) + λ(D) · cos(u(t), C_j(t)) + ε

Termine per termine.

1. **B_j(t) = ln R_j(t)** (forza di base). Da ACT-R (Anderson e Schooler 1991; Pavlik e Anderson 2005). Nel sistema la somma Σ t_k^(−d) non c'è, c'è FSRS. Il ponte è diretto: FSRS usa R(t) = (1 + f · t/S)^(−0.5) (forma delle versioni 4.5 e 5; f = 19/81), una potenza con esponente −0.5, la stessa d = 0.5 di ACT-R. ln R è quindi una forza di base a potenza in cui S riassume ripetizioni e spaziatura (ruolo di d_k in Pavlik e Anderson). Non linearità: logaritmo (rendimenti decrescenti delle ripetizioni).

2. **Σ_k a_k · (S_max − ln fan_k)** (attivazione diffusa dagli engrammi accesi dal messaggio, con a_k attivazione dell'engramma k che appartiene alla catena dell'arco j). Da ACT-R (S_ji, fan effect, Anderson e Reder 1999) e Collins e Loftus 1975. fan_k = numero di archi che toccano l'engramma k. Un luogo condiviso da due ricordi spinge entrambi allo stesso modo e poco: non decide da solo. Non linearità: −ln fan. Protegge anche dall'effetto DRM (engrammi iper-connessi).

3. **λ_W · W_j** (vicinanza al senso del ricordo). Corrisponde alla somiglianza di contesto di CMR (a = M^CF c): quanto l'arco è centrale per il ricordo che si sta completando. Lineare; la non linearità arriva dalla scelta.

4. **γ · ln(1 + κ ||C_j(t)||)** (forza emotiva dell'arco). Da McGaugh 2004, Yonelinas e Ritchey 2015 e dal φ_emot di eCMR (Talmi 2019). C_j(t) è la carica già attenuata di notte: il fading affect bias (Walker) è già dentro. Non linearità: saturazione logaritmica; i dati umani sull'arousal nella memoria a lungo termine mostrano un effetto crescente ma non illimitato, la U rovesciata di Yerkes-Dodson qui non ha supporto diretto.

5. **λ(D) · cos(u(t), C_j(t))** (congruenza con l'umore). Da CMR3 (Cohen e Kahana 2022) e Bower 1981, Matt 1992. Con λ(D) = λ_0 · D: il peso cresce con quanto l'umore è lontano dalla calma, perché la memoria dipendente dall'umore compare solo con umori intensi (Eich 1995). Con umore calmo il termine si spegne. Non linearità: prodotto fra D e coseno (interazione).

6. **ε** rumore logistico di scala s. Da ACT-R. In pratica si usa la softmax sotto, che lo contiene.

**Soglia.** Concorrono solo gli archi con A_j > τ (ACT-R). Se nessuno supera τ non si inietta nulla: il ricordo affiora "senza colore".

### C2. Regola di scelta del vettore unico

P(j) = e^(A_j/θ) / Σ_k e^(A_k/θ), con θ(D) = θ_0 / (1 + η · D)

- Softmax = regola di Luce con rumore logistico (ACT-R; Luce 1959; τ di CMR).
- La temperatura si abbassa quando l'umore è intenso: competizione più ripida, come nella competizione distorta dall'arousal (Mather e Sutherland 2011).
- **Vettore iniettato: C_j* dell'arco con A più alta (argmax)**. Motivo: monitoraggio della fonte (Johnson 1993), l'emozione deve appartenere a un ricordo preciso; e ACT-R recupera un solo pezzo per volta. In alternativa, campionare j secondo P(j) se si vuole la variabilità umana.
- **Dopo la scelta (facoltativo, dai dati umani):** (a) riconsolidamento, C_j* ← (1 − ρ) C_j* + ρ · u(t) con ρ piccolo (Nader 2000; CMR3: il richiamo riporta e aggiorna il contesto); (b) l'umore si sposta verso C_j* (CMR3, c^IN emotivo); (c) piccolo calo di R per i perdenti molto vicini (RIF, Anderson, Bjork e Bjork 1994). Il punto (b) crea il circolo che CMR3 usa per spiegare l'umore negativo che si autoalimenta: va dosato.

### C3. Esempio a mano: la casa d'infanzia

Ipotesi numeriche (illustrative):

- **Arco infanzia**: 500 esposizioni fra 30 e 40 anni fa (giorni 11000-14600) più 20 rievocazioni negli ultimi 10 anni. Carica attuale libertà/gioia ||C|| = 0.6 (positiva, sbiadita poco).
- **Arco giovane adulta**: 40 esposizioni fra 15 e 17 anni fa (giorni 5500-6200), mai rievocato. Carica di disagio 0.7 alla codifica, attenuata a 0.3 (il negativo sbiadisce prima).
- Il messaggio accende l'engramma "paese", condiviso: a = 1, fan = 2, S_max = 2. W_j = 0.5 per entrambi.
- Umore calmo: D = 0.1, λ_0 = 1. cos(u, C_infanzia) = +0.1, cos(u, C_giovane) = −0.1.
- γ = 1, κ = 1, λ_W = 1, θ_0 = 0.4, η = 1.

Calcolo (B calcolato con la formula ACT-R esatta, d = 0.5):

| Termine | Infanzia | Giovane adulta |
|---|---|---|
| B = ln Σ t^(−0.5) | +1.64 | −0.65 |
| Diffusione dal luogo 1·(2 − ln 2) | +1.31 | +1.31 |
| λ_W · W | +0.50 | +0.50 |
| ln(1 + ||C||) | +0.47 | +0.26 |
| λ(D)·cos = 0.1 · (±0.1) | +0.01 | −0.01 |
| **A** | **3.93** | **1.41** |

θ = 0.4 / 1.1 = 0.36. P(infanzia) = 1 / (1 + e^(−(3.93 − 1.41)/0.36)) = 1 / (1 + e^(−7.0)) ≈ 0.999.

Vince l'infanzia, e vince per le ragioni che i dati umani indicano: molte più esposizioni e rievocazioni (somma di ACT-R), carica positiva che ha resistito di più (fading affect bias), mentre il luogo spinge entrambi allo stesso modo (fan). L'emozione che torna col luogo è la libertà dell'infanzia.

**Controprova (umore negativo intenso).** Stesso esempio con D = 0.9, umore orientato al disagio: cos(u, C_giovane) = +0.9, cos(u, C_infanzia) = −0.5, λ = 0.9. Il termine di umore vale +0.81 per la giovane adulta e −0.45 per l'infanzia: A = 3.47 contro 2.23. Vince ancora l'infanzia, ma con margine ridotto (θ = 0.21, P ≈ 0.997). Se in più l'arco giovane fosse stato rievocato spesso di recente (rimuginio), B salirebbe e potrebbe vincere: è la previsione di CMR3 per la depressione, ed è un comportamento umano documentato (Matt 1992). La funzione lo riproduce senza regole speciali.

---

## D. Paper determinanti per la pagina pubblica

1. Anderson, J. R. e Schooler, L. J. (1991). Reflections of the environment in memory. Psychological Science. https://doi.org/10.1111/j.1467-9280.1991.tb00174.x
2. Anderson, J. R. et al. (2004). An integrated theory of the mind. Psychological Review. https://doi.org/10.1037/0033-295X.111.4.1036
3. Polyn, S. M., Norman, K. A. e Kahana, M. J. (2009). A context maintenance and retrieval model of organizational processes in free recall. Psychological Review. https://doi.org/10.1037/a0014420
4. Talmi, D., Lohnas, L. J. e Daw, N. D. (2019). A retrieved context model of the emotional modulation of memory. Psychological Review. https://doi.org/10.1037/rev0000132
5. Cohen, R. T. e Kahana, M. J. (2022). A memory-based theory of emotional disorders. Psychological Review. https://doi.org/10.1037/rev0000334
6. McGaugh, J. L. (2004). The amygdala modulates the consolidation of memories of emotionally arousing experiences. Annual Review of Neuroscience. https://doi.org/10.1146/annurev.neuro.27.070203.144157
7. Walker, W. R., Skowronski, J. J. e Thompson, C. P. (2003). Life is pleasant, and memory helps to keep it that way! Review of General Psychology. https://doi.org/10.1037/1089-2680.7.2.203
8. Bower, G. H. (1981). Mood and memory. American Psychologist. https://doi.org/10.1037/0003-066X.36.2.129
9. Wixted, J. T. e Ebbesen, E. B. (1991). On the form of forgetting. Psychological Science. https://doi.org/10.1111/j.1467-9280.1991.tb00175.x
10. Teyler, T. J. e Rudy, J. W. (2007). The hippocampal indexing theory and episodic memory: updating the index. Hippocampus. https://doi.org/10.1002/hipo.20350
11. Anderson, M. C., Bjork, R. A. e Bjork, E. L. (1994). Remembering can cause forgetting. JEP: Learning, Memory, and Cognition. https://doi.org/10.1037/0278-7393.20.5.1063
12. Mather, M. e Sutherland, M. R. (2011). Arousal-biased competition in perception and memory. Perspectives on Psychological Science. https://doi.org/10.1177/1745691611400234

---

## E. Limiti e cose che i dati umani non dicono

- **Nessun dato umano sceglie "un'emozione unica" fra dieci ricordi.** Gli esperimenti misurano quali elementi si ricordano e in che ordine, non quale affetto accompagna un richiamo multiplo. La regola argmax è una scelta progettuale coerente con ACT-R (un pezzo per volta) e con il monitoraggio della fonte, non un risultato misurato. Nella mente umana l'affetto potrebbe essere una miscela.
- **44 emozioni contro 1-3 dimensioni.** eCMR ha una sola dimensione emotiva, CMR3 tre (negativo, positivo, neutro). Nessun modello tarato usa 44 assi: il coseno su 44 assi è un'estensione mia.
- **I parametri sono tarati su liste di parole in laboratorio** (minuti o giorni), con poche eccezioni (diari del fading affect bias, reminiscence bump). L'estrapolazione a decenni di vita autobiografica non è validata.
- **Memoria del fatto e affetto del fatto sono due cose diverse**: il ricordo emotivo si dimentica più lentamente (Yonelinas e Ritchey), mentre l'affetto negativo sbiadisce più in fretta (Walker). La funzione li tiene separati: R per il fatto, C per l'affetto.
- **La U rovesciata dell'arousal** non è dimostrata per il richiamo a lungo termine di ricordi umani; Yerkes e Dodson è sui topi e riguarda l'apprendimento di un compito.
- **Memoria dipendente dall'umore**: effetto fragile, spesso non replicato con umori lievi (Eich 1995). Il peso λ(D) va tenuto basso con D piccolo.
- **Riconsolidamento negli umani**: la prova forte (Nader 2000) è sui ratti e sulla paura condizionata; nell'uomo i risultati sono misti. Il passo ρ va tenuto piccolo.
- **Valori dei parametri**: d = 0.5 è solido; S_max, s, τ, c, a, φ_emot, i valori numerici di Murayama 2014 e Matt 1992 vanno riletti nei testi prima della pubblicazione. Nel rapporto sono indicati come "da verificare sul testo".
- **Riferimenti non verificati qui**: Luce 1959 (libro, nessun DOI); le estensioni ACT-R/Φ di Dancy e colleghi.
- **FSRS** è un algoritmo tarato su ripassi di flashcard, non su memoria autobiografica: la corrispondenza ln R ≈ forza di base di ACT-R vale nella forma (potenza con esponente −0.5), non nei dati.
