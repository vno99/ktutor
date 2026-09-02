#!/usr/bin/env bash
#
# check-i18n.sh — fail if any hardcoded UI string is rendered from a component
#                  (i.e. text content that is NOT routed through next-intl).
#
# This is the enforcement of the design-system rule "no hardcoded strings"
# (docs/design-system.md § i18n). The check is intentionally conservative:
#   - We scan only files that produce user-facing text: components/*.tsx,
#     app/**/*.tsx (server components), and pages that we author.
#   - We look for the pattern `>Xxx<` where the content begins with a
#     capitalized word and contains at least one space (catches phrases,
#     ignores single words like "FR" inside a button).
#
# The script exits 0 when no offenders are found, 1 otherwise.
# In s11a, the home page is fully i18n-ised, so this script should exit 0.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAN_DIRS=("$ROOT_DIR/components" "$ROOT_DIR/app")

# Pattern: `>Capitalized word<` followed by a space and more text, ending
# with `<`. Matches typical French/English JSX text content.
# Accents (à-ÿ) cover French diacritics.
PATTERN='>[A-Z][a-zA-Zà-ÿ]{2,}[ a-zA-Zà-ÿ]*<'

found=0
for dir in "${SCAN_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    continue
  fi
  if grep -RInP --include='*.tsx' --include='*.ts' \
    --exclude-dir=node_modules --exclude-dir=.next \
    "$PATTERN" "$dir" >/tmp/check-i18n-hits 2>/dev/null; then
    if [[ -s /tmp/check-i18n-hits ]]; then
      echo "::error::Hardcoded UI strings found (must be routed through useTranslations):"
      cat /tmp/check-i18n-hits
      found=1
    fi
  fi
done

if [[ $found -eq 1 ]]; then
  echo
  echo "Fix: move the string into frontend/messages/{fr,en}.json under the appropriate namespace and call useTranslations('<ns>') in the component."
  exit 1
fi

echo "check-i18n: OK (no hardcoded UI strings detected)"
exit 0
