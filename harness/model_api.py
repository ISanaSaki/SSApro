"""Practice donor-behaviour model (PUBLIC practice calibration).

The function set mirrors the real evaluation model, but the numerical calibration below is a
PRACTICE approximation drawn for realistic-looking practice runs. The evaluation harness uses
a DIFFERENT, unpublished calibration and additionally shifts part of it per run/seed, so do not
over-optimize against these numbers: estimate donor behaviour from history/ and your own
practice runs instead."""
from dataclasses import dataclass, field, asdict
import numpy as np


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


@dataclass
class ModelParams:
    b0: float = -0.25
    b_dist: float = -0.032
    b_night: float = -0.42
    b_urg: tuple = (0.7, 0.25, -0.15)
    b_fatigue: float = -0.28
    b_rel: float = 2.1
    b_rural: float = -0.18
    seen_day: float = 0.86
    seen_night: float = 0.55
    seen_quiet: float = 0.22
    delay_median_min: float = 7.0
    delay_sigma: float = 0.85
    arrive_b0: float = 1.8
    arrive_rel: float = 1.4
    arrive_dist: float = -0.020
    screen_b0: float = 2.2
    abandon_wait_min: float = 70.0
    city_offset: tuple = (0, 0, 0, 0, 0, 0, 0)   # unused by the practice model

    def to_json(self):
        return asdict(self)


def in_quiet(hour, qs, qe):
    cross = qs > qe
    return np.where(qs < 0, False, np.where(cross, (hour >= qs) | (hour < qe), (hour >= qs) & (hour < qe)))


def _hour(ts):
    return np.floor((ts % 1440.0) / 60.0)


def p_seen(P, W, idx, ts):
    h = _hour(ts)
    q = in_quiet(h, W.qs[idx], W.qe[idx])
    night = (h >= 22) | (h < 7)
    return np.where(q, P.seen_quiet, P.seen_night if night else P.seen_day)


def p_accept(P, W, idx, ts, urg, fat, travel):
    h = _hour(ts)
    night = 1.0 if (h >= 22 or h < 7) else 0.0
    off = np.array(P.city_offset)[W.city[idx]]
    z = (P.b0 + P.b_dist * travel + P.b_night * night + P.b_urg[urg] + P.b_fatigue * fat
         + P.b_rel * (W.rel[idx] - 0.5) + P.b_rural * W.rural[idx] + off)
    return sigmoid(z)


def p_arrive(P, W, idx, travel):
    return sigmoid(P.arrive_b0 + P.arrive_rel * (W.rel[idx] - 0.5) + P.arrive_dist * travel)


def p_screen(P, W, idx):
    z = P.screen_b0 + 0.5 * W.health[idx] - 0.02 * np.maximum(W.age[idx] - 50, 0) - 0.05 * np.maximum(55 - W.weight[idx], 0)
    return sigmoid(z)


def p_success(P, W, idx, ts, urg, fat, travel):
    return (p_seen(P, W, idx, ts) * p_accept(P, W, idx, ts, urg, fat, travel)
            * p_arrive(P, W, idx, travel) * p_screen(P, W, idx))


def sample_response(rng, P, W, idx, ts, urg, fat, travel):
    n = len(idx)
    seen = rng.random(n) < p_seen(P, W, idx, ts)
    acc = seen & (rng.random(n) < p_accept(P, W, idx, ts, urg, fat, travel))
    scale = 0.5 if urg == 0 else 1.0
    delay = rng.lognormal(np.log(P.delay_median_min * scale), P.delay_sigma, n)
    return seen, acc, delay


def sample_arrival(rng, P, W, idx, travel):
    n = len(idx)
    arrived = rng.random(n) < p_arrive(P, W, idx, travel)
    delay = travel * rng.lognormal(0.0, 0.2, n) + rng.uniform(3, 8, n)
    passed = rng.random(n) < p_screen(P, W, idx)
    return arrived, delay, passed
