#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.27",
#   "beautifulsoup4>=4.12",
#   "ruamel.yaml>=0.18",
# ]
# ///
"""One-off: backfill `og_image:` on filed bookmarks that don't have one.

Walks filed bookmarks under <collection>/, _unsorted/, _broken/. For each
file missing `og_image:` in frontmatter, fetches its URL, parses the page
for `<meta property="og:image">` (and `og:image:url` as a fallback),
resolves relative URLs against the page's final URL, and writes the result
into the bookmark's frontmatter via ruamel.yaml (preserving the existing
layout).

Idempotent: re-running skips files that already have og_image set.

Usage:  backfill_og_image.py <vault> [--dry-run] [--concurrency N]
                                     [--timeout S] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import io
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from ruamel.yaml import YAML


FRONTMATTER_RE = re.compile(r"^(---\n)(.*?\n)(---\n)(.*)", re.DOTALL)
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def yaml_rt() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 9999
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def collect_filed_bookmarks(vault: Path) -> list[Path]:
    out: list[Path] = []
    for child in sorted(vault.iterdir()):
        if not child.is_dir():
            continue
        if child.name in ("_unsorted", "_broken"):
            for p in child.glob("*.md"):
                if p.name != "README.md":
                    out.append(p)
            continue
        if child.name.startswith("_"):
            continue
        if child.name == "outputs":
            continue
        if not (child / "README.md").exists():
            continue
        for p in child.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    return out


def parse_bookmark(path: Path) -> tuple[dict | None, str]:
    """Return (frontmatter, full_text). frontmatter is None if malformed."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, ""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    yaml = yaml_rt()
    try:
        fm = yaml.load(m.group(2))
    except Exception:
        return None, text
    return fm, text


def extract_og_image(html: str, base_url: str) -> str:
    """Parse `<meta property="og:image">` / og:image:url. Resolve relative URLs."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    candidates: list[str] = []
    for tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:image(?::url)?$")}):
        content = (tag.get("content") or "").strip()
        if content:
            candidates.append(content)
    for c in candidates:
        if c.startswith("data:"):
            continue
        # Resolve relative to base
        try:
            return urljoin(base_url, c)
        except ValueError:
            continue
    return ""


def write_og_image(path: Path, og_image: str) -> bool:
    """Insert `og_image: "<url>"` into frontmatter. Idempotent — skip if present."""
    yaml = yaml_rt()
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    open_marker, fm_block, close_marker, body = m.groups()
    fm = yaml.load(fm_block)
    if fm is None:
        return False
    if fm.get("og_image"):
        return False  # already set
    fm["og_image"] = og_image
    buf = io.StringIO()
    yaml.dump(fm, buf)
    path.write_text(open_marker + buf.getvalue() + close_marker + body, encoding="utf-8")
    return True


async def fetch_og(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str) -> tuple[str, str | None]:
    """Return (og_image_url, error). og_image_url is "" if not found."""
    async with sem:
        try:
            resp = await client.get(url)
        except httpx.TimeoutException:
            return "", "timeout"
        except httpx.HTTPError as e:
            return "", f"http: {type(e).__name__}"
        except Exception as e:  # noqa: BLE001
            return "", f"other: {type(e).__name__}"
        if resp.status_code == 429:
            return "", "rate-limited (429)"
        if resp.status_code >= 400:
            return "", f"status {resp.status_code}"
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "html" not in content_type:
            return "", "not html"
        try:
            html = resp.text
        except Exception:
            return "", "decode error"
        return extract_og_image(html, str(resp.url)), None


async def run_async(
    targets: list[tuple[Path, str]],
    concurrency: int,
    timeout: float,
) -> list[tuple[Path, str, str, str | None]]:
    """Return [(path, url, og_image_or_blank, error_or_None)]."""
    headers = {"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    sem = asyncio.Semaphore(concurrency)
    timeout_cfg = httpx.Timeout(timeout, connect=timeout)
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=timeout_cfg,
    ) as client:
        coros = [fetch_og(client, sem, url) for _, url in targets]
        results = await asyncio.gather(*coros)
    return [(p, u, og, err) for (p, u), (og, err) in zip(targets, results)]


def main() -> int:
    p = argparse.ArgumentParser(prog="backfill_og_image.py")
    p.add_argument("vault")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--limit", type=int, default=0,
                   help="cap targets (0 = no cap)")
    args = p.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    bookmarks = collect_filed_bookmarks(vault)
    targets: list[tuple[Path, str]] = []
    skipped_already_set = 0
    skipped_no_url = 0
    for bm in bookmarks:
        fm, _ = parse_bookmark(bm)
        if not fm:
            continue
        if fm.get("og_image"):
            skipped_already_set += 1
            continue
        url = fm.get("url")
        if not url or not isinstance(url, str) or not re.match(r"^https?://", url):
            skipped_no_url += 1
            continue
        targets.append((bm, url))

    if args.limit > 0:
        targets = targets[: args.limit]

    print(
        f"backfill_og_image: scanned {len(bookmarks)} bookmarks; "
        f"already_set={skipped_already_set} no_url={skipped_no_url} "
        f"to_fetch={len(targets)}"
        + (" [DRY-RUN]" if args.dry_run else ""),
        file=sys.stderr,
    )
    if not targets:
        return 0

    if args.dry_run:
        for path, url in targets[:20]:
            print(f"  would fetch: {path.relative_to(vault)}  ({url})")
        if len(targets) > 20:
            print(f"  …and {len(targets) - 20} more")
        return 0

    results = asyncio.run(run_async(targets, args.concurrency, args.timeout))
    written = 0
    no_og = 0
    errors: dict[str, int] = {}
    for path, url, og_image, err in results:
        if err:
            errors[err] = errors.get(err, 0) + 1
            continue
        if not og_image:
            no_og += 1
            continue
        try:
            if write_og_image(path, og_image):
                written += 1
        except OSError as e:
            print(f"warning: write failed for {path}: {e}", file=sys.stderr)

    print()
    print(f"backfill_og_image: written={written}  no_og_tag={no_og}  errors={sum(errors.values())}")
    if errors:
        print("error breakdown:")
        for k, n in sorted(errors.items(), key=lambda x: -x[1]):
            print(f"  {k}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
