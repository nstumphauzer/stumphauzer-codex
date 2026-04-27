#!/usr/bin/env python3
"""
v2 — Relevance-scored photo picker.

For each event index we collect candidates from multiple sources (Wikipedia
article lead images, Commons categories, Commons searches) and score them.
Higher score = more likely to be a contemporaneous, on-topic photo.
"""

import json, sys, urllib.request, urllib.parse, hashlib, subprocess, re
from pathlib import Path

UA = "JFK-Time-Machine/1.0 (nicholas@retvrn.world)"
PHOTOS_DIR = Path(__file__).parent / "jfk" / "photos"
PHOTOS_DIR.mkdir(exist_ok=True)

CWAPI = "https://commons.wikimedia.org/w/api.php"
WPAPI = "https://en.wikipedia.org/w/api.php"

# ── Per-event sources + scoring keywords ────────────────────────────────────
# article: Wikipedia article whose lead image to try first
# cats:    Commons categories to scan
# searches: free-text Commons file searches
# year:    the year that should appear in good filenames (huge score boost)
# keywords: event-specific tokens that ID a relevant photo (boost)
EVENTS = [
    # 0: Born May 29, 1917 — Brookline
    dict(year="1917", article="John F. Kennedy National Historic Site",
         cats=["Category:John F. Kennedy National Historic Site",
               "Category:John F. Kennedy as a child",
               "Category:Childhood of John F. Kennedy"],
         searches=["JFK birthplace Brookline house", "Kennedy 83 Beals Street", "John Kennedy infant"],
         keywords=["birthplace", "beals", "brookline", "house", "national_historic", "infant", "baby", "young"]),
    # 1: Scarlet fever 1920 — child portrait
    dict(year="1920", article=None,
         cats=["Category:John F. Kennedy as a child", "Category:Childhood of John F. Kennedy"],
         searches=["John F Kennedy as child", "Kennedy children 1920", "Kennedy boy young"],
         keywords=["young", "child", "boy", "rose", "infant"]),
    # 2: Riverdale 1927 — family
    dict(year="1927", article=None,
         cats=["Category:Kennedy family", "Category:John F. Kennedy as a child"],
         searches=["Kennedy family 1927", "Kennedy family group"],
         keywords=["family", "siblings", "joseph", "rose"]),
    # 3: Choate 1931
    dict(year="1931", article=None,
         cats=["Category:John F. Kennedy at Choate", "Category:Choate Rosemary Hall"],
         searches=["Kennedy Choate", "Choate Rosemary Hall students"],
         keywords=["choate", "school", "yearbook", "students", "campus"],
         must=["kennedy", "jfk", "choate"]),
    # 4: Harvard 1936
    dict(year="1939", article=None,
         cats=["Category:John F. Kennedy at Harvard University", "Category:John F. Kennedy in 1939", "Category:John F. Kennedy in 1940"],
         searches=["Kennedy Harvard student", "Kennedy 1939 Harvard"],
         keywords=["harvard", "student", "campus", "yearbook", "young"]),
    # 5: London 1938
    dict(year="1938", article="Joseph P. Kennedy Sr.",
         cats=["Category:Joseph P. Kennedy Sr.", "Category:Kennedy family"],
         searches=["Joseph Kennedy ambassador London 1938", "Kennedy ambassador embassy"],
         keywords=["ambassador", "london", "embassy", "joseph"]),
    # 6: Why England Slept 1940
    dict(year="1940", article="Why England Slept",
         cats=[],
         searches=["Why England Slept book cover"],
         keywords=["why_england", "slept", "book", "1940"],
         must=["england", "slept"]),
    # 7: Navy commission 1941
    dict(year="1941", article=None,
         cats=["Category:John F. Kennedy in 1941", "Category:John F. Kennedy in the United States Navy"],
         searches=["John F Kennedy Navy 1941 ensign", "Lt John F Kennedy Navy uniform"],
         keywords=["navy", "uniform", "lieutenant", "ensign", "naval", "1941"]),
    # 8: PT-109 Aug 2 1943
    dict(year="1943", article="PT-109",
         cats=["Category:John F. Kennedy in 1943", "Category:PT-109"],
         searches=["PT-109", "PT109 boat", "Lt John F Kennedy PT boat"],
         keywords=["pt-109", "pt_109", "pt109", "boat", "navy", "solomon", "lieutenant"]),
    # 9: Joe Jr KIA 1944
    dict(year="1944", article="Joseph P. Kennedy Jr.",
         cats=["Category:Joseph P. Kennedy Jr."],
         searches=["Joseph Kennedy Jr Navy", "Joe Kennedy Jr pilot"],
         keywords=["joseph", "kennedy jr", "navy", "pilot", "uniform"]),
    # 10: Hearst 1945 Berlin
    dict(year="1945", article=None,
         cats=["Category:John F. Kennedy in 1945"],
         searches=["John F Kennedy 1945", "Kennedy postwar Berlin 1945"],
         keywords=["1945", "kennedy"]),
    # 11: Congress 1946
    dict(year="1946", article=None,
         cats=["Category:John F. Kennedy in 1946", "Category:John F. Kennedy in 1947"],
         searches=["John F Kennedy 1946 candidate", "Kennedy Congress 1946"],
         keywords=["1946", "candidate", "congress", "campaign", "boston"]),
    # 12: Addison 1947
    dict(year="1947", article=None,
         cats=["Category:John F. Kennedy in 1947", "Category:John F. Kennedy in 1948"],
         searches=["John F Kennedy 1947 congressman", "Kennedy 1948 Capitol"],
         keywords=["1947", "1948", "congressman", "congress", "freshman", "house"]),
    # 13: Senate 1952
    dict(year="1952", article=None,
         cats=["Category:John F. Kennedy in 1952", "Category:John F. Kennedy in 1953"],
         searches=["John F Kennedy 1952 senate", "Kennedy senator 1953 portrait"],
         keywords=["1952", "1953", "senator", "senate"]),
    # 14: Wedding 1953
    dict(year="1953", article="Wedding of John F. Kennedy and Jacqueline Bouvier",
         cats=["Category:Wedding of John F. Kennedy and Jacqueline Bouvier"],
         searches=["John Jacqueline Kennedy wedding 1953", "JFK wedding Newport"],
         keywords=["wedding", "jacqueline", "bouvier", "newport"]),
    # 15: Surgery 1954-1955
    dict(year="1954", article=None,
         cats=["Category:John F. Kennedy in 1954", "Category:John F. Kennedy in 1955"],
         searches=["John F Kennedy 1955", "John F Kennedy 1954 senator"],
         keywords=["1954", "1955", "senator", "kennedy"]),
    # 16: Pulitzer 1957
    dict(year="1957", article="Profiles in Courage",
         cats=["Category:Profiles in Courage", "Category:John F. Kennedy in 1957"],
         searches=["Profiles in Courage book cover", "John F Kennedy 1957"],
         keywords=["profiles", "courage", "1957", "book"],
         must=["kennedy", "jfk", "profiles_in_courage", "profiles in courage", "courage"]),
    # 17: Caroline born Nov 1957
    dict(year="1957", article=None,
         cats=["Category:Caroline Kennedy as a child", "Category:John F. Kennedy in 1957", "Category:John F. Kennedy in 1958"],
         searches=["Caroline Kennedy 1958 child", "Caroline Kennedy baby Hyannis", "Kennedy daughter Caroline"],
         keywords=["caroline", "1958", "baby", "child", "infant", "1957"],
         must=["caroline", "kennedy_family", "kennedy_children", "jacqueline"]),
    # 18: Jan 1960 announce
    dict(year="1960", article=None,
         cats=["Category:John F. Kennedy in 1960"],
         searches=["John F Kennedy 1960 senate caucus", "Kennedy 1960 announce candidacy"],
         keywords=["1960", "candidate", "campaign", "senator", "caucus", "announce"]),
    # 19: WV primary May 1960
    dict(year="1960", article=None,
         cats=["Category:John F. Kennedy in 1960"],
         searches=["Kennedy West Virginia 1960 campaign", "Kennedy 1960 May primary rally"],
         keywords=["1960", "west_virginia", "primary", "rally", "campaign"]),
    # 20: Sept 1960 debate
    dict(year="1960", article="Kennedy–Nixon debates",
         cats=["Category:Kennedy–Nixon debates", "Category:John F. Kennedy in 1960"],
         searches=["Kennedy Nixon debate 1960", "Kennedy Nixon television debate"],
         keywords=["nixon", "debate", "1960", "television", "cbs"]),
    # 21: Nov 1960 elected
    dict(year="1960", article=None,
         cats=["Category:John F. Kennedy in 1960", "Category:1960 United States presidential election"],
         searches=["Kennedy victory 1960 Hyannis", "Kennedy president elect 1960"],
         keywords=["1960", "victory", "hyannis", "election", "president-elect", "press conference"]),
    # 22: John Jr born Nov 1960
    dict(year="1960", article=None,
         cats=["Category:John F. Kennedy Jr. as a child", "Category:John F. Kennedy in 1960", "Category:John F. Kennedy in 1961"],
         searches=["John F Kennedy Jr baby Hyannis", "John John Kennedy infant 1961"],
         keywords=["john jr", "baby", "infant", "1960", "1961", "child", "salute"]),
    # 23: Inauguration Jan 20 1961
    dict(year="1961", article="Inauguration of John F. Kennedy",
         cats=["Category:Inauguration of John F. Kennedy"],
         searches=["John F Kennedy inauguration 1961", "Kennedy oath inauguration"],
         keywords=["inauguration", "oath", "swearing", "capitol", "1961"]),
    # 24: Bay of Pigs Apr 17 1961
    dict(year="1961", article="Bay of Pigs Invasion",
         cats=["Category:Bay of Pigs Invasion"],
         searches=["Bay of Pigs invasion", "Brigade 2506"],
         keywords=["bay of pigs", "brigade", "2506", "cuba", "invasion", "playa", "giron"],
         must=["kennedy", "jfk", "pigs", "giron", "brigade", "2506", "playa"]),
    # 25: Moon speech May 25 1961
    dict(year="1961", article="We choose to go to the Moon",
         cats=["Category:John F. Kennedy in 1961"],
         searches=["Kennedy Congress 1961", "Kennedy joint session 1961"],
         keywords=["congress", "speech", "joint session", "rice", "1961"]),
    # 26: Vienna summit June 1961
    dict(year="1961", article="Vienna summit",
         cats=["Category:Vienna summit (1961)", "Category:John F. Kennedy in 1961"],
         searches=["Kennedy Khrushchev Vienna", "Vienna summit 1961"],
         keywords=["khrushchev", "vienna", "summit", "1961"]),
    # 27: Berlin Wall Aug 1961
    dict(year="1961", article="Berlin Wall",
         cats=["Category:Berlin Wall in 1961", "Category:Construction of the Berlin Wall"],
         searches=["Berlin Wall 1961 construction", "Berlin Wall barbed wire 1961"],
         keywords=["berlin wall", "1961", "construction", "barbed wire"],
         must=["berlin", "mauer"]),
    # 28: Glenn Feb 1962
    dict(year="1962", article="Mercury-Atlas 6",
         cats=["Category:Mercury-Atlas 6"],
         searches=["Friendship 7 John Glenn", "Mercury Atlas 6 launch"],
         keywords=["friendship", "mercury", "atlas", "glenn", "1962", "launch"],
         must=["mercury", "atlas", "glenn", "friendship", "ma6", "ma-6"]),
    # 29: Ole Miss riot Sep 1962
    dict(year="1962", article="Ole Miss riot of 1962",
         cats=["Category:Ole Miss riot of 1962", "Category:James Meredith"],
         searches=["Ole Miss riot 1962", "James Meredith Ole Miss"],
         keywords=["ole miss", "meredith", "1962", "riot", "marshals", "oxford"],
         must=["kennedy", "meredith", "ole_miss", "olemiss", "ole miss", "marshals", "oxford"]),
    # 30: Cuban Missile Crisis Oct 1962
    dict(year="1962", article=None,
         cats=["Category:Cuban Missile Crisis", "Category:John F. Kennedy in 1962"],
         searches=["Kennedy ExComm October 1962", "Kennedy address Cuban missile"],
         keywords=["missile_crisis", "missile", "u-2", "cuba", "cuban", "1962", "khrushchev", "excomm", "address"],
         must=["kennedy", "missile", "cuba", "cuban", "khrushchev", "excomm"]),
    # 31: Peace Speech June 10 1963
    dict(year="1963", article="American University speech",
         cats=["Category:John F. Kennedy in 1963"],
         searches=["John F Kennedy American University 1963", "Kennedy peace speech June 1963"],
         keywords=["american university", "1963", "june", "peace", "commencement"]),
    # 32: Civil Rights Address June 11 1963
    dict(year="1963", article="Report to the American People on Civil Rights",
         cats=["Category:John F. Kennedy in 1963"],
         searches=["Kennedy civil rights address 1963", "Kennedy oval office June 1963"],
         keywords=["civil rights", "oval office", "1963", "june", "address"]),
    # 33: Berlin June 26 1963
    dict(year="1963", article=None,
         cats=["Category:John F. Kennedy in 1963"],
         searches=["Bundesarchiv Kennedy Berlin", "Kennedy Schöneberg 1963", "Kennedy West Berlin 1963"],
         keywords=["berlin", "1963", "bundesarchiv", "ich bin", "rathaus", "brandt", "schöneberg"],
         must=["kennedy", "berlin", "bundesarchiv", "schöneberg", "schoneberg", "rathaus", "tegel", "brandt"]),
    # 34: Patrick dies Aug 9 1963
    dict(year="1963", article="Patrick Bouvier Kennedy",
         cats=["Category:Patrick Bouvier Kennedy"],
         searches=["Patrick Bouvier Kennedy 1963", "Jacqueline Kennedy 1963 hospital"],
         keywords=["patrick", "1963", "jacqueline"]),
    # 35: March on Washington Aug 28 1963
    dict(year="1963", article="March on Washington for Jobs and Freedom",
         cats=["Category:March on Washington for Jobs and Freedom"],
         searches=["March on Washington 1963", "Civil Rights March Washington 1963 Lincoln"],
         keywords=["march", "washington", "1963", "lincoln", "king"],
         must=["march_on_washington", "march on washington", "civil_rights_march", "rustin", "kennedy", "king"]),
    # 36: Test Ban Treaty Oct 7 1963
    dict(year="1963", article=None,
         cats=["Category:Partial Nuclear Test Ban Treaty", "Category:John F. Kennedy in 1963"],
         searches=["Kennedy Test Ban Treaty signing 1963", "Test Ban Treaty signing East Room"],
         keywords=["test_ban", "treaty", "1963", "signing", "harriman", "east room"],
         must=["kennedy", "jfk", "test_ban", "test ban", "treaty"]),
    # 37: Assassination Nov 22 1963
    dict(year="1963", article="Assassination of John F. Kennedy",
         cats=["Category:Assassination of John F. Kennedy", "Category:John F. Kennedy in Dallas"],
         searches=["John F Kennedy Dallas 1963 motorcade", "Kennedy assassination Dallas 1963"],
         keywords=["dallas", "motorcade", "1963", "limousine", "lincoln", "dealey"]),
    # 38: State funeral Nov 25 1963
    dict(year="1963", article="State funeral of John F. Kennedy",
         cats=["Category:State funeral of John F. Kennedy"],
         searches=["John F Kennedy funeral 1963", "Kennedy caisson Arlington 1963"],
         keywords=["funeral", "caisson", "arlington", "1963", "procession"]),
]

