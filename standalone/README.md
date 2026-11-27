# Dark Eden dedicated server
From this directory run `docker compose up -d --wait` with Docker Compose v2 and Linux containers. On Unraid or another LAN host, first create a .env file with the following values, replacing the example IP with the host's reachable IPv4 address.

    DARKEDEN_IP=192.168.1.20
    DARKEDEN_BIND=0.0.0.0

Run `docker compose exec odk-mysql bash /opt/darkeden-admin add-player` to create a game login. Use a unique game password because the original game stores it in plaintext. Stock sample accounts are disabled on fresh databases. Use on a trusted network.

Run `docker compose logs game` for startup diagnostics. Use `docker compose down` to stop. The darkeden_world volume retains accounts and characters. After changing the advertised IP, stop and start the stack. The first startup pulls the upstream Linux server image and imports both databases.
