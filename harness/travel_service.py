"""Travel-time Service with a per-sim-minute quota (stdlib). GET /travel?from=lat,lon&to=lat,lon -> {"minutes":..}"""
import json, sys, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from harness import geo
from harness.simconfig import ORIGIN_LAT, ORIGIN_LON
from harness.common import VClock, make_server, DEFAULT_SPEED


def to_xy(lat, lon):
    return (lon - ORIGIN_LON) * 111.0 * np.cos(np.radians(ORIGIN_LAT)), (lat - ORIGIN_LAT) * 111.0


def serve(clock, port=9200, quota_per_min=30):
    calls, lock = [], threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _s(self, c, b, h=None):
            r = json.dumps(b).encode(); self.send_response(c); self.send_header("Content-Type", "application/json")
            for k, v in (h or {}).items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(r))); self.end_headers(); self.wfile.write(r)
        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/health": return self._s(200, {"ok": True})
            if u.path != "/travel": return self._s(404, {"error": {"code": "not_found", "message": ""}})
            q = parse_qs(u.query)
            try:
                a = [float(v) for v in q["from"][0].split(",")]; b = [float(v) for v in q["to"][0].split(",")]
            except Exception: return self._s(400, {"error": {"code": "validation_error", "message": "from/to=lat,lon"}})
            now = clock.now()
            with lock:
                calls[:] = [t for t in calls if now - t < 1.0]
                if len(calls) >= quota_per_min: return self._s(429, {"error": {"code": "quota_exceeded", "message": "quota"}}, {"Retry-After": "1"})
                calls.append(now)
            ax, ay = to_xy(*a); bx, by = to_xy(*b)
            self._s(200, {"minutes": round(float(geo.route_minutes(ax, ay, bx, by)), 1), "sim_time": round(now, 2)})
    srv = make_server(port, H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv


if __name__ == "__main__":
    serve(VClock(DEFAULT_SPEED)); print("travel on :9200"); threading.Event().wait()
