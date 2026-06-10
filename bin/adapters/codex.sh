#!/usr/bin/env bash
# Codex adapter — one of bin/adapters/<harness>.sh.
#
#   bin/adapters/codex.sh <build|install|uninstall> [plugin]
#
#   build      Generate, from meta.yaml:
#                - plugins/<name>/.codex-plugin/plugin.json  (per plugin)
#                - .agents/plugins/marketplace.json           (the local catalog)
#              Pure function of the working tree — no $HOME writes, no `codex` needed.
#   install    build, then register the marketplace and add each plugin:
#                codex plugin marketplace add "$repo_root"
#                codex plugin add <name>@agent-marketplace   (per plugin)
#              Codex reads the catalog, resolves each source.path relative to the
#              catalog root, and COPIES the plugin into its cache (snapshot — not a
#              live symlink, so edits need a re-add to take effect).
#   uninstall  codex plugin remove <name>@agent-marketplace  (per plugin), then
#              codex plugin marketplace remove agent-marketplace (only on full uninstall).
#
# VERIFIED against codex-cli 0.139.0 in a sandboxed CODEX_HOME (this machine does
# have codex, contrary to REDESIGN-PLAN's assumption): the catalog schema below is
# accepted, paths resolve, and versions flow from .codex-plugin/plugin.json.
#
# ALIAS PLUGINS ARE SKIPPED (e.g. bookmark -> bm). Verified empirically: Codex
# COPIES each plugin into its cache, and bookmark's content is relative symlinks
# (agents/commands/skills/server -> ../bm/...). Those point outside the copied
# tree, so the copy drops them and bookmark lands as an empty shell. This is the
# same conclusion as REDESIGN-PLAN §2 ("one entry per non-alias plugin"), for a
# mechanism reason: copy-install can't carry symlinked content. (Claude keeps the
# alias because it discovers a whole-dir symlink in place; see HARNESS-NOTES.)

set -euo pipefail

HARNESS=codex
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
source "$(dirname "$0")/lib.sh"

build_one() {
  local name=$1
  gen_plugin_json "$repo_root/plugins/$name/meta.yaml" \
                  "$repo_root/plugins/$name/.codex-plugin/plugin.json"
  echo "codex: built $name/.codex-plugin/plugin.json"
}

build_catalog() {
  python3 - "$repo_root" <<'PY'
import sys, os, glob, json, yaml
root = sys.argv[1]
plugins = []
for meta_path in sorted(glob.glob(os.path.join(root, "plugins", "*", "meta.yaml"))):
    m = yaml.safe_load(open(meta_path)) or {}
    name = m["name"]
    if m.get("alias_of"):
        continue   # copy-install drops the symlinked content; skip (see header)
    h = m.get("harnesses")
    if h is not None and "codex" not in h:
        continue
    dn = m.get("display_name") or " ".join(w.capitalize() for w in str(name).split("_"))
    plugins.append({
        "name": name,
        # Local source: Codex resolves source.path relative to the catalog root.
        "source": {"source": "local", "path": f"./plugins/{name}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "interface": {"displayName": dn},
    })
out = os.path.join(root, ".agents", "plugins", "marketplace.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump({"name": "agent-marketplace", "plugins": plugins}, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"codex: built .agents/plugins/marketplace.json ({len(plugins)} plugins: "
      + ", ".join(p["name"] for p in plugins) + ")")
PY
}

MKT=agent-marketplace   # must match the catalog's top-level "name"

require_codex() {
  if ! command -v codex >/dev/null 2>&1; then
    echo "codex: 'codex' CLI not found — generated manifests are ready, but" >&2
    echo "       install/uninstall need Codex. Run on a machine with codex:" >&2
    echo "         codex plugin marketplace add \"$repo_root\"" >&2
    echo "         codex plugin add <name>@$MKT" >&2
    return 1
  fi
}

cmd=${1:-}
target=${2:-}
case "$cmd" in
  build|install|uninstall) ;;
  *) echo "usage: $(basename "$0") <build|install|uninstall> [plugin]" >&2; exit 2 ;;
esac

# Resolve the codex-targeted plugin set once (honoring `harnesses` + optional target).
targets=()
while IFS= read -r name; do
  [ -n "$name" ] || continue
  meta_path="$repo_root/plugins/$name/meta.yaml"
  [ -f "$meta_path" ] || { echo "codex: skip $name — no meta.yaml" >&2; continue; }
  if is_alias "$meta_path"; then
    echo "codex: skip $name — alias plugin (copy-install can't carry its symlinks)"; continue
  fi
  if ! installs_on "$meta_path" "$HARNESS"; then
    echo "codex: skip $name — harnesses excludes $HARNESS"; continue
  fi
  targets+=("$name")
done < <(plugins_list "$target")

# Per-plugin manifests for the targets, plus the always-whole-repo catalog (one
# source.path per plugin), so a scoped target never leaves the catalog partial.
if [ ${#targets[@]} -gt 0 ]; then
  for name in "${targets[@]}"; do build_one "$name"; done
fi
build_catalog

case "$cmd" in
  install)
    require_codex || exit 0
    codex plugin marketplace add "$repo_root" || true   # idempotent: reports alreadyAdded
    if [ ${#targets[@]} -gt 0 ]; then
      for name in "${targets[@]}"; do
        codex plugin add "$name@$MKT" \
          || echo "codex: warn — 'codex plugin add $name@$MKT' failed (already installed?)" >&2
      done
      echo "codex: installed ${targets[*]}"
    fi
    ;;
  uninstall)
    require_codex || exit 0
    if [ ${#targets[@]} -gt 0 ]; then
      for name in "${targets[@]}"; do
        codex plugin remove "$name@$MKT" 2>/dev/null || true
      done
    fi
    if [ -z "$target" ]; then
      codex plugin marketplace remove "$MKT" 2>/dev/null || true
      echo "codex: removed plugins + marketplace '$MKT'"
    else
      echo "codex: removed plugin '$target' (marketplace '$MKT' left registered)"
    fi
    ;;
esac
