#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${DARKEDEN_ENV_FILE:-$SCRIPT_DIR/.env.selfbuilt}
COMPOSE_FILE=$SCRIPT_DIR/compose.selfbuilt.yaml
LOG_DIR=$SCRIPT_DIR/build-logs
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG_FILE=$LOG_DIR/selfbuilt-build-$STAMP.log

mkdir -p "$LOG_DIR"
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found. Run this script on the Docker host." >&2
    exit 127
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required (docker compose)." >&2
    exit 127
fi

if [[ -f "$ENV_FILE" ]]; then
    COMPOSE_ENV=(--env-file "$ENV_FILE")
else
    COMPOSE_ENV=()
fi
COMPOSE=(docker compose "${COMPOSE_ENV[@]}" -f "$COMPOSE_FILE")

cd "$REPO_ROOT"
SOURCE_REVISION=$(git rev-parse HEAD 2>/dev/null || printf 'no-git-metadata')
SOURCE_TREE_SHA256=$(
    find CMakeLists.txt src data docker/conf standalone/start.sh Dockerfile.selfbuilt \
        -type f -print0 2>/dev/null \
        | sort -z \
        | xargs -0 sha256sum \
        | sha256sum \
        | awk '{print $1}'
)
SOURCE_PATCH_SHA256=$(
    git diff HEAD --binary -- CMakeLists.txt src data docker/conf standalone/start.sh Dockerfile.selfbuilt 2>/dev/null \
        | sha256sum \
        | awk '{print $1}'
)
SOURCE_DIRTY=false
if [[ -n $(git status --porcelain -- CMakeLists.txt src data docker/conf standalone/start.sh Dockerfile.selfbuilt 2>/dev/null || true) ]]; then
    SOURCE_DIRTY=true
fi

export DARKEDEN_SOURCE_REVISION=$SOURCE_REVISION
export DARKEDEN_SOURCE_TREE_SHA256=$SOURCE_TREE_SHA256
export DARKEDEN_SOURCE_PATCH_SHA256=$SOURCE_PATCH_SHA256

{
    printf 'Build started: %s\n' "$STAMP"
    printf 'Repository: %s\n' "$REPO_ROOT"
    printf 'Source revision: %s\n' "$SOURCE_REVISION"
    printf 'Source input SHA-256: %s\n' "$SOURCE_TREE_SHA256"
    printf 'Tracked patch SHA-256: %s\n' "$SOURCE_PATCH_SHA256"
    printf 'Relevant worktree dirty: %s\n' "$SOURCE_DIRTY"
    printf 'Docker: '; docker --version
    printf 'Compose: '; docker compose version
    printf 'Base image: selected by Compose env file (default ubuntu:20.04)\n'
    printf '\n--- Docker build output ---\n'
} | tee "$LOG_FILE"

set +e
"${COMPOSE[@]}" build --progress plain game 2>&1 | tee -a "$LOG_FILE"
BUILD_STATUS=${PIPESTATUS[0]}
set -e

if (( BUILD_STATUS != 0 )); then
    printf '\nBuild failed with exit code %d. Full log: %s\n' "$BUILD_STATUS" "$LOG_FILE" | tee -a "$LOG_FILE" >&2
    exit "$BUILD_STATUS"
fi

{
    printf '\n--- Built image metadata ---\n'
    docker image inspect darkeden-selfbuilt:local \
        --format 'image_id={{.Id}}{{"\n"}}labels={{json .Config.Labels}}'
    docker run --rm --entrypoint cat darkeden-selfbuilt:local \
        /usr/share/darkeden-build/build-info.txt
    printf '\nBuild succeeded. Full log: %s\n' "$LOG_FILE"
} 2>&1 | tee -a "$LOG_FILE"
