from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

try:
    # Available in sklearn >= 0.21; present widely.
    from sklearn.ensemble import HistGradientBoostingClassifier
except Exception:  # noqa: BLE001
    HistGradientBoostingClassifier = None  # type: ignore[misc,assignment]

from backtester import _find_future_index, label_outcome, load_time_series
from feature_engineering import FeatureConfig, build_features


ModelFamily = Literal["logreg", "decision_tree", "hgb"]


@dataclass(frozen=True)
class TrainConfig:
    horizon_hours: float = 24.0
    range_threshold_pct: float = 0.01

    model_family: ModelFamily = "logreg"
    random_state: int = 7

    # Time series CV
    n_splits: int = 5

    # Calibration holdout (last chunk after building dataset)
    calibration_frac: float = 0.20
    calibration_method: Literal["isotonic", "sigmoid"] = "isotonic"

    # Feature config
    feature_cfg: FeatureConfig = FeatureConfig()

    # Persistence
    models_dir: Path = Path("models")
    importance_n_repeats: int = 8

    # Explainability
    top_k_explanations: int = 8


OUTCOMES: tuple[str, str, str] = ("up", "down", "range")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_label(y: str) -> int:
    if y == "up":
        return 0
    if y == "down":
        return 1
    return 2


def _label_to_name(i: int) -> str:
    return OUTCOMES[int(i)]


