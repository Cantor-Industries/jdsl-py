#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
output_path=${1:-"$repo_root/jdsl-linux-x64.tar.gz"}

if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [output-tarball-path]\n' "$0" >&2
    exit 2
fi

output_dir=$(dirname -- "$output_path")
if [[ ! -d "$output_dir" ]]; then
    printf 'Output directory does not exist: %s\n' "$output_dir" >&2
    exit 1
fi

tmp_dir=$(mktemp -d)
staged_output="$output_dir/.jdsl-linux-x64.tar.gz.$$"
cleanup() {
    rm -rf "$tmp_dir"
    rm -f "$staged_output"
}
trap cleanup EXIT

stage="$tmp_dir/stage"
mkdir -p "$stage/bin" "$stage/lib"
cp "$script_dir/jdsl-linux-launcher" "$stage/bin/jdsl"
chmod 755 "$stage/bin/jdsl"
cp -a "$repo_root/jdsl" "$repo_root/jdsl_harness" "$stage/lib/"
find "$stage" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$stage" -type f -name '*.pyc' -delete

archive="$tmp_dir/jdsl-linux-x64.tar.gz"
tar -czf "$archive" -C "$stage" bin lib
tar -tzf "$archive" >/dev/null

(
    cd "$repo_root"
    uv run python "$stage/bin/jdsl" --help >/dev/null
)

cp "$archive" "$staged_output"
mv -f "$staged_output" "$output_path"
printf 'Built %s\n' "$output_path"
sha256sum "$output_path"