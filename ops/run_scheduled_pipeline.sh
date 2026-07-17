#!/bin/sh
set -eu

: "${REVENUE_ANALYTICS_HOME:?REVENUE_ANALYTICS_HOME is required}"

state_dir="${PIPELINE_STATE_DIR:-${REVENUE_ANALYTICS_HOME}/outputs/operations}"
lock_path="${PIPELINE_LOCK_PATH:-${state_dir}/pipeline.lock}"
make_bin="${MAKE_BIN:-make}"
flock_bin="${FLOCK_BIN:-flock}"

mkdir -p "${state_dir}"
exec "${flock_bin}" -n -E 75 "${lock_path}" "${make_bin}" -C "${REVENUE_ANALYTICS_HOME}" orchestrate
