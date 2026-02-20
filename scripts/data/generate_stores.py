#!/usr/bin/env python3
"""
generate_stores.py
──────────────────
Reads scripts/data/stores.csv and scripts/data/coupons.csv and generates
content/stores/<slug>.md files with ALL coupon data embedded directly
in the front matter — no JSON data files needed.

Usage (run from Hugo project root):
    python3 scripts/data/generate_stores.py
    python3 scripts/data/generate_stores.py --dry-run
    python3 scripts/data/generate_stores.py --root /path/to/hugo
"""

import argparse
import csv
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
    """Escape double-quotes for YAML double-quoted scalars."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def bool_field(value: str) -> str:
    return "true" if str(value).strip().lower() in {"true", "1", "yes"} else "false"


def read_csv(path: Path) -> list[dict]:
    """Read CSV trying multiple encodings (handles Windows-saved files)."""
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

def build_markdown(store: dict, coupons: list[dict]) -> str:
    """Build a .md file with store metadata + all coupons in the front matter."""
    name     = pick(store, "website_name", "store_name", "name")
    slug     = pick(store, "slug", "store_slug", "id", "store_id") or slugify(name)
    desc     = pick(store, "website_desc", "store_description", "description")
    logo     = pick(store, "logo_url", "store_logo_url")
    url      = pick(store, "website_url", "store_url")
    aff_url  = pick(store, "website_aff_url", "store_aff_url") or url
    active   = bool_field(pick(store, "is_active",       "store_active",   fallback="true"))
    featured = bool_field(pick(store, "website_featured", "store_featured", fallback="false"))
    count    = len(coupons)

    # ── Store front matter ────────────────────────────────────────────────────
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

    # ── Embed coupons as a YAML list ──────────────────────────────────────────
    if coupons:
        lines.append("coupons:")
        for c in coupons:
            lines.append("  - coupon_id: \""      + safe_yaml(pick(c, "coupon_id"))          + "\"")
            lines.append("    coupon_title: \""    + safe_yaml(pick(c, "coupon_title"))       + "\"")
            lines.append("    coupon_code: \""     + safe_yaml(pick(c, "coupon_code"))        + "\"")
            lines.append("    coupon_description: \"" + safe_yaml(pick(c, "coupon_description")) + "\"")
            lines.append("    coupon_aff_url: \""  + safe_yaml(pick(c, "coupon_aff_url"))     + "\"")
            lines.append("    coupon_type: \""     + safe_yaml(pick(c, "coupon_type", fallback="Deal")) + "\"")
            lines.append("    coupon_start: \""    + safe_yaml(pick(c, "coupon_start"))       + "\"")
            lines.append("    expires_at: \""      + safe_yaml(pick(c, "coupon_expired", "expires_at")) + "\"")
    else:
        lines.append("coupons: []")

    lines.append("---")
    lines.append("")
    if desc:
        lines.append(desc)
        lines.append("")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Hugo content/stores/*.md files from CSV — no JSON needed."
    )
    parser.add_argument("--root",        default=".",  help="Hugo project root")
    parser.add_argument("--stores-csv",  default=None, help="Path to stores.csv")
    parser.add_argument("--coupons-csv", default=None, help="Path to coupons.csv")
    parser.add_argument("--out-dir",     default=None, help="Output dir for .md files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    root             = Path(args.root).resolve()
    stores_csv_path  = Path(args.stores_csv)  if args.stores_csv  else root / "scripts" / "data" / "stores.csv"
    coupons_csv_path = Path(args.coupons_csv) if args.coupons_csv else root / "scripts" / "data" / "coupons.csv"
    out_dir          = Path(args.out_dir)      if args.out_dir     else root / "content" / "stores"

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

    # ── Group coupons by store_id ─────────────────────────────────────────────
    coupons_by_store: dict[str, list] = defaultdict(list)
    for coupon in coupons:
        sid = pick(coupon, "store_id", "storeId", "store_slug")
        if sid:
            coupons_by_store[sid].append(coupon)

    # ── Write .md files ───────────────────────────────────────────────────────
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for store in stores:
        name = pick(store, "website_name", "store_name", "name")
        slug = pick(store, "slug", "store_slug", "id", "store_id")
        if not slug and name:
            slug = slugify(name)
        if not slug:
            print(f"  ⚠️  Skipping row with no slug or name: {store}")
            skipped += 1
            continue

        store["slug"] = slug
        sid = pick(store, "store_id", "id") or slug
        store_coupons = coupons_by_store.get(sid, [])

        md_path = out_dir / f"{slug}.md"
        md_text = build_markdown(store, store_coupons)

        if args.dry_run:
            print(f"[DRY RUN] → {md_path}  ({len(store_coupons)} coupons)")
            print(md_text[:300], "...\n")
        else:
            md_path.write_text(md_text, encoding="utf-8")
            written += 1

    if not args.dry_run:
        if skipped:
            print(f"⚠️  Skipped {skipped} row(s) with no slug.")
        print(f"\n✅ {written} .md files written to: {out_dir}")
        print("✨ Done! Run: hugo server")
    else:
        print(f"\n[DRY RUN] Would write {len(stores) - skipped} .md files to {out_dir}")


if __name__ == "__main__":
    main()