#!/usr/bin/env python3
"""
generate_stores.py
──────────────────
Reads scripts/data/stores.csv and scripts/data/coupons.csv and:

  1. Generates content/stores/<slug>.md       (Hugo store content pages)
  2. Generates data/featured_stores.json      (homepage Trending Stores)
  3. Generates data/latest_coupons.json       (homepage Latest Coupons feed)
  4. Generates static/stores-search-data.json (lazy-loaded client search index)

Changes from original version:
  ┌─────────────────────────────────────────────────────────────────────┐
  │  SEO GENERATION                                                     │
  │  • generate_title()     — clean pattern, never keyword-stuffed     │
  │  • generate_h1()        — includes active coupon count             │
  │  • generate_meta()      — features best coupon, ≤160 chars        │
  │  • generate_keywords()  — 6 natural variants, current month/year  │
  │  • detect_best_discount()— auto-parsed from coupon titles          │
  │  • verified_date         — defaults to current month/year          │
  │                                                                     │
  │  DATA QUALITY                                                       │
  │  • Coupon sorting: active-with-code → active-deal → expiring-soon  │
  │    → no-expiry → expired  (expired coupons last, never deleted)   │
  │  • Duplicate slug detection (blocking error)                       │
  │  • Duplicate coupon_id detection (warning)                         │
  │  • Validation report before any files are written                  │
  │  • coupon_count always reflects actual coupon count, not CSV field │
  │                                                                     │
  │  NEW OUTPUTS                                                        │
  │  • static/stores-search-data.json — minified search index for     │
  │    lazy-loading in app.js (replaces inline STORES_DATA in HTML)   │
  │                                                                     │
  │  CLI FLAGS                                                          │
  │  • --store <slug>      Process a single store only                │
  │  • --no-search-data    Skip search index output                   │
  │  • --skip-validation   Bypass CSV validation (not recommended)    │
  │  • --quiet             Suppress per-store progress lines           │
  └─────────────────────────────────────────────────────────────────────┘

Usage (run from Hugo project root):
    python3 scripts/data/generate_stores.py
    python3 scripts/data/generate_stores.py --dry-run
    python3 scripts/data/generate_stores.py --store amazon
    python3 scripts/data/generate_stores.py --root /path/to/hugo
    python3 scripts/data/generate_stores.py --dry-run --store nike --quiet

Requirements: Python 3.9+, stdlib only (no third-party packages).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

LATEST_COUPON_LIMIT  = 12     # Max coupons in data/latest_coupons.json
SEARCH_DATA_LIMIT    = 10_000 # Max stores in search index
EXPIRING_SOON_DAYS   = 14     # Days before expiry to flag as "expiring soon"
META_DESC_MAX_LEN    = 160    # Hard limit for meta description length

# CSV cell values that are treated as "empty / not provided"
_INVALID_VALUES = frozenset({
    "", "undefined", "null", "none", "n/a", "na", "false", "0",
})

# Valid slug characters
_SLUG_INVALID = frozenset({"undefined", "null", "none", "n/a", ""})


# ══════════════════════════════════════════════════════════════════════════════
# DATE UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def current_month_year() -> str:
    """Return the current month and year, e.g. 'May 2026'."""
    return datetime.now().strftime("%B %Y")


def parse_ddmmyyyy(value: str) -> datetime | None:
    """
    Parse a DD/MM/YYYY date string to a UTC-aware datetime.
    Returns None if the string is empty or malformed.
    """
    value = (value or "").strip()
    if not value:
        return None
    parts = value.split("/")
    if len(parts) != 3:
        return None
    try:
        return datetime(
            int(parts[2]), int(parts[1]), int(parts[0]),
            tzinfo=timezone.utc,
        )
    except (ValueError, IndexError):
        return None


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def is_expired(expires_at: str) -> bool:
    """Return True if the DD/MM/YYYY date is in the past."""
    dt = parse_ddmmyyyy(expires_at)
    return dt is not None and dt < _now_utc()


def is_expiring_soon(expires_at: str) -> bool:
    """Return True if the coupon expires within EXPIRING_SOON_DAYS days."""
    dt = parse_ddmmyyyy(expires_at)
    if dt is None:
        return False
    delta = (dt - _now_utc()).days
    return 0 <= delta <= EXPIRING_SOON_DAYS


# ══════════════════════════════════════════════════════════════════════════════
# STRING UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def slugify(text: str) -> str:
    """Convert any string to a URL-safe ASCII slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+",     "-", text)
    return text.strip("-")


