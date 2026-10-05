#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-http://1.201.116.156:18002}"

echo "Checking ${base_url}/health"
curl --fail --silent --show-error "${base_url}/health"
echo

echo "Checking ${base_url}/version"
curl --fail --silent --show-error "${base_url}/version"
echo
