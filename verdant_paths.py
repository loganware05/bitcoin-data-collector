from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_ROOT = Path("/Volumes/Verdant_AI/btc_kalshi")
ENV_VAR = "BTC_KALSHI_ROOT"


@dataclass(frozen=True)
class VerdantLayout:
    """Resolved directory layout under a Verdant (or custom) data root."""

    data_root: Path
    snapshots_dir: Path
    models_dir: Path
    hourly_outputs_dir: Path
    datasets_dir: Path
    market_probs_dir: Path
    live_runner_dir: Path
    health_log: Path


def resolve_data_root(data_root: str | Path | None = None) -> Path:
    """Resolve data root from explicit arg, BTC_KALSHI_ROOT env, or default Verdant path."""
    if data_root is not None:
        return Path(data_root).expanduser().resolve()
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DATA_ROOT.resolve()


def resolve_layout(
    data_root: str | Path | None = None,
    *,
    snapshots_dir: str | Path | None = None,
    models_dir: str | Path | None = None,
    hourly_outputs_dir: str | Path | None = None,
    datasets_dir: str | Path | None = None,
) -> VerdantLayout:
    """Build full layout; individual dirs override defaults under data_root."""
    root = resolve_data_root(data_root)
    return VerdantLayout(
        data_root=root,
        snapshots_dir=Path(snapshots_dir).expanduser().resolve()
        if snapshots_dir
        else root / "snapshots",
        models_dir=Path(models_dir).expanduser().resolve() if models_dir else root / "models",
        hourly_outputs_dir=Path(hourly_outputs_dir).expanduser().resolve()
        if hourly_outputs_dir
        else root / "hourly_outputs",
        datasets_dir=Path(datasets_dir).expanduser().resolve() if datasets_dir else root / "datasets",
        market_probs_dir=root / "market_probs",
        live_runner_dir=root / "live_runner",
        health_log=root / "snapshot_daemon_health.jsonl",
    )


def ensure_layout_dirs(layout: VerdantLayout) -> None:
    """Create standard directories if missing."""
    for path in (
        layout.snapshots_dir,
        layout.models_dir,
        layout.hourly_outputs_dir,
        layout.datasets_dir,
        layout.market_probs_dir,
        layout.live_runner_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def add_data_root_arg(parser) -> None:
    """Register --data-root on an argparse parser."""
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help=f"Base data directory (default: ${ENV_VAR} or {DEFAULT_DATA_ROOT})",
    )


def layout_from_args(args, repo_root: Path | None = None) -> VerdantLayout:
    """Build layout from parsed args with optional path overrides."""
    layout = resolve_layout(getattr(args, "data_root", None))
    repo_root = repo_root or Path(__file__).resolve().parent

    snapshots = getattr(args, "snapshots_dir", None) or getattr(args, "collect_output_dir", None)
    models = getattr(args, "models_base_dir", None) or getattr(args, "models_dir", None)
    hourly = getattr(args, "output_dir", None)

    def _resolve(path: Path | None, default: Path) -> Path:
        if path is None:
            return default
        return path if path.is_absolute() else repo_root / path

    return VerdantLayout(
        data_root=layout.data_root,
        snapshots_dir=_resolve(snapshots, layout.snapshots_dir),
        models_dir=_resolve(models, layout.models_dir),
        hourly_outputs_dir=_resolve(hourly, layout.hourly_outputs_dir),
        datasets_dir=layout.datasets_dir,
        market_probs_dir=layout.market_probs_dir,
        live_runner_dir=layout.live_runner_dir,
        health_log=layout.health_log,
    )


__all__ = [
    "DEFAULT_DATA_ROOT",
    "ENV_VAR",
    "VerdantLayout",
    "add_data_root_arg",
    "ensure_layout_dirs",
    "layout_from_args",
    "resolve_data_root",
    "resolve_layout",
]
