#!/usr/bin/env python3
"""
generate_stores.py
──────────────────
Reads scripts/data/stores.csv and scripts/data/coupons.csv and:

  1. Generates content/stores/<slug>.md  (Hugo content pages)
  2. Generates data/featured_stores.json (homepage "Trending Stores" section)
  3. Generates data/latest_coupons.json  (homepage "Latest Coupon Codes" section)

Usage (run from Hugo project root):
    python3 scripts/data/generate_stores.py
    python3 scripts/data/generate_stores.py --dry-run
    python3 scripts/data/generate_stores.py --root /path/to/hugo
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def safe_yaml(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def bool_field(value: str) -> str:
    return "true" if str(value).strip().lower() in {"true", "1", "yes"} else "false"


def is_true(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as fh:
                rows = list(csv.DictReader(fh))
            if encoding != "utf-8-sig":
                print(f"  ℹ️  {path.name} read with {encoding} encoding")
            return rows
        except UnicodeDecodeError:
            continue
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


_INVALID = {"undefined", "null", "none", "n/a", ""}


def pick(row: dict, *keys: str, fallback: str = "") -> str:
    for key in keys:
        val = (row.get(key) or "").strip()
        if val.lower() not in _INVALID:
            return val
    return fallback


# ── Markdown builder ──────────────────────────────────────────────────────────

def build_markdown(store: dict, coupons: list) -> str:
    name     = pick(store, "website_name", "store_name", "name")
    slug     = pick(store, "slug", "store_slug", "id", "store_id") or slugify(name)
    desc     = pick(store, "website_desc", "store_description", "description")
    logo     = pick(store, "logo_url", "store_logo_url")
    url      = pick(store, "website_url", "store_url")
    aff_url  = pick(store, "website_aff_url", "store_aff_url") or url
    active   = bool_field(pick(store, "is_active",        "store_active",   fallback="true"))
    featured = bool_field(pick(store, "website_featured", "store_featured", fallback="false"))
    count    = len(coupons)

    lines = [
        "---",
        f'title: "{safe_yaml(name)}"',
        f'slug: "{safe_yaml(slug)}"',
        f'description: "{safe_yaml(desc)}"',
        f'logo_url: "{safe_yaml(logo)}"',
        f'website_url: "{safe_yaml(url)}"',
        f'website_aff_url: "{safe_yaml(aff_url)}"',
        f'is_active: {active}',
        f'website_featured: {featured}',
        f'coupon_count: {count}',
        f'store_id: "{safe_yaml(slug)}"',
    ]

    if coupons:
        lines.append("coupons:")
        for c in coupons:
            lines.append("  - coupon_id: \""         + safe_yaml(pick(c, "coupon_id"))          + "\"")
            lines.append("    coupon_title: \""       + safe_yaml(pick(c, "coupon_title"))       + "\"")
            lines.append("    coupon_code: \""        + safe_yaml(pick(c, "coupon_code"))        + "\"")
            lines.append("    coupon_description: \"" + safe_yaml(pick(c, "coupon_description")) + "\"")
            lines.append("    coupon_aff_url: \""     + safe_yaml(pick(c, "coupon_aff_url"))     + "\"")
            lines.append("    coupon_type: \""        + safe_yaml(pick(c, "coupon_type", fallback="Deal")) + "\"")
            lines.append("    coupon_start: \""       + safe_yaml(pick(c, "coupon_start"))       + "\"")
            lines.append("    expires_at: \""         + safe_yaml(pick(c, "coupon_expired", "expires_at")) + "\"")
    else:
        lines.append("coupons: []")

    lines.append("---")
    lines.append("")
    if desc:
        lines.append(desc)
        lines.append("")

    return "\n".join(lines)


# ── JSON builders ─────────────────────────────────────────────────────────────

def build_featured_stores(stores: list, coupons_by_store_id: dict) -> list:
    """
    Returns stores where website_featured == true.
    coupons_by_store_id is keyed by the raw store_id column (e.g. "4", "10").
    """
    featured = []
    for store in stores:
        if not is_true(pick(store, "website_featured", "store_featured", fallback="false")):
            continue

        name     = pick(store, "website_name", "store_name", "name")
        slug     = pick(store, "slug", "store_slug", "id", "store_id") or slugify(name)
        logo     = pick(store, "logo_url", "store_logo_url")
        url      = pick(store, "website_url", "store_url")
        aff_url  = pick(store, "website_aff_url", "store_aff_url") or url
        # Use raw store_id for coupon lookup (matches coupons.csv store_id column)
        raw_id   = pick(store, "store_id", "id") or slug
        count    = len(coupons_by_store_id.get(raw_id, []))

        featured.append({
            "website_name":    name,
            "slug":            slug,
            "logo_url":        logo,
            "website_url":     url,
            "website_aff_url": aff_url,
            "coupon_count":    count,
        })

    return featured


def build_latest_coupons(coupons: list, stores_by_raw_id: dict, limit: int = 12) -> list:
    """
    Returns most recent coupons with store info nested.
    stores_by_raw_id is keyed by the raw store_id column (e.g. "4", "10").
    """
    latest = []
    for c in coupons[:limit]:
        raw_id = pick(c, "store_id", "storeId")
        store  = stores_by_raw_id.get(raw_id, {})
        name   = pick(store, "website_name", "store_name", "name") if store else pick(c, "store_name")
        slug   = store.get("slug", slugify(name)) if store else slugify(name)
        logo   = pick(store, "logo_url", "store_logo_url") if store else ""

        latest.append({
            "coupon_id":          pick(c, "coupon_id"),
            "coupon_title":       pick(c, "coupon_title"),
            "coupon_code":        pick(c, "coupon_code"),
            "coupon_description": pick(c, "coupon_description"),
            "coupon_aff_url":     pick(c, "coupon_aff_url"),
            "coupon_type":        pick(c, "coupon_type", fallback="Deal"),
            "coupon_start":       pick(c, "coupon_start"),
            "expires_at":         pick(c, "coupon_expired", "expires_at"),
            "stores": {
                "website_name": name,
                "slug":         slug,
                "logo_url":     logo,
            },
        })

    return latest


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Hugo content/stores/*.md + data JSON files from CSV."
    )
    parser.add_argument("--root",        default=".",  help="Hugo project root")
    parser.add_argument("--stores-csv",  default=None, help="Path to stores.csv")
    parser.add_argument("--coupons-csv", default=None, help="Path to coupons.csv")
    parser.add_argument("--out-dir",     default=None, help="Output dir for .md files")
    parser.add_argument("--data-dir",    default=None, help="Output dir for JSON data files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    root             = Path(args.root).resolve()
    stores_csv_path  = Path(args.stores_csv)  if args.stores_csv  else root / "scripts" / "data" / "stores.csv"
    coupons_csv_path = Path(args.coupons_csv) if args.coupons_csv else root / "scripts" / "data" / "coupons.csv"
    out_dir          = Path(args.out_dir)      if args.out_dir     else root / "content" / "stores"
    data_dir         = Path(args.data_dir)     if args.data_dir    else root / "data"

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = []
    if not stores_csv_path.exists():
        errors.append(f"  ✗ stores.csv not found at: {stores_csv_path}")
    if not coupons_csv_path.exists():
        errors.append(f"  ✗ coupons.csv not found at: {coupons_csv_path}")
    if errors:
        print("❌ Missing required files:\n" + "\n".join(errors))
        sys.exit(1)

    # ── Read ──────────────────────────────────────────────────────────────────
    stores  = read_csv(stores_csv_path)
    coupons = read_csv(coupons_csv_path)
    print(f"📦 {len(stores)} stores | 🎫 {len(coupons)} coupons")

    # ── Group coupons by raw store_id (e.g. "1", "4", "10") ──────────────────
    coupons_by_store_id: dict = defaultdict(list)
    for coupon in coupons:
        sid = pick(coupon, "store_id", "storeId")
        if sid:
            coupons_by_store_id[sid].append(coupon)

    # ── Build stores lookup by raw store_id ───────────────────────────────────
    stores_by_raw_id: dict = {}
    for store in stores:
        name   = pick(store, "website_name", "store_name", "name")
        slug   = pick(store, "slug", "store_slug", "id", "store_id") or slugify(name)
        raw_id = pick(store, "store_id", "id") or slug
        store["slug"] = slug          # cache resolved slug back onto row
        stores_by_raw_id[raw_id] = store

    # ── 1. Write content/stores/<slug>.md ─────────────────────────────────────
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for store in stores:
        name   = pick(store, "website_name", "store_name", "name")
        slug   = store.get("slug") or slugify(name)
        raw_id = pick(store, "store_id", "id") or slug

        if not slug:
            print(f"  ⚠️  Skipping row with no slug or name: {store}")
            skipped += 1
            continue

        store_coupons = coupons_by_store_id.get(raw_id, [])
        md_path = out_dir / f"{slug}.md"
        md_text = build_markdown(store, store_coupons)

        if args.dry_run:
            print(f"[DRY RUN] → {md_path}  ({len(store_coupons)} coupons)")
        else:
            md_path.write_text(md_text, encoding="utf-8")
            written += 1

    # ── 2. Write data/featured_stores.json ────────────────────────────────────
    featured      = build_featured_stores(stores, coupons_by_store_id)
    featured_path = data_dir / "featured_stores.json"

    if args.dry_run:
        print(f"\n[DRY RUN] → {featured_path}  ({len(featured)} featured stores)")
        for s in featured:
            print(f"           ⭐ {s['website_name']} ({s['slug']}) — {s['coupon_count']} coupons")
    else:
        data_dir.mkdir(parents=True, exist_ok=True)
        featured_path.write_text(json.dumps(featured, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"⭐  {len(featured)} featured stores → {featured_path}")

    # ── 3. Write data/latest_coupons.json ─────────────────────────────────────
    latest      = build_latest_coupons(coupons, stores_by_raw_id, limit=12)
    latest_path = data_dir / "latest_coupons.json"

    if args.dry_run:
        print(f"\n[DRY RUN] → {latest_path}  ({len(latest)} latest coupons)")
        for c in latest:
            print(f"           🎫 [{c['stores']['website_name']}] {c['coupon_title']}")
    else:
        latest_path.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"🎫  {len(latest)} latest coupons  → {latest_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    if not args.dry_run:
        if skipped:
            print(f"⚠️  Skipped {skipped} row(s) with no slug.")
        print(f"\n✅ {written} .md files  → {out_dir}")
        print("✨ Done! Run: hugo server")
    else:
        print(f"\n[DRY RUN] Would write {len(stores) - skipped} .md files to {out_dir}")


if __name__ == "__main__":
    main()