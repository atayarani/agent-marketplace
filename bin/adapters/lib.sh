#!/usr/bin/env bash
# Shared, harness-AGNOSTIC helpers for bin/adapters/<harness>.sh.
#
# Only meta.yaml access and the common {name,version,description} manifest
# projection live here — the things that would otherwise be copy-pasted into
# four adapters and drift. Anything harness-specific stays in <harness>.sh.
#
# Callers must set `repo_root` before sourcing.

: "${repo_root:?lib.sh: repo_root must be set before sourcing}"

# meta_get <meta.yaml> <field> -> scalar value on stdout (empty if absent/non-scalar)
meta_get() {
  python3 - "$1" "$2" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1])) or {}
v = m.get(sys.argv[2], "")
print(v if isinstance(v, (str, int, float)) else "")
PY
}

# installs_on <meta.yaml> <harness> -> exit 0 if this plugin targets the harness
# (default: all harnesses when `harnesses:` is absent)
installs_on() {
  python3 - "$1" "$2" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1])) or {}
h = m.get("harnesses")
sys.exit(0 if (h is None or sys.argv[2] in h) else 1)
PY
}

# is_alias <meta.yaml> -> exit 0 if alias_of is set (content is symlinks into another plugin)
is_alias() {
  python3 - "$1" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1])) or {}
sys.exit(0 if m.get("alias_of") else 1)
PY
}

# display_name <meta.yaml> -> explicit display_name, else titlecased name (snake_case -> spaced)
display_name() {
  python3 - "$1" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1])) or {}
print(m.get("display_name") or " ".join(w.capitalize() for w in str(m["name"]).split("_")))
PY
}

# gen_plugin_json <meta.yaml> <out.json> -> write {name,version,description}
# (the shape Claude and Codex both consume). Versions are stringified so a
# two-dot tag like 1.8.0 never round-trips through a YAML float.
gen_plugin_json() {
  python3 - "$1" "$2" <<'PY'
import sys, json, yaml, os
m = yaml.safe_load(open(sys.argv[1]))
obj = {"name": m["name"], "version": str(m["version"]), "description": m["description"]}
os.makedirs(os.path.dirname(sys.argv[2]), exist_ok=True)
with open(sys.argv[2], "w") as f:
    json.dump(obj, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}

# plugins_list [name] -> one plugin dir-name per line (all plugins, or just <name>)
plugins_list() {
  if [ -n "${1:-}" ]; then
    echo "$1"
  else
    local d
    for d in "$repo_root"/plugins/*/; do basename "$d"; done
  fi
}
