from future import annotations import os, time, json, threading, queue, base64 from functools import wraps from flask import Flask, request, Response, jsonify

app = Flask(name)
Simple in-memory event queue for SSE live status

_event_q: "queue.Queue[dict]" = queue.Queue(maxsize=2000)

def _env(k: str, default: str | None = None) -> str | None: v = os.environ.get(k) return v if v is not None else default

def _log(kind: str, message: str, extra: dict | None = None): payload = {"kind": kind, "message": message, "ts": time.time()} if extra: payload.update(extra) try: _event_q.put_nowait(payload) except queue.Full: # Drop oldest-like behavior: drain a few and push try: _event_q.get_nowait() _event_q.put_nowait(payload) except Exception: pass

def sse_format(data: dict) -> bytes: return f"data: {json.dumps(data)}\n\n".encode("utf-8")

def basic_auth_required(fn): @wraps(fn) def wrapper(*args, **kwargs): auth = request.authorization u = _env("ADMIN_USER") p = _env("ADMIN_PASS") if not u or not p: return Response("Admin credentials not configured", status=503) if not auth or auth.username != u or auth.password != p: return Response( "Authentication required", 401, {"WWW-Authenticate": 'Basic realm="tandy-scraper"'}, ) return fn(*args, **kwargs) return wrapper

@app.get("/health") def health(): return "ok", 200

@app.get("/") @basic_auth_required def dashboard(): # Minimal live dashboard with a Start button and streaming logs html = f"""
Tandy Leather Class Scraper
Idle
""" return Response(html, mimetype="text/html")

@app.get("/events") @basic_auth_required def events(): def gen(): # Send a hello so UI populates fast yield sse_format({"kind": "INFO", "message": "SSE connected", "ts": time.time()}) last_heartbeat = time.time() while True: try: item = _event_q.get(timeout=5) yield sse_format(item) except queue.Empty: # keep-alive every ~20s now = time.time() if now - last_heartbeat > 20: last_heartbeat = now yield sse_format({"kind": "HEARTBEAT", "message": "ping", "ts": now}) return Response(gen(), mimetype="text/event-stream")

def _background_scrape(): _log("INFO", "Scrape started") try: # We’ll wire this to the real scraper right after we add scraper.py try: import scraper # to be added in next step except Exception as e: _log("ERROR", "scraper.py not found yet. We’ll add it next.", {"detail": str(e)}) _log("INFO", "Stub run complete") return

    scraper.run_all(progress=_log)  # real implementation will stream logs
    _log("SUCCESS", "Scrape complete")
except Exception as e:
    _log("ERROR", "Scrape failed", {"detail": str(e)})

@app.post("/api/scrape") @basic_auth_required def api_scrape(): t = threading.Thread(target=_background_scrape, daemon=True) t.start() return jsonify({"status": "started"}), 202

if name == "main": # For local testing; on Render we use gunicorn (see render.yaml) app.run(host="0.0.0.0", port=10000, debug=False)
