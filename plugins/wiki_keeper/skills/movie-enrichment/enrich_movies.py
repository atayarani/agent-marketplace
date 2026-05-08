#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Backfill metadata + blurb on `lists/media/movies/items/*.md` from public movie APIs.

Idempotent: items that already have a `## Blurb` section are skipped.
Non-destructive: existing frontmatter values are preserved; only empty fields
are filled. The body's existing sections are kept in place — the new `## Blurb`
section is inserted right after the H1.

Sources tried (in priority order, configurable via `--sources`):
  1. TMDB         — requires TMDB_BEARER (preferred) or TMDB_API_KEY env var.
                    Best blurbs and metadata; free signup, generous limits.
  2. Wikipedia    — best for famous / canonical films; no auth needed.
                    Prefers `(film)` / `(YYYY film)` disambiguated pages.
  3. OMDB         — IMDB-derived; requires OMDB_API_KEY env var.
                    1000/day free tier; concise plot summaries.

The script never writes the tokens anywhere; they're read from env only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

USER_AGENT = "wiki-keeper/movie-enrichment/0.1 (https://github.com/atayarani/agent-marketplace)"
TODAY = date.today().isoformat()

# Per-source pacing (seconds between requests).
PACE = {
    "tmdb": 0.25,
    "wikipedia": 0.25,
    "omdb": 0.25,
}

# ---- HTTP --------------------------------------------------------------------


def http_json(
    url: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 20,
    on_429: str = "backoff",
) -> tuple[dict | None, int]:
    """Fetch JSON. Returns (parsed_json_or_None, http_status_or_-1)."""
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    backoff = 2.0
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read()), resp.status
        except urllib.error.HTTPError as e:
            if e.code == 429 and on_429 == "backoff" and attempt + 1 < 3:
                time.sleep(backoff)
                backoff *= 2
                continue
            return None, e.code
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            return None, -1
    return None, -1


# ---- String similarity -------------------------------------------------------


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"['']", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(the|a|an) ", "", s)
    return s


