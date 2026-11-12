"""Tests for AIResponseRankingStrategy (competition module C1)."""
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ai.ranking import AIResponseRankingStrategy  # noqa: E402

MODEL_PATH = REPO_ROOT / "app" / "ai" / "model" / "ranker.joblib"


def make_donors(n):
    return [
        SimpleNamespace(
            donor_id=f"D{i:04d}",
            blood_group=["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"][i % 8],
            sex="F" if i % 2 else "M",
            age=18 + (i % 47),
            weight_kg=50.0 + (i % 40),
            notified_90d=i % 6,
            quiet_start_hour=22 if i % 3 else 0,
            quiet_end_hour=7 if i % 3 else 0,
            last_donation_at=None,
            last_donation_type=None,
        )
        for i in range(n)
    ]


def make_context(donors):
    return SimpleNamespace(
        travel_minutes={d.donor_id: float(100 - i) for i, d in enumerate(donors)},
        history_stats={},
        sim_min=100.0,
    )


def test_strategy_name_and_real_artifact():
    strategy = AIResponseRankingStrategy(str(MODEL_PATH))
    assert strategy.name == "ai_response"
    assert strategy.available is True


def test_rank_returns_all_donors_sorted_desc_scores_in_unit_interval():
    strategy = AIResponseRankingStrategy(str(MODEL_PATH))
    donors = make_donors(30)
    ranked = strategy.rank(donors, make_context(donors))

    assert len(ranked) == len(donors)
    ids = {r.donor_id for r in ranked}
    assert ids == {d.donor_id for d in donors}

    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_rank_tiebreak_prefers_shorter_travel():
    strategy = AIResponseRankingStrategy(str(MODEL_PATH))
    donors = make_donors(10)
    ctx = make_context(donors)
    ranked = strategy.rank(donors, ctx)
    for a, b in zip(ranked, ranked[1:]):
        assert a.score > b.score or (a.score == b.score and a.travel_minutes <= b.travel_minutes)


def test_missing_model_falls_back_to_travel_time_without_exception():
    strategy = AIResponseRankingStrategy(str(REPO_ROOT / "app" / "ai" / "model" / "missing.joblib"))
    assert strategy.available is False

    donors = make_donors(12)
    ranked = strategy.rank(donors, make_context(donors))
    assert len(ranked) == len(donors)
    travels = [r.travel_minutes for r in ranked]
    assert travels == sorted(travels)  # ascending travel = travel_time ranking
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)  # score == -travel


def test_malformed_donors_do_not_raise():
    strategy = AIResponseRankingStrategy(str(MODEL_PATH))
    donors = [SimpleNamespace(donor_id=f"X{i}") for i in range(5)]
    ranked = strategy.rank(donors, make_context(donors))
    assert len(ranked) == 5
