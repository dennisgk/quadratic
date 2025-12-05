#!/usr/bin/env bash

set -euo pipefail

# Resolve directory of this script
SCRIPT_DIR="$(dirname -- "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(realpath "$SCRIPT_DIR")"

source "${SCRIPT_DIR}/../python-wasm/utility.sh"
pushd-quiet "${SCRIPT_DIR}"

echo "Building package with 'python -m build'"
python3 -m build

# Copy wheels to quadratic-client/public/
DIST_DIR="${SCRIPT_DIR}/dist"
TARGET_DIR="${SCRIPT_DIR}/../../quadratic-client/public"

mkdir -p "${TARGET_DIR}"

pushd "${DIST_DIR}"
find . -maxdepth 1 -name "*.whl" -exec cp '{}' "${TARGET_DIR}/" \;
popd

popd-quiet

echo "Python build complete."
