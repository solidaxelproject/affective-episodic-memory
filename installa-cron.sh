#!/usr/bin/env bash
# Installa il cron notturno della memoria (04:30). Da lanciare come utente host (non root, non nel container).
LINEA='30 4 * * * /bin/bash /data/memoria-episodica-affettiva/notte-memoria.sh >> /tmp/notte-memoria.log 2>&1'
(crontab -l 2>/dev/null | grep -vF "notte-memoria.sh"; echo "$LINEA") | crontab -
echo "installato:"
crontab -l | grep notte-memoria
