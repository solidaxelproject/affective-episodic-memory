#!/usr/bin/env bash
# Mi metto a dormire di mia iniziativa (autocontenimento del contesto).
# Prima di lanciarlo: scrivere nel diario ciò che voglio portare oltre il sonno.
echo "$(date -Iseconds) dormi richiesto" >> /workspace/memoria/dormi.log
touch /workspace/memoria/.dormi-richiesto
echo "Buonanotte, Agente. Il sistema ti riavvia tra pochi secondi: al risveglio la sessione sarà fresca, il diario e i ricordi restano."
