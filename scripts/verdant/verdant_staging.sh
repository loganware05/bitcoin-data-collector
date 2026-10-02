#!/usr/bin/env bash
# Local laptop staging when Verdant volume is unplugged.
# Scans, snapshots, and cached models live under BTC_KALSHI_LOCAL_ROOT until push on remount.
#
# Shell library — source from other verdant scripts; do not execute directly.
set -euo pipefail

: "${BTC_KALSHI_REMOTE_ROOT:=/Volumes/Verdant_AI/btc_kalshi}"
: "${BTC_KALSHI_LOCAL_ROOT:=$HOME/.local/share/verdant-btc-kalshi}"
# Max age (days) of remote snapshots to pull into local cache (0 = all).
: "${BTC_KALSHI_SNAPSHOT_CACHE_DAYS:=21}"

verdant_remote_mounted() {
  [[ -d "$BTC_KALSHI_REMOTE_ROOT" && -r "$BTC_KALSHI_REMOTE_ROOT" ]]
}

verdant_local_has_scan_cache() {
  [[ -n "$(find "$BTC_KALSHI_LOCAL_ROOT/models" -name 'model_*.json' -print -quit 2>/dev/null)" ]]
}

verdant_local_has_snapshot_cache() {
  [[ -n "$(find "$BTC_KALSHI_LOCAL_ROOT/snapshots" -name 'btc_market_intel_*.json' -print -quit 2>/dev/null)" ]]
}

verdant_ensure_local_dirs() {
  mkdir -p \
    "$BTC_KALSHI_LOCAL_ROOT/hourly_outputs" \
    "$BTC_KALSHI_LOCAL_ROOT/models" \
    "$BTC_KALSHI_LOCAL_ROOT/market_probs" \
    "$BTC_KALSHI_LOCAL_ROOT/snapshots"
}

# Pull models + market_probs + recent snapshots from Verdant → local cache.
verdant_pull_cache() {
  if ! verdant_remote_mounted; then
    echo "staging: remote not mounted; skip pull"
    return 0
  fi
  verdant_ensure_local_dirs
  echo "staging: pulling model/market_probs/snapshot cache → $BTC_KALSHI_LOCAL_ROOT"
  if [[ -d "$BTC_KALSHI_REMOTE_ROOT/models" ]]; then
    rsync -a --omit-dir-times "$BTC_KALSHI_REMOTE_ROOT/models/" "$BTC_KALSHI_LOCAL_ROOT/models/"
  fi
  if [[ -d "$BTC_KALSHI_REMOTE_ROOT/market_probs" ]]; then
    rsync -a --omit-dir-times "$BTC_KALSHI_REMOTE_ROOT/market_probs/" "$BTC_KALSHI_LOCAL_ROOT/market_probs/"
  fi
  if [[ -d "$BTC_KALSHI_REMOTE_ROOT/snapshots" ]]; then
    if [[ "${BTC_KALSHI_SNAPSHOT_CACHE_DAYS}" == "0" ]]; then
      rsync -a --omit-dir-times "$BTC_KALSHI_REMOTE_ROOT/snapshots/" "$BTC_KALSHI_LOCAL_ROOT/snapshots/"
    else
      # Prefer recent snapshots for offline continuity (bounded disk use).
      find "$BTC_KALSHI_REMOTE_ROOT/snapshots" -maxdepth 1 -type f -name 'btc_market_intel_*.json' \
        -mtime "-${BTC_KALSHI_SNAPSHOT_CACHE_DAYS}" -print0 2>/dev/null \
        | while IFS= read -r -d '' f; do
            cp -p "$f" "$BTC_KALSHI_LOCAL_ROOT/snapshots/$(basename "$f")"
          done
      echo "staging: snapshot cache refreshed (mtime ≤ ${BTC_KALSHI_SNAPSHOT_CACHE_DAYS}d)"
    fi
  fi
}

