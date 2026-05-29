#!/bin/bash
# scripts/copy-static.sh
# Writes robots.txt and sitemap.xml into every store subdomain folder

PUBLIC_DIR="./public"
BASE_DOMAIN="couponhauls.com"

SKIP_FOLDERS=(
  "stores" "blog" "css" "js" "images" "fonts"
  "about" "contact" "privacy" "affiliate-disclaimer"
  "page" "tags" "categories"
)

if [ ! -d "$PUBLIC_DIR" ]; then
  echo "ERROR: $PUBLIC_DIR not found. Run hugo first."
  exit 1
fi

echo "Writing robots.txt + sitemap.xml to store subfolders..."

count=0
skipped=0

for dir in "$PUBLIC_DIR"/*/; do
  [ -d "$dir" ] || continue
  slug=$(basename "$dir")

  skip=false
  for folder in "${SKIP_FOLDERS[@]}"; do
    if [[ "$slug" == "$folder" ]]; then
      skip=true
      break
    fi
  done

  if $skip; then
    skipped=$((skipped + 1))
    continue
  fi

  # ── robots.txt — reference BOTH subdomain and main sitemaps ──────────────
  cat > "$dir/robots.txt" << EOF
User-agent: *
Allow: /

Sitemap: https://${slug}.${BASE_DOMAIN}/sitemap.xml
Sitemap: https://www.${BASE_DOMAIN}/sitemap.xml
EOF

  # ── sitemap.xml — only the canonical subdomain URL ───────────────────────
  cat > "$dir/sitemap.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://${slug}.${BASE_DOMAIN}/</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
    <lastmod>$(date +%Y-%m-%d)</lastmod>
  </url>
</urlset>
EOF

  echo "  ✓ ${slug}.${BASE_DOMAIN}"
  count=$((count + 1))
done

echo "Done: ${count} stores updated, ${skipped} skipped."