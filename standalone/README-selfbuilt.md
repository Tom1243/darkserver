# Self-built Dark Eden server image

This is an opt-in build and test path. It does not change `compose.yaml`, the existing `darkeden` Compose project, or its `world` database volume. The self-built stack uses a different Compose project and the explicit `darkeden_selfbuilt_world` volume.

The image compiles `loginserver`, `sharedserver`, and `gameserver` from the checkout with the existing C++11 setting. It uses Ubuntu 20.04 as both the build and runtime base and retains the current MySQL 5.7 configuration, resource files, server configs, startup order, and client-facing ports. `sharedserver` TCP 9977 stays internal: the game config connects to `127.0.0.1:9977` because all three server processes share one container network namespace.

## Build

Run these commands on an Unraid host or another Linux Docker host with Git and Docker Compose v2. Clone into a new directory so the existing production checkout and its files remain untouched. Replace the example IP with the address clients should use to reach the host.

```bash
mkdir -p /mnt/user/appdata/darkeden-selfbuilt
cd /mnt/user/appdata/darkeden-selfbuilt
git clone --single-branch --branch selfbuilt https://github.com/Tom1243/darkserver.git source
cd source
cp standalone/.env.selfbuilt.example standalone/.env.selfbuilt
sed -i 's/^DARKEDEN_IP=.*/DARKEDEN_IP=192.168.1.20/; s/^DARKEDEN_BIND=.*/DARKEDEN_BIND=0.0.0.0/' standalone/.env.selfbuilt
./standalone/build-selfbuilt.sh
```

The script writes a timestamped diagnostic log under `standalone/build-logs/` and tags the result `darkeden-selfbuilt:local`. It records the Git revision, hashes of the source/resource/config inputs and tracked patches, compiler/CMake and package versions, and the built image labels. The example `.env.selfbuilt` and build logs are excluded from Git. The clone and build context are about 50 MB before build artifacts; reserve roughly 2–3 GB of free Docker storage for base images, compiler layers, and the MySQL test image. Actual usage depends on the existing Docker cache.

Ubuntu's package repositories can update over time. This pipeline records the versions actually used; for a later fully pinned rebuild, set `DARKEDEN_UBUNTU_BASE_IMAGE` to a tested immutable Ubuntu image digest and pin the apt package versions from the build manifest.

## Fresh-database test

The self-built Compose file initializes its own MySQL 5.7 database volume from the checked-in schema and uses `fresh-world.sql` to disable the bundled sample logins. It never mounts or references the existing production database volume.

The game ports match the current deployment, so stop the production game service while the self-built game is published on the same host ports. Leave the production database and its volume alone. In Unraid, use the existing production Compose file path for `PRODUCTION_COMPOSE` (the file stays in your production appdata directory and is not included here). Then run these from the repository root:

```bash
PRODUCTION_COMPOSE=/path/to/your/existing/production/compose.yaml
docker compose -f "$PRODUCTION_COMPOSE" stop game
docker compose --env-file standalone/.env.selfbuilt -f standalone/compose.selfbuilt.yaml up -d --wait
docker compose --env-file standalone/.env.selfbuilt -f standalone/compose.selfbuilt.yaml ps
docker compose --env-file standalone/.env.selfbuilt -f standalone/compose.selfbuilt.yaml logs --tail=200 game
```

The image startup log should show all three services opening their configured ports. Create a disposable test login in the isolated database:

```bash
docker compose --env-file standalone/.env.selfbuilt -f standalone/compose.selfbuilt.yaml exec odk-mysql bash /opt/darkeden-admin add-player
```

Smoke-test the legacy client: connect, select the test character, enter the world, change zones, talk to an NPC, move an item, reload, then log out and back in to confirm persistence. Exercise one guild action to cover the game-to-sharedserver connection. Record the client build, test account/character, result, and relevant logs.

### Testing from a copy of an existing database

The fresh test world is preferred for the first build. If existing character state is needed, first make a private backup while the game is stopped, then restore that backup **only into** `darkeden_selfbuilt_world`. The test Compose project must remain pointed at its own `odk-mysql` service. Do not mount the production MySQL volume into the self-built stack. Keep dumps private because legacy account records can contain plaintext passwords. The configure job updates the test database's advertised `GameServerInfo` IP; it does not update production data.

## Rollback and cleanup

Stop the test stack without deleting its test database:

```bash
docker compose --env-file standalone/.env.selfbuilt -f standalone/compose.selfbuilt.yaml down
```

Bring the original game process back using the original Compose file:

```bash
docker compose -f "$PRODUCTION_COMPOSE" up -d game
```

If this is a new shell, set `PRODUCTION_COMPOSE` again to the same existing production Compose file path first. On Unraid, the equivalent is starting the original game service in the existing stack.

Only if the isolated test world should be permanently deleted, remove the **self-built** volume explicitly:

```bash
docker volume rm darkeden_selfbuilt_world
```

Do not use `down -v` against the production project. The existing external-image deployment and its database volume remain the fallback until a successful build and client smoke test are reported and a deliberate switch is made.

## Logs and troubleshooting

- Build failure: read the last timestamped `standalone/build-logs/selfbuilt-build-*.log`; it includes the full plain-progress Docker build output and exit status.
- Startup failure: inspect `docker compose ... logs --tail=200 game` and the isolated MySQL logs. The container exits if any server fails to open its expected TCP port.
- Missing shared library: the Docker build checks each executable with `ldd` and fails with the unresolved library name.
- Client cannot connect: confirm `DARKEDEN_IP`, `DARKEDEN_BIND`, host firewall/router rules, and that the original game container is stopped so the shared client ports are available.
- Do not publish TCP 9977 for this combined-container setup; it is the private gameserver-to-sharedserver link.
