#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.27",
#   "pyyaml>=6.0",
# ]
# ///
"""Audit bm vault links: two-pass HEAD/GET checker.

Walks filed bookmarks under <collection>/*.md and _unsorted/*.md (excluding
files already marked `status: broken`). For each URL:

  Pass 1 — HEAD request, follow redirects, 10s timeout
  Pass 2 — GET retry for anything that failed Pass 1 (except 429 = bot-walled)

URLs that fail BOTH passes are `confirmed_broken`:
  - the bookmark file is git-moved to `_broken/`
  - its frontmatter `status: active` is flipped to `status: broken`
  - a `broken_at: <ISO>` field is appended

Everything else (bot-walled, transient) is reported but not moved.

The markdown report is printed to stdout (the bm:audit SKILL.md redirects
to --out PATH if requested). The report is NEVER written into the vault.

Usage:  audit_links.py <vault> [--concurrency N] [--timeout S]
                                [--dry-run] [--user-agent STR]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import yaml


FRONTMATTER_RE = re.compile(r"^(---\n)(.*?\n)(---\n)(.*)", re.DOTALL)
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ---------- vault walking ----------

def list_user_collections(vault: Path) -> list[Path]:
    out = []
    for child in sorted(vault.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        if child.name == "outputs":
            continue
        if not (child / "README.md").exists():
            continue
        out.append(child)
    return out


def collect_filed_bookmarks(vault: Path) -> list[Path]:
    out: list[Path] = []
    for coll in list_user_collections(vault):
        for p in coll.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    unsorted = vault / "_unsorted"
    if unsorted.is_dir():
        for p in unsorted.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    return out


def parse_frontmatter(path: Path) -> tuple[dict | None, str]:
    """Return (frontmatter_dict, full_file_text)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, ""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(2)) or {}
    except yaml.YAMLError:
        return None, text
    return fm, text


# ---------- HTTP classification ----------

@dataclass
class CheckResult:
    file: Path
    url: str
    pass1_status: int | None = None
    pass1_error: str | None = None
    pass2_status: int | None = None
    pass2_error: str | None = None
    bucket: str = "ok"  # ok | confirmed_broken | bot_walled | transient
    final_code: int | None = None
    final_error: str | None = None


def classify(status: int | None, err: str | None) -> str:
    """Classify a response into one of four buckets.

    Conservative on 4xx: only 404 / 410 / 451 are treated as "definitely dead"
    candidates. 401 / 403 / 429 are bot-walling signals (Cloudflare-fronted
    sites routinely 403 anything without a JS-capable browser); they're
    reported but never moved to _broken/. Everything else 4xx (weird codes
    like 400 / 405 / 406) is treated as transient — better to leave it
    alone than to false-positive an active bookmark.
    """
    if err is not None:
        return "candidate_transient"
    if status is None:
        return "candidate_transient"
    if 200 <= status < 400:
        return "ok"
    if status in (401, 403, 429):
        return "bot_walled"
    if status in (404, 410, 451):
        return "candidate_broken"
    if 400 <= status < 500:
        return "candidate_transient"
    if 500 <= status < 600:
        return "candidate_transient"
    return "candidate_transient"


async def request_once(
    client: httpx.AsyncClient,
    method: str,
    url: str,
) -> tuple[int | None, str | None]:
    try:
        resp = await client.request(method, url)
        return resp.status_code, None
    except httpx.TimeoutException:
        return None, "timeout"
    except httpx.ConnectError as e:
        return None, f"connect: {type(e).__name__}: {e}"
    except httpx.ReadError as e:
        return None, f"read: {type(e).__name__}: {e}"
    except httpx.NetworkError as e:
        return None, f"network: {type(e).__name__}: {e}"
    except httpx.TooManyRedirects:
        return None, "too-many-redirects"
    except httpx.UnsupportedProtocol as e:
        return None, f"unsupported-protocol: {e}"
    except httpx.HTTPError as e:
        return None, f"http: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 — defensive last-resort
        return None, f"other: {type(e).__name__}: {e}"


