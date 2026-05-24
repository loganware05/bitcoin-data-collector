from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtester import _find_future_index, label_outcome
from feature_engineering import FeatureConfig, build_features
from decision_utils import combined_model_confidence, extract_rule_probs
from kalshi_mapper import FusionConfig, fuse_probabilities, map_to_kalshi_decision
from ml_model import TrainedArtifact, load_artifact
from signal_engine import SignalEngineConfig, generate_signal


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, sort_keys=False) + "\n")


def _load_latest_model(models_dir: Path) -> Path | None:
    if not models_dir.exists():
        return None
    candidates = sorted(models_dir.glob("model_*.joblib"))
    return candidates[-1] if candidates else None


@dataclass(frozen=True)
class LiveConfig:
    interval_seconds: int = 60 * 15
    output_dir: Path = Path("live_outputs")

    models_dir: Path = Path("models")
    feature_cfg: FeatureConfig = FeatureConfig()
    signal_cfg: SignalEngineConfig = SignalEngineConfig()
    fusion_cfg: FusionConfig = FusionConfig()

    # Where live runner writes
    predictions_log: Path = Path("live_outputs/predictions_log.jsonl")
    outcomes_log: Path = Path("live_outputs/outcomes_log.jsonl")

    # Labeling config (should match ml_model TrainConfig)
    horizon_hours: float = 24.0
    range_threshold_pct: float = 0.01

    # Market implied probability is manual for now; can be set per-run
    market_implied_prob: float | None = None


def load_snapshot_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("Snapshot JSON must be an object.")
    return obj


def _collect_snapshot_via_subprocess(output_dir: Path) -> dict[str, Any]:
    """
    Uses the existing collector as an external process so we don't have to refactor it.
    Assumes it writes a single JSON file into output_dir (timestamped).
    """
    import subprocess
    import sys

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "btc_market_intel_collector.py", "--output-dir", str(output_dir), "--no-csv"]
    subprocess.run(cmd, check=False, capture_output=True, text=True)
    # Load newest snapshot json in directory
    candidates = sorted(output_dir.glob("btc_market_intel_*.json"))
    if not candidates:
        raise RuntimeError("Collector did not produce a snapshot JSON.")
    return load_snapshot_json(candidates[-1])


def run_once(cfg: LiveConfig, model: TrainedArtifact | None = None) -> dict[str, Any]:
    """
    One iteration: collect snapshot -> rule signal -> ML features/proba -> fuse -> map -> log.
    Returns decision object.
    """
    # Collect snapshot (subprocess) into output dir
    snap_dir = cfg.output_dir / "snapshots"
    snapshot: dict[str, Any]
    try:
        snapshot = _collect_snapshot_via_subprocess(snap_dir)
    except Exception as exc:  # noqa: BLE001
        decision = {
            "timestamp": _now_iso(),
            "error": f"collector_failed: {exc}",
            "recommendation": "NO TRADE",
            "warnings": ["collector failed; no decision"],
        }
        _append_jsonl(cfg.predictions_log, decision)
        return decision

    # Rule engine baseline
    rule_out = generate_signal(snapshot, cfg.signal_cfg)
    p_rule = extract_rule_probs(rule_out)
    rule_conf = float(rule_out.get("confidence", 0.0))

    # ML inference (degraded mode if missing model/candles)
    warnings: list[str] = []
    p_ml: dict[str, float] | None = None
    ml_expl: list[str] = []
    if model is None:
        latest = _load_latest_model(cfg.models_dir)
        if latest is not None:
            model = load_artifact(latest)
        else:
            warnings.append("no saved model found; using rule engine only")

    if model is not None:
        x_row, meta = build_features(snapshot, cfg=cfg.feature_cfg)
        warnings.extend(list(meta.get("warnings", [])))
        try:
            p_ml = model.predict_proba(x_row)
            ml_expl = model.explain_prediction(x_row)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"ml_inference_failed: {exc}; using rule engine only")
            p_ml = None

    # Fuse (if p_ml is None, fuse_probabilities returns p_rule baseline)
    fused = fuse_probabilities(
        p_rule=p_rule,
        p_ml=p_ml,
        w_rule=cfg.fusion_cfg.w_rule,
        w_ml=cfg.fusion_cfg.w_ml,
    )

    combined_conf = combined_model_confidence(rule_conf, ml_available=p_ml is not None)

    decision = map_to_kalshi_decision(
        fused_probs=fused,
        model_confidence=combined_conf,
        market_implied_prob=cfg.market_implied_prob,
        cfg=cfg.fusion_cfg,
        key_factors=list(rule_out.get("key_drivers", [])) if isinstance(rule_out, dict) else [],
        ml_explanation=ml_expl,
        warnings=list(rule_out.get("warnings", [])) + warnings if isinstance(rule_out, dict) else warnings,
    )

    # Add extra context for eval loop
    decision_row = {
        "timestamp": snapshot.get("timestamp"),
        "spot_price_usd": (snapshot.get("price_data") or {}).get("spot_price_usd"),
        "rule": {
            "confidence": rule_conf,
            "probabilities": p_rule,
        },
        "ml": {
            "available": bool(p_ml is not None),
            "probabilities": p_ml,
        },
        "fused_probabilities": fused,
        "decision": decision,
        "market_implied_prob": cfg.market_implied_prob,
        "runner_timestamp": _now_iso(),
    }
    _append_jsonl(cfg.predictions_log, decision_row)
    return decision_row


