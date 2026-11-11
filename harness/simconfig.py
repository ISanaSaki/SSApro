"""Public contest constants (mirrors participant_kit/rules.yaml and the published data card).
This file ships to participants; it contains no hidden evaluation parameters."""
from datetime import datetime

# Day 0, 00:00 of the simulated timeline (published). History covers [-365, 0).
SNAPSHOT = datetime(2027, 1, 15, 0, 0)
SIM_EPOCH_ISO = "2027-01-15T00:00:00+03:30"   # sim_time 0, Iran local time (published)

# Fictional geographic origin (km -> lat/lon), published in the data card.
ORIGIN_LAT, ORIGIN_LON = 33.0, 50.0

GROUPS = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
GROUP_FREQ = [0.33, 0.28, 0.21, 0.06, 0.042, 0.04, 0.03, 0.008]
PRODUCTS = ["red_cells", "platelets", "plasma"]
URGENCY = ["critical", "urgent", "planned"]
# donation type code per product: 1 whole_blood, 2 platelets, 3 plasma
DON_TYPE = {0: 1, 1: 2, 2: 3}

# Base rules — identical to participant_kit/rules.yaml (version 1).
RULES_V1 = dict(
    version=1,
    age_min=18, age_max=65, weight_min_kg=50,
    interval_wb_male=60, interval_wb_female=90,
    interval_apheresis=14, cross_block=14,
    event_deferral={"tattoo": 180, "travel_risk": 90},
    sla={0: 90, 1: 240, 2: 1440},
    shelf_days={0: 42, 1: 5, 2: 365},
    proc_min=20,
    visit_min={0: 20, 1: 90, 2: 45},
)
