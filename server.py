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
    "mythic": "Mythic", "ultimate": "Ultimate", "eternal": "Eternal",
    "legend": "Legendary", "unique": "Unique", "fabled": "Fabled",
    "heroic": "Heroic", "rare": "Rare", "special": "Special",
}

CHAR_STORE = {}
NEWS_CACHE = {"ts": 0.0, "data": None}


def clean_text(raw_html):
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_spans(block_html, cls_name):
    m = re.search(rf'<div[^>]+class="[^"]*\b{cls_name}\b[^"]*"[^>]*>(.*?)</div>', block_html, flags=re.I | re.S)
    if not m:
        return []
    inner = m.group(1)
    spans = re.findall(r"<span[^>]*>(.*?)</span>", inner, flags=re.I | re.S)
    if not spans:
        txt = clean_text(inner)
        return [txt] if txt else []
    out = []
    for sp in spans:
        txt = clean_text(sp)
        if txt:
            out.append(txt)
    return out


def parse_it_cards(gear_html):
    """Parses all <div class="it">...</div> blocks from Siel.tools /gear page."""
    cards = []
    # Split cleanly at each <div class="it"> card boundary
    chunks = re.split(r'<div\s+class="it(?:\s+[^"]*)?">', gear_html, flags=re.I)
    for chunk in chunks[1:]:
        # Bound chunk before next major section
        card_html = re.split(r'</section>|</article>|<div\s+class="(?:doll|win|gear-sec)', chunk, maxsplit=1)[0]

        name_m = re.search(r'<span[^>]+class="[^"]*\bit-name\b([^"]*)"[^>]*>(.*?)</span>', card_html, flags=re.I | re.S)
        if not name_m:
            continue
        cls_attr = name_m.group(1).lower()
        name = clean_text(name_m.group(2))

        rarity = "Unique"
        for k, v in GRADE_MAP.items():
            if k in cls_attr:
                rarity = v
                break

        ench_m = re.search(r'<span[^>]+class="[^"]*\bench\b[^"]*"[^>]*>\s*\+?(\d+)', card_html, flags=re.I | re.S)
        enchant = int(ench_m.group(1)) if ench_m else None

        exceed_m = re.search(r'<span[^>]+class="[^"]*\bexceed\b[^"]*"[^>]*>(.*?)</span>', card_html, flags=re.I | re.S)
        exceed = clean_text(exceed_m.group(1)) if exceed_m else ""

        meta_m = re.search(r'<div[^>]+class="[^"]*\bit-meta\b[^"]*"[^>]*>(.*?)</div>', card_html, flags=re.I | re.S)
        meta = clean_text(meta_m.group(1)) if meta_m else ""

        icon_m = re.search(r'<img[^>]+src="(https://assets\.playnccdn\.com/static-aion2-gamedata/resources/(?:Icon_|UT_)[^"]+)"', card_html, flags=re.I)
        icon = icon_m.group(1) if icon_m else ""

        # Main stats (it-main)
        main_stats = extract_spans(card_html, "it-main")
        if exceed:
            main_stats.insert(0, exceed)
        if meta:
            main_stats.insert(0, meta)

        # Sub stats + Magic Stones (it-sub + it-stones -> Passives)
        passives = extract_spans(card_html, "it-sub")
        stones_m = re.search(r'<div[^>]+class="[^"]*\bit-stones\b[^"]*"[^>]*>(.*?)</div>', card_html, flags=re.I | re.S)
        if stones_m:
            for st_tag, st_inner in re.findall(r'<span([^>]*)>(.*?)</span>', stones_m.group(1), flags=re.I | re.S):
                title_m = re.search(r'title="([^"]+)"', st_tag, flags=re.I)
                stone_type = html_lib.unescape(title_m.group(1)) if title_m else "Manastone"
                stone_val = clean_text(st_inner)
                if stone_val:
                    passives.append(f"[{stone_type}] {stone_val}")

        # Skills (it-skills -> Actives)
        actives = []
        skills_m = re.search(r'<div[^>]+class="[^"]*\bit-skills\b[^"]*"[^>]*>(.*?)</div>', card_html, flags=re.I | re.S)
        if skills_m:
            for sk_inner in re.findall(r'<span[^>]+class="[^"]*\bsk\b[^"]*"[^>]*>(.*?)</span>', skills_m.group(1), flags=re.I | re.S):
                sk_txt = clean_text(sk_inner)
                if sk_txt:
                    actives.append(sk_txt)

        cards.append({
            "name": name,
            "slot": meta.split("·")[0].strip() if "·" in meta else (meta or "Equipment"),
            "icon": icon,
            "rarity": rarity,
            "enchant": enchant,
            "stats": main_stats,
            "passives": passives,
            "actives": actives,
        })
    return cards


def scrape_siel_gear_page(srv_clean, name_clean):
    """Combines overview slot icons/order with detailed <div class="it"> cards from /gear."""
    overview_items = []
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
                for g_key, g_name in GRADE_MAP.items():
                    if g_key in cls_str.lower():
                        grade = g_name
                        break
                clean_title = re.sub(r"\s*\+\d+\s*$", "", html_lib.unescape(title_attr)).strip()
                overview_items.append({
                    "id": slot_id,
                    "slot": SLOT_NAMES.get(slot_id, f"Slot {slot_id}"),
                    "name": clean_title or SLOT_NAMES.get(slot_id, f"Item {slot_id}"),
                    "icon": img_m.group(1) if img_m else "",
                    "rarity": grade,
                    "enchant": int(enc_m.group(1)) if enc_m else None,
                    "stats": [],
                    "passives": [],
                    "actives": [],
                })
    except Exception:
        pass

    gear_cards = []
    gear_url = f"{SIEL_ORIGIN}/eu/{srv_clean}/{name_clean}/gear"
    try:
        g_resp = cffi_requests.get(gear_url, impersonate="chrome", timeout=14)
        if g_resp.status_code == 200:
            gear_cards = parse_it_cards(g_resp.text)
    except Exception:
        pass

    if not overview_items:
        for idx, c in enumerate(gear_cards, start=1):
            c["id"] = str(idx)
        return gear_cards

    # Merge parsed <div class="it"> details into overview items by matching name & enchant
    used_cards = set()
    for ov in overview_items:
        best_idx = None
        for idx, gc in enumerate(gear_cards):
            if idx in used_cards:
                continue
            if gc["name"].lower() == ov["name"].lower():
                if ov["enchant"] is None or gc["enchant"] == ov["enchant"]:
                    best_idx = idx
                    break
                if best_idx is None:
                    best_idx = idx
        if best_idx is not None:
            used_cards.add(best_idx)
            gc = gear_cards[best_idx]
            ov["stats"] = gc["stats"]
            ov["passives"] = gc["passives"]
            ov["actives"] = gc["actives"]
            if not ov["icon"] and gc["icon"]:
                ov["icon"] = gc["icon"]
            if ov["enchant"] is None:
                ov["enchant"] = gc["enchant"]

    # Append any extra items from /gear not listed in overview
    for idx, gc in enumerate(gear_cards):
        if idx not in used_cards:
            gc["id"] = str(100 + idx)
            overview_items.append(gc)

    return overview_items


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
            return self._send_json(200, {"status": "AION DAEVA HUB Backend Running", "version": "0.0.13", "cached": len(CHAR_STORE)})

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
    print(f"AION DAEVA HUB Backend v0.0.13 listening on port {PORT}")
    server.serve_forever()
