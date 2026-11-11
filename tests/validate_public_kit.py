"""Public, non-scoring sanity checks for the participant dataset."""
from pathlib import Path
import pandas as pd, yaml

ROOT = Path(__file__).resolve().parents[1] / "participant_kit"
required = [
 "donors.csv","hospitals.csv","centers.csv","inventory.csv","areas.csv",
 "compat.yaml","rules.yaml","openapi.yaml","DATA_CARD.md","donor_events.csv",
 "history/requests.csv","history/responses.csv",
 "travel_matrix_areas.csv","travel_area_to_hospital.csv",
 "travel_area_to_center.csv","travel_center_to_hospital.csv"
]
missing = [x for x in required if not (ROOT/x).is_file()]
assert not missing, f"Missing files: {missing}"
donors = pd.read_csv(ROOT/"donors.csv")
hospitals = pd.read_csv(ROOT/"hospitals.csv")
centers = pd.read_csv(ROOT/"centers.csv")
inventory = pd.read_csv(ROOT/"inventory.csv")
requests = pd.read_csv(ROOT/"history/requests.csv")
responses = pd.read_csv(ROOT/"history/responses.csv")
compat = yaml.safe_load((ROOT/"compat.yaml").read_text())
rules = yaml.safe_load((ROOT/"rules.yaml").read_text())
assert donors.donor_id.is_unique
assert hospitals.hospital_id.is_unique and centers.center_id.is_unique
assert set(donors.blood_group) <= set(compat["red_cells"])
assert set(inventory.center_id) <= set(centers.center_id)
assert (inventory.units > 0).all()
assert set(requests.hospital_id) <= set(hospitals.hospital_id)
assert set(responses.donor_id) <= set(donors.donor_id)
assert set(responses.request_id) <= set(requests.rid)
assert donors.notified_90d.ge(0).all()
events = pd.read_csv(ROOT/"donor_events.csv")
assert set(events.event) <= {"tattoo", "travel_risk"}
assert set(events.donor_id) <= set(donors.donor_id)
assert (pd.to_datetime(events.defer_until) > pd.to_datetime(events.event_at)).all()
for name, key in [("travel_matrix_areas.csv","area_id"),
                  ("travel_area_to_hospital.csv","area_id"),
                  ("travel_area_to_center.csv","area_id"),
                  ("travel_center_to_hospital.csv","center_id")]:
    frame = pd.read_csv(ROOT/name)
    assert frame.columns[0] == key, (name, frame.columns[0])
print("PASS: public dataset sanity checks")
print(f"donors={len(donors)} hospitals={len(hospitals)} centers={len(centers)} requests={len(requests)} responses={len(responses)}")
