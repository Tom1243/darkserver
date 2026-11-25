#!/bin/bash
set -eu
cd "${1:-.}"
if [[ ! -f compose.yaml || ! -f admin.sh ]]; then
    echo "Run this from the Dark Eden standalone directory." >&2
    exit 1
fi

# Carry over the existing database configuration without printing it.
if ! credential_line=$(grep -m1 '^export LC_ALL=C MYSQL_PWD=' admin.sh); then
    echo "Could not find the existing database configuration." >&2
    exit 1
fi
replacement=$(mktemp)
trap 'rm -f "$replacement"' EXIT
printf '%s\n' '#!/bin/bash' 'set -eu' "$credential_line" > "$replacement"
cat >> "$replacement" <<'ADMIN_HELPER'
db=(mysql --protocol=tcp -uelcastle DARKEDEN)
case "${1:-}" in
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
ADMIN_HELPER
bash -n "$replacement"
if [[ ! -e admin.sh.before-account-fix ]]; then
    cp -p admin.sh admin.sh.before-account-fix
fi
# Keep the same inode so a running container sees the new bind-mounted file.
cat "$replacement" > admin.sh
echo 'Dark Eden account helper updated.'
