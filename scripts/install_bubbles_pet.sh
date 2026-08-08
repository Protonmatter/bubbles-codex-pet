#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${1:-$repo_root/bubbles}"
codex_root="${CODEX_HOME:-$HOME/.codex}"
target_dir="${2:-$codex_root/pets/bubbles}"

python3 "$repo_root/scripts/verify_bubbles_pet.py" "$source_dir"
mkdir -p "$(dirname "$target_dir")"
staging_dir="$(mktemp -d "${target_dir}.install.XXXXXX")"
backup=""
cleanup() {
  [[ ! -d "$staging_dir" ]] || rm -r "$staging_dir"
}
trap cleanup EXIT
cp -R "$source_dir"/. "$staging_dir"/
if [[ -e "$target_dir" ]]; then
  backup_base="${target_dir}.backup.$(date -u +%Y%m%dT%H%M%SZ).$$"
  backup="$backup_base"
  suffix=0
  while [[ -e "$backup" ]]; do
    suffix=$((suffix + 1))
    backup="${backup_base}.${suffix}"
  done
  mv "$target_dir" "$backup"
  echo "Existing Bubbles pet moved to $backup"
fi
if ! mv "$staging_dir" "$target_dir"; then
  if [[ -n "$backup" && -e "$backup" && ! -e "$target_dir" ]]; then
    mv "$backup" "$target_dir"
  fi
  echo "Installation failed; previous Bubbles pet restored" >&2
  exit 1
fi
echo "Installed Bubbles at $target_dir"
