#!/usr/bin/env bash
# Reverse SSH tunnel: đưa Ollama của container về loopback Hostinger.
#   Hostinger 127.0.0.1:11434  ->  VPS AI 127.0.0.1:11434 (Ollama)
#
# Cách chạy (container KHÔNG có systemd):
#   tmux new -s tunnel
#   bash tunnel.sh
#   # tách khỏi tmux: Ctrl+B rồi nhấn D
set -u

REMOTE_USER=root
REMOTE_HOST=187.127.208.218
REMOTE_PORT=11434   # cổng trên Hostinger (loopback)
LOCAL_PORT=11434    # cổng Ollama trong container

while true; do
  echo "[$(date '+%F %T')] Mở tunnel ${REMOTE_PORT} -> ${LOCAL_PORT} ..."
  ssh -N \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes \
      -R "127.0.0.1:${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" \
      "${REMOTE_USER}@${REMOTE_HOST}"
  echo "[$(date '+%F %T')] Tunnel rớt, thử lại sau 5s ..."
  sleep 5
done
