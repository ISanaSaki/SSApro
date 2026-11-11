"""Fictional province geography: cities, villages, a river with 3 bridges and a slow mountain zone."""
import numpy as np
from harness.simconfig import ORIGIN_LAT, ORIGIN_LON

W_KM, H_KM = 200.0, 160.0
GRID_NX, GRID_NY = 20, 10          # 200 areas of 10 km x 16 km
CITIES = [
    dict(id="C1", name="آذرگان", x=100.0, y=80.0, w=0.36, sigma=6.0),
    dict(id="C2", name="بهارستان", x=45.0, y=122.0, w=0.17, sigma=4.5),
    dict(id="C3", name="پارسیان", x=162.0, y=108.0, w=0.14, sigma=4.0),   # inside mountain zone
    dict(id="C4", name="تبرا", x=60.0, y=35.0, w=0.12, sigma=3.5),
    dict(id="C5", name="سروستان", x=150.0, y=40.0, w=0.10, sigma=3.5),
    dict(id="C6", name="نیلاب", x=112.0, y=142.0, w=0.11, sigma=3.0),
]
BRIDGES_Y = np.array([28.0, 84.0, 136.0])
MTN = (135.0, 200.0, 85.0, 130.0)  # xmin, xmax, ymin, ymax
ROAD_FACTOR, BASE_SPEED, MTN_SPEED, OVERHEAD = 1.25, 55.0, 32.0, 4.0


def river_x(y):
    return 96.0 + 7.0 * np.sin(np.asarray(y, float) / 28.0)


def in_mtn(x, y):
    return (x >= MTN[0]) & (x <= MTN[1]) & (y >= MTN[2]) & (y <= MTN[3])


def route_minutes(px, py, qx, qy):
    """Driving minutes between points (km coords). Broadcasts. River crossing forces a bridge detour;
    mountain endpoints are slow. Deliberately creates 'near as the crow flies, far by road' pairs."""
    px, py, qx, qy = np.broadcast_arrays(*(np.asarray(a, float) for a in (px, py, qx, qy)))
    d = np.hypot(px - qx, py - qy)
    cross = (px > river_x(py)) != (qx > river_x(qy))
    bx = river_x(BRIDGES_Y)
    via = (np.hypot(px[..., None] - bx, py[..., None] - BRIDGES_Y)
           + np.hypot(qx[..., None] - bx, qy[..., None] - BRIDGES_Y)).min(-1)
    length = np.where(cross, via, d) * ROAD_FACTOR
    speed = np.where(in_mtn(px, py) | in_mtn(qx, qy), MTN_SPEED, BASE_SPEED)
    return length / speed * 60.0 + OVERHEAD


def to_latlon(x, y):
    lat = ORIGIN_LAT + np.asarray(y) / 111.0
    lon = ORIGIN_LON + np.asarray(x) / (111.0 * np.cos(np.radians(ORIGIN_LAT)))
    return lat, lon


def to_xy(lat, lon):
    """Inverse of to_latlon (same convention as the Travel service)."""
    x = (np.asarray(lon, float) - ORIGIN_LON) * 111.0 * np.cos(np.radians(ORIGIN_LAT))
    y = (np.asarray(lat, float) - ORIGIN_LAT) * 111.0
    return x, y


def area_index(x, y):
    ix = np.clip((np.asarray(x) // (W_KM / GRID_NX)).astype(int), 0, GRID_NX - 1)
    iy = np.clip((np.asarray(y) // (H_KM / GRID_NY)).astype(int), 0, GRID_NY - 1)
    return iy * GRID_NX + ix


def area_centroids():
    n = GRID_NX * GRID_NY
    ids = np.arange(n)
    cx = (ids % GRID_NX + 0.5) * (W_KM / GRID_NX)
    cy = (ids // GRID_NX + 0.5) * (H_KM / GRID_NY)
    return cx, cy


def make_villages(rng, n=60):
    pts = []
    # 6 deliberately in the mountain zone, the rest uniform away from city centres
    while len(pts) < 6:
        pts.append((rng.uniform(MTN[0] + 3, MTN[1] - 3), rng.uniform(MTN[2] + 3, MTN[3] - 3)))
    while len(pts) < n:
        x, y = rng.uniform(5, W_KM - 5), rng.uniform(5, H_KM - 5)
        if min(np.hypot(x - c["x"], y - c["y"]) for c in CITIES) > 9.0:
            pts.append((x, y))
    pts = np.array(pts)
    w = rng.lognormal(0.0, 0.7, n)
    return pts[:, 0], pts[:, 1], w / w.sum()
