import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests as cffi_requests

PORT = int(os.environ.get("PORT", 10000))
ALLOWED_CHARS = {"Teiza", "SteveDzs", "Snowflake"}
SIEL_API = "https://siel.tools/api/players/eu/2309/"
OFFICIAL_NEWS_URL = "https://aion2.plaync.com/en-us/board/notice"

CACHE = {}
CACHE_TTL = 180


def fetch_siel_char(name):
    now = time.time()
    key = f"char:{name}"
    if key in CACHE and now - CACHE[key][0] < CACHE_TTL:
        return CACHE[key][1]

    resp = cffi_requests.get(
        f"{SIEL_API}{name}",
        impersonate="chrome",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://siel.tools/eu/nemon/{name}",
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    CACHE[key] = (now, data)
    return data


def fetch_official_news():
    now = time.time()
    key = "news"
    if key in CACHE and now - CACHE[key][0] < 900:
        return CACHE[key][1]

    items = []
    try:
        resp = cffi_requests.get(OFFICIAL_NEWS_URL, impersonate="chrome", timeout=20)
        html = resp.text
        matches = re.findall(
            r'<a[^>]+href=["\'](/en-us/board/notice/view\?articleId=[^"\']+)["\'][^>]*>(.*?)</a>',
            html,
            flags=re.I | re.S,
        )
        for href, raw_title in matches:
            title = re.sub(r"<[^>]+>", " ", raw_title)
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) > 4:
                items.append({
                    "title": title,
                    "url": f"https://aion2.plaync.com{href}",
                    "source": "NCSOFT Official",
                })
            if len(items) >= 8:
                break
    except Exception:
        pass

    if not items:
        items = [
            {"title": "AION 2 Official Notices & Patch Notes", "url": OFFICIAL_NEWS_URL, "source": "NCSOFT Official"},
            {"title": "Server Status & Maintenance Schedule", "url": OFFICIAL_NEWS_URL, "source": "NCSOFT Official"},
        ]

    result = {"items": items}
    CACHE[key] = (now, result)
    return result


class Handler(BaseHTTPRequestHandler):
    def _send_headers(self, status=200, content_type="application/json; charset=utf-8", length=0):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(length))
        self.end_headers()

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_headers(204, "text/plain", 0)

    def do_HEAD(self):
        self._send_headers(200, "application/json; charset=utf-8", 0)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/character":
            name = parse_qs(parsed.query).get("name", ["Teiza"])[0]
            if name not in ALLOWED_CHARS:
                self._send_json({"error": "Character not allowed"}, 400)
                return
            try:
                data = fetch_siel_char(name)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, 502)
            return

        if parsed.path == "/news":
            self._send_json(fetch_official_news())
            return

        self._send_json({"status": "AION 2 Twitch Extension Backend Running"})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server listening on 0.0.0.0:{PORT}")
    server.serve_forever()
