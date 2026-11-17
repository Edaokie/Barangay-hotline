#!/usr/bin/env bash
# Copy the customised Asterisk configs from /etc/asterisk into this repo,
# replacing SIP passwords and voicemail PINs with <redacted>.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC=/etc/asterisk
FILES="pjsip.conf extensions.conf queues.conf voicemail.conf cdr.conf modules.conf"
for f in $FILES; do
  sed -E \
    -e 's/^([[:space:]]*password[[:space:]]*=[[:space:]]*).*/\1<redacted>/' \
    -e '/^\[default\]/,/^\[/ s/^([[:space:]]*[0-9]+[[:space:]]*=>[[:space:]]*)[^,]+/\1<redacted>/' \
    "$SRC/$f" > "$REPO/asterisk/$f"
done
echo "Synced: $FILES"
grep -rnE 'ChangeMe|=>[[:space:]]*1234' "$REPO/asterisk" && { echo "SECRET LEAK - aborting"; exit 1; } || echo "Secret check: clean"
