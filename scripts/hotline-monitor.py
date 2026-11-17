#!/usr/bin/env python3
"""Hotline live monitor collector (lab prototype).

Every 2 s, asks Asterisk (asterisk -rx) for registrations, live calls, queues and RTP
stats, reads the CDR / queue_log / locations.csv / messages.log tails, and writes one
JSON snapshot to the static web root. monitor.html polls that file.

Standard library only, LAN only, read-only towards Asterisk (no AMI/ARI needed).
Run as root (needs the Asterisk control socket and logs): systemd unit hotline-monitor.service
"""
import csv, json, os, re, subprocess, time, datetime

OUT = "/var/lib/asterisk/static-http/barangay/status.json"
LOG = "/var/log/asterisk"
INTERVAL = 2
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def rx(cmd):
    try:
        r = subprocess.run(["asterisk", "-rx", cmd], capture_output=True, text=True, timeout=5)
        return ANSI.sub("", r.stdout)
    except Exception:
        return ""


def tail(path, n):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 64 * 1024))
            return f.read().decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []


def endpoints():
    eps = {}
    for line in rx("pjsip show endpoints").splitlines():
        m = re.match(r"\s*Endpoint:\s+(\d+)(?:/\S*)?\s+(.+?)\s+(\d+) of", line)
        if m:
            eps[m.group(1)] = {"ext": m.group(1), "state": m.group(2).strip(), "calls": int(m.group(3)),
                               "contact": "", "ip": "", "rtt_ms": None, "reg": "Not registered"}
    for line in rx("pjsip show contacts").splitlines():
        m = re.match(r"\s*Contact:\s+(\d+)/(\S+)\s+\S+\s+(\S+)\s+(\S+)", line)
        if m and m.group(1) in eps:
            e = eps[m.group(1)]
            ipm = re.search(r"@([\d.]+|\[[^\]]+\])(?::(\d+))?", m.group(2))
            e.update(contact=m.group(2), ip=ipm.group(1) if ipm else "", reg=m.group(3))
            try:
                e["rtt_ms"] = round(float(m.group(4)), 1)
            except ValueError:
                pass
    names = {"1001": "Resident (iPhone A)", "1002": "Responder 1 (iPhone B)",
             "1003": "Responder 2", "1004": "Web resident (browser)"}
    for k, e in eps.items():
        e["role"] = names.get(k, "")
    return sorted(eps.values(), key=lambda e: e["ext"])


def channel_vars(chan):
    v = {}
    for line in rx(f"core show channel {chan}").splitlines():
        m = re.match(r"\s*(CAT|LOC|TRIES)=(.*)$", line)
        if m:
            v[m.group(1)] = m.group(2).strip()
    return v


def rtp_stats():
    stats = {}
    for line in rx("pjsip show channelstats").splitlines():
        t = line.split()
        # [bridge-id] <channel-id> <uptime> <codec> rxcount rxlost rx% rxjitter txcount txlost tx% txjitter rtt
        for i, tok in enumerate(t):
            if re.fullmatch(r"\d\d:\d\d:\d\d", tok) and i >= 1 and len(t) - i >= 11:
                cid = t[i - 1]
                n = t[i + 2:i + 11]
                try:
                    stats[cid] = {"codec": t[i + 1], "rx": int(n[0]), "rx_lost": int(n[1]), "rx_loss_pct": float(n[2]),
                                  "rx_jitter": float(n[3]), "tx": int(n[4]), "tx_lost": int(n[5]),
                                  "tx_loss_pct": float(n[6]), "tx_jitter": float(n[7]), "rtt": float(n[8])}
                except (ValueError, IndexError):
                    pass
                break
    return stats


def calls():
    out, rtp = [], rtp_stats()
    for line in rx("core show channels concise").splitlines():
        f = line.split("!")
        if len(f) < 14:
            continue
        chan, ctx, exten, _prio, state, app, data, cid, *_rest = f
        dur, bridged, uid = f[11], f[12], f[13]
        v = channel_vars(chan) if chan.startswith("PJSIP/") else {}
        step = {"Playback": "Playing prompt", "BackGround": "Menu", "Background": "Menu", "WaitExten": "Waiting for key",
                "Queue": "In queue (ringing responders)", "VoiceMail": "Leaving voicemail", "Dial": "Ringing",
                "AppDial": "Responder leg", "Echo": "Echo test", "VoiceMailMain": "Checking voicemail",
                "Record": "Recording prompt", "Wait": "Answering", "MixMonitor": "Recording"}.get(app, app)
        out.append({"channel": chan, "context": ctx, "exten": exten, "state": state, "app": app, "data": data,
                    "step": step, "callerid": cid, "duration": int(dur or 0), "bridged": bridged, "uniqueid": uid,
                    "category": v.get("CAT", ""), "location": v.get("LOC", ""),
                    "rtp": rtp.get(chan.split("/", 1)[-1])})
    return out