# Push locally staged scans to Verdant (never deletes remote files).
verdant_push_pending_scans() {
  if ! verdant_remote_mounted; then
    echo "staging: remote not mounted; scans remain in $BTC_KALSHI_LOCAL_ROOT/hourly_outputs"
    return 0
  fi
  verdant_ensure_local_dirs
  mkdir -p "$BTC_KALSHI_REMOTE_ROOT/hourly_outputs"
  shopt -s nullglob
  for f in "$BTC_KALSHI_LOCAL_ROOT/hourly_outputs"/scan_*.{json,csv}; do
    [[ -e "$f" ]] || continue
    local base dest
    base="$(basename "$f")"
    dest="$BTC_KALSHI_REMOTE_ROOT/hourly_outputs/$base"
    if [[ -f "$dest" ]]; then
      continue
    fi
    cp -p "$f" "$dest"
  done
  shopt -u nullglob
  local pending
  pending="$(find "$BTC_KALSHI_LOCAL_ROOT/hourly_outputs" -maxdepth 1 -name 'scan_*.json' 2>/dev/null | wc -l | tr -d ' ')"
  echo "staging: push complete; $pending scan JSON still under local staging (duplicates skipped on remote)"
}

# Push locally collected snapshots that are not yet on Verdant.
verdant_push_pending_snapshots() {
  if ! verdant_remote_mounted; then
    echo "staging: remote not mounted; snapshots remain in $BTC_KALSHI_LOCAL_ROOT/snapshots"
    return 0
  fi
  verdant_ensure_local_dirs
  mkdir -p "$BTC_KALSHI_REMOTE_ROOT/snapshots"
  local copied=0
  shopt -s nullglob
  for f in "$BTC_KALSHI_LOCAL_ROOT/snapshots"/btc_market_intel_*.json; do
    [[ -e "$f" ]] || continue
    local base dest
    base="$(basename "$f")"
    dest="$BTC_KALSHI_REMOTE_ROOT/snapshots/$base"
    if [[ -f "$dest" ]]; then
      continue
    fi
    cp -p "$f" "$dest"
    copied=$((copied + 1))
  done
  shopt -u nullglob
  echo "staging: pushed $copied new local snapshot(s) to remote"
}

# Set BTC_KALSHI_ROOT for the current job. Prefer remote when mounted.
verdant_resolve_active_root() {
  if verdant_remote_mounted; then
    export BTC_KALSHI_ROOT="$BTC_KALSHI_REMOTE_ROOT"
    echo "staging: using remote data root $BTC_KALSHI_ROOT"
    return 0
  fi
  if verdant_local_has_scan_cache; then
    export BTC_KALSHI_ROOT="$BTC_KALSHI_LOCAL_ROOT"
    echo "staging: remote offline — using local cache $BTC_KALSHI_ROOT"
    return 0
  fi
  echo "ERROR: Verdant not mounted and no local model cache at $BTC_KALSHI_LOCAL_ROOT" >&2
  echo "  Connect drive and run: scripts/verdant/sync_verdant_staging.sh --pull" >&2
  return 1
}

# Full sync cycle: pull cache, push pending scans + snapshots.
verdant_sync_all() {
  verdant_pull_cache
  verdant_push_pending_scans
  verdant_push_pending_snapshots
}

# Prepare for hourly scan: sync, resolve root, ensure output dirs exist.
verdant_prepare_hourly_scan() {
  verdant_ensure_local_dirs
  if verdant_remote_mounted; then
    verdant_pull_cache
    verdant_push_pending_scans
    verdant_push_pending_snapshots
  fi
  verdant_resolve_active_root
  mkdir -p "$BTC_KALSHI_ROOT/hourly_outputs"
}

# After scan: if we wrote locally while remote is up, copy isn't needed;
# if remote came online during scan or we wrote locally, push pending.
verdant_finalize_hourly_scan() {
  if [[ "${BTC_KALSHI_ROOT:-}" == "$BTC_KALSHI_LOCAL_ROOT" ]]; then
    echo "staging: scan saved locally; will push on next sync when drive connected"
  fi
  if verdant_remote_mounted; then
    verdant_push_pending_scans
    verdant_push_pending_snapshots
  fi
}
