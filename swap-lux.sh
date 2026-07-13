#!/usr/bin/env bash
# DA LANCIARE A MANO dopo smoke OK: ripunta llama-35b.service su llama-lux
# b9966 (canale embeddings_input) con backup e rollback automatico.
set -u
SVC=$HOME/.config/systemd/user/llama-35b.service
LUXBIN=/data/llama-lux/build/bin/llama-server
LIBS=/data/llama-lux/build/bin:/usr/local/lib/ollama/cuda_v13

cp "$SVC" "$SVC.llamacpp-bak"   # rollback istantaneo
sed -i "s#^Environment=LD_LIBRARY_PATH=.*#Environment=LD_LIBRARY_PATH=$LIBS#" "$SVC"
sed -i "s#ExecStart=[^ ]*/llama-server #ExecStart=$LUXBIN #" "$SVC"
systemctl --user daemon-reload
systemctl --user restart llama-35b.service
echo "attendo :8090..."
OK=0
for i in $(seq 1 120); do
  curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1 && { OK=1; break; }
  sleep 3
done
if [ "$OK" = 1 ]; then
  echo "OK: Agente online su llama-lux. Backup: $SVC.llamacpp-bak"
else
  echo "KO: rollback al binario precedente"
  cp "$SVC.llamacpp-bak" "$SVC"
  systemctl --user daemon-reload
  systemctl --user restart llama-35b.service
fi
