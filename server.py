import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, urljoin
from curl_cffi import requests as cffi_requests

PORT = int(os.environ.get("PORT", 10000))
SIEL_ORIGIN = "https://siel.tools"
SIEL_API_BASE = "https://siel.tools/api/players/eu"
NOTICE_LIST_URL = "https://aion2.plaync.com/en-us/board/notice/list"
UPDATE_LIST_URL = "https://aion2.plaync.com/en-us/board/update/list"

SERVER_IDS = {
    "nemon": "2309", "hithanya": "2308", "siel": "2301", "israphel": "2302",
    "nezekan": "2303", "zikel": "2304", "vaizel": "2305", "triniel": "2306",
    "kaisinel": "2307", "lumiel": "2310", "yustiel": "2311", "marchutan": "2312",
    "ariel": "2313", "azphel": "2314",
}

CHAR_STORE = {
    "nemon:teiza": {
        "player": {
            "name": "Teiza", "server": "Nemon", "level": 45, "className": "Ranger",
            "combatPower": 148895, "itemLevel": 2509,
            "stats": {"Might": 23, "Dexterity": 4, "Precision": 50, "Willpower": 14, "Intelligence": 0, "Constitution": 5},
            "daevanion": [
                {"name": "Nezekan", "unlocked": 63, "total": 88},
                {"name": "Zikel", "unlocked": 56, "total": 88},
                {"name": "Vaizel", "unlocked": 56, "total": 88},
                {"name": "Triniel", "unlocked": 67, "total": 116},
                {"name": "Azphel", "unlocked": 21, "total": 152},
            ],
            "equipment": [],
        }
    }
}

NEWS_CACHE = {"ts": 0.0, "data": None}


def resolve_icon(val):
    if isinstance(val, dict):
        val = val.get("url") or val.get("src") or val.get("path") or val.get("iconUrl")
    if not isinstance(val, str) or not val.strip():
        return ""
    val = val.strip()
    if val.startswith("//"):
        return "https:" + val
    if val.startswith("/"):
        return urljoin(SIEL_ORIGIN, val)
    return val


def extract_equipment_list(root):
    preferred = {
        "equipment", "equipments", "gear", "items", "equipmentlist",
        "equipmentslist", "wornitems", "equippeditems", "equipmentslots"
    }
    queue = [root]
    seen = set()
    while queue:
        obj = queue.pop(0)
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in preferred and isinstance(v, list) and any(isinstance(x, dict) for x in v):
                    return v
                if isinstance(v, (dict, list)):
                    queue.append(v)
        elif isinstance(obj, list):
            if any(isinstance(x, dict) and any(f in x for f in ("itemName", "iconUrl", "slotName", "enchantLevel", "passives")) for x in obj):
                return obj
            for x in obj:
                if isinstance(x, (dict, list)):
                    queue.append(x)
    return []


def normalize_equipment(raw_root):
    raw_items = extract_equipment_list(raw_root)
    normalized = []
    for idx, entry in enumerate(raw_items):
        if not isinstance(entry, dict):
            continue
        item = {**entry.get("item", {}), **entry} if isinstance(entry.get("item"), dict) else entry
        name = item.get("name") or item.get("itemName") or item.get("displayName") or f"Item {idx + 1}"
        slot = item.get("slot") or item.get("slotName") or item.get("equipmentSlot") or item.get("type") or "Equipment"
        icon = resolve_icon(
            item.get("iconUrl") or item.get("iconURL") or item.get("icon") or
            item.get("imageUrl") or item.get("image") or item.get("iconPath")
        )
        anim = resolve_icon(item.get("animationUrl") or item.get("animUrl") or item.get("effectUrl"))
        rarity = str(item.get("rarity") or item.get("grade") or item.get("quality") or "Rare")
        enchant = item.get("enchant") if item.get("enchant") is not None else (
            item.get("enchantLevel") if item.get("enchantLevel") is not None else item.get("enhanceLevel")
        )
        stats = item.get("stats") or item.get("options") or item.get("attributes") or item.get("bonusStats") or []
        passives = item.get("passives") or item.get("passiveSkills") or item.get("passiveEffects") or item.get("passive") or []
        actives = item.get("actives") or item.get("activeSkills") or item.get("activeEffects") or item.get("active") or []

        normalized.append({
            "id": str(item.get("id") or item.get("itemId") or idx),
            "name": str(name),
            "slot": str(slot),
            "icon": icon,
            "anim": anim,
            "rarity": rarity,
            "enchant": enchant,
            "stats": stats,
            "passives": passives,
            "actives": actives,
        })
    return normalized


