#!/bin/bash
# Fetch lead images for each JFK event from Wikipedia API.
# Downloads to ./photos/<index>.jpg matching the EVENTS array order in the HTML.

set -e
cd "$(dirname "$0")"
mkdir -p photos

TITLES=(
  "John_F._Kennedy_National_Historic_Site"
  "John_F._Kennedy"
  "Kennedy_family"
  "Choate_Rosemary_Hall"
  "John_F._Kennedy"
  "Joseph_P._Kennedy_Sr."
  "Why_England_Slept"
  "John_F._Kennedy_in_the_United_States_Navy"
  "PT-109"
  "Joseph_P._Kennedy_Jr."
  "John_F._Kennedy"
  "John_F._Kennedy"
  "John_F._Kennedy"
  "1952_United_States_Senate_election_in_Massachusetts"
  "Wedding_of_John_F._Kennedy_and_Jacqueline_Bouvier"
  "John_F._Kennedy"
  "Profiles_in_Courage"
  "Caroline_Kennedy"
  "1960_United_States_presidential_election"
  "1960_Democratic_Party_presidential_primaries"
  "Kennedy%E2%80%93Nixon_debates"
  "1960_United_States_presidential_election"
  "John_F._Kennedy_Jr."
  "Inauguration_of_John_F._Kennedy"
  "Bay_of_Pigs_Invasion"
  "We_choose_to_go_to_the_Moon"
  "Vienna_summit"
  "Berlin_Wall"
  "Mercury-Atlas_6"
  "Ole_Miss_riot_of_1962"
  "Cuban_Missile_Crisis"
  "American_University_speech"
  "Report_to_the_American_People_on_Civil_Rights"
  "Ich_bin_ein_Berliner"
  "Patrick_Bouvier_Kennedy"
  "March_on_Washington_for_Jobs_and_Freedom"
  "Partial_Nuclear_Test_Ban_Treaty"
  "Assassination_of_John_F._Kennedy"
  "State_funeral_of_John_F._Kennedy"
)

UA="JFK-Time-Machine/1.0 (https://example.com; nicholas@retvrn.world)"

for i in "${!TITLES[@]}"; do
  title="${TITLES[$i]}"
  printf "[%2d] %-60s ... " "$i" "$title"
  url=$(curl -sA "$UA" "https://en.wikipedia.org/w/api.php?action=query&titles=${title}&prop=pageimages&piprop=original&format=json" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    pages = d.get('query',{}).get('pages',{})
    for p in pages.values():
        orig = p.get('original')
        if orig and 'source' in orig:
            print(orig['source'])
        else:
            print('')
        break
except Exception as e:
    print('')
")
  if [ -n "$url" ]; then
    curl -sLA "$UA" "$url" -o "photos/${i}.jpg"
    sz=$(stat -f%z "photos/${i}.jpg" 2>/dev/null || stat -c%s "photos/${i}.jpg")
    if [ "$sz" -gt 2000 ]; then
      echo "ok ($sz bytes)"
    else
      echo "FAILED (small file $sz)"
      rm -f "photos/${i}.jpg"
    fi
  else
    echo "no image"
  fi
done

echo
echo "Photos in ./photos:"
ls -1 photos/ | wc -l
