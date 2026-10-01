#!/bin/sh
# check-release.sh — verify the built PRG matches the blessed binary.
#
# RELEASE.sha256 pins the sha256 of the PRG currently under play-test /
# shipped.  Run this after touching ANYTHING in the project:
#   PASS    = the binary is exactly the blessed one
#   DRIFT   = a rebuild changed the game — do not overwrite delivery
#             media or shipped files from a drifted build; acknowledge
#             the change by updating RELEASE.sha256 in the same commit
#
# Usage: tools/check-release.sh [path/to/dodge.prg]
#        (default: ../output/build/dodge.prg relative to this script)
set -e
cd "$(dirname "$0")/.."
prg="${1:-output/build/dodge.prg}"
want=$(grep -v '^#' RELEASE.sha256 | awk 'NF {print $1}')

if [ -z "$want" ]; then
    echo "check-release: FAIL — RELEASE.sha256 has no hash"
    exit 1
fi
if [ ! -f "$prg" ]; then
    echo "check-release: FAIL — $prg missing (blessed build not on disk)"
    exit 1
fi

got=$(sha256sum "$prg" | awk '{print $1}')
if [ "$got" = "$want" ]; then
    echo "check-release: PASS — $prg matches the blessed build"
    exit 0
fi

echo "check-release: DRIFT — $prg does NOT match the blessed build"
echo "  blessed: $want"
echo "  actual : $got"
echo "  Do not ship, overwrite delivery media, or re-capture manual"
echo "  assets from a drifted build.  If the change is intended,"
echo "  update RELEASE.sha256 in the same commit and say so."
exit 1