def backfill_outcomes(
    predictions_log: str | Path,
    outcomes_log: str | Path,
    *,
    horizon_hours: float,
    range_threshold_pct: float,
) -> dict[str, Any]:
    """
    Reads predictions JSONL and, when enough time has passed, labels realized outcome using future prices.
    This works best if your predictions are at regular-ish cadence.
    """
    pred_path = Path(predictions_log)
    out_path = Path(outcomes_log)
    if not pred_path.exists():
        return {"n_predictions": 0, "n_outcomes_written": 0}

    rows: list[dict[str, Any]] = []
    with pred_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("timestamp") is not None:
                rows.append(obj)
    if not rows:
        return {"n_predictions": 0, "n_outcomes_written": 0}

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["spot_price_usd"] = pd.to_numeric(df["spot_price_usd"], errors="coerce")
    df = df.dropna(subset=["timestamp", "spot_price_usd"]).sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        return {"n_predictions": int(len(rows)), "n_outcomes_written": 0}

    horizon = pd.Timedelta(hours=float(horizon_hours))
    fut = _find_future_index(df["timestamp"], horizon)
    df["future_index"] = fut
    eligible = df[df["future_index"] >= 0].copy()
    eligible["future_index"] = eligible["future_index"].astype(int)
    if eligible.empty:
        return {"n_predictions": int(len(df)), "n_outcomes_written": 0}

    # Load already-written timestamps to avoid duplicates
    existing: set[str] = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = obj.get("timestamp") if isinstance(obj, dict) else None
                if isinstance(ts, str):
                    existing.add(ts)

    written = 0
    for _, r in eligible.iterrows():
        ts = r["timestamp"]
        ts_iso = ts.isoformat()
        if ts_iso in existing:
            continue
        j = int(r["future_index"])
        cp = float(r["spot_price_usd"])
        fp = float(df.loc[j, "spot_price_usd"])
        y = label_outcome(cp, fp, float(range_threshold_pct))
        if y not in ("up", "down", "range"):
            continue
        out_row = {"timestamp": ts_iso, "future_timestamp": df.loc[j, "timestamp"].isoformat(), "y_true": y, "cp": cp, "fp": fp}
        _append_jsonl(out_path, out_row)
        written += 1
    return {"n_predictions": int(len(df)), "n_outcomes_written": int(written)}


def run_loop(cfg: LiveConfig) -> None:
    while True:
        try:
            run_once(cfg)
        except Exception as exc:  # noqa: BLE001
            _append_jsonl(
                cfg.predictions_log,
                {"timestamp": _now_iso(), "error": str(exc), "recommendation": "NO TRADE", "warnings": ["runner error"]},
            )
        try:
            backfill_outcomes(
                cfg.predictions_log,
                cfg.outcomes_log,
                horizon_hours=cfg.horizon_hours,
                range_threshold_pct=cfg.range_threshold_pct,
            )
        except Exception:  # noqa: BLE001
            pass
        time.sleep(max(15, int(cfg.interval_seconds)))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Live runner: collector -> features -> ML+rule -> Kalshi decision log.")
    parser.add_argument("--interval-seconds", type=int, default=60 * 15)
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--output-dir", default="live_outputs")
    parser.add_argument("--market-implied-prob", type=float, default=None)
    parser.add_argument("--once", action="store_true", help="Run a single iteration then exit.")
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    cfg = LiveConfig(
        interval_seconds=int(args.interval_seconds),
        output_dir=out_dir,
        models_dir=Path(args.models_dir),
        predictions_log=out_dir / "predictions_log.jsonl",
        outcomes_log=out_dir / "outcomes_log.jsonl",
        market_implied_prob=(None if args.market_implied_prob is None else float(args.market_implied_prob)),
    )
    if args.once:
        run_once(cfg)
        backfill_outcomes(
            cfg.predictions_log,
            cfg.outcomes_log,
            horizon_hours=cfg.horizon_hours,
            range_threshold_pct=cfg.range_threshold_pct,
        )
        return 0
    run_loop(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

