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
NOTICE_LIST_URL = "https://aion2.plaync.com/en-us/board/notice/list"
UPDATE_LIST_URL = "https://aion2.plaync.com/en-us/board/update/list"
STEAM_NEWS_API = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=3393110&count=8&maxlength=300"

CHAR_STORE = {
    "Teiza": {
        "player": {
            "name": "Teiza",
            "level": 45,
            "className": "Ranger",
            "combatPower": 148895,
            "itemLevel": 2509,
            "stats": {
                "Might": 23,
                "Dexterity": 4,
                "Precision": 50,
                "Willpower": 14,
                "Intelligence": 0,
                "Constitution": 5,
            },
            "daevanion": [
                {"name": "Nezekan", "unlocked": 63, "total": 88},
                {"name": "Zikel", "unlocked": 56, "total": 88},
                {"name": "Vaizel", "unlocked": 56, "total": 88},
                {"name": "Triniel", "unlocked": 67, "total": 116},
                {"name": "Azphel", "unlocked": 21, "total": 152},
            ],
        }
    },
    "SteveDzs": {
        "player": {
            "name": "SteveDzs",
            "level": 45,
            "className": "Assassin",
            "combatPower": 130562,
            "itemLevel": 2423,
            "stats": {
                "Might": 17,
                "Dexterity": 16,
                "Precision": 38,
                "Willpower": 0,
                "Intelligence": 0,
                "Constitution": 28,
            },
            "daevanion": [
                {"name": "Nezekan", "unlocked": 65, "total": 88},
                {"name": "Zikel", "unlocked": 55, "total": 88},
                {"name": "Vaizel", "unlocked": 56, "total": 88},
                {"name": "Triniel", "unlocked": 64, "total": 116},
                {"name": "Azphel", "unlocked": 13, "total": 152},
            ],
        }
    },
    "Snowflake": {
        "player": {
            "name": "Snowflake",
            "level": 45,
            "className": "Gladiator",
            "combatPower": 104835,
            "itemLevel": 2096,
            "stats": {
                "Might": 31,
                "Dexterity": 35,
                "Precision": 9,
                "Willpower": 23,
                "Intelligence": 23,
                "Constitution": 5,
            },
            "daevanion": [
                {"name": "Nezekan", "unlocked": 65, "total": 88},
                {"name": "Zikel", "unlocked": 66, "total": 88},
                {"name": "Vaizel", "unlocked": 62, "total": 88},
                {"name": "Triniel", "unlocked": 40, "total": 116},
                {"name": "Azphel", "unlocked": 23, "total": 152},
            ],
        }
    },
}

NEWS_CACHE = {"ts": 0.0, "data": None}


def scrape_plaync_board(url, board_type):
    found = []
    try:
        resp = cffi_requests.get(
            url,
            impersonate="chrome",
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "nc_locale=en-us; language=en-us",
            },
            timeout=15,
        )
        html = resp.text
        pattern = rf'<a[^>]+href=["'](/en-us/board/{board_type}/view\?articleId=[^"']+)["'][^>]*>(.*?)</a>'
        for href, raw_title in re.findall(pattern, html, flags=re.I | re.S):
            title = re.sub(r"<[^>]+>", " ", raw_title)
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) > 4:
                found.append({
                    "title": title,
                    "url": f"https://aion2.plaync.com{href}",
                    "source": "PlayNC Official (EN)",
                })
            if len(found) >= 5:
                break
    except Exception:
        pass
    return found


def fetch_steam_official_news():
    found = []
    try:
        resp = cffi_requests.get(STEAM_NEWS_API, impersonate="chrome", timeout=12)
        if resp.status_code == 200:
            items = resp.json().get("appnews", {}).get("newsitems", [])
            for item in items:
                title = str(item.get("title", "")).strip()
                url = str(item.get("url", "")).strip()
                if title and url:
                    found.append({
                        "title": title,
                        "url": url,
                        "source": "NCSOFT Official News",
                    })
    except Exception:
        pass
    return found


def fetch_official_news():
    now = time.time()
    if NEWS_CACHE["data"] and now - NEWS_CACHE["ts"] < 900:
        return NEWS_CACHE["data"]

    items = scrape_plaync_board(UPDATE_LIST_URL, "update") + scrape_plaync_board(NOTICE_LIST_URL, "notice")

    if not items:
        items = fetch_steam_official_news()

    if not items:
        items = [
            {
                "title": "[Notice] Patch Notes | Nov. 25",
                "url": "https://aion2.plaync.com/en-us/board/update/view?articleId=6b0695806b68bef8bae9148e",
                "source": "PlayNC Patch Notes",
            },
            {
                "title": "[Notice] Updates to AION2 Operational Policy",
                "url": "https://aion2.plaync.com/en-us/board/notice/view?articleId=6b0560208a3bbc3e012690f8",
                "source": "PlayNC Official",
            },
            {
                "title": "AION 2 Official Updates Board (EN)",
                "url": UPDATE_LIST_URL,
                "source": "PlayNC Board",
            },
            {
                "title": "AION 2 Official Notices Board (EN)",
                "url": NOTICE_LIST_URL,
                "source": "PlayNC Board",
            },
        ]

    result = {"items": items[:8]}
    NEWS_CACHE["ts"] = now
    NEWS_CACHE["data"] = result
    return result


class Handler(BaseHTTPRequestHandler):
    def _send_headers(self, status=200, content_type="application/json; charset=utf-8", length=0):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
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

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/push":
            self._send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            name = payload.get("name")
            data = payload.get("data")
            if name in ALLOWED_CHARS and isinstance(data, dict):
                CHAR_STORE[name] = data
                self._send_json({"ok": True, "updated": name})
                return
            self._send_json({"error": "Invalid character payload"}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/character":
            name = parse_qs(parsed.query).get("name", ["Teiza"])[0]
            if name not in ALLOWED_CHARS:
                self._send_json({"error": "Character not allowed"}, 400)
                return

            try:
                resp = cffi_requests.get(
                    f"{SIEL_API}{name}",
                    impersonate="chrome",
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Referer": f"https://siel.tools/eu/nemon/{name}",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    fresh = resp.json()
                    if isinstance(fresh, dict) and "player" in fresh:
                        CHAR_STORE[name] = fresh
            except Exception:
                pass

            self._send_json(CHAR_STORE[name])
            return

        if parsed.path == "/news":
            self._send_json(fetch_official_news())
            return

        self._send_json({
            "status": "AION 2 Twitch Extension Backend Running",
            "characters": list(CHAR_STORE.keys()),
        })


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server listening on 0.0.0.0:{PORT}")
    server.serve_forever()