def _safe_snapshot(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def build_labeled_dataset(
    input_path: str | Path,
    cfg: TrainConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Load snapshots, compute features at each t, and label y by looking forward horizon.
    Returns a DataFrame with:
      - timestamp
      - y_true (str)
      - y (int 0/1/2)
      - features... (float)
    """
    cfg = cfg or TrainConfig()
    ts_df = load_time_series(input_path)
    if ts_df.empty:
        raise ValueError("No snapshot time series loaded.")

    ts_df = ts_df.dropna(subset=["timestamp", "spot_price_usd"]).copy()
    ts_df = ts_df.sort_values("timestamp").reset_index(drop=True)
    if ts_df.empty:
        raise ValueError("After dropping missing timestamps/prices, no rows remain.")

    horizon = pd.Timedelta(hours=float(cfg.horizon_hours))
    future_idx = _find_future_index(ts_df["timestamp"], horizon)
    ts_df["future_index"] = future_idx
    ts_df = ts_df[ts_df["future_index"] >= 0].copy()
    ts_df["future_index"] = ts_df["future_index"].astype(int)
    if ts_df.empty:
        raise ValueError("No rows have a valid future horizon. Provide more history.")

    future_prices = ts_df["future_index"].map(
        lambda j: float(ts_df.loc[j, "spot_price_usd"]) if j in ts_df.index else np.nan
    )
    ts_df["future_price"] = pd.to_numeric(future_prices, errors="coerce")
    ts_df = ts_df.dropna(subset=["future_price"]).copy()
    if ts_df.empty:
        raise ValueError("No valid future prices for labeling.")

    ys = [
        label_outcome(float(cp), float(fp), float(cfg.range_threshold_pct))
        for cp, fp in zip(ts_df["spot_price_usd"].astype(float), ts_df["future_price"].astype(float))
    ]
    ts_df["y_true"] = ys
    ts_df = ts_df[ts_df["y_true"].isin(list(OUTCOMES))].copy()
    if ts_df.empty:
        raise ValueError("No rows with valid labels (up/down/range).")

    # Feature build
    X_rows: list[pd.Series] = []
    metas: list[dict[str, Any]] = []
    for snap in ts_df["snapshot"].tolist():
        x, meta = build_features(_safe_snapshot(snap), cfg=cfg.feature_cfg)
        X_rows.append(x)
        metas.append(meta)

    X = pd.DataFrame(X_rows)
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.astype("float64")

    out = pd.concat([ts_df[["timestamp", "y_true"]].reset_index(drop=True), X.reset_index(drop=True)], axis=1)
    out["y"] = out["y_true"].map(_as_label).astype(int)

    meta = {
        "n_rows": int(len(out)),
        "n_features": int(X.shape[1]),
        "feature_names": list(X.columns),
        "warnings_sample": [m.get("warnings", []) for m in metas[:3]],
        "horizon_hours": float(cfg.horizon_hours),
        "range_threshold_pct": float(cfg.range_threshold_pct),
    }
    return out, meta


def _make_estimator(cfg: TrainConfig) -> Any:
    if cfg.model_family == "logreg":
        return LogisticRegression(
            multi_class="multinomial",
            solver="lbfgs",
            max_iter=400,
            C=1.0,
            random_state=cfg.random_state,
        )
    if cfg.model_family == "decision_tree":
        return DecisionTreeClassifier(
            max_depth=3,
            min_samples_leaf=25,
            random_state=cfg.random_state,
        )
    if cfg.model_family == "hgb":
        if HistGradientBoostingClassifier is None:
            raise RuntimeError("HistGradientBoostingClassifier unavailable in this scikit-learn build.")
        return HistGradientBoostingClassifier(
            max_depth=3,
            max_leaf_nodes=31,
            learning_rate=0.08,
            random_state=cfg.random_state,
        )
    raise ValueError(f"Unknown model_family: {cfg.model_family}")


def _make_pipeline(feature_names: list[str], cfg: TrainConfig) -> Pipeline:
    estimator = _make_estimator(cfg)

    # All numeric features; keep column selection stable
    numeric_features = list(feature_names)
    numeric_transform = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            # Standardize only for LR; trees don't need it, but it doesn't harm HGB much.
            ("scaler", StandardScaler(with_mean=True, with_std=True) if cfg.model_family == "logreg" else "passthrough"),
        ]
    )
    pre = ColumnTransformer([("num", numeric_transform, numeric_features)], remainder="drop")
    pipe = Pipeline([("preprocess", pre), ("model", estimator)])
    return pipe


@dataclass(frozen=True)
class TrainedArtifact:
    pipeline: Any
    feature_names: list[str]
    cfg: TrainConfig
    trained_at_utc: str
    metrics: dict[str, Any]

    def predict_proba(self, X_row: pd.Series | pd.DataFrame) -> dict[str, float]:
        if isinstance(X_row, pd.Series):
            X_df = X_row.to_frame().T
        else:
            X_df = X_row.copy()
        X_df = X_df.reindex(columns=self.feature_names)
        proba = self.pipeline.predict_proba(X_df)[0]
        # pipeline classes_ aligns with OUTCOMES order via training y encoding; keep safe mapping
        out = {"up": float(proba[0]), "down": float(proba[1]), "range": float(proba[2])}
        s = sum(out.values()) or 1.0
        return {k: float(v / s) for k, v in out.items()}

    def explain_prediction(self, X_row: pd.Series, top_k: int | None = None) -> list[str]:
        top_k = int(top_k or self.cfg.top_k_explanations)
        model = self.pipeline.named_steps["model"]
        pre = self.pipeline.named_steps["preprocess"]

        X_df = X_row.to_frame().T.reindex(columns=self.feature_names)
        # Use predicted class for directionality
        proba = self.pipeline.predict_proba(X_df)[0]
        pred_class = int(np.argmax(proba))

        if isinstance(model, LogisticRegression):
            Xt = pre.transform(X_df)
            if hasattr(Xt, "toarray"):
                Xt = Xt.toarray()
            x_vec = np.asarray(Xt).reshape(-1)
            coefs = model.coef_[pred_class]
            contrib = x_vec * coefs
            idx = np.argsort(np.abs(contrib))[::-1][:top_k]
            out: list[str] = []
            for j in idx:
                name = self.feature_names[int(j)]
                out.append(f"{name} ({contrib[j]:+.3f})")
            return out

        # Tree-style: path splits narrative
        if hasattr(model, "tree_"):
            tree = model.tree_
            node = 0
            out: list[str] = []
            # Need unscaled values; X_df is raw.
            for _ in range(64):
                feat = int(tree.feature[node])
                if feat < 0:
                    break
                thr = float(tree.threshold[node])
                fname = self.feature_names[feat]
                val = float(X_df.iloc[0, feat]) if np.isfinite(X_df.iloc[0, feat]) else float("nan")
                go_left = bool(val <= thr) if np.isfinite(val) else True
                direction = "<=" if go_left else ">"
                out.append(f"{fname} {direction} {thr:.4g} (x={val:.4g})")
                node = int(tree.children_left[node] if go_left else tree.children_right[node])
                if len(out) >= top_k:
                    break
            return out

        # HGB: no simple path; fallback to permutation-style local sensitivity (1-feature flip is expensive).
        return [f"pred={_label_to_name(pred_class)} prob={float(proba[pred_class]):.3f} (no local explainer for this model)"]


def train_model(
    dataset: pd.DataFrame,
    cfg: TrainConfig | None = None,
) -> TrainedArtifact:
    cfg = cfg or TrainConfig()
    if dataset.empty:
        raise ValueError("Empty dataset.")
    if "y" not in dataset.columns:
        raise ValueError("Dataset missing y column.")

    feature_names = [c for c in dataset.columns if c not in ("timestamp", "y_true", "y")]
    X_all = dataset[feature_names].copy()
    y_all = dataset["y"].astype(int).to_numpy()

    n = len(dataset)
    cal_n = max(50, int(round(cfg.calibration_frac * n)))
    if n <= cal_n + 100:
        cal_n = max(30, int(round(0.15 * n)))
    split = n - cal_n
    split = max(1, min(split, n - 1))

    X_train = X_all.iloc[:split].copy()
    y_train = y_all[:split]
    X_cal = X_all.iloc[split:].copy()
    y_cal = y_all[split:]

    pipe = _make_pipeline(feature_names, cfg)

    # TimeSeriesSplit CV on training chunk (model selection is fixed; report CV metrics)
    tscv = TimeSeriesSplit(n_splits=max(2, int(cfg.n_splits)))
    cv_acc: list[float] = []
    cv_ll: list[float] = []
    for tr_idx, te_idx in tscv.split(X_train):
        pipe_fold = _make_pipeline(feature_names, cfg)
        pipe_fold.fit(X_train.iloc[tr_idx], y_train[tr_idx])
        p = pipe_fold.predict_proba(X_train.iloc[te_idx])
        yhat = np.argmax(p, axis=1)
        cv_acc.append(float(accuracy_score(y_train[te_idx], yhat)))
        cv_ll.append(float(log_loss(y_train[te_idx], p, labels=[0, 1, 2])))

    # Fit base on full training chunk
    pipe.fit(X_train, y_train)

    # Calibrate on final chunk (prefit)
    method = str(cfg.calibration_method)
    try:
        calibrated = CalibratedClassifierCV(pipe, method=method, cv="prefit")
        calibrated.fit(X_cal, y_cal)
        final_model: Any = calibrated
        cal_method_used = method
    except Exception:  # noqa: BLE001
        # Fallback to sigmoid if isotonic fails (e.g. insufficient samples)
        calibrated = CalibratedClassifierCV(pipe, method="sigmoid", cv="prefit")
        calibrated.fit(X_cal, y_cal)
        final_model = calibrated
        cal_method_used = "sigmoid"

    # Holdout metrics (cal chunk, post-calibration)
    p_cal = final_model.predict_proba(X_cal)
    yhat_cal = np.argmax(p_cal, axis=1)
    metrics = {
        "n": int(n),
        "train_n": int(len(X_train)),
        "cal_n": int(len(X_cal)),
        "cv_accuracy_mean": float(np.mean(cv_acc)) if cv_acc else float("nan"),
        "cv_accuracy_std": float(np.std(cv_acc)) if cv_acc else float("nan"),
        "cv_logloss_mean": float(np.mean(cv_ll)) if cv_ll else float("nan"),
        "calibration_method": cal_method_used,
        "holdout_accuracy": float(accuracy_score(y_cal, yhat_cal)),
        "holdout_logloss": float(log_loss(y_cal, p_cal, labels=[0, 1, 2])),
    }

    return TrainedArtifact(
        pipeline=final_model,
        feature_names=feature_names,
        cfg=cfg,
        trained_at_utc=_utc_stamp(),
        metrics=metrics,
    )


def save_artifact(artifact: TrainedArtifact) -> dict[str, str]:
    artifact.cfg.models_dir.mkdir(parents=True, exist_ok=True)
    stem = f"model_{artifact.cfg.model_family}_{artifact.trained_at_utc}"
    model_path = artifact.cfg.models_dir / f"{stem}.joblib"
    meta_path = artifact.cfg.models_dir / f"{stem}.json"
    joblib.dump(
        {
            "pipeline": artifact.pipeline,
            "feature_names": artifact.feature_names,
            "cfg": artifact.cfg,
            "trained_at_utc": artifact.trained_at_utc,
            "metrics": artifact.metrics,
        },
        model_path,
    )
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "feature_names": artifact.feature_names,
                "trained_at_utc": artifact.trained_at_utc,
                "metrics": artifact.metrics,
                "cfg": {
                    "horizon_hours": artifact.cfg.horizon_hours,
                    "range_threshold_pct": artifact.cfg.range_threshold_pct,
                    "model_family": artifact.cfg.model_family,
                    "n_splits": artifact.cfg.n_splits,
                    "calibration_frac": artifact.cfg.calibration_frac,
                    "calibration_method": artifact.cfg.calibration_method,
                },
            },
            f,
            indent=2,
            sort_keys=False,
        )
    return {"model_path": str(model_path), "meta_path": str(meta_path)}


def load_artifact(path: str | Path) -> TrainedArtifact:
    blob = joblib.load(path)
    return TrainedArtifact(
        pipeline=blob["pipeline"],
        feature_names=list(blob["feature_names"]),
        cfg=blob["cfg"],
        trained_at_utc=str(blob["trained_at_utc"]),
        metrics=dict(blob.get("metrics", {})),
    )


def compute_global_importance(
    artifact: TrainedArtifact,
    dataset: pd.DataFrame,
    out_dir: str | Path,
    n_repeats: int | None = None,
) -> pd.DataFrame:
    """
    Permutation importance on the calibration/holdout tail (most realistic live regime).
    Writes a simple bar plot (monochrome) and returns a DataFrame of importances.
    """
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    feature_names = artifact.feature_names
    X = dataset[feature_names].copy()
    y = dataset["y"].astype(int).to_numpy()
    n = len(dataset)
    cal_n = max(30, int(round(artifact.cfg.calibration_frac * n)))
    split = max(1, min(n - cal_n, n - 1))
    X_hold = X.iloc[split:].copy()
    y_hold = y[split:]

    rep = int(n_repeats or artifact.cfg.importance_n_repeats)
    imp = permutation_importance(
        artifact.pipeline,
        X_hold,
        y_hold,
        n_repeats=rep,
        random_state=artifact.cfg.random_state,
        scoring="neg_log_loss",
    )
    df = pd.DataFrame(
        {
            "feature": feature_names,
            "importance_mean": imp.importances_mean,
            "importance_std": imp.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)

    top = df.head(25).iloc[::-1]  # reverse for horizontal bar plot
    fig, ax = plt.subplots(figsize=(7.5, 9.0))
    ax.barh(top["feature"], top["importance_mean"])
    ax.set_xlabel("Permutation importance (Δ neg log loss)")
    ax.set_title("Global feature importance (holdout tail)")
    fig.tight_layout()
    fig.savefig(outp / "permutation_importance.png", dpi=150)
    plt.close(fig)

    df.to_csv(outp / "permutation_importance.csv", index=False)
    return df.reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Train and persist an interpretable BTC movement model (24h horizon).")
    parser.add_argument("input", help="CSV time series, JSON list, directory of snapshots, or single snapshot JSON.")
    parser.add_argument("--model-family", choices=["logreg", "decision_tree", "hgb"], default="logreg")
    parser.add_argument("--horizon-hours", type=float, default=24.0)
    parser.add_argument("--range-threshold-pct", type=float, default=0.01)
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--importance-dir", default="models/importance_latest")
    args = parser.parse_args(argv)

    cfg = TrainConfig(
        horizon_hours=float(args.horizon_hours),
        range_threshold_pct=float(args.range_threshold_pct),
        model_family=str(args.model_family),  # type: ignore[arg-type]
        models_dir=Path(args.models_dir),
    )
    dataset, meta = build_labeled_dataset(args.input, cfg=cfg)
    artifact = train_model(dataset, cfg=cfg)
    paths = save_artifact(artifact)
    compute_global_importance(artifact, dataset, args.importance_dir)

    print(json.dumps({"dataset": meta, "trained": artifact.metrics, "saved": paths}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

