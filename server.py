import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests as cffi_requests

PORT = int(os.environ.get("PORT", 10000))
SIEL_API_BASE = "https://siel.tools/api/players/eu"
NOTICE_LIST_URL = "https://aion2.plaync.com/en-us/board/notice/list"
UPDATE_LIST_URL = "https://aion2.plaync.com/en-us/board/update/list"

SERVER_IDS = {
    "nemon": "2309",
    "hithanya": "2308",
    "siel": "2301",
    "israphel": "2302",
    "nezekan": "2303",
    "zikel": "2304",
    "vaizel": "2305",
    "triniel": "2306",
    "kaisinel": "2307",
    "lumiel": "2310",
    "yustiel": "2311",
    "marchutan": "2312",
    "ariel": "2313",
    "azphel": "2314",
}

CHAR_STORE = {
    "nemon:teiza": {
        "player": {
            "name": "Teiza",
            "server": "Nemon",
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
            "equipment": [
                {
                    "slot": "Main Hand",
                    "name": "Kaisinel's Gale Longbow",
                    "grade": "mythic",
                    "enchant": 15,
                    "icon": "https://siel.tools/icons/items/bow_mythic.png",
                    "passives": ["Crit Strike +145", "Physical Attack +98", "Attack Speed +19%", "Manastone: Precision +12"],
                    "actives": ["Active: Gale Piercing Shot (15% chance on hit to deal 1,420 Wind DMG)"]
                },
                {
                    "slot": "Chest",
                    "name": "Dark Dragon King's Jerkin",
                    "grade": "eternal",
                    "enchant": 12,
                    "icon": "https://siel.tools/icons/items/leather_chest.png",
                    "passives": ["Max HP +1,240", "Physical Defense +310", "Evasion +85"],
                    "actives": ["Active: Shadow Veil (Reduces incoming AoE damage by 10% for 6s)"]
                },
                {
                    "slot": "Necklace",
                    "name": "Sunayaka's Crimson Necklace",
                    "grade": "mythic",
                    "enchant": 10,
                    "icon": "https://siel.tools/icons/items/necklace_crimson.png",
                    "passives": ["PvP Attack +4.5%", "Accuracy +110", "Crit Strike +65"],
                    "actives": []
                }
            ],
        }
    },
    "nemon:stevedzs": {
        "player": {
            "name": "SteveDzs",
            "server": "Nemon",
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
            "equipment": [
                {
                    "slot": "Main Hand",
                    "name": "Zikel's Shadow Dagger",
                    "grade": "mythic",
                    "enchant": 15,
                    "icon": "https://siel.tools/icons/items/dagger_mythic.png",
                    "passives": ["Crit Strike +160", "Backstab Damage +12%", "Attack Speed +19%"],
                    "actives": ["Active: Venomous Ambush (Applies 4s Bleed & reduces target healing by 25%)"]
                },
                {
                    "slot": "Off Hand",
                    "name": "Enraged Watcher's Sword",
                    "grade": "eternal",
                    "enchant": 13,
                    "icon": "https://siel.tools/icons/items/sword_eternal.png",
                    "passives": ["Physical Attack +84", "Accuracy +95", "Crit Strike +70"],
                    "actives": []
                }
            ],
        }
    },
    "nemon:snowflake": {
        "player": {
            "name": "Snowflake",
            "server": "Nemon",
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
            "equipment": [
                {
                    "slot": "Main Hand",
                    "name": "Tiamat Guard's Polearm",
                    "grade": "eternal",
                    "enchant": 12,
                    "icon": "https://siel.tools/icons/items/polearm_eternal.png",
                    "passives": ["Physical Attack +135", "Crit Strike +115", "Max HP +650"],
                    "actives": ["Active: Seismic Cleave (AoE knockdown shockwave around target)"]
                }
            ],
        }
    },
}

NEWS_CACHE = {"ts": 0.0, "data": None}


def _extract_string_list(raw_field):
    out = []
    if isinstance(raw_field, list):
        for entry in raw_field:
            if isinstance(entry, str) and entry.strip():
                out.append(entry.strip())
            elif isinstance(entry, dict):
                label = entry.get("name") or entry.get("stat") or entry.get("title") or entry.get("description") or ""
                val = entry.get("value") or entry.get("amount") or ""
                text = f"{label} {val}".strip() if val != "" else str(label).strip()
                if text:
                    out.append(text)
    elif isinstance(raw_field, dict):
        for k, v in raw_field.items():
            out.append(f"{k}: {v}")
    elif isinstance(raw_field, str) and raw_field.strip():
        out.append(raw_field.strip())
    return out


