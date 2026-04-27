#!/bin/bash
# Retry failed photo slots with fallback queries. Deletes the stale file FIRST
# so its own hash isn't in the "used" set when scoring candidates.
set -uo pipefail
cd "$(dirname "$0")"
UA="JFK-Time-Machine/1.0 (nicholas@retvrn.world)"

md5sum_cmd() {
  if command -v md5 >/dev/null 2>&1; then md5 -q "$1"
  else md5sum "$1" | awk '{print $1}'
  fi
}

# Fallback query lists per failed index (colon-separated, after the leading "<idx>::")
JOBS=(
  "1::John F Kennedy boy:Kennedy children 1920:Joseph P Kennedy family children:Rose Kennedy with children:Kennedy family Brookline"
  "2::Kennedy family 1927:Kennedy family Bronxville:Joseph Kennedy children 1928:Kennedy family group photo"
  "4::John F Kennedy Harvard:John F Kennedy 1940 graduate:Kennedy Harvard yearbook:John F Kennedy student"
  "10::John F Kennedy Potsdam:John F Kennedy 1945:James Forrestal Kennedy Berlin:John F Kennedy postwar Europe"
  "11::John F Kennedy 1946 campaign:John F Kennedy 11th district:John F Kennedy Boston 1947:Kennedy Massachusetts House"
  "13::John F Kennedy 1953 senator:John F Kennedy Cabot Lodge:Kennedy Senate Massachusetts:Kennedy senator office"
  "15::John F Kennedy 1955:John F Kennedy hospital bed:Kennedy Jacqueline 1954:John F Kennedy Profiles in Courage writing"
  "18::John F Kennedy 1960 announcement:Kennedy senator caucus 1960:John F Kennedy 1960 candidate"
  "19::Kennedy West Virginia 1960 campaign:Kennedy coal mine 1960:Kennedy primary 1960 Charleston"
  "21::Kennedy victory 1960 Hyannis:John F Kennedy president elect 1960:Kennedy concession Nixon 1960"
  "31::John F Kennedy 1963 American University speech:Kennedy June 10 1963:Kennedy peace speech 1963"
)

# Delete stale files first
for j in "${JOBS[@]}"; do
  idx="${j%%:*}"
  rm -f "photos/${idx}.jpg"
done

USED=$(mktemp)
trap "rm -f $USED" EXIT
for f in photos/*.jpg; do
  md5sum_cmd "$f" >> "$USED"
done
echo "Seeded $(wc -l < $USED) existing hashes."
echo

for j in "${JOBS[@]}"; do
  idx="${j%%:*}"
  rest="${j#*::}"
  echo "── [$idx] ──"

  picked=""
  IFS=':' read -ra QS <<< "$rest"
  for q in "${QS[@]}"; do
    [ -z "$q" ] && continue
    printf "   %-55s " "$q"
    urls=$(curl -sGA "$UA" \
      --data-urlencode "srsearch=${q} filetype:bitmap" \
      "https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srlimit=10&format=json" \
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
    for url in $urls; do
      tmp=$(mktemp).jpg
      curl -sLA "$UA" --max-filesize 25000000 "$url" -o "$tmp" 2>/dev/null
      sz=$(stat -f%z "$tmp" 2>/dev/null || stat -c%s "$tmp" 2>/dev/null || echo 0)
      if [ "$sz" -gt 5000 ]; then
        hash=$(md5sum_cmd "$tmp")
        if ! grep -qx "$hash" "$USED"; then
          mv "$tmp" "photos/${idx}.jpg"
          echo "$hash" >> "$USED"
          picked=1
          echo "✓ OK"
          break 2
        fi
      fi
      rm -f "$tmp"
    done
    echo "no new"
  done
  [ -z "$picked" ] && echo "   ALL FAILED for $idx"
done

echo
echo "Final count: $(ls photos/*.jpg 2>/dev/null | wc -l)"
echo "Duplicate hashes:"
for f in photos/*.jpg; do md5sum_cmd "$f"; done | sort | uniq -c | awk '$1>1 {print}'
