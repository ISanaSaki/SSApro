# BloodNet — Local Practice Guide

Everything in this kit runs **on your own laptop, on localhost, with your own internet
connection**. There are **no tokens to obtain, no cloud services, no API keys and no cost**:
the only credentials are the two fixed demo tokens below, shipped in the kit itself. This kit
is a deliberate **starting base** — build anything you like on top of it.

## What is in `harness/`

| Module | What it is |
|---|---|
| `mock_gateway.py` | Notification Gateway + Donor behaviour, `GET /clock` (the official simulation clock) |
| `travel_service.py` | Travel-time service (`GET /travel?from=lat,lon&to=lat,lon`) |
| `inventory_service.py` | Center Inventory service (`GET /inventory`, `POST /inventory/dispatch`) |
| `runner.py` | Runs a full practice scenario against your service and scores it |
| `contract_tests.py` | Black-box contract tests for the required API |
| `practice_scenarios.py` | The three public practice scenarios (P-normal, P-amend, P-abuse) |
| `practice_baselines.json` | Naive/Historic/Oracle reference metrics for those scenarios |
| `starter/starter_app.py` | A minimal but complete starting implementation of the whole contract |

## Quickstart (about 5 minutes)

```bash
# 1. dependencies (Python 3.10+)
pip install -r requirements.txt

# 2. boot the included starter service, or point the tools at your own service
python3 starter/starter_app.py            # listens on http://localhost:8000

# 3. verify your service against the contract
python3 -m harness.contract_tests --team http://127.0.0.1:8000

# 4. run a full practice scenario (Gateway/Travel/Inventory start automatically)
python3 -m harness.runner --team http://127.0.0.1:8000 --scenario P-normal --seed 1000

# 5. read the outcome
cat run_out/result.json
```

The runner starts the Gateway (:9100), Travel (:9200) and Inventory (:9300) on localhost,
submits the scenario's requests to your service, drives donor callbacks, and writes
`run_out/result.json` with metrics and a score normalized against the shipped practice
baselines (`score_0_100`).

For early development you can also run each mock service alone (pure standard library):

```bash
python3 -m harness.mock_gateway    --port 9100        # Donor Echo mode (fixed behaviour)
python3 -m harness.travel_service  --port 9200
python3 -m harness.inventory_service --port 9300 --kit participant_kit
```

## Practice scenarios

| Scenario | What it exercises |
|---|---|
| `P-normal` | Baseline demand: request lifecycle, stock dispatch, donor waves, callbacks |
| `P-amend` | Urgency amendments and cancellations on live requests |
| `P-abuse` | An unrealistic over-demand burst at one hospital plus requests from an **unregistered** hospital id (`H98`), which must be rejected |

Smoke a scenario quickly with `--max-requests 8 --speed 480`. A full scenario is a few
minutes at the default speed (×240).

## Important notes

- **Restart your service between runs.** The simulation clock restarts at 0 and request ids
  repeat between runs; a fresh instance avoids stale state.
- The practice donor model (`harness/model_api.py`) is a **public practice calibration**.
  The evaluation harness uses a different, unpublished calibration and shifts part of it per
  run — estimate donor behaviour from `participant_kit/history/` and your own practice runs
  instead of hard-coding these numbers.
- Practice scores rank you against Naive/Historic/Oracle on the practice catalogue only.
  The final evaluation runs a larger, different scenario catalogue.
- The optional AI/intelligent capability is **not required**: the core score is out of 100 and
  an AI feature can only add up to **+10 bonus** points in the harness's own practice
  score — in the official oral judging the optional AI module is worth up to **+20**
  (see `CHALLENGE.md`). Any technique is
  allowed (rules, optimization, ML, local models) but everything must run locally without paid
  services or external keys.
- Declare every feature you want judged in a top-level `DECLARED.md` in your repository.

## Troubleshooting

- **Port already in use** (9100/9200/9300/8000): stop the previous process or pass
  `--gateway-port/--travel-port/--inventory-port`.
- **Windows slow localhost**: the harness already listens on IPv4+IPv6; point `--team` at
  `http://127.0.0.1:8000` rather than `localhost` if you see ~2 s delays.
- **Callbacks arriving twice / out of order**: that is intentional chaos, deduplicate by
  `event_id`.
