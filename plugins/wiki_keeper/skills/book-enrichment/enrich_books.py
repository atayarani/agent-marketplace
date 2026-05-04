#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Backfill metadata + blurb on `lists/media/books/items/*.md` from public book APIs.

Idempotent: items that already have a `## Blurb` section are skipped.
Non-destructive: existing frontmatter values are preserved; only empty fields
are filled. The body's existing sections are kept in place — the new `## Blurb`
section is inserted right after the H1.

Sources tried (in priority order, configurable via `--sources`):
  1. Hardcover.app   — requires HARDCOVER_TOKEN env var. Best for fiction blurbs.
  2. Open Library    — primary metadata anchor; description quality varies.
  3. Wikipedia REST  — best for famous works; falls back when OL has no description.
  4. Google Books    — broad fallback; unauth daily quota is easily exhausted,
                       set GOOGLE_BOOKS_KEY for higher quota.

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

USER_AGENT = "wiki-keeper/book-enrichment/0.1 (https://github.com/atayarani/agent-marketplace)"
TODAY = date.today().isoformat()

# Per-source pacing (seconds between requests). Hardcover is hard-capped at 60/min.
PACE = {
    "openlibrary": 0.25,
    "wikipedia": 0.25,
    "hardcover": 1.05,
    "googlebooks": 0.40,
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


DERIVATIVE_MARKERS = (
    "study guide",
    "summary of",
    "summary and analysis",
    "analysis of",
    "abridged",
    "cliffsnotes",
    "sparknotes",
    "(adaptation)",
    "graphic novel",
)


def best_match(candidates, target_title, target_author, get_title, get_authors, get_popularity):
    """Pick the best candidate by title similarity, with author-match boost and popularity tie-break."""
    best, best_score = None, 0.0
    for c in candidates:
        cand_title = get_title(c)
        score = title_score(target_title, cand_title)
        if any(m in (cand_title or "").lower() for m in DERIVATIVE_MARKERS):
            score *= 0.5
        authors = get_authors(c)
        if target_author and authors:
            score = 0.7 * score + 0.3 * max(title_score(target_author, a) for a in authors)
        pop = max(0, get_popularity(c))
        score *= 1 + 0.04 * math.log(1 + pop)
        if score > best_score:
            best, best_score = c, score
    return best, best_score


# ---- Open Library ------------------------------------------------------------


def search_openlibrary(title: str, author: str = "") -> list | None:
    q = f"title={urllib.parse.quote(title)}"
    if author:
        q += f"&author={urllib.parse.quote(author)}"
    q += (
        "&limit=5&sort=editions"
        "&fields=key,title,author_name,first_publish_year,edition_count,subject,description"
    )
    data, status = http_json(f"https://openlibrary.org/search.json?{q}")
    time.sleep(PACE["openlibrary"])
    if not data:
        return None
    return data.get("docs") or None


def fetch_ol_work(work_key: str) -> dict | None:
    if not work_key.startswith("/works/"):
        return None
    data, _ = http_json(f"https://openlibrary.org{work_key}.json")
    time.sleep(PACE["openlibrary"])
    return data


def ol_description(work: dict) -> str:
    d = work.get("description")
    if isinstance(d, dict):
        d = d.get("value", "")
    if not d:
        return ""
    d = str(d).strip()
    # OL appends bibliographic notes after a "----" separator on some works
    d = re.split(r"\n\s*-{4,}\s*\n", d)[0].strip()
    if d.lower() in ("[summary needed]", ""):
        return ""
    return d


def try_openlibrary(title: str, author: str) -> dict | None:
    cands = search_openlibrary(title, author)
    if not cands:
        return None
    best, score = best_match(
        cands,
        title,
        author,
        get_title=lambda c: c.get("title", ""),
        get_authors=lambda c: c.get("author_name") or [],
        get_popularity=lambda c: c.get("edition_count") or 0,
    )
    if not best or score < 0.7:
        return {"_matched": False, "score": score}
    desc = ""
    work = fetch_ol_work(best.get("key", ""))
    if work:
        desc = ol_description(work)
    if not desc and best.get("description"):
        # Sometimes the search doc carries a description directly
        d = best["description"]
        desc = d if isinstance(d, str) else d.get("value", "")
    return {
        "_matched": True,
        "title": best.get("title"),
        "author": (best.get("author_name") or [None])[0],
        "url": f"https://openlibrary.org{best['key']}" if best.get("key") else "",
        "year": best.get("first_publish_year"),
        "description": desc,
        "source": "Open Library",
    }


# ---- Wikipedia ---------------------------------------------------------------


def search_wikipedia(title: str, author: str = "") -> str | None:
    queries = []
    if author:
        queries += [f"{title} {author}", f"{title} {author} novel"]
    queries += [f"{title} novel", f"{title} book", title]
    for q in queries:
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&format=json&limit=5&search={urllib.parse.quote(q)}"
        data, _ = http_json(url)
        time.sleep(PACE["wikipedia"])
        if not data or len(data) < 2 or not data[1]:
            continue
        for page in data[1]:
            low = page.lower()
            if any(bad in low for bad in ("disambiguation", "(film)", "(song)", "(album)", "(tv series)", "(band)")):
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


def try_wikipedia(title: str, author: str) -> dict | None:
    page = search_wikipedia(title, author)
    if not page:
        return None
    extract, page_url = fetch_wikipedia_summary(page)
    if not extract or len(extract) < 80:
        return None
    return {
        "_matched": True,
        "title": page,
        "author": author or None,
        "url": page_url or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page.replace(' ', '_'))}",
        "year": None,
        "description": extract,
        "source": f"Wikipedia: [{page}]({page_url})",
    }


