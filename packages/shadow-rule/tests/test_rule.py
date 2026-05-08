"""Smoke tests for shadow_rule — no pytest needed, run with `python -m test_rule`."""
import json
import tempfile
from pathlib import Path

from shadow_rule import ShadowRule, analyze


def test_fire_once_per_session():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.jsonl"
        rule = ShadowRule(
            name="t1",
            condition=lambda s: s["x"] > 10,
            log_path=p,
        )
        # Fire 5 times with condition true — only 1 event
        for _ in range(5):
            rule.evaluate({"x": 20})
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 1, f"expected 1 event, got {len(lines)}"
        print("✅ fire_once_per_session")


def test_reset_session():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.jsonl"
        rule = ShadowRule(
            name="t2",
            condition=lambda s: s["x"] > 10,
            log_path=p,
        )
        rule.evaluate({"x": 20})
        rule.reset_session()
        rule.evaluate({"x": 20})
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 2, f"expected 2 events after reset, got {len(lines)}"
        print("✅ reset_session")


def test_never_raises():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.jsonl"
        # Condition that throws
        rule = ShadowRule(
            name="t3",
            condition=lambda s: 1 / 0,
            log_path=p,
        )
        # Should not raise despite ZeroDivisionError in condition
        result = rule.evaluate({"x": 1})
        assert result is False
        assert not p.exists() or p.stat().st_size == 0
        print("✅ never_raises (swallows condition errors)")


def test_persistence():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.jsonl"
        r1 = ShadowRule(name="t4", condition=lambda s: s["x"] > 10, log_path=p)
        r1.evaluate({"x": 20})
        snap = r1.snapshot_flag()
        # New rule instance in a "restart" scenario
        r2 = ShadowRule(name="t4", condition=lambda s: s["x"] > 10, log_path=p)
        r2.restore_flag(snap)
        r2.evaluate({"x": 20})  # Should NOT fire (session flag restored)
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 1, f"expected 1 event (flag persisted), got {len(lines)}"
        print("✅ persistence (snapshot/restore)")


def test_analyze_joins_outcomes():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.jsonl"
        rule = ShadowRule(
            name="ta",
            condition=lambda s: s["x"] > 0,
            log_path=p,
            fire_once_per_session=False,  # allow multiple events
        )
        for i in range(5):
            rule.evaluate({"x": i + 1, "trade_id": 100 + i})

        def outcome_fn(ev):
            tid = ev["state"]["trade_id"]
            return {
                "actual_pnl": -5.0 if tid % 2 == 0 else 3.0,
                "hypothetical_pnl": -2.0 if tid % 2 == 0 else 4.0,
            }

        report = analyze(str(p), outcome_fn)
        assert report.total_fires == 5
        assert report.paired == 5
        assert report.summary_stats["paired_count"] == 5
        assert "total_delta" in report.summary_stats
        print("✅ analyze (paired events + summary stats)")


if __name__ == "__main__":
    test_fire_once_per_session()
    test_reset_session()
    test_never_raises()
    test_persistence()
    test_analyze_joins_outcomes()
    print("\n🎉 all shadow-rule tests passed")
