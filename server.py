import html as html_lib
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
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

SLOT_NAMES = {
    "1": "Main Hand", "2": "Off Hand", "3": "Helmet", "4": "Pauldrons",
    "5": "Breastplate", "6": "Greaves", "7": "Gloves", "8": "Boots",
    "10": "Necklace", "11": "Earring L", "12": "Earring R",
    "13": "Ring L", "14": "Ring R", "15": "Bracelet L", "16": "Bracelet R",
    "17": "Belt", "19": "Cloak", "22": "Amulet", "23": "Rune L", "24": "Rune R",
    "41": "Arcana I", "42": "Arcana II", "43": "Arcana III", "44": "Arcana IV", "45": "Arcana V",
}

GRADE_MAP = {
    "g-mythic": "Mythic", "g-ultimate": "Ultimate", "g-eternal": "Eternal",
    "g-legend": "Legendary", "g-unique": "Unique", "g-fabled": "Fabled",
    "g-heroic": "Heroic", "g-rare": "Rare", "g-special": "Special",
}

CHAR_STORE = {}
NEWS_CACHE = {"ts": 0.0, "data": None}


def strip_tags(raw_html):
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def scrape_siel_gear_page(srv_clean, name_clean):
    items_by_slot = {}
    ordered_slots = []

    ov_url = f"{SIEL_ORIGIN}/eu/{srv_clean}/{name_clean}"
    try:
        ov_resp = cffi_requests.get(ov_url, impersonate="chrome", timeout=12)
        if ov_resp.status_code == 200:
            slot_links = re.findall(
                r'<a[^>]+class="slot\s+([^"]*)"[^>]+title="([^"]*)"[^>]+href="[^"]*#slot-(\d+)"[^>]*>(.*?)</a>',
                ov_resp.text,
                flags=re.I | re.S,
            )
            for cls_str, title_attr, slot_id, inner in slot_links:
                img_m = re.search(r'<img[^>]+src="([^"]+)"', inner, flags=re.I)
                enc_m = re.search(r'<b>\s*\+?(\d+)\s*</b>', inner, flags=re.I)
                grade = "Unique"
                for g_cls, g_name in GRADE_MAP.items():
                    if g_cls in cls_str:
                        grade = g_name
                        break
                clean_title = re.sub(r"\s*\+\d+\s*$", "", html_lib.unescape(title_attr)).strip()
                entry = {
                    "id": slot_id,
                    "slot": SLOT_NAMES.get(slot_id, f"Slot {slot_id}"),
                    "name": clean_title or SLOT_NAMES.get(slot_id, f"Item {slot_id}"),
                    "icon": img_m.group(1) if img_m else "",
                    "rarity": grade,
                    "enchant": int(enc_m.group(1)) if enc_m else None,
                    "stats": [],
                    "passives": [],
                    "actives": [],
                }
                items_by_slot[slot_id] = entry
                if slot_id not in ordered_slots:
                    ordered_slots.append(slot_id)
    except Exception:
        pass

    gear_url = f"{SIEL_ORIGIN}/eu/{srv_clean}/{name_clean}/gear"
    try:
        g_resp = cffi_requests.get(gear_url, impersonate="chrome", timeout=14)
        if g_resp.status_code == 200:
            parts = re.split(r'id="slot-(\d+)"', g_resp.text, flags=re.I)
            for i in range(1, len(parts) - 1, 2):
                slot_id = parts[i]
                block = parts[i + 1][:6500]
                entry = items_by_slot.get(slot_id)
                if not entry:
                    img_m = re.search(r'<img[^>]+src="(https://assets\.playnccdn\.com/[^"]+)"', block, flags=re.I)
                    entry = {
                        "id": slot_id,
                        "slot": SLOT_NAMES.get(slot_id, f"Slot {slot_id}"),
                        "name": SLOT_NAMES.get(slot_id, f"Item {slot_id}"),
                        "icon": img_m.group(1) if img_m else "",
                        "rarity": "Unique",
                        "enchant": None,
                        "stats": [],
                        "passives": [],
                        "actives": [],
                    }
                    items_by_slot[slot_id] = entry
                    ordered_slots.append(slot_id)

                block = re.split(r'</article>|</section>|<div class="gear-card', block, maxsplit=1)[0]
                lines = strip_tags(block)

                stats, passives, actives = [], [], []
                mode = "stats"
                for ln in lines:
                    low = ln.lower()
                    if ln == entry["name"] or low in ("details", "gear", "overview"):
                        continue
                    if re.match(r"^\+\d+$", ln):
                        if entry["enchant"] is None:
                            entry["enchant"] = int(ln[1:])
                        continue
                    if any(k in low for k in ("passive", "set effect", "soul imprint", "manastone", "godstone")):
                        mode = "passives"
                        passives.append(ln)
                        continue
                    if any(k in low for k in ("active", "use:", "skill:", "cooldown", "cast time")):
                        mode = "actives"
                        actives.append(ln)
                        continue
                    if 2 < len(ln) < 140:
                        if mode == "passives":
                            passives.append(ln)
                        elif mode == "actives":
                            actives.append(ln)
                        else:
                            stats.append(ln)

                if stats:
                    entry["stats"] = stats[:14]
                if passives:
                    entry["passives"] = passives[:10]
                if actives:
                    entry["actives"] = actives[:8]
    except Exception:
        pass

    return [items_by_slot[sid] for sid in ordered_slots if sid in items_by_slot]


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
            "equipment": [],
            "raw": p,
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
                    "Referer": f"{SIEL_ORIGIN}/eu/{srv_clean}/{name_clean}",
                },
                timeout=12,
            )
            if resp.status_code == 200:
                norm = normalize_player(resp.json(), name_clean, srv_clean)
                if norm and (norm["player"]["combatPower"] > 0 or norm["player"]["itemLevel"] > 0):
                    norm["player"]["equipment"] = scrape_siel_gear_page(srv_clean, name_clean)
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
            return self._send_json(200, {"status": "AION DAEVA HUB Backend Running", "version": "0.0.12", "cached": len(CHAR_STORE)})

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
    print(f"AION DAEVA HUB Backend v0.0.12 listening on port {PORT}")
    server.serve_forever()
