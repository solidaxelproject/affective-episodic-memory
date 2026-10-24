#!/bin/bash
# 24/10: la paura di catena-dosi-fini e' stata saltata (lancio non partito fra due prove). Dopo catena-dosi-fini e
# sistema-dosi-3b rilancia TUTTE le prove delle dosi: i punti gia' fatti si saltano, quindi gira solo quello che manca.
# 30 s fra un lancio e l'altro (la GPU si libera piano). Rabbia e disgusto PRIMA (ordine dell'utente).
cd /data/memoria-episodica-affettiva/research/long-context
while systemctl --user is-active --quiet catena-dosi-fini || systemctl --user is-active --quiet sistema-dosi-3b; do sleep 60; done
d() { python3 -c "import json;print(json.dumps({'fino31':[round($1+i*0.001,3) for i in range(int(round(($2-$1)/0.001))+1)]}))"; }
v() { sleep 30; GIRO=${GIRO:-medio} FINESTRE=fino31 MODI=pensiero ./lancia.sh sistema-vari; echo "$EMOZIONI $FONTI uscita $?"; }
EMOZIONI=fiducia          FONTI=sé-medio USCITA=prova-dosi-medio.jsonl DOSI='{"fino31": [0.04,0.045,0.05,0.055,0.06,0.065,0.07,0.075,0.08]}' v
EMOZIONI=rabbia,disgusto  FONTI=sé-medio USCITA=prova-dosi-medio.jsonl DOSI='{"fino31": [0.015,0.02,0.025,0.03,0.035,0.04,0.045]}' v
EMOZIONI=fiducia,rabbia,disgusto FONTI=caso USCITA=prova-dosi-medio.jsonl DOSI='{"fino31": [0.02,0.04,0.06]}' v
EMOZIONI=attesa           FONTI=sé-medio USCITA=prova-dosi-medio.jsonl DOSI='{"fino31": [0.02,0.025,0.03,0.035,0.04,0.045,0.05,0.055,0.06,0.065,0.07,0.075]}' v
EMOZIONI=gioia     FONTI=sé-medio USCITA=prova-dosi-fini.jsonl DOSI=$(d 0.020 0.045) v
EMOZIONI=paura     FONTI=sé-medio USCITA=prova-dosi-fini.jsonl DOSI=$(d 0.040 0.065) v
EMOZIONI=tristezza FONTI=sé-medio USCITA=prova-dosi-fini.jsonl DOSI=$(d 0.025 0.050) v
EMOZIONI=sorpresa  FONTI=sé-medio USCITA=prova-dosi-fini.jsonl DOSI=$(d 0.035 0.065) v
GIRO=esterno EMOZIONI=serenità FONTI=sé-esterno USCITA=prova-dosi-fini.jsonl DOSI=$(d 0.030 0.065) v
echo fine recupero $(date +%T)
