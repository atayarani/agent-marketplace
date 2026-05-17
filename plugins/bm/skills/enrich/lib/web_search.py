#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
"""Fetch web-search snippets for a URL as supplementary context for /bm:enrich.

Usage: web_search.py <url>

Reads TAVILY_API_KEY from env. Prints JSON to stdout:
  {
    "url":      "<input url>",
    "snippets": ["...", "..."],   # up to 5
    "backend":  "tavily"
  }

Exits non-zero on missing API key or fetch failure. Stderr carries the error.
The parent skill treats non-zero exit as "no snippets available" — never crash
the enrich loop on search failure.
"""
from __future__ import annotations

import json
import os
import sys

import httpx

API_KEY = os.environ.get("TAVILY_API_KEY")
TIMEOUT = 10.0
MAX_SNIPPETS = 5
SNIPPET_MAX_CHARS = 500
ENDPOINT = "https://api.tavily.com/search"


def search_tavily(url: str) -> list[str]:
    """Query Tavily search for the URL. Return up to MAX_SNIPPETS snippets."""
    if not API_KEY:
        print("error: TAVILY_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    resp = httpx.post(
        ENDPOINT,
        json={
            "api_key": API_KEY,
            "query": url,
            "max_results": MAX_SNIPPETS,
            "include_answer": False,
            "include_raw_content": False,
            "search_depth": "basic",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        (r.get("content") or "")[:SNIPPET_MAX_CHARS]
        for r in (data.get("results") or [])[:MAX_SNIPPETS]
    ]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: web_search.py <url>", file=sys.stderr)
        return 2
    url = sys.argv[1]
    try:
        snippets = search_tavily(url)
    except httpx.HTTPError as e:
        print(f"error: search failed: {e}", file=sys.stderr)
        return 1
    except (ValueError, KeyError) as e:
        # json.JSONDecodeError is a ValueError subclass. KeyError covers
        # unexpected payload shapes from the backend.
        print(f"error: malformed Tavily response: {e}", file=sys.stderr)
        return 1
    json.dump(
        {"url": url, "snippets": snippets, "backend": "tavily"},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
