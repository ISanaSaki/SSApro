import json

import pytest

from scripts.smoke import print_summary, wait_health


def test_print_summary(tmp_path, capsys):
    result = {
        "summary": {
            "score_0_100": 61.5,
            "score_final": 61.5,
            "safety": 1,
            "notif_per_unit": 4.2,
            "overfill_units": 0,
            "harness": {"valid_run": True},
        }
    }
    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    print_summary(tmp_path)
    captured = capsys.readouterr().out
    assert "score_0_100" in captured
    assert "61.5" in captured


def test_print_summary_missing_file(tmp_path, capsys):
    print_summary(tmp_path)
    captured = capsys.readouterr().err
    assert "not found" in captured


def test_wait_health_unreachable():
    assert wait_health("http://127.0.0.1:1", timeout_sec=1.5) is False


@pytest.mark.skip(reason="requires a running local service")
def test_wait_health_reachable():
    assert wait_health("http://127.0.0.1:8000", timeout_sec=5.0) is True
