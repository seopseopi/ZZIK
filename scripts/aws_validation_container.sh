#!/usr/bin/env bash
# Runs only the validation image. Never provisions AWS resources or starts the app.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
mode="${1:-plan}"
image="${ZZIK_VALIDATION_IMAGE:-zzik-aws-validation:local}"
if [[ $# -gt 1 || ! "$image" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/@:-]*$ ]]; then
  echo 'Usage: bash scripts/aws_validation_container.sh [build|plan|execute]' >&2
  exit 2
fi
case "$mode" in
  build)
    exec docker build --target aws-validation -f infra/backend.Dockerfile \
      --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" -t "$image" .
    ;;
  plan) network=none ;;
  execute)
    if [[ "$(uname -s)" != Linux ]]; then
      echo 'Live validation requires the designated Linux EC2 host.' >&2; exit 2
    fi
    if [[ ! "${ZZIK_IAM_USERNAME:-}" =~ ^kmuct-edu-[0-9]{2,3}$ ]]; then
      echo 'Set ZZIK_IAM_USERNAME to your education IAM username.' >&2; exit 2
    fi
    if [[ ! "${ZZIK_VALIDATION_BUCKET:-}" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ||
          "$ZZIK_VALIDATION_BUCKET" != "$ZZIK_IAM_USERNAME-"* ]]; then
      echo 'Set ZZIK_VALIDATION_BUCKET to your existing username-prefixed private test bucket.' >&2; exit 2
    fi
    if [[ ! "${ZZIK_EXPECTED_ROLE:-}" =~ ^[a-zA-Z0-9+=,.@_-]{1,64}$ ]]; then
      echo 'Set ZZIK_EXPECTED_ROLE to the role inside your assigned instance profile.' >&2; exit 2
    fi
    network=host
    ;;
  *) echo 'Expected build, plan, or execute.' >&2; exit 2 ;;
esac
# Only the report directory is mounted. Host AWS keys, .env, and source are not.
reports="$root/data/aws-validation/reports"
if [[ "$reports" == *','* || -L "$root/data" || -L "$root/data/aws-validation" || -L "$reports" ]]; then
  echo 'Report path must not contain commas or symlinked data directories.' >&2; exit 2
fi
mkdir -p "$reports"
report="$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
args=(run --rm --pull=never --read-only --cap-drop ALL --security-opt no-new-privileges
  --user "$(id -u):$(id -g)" --pids-limit 128 --memory 512m --cpus 1
  --tmpfs /tmp:rw,nosuid,nodev,size=64m --network "$network"
  --env AWS_CONFIG_FILE=/dev/null --env AWS_SHARED_CREDENTIALS_FILE=/dev/null
  --env BOTO_CONFIG=/dev/null --env AWS_EC2_METADATA_V1_DISABLED=true
  --mount "type=bind,src=$reports,dst=/reports")
if [[ "$mode" == plan ]]; then
  args+=(--env AWS_EC2_METADATA_DISABLED=true)
fi
args+=("$image" --manifest backend/fixtures/aws-validation/manifest.json
  --region us-east-1 --max-calls 7 --report "/reports/$report")
if [[ "$mode" == execute ]]; then
  args+=(--execute --bucket "$ZZIK_VALIDATION_BUCKET" --expected-role "$ZZIK_EXPECTED_ROLE")
fi
printf 'Report: %s/%s\n' "$reports" "$report" >&2
exec docker "${args[@]}"
