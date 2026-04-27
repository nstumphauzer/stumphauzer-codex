#!/bin/bash
# Replace missing/duplicated photos with unique relevant images via Wikimedia Commons file search.
# Tracks md5 hashes of currently-saved photos so a new fetch never matches an already-used image.

set -uo pipefail
cd "$(dirname "$0")"
UA="JFK-Time-Machine/1.0 (nicholas@retvrn.world)"

md5sum_cmd() {
  if command -v md5 >/dev/null 2>&1; then md5 -q "$1"
  else md5sum "$1" | awk '{print $1}'
  fi
}

# Per-index queries — most specific first
declare -a JOBS=(
  "0|John F Kennedy birthplace Brookline 83 Beals Street"
  "1|John F Kennedy child Hyannis Port 1920"
  "2|Kennedy family Bronxville 1927"
  "3|John F Kennedy Choate school"
  "4|John F Kennedy Harvard student 1939"
  "5|Joseph P Kennedy Sr ambassador London"
  "7|John F Kennedy Navy uniform 1942"
  "8|USS PT-109 Kennedy Solomon Islands"
  "10|John F Kennedy 1945 Berlin Hearst"
  "11|John F Kennedy congressman 1947 Capitol"
  "12|John F Kennedy 1948 representative"
  "13|John F Kennedy Senate portrait 1953"
  "14|John F Kennedy Jacqueline wedding 1953 Newport"
  "15|John F Kennedy crutches back surgery"
  "18|John F Kennedy announce candidacy 1960 caucus"
  "19|John F Kennedy West Virginia primary 1960 coal miners"
  "21|John F Kennedy president-elect Hyannis November 1960"
  "25|Kennedy Rice University moon speech 1962"
  "26|Kennedy Khrushchev Vienna summit 1961"
  "31|Kennedy American University commencement speech 1963"
  "32|Kennedy Civil Rights Address Oval Office June 1963"
  "35|March on Washington Jobs Freedom 1963 King"
)

USED=$(mktemp)
trap "rm -f $USED" EXIT

# Seed used hashes from EXISTING photos (excluding the ones we're about to replace)
declare -A REPLACE_IDX=()
for j in "${JOBS[@]}"; do
  i="${j%%|*}"; REPLACE_IDX[$i]=1
done
for f in photos/*.jpg; do
  [ -f "$f" ] || continue
  base=$(basename "$f" .jpg)
  if [ -z "${REPLACE_IDX[$base]:-}" ]; then
    md5sum_cmd "$f" >> "$USED"
  fi
done
echo "Seeded $(wc -l < $USED) existing hashes."

for j in "${JOBS[@]}"; do
  idx="${j%%|*}"
  q="${j#*|}"
  printf "[%2s] %-60s ... " "$idx" "$q"

  # Search Commons for top hits
  urls=$(curl -sGA "$UA" \
    --data-urlencode "srsearch=${q} filetype:bitmap" \
    "https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srlimit=8&format=json" \
    | python3 -c "
import json, sys, urllib.parse
try:
  d = json.load(sys.stdin)
  for h in d.get('query', {}).get('search', []):
    fname = h['title'].replace('File:', '')
    if fname.lower().endswith(('.jpg','.jpeg','.png','.tif','.tiff')):
      print('https://commons.wikimedia.org/wiki/Special:FilePath/' + urllib.parse.quote(fname))
except: pass
")

  picked=""
  for url in $urls; do
    tmp=$(mktemp).jpg
    curl -sLA "$UA" --max-filesize 25000000 "$url" -o "$tmp"
    sz=$(stat -f%z "$tmp" 2>/dev/null || stat -c%s "$tmp" 2>/dev/null || echo 0)
    if [ "$sz" -gt 5000 ]; then
      hash=$(md5sum_cmd "$tmp")
      if ! grep -qx "$hash" "$USED"; then
        mv "$tmp" "photos/${idx}.jpg"
        echo "$hash" >> "$USED"
        picked="$url"
        break
      fi
    fi
    rm -f "$tmp"
  done

  if [ -n "$picked" ]; then
    echo "ok"
  else
    echo "FAILED"
  fi
done

echo
echo "Final photo count: $(ls photos/*.jpg 2>/dev/null | wc -l)"
echo "Duplicates remaining (should be empty):"
for f in photos/*.jpg; do md5sum_cmd "$f"; done | sort | uniq -c | awk '$1>1 {print}'
