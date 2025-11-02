#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <worktree-path>" >&2
  exit 1
fi

wt="$1"

# Normalize path
wt="$(cd "$wt" 2>/dev/null && pwd || echo "$wt")"

if [[ ! -d "$wt/.git" && ! -f "$wt/.git" ]]; then
  echo "Error: '$wt' does not look like a git worktree (no .git present)." >&2
  exit 2
fi

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$root" ]]; then
  # Fallback: try to resolve from worktree
  if [[ -f "$wt/.git" ]]; then
    root_dir_line=$(grep -E '^gitdir: ' "$wt/.git" | sed 's/^gitdir: //')
    if [[ -n "$root_dir_line" ]]; then
      root="$(cd "$wt" && cd "$root_dir_line/.." && pwd)"
    fi
  fi
fi

copy_if_present() {
  local src="$1" dst="$2"
  if [[ -e "$src" ]]; then
    # Preserve file type; for directories, copy recursively
    if [[ -d "$src" ]]; then
      rsync -a --delete "$src/" "$dst/"
    else
      cp -f "$src" "$dst"
    fi
    echo "Copied $(basename "$src") -> $dst"
  else
    echo "Skip: $(basename "$src") not found in repo root" >&2
  fi
}

mkdir -p "$wt"

# Copy root-level ignored/local files into the worktree if present
copy_if_present "$root/.env" "$wt/.env"
copy_if_present "$root/.sjzl_env" "$wt/.sjzl_env"

# For virtualenv, if a root .venv exists, mirror its structure; otherwise create a fresh venv
if [[ -d "$root/.venv" ]]; then
  mkdir -p "$wt/.venv"
  rsync -a --delete "$root/.venv/" "$wt/.venv/" || true
  echo "Mirrored .venv from root into worktree (may be large)."
else
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv "$wt/.venv" || true
    echo "Created new .venv in worktree. Activate with: source $wt/.venv/bin/activate"
  else
    echo "Python3 not found; skipped virtualenv creation." >&2
  fi
fi

# Safety: ensure these paths stay untracked regardless of .gitignore
# Use worktree-specific exclude file
wt_git_dir=""
if [[ -f "$wt/.git" ]]; then
  wt_git_dir=$(sed -n 's/^gitdir: //p' "$wt/.git")
else
  wt_git_dir="$wt/.git"
fi
if [[ -n "$wt_git_dir" ]]; then
  mkdir -p "$wt_git_dir/info"
  {
    echo ".env"
    echo ".sjzl_env"
    echo ".venv/"
  } | sort -u >> "$wt_git_dir/info/exclude"
fi

