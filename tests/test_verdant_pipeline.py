from __future__ import annotations

import json
from pathlib import Path

from pipeline_preflight import HORIZON_SPECS, assess_horizon_readiness, audit_snapshots
from scan_interpreter import analyze_scan
from verdant_paths import resolve_data_root, resolve_layout


def test_run_verdant_pipeline_importable():
    """Pipeline script must resolve repo modules when run from examples/."""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(repo / "examples" / "run_verdant_pipeline.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )
    assert proc.returncode == 0, proc.stderr
    assert "Verdant multi-horizon ML pipeline" in proc.stdout


def test_resolve_layout_defaults():
    root = Path("/tmp/btc_test_root").resolve()
    layout = resolve_layout(root)
    assert layout.snapshots_dir == root / "snapshots"
    assert layout.models_dir == root / "models"
    assert layout.hourly_outputs_dir == root / "hourly_outputs"


def test_resolve_data_root_explicit():
    assert resolve_data_root("/tmp/x") == Path("/tmp/x").resolve()


def test_audit_snapshots_empty_dir(tmp_path: Path):
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    audit = audit_snapshots(snap_dir, data_root=tmp_path)
    assert audit.snapshot_count == 0
    assert audit.mount_ok is True


def test_horizon_specs_have_five_entries():
    assert len(HORIZON_SPECS) == 5


def test_horizon_specs_keys():
    keys = {s["key"] for s in HORIZON_SPECS}
    assert keys == {"15m", "30m", "60m", "4h", "24h"}


def test_assess_horizon_readiness_missing_dir(tmp_path: Path):
    spec = HORIZON_SPECS[0]
    result = assess_horizon_readiness(tmp_path / "missing", spec)
    assert result.ok is False
    assert result.labeled_rows == 0


def test_analyze_scan_no_trade_breakdown():
    scan = {
        "timestamp": "2026-05-30T12:00:00+00:00",
        "btc_price": 90000.0,
        "scan_meta": {"pipeline_warnings": [], "kalshi_api_available": True},
        "ranked": {
            "counts": {"buy_yes": 0, "buy_no": 0, "no_trade": 2, "total": 2},
            "buy_yes": [],
            "buy_no": [],
            "all_contracts": [
                {
                    "recommendation": "NO TRADE",
                    "warnings": ["confidence 0.50 below threshold 0.65"],
                },
                {
                    "recommendation": "NO TRADE",
                    "warnings": ["edge below minimum threshold; defaulting to NO TRADE"],
                },
            ],
        },
        "model_summary": {"horizons_available": ["60m"], "ml_any_available": True},
    }
    analysis = analyze_scan(scan)
    assert analysis["counts"]["no_trade"] == 2
    assert "confidence_below_min" in analysis["no_trade_reason_breakdown"]
    assert "edge_below_min" in analysis["no_trade_reason_breakdown"]
