#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="${SITE_DIR:-site}"

zensical build

if [[ -n "${READTHEDOCS_OUTPUT:-}" ]]; then
  mkdir -p "${READTHEDOCS_OUTPUT}/html"
  cp -a "${SITE_DIR}/." "${READTHEDOCS_OUTPUT}/html/"
fi

