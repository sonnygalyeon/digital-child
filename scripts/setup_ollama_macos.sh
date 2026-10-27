#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "$0")/macos/setup_ollama.sh" "$@"