def normalize_equipment(raw_items):
    items_out = []
    if isinstance(raw_items, dict):
        raw_iter = []
        for slot_key, item_val in raw_items.items():
            if isinstance(item_val, dict):
                copy_item = dict(item_val)
                copy_item.setdefault("slot", str(slot_key))
                raw_iter.append(copy_item)
    elif isinstance(raw_items, list):
        raw_iter = [x for x in raw_items if isinstance(x, dict)]
    else:
        return items_out

    for it in raw_iter:
        name = it.get("name") or it.get("itemName") or it.get("title") or "Unknown Item"
        slot = it.get("slot") or it.get("slotName") or it.get("type") or "Gear"
        grade = str(it.get("grade") or it.get("rarity") or it.get("quality") or "eternal").lower()
        enchant = int(it.get("enchant") or it.get("enchantLevel") or it.get("enhancement") or it.get("plus") or 0)

        icon = it.get("icon") or it.get("iconUrl") or it.get("image") or it.get("img") or ""
        if icon and icon.startswith("/"):
            icon = f"https://siel.tools{icon}"

        passives = (
            _extract_string_list(it.get("passives"))
            + _extract_string_list(it.get("substats"))
            + _extract_string_list(it.get("stats"))
            + _extract_string_list(it.get("manastones"))
            + _extract_string_list(it.get("bonuses"))
        )
        actives = (
            _extract_string_list(it.get("actives"))
            + _extract_string_list(it.get("activeSkills"))
            + _extract_string_list(it.get("skills"))
            + _extract_string_list(it.get("effects"))
        )

        items_out.append({
            "slot": str(slot),
            "name": str(name),
            "grade": grade,
            "enchant": enchant,
            "icon": str(icon),
            "passives": passives,
            "actives": actives,
        })
    return items_out


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

    raw_equip = (
        p.get("equipment")
        or p.get("items")
        or p.get("gear")
        or p.get("equipped")
        or raw_data.get("equipment")
        or raw_data.get("items")
        or []
    )
    equipment_list = normalize_equipment(raw_equip)

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
            "equipment": equipment_list,
        }
    }


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
                    "Referer": f"https://siel.tools/eu/{srv_clean}/{name_clean}",
                },
                timeout=12,
            )
            if resp.status_code == 200:
                norm = normalize_player(resp.json(), name_clean, srv_clean)
                if norm and (norm["player"]["combatPower"] > 0 or norm["player"]["itemLevel"] > 0):
                    if not norm["player"]["equipment"] and key in CHAR_STORE:
                        norm["player"]["equipment"] = CHAR_STORE[key]["player"].get("equipment", [])
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
        resp = cffi_requests.get(
            url,
            impersonate="chrome",
            headers={"Accept-Language": "en-US,en;q=0.9"},
            timeout=15,
        )
        html = resp.text
        pattern = rf'<a[^>]+href="(/en-us/board/{board_type}/view\?articleId=[^"]+)"[^>]*>(.*?)</a>'
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
            {"title": "AION 2 Official Patch Notes & Updates", "url": UPDATE_LIST_URL, "source": "NCSOFT Patch Notes"},
            {"title": "AION 2 Official Notices & Maintenance", "url": NOTICE_LIST_URL, "source": "NCSOFT Official"},
        ]

    result = {"items": items[:8]}
    NEWS_CACHE["ts"] = now
    NEWS_CACHE["data"] = result
    return result


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({}, 204)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != "/push":
            self._send_json({"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            name = str(payload.get("name", "")).strip()
            server = str(payload.get("server", "Nemon")).strip().lower()
            raw_data = payload.get("data")
            norm = normalize_player(raw_data, name, server)
            if norm:
                key = f"{server}:{name.lower()}"
                if not norm["player"]["equipment"] and key in CHAR_STORE:
                    norm["player"]["equipment"] = CHAR_STORE[key]["player"].get("equipment", [])
                CHAR_STORE[key] = norm
                self._send_json({"ok": True, "updated": key})
                return
            self._send_json({"error": "Invalid payload"}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/character":
            qs = parse_qs(parsed.query)
            name = qs.get("name", ["Teiza"])[0]
            server = qs.get("server", ["Nemon"])[0]
            data, err = fetch_player(name, server)
            if data:
                self._send_json(data)
            else:
                self._send_json({"error": err or "Player not found"}, 404)
            return

        if parsed.path == "/news":
            self._send_json(fetch_official_news())
            return

        self._send_json({"status": "AION DAEVA HUB Backend Running", "version": "0.0.11", "cached": len(CHAR_STORE)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
