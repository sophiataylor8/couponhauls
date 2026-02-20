#!/usr/bin/env python3
"""
generate_stores.py
──────────────────
Reads data/stores.csv and data/coupons.csv and generates individual
Markdown files inside content/stores/ for a Hugo static site.

Usage:
    python3 generate_stores.py                        # run from project root
    python3 generate_stores.py --root /path/to/hugo   # explicit root
    python3 generate_stores.py --dry-run              # preview without writing

Supported CSV column names
──────────────────────────
stores.csv  : store_id / id
              store_slug / slug
              store_name / website_name / name
              store_description / website_desc / description
              store_logo_url / logo_url
              store_url / website_url
              store_aff_url / website_aff_url
              store_active / is_active
              store_featured / website_featured

coupons.csv : store_id / storeId / store_slug
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert any string into a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def safe_yaml(value: str) -> str:
    """Escape double-quotes so the string is safe inside YAML double-quoted scalars."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def bool_field(value: str) -> str:
    """Normalise CSV boolean-ish strings to YAML true/false."""
    return "true" if str(value).strip().lower() in {"true", "1", "yes"} else "false"


def read_csv(path: Path) -> list[dict]:
    """Read a CSV file and return a list of row dicts."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


_INVALID_VALUES = {"undefined", "null", "none", "n/a", ""}

def pick(row: dict, *keys: str, fallback: str = "") -> str:
    """Return the first non-empty, non-placeholder value found among the given keys."""
    for key in keys:
        val = (row.get(key) or "").strip()
        if val.lower() not in _INVALID_VALUES:
            return val
    return fallback


# ── Markdown builder ──────────────────────────────────────────────────────────

def build_markdown(store: dict) -> str:
    """Return the full Markdown string for one store page."""
    name     = pick(store, "website_name", "store_name", "name")
    slug     = pick(store, "slug", "store_slug", "id", "store_id") or slugify(name)
    desc     = pick(store, "website_desc", "store_description", "description")
    logo     = pick(store, "logo_url", "store_logo_url")
    url      = pick(store, "website_url", "store_url")
    aff_url  = pick(store, "website_aff_url", "store_aff_url") or url
    active   = bool_field(pick(store, "is_active", "store_active", fallback="true"))
    featured = bool_field(pick(store, "website_featured", "store_featured", fallback="false"))
    count    = int(store.get("coupon_count", 0))

    front_matter = f"""\
---
title: "{safe_yaml(name)}"
slug: "{safe_yaml(slug)}"
description: "{safe_yaml(desc)}"
logo_url: "{safe_yaml(logo)}"
website_url: "{safe_yaml(url)}"
website_aff_url: "{safe_yaml(aff_url)}"
is_active: {active}
website_featured: {featured}
coupon_count: {count}
store_id: "{safe_yaml(slug)}"
---
"""
    body = f"\n{desc}\n" if desc else ""
    return front_matter + body


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Hugo content/stores/*.md files from CSV data."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Path to the Hugo project root (default: current directory)",
    )
    parser.add_argument(
        "--stores-csv",
        default=None,
        help="Path to stores.csv (default: <root>/data/stores.csv)",
    )
    parser.add_argument(
        "--coupons-csv",
        default=None,
        help="Path to coupons.csv (default: <root>/data/coupons.csv)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for .md files (default: <root>/content/stores)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without creating any files",
    )
    args = parser.parse_args()

    root             = Path(args.root).resolve()
    stores_csv_path  = Path(args.stores_csv)  if args.stores_csv  else root / "data" / "stores.csv"
    coupons_csv_path = Path(args.coupons_csv) if args.coupons_csv else root / "data" / "coupons.csv"
    out_dir          = Path(args.out_dir)      if args.out_dir     else root / "content" / "stores"

    # ── Validate inputs ───────────────────────────────────────────────────────
    errors = []
    if not stores_csv_path.exists():
        errors.append(f"  ✗ stores.csv not found at: {stores_csv_path}")
    if not coupons_csv_path.exists():
        errors.append(f"  ✗ coupons.csv not found at: {coupons_csv_path}")
    if errors:
        print("❌ Missing required files:")
        print("\n".join(errors))
        print("\nRun from your Hugo project root, or pass --root /path/to/project")
        print("Expected locations: data/stores.csv and data/coupons.csv")
        sys.exit(1)

    # ── Read data ─────────────────────────────────────────────────────────────
    stores  = read_csv(stores_csv_path)
    coupons = read_csv(coupons_csv_path)
    print(f"📦 {len(stores)} stores | 🎫 {len(coupons)} coupons")

    # ── Count coupons per store ───────────────────────────────────────────────
    coupon_counts: dict[str, int] = defaultdict(int)
    for coupon in coupons:
        sid = pick(coupon, "store_id", "storeId", "store_slug")
        if sid:
            coupon_counts[sid] += 1

    # ── Enrich stores ─────────────────────────────────────────────────────────
    skipped = []
    enriched_stores = []
    for store in stores:
        name = pick(store, "website_name", "store_name", "name")
        slug = pick(store, "slug", "store_slug", "id", "store_id")

        if not slug and name:
            slug = slugify(name)

        if not slug:
            skipped.append(store)
            print(f"  ⚠️  Skipping row with no slug or name: {store}")
            continue

        store["slug"] = slug
        sid = pick(store, "store_id", "id") or slug
        store["coupon_count"] = coupon_counts.get(sid, coupon_counts.get(slug, 0))
        enriched_stores.append(store)

    if skipped:
        print(f"\n⚠️  Skipped {len(skipped)} row(s) with no resolvable slug.\n")

    # ── Write .md files ───────────────────────────────────────────────────────
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for store in enriched_stores:
        slug    = store["slug"]
        md_path = out_dir / f"{slug}.md"
        md_text = build_markdown(store)

        if args.dry_run:
            print(f"── [DRY RUN] Would write: {md_path}")
            print(md_text)
            print()
        else:
            md_path.write_text(md_text, encoding="utf-8")
            written += 1

    if not args.dry_run:
        print(f"\n✅ {written} store .md files written to: {out_dir}")
        print("\n✨ Done! Run: hugo server")
    else:
        print(f"\n[DRY RUN] Would write {len(enriched_stores)} .md files to {out_dir}")


if __name__ == "__main__":
    main()