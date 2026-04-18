#!/bin/bash
# ============================================================
# scripts/copy-static.sh
# Runs after Hugo build — writes robots.txt and sitemap.xml
# into every store subfolder inside /public
# ============================================================

PUBLIC_DIR="./public"
BASE_DOMAIN="couponhauls.com"

# ── Non-store folders to skip ────────────────────────────────
SKIP_FOLDERS=(
  "stores"
  "blog"
  "css"
  "js"
  "images"
  "fonts"
  "about"
  "contact"
  "privacy"
  "affiliate-disclaimer"
  "page"
  "tags"
  "categories"
)

# ── Check public folder exists ───────────────────────────────
if [ ! -d "$PUBLIC_DIR" ]; then
  echo ""
  echo "ERROR: $PUBLIC_DIR folder not found."
  echo "Run 'hugo --minify' first before this script."
  echo ""
  exit 1
fi

echo ""
echo "================================================"
echo "  Writing robots.txt + sitemap.xml to subfolders"
echo "================================================"

count=0
skipped=0

for dir in "$PUBLIC_DIR"/*/; do
  [ -d "$dir" ] || continue

  slug=$(basename "$dir")

  # Skip non-store folders
  skip=false
  for folder in "${SKIP_FOLDERS[@]}"; do
    if [[ "$slug" == "$folder" ]]; then
      skip=true
      break
    fi
  done

  if $skip; then
    echo "  — skipped: $slug"
    skipped=$((skipped + 1))
    continue
  fi

  # ── Write robots.txt ──────────────────────────────────────
  cat > "$dir/robots.txt" << EOF
User-agent: *
Allow: /

# Block search queries
Disallow: /stores/?q=

Sitemap: https://www.${BASE_DOMAIN}/sitemap.xml
EOF

  # ── Write sitemap.xml ─────────────────────────────────────
  cat > "$dir/sitemap.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://${slug}.${BASE_DOMAIN}/</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
EOF

  echo "  ✓ ${slug}.${BASE_DOMAIN}"
  count=$((count + 1))

done

echo "------------------------------------------------"
echo "  ✓ ${count} store folders updated"
echo "  — ${skipped} folders skipped"
echo "================================================"
echo ""