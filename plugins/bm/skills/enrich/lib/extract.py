#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.27",
#   "beautifulsoup4>=4.12",
# ]
# ///
"""Fetch a URL from an inbox file and emit extracted page metadata as JSON.

Reads the `url` field (and optional `web_search` boolean) from the inbox
file's frontmatter, fetches the page (15s timeout, follows redirects, retries
once on transient), parses the HTML with BeautifulSoup, and prints one JSON
record to stdout.

Usage:  extract.py <inbox-file>

Output schema (always all nine keys; null/empty for absent values):
  {
    "url":                  "https://...",
    "fetch_status":         200,
    "title":                "..." | null,
    "meta_description":     "..." | null,
    "og":                   {"title": "...", "description": "...",
                              "site_name": "...", "type": "..."},
    "json_ld":              <parsed JSON> | null,
    "body_text_excerpt":    "...",     # first 4096 chars of body get_text
    "web_search_override":  true | false | null,  # from `web_search` fm key
    "inbox_title":          "..." | null  # from inbox fm `title:` (bookmarklet captures)
  }

Per-host fallbacks: when the regular fetch returns 2xx but the HTML body is
thin (typical of anti-bot walls — IMDb name pages serve HTTP 202 with no
parseable title), specific known-good per-host JSON endpoints are queried to
populate `title` / `meta_description` / `og` from authoritative data. Today:
  - IMDb `/name/nmXXXXX` → `v3.sg.media-imdb.com/suggestion/h/<nm>.json`

On fetch failure (timeout, non-2xx after one retry), an informative error is
printed to stderr and the script exits 1. Invalid invocation exits 2.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "bm-enrich/0.1 (https://github.com/atayarani/agent-marketplace)"
TIMEOUT = 15.0
EXCERPT_MAX = 4096
RETRY_DELAY = 1.0
# Transient errors that warrant one retry. 5xx responses are also retried
# (see fetch()); 4xx responses fail immediately.
TRANSIENT_EXC: tuple[type[BaseException], ...] = (httpx.ConnectError, httpx.ReadTimeout)


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"extract.py: {msg}", file=sys.stderr)
    sys.exit(code)


def read_frontmatter(path: Path) -> dict[str, Any]:
    """Parse inbox file frontmatter.

    Returns {"url": str, "web_search_override": bool | None,
             "inbox_title": str | None}. `url` is required;
    `web_search_override` reflects the optional `web_search: true|false`
    frontmatter key (None when absent). `inbox_title` reflects the optional
    `title:` frontmatter key (typically set by the bookmarklet at capture time).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        die(f"file not found: {path}")
    except OSError as e:
        die(f"could not read {path}: {e}")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", content, re.DOTALL)
    if not m:
        die(f"no frontmatter block in {path}")
    fm = m.group(1)
    um = re.search(r"^url:\s*(\S.*?)\s*$", fm, re.MULTILINE)
    if not um:
        die(f"no url field in frontmatter: {path}")
    wm = re.search(r"^web_search:\s*(true|false)\s*$", fm, re.MULTILINE | re.IGNORECASE)
    override: bool | None = None
    if wm:
        override = wm.group(1).lower() == "true"
    tm = re.search(r'^title:\s*"?(.+?)"?\s*$', fm, re.MULTILINE)
    inbox_title: str | None = None
    if tm:
        raw = tm.group(1).strip()
        # Unescape \" inside the captured value (server.py writes \" for inner quotes)
        raw = raw.replace('\\"', '"')
        inbox_title = raw or None
    return {
        "url": um.group(1).strip(),
        "web_search_override": override,
        "inbox_title": inbox_title,
    }


def fetch(url: str) -> tuple[httpx.Response | None, str | None, int]:
    """Fetch with one retry on transient (ConnectError / ReadTimeout / 5xx).

    Returns (response, error_msg, status_code):
      - On success: (Response, None, status)
      - On hard failure (transient exhausted, or HTTP 4xx/5xx after retry):
        (None, error_msg, status_code_or_0)

    Caller decides whether to die or degrade gracefully (e.g., bookmarklet
    captures with an inbox_title can still proceed to the enricher).
    """
    headers = {"User-Agent": USER_AGENT}
    last_err = "unknown"
    last_status = 0
    with httpx.Client(
        timeout=TIMEOUT, follow_redirects=True, headers=headers
    ) as client:
        for attempt in range(2):
            try:
                resp = client.get(url)
            except TRANSIENT_EXC as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt == 0:
                    time.sleep(RETRY_DELAY)
                    continue
                return (None, f"fetch failed for {url}: {last_err}", 0)
            if 500 <= resp.status_code < 600 and attempt == 0:
                time.sleep(RETRY_DELAY)
                continue
            last_status = resp.status_code
            if resp.status_code >= 400:
                return (None, f"HTTP {resp.status_code} for {url}", resp.status_code)
            return (resp, None, resp.status_code)
    return (None, f"fetch failed for {url}: exhausted retries", last_status)


