# Participant kit release notes

- Public challenge brief and participant setup guide added.
- API contract includes request lifecycle, coordinator approval, amendment and callback schemas (callback payloads may include an optional `reason`, e.g. decline or no-show details).
- Data dictionary and mock-service contract added.
- Travel matrix row keys are explicitly named.
- `notified_90d` is calculated from the supplied synthetic notification history.
- `donor_events.csv` added: temporary-deferral life events per donor (`tattoo` 180 days, `travel_risk` 90 days per `rules.yaml`). A donor is temporarily ineligible from `event_at` until `defer_until`; notifying such a donor is declined and counted as a safety error.
- The AI capability in your product is OPTIONAL and never part of the core practice score: the harness core is out of 100 and its AI bonus adds up to +10 in practice runs; in the official oral judging the optional AI module is worth up to +20 (maximum 120). Declare the features you want judged in a top-level `DECLARED.md`; a declared feature that fails verification scores 0 for that feature and loses 25% of its available points.
- `requirements.txt` fixed (previous version could not be installed with pip).
- Optional `Dockerfile.example` and `docker-compose.example.yml` templates added; Docker is not required.
- Public examples and dataset sanity checks included (now also validating `donor_events.csv`).

All datasets and contest rules are synthetic. They are not medical advice.

## Added in this release (round 3 — local practice kit)
- `harness/`: a complete LOCAL practice harness — mock Gateway + Donor behaviour, Travel and Inventory services, the scenario runner with scoring, and the contract tests. Everything runs on localhost on your own laptop: no tokens to obtain, no cloud services, no cost.
- Three public practice scenarios (`P-normal`, `P-amend`, `P-abuse`) with shipped Naive/Historic/Oracle practice baselines, so `run_out/result.json` includes an honest local score.
- `starter/starter_app.py`: a minimal but complete starting implementation (stdlib only) that passes the contract tests — use it as your base and improve it.
- `PRACTICE.md`: five-minute quickstart and troubleshooting.
- Scoring clarified: the practice harness core is out of 100 with a +10 practice AI bonus; the official judging is the oral defense (backend 70 / frontend 30) with an optional +20 AI module (see `CHALLENGE.md` and `Judging-Brief-FA.pdf`).
- `requirements.txt` now includes `numpy` (practice harness dependency).