def normalize_player(raw_data, name, server):
    if not isinstance(raw_data, dict):
        return None
    p = raw_data.get("player") if isinstance(raw_data.get("player"), dict) else raw_data
    if not isinstance(p, dict):
        return None

    cp = p.get("combatPower") or p.get("combat_power") or p.get("cp") or 0
    il = p.get("itemLevel") or p.get("item_level") or p.get("gearScore") or 0
    lv = p.get("level") or p.get("lv") or 45
    cls = p.get("className") or p.get("class") or p.get("job") or "Daeva"
    real_name = p.get("name") or name
    stats = p.get("stats") if isinstance(p.get("stats"), dict) else {}

    raw_daev = p.get("daevanion") or p.get("daevanionBoards") or p.get("boards") or []
    daev_list = []
    if isinstance(raw_daev, list):
        for item in raw_daev:
            if isinstance(item, dict):
                daev_list.append({
                    "name": item.get("name") or item.get("boardName") or "Board",
                    "unlocked": int(item.get("unlocked") or item.get("current") or 0),
                    "total": int(item.get("total") or item.get("max") or 88),
                })
    elif isinstance(raw_daev, dict):
        for k, v in raw_daev.items():
            if isinstance(v, dict):
                daev_list.append({
                    "name": str(k),
                    "unlocked": int(v.get("unlocked") or v.get("current") or 0),
                    "total": int(v.get("total") or v.get("max") or 88),
                })

    equipment = normalize_equipment(raw_data)

    return {
        "player": {
            "name": str(real_name),
            "server": server.capitalize(),
            "level": int(lv),
            "className": str(cls),
            "combatPower": int(float(cp)),
            "itemLevel": int(float(il)),
            "stats": stats,
            "daevanion": daev_list,
            "equipment": equipment,
            "raw": p,
        }
    }


def scrape_siel_page_data(srv_clean, name_clean):
    page_url = f"{SIEL_ORIGIN}/eu/{srv_clean}/{name_clean}"
    try:
        resp = cffi_requests.get(page_url, impersonate="chrome", timeout=12)
        if resp.status_code != 200:
            return None
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, flags=re.S)
        if match:
            return json.loads(match.group(1))
    except Exception:
        pass
    return None


def fetch_player(name, server):
    srv_clean = re.sub(r"[^a-zA-Z0-9]", "", server).lower() or "nemon"
    name_clean = re.sub(r"[^a-zA-Z0-9_-]", "", name).strip()
    if not name_clean:
        return None, "Invalid player name"

    key = f"{srv_clean}:{name_clean.lower()}"
    srv_id = SERVER_IDS.get(srv_clean, srv_clean if srv_clean.isdigit() else "2309")

    urls_to_try = [
        f"{SIEL_API_BASE}/{srv_id}/{name_clean}",
        f"{SIEL_API_BASE}/{srv_clean}/{name_clean}",
    ]

    for url in urls_to_try:
        try:
            resp = cffi_requests.get(
                url,
                impersonate="chrome",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": f"{SIEL_ORIGIN}/eu/{srv_clean}/{name_clean}",
                },
                timeout=12,
            )
            if resp.status_code == 200:
                norm = normalize_player(resp.json(), name_clean, srv_clean)
                if norm and (norm["player"]["combatPower"] > 0 or norm["player"]["itemLevel"] > 0):
                    if not norm["player"]["equipment"]:
                        page_json = scrape_siel_page_data(srv_clean, name_clean)
                        if page_json:
                            norm["player"]["equipment"] = normalize_equipment(page_json)
                    CHAR_STORE[key] = norm
                    return norm, None
            elif resp.status_code == 404:
                return None, f"Player '{name_clean}' not found on {srv_clean.capitalize()}"
        except Exception:
            continue

    if key in CHAR_STORE:
        return CHAR_STORE[key], None

    return None, f"Siel.tools rate-limited or '{name_clean}' unavailable on {srv_clean.capitalize()}"


def scrape_board(url, board_type):
    found = []
    try:
        resp = cffi_requests.get(url, impersonate="chrome", headers={"Accept-Language": "en-US,en;q=0.9"}, timeout=15)
        pattern = rf'<a[^>]+href="(/en-us/board/{board_type}/view\?articleId=[^"]+)"[^>]*>(.*?)</a>'
        for href, raw_title in re.findall(pattern, resp.text, flags=re.I | re.S):
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw_title)).strip()
            if len(title) > 4:
                found.append({"title": title, "url": f"https://aion2.plaync.com{href}", "source": "NCSOFT Official"})
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
        items = [{"title": "AION 2 Official Patch Notes & Updates", "url": UPDATE_LIST_URL, "source": "NCSOFT Official"}]
    NEWS_CACHE["ts"] = now
    NEWS_CACHE["data"] = items
    return items


class HubHandler(BaseHTTPRequestHandler):
    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path in ("/", "/health"):
            return self._send_json(200, {"status": "AION DAEVA HUB Backend Running", "version": "0.0.11", "cached": len(CHAR_STORE)})

        if parsed.path == "/player":
            name = (qs.get("name") or [""])[0]
            server = (qs.get("server") or ["Nemon"])[0]
            data, err = fetch_player(name, server)
            if data:
                return self._send_json(200, data)
            return self._send_json(404, {"error": err or "Player not found"})

        if parsed.path == "/news":
            return self._send_json(200, {"items": fetch_official_news()})

        return self._send_json(404, {"error": "Not found"})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HubHandler)
    print(f"AION DAEVA HUB Backend v0.0.11 listening on port {PORT}")
    server.serve_forever()
