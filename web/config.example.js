// Copy to config.js on the server and set the 1004 password from pjsip.conf.
// The [web] context only allows dialling 8000, so this credential can't make other calls.
window.HOTLINE_CONFIG = { user: "1004", password: "<redacted>", target: "8000" };
