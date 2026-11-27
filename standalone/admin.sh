#!/bin/bash
set -eu
export LC_ALL=C
# Use the database login defined by this installation's initialization SQL.
MYSQL_PWD=$(awk -F "'" '/^CREATE USER / && $2 == "elcastle" { print $6; exit }' /docker-entrypoint-initdb.d/0-schema.sql)
: "${MYSQL_PWD:?Missing game database credential in initialization SQL}"
export MYSQL_PWD
db=(mysql --protocol=tcp -uelcastle DARKEDEN)
case "${1:-}" in
health)
    "${db[@]}" -h127.0.0.1 -e 'SELECT IP FROM GameServerInfo' >/dev/null
    ;;
address)
    [[ $ADVERTISE_IP =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || { echo "Expected IPv4 address" >&2; exit 2; }
    IFS=. read -ra parts <<< "$ADVERTISE_IP"
    for part in "${parts[@]}"; do ((10#$part <= 255)) || exit 2; done
    "${db[@]}" -hodk-mysql -e "UPDATE GameServerInfo SET IP='$ADVERTISE_IP' WHERE Nickname='game1'"
    ;;
add-player)
    read -rp 'Player ID (4-10 letters or digits): ' player
    read -rsp 'Game password (6-10 letters or digits): ' password
    if [[ -t 0 ]]; then echo >&2; fi
    player=${player%$'\r'}
    password=${password%$'\r'}
    [[ $player =~ ^[a-zA-Z0-9]{4,10}$ && $password =~ ^[a-zA-Z0-9]{6,10}$ ]] || { echo "Invalid player ID or password." >&2; exit 2; }
    # SQL errors can quote the statement. Report the error code without printing credentials.
    if ! result=$(printf "INSERT INTO Player (PlayerID,Password,Name,CurrentWorldID,CurrentServerGroupID,PayType,creation_date) VALUES ('%s','%s','%s',1,0,0,CURDATE());\n" "$player" "$password" "$player" | "${db[@]}" -h127.0.0.1 2>&1); then
        code=unknown
        if [[ $result =~ ERROR[[:space:]]+([0-9]+) ]]; then code=${BASH_REMATCH[1]}; fi
        case "$code" in
            1062) detail="This player ID already exists." ;;
            1044|1045|1142) detail="The database rejected the login or insert permission." ;;
            2002|2003|2013) detail="Could not connect to MySQL inside the container." ;;
            1049|1146) detail="The game database or player table is missing." ;;
            *) detail="MySQL did not create the account." ;;
        esac
        printf 'Account creation failed (MySQL error %s). %s\n' "$code" "$detail" >&2
        exit 1
    fi
    echo "Player created."
    ;;
*) exit 2 ;;
esac
