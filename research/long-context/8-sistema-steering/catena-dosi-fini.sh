#!/bin/bash
# 24/10: "una volta individuato il picco di utilità rifinisci a step di 0.001 per avere un range di dosaggi
# per ogni emozione, fallo anche per le altre emozioni". Picchi dal giudice Opus su frase-b (8 contesti, sé, pensiero,
# L15-L31): gioia 0.025-0.04, paura 0.055, sorpresa 0.04-0.065, tristezza 0.04-0.045, serenità 0.04-0.06.
# Attesa (nuova del giro medio) non ha dati: prima a passi di 0.005. Fiducia, rabbia, disgusto: dopo sistema-dosi-3
# e il loro giudizio. Parte quando sistema-dosi-3 ha finito. Uscita prova-dosi-fini.jsonl.
cd /data/memoria-episodica-affettiva/research/long-context
while systemctl --user is-active --quiet sistema-dosi-3; do sleep 60; done
d() { python3 -c "import json;print(json.dumps({'fino31':[round($1+i*0.001,3) for i in range(int(round(($2-$1)/0.001))+1)]}))"; }
export GIRO=medio FINESTRE=fino31 MODI=pensiero USCITA=prova-dosi-fini.jsonl
EMOZIONI=gioia     FONTI=sé-medio   DOSI=$(d 0.020 0.045) ./lancia.sh sistema-vari
EMOZIONI=paura     FONTI=sé-medio   DOSI=$(d 0.040 0.065) ./lancia.sh sistema-vari
EMOZIONI=tristezza FONTI=sé-medio   DOSI=$(d 0.025 0.050) ./lancia.sh sistema-vari
EMOZIONI=sorpresa  FONTI=sé-medio   DOSI=$(d 0.035 0.065) ./lancia.sh sistema-vari
EMOZIONI=attesa    FONTI=sé-medio   DOSI='{"fino31": [0.02,0.025,0.03,0.035,0.04,0.045,0.05,0.055,0.06,0.065,0.07,0.075]}' USCITA=prova-dosi-medio.jsonl ./lancia.sh sistema-vari
GIRO=esterno EMOZIONI=serenità FONTI=sé-esterno DOSI=$(d 0.030 0.065) ./lancia.sh sistema-vari
echo fine catena $(date +%T)