def title_score(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# Markers that indicate a *non-film* page or a derivative — penalize or skip.
NON_FILM_MARKERS = (
    "(novel)",
    "(book)",
    "(short story)",
    "(album)",
    "(song)",
    "(band)",
    "(tv series)",
    "(tv show)",
    "(painting)",
    "(play)",
    "(opera)",
    "(video game)",
    "(comic)",
)
# Markers that *positively* indicate a film page on Wikipedia.
FILM_MARKERS = (
    "(film)",
    " film)",  # catches "(YYYY film)", "(YYYY American film)", etc.
    "(film series)",
)
DERIVATIVE_MARKERS = (
    "(remake)",
    "(reboot)",
    "(prequel)",
    "(sequel)",
    "(short film)",
    "behind the scenes",
    "making of",
)


def best_match(candidates, target_title, target_director, target_year, get_title, get_directors, get_year, get_popularity):
    """Pick the best candidate by title similarity, with director-match boost, year-match boost, and popularity tie-break."""
    best, best_score = None, 0.0
    for c in candidates:
        cand_title = get_title(c) or ""
        score = title_score(target_title, cand_title)
        if any(m in cand_title.lower() for m in DERIVATIVE_MARKERS):
            score *= 0.5
        directors = get_directors(c) or []
        if target_director and directors:
            score = 0.7 * score + 0.3 * max(title_score(target_director, d) for d in directors)
        cand_year = get_year(c)
        if target_year and cand_year:
            try:
                gap = abs(int(target_year) - int(cand_year))
                # Strong year-match boost; disallow when off by >5 years for ambiguous remake territory
                if gap == 0:
                    score *= 1.15
                elif gap <= 2:
                    score *= 1.05
                elif gap > 5:
                    score *= 0.7
            except (TypeError, ValueError):
                pass
        pop = max(0, get_popularity(c) or 0)
        score *= 1 + 0.04 * math.log(1 + pop)
        if score > best_score:
            best, best_score = c, score
    return best, best_score


# ---- TMDB --------------------------------------------------------------------


def tmdb_auth_headers() -> tuple[dict, str]:
    """Return (headers, query_suffix) depending on which auth env var is set.

    TMDB supports two auth modes:
      - Bearer (v4 read access token) via Authorization header
      - api_key query param (v3)
    Bearer is preferred because it doesn't leak into URLs.
    """
    bearer = os.environ.get("TMDB_BEARER")
    if bearer:
        return ({"Authorization": f"Bearer {bearer}"}, "")
    api_key = os.environ.get("TMDB_API_KEY")
    if api_key:
        return ({}, f"&api_key={urllib.parse.quote(api_key)}")
    return ({}, "")


def search_tmdb(title: str, director: str, year: str | None) -> list | None:
    headers, key_q = tmdb_auth_headers()
    if not headers and not key_q:
        return None
    q = urllib.parse.quote(title)
    url = f"https://api.themoviedb.org/3/search/movie?query={q}&include_adult=true&language=en-US&page=1"
    if year:
        url += f"&year={urllib.parse.quote(str(year))}"
    url += key_q
    data, _ = http_json(url, headers=headers)
    time.sleep(PACE["tmdb"])
    if not data:
        return None
    return data.get("results") or None


def fetch_tmdb_credits(movie_id: int) -> list:
    """Return list of director names for the movie."""
    headers, key_q = tmdb_auth_headers()
    if not headers and not key_q:
        return []
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits?language=en-US{key_q}"
    data, _ = http_json(url, headers=headers)
    time.sleep(PACE["tmdb"])
    if not data:
        return []
    crew = data.get("crew") or []
    return [c.get("name", "") for c in crew if c.get("job") == "Director"]


def try_tmdb(title: str, director: str, year: str | None) -> dict | None:
    headers, _ = tmdb_auth_headers()
    if not headers and not os.environ.get("TMDB_API_KEY"):
        return None
    cands = search_tmdb(title, director, year)
    if not cands:
        return None
    best, score = best_match(
        cands,
        title,
        director,
        year,
        get_title=lambda c: c.get("title", ""),
        # TMDB search doesn't return crew — we'll patch director after we pick.
        get_directors=lambda c: [],
        get_year=lambda c: (c.get("release_date", "") or "")[:4] or None,
        get_popularity=lambda c: c.get("popularity") or 0,
    )
    if not best or score < 0.7:
        return {"_matched": False, "score": score}
    desc = (best.get("overview") or "").strip()
    if not desc or len(desc) < 80:
        return {"_matched": False, "score": score, "thin_desc": True}
    movie_id = best.get("id")
    directors = fetch_tmdb_credits(movie_id) if movie_id else []
    primary_director = directors[0] if directors else ""
    year_match = re.match(r"^(\d{4})", best.get("release_date", "") or "")
    return {
        "_matched": True,
        "title": best.get("title"),
        "director": primary_director,
        "url": f"https://www.themoviedb.org/movie/{movie_id}" if movie_id else "",
        "year": int(year_match.group(1)) if year_match else None,
        "description": desc,
        "source": f"[TMDB](https://www.themoviedb.org/movie/{movie_id})" if movie_id else "TMDB",
    }


# ---- Wikipedia ---------------------------------------------------------------


def search_wikipedia(title: str, director: str = "", year: str | None = None) -> str | None:
    queries = []
    if year:
        queries += [f"{title} {year} film"]
    if director:
        queries += [f"{title} {director} film"]
    queries += [f"{title} film", f"{title} movie", title]

    for q in queries:
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&format=json&limit=10&search={urllib.parse.quote(q)}"
        data, _ = http_json(url)
        time.sleep(PACE["wikipedia"])
        if not data or len(data) < 2 or not data[1]:
            continue
        # Pass 1: prefer film-marked pages
        for page in data[1]:
            low = page.lower()
            if "disambiguation" in low:
                continue
            if any(bad in low for bad in NON_FILM_MARKERS):
                continue
            if any(good in low for good in FILM_MARKERS):
                return page
        # Pass 2: accept plain title that doesn't have a non-film disambiguator
        for page in data[1]:
            low = page.lower()
            if "disambiguation" in low:
                continue
            if any(bad in low for bad in NON_FILM_MARKERS):
                continue
            return page
    return None


def fetch_wikipedia_summary(page_title: str) -> tuple[str, str]:
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title.replace(' ', '_'))}"
    data, _ = http_json(url)
    time.sleep(PACE["wikipedia"])
    if not data or data.get("type") == "disambiguation":
        return "", ""
    extract = (data.get("extract") or "").strip()
    page_url = (data.get("content_urls", {}).get("desktop", {}).get("page")) or ""
    return extract, page_url


