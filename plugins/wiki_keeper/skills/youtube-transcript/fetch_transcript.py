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
"""

from __future__ import annotations

import argparse
import re
import sys
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
    args = p.parse_args()

    video_id = extract_video_id(args.source)
    api = YouTubeTranscriptApi()

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
        print(f"could not retrieve transcript for {video_id}: {e}", file=sys.stderr)
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
