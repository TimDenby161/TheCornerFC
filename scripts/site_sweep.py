"""A slow look over the live site for what a visitor would notice is wrong (T-060).

Reads every page in the sitemap, then a sample of the player pages those pages link to, one
request a second so the site and its database barely notice, and flags:
  - any answer that isn't 200
  - garbled text (UTF-8 read as Latin-1: "CvetkoviÄ")
  - "NaN", "Infinity", "undefined", "null" or "[object Object]" in the visible text
  - stand-in names ("Team 123", "Competition 45")
  - a percentage over 100%, and an Ability or rank figure outside 0 to 100
Writes the findings, page by page, to a JSON file and prints a summary. Reads only public pages,
as a signed-out visitor; nothing is written anywhere.

    python scripts/site_sweep.py [--base https://thecornerfc.com] [--players 300] [--out sweep.json]
"""
import argparse
import html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

MANGLED = re.compile("[\xc2-\xdf][\x80-\xbf€™ŒœŠš]|[\xe0-\xef][\x80-\xbf]{2}")
# the same once the site has dropped the invisible second half: a stray capital in mid-word
# ("CvetkoviÄ", "OulaÃ"), which real names don't have
STRIPPED = re.compile("(?<=[a-z\xdf-\xff])[\xc2-\xc6\xc9\xd0](?![a-z\xdf-\xff])")
BAD_WORDS = re.compile(r"\b(NaN|Infinity|undefined|null)\b|\[object Object\]")
STAND_IN = re.compile(r"\b(Team|Competition) \d{1,7}\b")
PERCENT = re.compile(r"(?<![\d.])(\d{1,4}(?:\.\d+)?)%")
ABILITY = re.compile(r'<span class="val">([^<]*)</span><span class="lbl">Ability')
CHIP_RANK = re.compile(r'<span class="pos-chip-rank">([^<]*)</span>')
PLAYER_LINK = re.compile(r'href="(/player/\d+)"')
SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
AGENT = "TheCornerFC-sweep/1 (+https://thecornerfc.com; the site checking itself)"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:                      # timeouts, resets: reported, not fatal
        return f"error: {type(e).__name__}", ""


def visible(page):
    return html.unescape(TAG.sub(" ", SCRIPT.sub(" ", page)))


def check(page):
    """The problems one page shows, as short strings with an example each."""
    text = visible(page)
    found = []
    for name, pattern in (("garbled text", MANGLED), ("garbled text", STRIPPED), ("bad value", BAD_WORDS), ("stand-in name", STAND_IN)):
        hits = {text[max(0, m.start() - 10):m.end() + 2].strip() for m in pattern.finditer(text)}
        if hits:
            found.append(f"{name}: {', '.join(sorted(hits)[:5])}")
    over = sorted({m.group() for m in PERCENT.finditer(text) if float(m.group(1)) > 100})
    if over:
        found.append(f"over 100%: {', '.join(over[:5])}")
    for name, pattern in (("Ability", ABILITY), ("position rank", CHIP_RANK)):
        for m in pattern.finditer(page):
            v = m.group(1).strip()
            if v not in ("–", "-", "") and not (v.replace(".", "", 1).isdigit() and 0 <= float(v) <= 100):
                found.append(f"{name} out of range: {v}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://thecornerfc.com")
    ap.add_argument("--players", type=int, default=300)
    ap.add_argument("--out", default="sweep.json")
    ap.add_argument("--pause", type=float, default=1.0)
    args = ap.parse_args()

    status, sitemap = fetch(f"{args.base}/sitemap.xml")
    if status != 200:
        sys.exit(f"sitemap: {status}")
    pages = [re.sub(r"^https?://[^/]+", "", u) for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)]
    players = set()
    results = {}

    def visit(path):
        status, page = fetch(args.base + path)
        problems = [f"status {status}"] if status != 200 else check(page)
        if problems:
            results[path] = problems
        players.update(PLAYER_LINK.findall(page))
        time.sleep(args.pause)
        return status

    started = time.time()
    statuses = Counter()
    for n, path in enumerate(pages, 1):
        statuses[visit(path)] += 1
        if n % 100 == 0:
            print(f"{n}/{len(pages)} sitemap pages, {len(results)} with problems", flush=True)
    sample = sorted(players - set(pages))
    random.Random(20261022).shuffle(sample)
    for path in sample[:args.players]:
        statuses[visit(path)] += 1

    by_kind = Counter(p.split(":")[0] for problems in results.values() for p in problems)
    summary = {"base": args.base, "pages": len(pages) + min(len(sample), args.players), "sitemap_pages": len(pages),
               "player_pages": min(len(sample), args.players), "minutes": round((time.time() - started) / 60, 1),
               "statuses": {str(k): v for k, v in statuses.items()}, "pages_with_problems": len(results),
               "problems_by_kind": dict(by_kind)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "pages": results}, f, indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
