"""An optional passcode in front of the whole game, so a public URL can't burn the Gemini quota.

Set ACCESS_CODE and the page, the API and the WebSocket all need it once. After that a
cookie remembers the browser. Without ACCESS_CODE nothing changes."""
import hashlib
import hmac
import os
import time

COOKIE = "dungeon_access"
MAX_AGE = 60 * 60 * 24 * 365
# things that have to load before you've typed the code: the passcode page itself,
# the health check, and what Android needs to install the app
OPEN = ("/login", "/api/login", "/api/health", "/manifest.webmanifest", "/sw.js", "/static/icons/", "/static/favicon.svg")
MAX_FAILS, WINDOW = 10, 15 * 60
MAX_FAILS_ALL = 100  # across every address, in case someone spreads guesses out
_fails = {}


def code():
    return os.getenv("ACCESS_CODE", "").strip()


def enabled():
    return bool(code())


def token():
    # the cookie holds a hash of the code, never the code itself
    return hashlib.sha256(f"ai-dungeon:{code()}".encode()).hexdigest()


def allowed(cookies):
    if not enabled():
        return True
    return hmac.compare_digest(cookies.get(COOKIE, ""), token())


def is_open(path):
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in OPEN)


def _recent(key, now):
    _fails[key] = [t for t in _fails.get(key, []) if now - t < WINDOW]
    return len(_fails[key])


def locked_out(ip, now=None):
    now = now or time.time()
    return _recent(ip, now) >= MAX_FAILS or _recent("*", now) >= MAX_FAILS_ALL


def check(ip, attempt, now=None):
    """True if the attempt is right. Too many wrong guesses from one address locks it out for a while."""
    if locked_out(ip, now):
        return False
    if hmac.compare_digest(" ".join(str(attempt).split()).lower(), code().lower()):
        _fails.pop(ip, None)
        return True
    for key in (ip, "*"):
        _fails.setdefault(key, []).append(now or time.time())
    return False


LOGIN_PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#110e0c">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<title>AI Dungeon</title>
<style>
  html,body{margin:0;height:100%;background:#110e0c;color:#ece3d6;font:17px/1.4 system-ui,sans-serif}
  main{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;gap:18px}
  img{width:72px;height:72px}
  h1{font:600 30px Georgia,serif;margin:0;letter-spacing:.02em}
  p{margin:0;color:#a8998a;text-align:center;max-width:22em}
  form{display:flex;flex-direction:column;gap:12px;width:100%;max-width:320px}
  input{font:inherit;padding:14px 16px;border-radius:12px;border:1px solid #4a3b2e;background:#1c1714;color:#ece3d6;text-align:center;letter-spacing:.04em}
  button{font:600 17px system-ui;padding:14px;border:0;border-radius:12px;background:#c4632a;color:#fff}
  .err{color:#e08a6a;min-height:1.4em}
</style></head>
<body><main>
  <img src="/static/favicon.svg" alt="">
  <h1>AI Dungeon</h1>
  <p>This game is private. Enter the passcode to play.</p>
  <form id="f"><input id="c" name="code" autocomplete="current-password" autocapitalize="none" autocorrect="off"
    spellcheck="false" placeholder="passcode" required autofocus><button>Enter</button><div class="err" id="e"></div></form>
</main>
<script>
document.getElementById("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const r = await fetch("/api/login", {method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({code: document.getElementById("c").value})});
  if (r.ok) { location.replace("/"); return; }
  document.getElementById("e").textContent = r.status === 429 ? "Too many tries. Wait a bit." : "That's not it.";
});
</script></body></html>"""
