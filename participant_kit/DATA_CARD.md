# BloodNet synthetic dataset — Data Card

## Purpose and safety
This dataset is generated for a programming contest in a fictional province. Every person, hospital, center, coordinate, request, and event is synthetic. It is not a clinical dataset, must not be used for care decisions, and does not define medical eligibility or transfusion policy.

## Snapshot and time
- Snapshot epoch: `2027-01-15T00:00:00+03:30` (Iran local time, fixed contest clock).
- CSV timestamps are ISO-8601 local timestamps without a UTC offset unless explicitly stated otherwise.
- Simulation APIs use floating-point simulation minutes since the snapshot epoch. Use the Gateway `/clock` endpoint; do not use operating-system wall time.

## Files
| File | Rows / purpose |
|---|---|
| `donors.csv` | Synthetic donor profile, blood group, age/weight, fictional coordinates, quiet hours, last donation and 90-day notification count |
| `hospitals.csv` | 14 fictional hospitals, coordinates and synthetic request-weight / credit category |
| `centers.csv` | 5 fictional blood centers, opening hours and bed-capacity metadata |
| `inventory.csv` | Opening stock snapshot at simulation minute 0; it is not the live inventory |
| `areas.csv` | 200 fictional geographic service areas and centroids |
| `compat.yaml` | Contest compatibility matrix by product, recipient group and donor group |
| `rules.yaml` | Initial contest eligibility, interval, SLA, shelf-life and processing parameters |
| `travel_*.csv` | Fictional travel-time matrices in minutes; first column is the named row key |
| `history/requests.csv` | Historical synthetic demand and outcomes over the preceding 365 days |
| `history/responses.csv` | Synthetic notification and donor-response history used for aggregate features |
| `donor_events.csv` | Temporary-deferral life events per donor (`tattoo`, `travel_risk`) with `defer_days` and `defer_until`; a later event replaces an earlier one |

## Important field definitions
- `notified_90d`: number of notification records for the donor in the 90 calendar days preceding the snapshot, calculated from `history/responses.csv`.
- `permanently_excluded`: synthetic permanent exclusion flag. It is not a real-world medical determination.
- `quiet_start_hour`, `quiet_end_hour`: local-hour quiet window. Equal values mean no quiet interval; a start greater than end crosses midnight.
- `credit_level`: synthetic categorical hospital metadata (`low`, `medium`, `high`) for contest prioritization experiments only. It is not a financial credit score and has no legal or real-world meaning.
- `inventory.csv`: opening stock only. Use the Inventory API for current stock during the simulation; stock can be replenished and units expire.
- `travel_*` matrices: row key is the first column (`area_id` or `center_id`); remaining column headers are destination IDs. Values are estimated fictional minutes.
- `donor_events.csv`: each row is a temporary-deferral life event. A donor is ineligible from `event_at` until `defer_until` (tattoo 180 days, travel_risk 90 days per `rules.yaml`). When a donor has several events, the latest one applies. The simulation applies the same rule; notifying a deferred donor is declined and counted as a safety error.

## Product scope
The current API/data package supports `red_cells`, `platelets`, and `plasma`. Teams should implement all three using the published compatibility matrix unless the final event brief explicitly narrows the required scope. Compatibility rules are synthetic contest rules, not medical advice.

## Reproducibility
The organizer retains the generation seed and exact generator version. Teams should treat the supplied CSV/YAML files as immutable inputs. Do not assume that row order has semantic meaning.
