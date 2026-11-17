#!/usr/bin/env bash
# Day 6 self-test: browser (headless Firefox, fake mic + fake GPS) calls the hotline under
# tc-netem network profiles. Collects browser getStats, Asterisk RTCP (qos.csv), CDR category
# (did the DTMF menu still work?) and a pcap per profile.
#
# Usage: scripts/day6-selftest.sh [iface]     (default lo: browser + Asterisk on the same VM)
#   On lo, netem applies to BOTH directions (each packet crosses lo egress once per direction),
#   so per-direction delay/loss below is effectively doubled round-trip. For phone tests use
#   enp0s1 — then netem only shapes VM→phone traffic.
# Needs: sudo, firefox, Firefox test profile at ~/labtest/ff (see docs/test-log.md).
set -uo pipefail
IFACE="${1:-lo}"
HOST="${HOTLINE_HOST:-$(ip -4 -o addr show enp0s1 | awk '{print $4}' | cut -d/ -f1 | head -1)}"
PROFILE_DIR="$HOME/labtest/ff"
OUT="$HOME/labtest/day6-$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT"
URL="https://$HOST:8089/static/barangay/index.html?auto=1&dtmf=2&dtmfAt=8&hangupAt=20"

read -ra NAMES <<< "${PROFILES:-baseline lan-good congested poor bad}"
declare -A NETEM=(
  [baseline]=""
  [lan-good]="delay 20ms 5ms"
  [congested]="delay 100ms 30ms distribution normal loss 1%"
  [poor]="delay 150ms 40ms distribution normal loss 5%"
  [bad]="delay 300ms 60ms distribution normal loss 10%"
)

cleanup() { sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true; sudo pkill -f "tcpdump -i $IFACE -n -w $OUT" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "profile,netem,browser_rx,browser_lost,browser_jitter_s,browser_tx,category_routed,uniqueid,asterisk_rtcp" > "$OUT/results.csv"
for name in "${NAMES[@]}"; do
  rule="${NETEM[$name]}"
  cleanup
  [ -n "$rule" ] && sudo tc qdisc add dev "$IFACE" root netem $rule
  echo "== $name: ${rule:-no impairment} on $IFACE"
  sudo tcpdump -i "$IFACE" -n -w "$OUT/$name.pcap" "udp portrange 10000-20000 or udp portrange 30000-65535" >/dev/null 2>&1 &
  before=$(sudo wc -l < /var/log/asterisk/qos.csv)
  timeout 70 firefox --headless --no-remote --profile "$PROFILE_DIR" "$URL" > "$OUT/$name-browser.log" 2>&1
  sudo pkill -f "tcpdump -i $IFACE -n -w $OUT/$name.pcap" 2>/dev/null; wait 2>/dev/null
  # wait for the hangup handler row
  timeout 20 bash -c "until [ \$(sudo wc -l < /var/log/asterisk/qos.csv) -gt $before ]; do :; done"
  q=$(sudo tail -n +$((before + 1)) /var/log/asterisk/qos.csv | tail -1)
  uid=$(echo "$q" | cut -d, -f2); cat=$(echo "$q" | cut -d, -f4); rtcp=$(echo "$q" | cut -d, -f6-)
  rx=$(grep -oP 'rx packets=\K\d+' "$OUT/$name-browser.log" | tail -1); lost=$(grep -oP 'lost=\K-?\d+' "$OUT/$name-browser.log" | tail -1)
  jit=$(grep -oP 'jitter=\K[0-9.e-]+' "$OUT/$name-browser.log" | tail -1); tx=$(grep -oP 'tx packets=\K\d+' "$OUT/$name-browser.log" | tail -1)
  echo "$name,\"$rule\",${rx:-},${lost:-},${jit:-},${tx:-},${cat:-},${uid:-},\"$rtcp\"" >> "$OUT/results.csv"
  echo "   browser rx=${rx:-?} lost=${lost:-?} jitter=${jit:-?}s tx=${tx:-?} | routed=${cat:-?} | asterisk: $rtcp"
done
cleanup
echo "Results: $OUT/results.csv  (pcaps: open in Wireshark → Decode As RTP → Telephony › RTP › Stream Analysis)"
