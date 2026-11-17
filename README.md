# Barangay VoIP Emergency Hotline — Lab Prototype

Lab-scale prototype of a free, always-answered emergency hotline for barangay responders
(case study: Barangay Mahayahay, Iligan City). Supports an MSU-IIT graduate research proposal.

**Runs fully offline on a local network** — no public IP, no port forwarding, no internet-facing services.

## Stack (all free / open source)
| Part | Tool |
| --- | --- |
| PBX | Asterisk 24.0.0 (built from source), PJSIP |
| Server | Ubuntu 26.04 ARM64 VM in UTM on a MacBook |
| Clients | Linphone on iPhones |
| Network | Phone hotspot (local traffic only) |

## Call flow (dial 8000)
1. Consent notice (prompt-101) — calls are recorded
2. Menu (prompt-102): **1** Fire · **2** Medical · **3** Peace & order · no input → General
3. Category saved to CDR, call recorded (MixMonitor), "connecting" (prompt-103)
4. Category queue rings responders (round-robin, 60 s)
5. Nobody answers → prompt-104 → voicemail, so no call is lost

## Web caller (Day 5)
Open `https://<VM-IP>:8089/static/barangay/index.html` on a device that trusts the lab CA → tap **TAWAG** →
GPS is sent in an `X-Location` SIP header → hotline IVR. Location is logged to `/var/log/asterisk/locations.csv`
(joins to the CDR via UNIQUEID). The browser account can only dial 8000.

## Repo layout
- `asterisk/` — the 7 customised configs from `/etc/asterisk` (**passwords/PINs redacted**)
- `web/` — "Call Barangay" page (index.html, app.js; `config.example.js` → `config.js` on server)
- `scripts/install-web.sh` — install the page + SIP.js into Asterisk's static web root
- `scripts/sync-from-etc.sh` — refresh `asterisk/` from the live server (redacts secrets, refuses to finish if any leak)
- `docs/` — progress notes and evidence for the methods section
- `CLAUDE.md` — project context and working rules

## Reproduce
Copy `asterisk/*.conf` into `/etc/asterisk/`, set your own passwords/PINs in place of `<redacted>`,
then `sudo systemctl restart asterisk`. Register Linphone clients as 1001–1003 to the server's LAN IP.

## Progress
- [x] Day 1 — VM + Asterisk built
- [x] Day 2 — phone-to-phone calls
- [x] Day 3 — queue, consent, recording, voicemail, CDR
- [ ] Day 4 — IVR category queues (live test pending)
- [~] Day 5 — HTTPS/WSS + SIP.js web "Call Barangay" page with GPS (server done; device test pending)
- [ ] Day 6 — call-quality tests (netem, tcpdump, RTCP stats)
- [ ] Day 7 — evidence pack + demo
