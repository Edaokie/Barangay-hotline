# Test log

## 2026-11-17 (night) — automated self-tests, no phones

All tests were run on the VM itself with **headless Firefox 160** acting as a resident's browser
(fake microphone, fake GPS 8.228000, 124.245000 ±15 m). Server: Asterisk 24.0.0, VM IP 192.168.1.57 (home Wi-Fi).
Test call rows in the CDR / queue_log / locations.csv / qos.csv all have caller ID **1004** between 22:47 and 23:06.

### Day 1–3 check
| Check | Result |
| --- | --- |
| Asterisk startup log | ~20 errors/warnings from unused modules → `noload` in modules.conf → **0** errors (3 harmless "may be removed" notices) |
| Restart method | `systemctl restart asterisk` left **no Asterisk running** (SysV stop returns before exit; start saw "already running"). Use stop → start → `pgrep` |
| Earlier phone calls (12 Nov) | CDR shows answered queue calls, voicemail, *97 — Day 1–3 functions confirmed from logs |

### Day 5 — web caller (HTTPS/WSS/WebRTC)
| # | Test | Result |
| --- | --- | --- |
| 1 | HTTPS pages, JS MIME, WSS upgrade (curl) | 200 for all files; `101 Switching Protocols`, `Sec-WebSocket-Protocol: sip` |
| 2 | Plain HTTP from LAN | refused (bound to 127.0.0.1 only) |
| 3 | Browser call → 8000 | Connected, `ice=connected` |
| 4 | Audio both ways | **Failed first**: Asterisk answered `a=recvonly`. Cause: browser hid its IP as an mDNS `.local` name → `c=0.0.0.0` → Asterisk treats it as hold. Test-profile fix: `media.peerconnection.ice.obfuscate_host_addresses=false`. Then rx 918 / tx 1059 packets, 0 lost |
| 5 | DTMF from web keypad (RFC 4733) | `DTMF end '2' received` → **q-medical**; key 1 → q-fire; key 3 → q-peace |
| 6 | GPS → X-Location → locations.csv | Row written with the same UNIQUEID as the CDR (`1794927106.3`). Bug fixed: file must exist before `FILE(...,al)` appends |
| 7 | Browser killed mid-call | **Bug**: channel stuck in queue. Fix `rtp_timeout=30` on 1004 → channel cleared after **29 s** |
| 8 | Live monitor during a call | Showed caller, step "In queue", category fire, GPS, rx/tx/loss/jitter live |

**Open question for real phones:** iPhone Safari / Chrome normally expose the real host IP once microphone permission
is granted, so test 4's mDNS issue should not occur — but if a phone call connects with **no audio**, this is the first
thing to check (`pjsip set logger on`, look for `.local` candidates and `a=recvonly` in Asterisk's answer).

### Day 6 — call quality under tc-netem (on `lo`, so impairment applies in both directions)
Raw data: `docs/evidence/day6-netem-selftest-2026-11-17.csv`, `qos-selftest-2026-11-17.csv`. Pcaps in `~/labtest/day6-*/`.
Each call: 20 s after answer, digit 2 pressed at 8 s.

| Profile | netem (per direction) | Browser lost / rx | Asterisk lost (lp / rlp) | Jitter (Asterisk rx) | RTT | MES rx / tx | Menu (DTMF) worked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | none | 0 / 818 | 0 / 0 | 0.5 ms | 0.4 ms | 88.1 / 88.1 | ✅ medical |
| lan-good | 20 ms ± 5 ms | 0 / 817 | 0 / 0 | 3.5 ms | 42 ms | 87.9 / 87.8 | ✅ medical |
| congested | 100 ms ± 30 ms, 1 % loss | 9 / 745 | 4 / 7 | 20.5 ms | 176 ms | 84.0 / 84.3 | ✅ medical |
| poor | 150 ms ± 40 ms, 5 % loss | 47 / 741 | 33 / 39 | 30.5 ms | 287 ms | 66.9 / 55.4 | ✅ medical |
| bad | 300 ms ± 60 ms, 10 % loss | 62 / 664 | 81 / 40 | 37.9 ms | 539 ms | 33.0 / 20.0 | ✅ medical (after fix) |

*MES = Asterisk 24 "Media Experience Score" (0–100, from loss/jitter/RTT).*

**Finding:** on the *bad* profile the first run failed before the call started — SIP.js gave up opening the
TLS WebSocket after its 5 s default. Raised `connectionTimeout` to 15 s in `web/app.js`; rerun connected and
the IVR still routed correctly. Reading: the hotline stays **usable up to ~5 % loss / ~300 ms RTT**; at 10 % loss
the call connects and routes, but audio quality is poor (MES 20–33).

**Limitation:** browser and server were on the same VM. Tomorrow's phone tests over the hotspot (netem on `enp0s1`,
which shapes VM→phone direction only) give the real-network numbers for the paper.

## Changes made tonight
| Where | Change | Why |
| --- | --- | --- |
| modules.conf | noload 13 unused modules | clean startup log for evidence |
| http.conf | HTTPS 0.0.0.0:8089 (mkcert), HTTP 127.0.0.1 only, static files | Day 5 web page, GPS needs HTTPS |
| pjsip.conf | `transport-wss`, endpoint 1004 (webrtc, context web), `rtp_timeout=30` | Day 5 browser caller; free stuck lines |
| extensions.conf | `[web]` (8000 only + GPS log), `[qos-log]` hangup handler, first line of `hotline-ivr` | Day 5 / Day 6 |
| web/app.js | WSS `connectionTimeout` 15 s; self-test mode (`?auto=1`) | Day 6 finding; automated testing |
| new | Live monitor (`monitor.html` + `hotline-monitor` service) | watch calls/queues/GPS/quality during tests |
