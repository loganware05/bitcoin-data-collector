"""Evaluate / fit Kalshi scan probabilities against settled outcomes.

Memory-safe design:
  1) ``--mode refresh-cache`` or eval/fit with scans → batch-load scans, unique-ticker
     outcome cache on disk.
  2) ``--mode eval`` → metrics from labeled cache only (no calibrator write).
  3) ``--mode fit`` → isotonic fit from labeled cache only (separate process).

Weekly retrain must invoke eval and fit as two processes so they never double-load
all scan JSON in one address space.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kalshi_client import KalshiClient, KalshiClientConfig
from probability_calibration import (
    CalibratorConfig,
    SettlementProbabilityCalibrator,
    evaluate_calibration_slices,
    load_settlement_calibrator,
    save_calibrator,
)
from probability_calibration import calibration_dir as _calibration_dir
from settlement_label_store import (
    build_or_update_labeled_table,
    default_cache_dir,
    filter_scan_paths,
    load_labeled_rows,
    load_scan_rows_batched,
)


@dataclass(frozen=True)
class SettlementEvalConfig:
    min_samples: int = 10
    calibration_bins: int = 10
    exclude_no_trade_for_eval: bool = True


def _parse_result_yes(result: str | None) -> int | None:
    if not result:
        return None
    r = str(result).strip().lower()
    if r in ("yes", "true", "1"):
        return 1
    if r in ("no", "false", "0"):
        return 0
    return None


def fetch_settled_market(client: KalshiClient, ticker: str) -> dict[str, Any] | None:
    """Fetch a single market by ticker (any status) for settlement outcome."""
    try:
        data = client._get(f"/markets/{ticker}")  # noqa: SLF001
        market = data.get("market") if isinstance(data, dict) else None
        return market if isinstance(market, dict) else data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _outcome_fetcher(client: KalshiClient | None = None):
    client = client or KalshiClient(KalshiClientConfig(status="settled"))

    def _fetch(ticker: str) -> int | None:
        raw = fetch_settled_market(client, ticker)
        if not raw:
            return None
        result = raw.get("result") or raw.get("settlement_value")
        return _parse_result_yes(str(result) if result is not None else None)

    return _fetch


def load_scan_rows(scan_paths: list[Path], *, batch_size: int = 25) -> pd.DataFrame:
    """Backward-compatible scan loader (batched)."""
    return load_scan_rows_batched(scan_paths, batch_size=batch_size)


def attach_settlement_outcomes(
    df: pd.DataFrame,
    *,
    client: KalshiClient | None = None,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """Attach y_true using unique-ticker resolution (optional disk cache)."""
    from settlement_label_store import apply_outcomes, resolve_ticker_outcomes

    if df.empty:
        out = df.copy()
        out["y_true"] = []
        return out

    cache = Path(cache_dir) if cache_dir is not None else Path(".settlement_cache_ephemeral")
    outcomes = resolve_ticker_outcomes(
        df["ticker"].astype(str).tolist(),
        cache_dir=cache,
        fetch_outcome=_outcome_fetcher(client),
        persist=cache_dir is not None,
    )
    return apply_outcomes(df, outcomes)


def refresh_settlement_cache(
    scan_paths: list[Path],
    *,
    cache_dir: Path,
    client: KalshiClient | None = None,
    since: datetime | None = None,
    batch_size: int = 25,
) -> dict[str, Any]:
    return build_or_update_labeled_table(
        scan_paths,
        cache_dir=cache_dir,
        fetch_outcome=_outcome_fetcher(client),
        since=since,
        batch_size=batch_size,
    )


def _metrics_from_labeled(
    labeled: pd.DataFrame,
    *,
    cfg: SettlementEvalConfig,
    models_base_dir: Path | None = None,
) -> dict[str, Any]:
    cal_cfg = CalibratorConfig(
        min_samples=cfg.min_samples,
        exclude_no_trade_for_eval=cfg.exclude_no_trade_for_eval,
        calibration_bins=cfg.calibration_bins,
    )
    work = labeled.dropna(subset=["y_true"]).copy()
    if work.empty:
        return {"n": 0, "warnings": ["no labeled rows"]}
    work["y_true"] = work["y_true"].astype(int)
    if len(work) < cfg.min_samples:
        return {
            "n": int(len(work)),
            "warnings": [f"need at least {cfg.min_samples} settled contracts; found {len(work)}"],
        }

    calibrator = load_settlement_calibrator(Path(models_base_dir)) if models_base_dir else None
    slices = evaluate_calibration_slices(work, cfg=cal_cfg, calibrator=calibrator)

    p_raw = work["model_yes_probability"].astype(float).to_numpy()
    y = work["y_true"].astype(int).to_numpy()
    brier = float(np.mean((p_raw - y) ** 2))
    acc = float(((p_raw >= 0.5).astype(int) == y).mean())

    primary = slices.get("no_trade_excluded") or slices.get("actionable") or {}
    if not primary or int(primary.get("n") or 0) == 0:
        primary = slices.get("all_settled") or {}

    gap = slices.get("max_calibration_gap")
    if gap is None and isinstance(primary, dict):
        gap = primary.get("max_calibration_gap_calibrated") or primary.get("max_calibration_gap_raw")

    actionable = (
        work[work["recommendation"].isin(["BUY YES", "BUY NO"])]
        if "recommendation" in work.columns
        else work
    )
    result: dict[str, Any] = {
        "n": int(len(work)),
        "n_actionable": int(len(actionable)),
        "brier_score": round(brier, 4),
        "accuracy_at_50pct": round(acc, 4),
        "max_calibration_gap": gap,
        "max_calibration_gap_raw_all": (slices.get("all_settled") or {}).get("max_calibration_gap_raw"),
        "calibration_slices": slices,
        "exclude_no_trade_for_eval": cfg.exclude_no_trade_for_eval,
        "gate_max_calibration_gap": 0.12,
        "gate_pass": gap is not None and float(gap) <= 0.12,
        "by_recommendation": work.groupby("recommendation", dropna=False)["y_true"]
        .agg(["count", "mean"])
        .to_dict()
        if "recommendation" in work.columns
        else {},
    }
    if calibrator is not None and calibrator.fitted:
        result["calibrator_loaded"] = True
        result["calibrator_meta"] = calibrator.meta
    return result


def evaluate_from_cache(
    cache_dir: Path,
    *,
    cfg: SettlementEvalConfig | None = None,
    models_base_dir: Path | None = None,
    report_out: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or SettlementEvalConfig()
    labeled = load_labeled_rows(cache_dir)
    result = _metrics_from_labeled(labeled, cfg=cfg, models_base_dir=models_base_dir)
    result["cache_dir"] = str(cache_dir)
    result["mode"] = "eval"
    if report_out is not None:
        report_out = Path(report_out)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["report_path"] = str(report_out)
    return result


def fit_from_cache(
    cache_dir: Path,
    models_base_dir: Path,
    *,
    cfg: CalibratorConfig | None = None,
) -> dict[str, Any]:
    """Fit isotonic calibrator from cached labeled rows only (no scan reload)."""
    cfg = cfg or CalibratorConfig()
    labeled = load_labeled_rows(cache_dir)
    labeled = labeled.dropna(subset=["y_true"])
    if labeled.empty:
        return {"success": False, "warnings": ["no labeled rows in cache"], "mode": "fit"}
    if len(labeled) < cfg.min_samples:
        return {
            "success": False,
            "warnings": [f"need at least {cfg.min_samples} settled contracts; found {len(labeled)}"],
            "mode": "fit",
        }

    calibrator = SettlementProbabilityCalibrator()
    try:
        meta = calibrator.fit(labeled, cfg=cfg)
    except ValueError as exc:
        return {"success": False, "warnings": [str(exc)], "mode": "fit"}

    manifest = save_calibrator(calibrator, _calibration_dir(Path(models_base_dir)))
    slices = evaluate_calibration_slices(labeled, cfg=cfg, calibrator=calibrator)
    return {
        "success": True,
        "manifest": str(manifest),
        "fit_meta": meta,
        "calibration_slices": slices,
        "cache_dir": str(cache_dir),
        "mode": "fit",
    }


def fit_settlement_calibrator(
    scan_paths: list[Path],
    models_base_dir: Path,
    *,
    cfg: CalibratorConfig | None = None,
    client: KalshiClient | None = None,
    cache_dir: Path | None = None,
    since: datetime | None = None,
    batch_size: int = 25,
) -> dict[str, Any]:
    """Fit calibrator; prefers cache_dir path (refresh then fit)."""
    cfg = cfg or CalibratorConfig()
    if cache_dir is None:
        # Legacy one-shot path (still unique-ticker cached ephemerally).
        df = load_scan_rows(scan_paths, batch_size=batch_size)
        if df.empty:
            return {"success": False, "warnings": ["no scan rows found"]}
        labeled = attach_settlement_outcomes(df, client=client).dropna(subset=["y_true"])
        if len(labeled) < cfg.min_samples:
            return {
                "success": False,
                "warnings": [f"need at least {cfg.min_samples} settled contracts; found {len(labeled)}"],
            }
        calibrator = SettlementProbabilityCalibrator()
        try:
            meta = calibrator.fit(labeled, cfg=cfg)
        except ValueError as exc:
            return {"success": False, "warnings": [str(exc)]}
        manifest = save_calibrator(calibrator, _calibration_dir(Path(models_base_dir)))
        slices = evaluate_calibration_slices(labeled, cfg=cfg, calibrator=calibrator)
        return {
            "success": True,
            "manifest": str(manifest),
            "fit_meta": meta,
            "calibration_slices": slices,
        }

    refresh = refresh_settlement_cache(
        scan_paths,
        cache_dir=cache_dir,
        client=client,
        since=since,
        batch_size=batch_size,
    )
    if not refresh.get("success"):
        return {**refresh, "success": False}
    fit_out = fit_from_cache(cache_dir, models_base_dir, cfg=cfg)
    fit_out["cache_refresh"] = refresh
    return fit_out


def evaluate_scan_settlements(
    scan_paths: list[Path],
    *,
    cfg: SettlementEvalConfig | None = None,
    client: KalshiClient | None = None,
    models_base_dir: Path | None = None,
    cache_dir: Path | None = None,
    since: datetime | None = None,
    batch_size: int = 25,
    report_out: Path | None = None,
) -> dict[str, Any]:
    """
    Join historical scan outputs to Kalshi settled market results.

    When cache_dir is set, refreshes the labeled store then evaluates from cache.
    """
    cfg = cfg or SettlementEvalConfig()
    paths = filter_scan_paths(scan_paths, since=since)
    if cache_dir is not None:
        refresh = refresh_settlement_cache(
            paths,
            cache_dir=cache_dir,
            client=client,
            since=None,  # already filtered
            batch_size=batch_size,
        )
        result = evaluate_from_cache(
            cache_dir,
            cfg=cfg,
            models_base_dir=models_base_dir,
            report_out=report_out,
        )
        result["cache_refresh"] = refresh
        result["n_scans"] = len(paths)
        result["since"] = since.isoformat() if since else None
        return result

    df = load_scan_rows(paths, batch_size=batch_size)
    if df.empty:
        return {"n": 0, "warnings": ["no scan rows found"]}
    labeled = attach_settlement_outcomes(df, client=client)
    result = _metrics_from_labeled(labeled, cfg=cfg, models_base_dir=models_base_dir)
    result["n_scans"] = len(paths)
    result["since"] = since.isoformat() if since else None
    if report_out is not None:
        report_out = Path(report_out)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["report_path"] = str(report_out)
    return result


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%SZ", "%Y%m%dT%H%M%SZ"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized --since value: {raw}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate or fit Kalshi scan probabilities against settled outcomes."
    )
    parser.add_argument(
        "--mode",
        choices=("eval", "fit", "refresh-cache"),
        default=None,
        help="Process mode. Prefer explicit mode so eval and fit never share one process.",
    )
    parser.add_argument(
        "--scan-dir",
        type=Path,
        default=None,
        help="Directory containing scan_*.json files",
    )
    parser.add_argument("--models-base-dir", type=Path, default=None, help="Base models dir for calibrator I/O")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Settlement label cache dir (default: <scan-dir>/../settlement_cache or ./settlement_cache)",
    )
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--since", type=str, default=None, help="Only include scans on/after this UTC date")
    parser.add_argument("--report-out", type=Path, default=None, help="Write eval JSON report to this path")
    parser.add_argument(
        "--fit-calibration",
        action="store_true",
        help="Deprecated alias for --mode fit (still does NOT run eval in the same process)",
    )
    parser.add_argument(
        "--include-no-trade-calibration",
        action="store_true",
        help="Include NO TRADE rows in primary calibration gap (default: exclude)",
    )
    args = parser.parse_args(argv)

    mode = args.mode
    if mode is None:
        mode = "fit" if args.fit_calibration else "eval"

    try:
        since = _parse_since(args.since)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    scan_paths: list[Path] = []
    if args.scan_dir is not None:
        scan_paths = sorted(args.scan_dir.glob("scan_*.json"))

    if args.cache_dir is not None:
        cache_dir = args.cache_dir
    elif args.scan_dir is not None:
        cache_dir = default_cache_dir(args.scan_dir.parent)
    else:
        cache_dir = Path("settlement_cache")

    eval_cfg = SettlementEvalConfig(
        min_samples=args.min_samples,
        exclude_no_trade_for_eval=not args.include_no_trade_calibration,
    )
    fit_cfg = CalibratorConfig(min_samples=max(30, args.min_samples))

    if mode == "refresh-cache":
        if args.scan_dir is None:
            parser.error("--mode refresh-cache requires --scan-dir")
        out = refresh_settlement_cache(
            scan_paths,
            cache_dir=cache_dir,
            since=since,
            batch_size=args.batch_size,
        )
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("success") else 1

    if mode == "fit":
        if args.models_base_dir is None:
            parser.error("--mode fit requires --models-base-dir")
        # Refresh from scans when provided; otherwise fit existing cache only.
        if args.scan_dir is not None:
            refresh = refresh_settlement_cache(
                scan_paths,
                cache_dir=cache_dir,
                since=since,
                batch_size=args.batch_size,
            )
            if not refresh.get("success"):
                print(json.dumps(refresh, indent=2, default=str))
                return 1
            fit_out = fit_from_cache(cache_dir, args.models_base_dir, cfg=fit_cfg)
            fit_out["cache_refresh"] = refresh
        else:
            fit_out = fit_from_cache(cache_dir, args.models_base_dir, cfg=fit_cfg)
        print(json.dumps(fit_out, indent=2, default=str))
        return 0 if fit_out.get("success") else 1

    # mode == eval
    if args.scan_dir is not None:
        result = evaluate_scan_settlements(
            scan_paths,
            cfg=eval_cfg,
            models_base_dir=args.models_base_dir,
            cache_dir=cache_dir,
            since=since,
            batch_size=args.batch_size,
            report_out=args.report_out,
        )
    else:
        result = evaluate_from_cache(
            cache_dir,
            cfg=eval_cfg,
            models_base_dir=args.models_base_dir,
            report_out=args.report_out,
        )
    print(json.dumps(result, indent=2, default=str))
    if result.get("warnings") and result.get("n", 0) < args.min_samples:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
