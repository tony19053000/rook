#!/usr/bin/env bash
# Clone and pre-build the demo apps listed in repos.txt (run at image build time, as root, network on).
#   build-demos.sh <repos.txt> <dest-dir>
# Each non-comment line: <owner/name> <40-char commit SHA> <https git URL> <recipe>
# recipe: none | npm (npm ci) | go (go build ./...) | uv (uv sync --frozen)
# The checkout is verified against the pinned SHA; the app lands in <dest-dir>/<name>, which must match the
# `app_dir` of its allowlist.yaml entry.
set -euo pipefail

manifest=$1
dest=$2
mkdir -p "$dest"

while read -r ref sha url recipe extra; do
    [[ -z "${ref:-}" || "$ref" == \#* ]] && continue
    if [[ -n "${extra:-}" || -z "${recipe:-}" ]]; then
        echo "bad line in $manifest for $ref: want '<owner/name> <sha> <url> <recipe>'" >&2
        exit 1
    fi
    [[ "$ref" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "bad repo ref: $ref" >&2; exit 1; }
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "$ref: the commit must be a full 40-char SHA" >&2; exit 1; }
    [[ "$url" == https://* ]] || { echo "$ref: only https git URLs" >&2; exit 1; }
    name=${ref#*/}
    app="$dest/$name"
    echo "demo $ref@$sha -> $app ($recipe)"
    git init -q "$app"
    git -C "$app" fetch -q --depth 1 "$url" "$sha"
    git -C "$app" -c advice.detachedHead=false checkout -q FETCH_HEAD
    head=$(git -C "$app" rev-parse HEAD)
    [[ "$head" == "$sha" ]] || { echo "$ref: checked out $head, pinned $sha" >&2; exit 1; }
    rm -rf "$app/.git"
    case "$recipe" in
        none) ;;
        npm) (cd "$app" && npm ci --no-audit --no-fund) ;;
        go) (cd "$app" && go build ./...) ;;
        uv) (cd "$app" && uv sync --frozen) ;;
        *) echo "$ref: unknown recipe '$recipe'" >&2; exit 1 ;;
    esac
done < "$manifest"
