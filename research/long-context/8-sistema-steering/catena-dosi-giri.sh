#!/bin/bash
# 24/10 (l'utente: "appena possibile fai partire il successivo lavoro preliminare alla fase 2"): dopo il giro medio,
# taratura delle dosi dei giri INTERNO (intense) ed ESTERNO (lievi; serenità gia' fatta a parte), vettori
# sé-interno / sé-esterno del 22/10, L15-L31, pensiero, 12 contesti, passi di 0.005 da 0.015 a 0.075 + caso a
# 0.03/0.05/0.07. Poi giudice Opus e rifinitura a 0.001 attorno al picco. Uscita prova-dosi-giri.jsonl.
cd /data/memoria-episodica-affettiva/research/long-context
while systemctl --user is-active --quiet dosi-fiducia-fine || systemctl --user is-active --quiet catena-dosi-recupero; do sleep 60; done
GROSSE='{"fino31": [0.015,0.02,0.025,0.03,0.035,0.04,0.045,0.05,0.055,0.06,0.065,0.07,0.075]}'
v() { sleep 30; FINESTRE=fino31 MODI=pensiero USCITA=prova-dosi-giri.jsonl ./lancia.sh sistema-vari; echo "$GIRO $FONTI uscita $?"; }
GIRO=interno FONTI=sé-interno DOSI=$GROSSE v
GIRO=interno FONTI=caso DOSI='{"fino31": [0.03,0.05,0.07]}' v
GIRO=esterno EMOZIONI=accettazione,apprensione,distrazione,malinconia,noia,fastidio,interesse FONTI=sé-esterno DOSI=$GROSSE v
GIRO=esterno EMOZIONI=accettazione,apprensione,distrazione,malinconia,noia,fastidio,interesse FONTI=caso DOSI='{"fino31": [0.03,0.05,0.07]}' v
echo fine giri $(date +%T)
