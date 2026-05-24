from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtester import _find_future_index, label_outcome, load_time_series
from decision_utils import combined_model_confidence, extract_rule_probs
from feature_engineering import FeatureConfig, build_features
from kalshi_mapper import FusionConfig, fuse_probabilities, map_to_kalshi_decision
from ml_model import OUTCOMES, TrainConfig, TrainedArtifact, build_labeled_dataset, load_artifact
from signal_engine import SignalEngineConfig, generate_signal

DEFAULT_OUTPUT_DIR = Path("/Volumes/Verdant_AI/btc_kalshi/datasets")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_snapshot(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _ensure_output_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(
            f"Cannot create output directory {path}. Is /Volumes/Verdant_AI mounted?"
        ) from exc
    if not path.is_dir():
        raise OSError(f"Output path is not a directory: {path}")
    return path


def _load_latest_model_path(models_dir: Path) -> Path | None:
    if not models_dir.exists():
        return None
    candidates = sorted(models_dir.glob("model_*.joblib"))
    return candidates[-1] if candidates else None


def _resolve_model_path(model_path: str | Path | None, models_dir: Path) -> Path | None:
    if model_path is not None:
        p = Path(model_path)
        if not p.exists():
            raise FileNotFoundError(f"Model not found: {p}")
        return p
    return _load_latest_model_path(models_dir)


@dataclass(frozen=True)
class DatasetBuilderConfig:
    input_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR

    train_cfg: TrainConfig = TrainConfig()
    signal_cfg: SignalEngineConfig = SignalEngineConfig()
    feature_cfg: FeatureConfig = FeatureConfig()
    fusion_cfg: FusionConfig = FusionConfig()

    market_probs_csv: Path | None = None
    market_match_tolerance_minutes: float = 5.0
    model_path: Path | None = None
    models_dir: Path = Path("models")


def _enrich_labeled_with_prices(
    labeled: pd.DataFrame,
    input_path: str | Path,
    cfg: TrainConfig,
) -> pd.DataFrame:
    ts_df = load_time_series(input_path)
    ts_df = ts_df.dropna(subset=["timestamp", "spot_price_usd"]).copy()
    ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"], utc=True, errors="coerce")
    ts_df = ts_df.sort_values("timestamp").reset_index(drop=True)

    horizon = pd.Timedelta(hours=float(cfg.horizon_hours))
    ts_df["future_index"] = _find_future_index(ts_df["timestamp"], horizon)
    ts_df = ts_df[ts_df["future_index"] >= 0].copy()
    ts_df["future_index"] = ts_df["future_index"].astype(int)
    ts_df["future_price"] = ts_df["future_index"].map(
        lambda j: float(ts_df.loc[j, "spot_price_usd"]) if j in ts_df.index else np.nan
    )
    ts_df["future_timestamp"] = ts_df["future_index"].map(
        lambda j: ts_df.loc[j, "timestamp"] if j in ts_df.index else pd.NaT
    )
    price_cols = ts_df[["timestamp", "spot_price_usd", "future_price", "future_timestamp"]].copy()
    price_cols["timestamp"] = pd.to_datetime(price_cols["timestamp"], utc=True, errors="coerce")

    out = labeled.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    merged = out.merge(price_cols, on="timestamp", how="left")
    return merged


def load_market_probs_sidecar(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Market probs sidecar not found: {p}")
    df = pd.read_csv(p)
    if "timestamp" not in df.columns or "market_implied_prob" not in df.columns:
        raise ValueError("Sidecar CSV must include columns: timestamp, market_implied_prob")
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["market_implied_prob"] = pd.to_numeric(df["market_implied_prob"], errors="coerce")
    df = df.dropna(subset=["timestamp", "market_implied_prob"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def join_market_probs(
    timestamps: pd.Series,
    sidecar: pd.DataFrame,
    *,
    tolerance_minutes: float = 5.0,
) -> pd.Series:
    if sidecar.empty:
        return pd.Series(np.nan, index=timestamps.index, dtype=float)

    left = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, utc=True, errors="coerce"),
            "_orig_idx": timestamps.index,
        }
    )
    left_sorted = left.sort_values("timestamp")
    right = sidecar[["timestamp", "market_implied_prob"]].sort_values("timestamp")
    tol = pd.Timedelta(minutes=float(tolerance_minutes))
    merged = pd.merge_asof(
        left_sorted,
        right,
        on="timestamp",
        direction="nearest",
        tolerance=tol,
    )
    merged = merged.set_index("_orig_idx").sort_index()
    return merged["market_implied_prob"]


def build_and_export_labeled_features(
    cfg: DatasetBuilderConfig,
    *,
    stamp: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    stamp = stamp or _utc_stamp()
    out_dir = _ensure_output_dir(cfg.output_dir)

    labeled, meta = build_labeled_dataset(cfg.input_path, cfg=cfg.train_cfg)
    if len(labeled) < 1:
        raise ValueError(
            "Labeled dataset is empty. Collect more snapshots spanning at least one full horizon."
        )

    enriched = _enrich_labeled_with_prices(labeled, cfg.input_path, cfg.train_cfg)
    # Order columns: identity first, then features
    id_cols = ["timestamp", "spot_price_usd", "future_timestamp", "future_price", "y_true", "y"]
    feature_cols = [c for c in enriched.columns if c not in id_cols]
    enriched = enriched[id_cols + feature_cols]

    out_path = out_dir / f"labeled_features_{stamp}.csv"
    enriched.to_csv(out_path, index=False)

    manifest_extra = {
        "labeled_features_csv": str(out_path),
        "n_labeled_rows": int(len(enriched)),
        "warnings": [] if len(enriched) >= 2 else ["fewer than 2 labeled rows; limited training utility"],
    }
    return out_path, {**meta, **manifest_extra}


def _prepare_time_series(cfg: DatasetBuilderConfig) -> pd.DataFrame:
    ts_df = load_time_series(cfg.input_path)
    ts_df = ts_df.dropna(subset=["timestamp", "spot_price_usd"]).copy()
    ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"], utc=True, errors="coerce")
    ts_df = ts_df.sort_values("timestamp").reset_index(drop=True)

    horizon = pd.Timedelta(hours=float(cfg.train_cfg.horizon_hours))
    ts_df["future_index"] = _find_future_index(ts_df["timestamp"], horizon)
    ts_df = ts_df[ts_df["future_index"] >= 0].copy()
    ts_df["future_index"] = ts_df["future_index"].astype(int)
    ts_df["future_price"] = ts_df["future_index"].map(
        lambda j: float(ts_df.loc[j, "spot_price_usd"]) if j in ts_df.index else np.nan
    )
    ts_df["future_timestamp"] = ts_df["future_index"].map(
        lambda j: ts_df.loc[j, "timestamp"] if j in ts_df.index else pd.NaT
    )
    ts_df = ts_df.dropna(subset=["future_price"]).copy()

    ys = [
        label_outcome(float(cp), float(fp), float(cfg.train_cfg.range_threshold_pct))
        for cp, fp in zip(ts_df["spot_price_usd"].astype(float), ts_df["future_price"].astype(float))
    ]
    ts_df["y_true"] = ys
    ts_df = ts_df[ts_df["y_true"].isin(list(OUTCOMES))].copy()
    if ts_df.empty:
        raise ValueError("No rows with valid labels after filtering.")
    return ts_df


def build_and_export_decision_dataset(
    cfg: DatasetBuilderConfig,
    *,
    stamp: str | None = None,
    model: TrainedArtifact | None = None,
) -> tuple[Path, dict[str, Any]]:
    stamp = stamp or _utc_stamp()
    out_dir = _ensure_output_dir(cfg.output_dir)

    ts_df = _prepare_time_series(cfg)
    if len(ts_df) < 1:
        raise ValueError("Decision dataset is empty after filtering.")

    sidecar = (
        load_market_probs_sidecar(cfg.market_probs_csv)
        if cfg.market_probs_csv is not None
        else pd.DataFrame(columns=["timestamp", "market_implied_prob"])
    )
    market_probs = join_market_probs(
        ts_df["timestamp"],
        sidecar,
        tolerance_minutes=cfg.market_match_tolerance_minutes,
    )

    model_path = _resolve_model_path(cfg.model_path, cfg.models_dir)
    if model is None and model_path is not None:
        model = load_artifact(model_path)

    rows: list[dict[str, Any]] = []
    n_ml_ok = 0
    n_sidecar_matched = 0

    for i, r in ts_df.iterrows():
        snap = _safe_snapshot(r.get("snapshot"))
        rule_out = generate_signal(snap, cfg.signal_cfg)
        p_rule = extract_rule_probs(rule_out)
        rule_conf = float(rule_out.get("confidence", 0.0))

        warnings: list[str] = []
        p_ml: dict[str, float] | None = None
        if model is not None:
            try:
                x_row, meta = build_features(snap, cfg=cfg.feature_cfg)
                warnings.extend(list(meta.get("warnings", [])))
                p_ml = model.predict_proba(x_row)
                n_ml_ok += 1
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"ml_inference_failed: {exc}")

        fused = fuse_probabilities(
            p_rule=p_rule,
            p_ml=p_ml,
            w_rule=cfg.fusion_cfg.w_rule,
            w_ml=cfg.fusion_cfg.w_ml,
        )
        combined_conf = combined_model_confidence(rule_conf, ml_available=p_ml is not None)

        mkt_prob = market_probs.loc[i] if i in market_probs.index else np.nan
        mkt_val: float | None = None
        if pd.notna(mkt_prob):
            mkt_val = float(mkt_prob)
            n_sidecar_matched += 1

        decision = map_to_kalshi_decision(
            fused_probs=fused,
            model_confidence=combined_conf,
            market_implied_prob=mkt_val,
            cfg=cfg.fusion_cfg,
            key_factors=list(rule_out.get("key_drivers", [])) if isinstance(rule_out, dict) else [],
            ml_explanation=[],
            warnings=list(rule_out.get("warnings", [])) + warnings if isinstance(rule_out, dict) else warnings,
        )

        rows.append(
            {
                "timestamp": r["timestamp"].isoformat(),
                "spot_price_usd": float(r["spot_price_usd"]),
                "future_timestamp": r["future_timestamp"].isoformat() if pd.notna(r["future_timestamp"]) else None,
                "future_price": float(r["future_price"]),
                "y_true": r["y_true"],
                "y": {"up": 0, "down": 1, "range": 2}[r["y_true"]],
                "rule_p_up": p_rule["up"],
                "rule_p_down": p_rule["down"],
                "rule_p_range": p_rule["range"],
                "rule_confidence": rule_conf,
                "ml_available": p_ml is not None,
                "ml_p_up": None if p_ml is None else p_ml["up"],
                "ml_p_down": None if p_ml is None else p_ml["down"],
                "ml_p_range": None if p_ml is None else p_ml["range"],
                "fused_p_up": fused["up"],
                "fused_p_down": fused["down"],
                "fused_p_range": fused["range"],
                "market_implied_prob": decision["market_implied_prob"],
                "contract": decision["contract"],
                "probability": decision["probability"],
                "edge": decision["edge"],
                "confidence": decision["confidence"],
                "recommendation": decision["recommendation"],
                "recommended_side": decision["recommended_side"],
                "warnings": "; ".join(decision.get("warnings", [])),
                "key_factors": "; ".join(decision.get("key_factors", [])),
            }
        )

    out_df = pd.DataFrame(rows)
    out_path = out_dir / f"decision_dataset_{stamp}.csv"
    out_df.to_csv(out_path, index=False)

    meta = {
        "decision_dataset_csv": str(out_path),
        "n_decision_rows": int(len(out_df)),
        "n_ml_inference_ok": int(n_ml_ok),
        "n_sidecar_matched": int(n_sidecar_matched),
        "model_path": str(model_path) if model_path else None,
        "market_probs_csv": str(cfg.market_probs_csv) if cfg.market_probs_csv else None,
    }
    return out_path, meta


def write_manifest(
    output_dir: Path,
    *,
    stamp: str,
    sections: dict[str, Any],
    cfg: DatasetBuilderConfig,
) -> Path:
    out_dir = _ensure_output_dir(output_dir)
    manifest = {
        "created_at_utc": stamp,
        "input_path": str(cfg.input_path),
        "output_dir": str(out_dir),
        "horizon_hours": float(cfg.train_cfg.horizon_hours),
        "label_range_threshold_pct": float(cfg.train_cfg.range_threshold_pct),
        "rule_range_band_pct": float(cfg.signal_cfg.range_band_pct),
        "fusion": {
            "w_rule": cfg.fusion_cfg.w_rule,
            "w_ml": cfg.fusion_cfg.w_ml,
            "min_confidence": cfg.fusion_cfg.min_confidence,
            "min_edge": cfg.fusion_cfg.min_edge,
            "max_range_prob_for_directional": cfg.fusion_cfg.max_range_prob_for_directional,
        },
        **sections,
    }
    path = out_dir / f"dataset_manifest_{stamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path


def run_export(
    cfg: DatasetBuilderConfig,
    *,
    export_labeled: bool = True,
    export_decision: bool = True,
) -> dict[str, Any]:
    stamp = _utc_stamp()
    sections: dict[str, Any] = {}
    paths: dict[str, str] = {}

    if export_labeled:
        labeled_path, labeled_meta = build_and_export_labeled_features(cfg, stamp=stamp)
        paths["labeled_features"] = str(labeled_path)
        sections["labeled"] = labeled_meta

    if export_decision:
        decision_path, decision_meta = build_and_export_decision_dataset(cfg, stamp=stamp)
        paths["decision_dataset"] = str(decision_path)
        sections["decision"] = decision_meta

    manifest_path = write_manifest(cfg.output_dir, stamp=stamp, sections=sections, cfg=cfg)
    paths["manifest"] = str(manifest_path)

    return {"stamp": stamp, "paths": paths, "sections": sections}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build labeled feature and decision CSVs on Verdant_AI (rule+ML fuse, edge vs market)."
    )
    parser.add_argument("input", help="Snapshot directory, CSV, or JSON.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Export directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--market-probs-csv", default=None, help="Sidecar CSV: timestamp, market_implied_prob.")
    parser.add_argument("--market-match-tolerance-minutes", type=float, default=5.0)
    parser.add_argument("--model-path", default=None, help="Trained model .joblib (default: latest in models/).")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--horizon-hours", type=float, default=24.0)
    parser.add_argument("--range-threshold-pct", type=float, default=0.01)
    parser.add_argument("--w-rule", type=float, default=0.55)
    parser.add_argument("--w-ml", type=float, default=0.45)
    parser.add_argument("--min-edge", type=float, default=0.03)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--max-range-prob", type=float, default=0.55)
    parser.add_argument("--labeled-only", action="store_true")
    parser.add_argument("--decision-only", action="store_true")
    args = parser.parse_args(argv)

    export_labeled = not args.decision_only
    export_decision = not args.labeled_only
    if args.labeled_only and args.decision_only:
        raise SystemExit("Cannot set both --labeled-only and --decision-only.")

    cfg = DatasetBuilderConfig(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        train_cfg=TrainConfig(
            horizon_hours=float(args.horizon_hours),
            range_threshold_pct=float(args.range_threshold_pct),
        ),
        signal_cfg=SignalEngineConfig(),
        fusion_cfg=FusionConfig(
            w_rule=float(args.w_rule),
            w_ml=float(args.w_ml),
            min_edge=float(args.min_edge),
            min_confidence=float(args.min_confidence),
            max_range_prob_for_directional=float(args.max_range_prob),
        ),
        market_probs_csv=(None if args.market_probs_csv is None else Path(args.market_probs_csv)),
        market_match_tolerance_minutes=float(args.market_match_tolerance_minutes),
        model_path=(None if args.model_path is None else Path(args.model_path)),
        models_dir=Path(args.models_dir),
    )

    result = run_export(cfg, export_labeled=export_labeled, export_decision=export_decision)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
