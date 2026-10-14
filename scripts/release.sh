#!/usr/bin/env bash
# 사용법: scripts/release.sh YYYYMMDD [YYYYMMDD ...]
# 각 날짜의 리포트를 GitHub Release(daily-YYYYMMDD)로 만들거나 갱신한다. GH_TOKEN 필요.
set -euo pipefail

LATEST=$(ls data/top10/*.json | sort | tail -1 | xargs basename | cut -d. -f1)

for DATE in "$@"; do
  python -m mymoney notes --date "$DATE" --out notes.md >/dev/null
  TAG="daily-$DATE"
  TITLE="📊 ${DATE:0:4}-${DATE:4:2}-${DATE:6:2} TOP10"
  ASSET="top10-$DATE.json"
  cp "data/top10/$DATE.json" "$ASSET"
  if [ "$DATE" = "$LATEST" ]; then FLAG="--latest"; else FLAG="--latest=false"; fi
  if gh release view "$TAG" >/dev/null 2>&1; then
    gh release edit "$TAG" --title "$TITLE" --notes-file notes.md $FLAG >/dev/null
    gh release upload "$TAG" "$ASSET" --clobber
  else
    gh release create "$TAG" "$ASSET" --target main --title "$TITLE" --notes-file notes.md $FLAG >/dev/null
  fi
  rm -f "$ASSET"
  echo "release: $TAG"
done
rm -f notes.md
