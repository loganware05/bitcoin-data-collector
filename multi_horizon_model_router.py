from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ml_model import TrainedArtifact, load_artifact

HORIZON_MODEL_DIRS: dict[str, str] = {
    "15m": "15m",
    "30m": "30m",
    "60m": "60m",
    "4h": "4h",
    "24h": "24h",
}

VALID_HORIZONS: tuple[str, ...] = tuple(HORIZON_MODEL_DIRS.keys())


def resolve_model_dir(horizon_key: str, base_models_dir: Path) -> Path:
    """Return the model subdirectory for a horizon key under base_models_dir."""
    subdir = HORIZON_MODEL_DIRS.get(horizon_key)
    if subdir is None:
        supported = ", ".join(VALID_HORIZONS)
        raise ValueError(f"Unknown horizon key {horizon_key!r}; supported: {supported}")
    return base_models_dir / subdir


def _latest_model_path(models_dir: Path) -> Path | None:
    if not models_dir.exists():
        return None
    candidates = sorted(models_dir.glob("model_*.joblib"))
    if not candidates:
        return None
    return candidates[-1]


def load_model_for_horizon(horizon_key: str, base_models_dir: Path) -> TrainedArtifact | None:
    """Load the latest saved model artifact for the given horizon, or None if missing."""
    model_path = _latest_model_path(resolve_model_dir(horizon_key, base_models_dir))
    if model_path is None:
        return None
    return load_artifact(model_path)


def load_models_for_horizons(
    horizon_keys: Iterable[str],
    base_models_dir: Path,
) -> dict[str, TrainedArtifact | None]:
    """Load models for multiple horizons, deduplicating by horizon key."""
    out: dict[str, TrainedArtifact | None] = {}
    for key in horizon_keys:
        if key not in out:
            out[key] = load_model_for_horizon(key, base_models_dir)
    return out


__all__ = [
    "HORIZON_MODEL_DIRS",
    "VALID_HORIZONS",
    "load_model_for_horizon",
    "load_models_for_horizons",
    "resolve_model_dir",
]
