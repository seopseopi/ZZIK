#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PG_BIN="${PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
if [ ! -x "$PG_BIN/pg_ctl" ]; then
  echo 'PostgreSQL 17 is required. macOS: brew install postgresql@17'; exit 1
fi
mkdir -p data logs
if [ ! -f data/postgres/PG_VERSION ]; then
  password_file="$(mktemp)"
  chmod 600 "$password_file"
  printf '%s\n' 'moacut-local-only' > "$password_file"
  "$PG_BIN/initdb" -D data/postgres -U moacut --encoding=UTF8 --locale=C --auth-host=scram-sha-256 --auth-local=scram-sha-256 --pwfile="$password_file"
  rm -f "$password_file"
fi
if ! "$PG_BIN/pg_ctl" -D data/postgres status >/dev/null 2>&1; then
  "$PG_BIN/pg_ctl" -D data/postgres -l logs/postgres.log -o '-h 127.0.0.1 -p 54329' start
fi
export PGPASSWORD=moacut-local-only
if ! "$PG_BIN/psql" -h 127.0.0.1 -p 54329 -U moacut -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='moacut'" | rg -q 1; then
  "$PG_BIN/createdb" -h 127.0.0.1 -p 54329 -U moacut moacut
fi
if ! "$PG_BIN/psql" -h 127.0.0.1 -p 54329 -U moacut -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='moacut_test'" | rg -q 1; then
  "$PG_BIN/createdb" -h 127.0.0.1 -p 54329 -U moacut moacut_test
fi
if ! "$PG_BIN/psql" -h 127.0.0.1 -p 54329 -U moacut -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='zzik_e2e'" | rg -q 1; then
  "$PG_BIN/createdb" -h 127.0.0.1 -p 54329 -U moacut zzik_e2e
fi