def queues():
    qs, cur = [], None
    for line in rx("queue show").splitlines():
        m = re.match(r"(q-\S+) has (\d+) calls .*?'(\S+)' strategy.*?C:(\d+), A:(\d+)", line)
        if m:
            cur = {"name": m.group(1), "waiting": int(m.group(2)), "strategy": m.group(3),
                   "completed": int(m.group(4)), "abandoned": int(m.group(5)), "members": [], "callers": []}
            qs.append(cur)
            continue
        if cur is None:
            continue
        mm = re.match(r"\s+(PJSIP/\S+).*\((Not in use|In use|Unavailable|Ringing|Busy|Invalid|On Hold|Unknown|Paused)[^)]*\)(.*)", line)
        if mm:
            cur["members"].append({"name": mm.group(1), "status": mm.group(2), "info": mm.group(3).strip()})
        mc = re.match(r"\s+\d+\.\s+(\S+)\s+\(wait: ([\d:]+)", line)
        if mc:
            cur["callers"].append({"channel": mc.group(1), "wait": mc.group(2)})
    return qs


def locations():
    locs = {}
    for row in csv.reader(tail(f"{LOG}/locations.csv", 200)):
        if len(row) >= 4 and row[1] != "uniqueid":
            locs[row[1]] = row[3]
    return locs


def recent_cdr(locs, n=15):
    rows = []
    for r in csv.reader(tail(f"{LOG}/cdr-csv/Master.csv", n)):
        if len(r) < 18:
            continue
        src, dst, ctx, clid, chan, dchan, app, data, start = r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]
        dur, disp, uid, uf = r[12], r[14], r[16], r[17]
        if app == "Queue" and dchan:
            outcome = f"Answered by {dchan.split('/')[-1].split('-')[0]}"
        elif app == "Queue":
            outcome = "Hung up while waiting"
        elif app == "VoiceMail":
            outcome = "Left voicemail / reached voicemail"
        elif app == "Dial" and dchan and disp == "ANSWERED":
            outcome = f"Talked to {dchan.split('/')[-1].split('-')[0]}"
        elif disp != "ANSWERED":
            outcome = disp.title()
        else:
            outcome = app or disp
        rows.append({"start": start, "src": src, "dst": dst if ctx != "hotline-ivr" else "8000 (hotline)",
                     "category": uf, "outcome": outcome, "duration": int(dur or 0), "uniqueid": uid,
                     "location": locs.get(uid, "")})
    return list(reversed(rows))


QEV = {"ENTERQUEUE": "Caller entered queue", "CONNECT": "Responder answered", "ABANDON": "Caller hung up while waiting",
       "EXITWITHTIMEOUT": "Queue timed out → voicemail", "COMPLETEAGENT": "Responder ended call",
       "COMPLETECALLER": "Caller ended call", "RINGNOANSWER": "Responder did not answer",
       "RINGCANCELED": "Ringing cancelled", "EXITEMPTY": "Left: no responders"}


def queue_events(n=20):
    ev = []
    for line in tail(f"{LOG}/queue_log", n * 2):
        f = line.split("|")
        if len(f) < 5 or f[2] == "NONE":
            continue
        t = datetime.datetime.fromtimestamp(int(f[0])).strftime("%Y-%m-%d %H:%M:%S")
        detail = ""
        if f[4] == "ENTERQUEUE" and len(f) > 6:
            detail = f"caller {f[6]}"
        elif f[4] == "CONNECT" and len(f) > 5:
            detail = f"after {f[5]} s wait"
        elif f[4] in ("COMPLETEAGENT", "COMPLETECALLER") and len(f) > 6:
            detail = f"talk {f[6]} s"
        elif f[4] == "RINGNOANSWER" and len(f) > 5:
            detail = f"rang {int(f[5]) // 1000} s"
        ev.append({"time": t, "queue": f[2], "agent": "" if f[3] == "NONE" else f[3],
                   "event": QEV.get(f[4], f[4]), "code": f[4], "detail": detail, "uniqueid": f[1]})
    return list(reversed(ev))[:n]


def warnings(n=10):
    out = []
    for line in tail(f"{LOG}/messages.log", 300):
        if ("WARNING" in line or "ERROR" in line) and "pubsub" not in line and "may be removed" not in line:
            m = re.match(r"\[([^\]]+)\]\s+(\w+)\[[^\]]*\](?:\[[^\]]*\])?\s+(.*)", line)
            if m:
                out.append({"time": m.group(1), "level": m.group(2), "text": m.group(3)[:200]})
    return list(reversed(out))[:n]


def vm_ips():
    try:
        r = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True)
        return re.findall(r"inet ([\d.]+)", r.stdout)
    except Exception:
        return []


def snapshot():
    up = rx("core show uptime seconds")
    m = re.search(r"System uptime:\s+(\d+)", up)
    locs = locations()
    return {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "asterisk_up": bool(m), "uptime_s": int(m.group(1)) if m else 0, "vm_ips": vm_ips(),
            "endpoints": endpoints(), "calls": calls(), "queues": queues(),
            "recent_calls": recent_cdr(locs), "queue_events": queue_events(), "warnings": warnings()}


def main():
    while True:
        try:
            data = json.dumps(snapshot())
            tmp = OUT + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, OUT)
        except Exception as e:  # keep running; the page shows "stale" if this stops updating
            print("monitor error:", e, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
