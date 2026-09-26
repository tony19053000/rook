#!/usr/bin/env bash
# Pack the locally installed Bob Shell into the gitignored deploy/vendor/ for a live-mode image.
#   deploy/pack-bob.sh [path/to/node_modules/bobshell]
# Never commit the result (Bob's licence is unknown); .gitignore covers deploy/vendor/*.
set -euo pipefail

want=2.0.5
src=${1:-$HOME/.nvm/versions/node/v24.21.0/lib/node_modules/bobshell}
here=$(cd "$(dirname "$0")" && pwd)
out="$here/vendor/bobshell-$want.tgz"

[[ -f "$src/package.json" && -f "$src/dist/bob.js" ]] || { echo "no Bob Shell at $src" >&2; exit 1; }
version=$(sed -n 's/^ *"version": *"\([^"]*\)".*/\1/p' "$src/package.json" | head -n 1)
[[ "$version" == "$want" ]] || { echo "Bob Shell at $src is $version, expected $want" >&2; exit 1; }

mkdir -p "$here/vendor"
tar -czf "$out" -C "$(dirname "$src")" --owner=0 --group=0 "$(basename "$src")"
(cd "$here/vendor" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
echo "packed Bob Shell $version -> $out ($(du -h "$out" | cut -f1))"