def try_wikipedia(title: str, director: str, year: str | None) -> dict | None:
    page = search_wikipedia(title, director, year)
    if not page:
        return None
    extract, page_url = fetch_wikipedia_summary(page)
    if not extract or len(extract) < 80:
        return None
    return {
        "_matched": True,
        "title": page,
        "director": director or None,
        "url": page_url or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page.replace(' ', '_'))}",
        "year": None,  # Wikipedia REST summary doesn't reliably parse year
        "description": extract,
        "source": f"Wikipedia: [{page}]({page_url})" if page_url else f"Wikipedia: {page}",
    }


# ---- OMDB --------------------------------------------------------------------


def search_omdb(title: str, year: str | None, key: str) -> list | None:
    """OMDB's `s=` endpoint returns a list; `t=` returns one. Use `s=` for ranking."""
    url = f"http://www.omdbapi.com/?apikey={urllib.parse.quote(key)}&type=movie&s={urllib.parse.quote(title)}"
    if year:
        url += f"&y={urllib.parse.quote(str(year))}"
    data, _ = http_json(url)
    time.sleep(PACE["omdb"])
    if not data or data.get("Response") != "True":
        return None
    return data.get("Search") or None


def fetch_omdb_details(imdb_id: str, key: str) -> dict | None:
    url = f"http://www.omdbapi.com/?apikey={urllib.parse.quote(key)}&i={urllib.parse.quote(imdb_id)}&plot=full"
    data, _ = http_json(url)
    time.sleep(PACE["omdb"])
    if not data or data.get("Response") != "True":
        return None
    return data


def try_omdb(title: str, director: str, year: str | None) -> dict | None:
    key = os.environ.get("OMDB_API_KEY")
    if not key:
        return None
    cands = search_omdb(title, year, key)
    if not cands:
        return None
    # OMDB search results don't carry director or popularity; rank on title + year only.
    best, score = best_match(
        cands,
        title,
        director,
        year,
        get_title=lambda c: c.get("Title", ""),
        get_directors=lambda c: [],
        get_year=lambda c: c.get("Year", ""),
        get_popularity=lambda c: 0,
    )
    if not best or score < 0.7:
        return {"_matched": False, "score": score}
    imdb_id = best.get("imdbID", "")
    details = fetch_omdb_details(imdb_id, key) if imdb_id else None
    if not details:
        return {"_matched": False, "score": score, "thin_desc": True}
    desc = (details.get("Plot") or "").strip()
    if not desc or len(desc) < 80:
        return {"_matched": False, "score": score, "thin_desc": True}
    director_field = (details.get("Director") or "").strip()
    primary_director = director_field.split(",")[0].strip() if director_field and director_field != "N/A" else ""
    try:
        year_int = int((details.get("Year") or "").split("–")[0][:4])
    except ValueError:
        year_int = None
    return {
        "_matched": True,
        "title": details.get("Title"),
        "director": primary_director,
        "url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
        "year": year_int,
        "description": desc,
        "source": f"OMDB / [IMDB {imdb_id}](https://www.imdb.com/title/{imdb_id}/)" if imdb_id else "OMDB",
    }