async def check_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    file: Path,
    url: str,
) -> CheckResult:
    r = CheckResult(file=file, url=url)
    async with sem:
        # Pass 1: HEAD
        r.pass1_status, r.pass1_error = await request_once(client, "HEAD", url)
        c1 = classify(r.pass1_status, r.pass1_error)
        if c1 == "ok":
            r.bucket = "ok"
            r.final_code = r.pass1_status
            return r
        if c1 == "bot_walled":
            r.bucket = "bot_walled"
            r.final_code = r.pass1_status
            return r
        # Pass 2: GET retry (some servers reject HEAD)
        r.pass2_status, r.pass2_error = await request_once(client, "GET", url)
        c2 = classify(r.pass2_status, r.pass2_error)
        if c2 == "ok":
            r.bucket = "ok"
            r.final_code = r.pass2_status
            return r
        if c2 == "bot_walled":
            r.bucket = "bot_walled"
            r.final_code = r.pass2_status
            return r
        if c2 == "candidate_broken":
            r.bucket = "confirmed_broken"
            r.final_code = r.pass2_status
            return r
        # c2 == candidate_transient: still ambiguous, do not move
        r.bucket = "transient"
        r.final_code = r.pass2_status
        r.final_error = r.pass2_error or r.pass1_error
        return r


# ---------- vault mutations ----------

def short_url_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:6]


def flip_to_broken(text: str, iso_now: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return text
    open_marker, fm_block, close_marker, body = m.groups()
    # Flip status: active → status: broken (replace whole status line if present)
    new_fm = re.sub(
        r"^status:[ \t]*\S+",
        "status: broken",
        fm_block,
        count=1,
        flags=re.MULTILINE,
    )
    if "status: broken" not in new_fm:
        # No status line at all — append one
        if not new_fm.endswith("\n"):
            new_fm += "\n"
        new_fm += "status: broken\n"
    # Append broken_at: <iso> if not already present
    if "broken_at:" not in new_fm:
        if not new_fm.endswith("\n"):
            new_fm += "\n"
        new_fm += f"broken_at: {iso_now}\n"
    return open_marker + new_fm + close_marker + body


def move_to_broken(vault: Path, src: Path, url: str) -> Path:
    broken = vault / "_broken"
    broken.mkdir(parents=True, exist_ok=True)
    target = broken / src.name
    if target.exists():
        stem, suffix = src.stem, src.suffix
        candidate = broken / f"{stem}-{short_url_hash(url)}{suffix}"
        n = 1
        while candidate.exists():
            n += 1
            candidate = broken / f"{stem}-{short_url_hash(url)}-{n}{suffix}"
        target = candidate

    try:
        src_rel = src.relative_to(vault)
        dst_rel = target.relative_to(vault)
        subprocess.run(
            ["git", "-C", str(vault), "mv", str(src_rel), str(dst_rel)],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, ValueError):
        # File not tracked, vault not a git repo, or path-relative failure.
        # Fall back to plain rename.
        target.parent.mkdir(parents=True, exist_ok=True)
        src.rename(target)
    return target


# ---------- reporting ----------

def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_(none)_\n"
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def render_failure_detail(r: CheckResult) -> str:
    bits = []
    if r.pass1_status is not None:
        bits.append(f"HEAD {r.pass1_status}")
    elif r.pass1_error:
        bits.append(f"HEAD {r.pass1_error}")
    if r.pass2_status is not None:
        bits.append(f"GET {r.pass2_status}")
    elif r.pass2_error:
        bits.append(f"GET {r.pass2_error}")
    return "; ".join(bits) if bits else "no response"


# ---------- main ----------

async def run_checks(
    targets: list[tuple[Path, str]],
    concurrency: int,
    timeout: float,
    user_agent: str,
) -> list[CheckResult]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    sem = asyncio.Semaphore(concurrency)
    timeout_cfg = httpx.Timeout(timeout, connect=timeout)
    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=timeout_cfg,
        verify=True,
        http2=False,
    ) as client:
        coros = [check_one(client, sem, f, u) for f, u in targets]
        return await asyncio.gather(*coros)


