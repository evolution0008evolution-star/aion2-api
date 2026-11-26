import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests as cffi_requests

PORT = int(os.environ.get("PORT", 10000))
SIEL_BASE = "https://siel.tools/api/players/eu"
NOTICE_LIST_URL = "https://aion2.plaync.com/en-us/board/notice/list"
UPDATE_LIST_URL = "https://aion2.plaync.com/en-us/board/update/list"

EU_SERVERS = {
    "nemon": "2309",
    "hithanya": "2301",
    "siel": "2302",
    "israphel": "2303",
    "nezekan": "2304",
    "zikel": "2305",
    "vaizel": "2306",
    "triniel": "2307",
    "kaisinel": "2308",
    "lumiel": "2310",
    "yustiel": "2311",
    "marchutan": "2312",
    "ariel": "2313",
    "azphel": "2314",
    "fregion": "2315",
    "ereshkigal": "2316",
    "meslamtaeda": "2317",
    "beritra": "2318",
    "nania": "2319",
    "hadala": "2320",
    "tahavatha": "2321",
    "ludra": "2322",
    "luteros": "2323",
    "ulgorn": "2324",
    "phernos": "2325",
    "munin": "2326",
    "daminu": "2327",
    "odar": "2328",
    "kasaka": "2329",
    "zemurru": "2330",
    "bakarma": "2331",
    "kromede": "2332",
    "tsenka": "2333",
    "quai": "2334",
    "kochi": "2335",
    "baba": "2336",
}

CHAR_STORE = {
    "nemon:teiza": {
        "updatedAt": int(time.time()),
        "server": "Nemon",
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
        },
    },
    "nemon:stevedzs": {
        "updatedAt": int(time.time()),
        "server": "Nemon",
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
        },
    },
    "nemon:snowflake": {
        "updatedAt": int(time.time()),
        "server": "Nemon",
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
        },
    },
}

NEWS_CACHE = {"ts": 0.0, "data": None}


def scrape_board(url, board_type):
    found = []
    try:
        resp = cffi_requests.get(
            url,
            impersonate="chrome",
            headers={"Accept-Language": "en-US,en;q=0.9"},
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
                    "source": "NCSOFT Official",
                })
            if len(found) >= 5:
                break
    except Exception:
        pass
    return found


def fetch_official_news():
    now = time.time()
    if NEWS_CACHE["data"] and now - NEWS_CACHE["ts"] < 900:
        return NEWS_CACHE["data"]

    items = scrape_board(UPDATE_LIST_URL, "update") + scrape_board(NOTICE_LIST_URL, "notice")
    if not items:
        items = [
            {
                "title": "AION 2 Official Patch Notes & Updates",
                "url": UPDATE_LIST_URL,
                "source": "NCSOFT Patch Notes",
            },
            {
                "title": "Official Notices & Maintenance Schedule",
                "url": NOTICE_LIST_URL,
                "source": "NCSOFT Official",
            },
            {
                "title": "AION 2 Season 2 Roadmap & Events",
                "url": NOTICE_LIST_URL,
                "source": "NCSOFT Official",
            },
        ]

    result = {"items": items[:8], "updatedAt": int(now)}
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
            name = str(payload.get("name", "")).strip()
            server = str(payload.get("server", "Nemon")).strip() or "Nemon"
            data = payload.get("data")
            if name and isinstance(data, dict):
                key = f"{server.lower()}:{name.lower()}"
                data["updatedAt"] = int(time.time())
                data["server"] = server
                CHAR_STORE[key] = data
                self._send_json({"ok": True, "updated": name, "server": server})
                return
            self._send_json({"error": "Invalid payload"}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/character":
            qs = parse_qs(parsed.query)
            name = str(qs.get("name", ["Teiza"])[0]).strip()
            server = str(qs.get("server", ["Nemon"])[0]).strip() or "Nemon"
            if not re.match(r"^[A-Za-z0-9_]{2,24}$", name):
                self._send_json({"error": "Invalid character name"}, 400)
                return

            srv_slug = server.lower()
            srv_id = EU_SERVERS.get(srv_slug, "2309")
            key = f"{srv_slug}:{name.lower()}"

            try:
                resp = cffi_requests.get(
                    f"{SIEL_BASE}/{srv_id}/{name}",
                    impersonate="chrome",
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Referer": f"https://siel.tools/eu/{srv_slug}/{name}",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    fresh = resp.json()
                    if isinstance(fresh, dict) and "player" in fresh:
                        fresh["updatedAt"] = int(time.time())
                        fresh["server"] = server.capitalize()
                        CHAR_STORE[key] = fresh
            except Exception:
                pass

            if key in CHAR_STORE:
                self._send_json(CHAR_STORE[key])
            else:
                self._send_json({"error": f"Character {name} on {server} not cached yet"}, 404)
            return

        if parsed.path == "/news":
            self._send_json(fetch_official_news())
            return

        self._send_json({
            "status": "AION DAEVA HUB API Running",
            "servers": list(EU_SERVERS.keys()),
            "cached": list(CHAR_STORE.keys()),
        })


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"AION DAEVA HUB Server listening on 0.0.0.0:{PORT}")
    server.serve_forever()
