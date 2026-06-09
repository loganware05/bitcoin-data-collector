from __future__ import annotations

from pathlib import Path

import pytest

import multi_horizon_model_router as router


def test_resolve_model_dir_all_horizons(tmp_path: Path):
    for key in router.VALID_HORIZONS:
        assert router.resolve_model_dir(key, tmp_path) == tmp_path / key


def test_resolve_model_dir_invalid_key(tmp_path: Path):
    with pytest.raises(ValueError, match="Unknown horizon key"):
        router.resolve_model_dir("2h", tmp_path)


def test_load_model_for_horizon_missing_dir(tmp_path: Path):
    assert router.load_model_for_horizon("60m", tmp_path) is None


def test_load_model_for_horizon_empty_dir(tmp_path: Path):
    (tmp_path / "60m").mkdir()
    assert router.load_model_for_horizon("60m", tmp_path) is None


def test_load_model_for_horizon_picks_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model_dir = tmp_path / "60m"
    model_dir.mkdir()
    older = model_dir / "model_logreg_20260101T000000Z.joblib"
    newer = model_dir / "model_logreg_20260102T000000Z.joblib"
    older.write_text("old")
    newer.write_text("new")

    loaded_paths: list[Path] = []

    def fake_load_artifact(path: str | Path) -> object:
        loaded_paths.append(Path(path))
        return {"path": str(path)}

    monkeypatch.setattr(router, "load_artifact", fake_load_artifact)

    result = router.load_model_for_horizon("60m", tmp_path)
    assert result == {"path": str(newer)}
    assert loaded_paths == [newer]


def test_load_models_for_horizons_dedupes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_load(horizon_key: str, base: Path) -> object | None:
        calls.append(horizon_key)
        return {"horizon": horizon_key}

    monkeypatch.setattr(router, "load_model_for_horizon", fake_load)

    out = router.load_models_for_horizons(["60m", "60m", "15m"], tmp_path)
    assert calls == ["60m", "15m"]
    assert out == {"60m": {"horizon": "60m"}, "15m": {"horizon": "15m"}}