# Filename substrings that disqualify or heavily penalize a candidate
NEGATIVE = {
    -2000: ['.svg', '.ogg', '.ogv', '.webm', '.pdf', '.gif', '.tif', '.tiff'],
    -1500: ['memorial', 'museum', 'plaque', 'reenact', 're-enact', 'tribute', 'monument',
            'commemorat', 'anniversary', 'jfk_forum', 'jfk forum', 'kennedy_school',
            'kennedy school', 'library exhibit', 'pacific_partnership',
            'performing arts', 'performing_arts', 'gala opening',
            'pacific partnership', 'biden', 'obama', 'trump', 'ancexplorer',
            'grave', 'tombstone', 'headstone', 'eternal flame', 'cemetery',
            'svg.png', 'electoralcollege', 'electoral_map', 'electoral_college',
            'ambassador_to_', '_ambassador_2', 'us_ambassador', 'as_us', 'as_ambassador',
            'sandgate', 'brisbane', 'queensland', 'statelibqld', 'australia',
            'silver pitcher', 'silver_pitcher'],
    -800:  ['brochure', 'pamphlet', 'poster', 'campaign_brochure'],
    -500:  ['stamp', 'coin', 'medal', 'currency', 'document', 'letter', 'manuscript',
            'citation', 'memo', 'telegram', 'invitation_card', '_map_of', '_map.',
            'participation', '_logo', '_seal'],
    -300:  ['painting', 'portrait_painting', 'illustration', 'sketch', 'drawing'],
    -100:  ['signature', 'autograph', 'first_day_cover', 'firstday'],
}

