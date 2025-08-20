from __future__ import annotations
import os, time, json, threading, queue
from functools import wraps
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

# Simple in-memory event queue for SSE live status
_event_q: "queue.Queue[dict]" = queue.Queue(maxsize=2000)

def _env(k: str, default: str | None = None) -> str | None:
    v = os.environ.get(k)
    return v if v is not None else default

def _log(kind: str, message: str, extra: dict | None = None):
    payload = {"kind": kind, "message": message, "ts": time.time()}
    if extra:
        payload.update(extra)
    try:
        _event_q.put_nowait(payload)
    except queue.Full:
        try:
            _event_q.get_nowait()
            _event_q.put_nowait(payload)
        except Exception:
            pass

def sse_format(data: dict) -> bytes:
    return f"data: {json.dumps(data)}\n\n".encode("utf-8")

def basic_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        u = _env("ADMIN_USER")
        p = _env("ADMIN_PASS")
        if not u or not p:
            return Response("Admin credentials not configured", status=503)
        if not auth or auth.username != u or auth.password != p:
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="tandy-scraper"'},
            )
        return fn(*args, **kwargs)
    return wrapper

@app.get("/health")
def health():
    return "ok", 200

@app.get("/")
@basic_auth_required
def dashboard():
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Tandy Scraper Dashboard</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 16px; }
    .btn { padding: 10px 16px; background: #0d6efd; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }
    .btn:disabled { opacity: .6; cursor: not-allowed; }
    #log { margin-top: 16px; height: 60vh; overflow: auto; background:#111; color:#0f0; padding:12px; border-radius:8px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .bar { display:flex; gap:12px; align-items:center; }
  </style>
</head>
<body>
  <h2>Tandy Leather Class Scraper</h2>
  <div class="bar">
    <button id="start" class="btn">Start Scraping</button>
    <span id="status">Idle</span>
  </div>
  <div id="log"></div>

<script>
const logEl = document.getElementById('log');
const statusEl = document.getElementById('status');
const btn = document.getElementById('start');

function addLog(o) {
  const line = document.createElement('div');
  const ts = new Date(o.ts*1000).toLocaleTimeString();
  line.textContent = `[${ts}] [${o.kind}] ` + (typeof o.message === 'string' ? o.message : JSON.stringify(o.message));
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

const es = new EventSource('/events');
es.onmessage = (ev) => {
  try {
    const data = JSON.parse(ev.data);
    addLog(data);
    if (data.kind === 'SUCCESS' || data.kind === 'ERROR') {
      statusEl.textContent = data.kind === 'SUCCESS' ? 'Done' : 'Error';
    }
  } catch(e) {}
};

btn.onclick = async () => {
  btn.disabled = true;
  statusEl.textContent = 'Running...';
  try {
    const res = await fetch('/api/scrape', { method: 'POST' });
    if (!res.ok) throw new Error('Failed to start scrape');
    const j = await res.json();
    addLog({kind:'INFO', message:'Scrape started: ' + JSON.stringify(j), ts: Date.now()/1000});
  } catch(e) {
    addLog({kind:'ERROR', message:String(e), ts: Date.now()/1000});
  } finally {
    setTimeout(() => { btn.disabled = false; }, 5000);
  }
};
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")

@app.get("/events")
@basic_auth_required
def events():
    def gen():
        yield sse_format({"kind": "INFO", "message": "SSE connected", "ts": time.time()})
        last_heartbeat = time.time()
        while True:
            try:
                item = _event_q.get(timeout=5)
                yield sse_format(item)
            except queue.Empty:
                now = time.time()
                if now - last_heartbeat > 20:
                    last_heartbeat = now
                    yield sse_format({"kind": "HEARTBEAT", "message": "ping", "ts": now})
    return Response(gen(), mimetype="text/event-stream")

def _background_scrape():
    _log("INFO", "Scrape started")
    try:
        try:
            import scraper  # real scraping module you added
        except Exception as e:
            _log("ERROR", "scraper.py not found yet. We’ll add it next.", {"detail": str(e)})
            _log("INFO", "Stub run complete")
            return
        scraper.run_all(progress=_log)
        _log("SUCCESS", "Scrape complete")
    except Exception as e:
        _log("ERROR", "Scrape failed", {"detail": str(e)})

@app.post("/api/scrape")
@basic_auth_required
def api_scrape():
    t = threading.Thread(target=_background_scrape, daemon=True)
    t.start()
    return jsonify({"status": "started"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