def get_html_text(resp: httpx.Response) -> str:
    try:
        return resp.text
    except UnicodeDecodeError:
        return resp.content.decode("utf-8", errors="replace")


def extract_title(soup: BeautifulSoup) -> str | None:
    if soup.title:
        text = soup.title.get_text(strip=True)
        return text or None
    return None


def extract_meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find(
        "meta",
        attrs={"name": re.compile(r"^description$", re.IGNORECASE)},
    )
    if tag:
        content = tag.get("content")
        if content:
            return content.strip()
    return None


def extract_og(soup: BeautifulSoup) -> dict[str, str]:
    og: dict[str, str] = {}
    for tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
        prop = tag.get("property", "")
        content = tag.get("content")
        if not content:
            continue
        key = prop[len("og:"):]
        if key in ("title", "description", "site_name", "type") and key not in og:
            og[key] = content.strip()
    return og


def extract_json_ld(soup: BeautifulSoup) -> Any:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not tag.string:
            continue
        try:
            return json.loads(tag.string)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def extract_body_excerpt(soup: BeautifulSoup) -> str:
    if not soup.body:
        return ""
    return soup.body.get_text(separator=" ", strip=True)[:EXCERPT_MAX]


IMDB_NAME_RE = re.compile(r"^https?://(?:www\.)?imdb\.com/name/(nm\d+)", re.IGNORECASE)
IMDB_SUGGESTION_URL = "https://v3.sg.media-imdb.com/suggestion/h/{nm}.json"


def imdb_name_fallback(url: str) -> dict[str, str] | None:
    """For IMDb /name/nmXXXXX pages, query the public suggestion API.

    Returns {"name": "...", "role_summary": "..."} or None when the URL
    doesn't match, the API is unreachable, or no record is found. Cheap
    (~200ms, no auth) and exists because the IMDb HTML page bot-walls
    extract.py with HTTP 202 + empty body.
    """
    m = IMDB_NAME_RE.match(url)
    if not m:
        return None
    nm = m.group(1)
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(IMDB_SUGGESTION_URL.format(nm=nm))
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    arr = data.get("d", []) if isinstance(data, dict) else []
    # Require an exact nm-id match — the suggestion API does fuzzy prefix
    # matching and will return unrelated entries for malformed IDs.
    match = next((x for x in arr if x.get("id") == nm), None)
    if not match:
        return None
    name = (match.get("l") or "").strip()
    role = (match.get("s") or "").strip()
    if not name:
        return None
    return {"name": name, "role_summary": role}


def main() -> int:
    if len(sys.argv) != 2:
        die("usage: extract.py <inbox-file>", code=2)
    path = Path(sys.argv[1])
    fm = read_frontmatter(path)
    url = fm["url"]
    resp, err, status = fetch(url)
    if resp is None:
        # Graceful degradation: when the inbox file already has a title from
        # the bookmarklet capture, emit a soft-fail record (exit 0) so the
        # enricher can still classify from url + inbox_title alone. Without
        # an inbox_title there's nothing to work with — hard fail.
        if fm["inbox_title"]:
            print(f"extract.py: {err} — degrading to inbox-title fallback", file=sys.stderr)
            out = {
                "url": url,
                "fetch_status": status,
                "title": None,
                "meta_description": None,
                "og": {},
                "json_ld": None,
                "body_text_excerpt": "",
                "web_search_override": fm["web_search_override"],
                "inbox_title": fm["inbox_title"],
            }
            json.dump(out, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
            return 0
        die(err or f"fetch failed for {url}")
    soup = BeautifulSoup(get_html_text(resp), "html.parser")
    title_out = extract_title(soup)
    meta_out = extract_meta_description(soup)
    og_out = extract_og(soup)

    # Per-host fallback: IMDb name pages bot-wall the HTML fetch with HTTP 202
    # and an empty body. Backfill from the public suggestion API when title is
    # missing.
    if not title_out:
        imdb = imdb_name_fallback(url)
        if imdb:
            title_out = imdb["name"]
            if not og_out.get("title"):
                og_out["title"] = imdb["name"]
            if imdb["role_summary"]:
                if not meta_out:
                    meta_out = imdb["role_summary"]
                if not og_out.get("description"):
                    og_out["description"] = imdb["role_summary"]

    out = {
        "url": url,
        "fetch_status": resp.status_code,
        "title": title_out,
        "meta_description": meta_out,
        "og": og_out,
        "json_ld": extract_json_ld(soup),
        "body_text_excerpt": extract_body_excerpt(soup),
        "web_search_override": fm["web_search_override"],
        "inbox_title": fm["inbox_title"],
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
