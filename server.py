#!/usr/bin/env python3
"""24/7 Cloud Backend for AION 2 Twitch Video Overlay Extension."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import json
import os
import re
import threading
import time
from curl_cffi import requests as cffi_requests

PORT = int(os.environ.get("PORT", 8765))
ALLOWED_CHARS = {"Teiza", "SteveDzs", "Snowflake"}
SIEL_API = "https://siel.tools/api/players/eu/2309/"
OFFICIAL_NEWS_URL = "https://aion2.plaync.com/en-us/board/notice"

CACHE = {}
CACHE_LOCK = threading.RLock()
FETCH_LOCK = threading.Lock()
LAST_REQ = 0.0

def get_cached(key, ttl):
    with CACHE_LOCK:
        entry = CACHE.get(key)
        if entry and time.time() - entry[0] < ttl:
            return entry[1]
    return None

def set_cached(key, data):
    with CACHE_LOCK:
        CACHE[key] = (time.time(), data)

def parse_plaync_news(html):
    items = []
    pattern = re.compile(r'<a[^>]+href=["\'](/en-us/board/notice/view\?articleId=[^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for href, raw_title in pattern.findall(html):
        title = re.sub(r'<[^>]+>', ' ', raw_title)
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 4:
            items.append({
                "title": title,
                "url": f"https://aion2.plaync.com{href}",
                "source": "NCSOFT Official"
            })
        if len(items) >= 8:
            break
    if not items:
        items = [
            {"title": "AION 2 Official Notices & Patch Notes", "url": OFFICIAL_NEWS_URL, "source": "NCSOFT Official"},
            {"title": "Server Status & Maintenance Schedule", "url": OFFICIAL_NEWS_URL, "source": "NCSOFT Official"}
        ]
    return items

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        global LAST_REQ
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/health"):
            self._send_json({"status": "AION 2 Twitch Extension API Running"})
            return

        if parsed.path == "/character":
            name = parse_qs(parsed.query).get("name", ["Teiza"])[0]
            if name not in ALLOWED_CHARS:
                self._send_json({"error": "Character not allowed"}, 400)
                return

            cached = get_cached(f"char:{name}", 180)
            if cached:
                self._send_json(cached)
                return

            with FETCH_LOCK:
                cached = get_cached(f"char:{name}", 180)
                if cached:
                    self._send_json(cached)
                    return

                wait = 4.0 - (time.time() - LAST_REQ)
                if wait > 0:
                    time.sleep(wait)
                LAST_REQ = time.time()

                try:
                    resp = cffi_requests.get(
                        f"{SIEL_API}{name}",
                        impersonate="chrome",
                        headers={
                            "Accept": "application/json, text/plain, */*",
                            "Accept-Language": "en-US,en;q=0.9",
                            "Referer": f"https://siel.tools/eu/nemon/{name}",
                        },
                        timeout=20,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        set_cached(f"char:{name}", data)
                        self._send_json(data)
                        return
                    self._send_json({"error": f"Siel API HTTP {resp.status_code}"}, 502)
                except Exception as e:
                    self._send_json({"error": str(e)}, 502)
            return

        if parsed.path == "/news":
            cached = get_cached("news", 900)
            if cached:
                self._send_json(cached)
                return

            try:
                resp = cffi_requests.get(
                    OFFICIAL_NEWS_URL,
                    impersonate="chrome",
                    headers={"Accept": "text/html,application/xhtml+xml"},
                    timeout=20,
                )
                items = parse_plaync_news(resp.text)
                payload = {"items": items}
                set_cached("news", payload)
                self._send_json(payload)
            except Exception:
                self._send_json({
                    "items": [
                        {"title": "AION 2 Official Notices & Patch Notes", "url": OFFICIAL_NEWS_URL, "source": "NCSOFT Official"}
                    ]
                })
            return

        self._send_json({"error": "Not found"}, 404)

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server listening on port {PORT}")
    server.serve_forever()