POSITIVE_PREFIXES = ['jfkwhp-', 'arc', 'bundesarchiv']  # archival sources

# Years that signal a MODERN photo (decades after JFK era)
LATE_YEAR_RE = re.compile(r'\b(19[89]\d|20\d{2})\b')

def is_image_ext(fn):
    return fn.lower().endswith(('.jpg', '.jpeg', '.png'))

def http_json(api, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(api + "?" + qs, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def list_category_files(cat, limit=80):
    files = []
    try:
        d = http_json(CWAPI, {"action": "query", "list": "categorymembers",
                              "cmtitle": cat, "cmtype": "file|subcat",
                              "cmlimit": str(limit), "format": "json"})
        for m in d.get('query', {}).get('categorymembers', []):
            if m['title'].startswith('File:'):
                files.append(m['title'][5:])
            elif m['title'].startswith('Category:') and len(files) < limit:
                try:
                    sub = http_json(CWAPI, {"action": "query", "list": "categorymembers",
                                            "cmtitle": m['title'], "cmtype": "file",
                                            "cmlimit": "30", "format": "json"})
                    for sm in sub.get('query', {}).get('categorymembers', []):
                        if sm['title'].startswith('File:'):
                            files.append(sm['title'][5:])
                except Exception: pass
    except Exception: pass
    return files

def search_files(q, limit=15):
    try:
        d = http_json(CWAPI, {"action": "query", "list": "search",
                              "srsearch": f"{q} filetype:bitmap",
                              "srnamespace": "6", "srlimit": str(limit),
                              "format": "json"})
        return [h['title'][5:] for h in d.get('query', {}).get('search', [])]
    except Exception: return []

def article_lead_image(title):
    """Try Wikipedia article's lead image (full-size first, then thumbnail fallback)."""
    candidates = []
    for prop in ['piprop=original', 'pithumbsize=2000']:
        try:
            d = http_json(WPAPI, {"action": "query", "titles": title,
                                  "prop": "pageimages", prop.split('=')[0]: prop.split('=')[1],
                                  "format": "json"})
            for p in d.get('query', {}).get('pages', {}).values():
                src_obj = p.get('original') or p.get('thumbnail')
                if src_obj and 'source' in src_obj:
                    candidates.append(src_obj['source'])
        except Exception: pass
    return candidates

def article_images(title, limit=30):
    """All file titles referenced by the article."""
    try:
        d = http_json(WPAPI, {"action": "query", "titles": title,
                              "prop": "images", "imlimit": str(limit), "format": "json"})
        for p in d.get('query', {}).get('pages', {}).values():
            return [img['title'][5:] for img in p.get('images', []) if img['title'].startswith('File:')]
    except Exception: pass
    return []

def file_url(fname):
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(fname)}?width=1600"

def md5(b):
    return hashlib.md5(b).hexdigest()

def fetch(url, max_bytes=15_000_000):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read(max_bytes)
            return data
    except Exception:
        return None

def detect_format(data):
    if not data or len(data) < 100: return None
    if data[:3] == b'\xff\xd8\xff': return 'jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n': return 'png'
    return None

def png_to_jpeg(path):
    try:
        out = path.with_suffix('.tmp.jpg')
        subprocess.run(['sips', '-s', 'format', 'jpeg', str(path), '--out', str(out)],
                       check=True, capture_output=True)
        out.replace(path)
        return True
    except Exception:
        return False

def score(fname, ev, is_article_lead=False):
    """Higher = better. Returns score, or None if disqualified."""
    fn = fname.lower()
    s = 0
    # Disqualify dead-on negatives
    for w in NEGATIVE[-2000]:
        if w in fn: return None
    # Required substring gate — file must mention Kennedy/family OR an event subject
    must = ev.get('must', ['kennedy', 'jfk'])
    if not any(m in fn for m in must):
        return None
    # Year match — huge boost
    if ev['year'] in fn: s += 200
    # Year boost for decade neighbors
    yr = int(ev['year'])
    for delta in range(-3, 4):
        if delta == 0: continue
        if str(yr + delta) in fn:
            s += max(0, 80 - 20 * abs(delta))
    # MODERN year penalty (huge — these are anachronistic photos)
    late = LATE_YEAR_RE.findall(fn)
    if late:
        s -= 700 * len(late)
    # Kennedy mention
    if 'kennedy' in fn: s += 30
    if 'jfk' in fn: s += 30
    # Event-specific keywords
    for kw in ev['keywords']:
        if kw.lower() in fn: s += 80
    # Archival prefix bonus
    for pref in POSITIVE_PREFIXES:
        if fn.startswith(pref): s += 60
    # Negative keyword penalties
    for penalty, words in NEGATIVE.items():
        if penalty == -2000: continue
        for w in words:
            if w in fn: s += penalty
    # Mild article-lead boost (only if not already disqualified)
    if is_article_lead: s += 200
    return s

def pick_best(idx, ev, used):
    """Try article lead image first (it's editorially curated). If duplicate
       or unavailable, fall back to scored category + search candidates."""
    candidates = []  # (source_label, fetch_url, fname_for_score)

    # Source 1: Wikipedia article lead image (editorial pick, but score-vetted)
    if ev['article']:
        for url in article_lead_image(ev['article']):
            fname = urllib.parse.unquote(url.split('/')[-1])
            sc = score(fname, ev, is_article_lead=True)
            if sc is not None:
                candidates.append((f"article-lead:{ev['article']}", url, fname, sc))

        for fn in article_images(ev['article'], limit=30):
            if is_image_ext(fn):
                sc = score(fn, ev, is_article_lead=True)
                if sc is not None:
                    candidates.append((f"article-img:{ev['article']}", file_url(fn), fn, sc))

    # Source 2: Commons categories
    for cat in ev['cats']:
        for fn in list_category_files(cat, limit=80):
            if is_image_ext(fn):
                sc = score(fn, ev)
                if sc is not None:
                    candidates.append((cat, file_url(fn), fn, sc))

    # Source 3: Free-text searches
    for q in ev['searches']:
        for fn in search_files(q, limit=15):
            if is_image_ext(fn):
                sc = score(fn, ev)
                if sc is not None:
                    candidates.append((f"search:{q}", file_url(fn), fn, sc))

    # De-dupe by fname, keep highest-scoring source
    best_per_name = {}
    for src, url, fname, sc in candidates:
        if fname not in best_per_name or sc > best_per_name[fname][3]:
            best_per_name[fname] = (src, url, fname, sc)
    candidates = sorted(best_per_name.values(), key=lambda c: -c[3])

    for src, url, fname, sc in candidates[:30]:
        if sc < -300:  # candidates this bad: skip
            break
        data = fetch(url)
        kind = detect_format(data)
        if not kind: continue
        if len(data) < 30_000: continue
        h = md5(data)
        if h in used: continue

        target = PHOTOS_DIR / f"{idx}.jpg"
        target.write_bytes(data)
        if kind == 'png' and not png_to_jpeg(target):
            target.unlink(); continue
        if kind == 'png': h = md5(target.read_bytes())
        used.add(h)
        return src, fname, sc

    return None, None, None


def main():
    # Wipe existing replacements
    for i in range(len(EVENTS)):
        p = PHOTOS_DIR / f"{i}.jpg"
        if p.exists(): p.unlink()

    used = set()
    failures = []
    for i, ev in enumerate(EVENTS):
        sys.stdout.write(f"[{i:2d}] {ev['year']} ")
        sys.stdout.flush()
        src, fname, sc = pick_best(i, ev, used)
        if fname:
            short = (fname[:65] + "…") if len(fname) > 65 else fname
            print(f"score={sc:>4}  {short}  ({src[:30]})")
        else:
            failures.append(i)
            print("✗ no acceptable photo")

    print()
    total = len([f for f in PHOTOS_DIR.glob("*.jpg")])
    print(f"Done. {total}/{len(EVENTS)} photos. Failures: {failures}")

if __name__ == "__main__":
    main()
