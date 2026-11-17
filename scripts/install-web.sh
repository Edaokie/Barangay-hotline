#!/usr/bin/env bash
# Install the "Call Barangay" page into Asterisk's static web root.
# Usage: sudo scripts/install-web.sh   (SIP.js must already be at $SIPJS_DIR or in the web root)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DST=/var/lib/asterisk/static-http/barangay
mkdir -p "$DST"
install -m 644 "$REPO/web/index.html" "$REPO/web/app.js" "$REPO/web/monitor.html" "$DST/"
if [ ! -f "$DST/config.js" ]; then
  PW=$(awk '/^\[1004\]\(auth-tpl\)/{f=1} f&&/^password=/{sub(/^password=/,"");print;exit}' /etc/asterisk/pjsip.conf)
  printf 'window.HOTLINE_CONFIG = { user: "1004", password: "%s", target: "8000" };\n' "$PW" > "$DST/config.js"
  chmod 644 "$DST/config.js"
fi
if [ -n "${SIPJS_DIR:-}" ]; then rm -rf "$DST/sipjs"; cp -r "$SIPJS_DIR" "$DST/sipjs"; find "$DST/sipjs" -name '*.d.ts' -delete; fi
[ -f "$DST/sipjs/index.js" ] || { echo "SIP.js missing: run with SIPJS_DIR=/path/to/sip.js/lib"; exit 1; }
echo "Installed to $DST — open https://<VM-IP>:8089/static/barangay/index.html"
