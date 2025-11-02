#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage:
  $0 <worktree-path> <branch-name> [--from <start-point>] [--detach]

Examples:
  $0 worktrees/feat-login feat/login --from main
  $0 worktrees/try-xyz try/xyz --detach
  $0 worktrees/fixes fixes --from origin/main

Notes:
  - If <branch-name> does not exist and --from is provided, it will be created from that start point.
  - If --detach is provided, the worktree will be created detached at the start point (or current HEAD if none).
  - After creation, scripts/init-worktree.sh is called to copy local env files.
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

wt_path="$1"; shift
branch="$1"; shift
start_point=""; detach=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      shift
      start_point="${1:-}"
      [[ -z "$start_point" ]] && { echo "--from requires an argument" >&2; exit 2; }
      ;;
    --detach)
      detach=true
      ;;
    -h|--help)
      usage; exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2; usage; exit 2
      ;;
  esac
  shift || true
done

# Ensure worktrees dir exists if a nested path under worktrees/
mkdir -p "$(dirname "$wt_path")"

# Determine if branch exists locally
if git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "Branch '$branch' exists."
else
  if [[ "$detach" == true ]]; then
    echo "Detached mode requested; not creating branch '$branch'."
  else
    if [[ -n "$start_point" ]]; then
      echo "Creating branch '$branch' from '$start_point'..."
      git branch "$branch" "$start_point"
    else
      echo "Creating branch '$branch' from current HEAD..."
      git branch "$branch"
    fi
  fi
fi

# Add the worktree
if git worktree list | rg -q "^.*\s$(pwd)/$wt_path\s"; then
  echo "Worktree '$wt_path' already exists."
else
  if [[ "$detach" == true ]]; then
    if [[ -n "$start_point" ]]; then
      echo "Adding detached worktree at '$wt_path' from '$start_point'..."
      git worktree add --detach "$wt_path" "$start_point"
    else
      echo "Adding detached worktree at '$wt_path' from current HEAD..."
      git worktree add --detach "$wt_path"
    fi
  else
    echo "Adding worktree at '$wt_path' for branch '$branch'..."
    git worktree add "$wt_path" "$branch"
  fi
fi

# Initialize local env files in the new worktree
scripts/init-worktree.sh "$wt_path"

echo "Done. Worktree at: $wt_path"
