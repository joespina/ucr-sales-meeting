#!/bin/bash
# Pre-deploy checks for one meeting block.  Usage: tools/validate.sh 20260902
set -e
KEY="${1:?usage: tools/validate.sh YYYYMMDD}"
DIR="$(cd "$(dirname "$0")" && pwd)"
{ python3 "$DIR/extract_meetings.py" index.html; echo "const KEY='$KEY';"; cat "$DIR/checks.js"; } > /tmp/_ucr_checks.js
node /tmp/_ucr_checks.js
