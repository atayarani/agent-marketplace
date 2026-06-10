#!/usr/bin/env bash
# Retired. Gemini farm generation moved to bin/adapters/gemini.sh, which adds the
# alias_of / harnesses skip (so the farm is rebuildable again instead of aborting
# on the bm collisions). Kept as a thin shim for muscle memory and old docs.
exec "$(dirname "$0")/adapters/gemini.sh" build
