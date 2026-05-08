#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "youtube-transcript-api>=1.0.0",
# ]
# ///
"""Fetch a YouTube transcript by URL or video id.

Self-bootstraps via uv's PEP 723 inline script metadata, so the only
prerequisite on the host is `uv`. No global install of
`youtube-transcript-api` is needed.

Resilience: the standard `youtube-transcript-api` path can hit YouTube
IP-blocks after heavy use. When that happens (and `yt-dlp` is on PATH),
the script falls back to `yt-dlp --write-auto-subs` to fetch caption
VTT directly via the YouTube web player API — different infrastructure,
typically not subject to the same blocks. The VTT is then parsed,
deduped (auto-caption VTT contains alternating animation/stable cue
pairs), and formatted to match the API path's output. Pass
`--no-fallback` to disable.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
from youtube_transcript_api.formatters import (
    JSONFormatter,
    SRTFormatter,
    TextFormatter,
    WebVTTFormatter,
)

# IP-block exception classes vary across youtube-transcript-api versions.
# Fall back to string-matching on the error message if the imports fail.
try:
    from youtube_transcript_api._errors import IpBlocked, RequestBlocked  # type: ignore

    _IP_BLOCK_EXCS: tuple = (IpBlocked, RequestBlocked)
except ImportError:
    _IP_BLOCK_EXCS = ()

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PATH_KEYS = {"shorts", "embed", "v", "live"}


def extract_video_id(s: str) -> str:
    s = s.strip()
    if VIDEO_ID_RE.match(s):
        return s

    u = urlparse(s if "://" in s else f"https://{s}")
    host = (u.hostname or "").lower()

    if host.endswith("youtu.be"):
        candidate = u.path.lstrip("/").split("/", 1)[0]
        if VIDEO_ID_RE.match(candidate):
            return candidate

    if "youtube" in host:
        qs = parse_qs(u.query)
        if "v" in qs and VIDEO_ID_RE.match(qs["v"][0]):
            return qs["v"][0]
        parts = [p for p in u.path.split("/") if p]
        for i, p in enumerate(parts[:-1]):
            if p in PATH_KEYS and VIDEO_ID_RE.match(parts[i + 1]):
                return parts[i + 1]

    raise SystemExit(f"could not extract YouTube video id from: {s}")


def list_transcripts(api: YouTubeTranscriptApi, video_id: str) -> None:
    transcript_list = api.list(video_id)
    for t in transcript_list:
        kind = "auto-generated" if t.is_generated else "manual"
        translatable = ", translatable" if t.is_translatable else ""
        print(f"{t.language_code}\t{t.language} ({kind}{translatable})")


# ---- yt-dlp VTT fallback -----------------------------------------------------


def _is_ip_block_error(exc: Exception) -> bool:
    """Detect IP-block / request-blocked errors. Tries exception type first,
    falls back to message-matching on the error string."""
    if _IP_BLOCK_EXCS and isinstance(exc, _IP_BLOCK_EXCS):
        return True
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "blocking requests from your ip",
            "ipblocked",
            "requestblocked",
            "ip has been blocked",
        )
    )


def _parse_vtt_timestamp(s: str) -> float:
    """Parse a VTT timestamp (HH:MM:SS.mmm) into seconds."""
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def _parse_vtt(vtt_text: str) -> list[tuple[str, float, float]]:
    """Parse a YouTube auto-caption VTT into [(text, start, duration)] tuples.

    YouTube auto-caption VTT files contain alternating cue pairs: an
    animation cue with word-level <c>...</c> tags, then a stable cue with
    the plain text only. This parser strips the inline tags and dedups
    consecutive identical lines so callers see one segment per stable cue.
    """
    timestamp_re = re.compile(r"^(\d+:\d+:\d+\.\d+)\s+-->\s+(\d+:\d+:\d+\.\d+)")
    tag_re = re.compile(r"<[^>]+>")

    cues: list[tuple[float, float, str]] = []
    cur_start: float | None = None
    cur_end: float | None = None
    cur_lines: list[str] = []

    def _flush() -> None:
        # YouTube auto-caption VTT animation cues contain *two* text lines:
        #   line 1: the previous stable line (still on-screen during the
        #           karaoke-highlight effect)
        #   line 2: the new animation chunk (with word-level <c> tags that
        #           were stripped before this point)
        # Stable cues contain a single text line. Taking the last non-empty
        # line of each cue gives us the new content in both cases — and the
        # consecutive-dedup pass below collapses the resulting (animation,
        # stable) duplicates into one segment.
        nonlocal cur_start, cur_end, cur_lines
        if cur_start is not None and cur_lines:
            text = cur_lines[-1].strip()
            if text:
                cues.append((cur_start, cur_end if cur_end is not None else cur_start, text))
        cur_start = None
        cur_end = None
        cur_lines = []

    for line in vtt_text.splitlines():
        # VTT header lines
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        # Empty line ends a cue block
        if not line.strip():
            _flush()
            continue
        # Timestamp line opens / re-opens a cue
        m = timestamp_re.match(line)
        if m:
            # If a previous cue's text is still buffered, flush it first.
            _flush()
            cur_start = _parse_vtt_timestamp(m.group(1))
            cur_end = _parse_vtt_timestamp(m.group(2))
            continue
        # Cue text line — strip inline word-level tags
        cleaned = tag_re.sub("", line).strip()
        if cleaned:
            cur_lines.append(cleaned)
    _flush()

    # Dedup consecutive identical text (the animation/stable cue pair)
    deduped: list[tuple[float, float, str]] = []
    last_text: str | None = None
    for start, end, text in cues:
        if text != last_text:
            deduped.append((start, end, text))
            last_text = text

    return [(text, start, end - start) for start, end, text in deduped]


class _FallbackSnippet:
    """A FetchedTranscriptSnippet stand-in for the fallback path."""

    def __init__(self, text: str, start: float, duration: float) -> None:
        self.text = text
        self.start = start
        self.duration = duration


class _FallbackTranscript:
    """A FetchedTranscript stand-in that quacks like the API's return type
    well enough for the JSON / SRT / VTT / Text formatters to consume."""

    def __init__(
        self,
        snippets: list[_FallbackSnippet],
        video_id: str,
        language_code: str,
    ) -> None:
        self.snippets = snippets
        self.video_id = video_id
        self.language = language_code
        self.language_code = language_code
        self.is_generated = True

    def __iter__(self):
        return iter(self.snippets)

    def to_raw_data(self) -> list[dict]:
        return [
            {"text": s.text, "start": s.start, "duration": s.duration}
            for s in self.snippets
        ]


def _try_yt_dlp_fallback(
    video_id: str, languages: list[str]
) -> _FallbackTranscript | None:
    """Fetch auto-captions via yt-dlp as a fallback for IP-blocked API requests.

    Returns a _FallbackTranscript (compatible with the formatters) on success,
    or None if yt-dlp isn't installed, the captions don't exist in the
    requested languages, or any other failure.
    """
    if not shutil.which("yt-dlp"):
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--sub-langs", ",".join(languages),
            "--sub-format", "vtt",
            "--no-write-playlist-metafiles",
            "-o", "%(id)s",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            result = subprocess.run(
                cmd, cwd=tmpdir, capture_output=True, text=True, timeout=60
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if result.returncode != 0:
            return None

        # Find the .vtt that was written. yt-dlp names it <id>.<lang>.vtt
        # but if multiple langs were requested, just take the first .vtt found.
        vtt_files = sorted(Path(tmpdir).glob(f"{video_id}*.vtt"))
        if not vtt_files:
            return None

        vtt_path = vtt_files[0]
        try:
            vtt_text = vtt_path.read_text()
        except OSError:
            return None

        # Recover the language code from the filename: <id>.<lang>.vtt → <lang>
        stem_parts = vtt_path.stem.split(".")
        lang_code = stem_parts[-1] if len(stem_parts) >= 2 else languages[0]

        segments = _parse_vtt(vtt_text)
        if not segments:
            return None

        snippets = [
            _FallbackSnippet(text, start, duration)
            for text, start, duration in segments
        ]
        return _FallbackTranscript(snippets, video_id, lang_code)


# ---- main --------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        description="Fetch a YouTube transcript by URL or video id.",
    )
    p.add_argument("source", help="YouTube URL or 11-character video id")
    p.add_argument(
        "--languages",
        nargs="+",
        default=["en"],
        help="language codes to try in order (default: en)",
    )
    p.add_argument(
        "--format",
        choices=["text", "json", "srt", "vtt"],
        default="text",
        help="output format (default: text)",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="list available transcripts and exit",
    )
    p.add_argument(
        "--no-fallback",
        action="store_true",
        help="disable the yt-dlp VTT fallback path that activates on IP-block errors",
    )
    args = p.parse_args()

    video_id = extract_video_id(args.source)
    api = YouTubeTranscriptApi()

    fetched: object
    try:
        if args.list:
            list_transcripts(api, video_id)
            return 0

        fetched = api.fetch(video_id, languages=args.languages)
    except NoTranscriptFound as e:
        print(
            f"no transcript in {args.languages} for {video_id}; "
            f"run with --list to see what is available: {e}",
            file=sys.stderr,
        )
        return 2
    except TranscriptsDisabled:
        print(f"transcripts are disabled for {video_id}", file=sys.stderr)
        return 3
    except VideoUnavailable:
        print(f"video {video_id} is unavailable", file=sys.stderr)
        return 4
    except CouldNotRetrieveTranscript as e:
        if args.no_fallback or not _is_ip_block_error(e):
            print(
                f"could not retrieve transcript for {video_id}: {e}",
                file=sys.stderr,
            )
            return 5
        # IP-block detected — try yt-dlp fallback
        print(
            f"note: youtube-transcript-api hit an IP-block for {video_id}; "
            "falling back to yt-dlp VTT extraction",
            file=sys.stderr,
        )
        fetched = _try_yt_dlp_fallback(video_id, args.languages)
        if fetched is None:
            if not shutil.which("yt-dlp"):
                print(
                    "yt-dlp is not installed; install it (e.g. `brew install yt-dlp`) "
                    "or rerun later when the IP-block clears",
                    file=sys.stderr,
                )
            else:
                print(
                    "yt-dlp fallback also failed (no captions, video unavailable, "
                    "or other yt-dlp error)",
                    file=sys.stderr,
                )
            print(
                f"could not retrieve transcript for {video_id}: {e}",
                file=sys.stderr,
            )
            return 5

    formatters = {
        "text": TextFormatter(),
        "json": JSONFormatter(),
        "srt": SRTFormatter(),
        "vtt": WebVTTFormatter(),
    }
    output = formatters[args.format].format_transcript(fetched)
    sys.stdout.write(output if output.endswith("\n") else output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