SOURCE_FUNCS = {
    "tmdb": try_tmdb,
    "wikipedia": try_wikipedia,
    "omdb": try_omdb,
}
DEFAULT_ORDER = ["tmdb", "wikipedia", "omdb"]


# ---- File operations ---------------------------------------------------------


def split_fm(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    return (text[4:end], text[end + 4 :]) if end > -1 else ("", text)


def update_fm_field(fm: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    new_line = f"{key}: {value}"
    if pattern.search(fm):
        return pattern.sub(new_line, fm, count=1)
    return fm.rstrip("\n") + "\n" + new_line + "\n"


def fm_field(fm: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", fm, re.MULTILINE)
    return (m.group(1) if m else "").strip()


def reset_blurb(text: str) -> str:
    """Remove the `## Blurb` section (Blurb header through next ## section or EOF)."""
    return re.sub(r"\n## Blurb\b.*?(?=\n## |\Z)", "\n", text, count=1, flags=re.DOTALL)


def enrich_item(path: Path, sources: list, dry_run: bool = False) -> tuple[str, str | None]:
    """Returns (status, source_used). Status is one of:
    enriched-via-<source>, skip-already-enriched, skip-no-h1,
    ambiguous-no-match, ambiguous-low-score, ambiguous-no-description.
    """
    text = path.read_text()
    fm, body = split_fm(text)

    if re.search(r"^## Blurb\s*$", body, re.MULTILINE):
        return "skip-already-enriched", None

    title_m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if not title_m:
        return "skip-no-h1", None
    title = title_m.group(1).strip()
    existing_director = fm_field(fm, "creator")
    existing_year = fm_field(fm, "published") or None

    last_score = 0.0
    last_status = "ambiguous-no-match"
    for src in sources:
        result = SOURCE_FUNCS[src](title, existing_director, existing_year)
        if not result:
            continue
        if not result.get("_matched"):
            last_score = max(last_score, result.get("score", 0.0))
            if result.get("thin_desc"):
                last_status = "ambiguous-no-description"
            else:
                last_status = "ambiguous-low-score" if result.get("score", 0) > 0 else "ambiguous-no-match"
            continue
        # Got a match — apply it
        if dry_run:
            return f"would-enrich-via-{src}", src

        new_fm = fm
        if result.get("director") and not existing_director:
            new_fm = update_fm_field(new_fm, "creator", result["director"])
        if not fm_field(new_fm, "source_url") and result.get("url"):
            new_fm = update_fm_field(new_fm, "source_url", result["url"])
        if result.get("year") and not fm_field(new_fm, "published"):
            new_fm = update_fm_field(new_fm, "published", str(result["year"]))
        new_fm = update_fm_field(new_fm, "updated", TODAY)

        desc = result["description"]
        if len(desc) > 2000:
            desc = desc[:2000].rsplit(". ", 1)[0] + "."
        block = f"\n## Blurb\n\n{desc}\n\n*Source: {result['source']}*\n"
        new_body = re.sub(r"^(# .+\n)", lambda m: m.group(1) + block, body, count=1, flags=re.MULTILINE)
        new_text = f"---\n{new_fm.strip()}\n---\n{new_body if new_body.startswith(chr(10)) else chr(10) + new_body}"
        new_text = re.sub(r"---\n\n+#", "---\n\n#", new_text)
        path.write_text(new_text)
        return f"enriched-via-{src}", src

    return last_status, None


# ---- Vault discovery ---------------------------------------------------------


def find_vault(start: Path) -> Path | None:
    p = start.resolve()
    while True:
        if (p / "AGENTS.md").exists() or (p / "CLAUDE.md").exists():
            return p
        if p.parent == p:
            return None
        p = p.parent


# ---- CLI ---------------------------------------------------------------------


def parse_sources(arg: str) -> list:
    out = []
    for s in arg.split(","):
        s = s.strip().lower()
        if not s:
            continue
        if s not in SOURCE_FUNCS:
            sys.exit(f"unknown source: {s} (valid: {', '.join(SOURCE_FUNCS)})")
        out.append(s)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Enrich movie items in a wiki_keeper vault.")
    ap.add_argument("--vault", help="Vault root (auto-detected from PWD if omitted)")
    ap.add_argument("--status", default="to-watch", help="Status filter (default: to-watch; use 'any' for all)")
    ap.add_argument("--limit", type=int, help="Process at most N items")
    ap.add_argument("--items", help="Glob filter on filenames (e.g. 'a-*')")
    ap.add_argument("--sources", default=",".join(DEFAULT_ORDER), help="Comma-separated source order")
    ap.add_argument("--reset", action="store_true", help="Strip existing ## Blurb before re-enriching")
    ap.add_argument("--dry-run", action="store_true", help="Log decisions but don't write files")
    args = ap.parse_args(argv)

    vault = Path(args.vault) if args.vault else find_vault(Path.cwd())
    if not vault or not vault.is_dir():
        sys.exit(2)

    items_dir = vault / "lists/media/movies/items"
    if not items_dir.is_dir():
        sys.exit(f"no items dir found at {items_dir}")

    sources = parse_sources(args.sources)
    # Drop sources that lack required credentials, with a note rather than per-item failure.
    if "tmdb" in sources and not (os.environ.get("TMDB_BEARER") or os.environ.get("TMDB_API_KEY")):
        sources = [s for s in sources if s != "tmdb"]
        print("note: TMDB_BEARER/TMDB_API_KEY not set — skipping tmdb", file=sys.stderr)
    if "omdb" in sources and not os.environ.get("OMDB_API_KEY"):
        sources = [s for s in sources if s != "omdb"]
        print("note: OMDB_API_KEY not set — skipping omdb", file=sys.stderr)
    if not sources:
        sys.exit("no sources available — set TMDB_BEARER, TMDB_API_KEY, or OMDB_API_KEY, or include 'wikipedia' in --sources")

    glob = args.items or "*.md"
    if not glob.endswith(".md"):
        glob += ".md"
    paths = sorted(items_dir.glob(glob))

    # Filter by status
    if args.status != "any":
        keep = []
        for p in paths:
            t = p.read_text()
            fm, _ = split_fm(t)
            if fm_field(fm, "status") == args.status:
                keep.append(p)
        paths = keep

    if args.limit:
        paths = paths[: args.limit]

    if not paths:
        sys.exit(3)

    if args.reset and not args.dry_run:
        for p in paths:
            t = p.read_text()
            if re.search(r"^## Blurb\s*$", t, re.MULTILINE):
                p.write_text(reset_blurb(t))

    counts = {}
    log_path = vault / "system" / f"enrich-movies-{TODAY}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"enriching {len(paths)} items via [{', '.join(sources)}]")
    with open(log_path, "w") as log:
        log.write(f"# movie enrichment log {TODAY}\nsources: {sources}\n\n")
        for i, p in enumerate(paths, 1):
            try:
                status, src = enrich_item(p, sources, dry_run=args.dry_run)
            except Exception as e:
                status, src = "error", None
                log.write(f"error\t{p.name}\t{e}\n")
            counts[status] = counts.get(status, 0) + 1
            if status.startswith("ambiguous") or status == "error":
                log.write(f"{status}\t{p.name}\n")
            if i % 50 == 0:
                en = sum(v for k, v in counts.items() if k.startswith("enriched-via-"))
                print(f"  {i}/{len(paths)}; {en} enriched")

    print()
    print("=== summary ===")
    for k in sorted(counts):
        print(f"  {k:30s} {counts[k]}")
    print(f"\nlog: {log_path}")


if __name__ == "__main__":
    main()
