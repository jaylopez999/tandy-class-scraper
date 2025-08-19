from future import annotations import time, json, re from typing import Callable, Dict, List, Any from playwright.sync_api import sync_playwright

Store = Dict[str, str] Event = Dict[str, Any] ProgressFn = Callable[[str, str, Dict[str, Any] | None], None]

STORES: List[Store] = [ {"name": "Dallas #27", "url": "https://tandyleather.com/pages/tandy-leather-dallas-27"}, {"name": "Plano #184", "url": "https://tandyleather.com/pages/tandy-leather-184"}, {"name": "Fort Worth #107", "url": "https://tandyleather.com/pages/tandy-leather-fort-worth-107"}, {"name": "Fort Worth #04", "url": "https://tandyleather.com/pages/tandy-leather-fort-worth-04"}, ]

def _noop(kind: str, msg: str, extra: Dict[str, Any] | None = None) -> None: print(f"[{kind}] {msg} {extra or ''}")

def _looks_like_event(obj: Any) -> bool: if not isinstance(obj, dict): return False keys = set(k.lower() for k in obj.keys()) # Very generic heuristics for BookThatApp/event-like payloads return bool( {"title", "start"}.issubset(keys) or {"name", "start"}.issubset(keys) or any("event" in k for k in keys) )

def _extract_events_from_json(js: Any, source_url: str) -> List[Event]: out: List[Event] = [] def normalize(o: Dict[str, Any]) -> Event: title = o.get("title") or o.get("name") or "Class" start = o.get("start") or o.get("start_time") or o.get("starts_at") end = o.get("end") or o.get("end_time") or o.get("ends_at") price = o.get("price") or o.get("cost") or o.get("amount") avail = o.get("availability") or o.get("available") or o.get("spots") or o.get("capacity") return { "title": str(title) if title is not None else "Class", "start": start, "end": end, "price": price, "availability": avail, "source": source_url, } try: if isinstance(js, list): for it in js: if isinstance(it, dict) and _looks_like_event(it): out.append(normalize(it)) elif isinstance(it, dict): # search nested lists for v in it.values(): if isinstance(v, list): for vi in v: if isinstance(vi, dict) and _looks_like_event(vi): out.append(normalize(vi)) elif isinstance(js, dict): # common shapes: {"events":[...]}, {"data":{"events":[...]}} candidates: List[Any] = [] if "events" in js and isinstance(js["events"], list): candidates = js["events"] elif "data" in js and isinstance(js["data"], dict) and isinstance(js["data"].get("events"), list): candidates = js["data"]["events"] else: # fallback: scan dict values for v in js.values(): if isinstance(v, list): candidates.extend(v) for it in candidates: if isinstance(it, dict): out.append(normalize(it)) except Exception: pass return out

def _extract_events_from_dom(page) -> List[Event]: # Fallback: look for visible cards/buttons that look like classes out: List[Event] = [] try: cards = page.locator("text=/book/i").all() for i in range(len(cards)): el = cards[i] try: root = el.locator("xpath=ancestor-or-self::[count(.//button|.//a)=count(.//button|.//a)]").first except Exception: root = el text = root.inner_text(timeout=2000) # naive pulls title_match = re.search(r"(?i)^\s(.+?)\s*(?:\n|$)", text.strip()) time_match = re.search(r"(?i)(\b\d{1,2}:\d{2}\s*(?:AM|PM)\b)", text) price_match = re.search(r"(?i)$[\d]+(?:.\d{2})?", text) spots_match = re.search(r"(?i)(\d+)\s+spots?\s+left", text) title = title_match.group(1).strip() if title_match else "Class" price = price_match.group(0) if price_match else None avail = spots_match.group(1) if spots_match else None out.append({ "title": title, "start": time_match.group(1) if time_match else None, "end": None, "price": price, "availability": avail, "source": page.url, }) except Exception: pass return out

def scrape_store(context, store: Store, progress: ProgressFn = _noop) -> List[Event]: page = context.new_page() page.set_default_timeout(30000) progress("INFO", f"Visiting {store['name']}", {"url": store["url"]})

captured: List[Event] = []

def on_response(resp):
    url = resp.url
    try:
        if ("bookthatapp" in url.lower() or "calendar" in url.lower() or "event" in url.lower()) and \
           (resp.request.resource_type in ("xhr", "fetch")):
            ctype = resp.headers.get("content-type", "")
            if "application/json" in ctype:
                data = resp.json()
                evs = _extract_events_from_json(data, store["url"])
                if evs:
                    captured.extend(evs)
    except Exception:
        pass

page.on("response", on_response)
page.goto(store["url"], wait_until="load")
# allow dynamic widgets to load
try:
    page.wait_for_timeout(4000)
    # Some widgets show spinners; waiting a bit more helps
    page.wait_for_load_state("networkidle", timeout=10000)
except Exception:
    pass

# If we didn’t capture JSON events, try DOM fallback
if not captured:
    dom_events = _extract_events_from_dom(page)
    captured.extend(dom_events)

progress("INFO", f"Found {len(captured)} items at {store['name']}")
page.close()
return captured

def run_all(progress: ProgressFn = _noop) -> Dict[str, List[Event]]: out: Dict[str, List[Event]] = {} with sync_playwright() as pw: browser = pw.chromium.launch(headless=True) context = browser.new_context(user_agent="Mozilla/5.0 (compatible; TandyScraper/1.0)") for store in STORES: try: items = scrape_store(context, store, progress) out[store["name"]] = items # polite delay context.wait_for_timeout(1500) except Exception as e: progress("ERROR", f"Failed {store['name']}", {"detail": str(e)}) out[store["name"]] = [] browser.close() progress("SUCCESS", "All stores processed", {"counts": {k: len(v) for k, v in out.items()}}) return out

if name == "main": run_all()
