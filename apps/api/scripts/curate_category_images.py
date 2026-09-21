"""Build `data/media/category_images.json`: one open-licence Wikimedia Commons image per category.

    uv run python scripts/curate_category_images.py --contact https://naegajjanday.com/contact

`--contact` (a URL or e-mail of the service operator) is REQUIRED. Wikimedia's robot policy only
allows server-side API clients that identify themselves with contact details in the User-Agent;
anonymous scripts get HTTP 403. Do not work around that — pass a real contact.

The script is slow on purpose (one request every 2 s, ~50 requests in total) and writes
`category_images.review.html` next to the JSON: open it, check that each pick really shows the
category, and edit the JSON by hand where it does not (candidates 2 and 3 are listed for that).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

API = "https://commons.wikimedia.org/w/api.php"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "media"
OPEN_LICENSE = re.compile(r"^(cc0|cc by(-sa)? \d|public domain|pd)", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")

# category code -> Commons search phrase. Parent codes double as the fallback for unlisted children.
QUERIES: dict[str, str] = {
    "food": "Korean cuisine banchan table",
    "food.korean": "bibimbap",
    "food.noodle": "kalguksu",
    "food.japanese": "sushi platter",
    "food.chinese": "jajangmyeon",
    "food.western": "pasta dish restaurant",
    "food.asian": "pho noodle soup",
    "food.bbq": "samgyeopsal",
    "food.snack": "tteokbokki",
    "food.brunch": "brunch plate",
    "cafe": "cafe interior Seoul",
    "cafe.coffee": "latte art cup",
    "cafe.roastery": "coffee roaster",
    "cafe.view": "rooftop cafe",
    "cafe.book": "book cafe interior",
    "cafe.tea": "Korean traditional tea",
    "dessert": "cake slice dessert",
    "dessert.bakery": "bakery bread display",
    "dessert.icecream": "gelato display",
    "dessert.bingsu": "patbingsu",
    "attraction": "Seoul street",
    "attraction.park": "Seoul Forest",
    "attraction.street": "Ikseon-dong",
    "attraction.market": "Gwangjang Market",
    "attraction.landmark": "Gwanghwamun Plaza",
    "activity": "indoor climbing gym",
    "activity.arcade": "video arcade machines",
    "activity.boardgame": "board game cafe",
    "activity.craft": "pottery wheel workshop",
    "activity.escape": "escape room",
    "activity.sports": "bowling alley lanes",
    "activity.photo": "photo booth",
    "activity.karaoke": "noraebang",
    "culture": "museum exhibition hall",
    "culture.museum": "National Museum of Korea interior",
    "culture.gallery": "art gallery interior",
    "culture.exhibition": "art exhibition visitors",
    "culture.festival": "Seoul Lantern Festival",
    "culture.cinema": "movie theater interior seats",
    "culture.bookstore": "independent bookstore interior",
    "bar": "bar counter bottles",
    "bar.pub": "craft beer glasses",
    "bar.wine": "wine glasses bar",
    "bar.cocktail": "cocktail bar",
    "bar.izakaya": "izakaya",
    "bar.pocha": "pojangmacha",
    "bar.makgeolli": "makgeolli",
    "nightview": "Seoul night view",
    "nightview.observatory": "N Seoul Tower night",
    "nightview.riverside": "Han River night Seoul",
    "nightview.rooftop": "rooftop bar night",
}


def clean(text: str, limit: int = 80) -> str:
    return html.unescape(TAG.sub("", text or "")).strip()[:limit]


def candidates(body: dict[str, Any], limit: int = 3) -> list[dict[str, str]]:
    pages = sorted((body.get("query", {}).get("pages") or {}).values(), key=lambda p: p.get("index", 99))
    picks: list[dict[str, str]] = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licence = clean(meta.get("LicenseShortName", {}).get("value", ""))
        width, height = info.get("width", 0), info.get("height", 0)
        if info.get("mime") != "image/jpeg" or width < 1000 or not OPEN_LICENSE.match(licence):
            continue
        if width < height * 1.1:  # cards are landscape
            continue
        picks.append(
            {
                "url": info["thumburl"],
                "page_url": info["descriptionurl"],
                "title": clean(str(page["title"]).removeprefix("File:").rsplit(".", 1)[0], 60),
                "author": clean(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons",
                "license": licence,
            }
        )
        if len(picks) == limit:
            break
    return picks


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--contact", required=True, help="operator URL or e-mail, sent in the User-Agent")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chosen: dict[str, dict[str, str]] = {}
    review: list[str] = []
    headers = {"User-Agent": f"naegajjanday-curation/1.0 ({args.contact}) httpx"}
    with httpx.Client(timeout=30, headers=headers) as client:
        for code, query in QUERIES.items():
            res = client.get(
                API,
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": f"{query} filetype:bitmap",
                    "gsrnamespace": 6,
                    "gsrlimit": 12,
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata",
                    "iiurlwidth": 640,
                },
            )
            if res.status_code != 200:
                # 403 = robot policy. Stop instead of retrying: hammering a refusal makes it worse.
                raise SystemExit(f"Commons answered {res.status_code} for '{code}': {res.text[:200]}")
            picks = candidates(res.json())
            if picks:
                chosen[code] = picks[0]
            cells = "".join(
                f'<figure><img src="{p["url"]}" width="220"><figcaption>{i + 1}. {html.escape(p["title"])}'
                f"<br>{html.escape(p['author'])} · {p['license']}</figcaption></figure>"
                for i, p in enumerate(picks)
            )
            review.append(
                f"<h3>{code} — {html.escape(query)}</h3><div class=row>{cells or 'no result'}</div>"
            )
            print(f"{code}: {len(picks)} candidate(s)", flush=True)
            time.sleep(2.0)

    (OUT_DIR / "category_images.json").write_text(
        json.dumps(chosen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    style = "<style>body{font:14px sans-serif}.row{display:flex;gap:12px}figure{margin:0;width:220px}</style>"
    (OUT_DIR / "category_images.review.html").write_text(
        f"<meta charset=utf-8>{style}" + "".join(review), encoding="utf-8"
    )
    print(f"wrote {len(chosen)} images -> {OUT_DIR}")


if __name__ == "__main__":
    main()