def main() -> int:
    p = argparse.ArgumentParser(prog="audit_links.py")
    p.add_argument("vault")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--user-agent", default=DEFAULT_UA)
    p.add_argument("--limit", type=int, default=0, help="cap targets (for testing); 0 = no cap")
    args = p.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    bookmarks = collect_filed_bookmarks(vault)
    targets: list[tuple[Path, str]] = []
    skipped_no_url = 0
    skipped_already_broken = 0
    skipped_non_http = 0
    for bm in bookmarks:
        fm, _ = parse_frontmatter(bm)
        if not fm:
            continue
        if fm.get("status") == "broken":
            skipped_already_broken += 1
            continue
        url = fm.get("url")
        if not url or not isinstance(url, str):
            skipped_no_url += 1
            continue
        if not re.match(r"^https?://", url):
            skipped_non_http += 1
            continue
        targets.append((bm, url))

    if args.limit > 0:
        targets = targets[: args.limit]

    if not targets:
        print(f"# bm:audit links — {date.today().isoformat()}")
        print()
        print(f"Vault: `{vault}`")
        print()
        print("No active http(s) bookmarks to check.")
        print()
        print(f"- Skipped (already `status: broken`): {skipped_already_broken}")
        print(f"- Skipped (no url field):              {skipped_no_url}")
        print(f"- Skipped (non-http/https url):        {skipped_non_http}")
        return 0

    print(
        f"audit_links: checking {len(targets)} urls "
        f"(concurrency={args.concurrency}, timeout={args.timeout}s, dry_run={args.dry_run})",
        file=sys.stderr,
    )

    results = asyncio.run(run_checks(
        targets, args.concurrency, args.timeout, args.user_agent,
    ))

    ok = [r for r in results if r.bucket == "ok"]
    confirmed = [r for r in results if r.bucket == "confirmed_broken"]
    bot_walled = [r for r in results if r.bucket == "bot_walled"]
    transient = [r for r in results if r.bucket == "transient"]

    # Apply mutations for confirmed_broken (unless dry-run)
    iso_now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    moved: list[tuple[CheckResult, Path]] = []
    for r in confirmed:
        if args.dry_run:
            moved.append((r, vault / "_broken" / r.file.name))
            continue
        try:
            text = r.file.read_text(encoding="utf-8")
            new_text = flip_to_broken(text, iso_now)
            r.file.write_text(new_text, encoding="utf-8")
        except OSError as e:
            print(f"warning: could not edit frontmatter {r.file}: {e}", file=sys.stderr)
        try:
            new_path = move_to_broken(vault, r.file, r.url)
            moved.append((r, new_path))
        except OSError as e:
            print(f"warning: could not move {r.file} to _broken/: {e}", file=sys.stderr)
            moved.append((r, r.file))

    # ----- report -----
    today = date.today().isoformat()
    print(f"# bm:audit links — {today}")
    print()
    print(f"Vault: `{vault}`")
    if args.dry_run:
        print()
        print("**Mode:** `--dry-run` (no files moved, no frontmatter edited)")
    print()
    print(f"- URLs checked:           **{len(results)}**")
    print(f"- OK (2xx/3xx):           **{len(ok)}**")
    print(f"- Confirmed broken:       **{len(confirmed)}**" + (
        "  _(moved to `_broken/`, `status: broken`)_" if not args.dry_run and confirmed
        else ""
    ))
    print(f"- Bot-walled (401/403/429): **{len(bot_walled)}**")
    print(f"- Transient (5xx/timeout):  **{len(transient)}**")
    print()
    print(f"- Skipped (already broken): {skipped_already_broken}")
    print(f"- Skipped (no url):         {skipped_no_url}")
    print(f"- Skipped (non-http):       {skipped_non_http}")
    print()

    # Broken table
    print("## Broken" + ("" if args.dry_run else " (moved to `_broken/`)"))
    print()
    broken_rows = []
    for r, new_path in moved:
        try:
            new_rel = new_path.relative_to(vault)
        except ValueError:
            new_rel = new_path
        broken_rows.append([
            r.url,
            f"`{new_rel}`",
            r.final_code if r.final_code is not None else (r.final_error or "—"),
            render_failure_detail(r),
        ])
    print(md_table(["URL", "Path" + (" (would move to)" if args.dry_run else ""), "Status", "Failure detail"], broken_rows))

    # Bot-walled
    print("## Bot-walled (not moved — manual triage)")
    print()
    bw_rows = []
    for r in bot_walled:
        try:
            rel = r.file.relative_to(vault)
        except ValueError:
            rel = r.file
        bw_rows.append([
            r.url,
            f"`{rel}`",
            f"HTTP {r.final_code}" if r.final_code else (r.final_error or "—"),
        ])
    print(md_table(["URL", "Path", "Reason"], bw_rows))

    # Transient
    print("## Transient failures (not moved — recheck on next audit)")
    print()
    tr_rows = []
    for r in transient:
        try:
            rel = r.file.relative_to(vault)
        except ValueError:
            rel = r.file
        tr_rows.append([
            r.url,
            f"`{rel}`",
            render_failure_detail(r),
        ])
    print(md_table(["URL", "Path", "Error"], tr_rows))

    return 0


if __name__ == "__main__":
    sys.exit(main())