def safe_yaml(value: str) -> str:
    """Escape a string for use inside double-quoted YAML scalar values."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def bool_field(value: str) -> str:
    """Convert a truthy CSV string to a YAML boolean literal."""
    return "true" if str(value).strip().lower() in {"true", "1", "yes"} else "false"


def is_true(value: str) -> bool:
    """Return True for CSV values that mean 'yes / enabled'."""
    return str(value).strip().lower() in {"true", "1", "yes"}


def clean_str(value: str) -> str:
    """
    Strip whitespace and remove matching surrounding quote characters
    that some spreadsheet editors write as literal content.

    Examples:
        '"Amazon"'   → 'Amazon'
        "'Amazon'"   → 'Amazon'
        '  Amazon  ' → 'Amazon'
    """
    value = (value or "").strip()
    if len(value) >= 2:
        if value[0] == '"' and value[-1] == '"':
            value = value[1:-1].strip()
        elif value[0] == "'" and value[-1] == "'":
            value = value[1:-1].strip()
    return value


def pick(row: dict, *keys: str, fallback: str = "") -> str:
    """
    Return the first non-empty, clean value found among the given keys.
    Values matching _INVALID_VALUES are skipped as if absent.
    """
    for key in keys:
        raw = row.get(key) or row.get(key.strip()) or ""
        val = clean_str(raw)
        if val.lower() not in _INVALID_VALUES:
            return val
    return fallback


def trim_to_length(text: str, max_len: int) -> str:
    """
    Trim text to at most max_len characters, breaking at a word boundary
    and appending '…' if trimmed.
    """
    if len(text) <= max_len:
        return text
    trimmed = text[: max_len - 1].rsplit(" ", 1)[0].rstrip(".,;:-")
    return trimmed + "…"


# ══════════════════════════════════════════════════════════════════════════════
# CSV READING
# ══════════════════════════════════════════════════════════════════════════════

def read_csv(path: Path) -> list[dict]:
    """
    Read a CSV file with automatic encoding detection.
    Tries UTF-8-BOM first (common from Excel exports), then falls back
    to cp1252 and latin-1 before giving up and using UTF-8 with replacement.
    """
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as fh:
                rows = list(csv.DictReader(fh))
            if encoding not in ("utf-8-sig", "utf-8"):
                print(f"  ℹ️  {path.name} decoded with {encoding}")
            return rows
        except UnicodeDecodeError:
            continue
    # Last resort — replace undecodable bytes
    print(f"  ⚠️  {path.name}: could not auto-detect encoding; using UTF-8 with replacement.")
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


# ══════════════════════════════════════════════════════════════════════════════
# COUPON SORTING
# ══════════════════════════════════════════════════════════════════════════════

def _coupon_sort_key(coupon: dict) -> tuple:
    """
    Sort key that orders coupons from most to least desirable:

      0 — active coupon with a promo code
      1 — active deal (no code needed)
      2 — expiring within EXPIRING_SOON_DAYS days (any type)
      3 — no expiry date set
      4 — expired (always shown last)

    Secondary sort is by coupon_id (ascending) for stable, reproducible output.
    """
    exp_raw  = pick(coupon, "coupon_expired", "expires_at")
    has_code = bool(pick(coupon, "coupon_code"))

    if is_expired(exp_raw):
        primary = 4
    elif is_expiring_soon(exp_raw):
        primary = 2
    elif not exp_raw:
        primary = 3
    elif has_code:
        primary = 0
    else:
        primary = 1

    try:
        secondary = int(pick(coupon, "coupon_id") or 0)
    except ValueError:
        secondary = 0

    return (primary, secondary)


def sort_coupons(coupons: list[dict]) -> list[dict]:
    """Return coupons sorted by _coupon_sort_key."""
    return sorted(coupons, key=_coupon_sort_key)


# ══════════════════════════════════════════════════════════════════════════════
# SEO FIELD GENERATORS
# ══════════════════════════════════════════════════════════════════════════════

def generate_title(store_name: str, coupons: list[dict]) -> str:
    """
    Generate a clean, natural <title> tag value.

    Pattern: "{StoreName} Coupon Codes & Promo Codes – {Month Year}"

    Avoids keyword repetition and numbers-in-title tricks that look
    spammy in SERPs. The month/year signals freshness to both users
    and Google without over-stuffing.
    """
    return f"{store_name} Coupon Codes & Promo Codes \u2013 {current_month_year()}"


def generate_h1(store_name: str, coupons: list[dict]) -> str:
    """
    Generate a clean H1 heading for the store page.

    Uses the active coupon count for specificity. Falls back gracefully
    when there are no coupons.

    Pattern (with coupons):    "{StoreName} Coupons – {N} Verified Deals ({Month Year})"
    Pattern (without coupons): "{StoreName} Coupons & Deals – {Month Year}"
    """
    active_n = sum(
        1 for c in coupons
        if not is_expired(pick(c, "coupon_expired", "expires_at"))
    )
    count = active_n or len(coupons)
    if count:
        return (
            f"{store_name} Coupons \u2013 "
            f"{count} Verified Deals ({current_month_year()})"
        )
    return f"{store_name} Coupons & Deals \u2013 {current_month_year()}"


def generate_meta_description(store_name: str, coupons: list[dict]) -> str:
    """
    Generate a natural meta description capped at META_DESC_MAX_LEN chars.

    Strategy:
      - Prefer active coupons with a code (most useful to searchers)
      - Feature the best coupon title for specificity
      - Always state the count and "updated daily" for freshness signal
      - Never exceed META_DESC_MAX_LEN chars (trims at word boundary)
    """
    month_year = current_month_year()

    # Active coupons sorted best-first
    active = [
        c for c in sort_coupons(coupons)
        if not is_expired(pick(c, "coupon_expired", "expires_at"))
    ]
    count = len(active) or len(coupons)

    # Find the best coupon title to feature
    best_title = ""
    for c in active:
        t = pick(c, "coupon_title")
        if t:
            best_title = t
            break

    if best_title and count > 1:
        desc = (
            f"Find {count} verified {store_name} coupon codes for {month_year}. "
            f"Best deal: {best_title}. Updated daily, 100% free."
        )
    elif best_title:
        desc = (
            f"Save with verified {store_name} coupon codes for {month_year}. "
            f"Latest deal: {best_title}. Updated daily, 100% free."
        )
    elif count:
        desc = (
            f"Find {count} verified {store_name} coupon codes & promo codes for "
            f"{month_year}. Updated daily \u2014 100% free, no sign-up required."
        )
    else:
        desc = (
            f"Find the latest {store_name} coupon codes & promo codes for "
            f"{month_year}. Updated daily \u2014 100% free, no sign-up required."
        )

    return trim_to_length(desc, META_DESC_MAX_LEN)


def generate_keywords(store_name: str, slug: str) -> str:
    """
    Generate a non-stuffed, natural keyword string with 6 core variants.

    Avoids repeating the store name more than necessary and keeps the
    list to terms that reflect actual search intent.
    """
    name   = store_name.lower()
    period = current_month_year().lower()
    return (
        f"{name} coupon code, {name} promo code, "
        f"{name} discount code, {name} coupons, "
        f"{name} deals, {name} coupon {period}"
    )


def detect_best_discount(coupons: list[dict]) -> str:
    """
    Auto-detect the best available discount from active coupon titles
    and descriptions by scanning for common discount patterns.

    Priority: highest percentage → highest dollar amount → free shipping.
    Returns an empty string if nothing is detected.
    """
    pct_re    = re.compile(r"(\d+)\s*%\s*off",      re.IGNORECASE)
    dollar_re = re.compile(r"\$\s*(\d+)\s*(?:off)?", re.IGNORECASE)
    free_re   = re.compile(r"free\s+shipping",       re.IGNORECASE)

    best_pct        = 0
    best_dollar     = 0
    has_free_ship   = False

    for c in coupons:
        # Only look at active coupons
        if is_expired(pick(c, "coupon_expired", "expires_at")):
            continue

        text = (
            pick(c, "coupon_title") + " "
            + pick(c, "coupon_description")
        )

        for m in pct_re.findall(text):
            best_pct = max(best_pct, int(m))

        for m in dollar_re.findall(text):
            try:
                best_dollar = max(best_dollar, int(m))
            except ValueError:
                pass

        if free_re.search(text):
            has_free_ship = True

    if best_pct:
        return f"Up to {best_pct}% Off"
    if best_dollar:
        return f"Up to ${best_dollar} Off"
    if has_free_ship:
        return "Free Shipping"
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# MARKDOWN BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_markdown(store: dict, coupons: list[dict]) -> str:
    """
    Build the complete Hugo front matter + markdown body for one store page.

    SEO field priority (highest → lowest):
      1. CSV-provided value  (explicit override always wins)
      2. Auto-generated value (from store name + coupon data + current date)

    Coupons are sorted active-first before being written.
    coupon_count always reflects the actual number of coupons in the list,
    never the CSV value, to keep Hugo templates in sync.
    """

    # ── Core identifiers ──────────────────────────────────────────────────────
    store_name = pick(store, "store_name", "website_name", "name")
    name       = pick(store, "website_name", "store_name", "name")
    display    = store_name or name     # What to show in UI

    slug = (
        pick(store, "slug", "store_slug", "id", "store_id")
        or slugify(display)
    )

    url     = pick(store, "website_url",     "store_url")
    aff_url = pick(store, "website_aff_url", "store_aff_url") or url
    logo    = pick(store, "logo_url",        "store_logo_url")

    active   = bool_field(pick(store, "is_active",        "store_active",   fallback="true"))
    featured = bool_field(pick(store, "website_featured", "store_featured", fallback="false"))

    # ── Sort coupons ──────────────────────────────────────────────────────────
    sorted_coupons = sort_coupons(coupons)
    coupon_count   = len(sorted_coupons)   # Always use actual count

    # ── SEO: title ────────────────────────────────────────────────────────────
    store_title = (
        pick(store, "store_title")
        or generate_title(display, sorted_coupons)
    )

    # ── SEO: H1 ───────────────────────────────────────────────────────────────
    store_h1 = (
        pick(store, "store_h1")
        or generate_h1(display, sorted_coupons)
    )

    # ── SEO: meta description ─────────────────────────────────────────────────
    store_meta = (
        pick(store, "store_meta_description", "description")
        or generate_meta_description(display, sorted_coupons)
    )

    # ── SEO: keywords ─────────────────────────────────────────────────────────
    store_kw = (
        pick(store, "store_keywords")
        or generate_keywords(display, slug)
    )

    # ── Open Graph ────────────────────────────────────────────────────────────
    og_title = pick(store, "store_og_title")  or store_title
    og_desc  = pick(store, "store_og_description") or store_meta
    og_image = pick(store, "store_og_image")  or logo
    og_type  = pick(store, "store_og_type",   fallback="website")

    # ── Stats ─────────────────────────────────────────────────────────────────
    # best_discount: CSV override; auto-detect if absent
    best_discount = (
        pick(store, "best_discount")
        or detect_best_discount(sorted_coupons)
    )

    # verified_date: CSV override; default to current month/year
    verified_date = (
        pick(store, "verified_date")
        or current_month_year()
    )

    avg_saving = pick(store, "avg_saving")

    # ── Assemble front matter lines ───────────────────────────────────────────
    lines: list[str] = [
        "---",
        f'title: "{safe_yaml(store_title)}"',
        f'slug: "{safe_yaml(slug)}"',
        f'description: "{safe_yaml(store_meta)}"',
        "",
        "# ── Display name (used in UI: buttons, footer, cards, search) ───────",
        f'store_name: "{safe_yaml(display)}"',
        "",
        "# ── On-page SEO ──────────────────────────────────────────────────────",
        f'store_h1: "{safe_yaml(store_h1)}"',
        f'store_title: "{safe_yaml(store_title)}"',
        f'store_meta_description: "{safe_yaml(store_meta)}"',
        f'store_keywords: "{safe_yaml(store_kw)}"',
        "",
        "# ── Open Graph / Social sharing ──────────────────────────────────────",
        f'store_og_title: "{safe_yaml(og_title)}"',
        f'store_og_description: "{safe_yaml(og_desc)}"',
        f'store_og_image: "{safe_yaml(og_image)}"',
        f'store_og_type: "{safe_yaml(og_type)}"',
        "",
        "# ── Store data ───────────────────────────────────────────────────────",
        f'logo_url: "{safe_yaml(logo)}"',
        f'website_url: "{safe_yaml(url)}"',
        f'website_aff_url: "{safe_yaml(aff_url)}"',
        f'is_active: {active}',
        f'website_featured: {featured}',
        f'coupon_count: {coupon_count}',
        f'store_id: "{safe_yaml(slug)}"',
    ]

    if best_discount:
        lines.append(f'best_discount: "{safe_yaml(best_discount)}"')
    if verified_date:
        lines.append(f'verified_date: "{safe_yaml(verified_date)}"')
    if avg_saving:
        lines.append(f'avg_saving: "{safe_yaml(avg_saving)}"')

    lines.append("")

    # ── Coupons block ─────────────────────────────────────────────────────────
    if sorted_coupons:
        lines.append("coupons:")
        for c in sorted_coupons:
            lines.append(
                '  - coupon_id: "'
                + safe_yaml(pick(c, "coupon_id")) + '"'
            )
            lines.append(
                '    coupon_title: "'
                + safe_yaml(pick(c, "coupon_title")) + '"'
            )
            lines.append(
                '    coupon_code: "'
                + safe_yaml(pick(c, "coupon_code")) + '"'
            )
            lines.append(
                '    coupon_description: "'
                + safe_yaml(pick(c, "coupon_description")) + '"'
            )
            lines.append(
                '    coupon_aff_url: "'
                + safe_yaml(pick(c, "coupon_aff_url")) + '"'
            )
            lines.append(
                '    coupon_type: "'
                + safe_yaml(pick(c, "coupon_type", fallback="Deal")) + '"'
            )
            lines.append(
                '    coupon_start: "'
                + safe_yaml(pick(c, "coupon_start")) + '"'
            )
            lines.append(
                '    expires_at: "'
                + safe_yaml(pick(c, "coupon_expired", "expires_at")) + '"'
            )
    else:
        lines.append("coupons: []")

    lines.append("---")
    lines.append("")

    # ── Markdown body (store description) ────────────────────────────────────
    body = pick(store, "website_desc", "store_description", "description")
    if body:
        lines.append(body)
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# JSON BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_featured_stores(
    stores: list[dict],
    coupons_by_store_id: dict[str, list],
) -> list[dict]:
    """
    Build data/featured_stores.json.
    Only includes stores where website_featured = true.
    """
    featured: list[dict] = []

    for store in stores:
        if not is_true(
            pick(store, "website_featured", "store_featured", fallback="false")
        ):
            continue

        store_name = pick(store, "store_name", "website_name", "name")
        name       = pick(store, "website_name", "store_name", "name")
        slug       = (
            pick(store, "slug", "store_slug", "id", "store_id")
            or slugify(store_name or name)
        )
        raw_id  = pick(store, "store_id", "id") or slug
        url     = pick(store, "website_url",     "store_url")
        aff_url = pick(store, "website_aff_url", "store_aff_url") or url
        logo    = pick(store, "logo_url",        "store_logo_url")
        count   = len(coupons_by_store_id.get(raw_id, []))

        featured.append({
            "store_name":      store_name or name,
            "website_name":    name,
            "slug":            slug,
            "logo_url":        logo,
            "website_url":     url,
            "website_aff_url": aff_url,
            "coupon_count":    count,
        })

    return featured


def build_latest_coupons(
    coupons: list[dict],
    stores_by_raw_id: dict[str, dict],
    limit: int = LATEST_COUPON_LIMIT,
) -> list[dict]:
    """
    Build data/latest_coupons.json.

    Returns up to `limit` coupons with embedded store info.
    Active coupons always appear before expired ones.
    """
    # Separate active from expired, keep each group's original CSV order
    active  = [c for c in coupons if not is_expired(pick(c, "coupon_expired", "expires_at"))]
    expired = [c for c in coupons if     is_expired(pick(c, "coupon_expired", "expires_at"))]

    ordered = (active + expired)[:limit]
    result: list[dict] = []

    for c in ordered:
        raw_id = pick(c, "store_id", "storeId")
        store  = stores_by_raw_id.get(raw_id, {})

        store_name = (
            pick(store, "store_name", "website_name", "name") if store
            else pick(c, "store_name")
        )
        name = (
            pick(store, "website_name", "store_name", "name") if store
            else store_name
        )
        slug = (
            store.get("slug", "") if store
            else slugify(store_name or name)
        ) or slugify(store_name or name)
        logo = pick(store, "logo_url", "store_logo_url") if store else ""

        result.append({
            "coupon_id":          pick(c, "coupon_id"),
            "coupon_title":       pick(c, "coupon_title"),
            "coupon_code":        pick(c, "coupon_code"),
            "coupon_description": pick(c, "coupon_description"),
            "coupon_aff_url":     pick(c, "coupon_aff_url"),
            "coupon_type":        pick(c, "coupon_type", fallback="Deal"),
            "coupon_start":       pick(c, "coupon_start"),
            "expires_at":         pick(c, "coupon_expired", "expires_at"),
            "stores": {
                "store_name":   store_name or name,
                "website_name": name,
                "slug":         slug,
                "logo_url":     logo,
            },
        })

    return result


def build_search_data(
    stores: list[dict],
    coupons_by_store_id: dict[str, list],
) -> list[dict]:
    """
    Build static/stores-search-data.json — a compact, minified search
    index for lazy-loading in app.js.

    Fields kept minimal to reduce payload size:
      n  → store name  (display + search match)
      s  → slug        (URL construction)
      c  → coupon count

    Only active stores with valid slugs are included.
    Sorted A→Z by name for consistent output and binary-search compatibility.
    """
    results: list[dict] = []

    for store in stores:
        if not is_true(pick(store, "is_active", "store_active", fallback="true")):
            continue

        store_name = pick(store, "store_name", "website_name", "name")
        name       = pick(store, "website_name", "store_name", "name")
        display    = store_name or name
        slug       = (
            pick(store, "slug", "store_slug", "id", "store_id")
            or slugify(display)
        )

        if not slug or slug in _SLUG_INVALID:
            continue

        raw_id = pick(store, "store_id", "id") or slug
        count  = len(coupons_by_store_id.get(raw_id, []))

        results.append({"n": display, "s": slug, "c": count})

        if len(results) >= SEARCH_DATA_LIMIT:
            break

    results.sort(key=lambda x: x["n"].lower())
    return results


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_stores(stores: list[dict]) -> tuple[list[str], list[str]]:
    """
    Validate store rows before writing any files.

    Returns:
        warnings — non-blocking issues printed before processing
        errors   — blocking issues that abort the run
    """
    warnings: list[str] = []
    errors:   list[str] = []
    seen_slugs: dict[str, int] = {}   # slug → first row number

    for row_num, store in enumerate(stores, start=2):  # row 1 is the CSV header
        store_name = pick(store, "store_name", "website_name", "name")
        slug = (
            pick(store, "slug", "store_slug", "id", "store_id")
            or slugify(store_name)
        )

        if not store_name:
            warnings.append(
                f"  Row {row_num}: Missing store_name — row will be skipped."
            )
            continue

        if not slug or slug in _SLUG_INVALID:
            errors.append(
                f"  Row {row_num} ({store_name!r}): Cannot derive a valid slug."
            )
            continue

        if slug in seen_slugs:
            errors.append(
                f"  Row {row_num} ({store_name!r}): Duplicate slug '{slug}' "
                f"— first seen at row {seen_slugs[slug]}."
            )
        else:
            seen_slugs[slug] = row_num

        if not pick(store, "website_url", "store_url"):
            warnings.append(
                f"  Row {row_num} ({store_name!r}): Missing website_url."
            )

    return warnings, errors


def validate_coupons(coupons: list[dict]) -> list[str]:
    """
    Warn about coupon data quality issues.
    Returns a list of warning strings (non-blocking).
    """
    warnings: list[str] = []
    seen_ids: dict[str, str] = {}   # coupon_id → store_id

    for coupon in coupons:
        cid = pick(coupon, "coupon_id")
        sid = pick(coupon, "store_id", "storeId")

        if not cid:
            warnings.append(
                f"  Coupon in store '{sid}' has no coupon_id — may cause "
                f"duplicate or missing entries."
            )
            continue

        if cid in seen_ids:
            warnings.append(
                f"  Duplicate coupon_id '{cid}' in stores "
                f"'{seen_ids[cid]}' and '{sid}'."
            )
        else:
            seen_ids[cid] = sid

    return warnings


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_stores.py",
        description="Generate Hugo store pages and data JSON from CSV sources.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full generation (from Hugo project root)
  python3 scripts/data/generate_stores.py

  # Preview without writing any files
  python3 scripts/data/generate_stores.py --dry-run

  # Process a single store by slug
  python3 scripts/data/generate_stores.py --store amazon

  # Custom paths
  python3 scripts/data/generate_stores.py \\
      --stores-csv  data/stores.csv \\
      --coupons-csv data/coupons.csv \\
      --root        /var/www/couponhauls

  # Skip search data (e.g. when not using lazy-load search)
  python3 scripts/data/generate_stores.py --no-search-data
""",
    )

    # ── Path arguments ────────────────────────────────────────────────────────
    parser.add_argument(
        "--root", default=".",
        help="Hugo project root directory (default: current working directory)",
    )
    parser.add_argument(
        "--stores-csv", default=None,
        help="Path to stores.csv (default: <root>/scripts/data/stores.csv)",
    )
    parser.add_argument(
        "--coupons-csv", default=None,
        help="Path to coupons.csv (default: <root>/scripts/data/coupons.csv)",
    )
    parser.add_argument(
        "--out-dir", default=None,
        help="Output directory for .md files (default: <root>/content/stores)",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="Output directory for data JSON files (default: <root>/data)",
    )
    parser.add_argument(
        "--static-dir", default=None,
        help="Output directory for static files (default: <root>/static)",
    )

    # ── Behaviour arguments ───────────────────────────────────────────────────
    parser.add_argument(
        "--store", default=None, metavar="SLUG",
        help="Process only the store with this slug (skips JSON outputs)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching any files",
    )
    parser.add_argument(
        "--no-search-data", action="store_true",
        help="Skip writing static/stores-search-data.json",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Bypass CSV validation (use only when you know what you are doing)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-store progress lines; only print summary",
    )

    args = parser.parse_args()

    # ── Resolve paths ─────────────────────────────────────────────────────────
    root              = Path(args.root).resolve()
    stores_csv_path   = (
        Path(args.stores_csv)  if args.stores_csv
        else root / "scripts" / "data" / "stores.csv"
    )
    coupons_csv_path  = (
        Path(args.coupons_csv) if args.coupons_csv
        else root / "scripts" / "data" / "coupons.csv"
    )
    out_dir           = (
        Path(args.out_dir)     if args.out_dir
        else root / "content" / "stores"
    )
    data_dir          = (
        Path(args.data_dir)    if args.data_dir
        else root / "data"
    )
    static_dir        = (
        Path(args.static_dir)  if args.static_dir
        else root / "static"
    )

    # ── Check source files exist ──────────────────────────────────────────────
    missing: list[str] = []
    if not stores_csv_path.exists():
        missing.append(f"  ✗  stores.csv  not found: {stores_csv_path}")
    if not coupons_csv_path.exists():
        missing.append(f"  ✗  coupons.csv not found: {coupons_csv_path}")
    if missing:
        print("❌  Missing required input files:\n" + "\n".join(missing))
        sys.exit(1)

    # ── Load CSV data ─────────────────────────────────────────────────────────
    stores  = read_csv(stores_csv_path)
    coupons = read_csv(coupons_csv_path)

    print(f"\n📦  {len(stores):,} stores  |  🎫  {len(coupons):,} coupons\n")

    # ── Column diagnostics ────────────────────────────────────────────────────
    if stores:
        cols = {k.strip() for k in stores[0].keys()}

        seo_cols = {"store_h1", "store_title", "store_meta_description"}
        if seo_cols - cols:
            print(f"  ℹ️  SEO columns absent — will auto-generate: {seo_cols - cols}")
        else:
            print("  ✅  SEO columns found (store_h1, store_title, store_meta_description)")

        if "store_keywords" not in cols:
            print("  ℹ️  store_keywords absent — will auto-generate")

        if {"best_discount", "verified_date"} - cols:
            print("  ℹ️  best_discount / verified_date absent — will auto-detect")

        if "store_og_image" not in cols:
            print("  ℹ️  store_og_image absent — will fall back to logo_url")

        # Warn if store_name cells have embedded quotes
        sample = (stores[0].get("store_name") or "").strip()
        if sample and sample.startswith('"'):
            print(
                f"  ⚠️  store_name values appear quoted (e.g. {sample!r}). "
                f"clean_str() will strip them automatically."
            )

    # ── Validation ────────────────────────────────────────────────────────────
    if not args.skip_validation:
        store_warnings, store_errors = validate_stores(stores)
        coupon_warnings = validate_coupons(coupons)
        all_warnings = store_warnings + coupon_warnings

        if all_warnings:
            print("\n⚠️  Warnings:")
            for w in all_warnings:
                print(w)

        if store_errors:
            print("\n❌  Validation errors — aborting before writing any files:")
            for e in store_errors:
                print(e)
            print(
                "\nFix the errors above, or re-run with --skip-validation "
                "to bypass (not recommended)."
            )
            sys.exit(1)

    # ── Index coupons by store_id ─────────────────────────────────────────────
    coupons_by_store_id: dict[str, list[dict]] = defaultdict(list)
    for coupon in coupons:
        sid = pick(coupon, "store_id", "storeId")
        if sid:
            coupons_by_store_id[sid].append(coupon)

    # ── Build store lookup dict ───────────────────────────────────────────────
    stores_by_raw_id: dict[str, dict] = {}
    for store in stores:
        store_name = pick(store, "store_name", "website_name", "name")
        name       = pick(store, "website_name", "store_name", "name")
        slug       = (
            pick(store, "slug", "store_slug", "id", "store_id")
            or slugify(store_name or name)
        )
        raw_id = pick(store, "store_id", "id") or slug
        store["slug"] = slug          # cache computed slug on the dict
        stores_by_raw_id[raw_id] = store

    # ── Filter to single store when --store is given ──────────────────────────
    single_mode   = bool(args.store)
    target_stores = stores

    if single_mode:
        target_slug   = args.store.strip().lower()
        target_stores = [
            s for s in stores
            if (s.get("slug") or "").lower() == target_slug
            or pick(s, "slug", "store_slug", "store_id").lower() == target_slug
        ]
        if not target_stores:
            print(f"❌  No store found with slug '{args.store}'")
            sys.exit(1)
        print(f"  🔍  Single-store mode: {args.store}\n")

    # ── 1. Write content/stores/<slug>.md ────────────────────────────────────
    label = "[DRY RUN] " if args.dry_run else ""
    print(f"{label}Writing store pages → {out_dir}")

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    written        = 0
    skipped        = 0
    write_errors   = 0
    active_total   = 0

    for store in target_stores:
        store_name = pick(store, "store_name", "website_name", "name")
        name       = pick(store, "website_name", "store_name", "name")
        display    = store_name or name
        slug       = store.get("slug") or slugify(display)
        raw_id     = pick(store, "store_id", "id") or slug

        # Skip rows with no usable name/slug
        if not slug or slug in _SLUG_INVALID:
            if not args.quiet:
                print(f"  ⚠️  Skipping row with no valid slug: {dict(list(store.items())[:4])}")
            skipped += 1
            continue

        # Skip inactive stores
        if not is_true(pick(store, "is_active", "store_active", fallback="true")):
            skipped += 1
            continue

        active_total += 1
        store_coupons = coupons_by_store_id.get(raw_id, [])
        md_path       = out_dir / f"{slug}.md"
        md_text       = build_markdown(store, store_coupons)

        if args.dry_run:
            if not args.quiet:
                active_n = sum(
                    1 for c in store_coupons
                    if not is_expired(pick(c, "coupon_expired", "expires_at"))
                )
                print(
                    f"  [DRY RUN] {slug}.md  "
                    f"({display!r}, {len(store_coupons)} coupons, "
                    f"{active_n} active)"
                )
        else:
            try:
                md_path.write_text(md_text, encoding="utf-8")
                written += 1
                if not args.quiet:
                    print(f"  ✓  {slug}.md")
            except OSError as exc:
                print(f"  ✗  Failed to write {md_path}: {exc}")
                write_errors += 1

    # ── 2–4. JSON outputs (skipped in single-store mode) ─────────────────────
    if not single_mode:

        # ── 2. data/featured_stores.json ─────────────────────────────────────
        featured      = build_featured_stores(stores, coupons_by_store_id)
        featured_path = data_dir / "featured_stores.json"

        if args.dry_run:
            print(f"\n  [DRY RUN] → {featured_path}  ({len(featured)} featured stores)")
        else:
            data_dir.mkdir(parents=True, exist_ok=True)
            featured_path.write_text(
                json.dumps(featured, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\n⭐   {len(featured)} featured stores → {featured_path}")

        # ── 3. data/latest_coupons.json ──────────────────────────────────────
        latest      = build_latest_coupons(coupons, stores_by_raw_id)
        latest_path = data_dir / "latest_coupons.json"

        if args.dry_run:
            print(f"  [DRY RUN] → {latest_path}  ({len(latest)} coupons)")
        else:
            latest_path.write_text(
                json.dumps(latest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"🎫   {len(latest)} latest coupons → {latest_path}")

        # ── 4. static/stores-search-data.json ───────────────────────────────
        if not args.no_search_data:
            search_data      = build_search_data(stores, coupons_by_store_id)
            search_data_path = static_dir / "stores-search-data.json"

            if args.dry_run:
                print(
                    f"  [DRY RUN] → {search_data_path}  "
                    f"({len(search_data)} entries)"
                )
            else:
                static_dir.mkdir(parents=True, exist_ok=True)
                # Minified (no indent) to keep payload small
                search_data_path.write_text(
                    json.dumps(search_data, separators=(",", ":"), ensure_ascii=False),
                    encoding="utf-8",
                )
                size_kb = search_data_path.stat().st_size / 1024
                print(
                    f"🔍   {len(search_data)} stores in search index "
                    f"→ {search_data_path}  ({size_kb:.1f} KB)"
                )

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 56)
    if args.dry_run:
        print(f"  [DRY RUN] No files were written.")
        print(f"  Would write:  {active_total} store pages")
        if skipped:
            print(f"  Would skip:   {skipped} inactive / invalid stores")
    else:
        print(f"  ✅  Done!")
        print(f"  Store pages written:         {written}")
        if skipped:
            print(f"  Skipped (inactive/invalid):  {skipped}")
        if write_errors:
            print(f"  ⚠️   Write errors:             {write_errors}")
    print()

    if write_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()