# ---- Hardcover ---------------------------------------------------------------


HARDCOVER_QUERY = """
query Search($q: String!) {
  search(query: $q, query_type: "Book", per_page: 5, page: 1) {
    results
  }
}
"""


def hardcover_primary_author(doc: dict) -> str:
    types = doc.get("contribution_types") or []
    names = doc.get("author_names") or []
    for i, t in enumerate(types):
        if t == "Author" and i < len(names):
            return names[i]
    return names[0] if names else ""


def search_hardcover(title: str, author: str, token: str) -> list | None:
    q = f"{title} {author}".strip() if author else title
    body = json.dumps({"query": HARDCOVER_QUERY, "variables": {"q": q}}).encode()
    data, _ = http_json(
        "https://api.hardcover.app/v1/graphql",
        method="POST",
        body=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    time.sleep(PACE["hardcover"])
    if not data or not data.get("data"):
        return None
    raw = data["data"].get("search", {}).get("results")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    hits = raw.get("hits") or []
    return [h.get("document", {}) for h in hits] or None


def try_hardcover(title: str, author: str) -> dict | None:
    token = os.environ.get("HARDCOVER_TOKEN")
    if not token:
        return None
    cands = search_hardcover(title, author, token)
    if not cands:
        return None
    best, score = best_match(
        cands,
        title,
        author,
        get_title=lambda c: c.get("title", ""),
        get_authors=lambda c: c.get("author_names") or [],
        get_popularity=lambda c: (c.get("users_read_count") or 0) + (c.get("lists_count") or 0),
    )
    if not best or score < 0.7:
        return {"_matched": False, "score": score}
    desc = (best.get("description") or "").strip()
    if not desc or len(desc) < 80:
        return {"_matched": False, "score": score, "thin_desc": True}
    slug = best.get("slug") or ""
    return {
        "_matched": True,
        "title": best.get("title"),
        "author": hardcover_primary_author(best),
        "url": f"https://hardcover.app/books/{slug}" if slug else "",
        "year": best.get("release_year"),
        "description": desc,
        "source": f"[Hardcover.app](https://hardcover.app/books/{slug})" if slug else "Hardcover.app",
    }


# ---- Google Books ------------------------------------------------------------


def search_google_books(title: str, author: str, key: str | None) -> list | None:
    parts = [f"intitle:{urllib.parse.quote(title)}"]
    if author:
        parts.append(f"inauthor:{urllib.parse.quote(author)}")
    q = "+".join(parts)
    url = f"https://www.googleapis.com/books/v1/volumes?q={q}&maxResults=5&printType=books"
    if key:
        url += f"&key={urllib.parse.quote(key)}"
    data, status = http_json(url, on_429="fail")  # quota error: stop trying immediately
    time.sleep(PACE["googlebooks"])
    if status == 429 or not data:
        return None
    return data.get("items") or None


def try_googlebooks(title: str, author: str) -> dict | None:
    items = search_google_books(title, author, os.environ.get("GOOGLE_BOOKS_KEY"))
    if not items:
        return None
    cands = [item.get("volumeInfo", {}) for item in items]
    best, score = best_match(
        cands,
        title,
        author,
        get_title=lambda c: c.get("title", ""),
        get_authors=lambda c: c.get("authors") or [],
        get_popularity=lambda c: c.get("ratingsCount") or 0,
    )
    if not best or score < 0.7:
        return {"_matched": False, "score": score}
    desc = re.sub(r"<[^>]+>", "", (best.get("description") or "")).strip()
    if not desc or len(desc) < 80:
        return None
    year = None
    m = re.match(r"^(\d{4})", best.get("publishedDate", "") or "")
    if m:
        year = int(m.group(1))
    info_url = best.get("canonicalVolumeLink") or best.get("infoLink") or ""
    return {
        "_matched": True,
        "title": best.get("title"),
        "author": (best.get("authors") or [None])[0],
        "url": info_url,
        "year": year,
        "description": desc[:2000].rsplit(". ", 1)[0] + "." if len(desc) > 2000 else desc,
        "source": "Google Books",
    }


SOURCE_FUNCS = {
    "hardcover": try_hardcover,
    "openlibrary": try_openlibrary,
    "wikipedia": try_wikipedia,
    "googlebooks": try_googlebooks,
}
DEFAULT_ORDER = ["hardcover", "openlibrary", "wikipedia", "googlebooks"]


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
    enriched-via-<source>, skip-already-enriched, skip-not-target-status, skip-no-h1,
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
    existing_creator = fm_field(fm, "creator")

    last_score = 0.0
    last_status = "ambiguous-no-match"
    for src in sources:
        result = SOURCE_FUNCS[src](title, existing_creator)
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
        if result.get("author") and not existing_creator:
            new_fm = update_fm_field(new_fm, "creator", result["author"])
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
    ap = argparse.ArgumentParser(description="Enrich book items in a wiki_keeper vault.")
    ap.add_argument("--vault", help="Vault root (auto-detected from PWD if omitted)")
    ap.add_argument("--status", default="tbr", help="Status filter (default: tbr; use 'any' for all)")
    ap.add_argument("--limit", type=int, help="Process at most N items")
    ap.add_argument("--items", help="Glob filter on filenames (e.g. 'a-*')")
    ap.add_argument("--sources", default=",".join(DEFAULT_ORDER), help="Comma-separated source order")
    ap.add_argument("--reset", action="store_true", help="Strip existing ## Blurb before re-enriching")
    ap.add_argument("--dry-run", action="store_true", help="Log decisions but don't write files")
    args = ap.parse_args(argv)

    vault = Path(args.vault) if args.vault else find_vault(Path.cwd())
    if not vault or not vault.is_dir():
        sys.exit(2)

    items_dir = vault / "lists/media/books/items"
    if not items_dir.is_dir():
        sys.exit(f"no items dir found at {items_dir}")

    sources = parse_sources(args.sources)
    # Drop hardcover automatically if no token (rather than fail per item)
    if "hardcover" in sources and not os.environ.get("HARDCOVER_TOKEN"):
        sources = [s for s in sources if s != "hardcover"]
        print("note: HARDCOVER_TOKEN not set — skipping hardcover", file=sys.stderr)

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
    log_path = vault / "system" / f"enrich-books-{TODAY}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"enriching {len(paths)} items via [{', '.join(sources)}]")
    with open(log_path, "w") as log:
        log.write(f"# book enrichment log {TODAY}\nsources: {sources}\n\n")
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
