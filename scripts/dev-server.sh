#!/bin/bash
# scripts/dev-server.sh
# Wrapper for `hugo server` that auto-detects GitHub Codespaces
# and configures --baseURL / --appendPort accordingly so store
# subdomain links resolve correctly through the forwarded domain.
#
# Falls back to plain `hugo server -D` for local machines and
# Firebase Studio / Cloud Workstations previews.

set -e

if [ -n "$CODESPACE_NAME" ]; then
  # Codespaces port-forwarding domain defaults to app.github.dev
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  BASE_URL="https://${CODESPACE_NAME}-1313.${DOMAIN}/"

  echo "🔧 Detected GitHub Codespaces"
  echo "   Using baseURL: ${BASE_URL}"
  echo "   ⚠️  Make sure port 1313 is set to 'Public' in the Ports tab,"
  echo "      or the forwarded URL will show a GitHub auth page instead of Hugo."
  echo ""

  exec hugo server --bind 0.0.0.0 -D \
    --baseURL "$BASE_URL" \
    --appendPort=false
else
  echo "🔧 Local/dev environment — using default baseURL (http://localhost:1313/)"
  exec hugo server -D
fi