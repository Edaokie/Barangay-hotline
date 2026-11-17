# CLAUDE.md — Barangay VoIP Emergency Hotline (Lab Prototype)

## Project goal
Build a **lab-scale prototype** of a free, always-answered emergency hotline for barangay responders
(case study: Barangay Mahayahay, Iligan City), to show the system is feasible before any field deployment.
Owner: Edrian (edoaki), MSU-IIT graduate student. This prototype supports a research proposal and journal article.

**Hard constraints**
- **No public IP, no port forwarding, no internet-facing services.** Everything runs on a local network.
- Server = Ubuntu VM on the owner's MacBook (UTM). Clients = the owner's phones (Linphone).
- Calls must work fully offline on the LAN. Internet is only used for installing packages / tools.
- Zero budget: only free / open-source tools.
- Keep it simple and reproducible; every change should be explainable in a methods section.

## Environment
| Item | Value |
| --- | --- |
| Host | MacBook Pro (Apple Silicon), UTM, network = Bridged (en0) |
| VM | Ubuntu 26.04.1 LTS ARM64, hostname `asterisklab`, user `edoaki` |
| PBX | Asterisk **24.0.0** built from source (`/usr/src/asterisk-24.0.0`), service via `/etc/init.d/asterisk` |
| Channel driver | **PJSIP only** (no chan_sip) |
| Voicemail storage | FILE (not ODBC) |
| Network used for tests | iPhone A Personal Hotspot. VM IP is usually `172.20.10.14` — **always check with `ip -4 addr show enp0s1`** |
| Why hotspot | Home router has Wi-Fi client isolation (phones can't reach the VM). Proven with tcpdump + test web server. |

## Extensions (pjsip.conf, template-based)
| Ext | Role | Device | Password |
| --- | --- | --- | --- |
| 1001 | Resident (caller) | iPhone A, Linphone | `<redacted>` |
| 1002 | Responder 1 | iPhone B, Linphone | `<redacted>` |
| 1003 | Responder 2 | not registered yet (Mac "Telephone" app or 3rd phone) | `<redacted>` |

Transports: `[transport-udp]` and `[transport-tcp]` as **separate** sections, both `0.0.0.0:5060`.
Templates: `[endpoint-tpl](!)` (context=lab, ulaw/alaw, direct_media=no, rtp_symmetric, force_rport,
rewrite_contact, rfc4733), `[auth-tpl](!)`, `[aor-tpl](!)` (max_contacts=1, remove_existing, qualify 30 s).

## Dialplan (extensions.conf)
Context `[lab]`:
- `_100X` → Dial 20 s → VoiceMail(${EXTEN}@default)
- `600` → echo test
- `_7XXX` → prompt recorder: saves `/var/lib/asterisk/sounds/custom/prompt-XXX.wav`
- `8000` → `Goto(hotline-ivr,s,1)` (old Day 3 lines are commented out with `;`, keep them)
- `*97` → VoiceMailMain(${CALLERID(num)}@default)

Context `[hotline-ivr]`: consent prompt-101 → menu prompt-102 →
`1`=fire, `2`=medical, `3`=peace, `i`=invalid (repeat), `t`=timeout (repeat once, then general).
`route`: Set CDR(userfield)=${CAT} → MixMonitor(${CAT}-…wav,b) → prompt-103 → Queue(q-${CAT},t,,,60) → prompt-104 → VoiceMail(1002@default).

Custom prompts: 101 consent, 102 menu, 103 connecting, 104 leave a message (recorded by phone, Filipino/Bisaya).

## Queues (queues.conf)
`[hotline-tpl](!)` strategy=rrmemory, timeout=15, retry=3, wrapuptime=5, ringinuse=no.
`q-general` (1002, 1003), `q-fire` (1002), `q-medical` (1003, 1002), `q-peace` (1002).

## Other config
- `voicemail.conf` `[default]`: 1001/1002/1003 => PIN `<redacted>`
- `cdr.conf`: `usegmtime=no` (CSV in PHT; older rows before 13 Nov 04:08 are UTC)
- `modules.conf`: noload cdr_radius.so, cel_radius.so

## Progress (1-week build plan)
- [x] Day 1 — VM + Asterisk 24 built and running
- [x] Day 2 — 1001 ↔ 1002 calls over hotspot
- [x] Day 3 — hotline queue, consent prompt, recording (MixMonitor), voicemail, *97, CDR
- [ ] Day 4 — IVR with category queues: config loaded, **prompt-102 not recorded yet**, live test pending
- [ ] Day 5 — HTTPS (mkcert) + WSS + SIP.js "Call Barangay" web page with GPS (X-Location header)
- [ ] Day 6 — call-quality tests: `tc netem` profiles + tcpdump/Wireshark, QOS log via `${CHANNEL(rtcp,all)}`
- [ ] Day 7 — evidence pack + 5-minute demo
Later/simulated only: MySQL realtime, dispatcher dashboard, 911 escalation (fake extension), TLS for Linphone.

## Repos
- `/etc/asterisk` — local git (live config, history of every change). Not pushed.
- `~/barangay-hotline` — GitHub (private) mirror. Refresh with `scripts/sync-from-etc.sh` (redacts secrets).

## Rules for Claude Code
1. **Commit before every change:** `sudo git -C /etc/asterisk add -A && sudo git -C /etc/asterisk commit -m "<what/why>"`.
2. Explain the change and show the diff before applying. Change only what was asked.
3. Never add `external_media_address` / `external_signaling_address`, NAT to public IPs, port forwarding, or anything internet-facing.
4. Don't delete the commented-out Day 3 lines or `*.conf.sample` backups.
5. Don't change passwords, transports or bind addresses unless asked.
6. After edits, apply with the lightest reload and verify:
   - dialplan: `sudo asterisk -rx "dialplan reload"` then `dialplan show <ext>@<context>`
   - queues: `sudo asterisk -rx "queue reload all"` then `queue show`
   - pjsip endpoints: `sudo asterisk -rx "pjsip reload"`; **new transports need** `sudo systemctl restart asterisk`
7. Never print or commit passwords/PINs; use `<redacted>`. Run `scripts/sync-from-etc.sh` before every GitHub commit.
8. The owner does the phone actions (dial, answer). Claude watches logs and diagnoses.

## Useful commands
```bash
ip -4 addr show enp0s1                      # VM IP (changes per network)
sudo asterisk -rx "pjsip show contacts"     # who is registered
sudo asterisk -rx "pjsip show transports"
sudo asterisk -rx "queue show"
sudo asterisk -rvvv                         # live console; 'pjsip set logger on' for SIP traces
sudo tcpdump -ni enp0s1 port 5060           # does a phone's traffic reach the VM?
sudo tail -10 /var/log/asterisk/cdr-csv/Master.csv
ls -la /var/spool/asterisk/monitor/         # recordings (44-byte files = never answered, expected)
sudo ls -R /var/spool/asterisk/voicemail/default/
```

## Known issues / lessons
- Phone can't register → first check network reachability (tcpdump), not Asterisk. Home Wi-Fi isolates clients.
- iOS sleeps Linphone → open the app before tests; members show `Unavailable` otherwise.
- `Couldn't negotiate stream 0:audio … (nothing)` on re-INVITE (15× in logs, mostly 1001): check Linphone has PCMU/PCMA enabled and Media encryption = None; capture with `pjsip set logger on` on next test.
- `No registered publish handler for event presence`: Linphone presence publishing; harmless.
- Desktop install once caused two DHCP IPs; fixed by netplan renderer=NetworkManager + cloud-init network disabled.
- Opus on ARM64: `codec_opus` availability unconfirmed — check `core show codecs` before relying on it.

## Deployment requirement (for the proposal)
The barangay network must let devices reach the server: Wi-Fi client isolation off, or server on a wired port.
Remote residents over mobile data need a public IP/relay/TURN — out of scope for this lab.
