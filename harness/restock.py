"""Nightly center-stock replenishment (public world physics).
Every simulated midnight the centers receive a fresh delivery of red cells, plasma and
platelets; expired units are dropped. This is the same rule the Inventory service applies —
`inventory.csv` is only the day-0 snapshot."""
import numpy as np
from harness.simconfig import GROUP_FREQ


def restock(W, S, R, rng, day, target_per_center=None):
    """Nightly delivery of red cells/plasma/platelets from the (abstracted) national supply into center stock."""
    base = {0: 9.0, 1: 1.0, 2: 4.0}
    for c in range(len(W.beds0)):
        share = W.beds0[c] / sum(W.beds0)
        for p in range(3):
            for g in range(8):
                lam = base[p] * 1.3 * share * GROUP_FREQ[g]
                k = rng.poisson(lam)
                if k:
                    S.stock.setdefault((c, g, p), []).append([k, day + R.shelf_days[p] * rng.uniform(0.5, 1.0)])
    for key, bl in S.stock.items():
        S.stock[key] = [b for b in bl if b[0] > 0 and b[1] > day]
