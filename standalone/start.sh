#!/bin/bash
set -eu
mkdir -p ../log
pids=()
stop() { kill "${pids[@]}" 2>/dev/null || true; wait || true; }
trap stop EXIT
trap 'exit 0' TERM INT
for service in loginserver sharedserver gameserver; do
    "./$service" -f "../conf/$service.conf" &
    pid=$!
    pids+=("$pid")
    case "$service" in loginserver) port=9999;; sharedserver) port=9977;; gameserver) port=9998;; esac
    ready=false
    for ((i=0; i<180; i++)); do
        kill -0 "$pid" || exit 1
        if (echo >"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then ready=true; break; fi
        sleep 1
    done
    "$ready" || { echo "$service did not open port $port" >&2; exit 1; }
done
wait -n || true
exit 1
