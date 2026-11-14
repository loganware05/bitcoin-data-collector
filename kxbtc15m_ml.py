"""Contract-specific KXBTC15M train/eval against settlement outcomes.

Hermetic by default: reads fixture JSONL/JSON labeled with settlement_value.
Does not enable live trading. Time-ordered evaluation only (no shuffle).
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kxbtc15m_settlement_model import (
    estimate_p_up_settlement,
    label_settlement_outcome,
    time_ordered_calibration,
)


@dataclass(frozen=True)
class TrainEvalResult:
    n_train: int
    n_eval: int
    train_calibration: dict[str, Any]
    eval_calibration: dict[str, Any]
    fitted_vol: float
    notes: list[str]


def load_labeled_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text().strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    return list(data.get("rows") or data.get("examples") or [])


def _fit_vol_grid(rows: list[dict[str, Any]]) -> float:
    """Pick annualized vol that minimizes Brier on the training slice."""
    candidates = [0.30, 0.40, 0.50, 0.55, 0.65, 0.80, 1.00]
    best_vol = 0.55
    best_brier = float("inf")
    for vol in candidates:
        scored: list[dict[str, Any]] = []
        for r in rows:
            p, _ = estimate_p_up_settlement(
                settlement_index=float(r["settlement_index_at_decision"]),
                target_price=float(r["target_price"]),
                time_remaining_seconds=float(r["time_remaining_seconds"]),
                annualized_volatility=vol,
                directional_bias=float(r.get("directional_bias") or 0.0),
            )
            if p is None:
                continue
            label = label_settlement_outcome(
                settlement_value=float(r["settlement_value"]),
                target_price=float(r["target_price"]),
            )
            scored.append(
                {
                    "timestamp": r.get("timestamp") or r.get("close_time"),
                    "model_probability_up": p,
                    "outcome_up": label["outcome_up"],
                }
            )
        cal = time_ordered_calibration(scored)
        brier = cal["brier"] if cal["brier"] is not None else float("inf")
        if brier < best_brier:
            best_brier = brier
            best_vol = vol
    return best_vol


def score_rows(rows: list[dict[str, Any]], *, vol: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        p, drivers = estimate_p_up_settlement(
            settlement_index=float(r["settlement_index_at_decision"]),
            target_price=float(r["target_price"]),
            time_remaining_seconds=float(r["time_remaining_seconds"]),
            annualized_volatility=vol,
            directional_bias=float(r.get("directional_bias") or 0.0),
        )
        label = label_settlement_outcome(
            settlement_value=float(r["settlement_value"]),
            target_price=float(r["target_price"]),
        )
        out.append(
            {
                "timestamp": r.get("timestamp") or r.get("close_time"),
                "contract_ticker": r.get("contract_ticker"),
                "model_probability_up": p,
                "outcome_up": label["outcome_up"],
                "label": label["label"],
                "drivers": drivers,
            }
        )
    return [x for x in out if x["model_probability_up"] is not None]


def train_eval_time_ordered(
    rows: list[dict[str, Any]],
    *,
    eval_fraction: float = 0.30,
) -> TrainEvalResult:
    ordered = sorted(rows, key=lambda r: str(r.get("timestamp") or r.get("close_time") or ""))
    n = len(ordered)
    if n < 4:
        raise ValueError(f"need at least 4 labeled rows; got {n}")
    split = max(2, min(n - 2, int(math.floor(n * (1.0 - eval_fraction)))))
    train_rows = ordered[:split]
    eval_rows = ordered[split:]
    vol = _fit_vol_grid(train_rows)
    train_scored = score_rows(train_rows, vol=vol)
    eval_scored = score_rows(eval_rows, vol=vol)
    return TrainEvalResult(
        n_train=len(train_scored),
        n_eval=len(eval_scored),
        train_calibration=time_ordered_calibration(train_scored),
        eval_calibration=time_ordered_calibration(eval_scored),
        fitted_vol=vol,
        notes=[
            "Time-ordered split; no shuffle.",
            "Vol grid-fit on train Brier only.",
            "approved_for_execution remains false.",
        ],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, required=True, help="Fixture JSON/JSONL of labeled rows")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    rows = load_labeled_rows(args.labels)
    result = train_eval_time_ordered(rows)
    payload = {
        "n_train": result.n_train,
        "n_eval": result.n_eval,
        "fitted_vol": result.fitted_vol,
        "train_calibration": result.train_calibration,
        "eval_calibration": result.eval_calibration,
        "notes": result.notes,
        "approved_for_execution": False,
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
