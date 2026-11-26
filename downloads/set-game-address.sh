#!/usr/bin/env bash
set -euo pipefail
# Run from the directory containing the Dark Eden compose.yaml.
[[ -f compose.yaml ]] && docker compose config --services | grep -Fxq configure || {
  echo "Run this from your Dark Eden standalone compose directory."; exit 1;
}
if [[ -v DARKEDEN_IP ]]; then
  echo "Unset the shell's DARKEDEN_IP first so Compose uses this directory's .env."; exit 1
fi
read -rp "IPv4 address players should connect to (public for internet, Tower LAN IP for local): " ip
[[ $ip =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || { echo "Expected an IPv4 address."; exit 1; }
IFS=. read -ra octets <<< "$ip"
for part in "${octets[@]}"; do
  (( 10#$part <= 255 )) && [[ $part == 0 || $part != 0* ]] || { echo "Invalid IPv4 octet."; exit 1; }
done
[[ $ip != 0.0.0.0 ]] || { echo "Enter a reachable address."; exit 1; }
read -rp "Apply $ip and restart the game, disconnecting online players? [y/N] " answer
[[ $answer == [yY] ]] || exit 0
umask 077
tmp=$(mktemp ./.darkeden-env.XXXXXX)
trap 'rm -f "$tmp"' EXIT
if [[ -f .env ]]; then
  cp -p .env ".env.before-address.$(date +%s).$$"
  awk '!/^[[:space:]]*(export[[:space:]]+)?DARKEDEN_IP[[:space:]]*=/' .env > "$tmp"
  chmod --reference=.env "$tmp"
fi
printf 'DARKEDEN_IP=%s\n' "$ip" >> "$tmp"
mv "$tmp" .env
resolved=$(docker compose run --rm --no-deps -T --entrypoint printenv configure ADVERTISE_IP)
[[ $resolved == "$ip" ]] || { echo "Compose overrides ADVERTISE_IP ($resolved). Check compose.yaml and overrides."; exit 1; }
docker compose run --rm --no-deps -T configure
docker compose restart game
echo "Advertised address updated to $ip. Wait for game to become healthy in docker compose ps."
