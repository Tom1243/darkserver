#!/bin/bash
set -eu
export LC_ALL=C MYSQL_PWD=elca110
db=(mysql --protocol=tcp -hodk-mysql -uelcastle DARKEDEN)
case "${1:-}" in
address)
    [[ $ADVERTISE_IP =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || { echo "Expected IPv4 address" >&2; exit 2; }
    IFS=. read -ra parts <<< "$ADVERTISE_IP"
    for part in "${parts[@]}"; do ((10#$part <= 255)) || exit 2; done
    "${db[@]}" -e "UPDATE GameServerInfo SET IP='$ADVERTISE_IP' WHERE Nickname='game1'"
    ;;
add-player)
    read -rp 'Player ID (4-10 letters or digits): ' player
    read -rsp 'Game password (6-10 letters or digits): ' password
    echo >&2
    player=${player%$'\r'}; password=${password%$'\r'}
    [[ $player =~ ^[a-zA-Z0-9]{4,10}$ && $password =~ ^[a-zA-Z0-9]{6,10}$ ]] || { echo "Invalid player ID or password." >&2; exit 2; }
    # Never send the password as a process argument or print SQL errors containing it.
    if ! printf "INSERT INTO Player (PlayerID,Password,Name,CurrentWorldID,CurrentServerGroupID,PayType,creation_date) VALUES ('%s','%s','%s',1,0,0,CURDATE());\n" "$player" "$password" "$player" | "${db[@]}" 2>/dev/null; then
        echo "Account creation failed. Check whether the ID already exists and the database is ready." >&2; exit 1
    fi
    echo "Player created."
    ;;
*) exit 2 ;;
esac
