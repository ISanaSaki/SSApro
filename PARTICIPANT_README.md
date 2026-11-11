# BloodNet — Participant Kit

Welcome. This folder is the complete public technical kit for the challenge. It intentionally excludes organizer scoring code, hidden simulations, hidden scenario definitions, reference solutions, and private judging materials.

## Start here
1. **Read `Challenge_Brief.pdf` completely** — this is the official problem statement (Persian). Read it yourself before touching any AI tool; understanding the problem is your job, not the model's.
2. Read `CHALLENGE.md` completely.
3. Follow `PRACTICE.md`: run the included starter service, pass the contract tests and complete a full practice scenario on your laptop.
4. Read `participant_kit/DATA_CARD.md` and `participant_kit/openapi.yaml`.
5. Copy `.env.example` to `.env` if you want to override ports/URLs; the defaults already match the local practice services. The two tokens in it are fixed demo values shipped with the kit — there is nothing to request or provision.
6. Build your service so it starts cleanly from a fresh environment and exposes `GET /health`.
7. Keep all state in your application database; expect callbacks to be duplicated, concurrent and out of order.
8. Use the official simulation clock from `GET {GATEWAY_URL}/clock`. Never use wall-clock time for simulation logic.

## Quick start (from GitHub)
```bash
git clone <this repository> bloodnet-kit
cd bloodnet-kit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 starter/starter_app.py &                # included starting implementation (:8000)
python3 -m harness.contract_tests --team http://127.0.0.1:8000
```
Everything runs on your own laptop over localhost using your own internet — there are no accounts, tokens, keys or paid services, and nothing to deploy.

## Package contents
- `Challenge_Brief.pdf`: the official contest problem statement (Persian) — read it first.
- `participant_kit/`: synthetic CSV/YAML data (including `donor_events.csv` temporary-deferral history), API contract and data dictionary.
- `harness/`: the local practice harness — mock Gateway/Travel/Inventory services, scenario runner, contract tests, three public practice scenarios with baselines. Runs on localhost; no tokens, no cloud, no cost.
- `starter/`: a minimal but complete starting implementation (`starter_app.py`) that passes the contract tests; use it as a base, not a ceiling.
- `examples/`: valid request, callback, message and inventory payload examples.
- `tests/`: public schema and dataset sanity checks.
- `CHALLENGE.md`: scope, workflow and deliverables. `PRACTICE.md`: local practice guide.
- `requirements.txt`: dependencies for the practice harness and validation scripts.
- `Dockerfile.example` / `docker-compose.example.yml`: optional container templates for a generic Python service; adapt or ignore them, Docker is not required.

## Runtime services
All three mock services (Gateway + Donor behaviour, Travel, Inventory) are **included in this kit and run locally** — during practice via `harness/`, and the final evaluation uses the same services with a hidden scenario catalogue on the organizers' own machines. Default localhost ports: Gateway 9100, Travel 9200, Inventory 9300. There are no access tokens to obtain: your service accepts the two fixed demo tokens published in `.env.example` (make yours configurable, that is part of the contract).

## Important behavior
- All POST `/requests` calls require a unique `Idempotency-Key`.
- Retry `429` and `503` responses using `Retry-After` and the same idempotency key.
- Callback processing must be idempotent by `event_id`.
- Callback order is not guaranteed; model donor and request state as a state machine.
- Inventory dispatch must be atomic, idempotent by `dispatch_id`, expiry-aware, and compatibility-safe.
- A successful donor response is not a completed donation. Count supply only after the `donated` progress event.
- Check `participant_kit/donor_events.csv`: donors with a `defer_until` later than the current simulation time are temporarily ineligible (tattoo 180 d, travel_risk 90 d).
- `pending_review` requests are not approved until the coordinator approval callback/API is received.
- Never treat the published synthetic eligibility values as real medical advice.

## Submission
Submit a Git repository URL plus your recorded practice/evaluation outputs containing:
- setup/run instructions (a fresh machine must be able to start your service with one command);
- architecture and key design decisions;
- optional AI capability (if any): its input/output, evaluation method and limitations — it must run locally with no paid services, tokens or keys;
- a `DECLARED.md` listing the features you want judged;
- known limitations;
- a reproducible local demo path (the judges re-run your service locally; no credentials are needed).

The printed problem statement (`Challenge_Brief.pdf`) and organizer announcements on contest day take precedence if a wording conflict is discovered.
