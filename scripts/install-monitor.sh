#!/usr/bin/env bash
# Install/refresh the live monitor collector as a systemd service. Usage: sudo scripts/install-monitor.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
install -m 755 "$REPO/scripts/hotline-monitor.py" /usr/local/sbin/hotline-monitor.py
install -m 644 "$REPO/systemd/hotline-monitor.service" /etc/systemd/system/hotline-monitor.service
systemctl daemon-reload
systemctl enable --now hotline-monitor.service
systemctl restart hotline-monitor.service
echo "Monitor: https://<VM-IP>:8089/static/barangay/monitor.html"
