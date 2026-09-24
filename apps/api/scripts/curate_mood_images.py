"""Mood pictures per category from free image APIs — candidates for a human to pick (docs/43).

    # 1) gather candidates (Openverse needs no key; Pexels / Unsplash are used only when their key is set)
    uv run python scripts/curate_mood_images.py search [--only food.korean --only cafe] [--per 4]
    #    → data/media/mood_candidates.json + mood_candidates.review.html (open it and look at every picture)

    # 2) write the ones a person chose into category_images.json
    uv run python scripts/curate_mood_images.py apply --pick food.korean=pexels:<id> --pick cafe=openverse:<n>

Keys: PEXELS_API_KEY, UNSPLASH_ACCESS_KEY (environment or apps/api/.env). All three are free tiers.

Rules (why this is a script and not a runtime call):
- Nothing is picked automatically. A search result for "bibimbap" can be a photo of one named restaurant
  with its sign — that must not stand in for another business. Reject any picture with a shop sign, a
  logo, a readable menu board or recognisable people.
- Only licences that allow commercial use AND modification (we crop and tint the pictures).
  Openverse is queried with `license_type=commercial,modification`; ND / NC licences are dropped again here.
- Pictures are hotlinked from the provider (Unsplash requires it) and never presented as the place itself:
  the web labels them "분위기 이미지" with the credit line stored here.
- Unsplash asks apps to call the photo's `download_location` when a photo is put to use: `apply` does it once.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from curate_category_images import QUERIES

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "media"
CANDIDATES = OUT_DIR / "mood_candidates.json"
TARGET = OUT_DIR / "category_images.json"
UA = "naegajjanday-curation/1.0 (category mood pictures; human-reviewed)"
UTM = "utm_source=naegajjanday&utm_medium=referral"
NOT_ALLOWED = re.compile(r"\b(nc|nd)\b|non-?commercial|no-?deriv", re.IGNORECASE)

SOURCE_NAMES = {"openverse": "Openverse", "pexels": "Pexels", "unsplash": "Unsplash"}


def credit(author: str | None, license_name: str, source: str) -> str:
    parts = ["분위기 이미지"]
    if author:
        parts.append(f"© {author}")
    parts += [license_name, SOURCE_NAMES.get(source, source)]
    return " · ".join(parts)


# ── one parser per provider: API item → candidate (pure, tested) ──────────────────────────


def from_openverse(item: dict[str, Any]) -> dict[str, Any] | None:
    lic = f"CC {str(item.get('license') or '').upper()} {item.get('license_version') or ''}".strip()
    if item.get("license") in {"cc0", "pdm"}:
        lic = "CC0" if item["license"] == "cc0" else "Public Domain"
    if NOT_ALLOWED.search(lic) or not item.get("url"):
        return None
    author = item.get("creator") or None
    return {
        "id": f"openverse:{item['id']}",
        "source": "openverse",
        "url": item["url"],
        "thumbnail_url": item.get("thumbnail") or item["url"],
        "page_url": item.get("foreign_landing_url") or f"https://openverse.org/image/{item['id']}",
        "title": item.get("title") or "",
        "author": author or "알 수 없음",
        "license": lic,
        "attribution_text": credit(author, lic, "openverse"),
        "via": item.get("source"),  # the original host (flickr, wikimedia …)
    }


def from_pexels(item: dict[str, Any]) -> dict[str, Any] | None:
    src = item.get("src") or {}
    if not src.get("large"):
        return None
    return {
        "id": f"pexels:{item['id']}",
        "source": "pexels",
        "url": src["large"],
        "thumbnail_url": src.get("medium") or src["large"],
        "page_url": item.get("url"),
        "title": item.get("alt") or "",
        "author": item.get("photographer") or "Pexels",
        "license": "Pexels License",
        "attribution_text": credit(item.get("photographer"), "Pexels License", "pexels"),
    }


def from_unsplash(item: dict[str, Any]) -> dict[str, Any] | None:
    urls = item.get("urls") or {}
    user = item.get("user") or {}
    if not urls.get("regular"):
        return None
    page = (item.get("links") or {}).get("html")
    return {
        "id": f"unsplash:{item['id']}",
        "source": "unsplash",
        "url": urls["regular"],
        "thumbnail_url": urls.get("small") or urls["regular"],
        "page_url": f"{page}?{UTM}" if page else None,
        "title": item.get("alt_description") or "",
        "author": user.get("name") or "Unsplash",
        "license": "Unsplash License",
        "attribution_text": credit(user.get("name"), "Unsplash License", "unsplash"),
        "download_location": (item.get("links") or {}).get("download_location"),
    }


# ── search ──────────────────────────────────────────────────────────────────────────────


def _env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text("utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"') or None
    return None


def search(client: httpx.Client, query: str, per: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    r = client.get(
        "https://api.openverse.org/v1/images/",
        params={"q": query, "license_type": "commercial,modification", "page_size": per, "mature": "false"},
    )
    if r.status_code == 200:
        found += [c for c in map(from_openverse, r.json().get("results", [])) if c]
    else:
        print(f"  openverse {r.status_code}", file=sys.stderr)

    if key := _env("PEXELS_API_KEY"):
        r = client.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": per},
            headers={"Authorization": key},
        )
        if r.status_code == 200:
            found += [c for c in map(from_pexels, r.json().get("photos", [])) if c]
        else:
            print(f"  pexels {r.status_code}", file=sys.stderr)

    if key := _env("UNSPLASH_ACCESS_KEY"):
        r = client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": per, "content_filter": "high"},
            headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
        )
        if r.status_code == 200:
            found += [c for c in map(from_unsplash, r.json().get("results", [])) if c]
        else:
            print(f"  unsplash {r.status_code}", file=sys.stderr)
    return found


def review_html(candidates: dict[str, list[dict[str, Any]]]) -> str:
    rows = []
    for code, items in candidates.items():
        cells = "".join(
            f'<figure><img src="{html.escape(c["thumbnail_url"])}" loading="lazy"><figcaption>'
            f"<b>{html.escape(c['id'])}</b><br>{html.escape(c['attribution_text'])}<br>"
            f'<a href="{html.escape(c["page_url"] or c["url"])}" target="_blank">원본</a>'
            "</figcaption></figure>"
            for c in items
        )
        rows.append(
            f"<h2>{html.escape(code)} — “{html.escape(QUERIES.get(code, ''))}”</h2><div>{cells}</div>"
        )
    return (
        "<!doctype html><meta charset=utf-8><title>분위기 이미지 후보</title><style>"
        "body{font:14px sans-serif;margin:24px}div{display:flex;flex-wrap:wrap;gap:12px}"
        "figure{width:220px;margin:0}img{width:220px;height:150px;object-fit:cover}</style>"
        "<p>간판 · 로고 · 읽히는 메뉴판 · 알아볼 수 있는 사람이 있는 사진은 고르지 않는다. "
        "고른 것은 <code>apply --pick 코드=id</code></p>" + "".join(rows)
    )


def cmd_search(args: argparse.Namespace) -> None:
    codes = args.only or list(QUERIES)
    out: dict[str, list[dict[str, Any]]] = (
        json.loads(CANDIDATES.read_text("utf-8")) if CANDIDATES.exists() else {}
    )
    with httpx.Client(headers={"User-Agent": UA}, timeout=20) as client:
        for code in codes:
            print(f"{code}: {QUERIES[code]}")
            out[code] = search(client, QUERIES[code], args.per)
            time.sleep(1.5)  # all three free tiers are rate-limited; this is a one-off job
    CANDIDATES.write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    CANDIDATES.with_suffix(".review.html").write_text(review_html(out), "utf-8")
    print(f"→ {CANDIDATES.name} · {CANDIDATES.with_suffix('.review.html').name}")


def cmd_apply(args: argparse.Namespace) -> None:
    candidates = json.loads(CANDIDATES.read_text("utf-8"))
    by_id = {c["id"]: c for items in candidates.values() for c in items}
    target = json.loads(TARGET.read_text("utf-8"))
    key = _env("UNSPLASH_ACCESS_KEY")
    for pick in args.pick:
        code, _, cid = pick.partition("=")
        c = by_id.get(cid)
        if not c:
            sys.exit(f"후보에 없는 id: {cid}")
        if c["source"] == "unsplash" and c.get("download_location") and key:
            httpx.get(c["download_location"], headers={"Authorization": f"Client-ID {key}"}, timeout=20)
        target[code] = {
            k: c[k]
            for k in (
                "url",
                "thumbnail_url",
                "page_url",
                "title",
                "author",
                "license",
                "source",
                "attribution_text",
            )
        }
        print(f"{code} ← {cid} ({c['attribution_text']})")
    TARGET.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("search")
    s.add_argument("--only", action="append", help="이 업종 코드만 (여러 번 가능)")
    s.add_argument("--per", type=int, default=4, help="출처마다 후보 수")
    s.set_defaults(fn=cmd_search)
    a = sub.add_parser("apply")
    a.add_argument("--pick", action="append", required=True, help="업종코드=후보id")
    a.set_defaults(fn=cmd_apply)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
