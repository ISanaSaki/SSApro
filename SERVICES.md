# Mock services included in the kit (run locally on your laptop)

These three services ship inside this kit under `harness/` and run on **localhost** — there is
no hosted organizer infrastructure, no access tokens and no cost. Start them via the practice
runner (they come up automatically) or one by one:

```bash
python3 -m harness.mock_gateway      --port 9100          # + Donor Echo (fixed practice behaviour)
python3 -m harness.travel_service    --port 9200
python3 -m harness.inventory_service --port 9300 --kit participant_kit
```

In a full practice run (`python3 -m harness.runner ...`) the Gateway runs the practice donor
simulator (`sim` mode) instead of the fixed echo, so donors decline, accept, arrive, no-show
and donate like they will in evaluation.

## Gateway
- `GET /health` -> `{ "ok": true, "sim_time": number, "mode": "echo" }`
- `GET /clock` -> `{ "sim_time": number, "epoch": "2027-01-15T00:00:00+03:30", "speed": number }`
- `POST /messages` accepts `notification_id`, `donor_id`, `template`, `request_id`, `callback_url`.
- Templates: `request_wave`, `confirmed`, `not_needed`, `cancelled`, `reminder`.
- Responses: `202` accepted; `409` duplicate notification; `429` rate limited (honor `Retry-After`); `503` unavailable.
- The Gateway appends `/callbacks/gateway-status`, `/callbacks/donor-response` and `/callbacks/donor-progress` to `callback_url`.
- Never call admin endpoints (`/admin/*`): they are reserved for the harness and are not part of the participant contract.

## Travel
- `GET /travel?from=lat,lon&to=lat,lon` -> `{ "minutes": number }`.
- The service may return `429`; retry with bounded backoff.

## Inventory
- `GET /health` -> `{ "ok": true }`
- `GET /inventory` -> `{ "sim_time": number, "items": [{ "center_id", "blood_group", "product", "units", "expires_at", "expires_sim_min" }] }`
- `POST /inventory/dispatch` accepts `dispatch_id`, `request_id`, `center_id`, `blood_group`, `product`, `units`.
- Practice mode (`python -m harness.inventory_service --kit participant_kit`) accepts any request_id (it does not know your requests), checks stock, expiry and idempotency only, and needs `hospital_id` and `recipient_blood_group` in the body for ETA and compatibility checks.
- Compatibility is additionally enforced against the harness's registered requests in the evaluation run; an incompatible dispatch is a counted safety error in both cases.
- `201` dispatch created; `200` idempotent replay; `400` invalid input; `404` unknown request (evaluation); `409` insufficient stock or cancelled request; `422` incompatible group, product mismatch or reused dispatch ID with a different body.
- Stock is deducted atomically and by earliest expiry first. A failed dispatch must not deduct stock.
- Delivery ETA is 10 simulation minutes of handling plus center-to-hospital travel.
- Stock is replenished by the mock at simulation midnight. `inventory.csv` is only the initial snapshot.

## Clock, retries and callbacks
- Simulation minute 0 is the published epoch. All SLA, quiet hours, eligibility intervals and deadlines must use simulation time.
- Evaluation may deliver callbacks concurrently, more than once and out of order.
- Deduplicate callbacks by `event_id`, and notifications by your own stable `notification_id`.
- A donor's acceptance is not a completed donation. Only `donated` confirms a donated unit.
