// "Call Barangay" — browser caller for the lab hotline (SIP.js 0.21.2, served locally).
// Flow: get GPS → register-less INVITE to 8000 over WSS with X-Location header → IVR keypad.
import { UserAgent, Inviter, SessionState } from "./sipjs/index.js";

const CFG = window.HOTLINE_CONFIG;            // from config.js (user, password, target)
const host = location.hostname;
const $ = (s) => document.querySelector(s);
const callBtn = $("#call"), statusEl = $("#status"), locEl = $("#loc"), remote = $("#remote");
const keys = [...document.querySelectorAll(".keys button")];

let ua = null, session = null;

function setStatus(t) { statusEl.textContent = t; }
function setInCall(on) {
  callBtn.classList.toggle("incall", on);
  callBtn.innerHTML = on ? "TAPOS<small>Hang up</small>" : "TAWAG<small>Call Barangay</small>";
  keys.forEach((k) => (k.disabled = !on));
}

// GPS → "lat/lon/accuracy_m" (format the dialplan FILTER accepts). Never blocks the call for long.
function getLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve("none");
    navigator.geolocation.getCurrentPosition(
      (p) => resolve(`${p.coords.latitude.toFixed(6)}/${p.coords.longitude.toFixed(6)}/${Math.round(p.coords.accuracy)}`),
      () => resolve("none"),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
    );
  });
}

async function ensureUA() {
  if (ua) return ua;
  ua = new UserAgent({
    uri: UserAgent.makeURI(`sip:${CFG.user}@${host}`),
    // 15 s (SIP.js default is 5 s): Day 6 netem test showed the TLS/WSS handshake needs longer
    // on a bad link (300 ms ± 60 ms, 10 % loss) — an emergency caller should not be cut off by that.
    transportOptions: { server: `wss://${location.host}/ws`, connectionTimeout: 15 },
    authorizationUsername: CFG.user,
    authorizationPassword: CFG.password,
    displayName: "Web Resident",
    // LAN only: no STUN/TURN servers, host candidates are enough.
    sessionDescriptionHandlerFactoryOptions: { peerConnectionConfiguration: { iceServers: [] }, iceGatheringTimeout: 2000 },
    logLevel: "warn",
  });
  await ua.start();
  return ua;
}

async function startCall() {
  setInCall(true);
  setStatus("Gikuha ang lokasyon… · Getting location…");
  const loc = await getLocation();
  locEl.textContent = loc === "none" ? "Walay GPS · No location shared" : `📍 ${loc.split("/").slice(0, 2).join(", ")} (±${loc.split("/")[2]} m)`;

  try {
    setStatus("Nagkonektar… · Connecting…");
    await ensureUA();
    session = new Inviter(ua, UserAgent.makeURI(`sip:${CFG.target}@${host}`), {
      extraHeaders: [`X-Location: ${loc}`],
      sessionDescriptionHandlerOptions: { constraints: { audio: true, video: false } },
    });
    session.stateChange.addListener((s) => {
      if (s === SessionState.Establishing) setStatus("Nagring… · Ringing…");
      if (s === SessionState.Established) {
        setStatus("Konektado · Connected — pilia ang numero");
        const sdh = session.sessionDescriptionHandler;
        remote.srcObject = sdh.remoteMediaStream;
        remote.play().catch(() => {});
      }
      if (s === SessionState.Terminated) { setStatus("Natapos ang tawag · Call ended"); setInCall(false); session = null; }
    });
    await session.invite();
  } catch (e) {
    console.error(e);
    setStatus("Napakyas · Call failed — " + (e.message || e));
    setInCall(false);
    session = null;
  }
}

function hangUp() {
  if (!session) return setInCall(false);
  if (session.state === SessionState.Established) session.bye();
  else if (session.state === SessionState.Establishing || session.state === SessionState.Initial) session.cancel();
}

function sendDigit(d) {
  const sdh = session && session.sessionDescriptionHandler;
  const ok = !!(sdh && sdh.sendDtmf(d));
  if (ok) setStatus(`Gipili: ${d} · Selected`);
  return ok;
}

callBtn.addEventListener("click", () => (session ? hangUp() : startCall()));
keys.forEach((k) => k.addEventListener("click", () => sendDigit(k.dataset.d)));

// Lab self-test (only when the URL has ?auto=1): call, press a digit, hang up, log each step.
// e.g. index.html?auto=1&dtmf=2&dtmfAt=8&hangupAt=25   (seconds after the call connects)
const q = new URLSearchParams(location.search);
if (q.get("auto") === "1") {
  const t0 = Date.now(), log = (m) => console.log(`SELFTEST +${((Date.now() - t0) / 1000).toFixed(1)}s ${m}`);
  new MutationObserver(() => log(`status: ${statusEl.textContent}`)).observe(statusEl, { childList: true, characterData: true, subtree: true });
  startCall().then(() => {
    const est = setInterval(() => {
      if (!session || session.state !== SessionState.Established) return;
      clearInterval(est);
      const pc = session.sessionDescriptionHandler.peerConnection;
      log(`established; ice=${pc.iceConnectionState}`);
      setTimeout(() => log(`dtmf ${q.get("dtmf") || "2"} sent=${sendDigit(q.get("dtmf") || "2")}`), 1000 * (+q.get("dtmfAt") || 8));
      setTimeout(async () => {
        const st = await pc.getStats();
        st.forEach((r) => {
          if (r.type === "inbound-rtp" && r.kind === "audio") log(`rx packets=${r.packetsReceived} lost=${r.packetsLost} jitter=${r.jitter}`);
          if (r.type === "outbound-rtp" && r.kind === "audio") log(`tx packets=${r.packetsSent}`);
        });
        hangUp(); log("hangup");
      }, 1000 * (+q.get("hangupAt") || 25));
    }, 200);
  });
}
