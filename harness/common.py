import json, socket, threading, time, heapq, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

# Practice services and the evaluation run use the same speed, so wall-clock timing mistakes show up in practice too.
DEFAULT_SPEED = 240.0


def header(h, name, default=None):
    """Case-insensitive lookup in a headers dict returned by http()."""
    return next((v for k, v in (h or {}).items() if k.lower() == name.lower()), default)


class VClock:
    """Virtual simulation clock. sim_minutes advance `speed` times faster than wall-clock seconds/60."""
    def __init__(self, speed=60.0, start_min=0.0):
        self.speed, self.t0, self.s0 = speed, time.time(), start_min

    def now(self):
        return self.s0 + (time.time() - self.t0) * self.speed / 60.0

    def wall_for(self, sim_min):
        return max(0.0, (sim_min - self.now()) * 60.0 / self.speed)


class _DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0); super().server_bind()


def make_server(port, handler):
    """Listen on IPv4 and IPv6. An IPv4-only server makes every call to "localhost" wait ~2 s on Windows
    (the client tries ::1 first), which silently wrecks the timing of a simulation run."""
    try: return _DualStackServer(("::", port), handler)
    except OSError: return ThreadingHTTPServer(("0.0.0.0", port), handler)


def http(method, url, body=None, headers=None, timeout=10):
    # Same ~2 s penalty when the *other* side (e.g. a team service) listens on IPv4 only.
    url = url.replace("://localhost:", "://127.0.0.1:", 1)
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(); return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: j = json.loads(raw)
        except Exception: j = None
        return e.code, j, dict(e.headers)
    except Exception as e:
        return 0, {"error": str(e)}, {}


class Scheduler(threading.Thread):
    """Runs callables at virtual times on a worker pool, so one slow callback (e.g. a slow team endpoint)
    cannot delay every callback queued behind it. workers=0 runs them inline, one after another.
    Records two lags, in sim-minutes:
      dispatch: how late the harness itself got to a callable (harness overload; makes a run invalid)
      start:    how late it actually started (also includes waiting for pool workers, e.g. while a slow team holds them)."""
    def __init__(self, clock, workers=128):
        super().__init__(daemon=True); self.clock, self.q, self.cv, self.n, self.stop = clock, [], threading.Condition(), 0, False
        self.pool = ThreadPoolExecutor(workers, thread_name_prefix="sched") if workers else None
        self.lags = {"dispatch": [], "start": []}; self.lag_lock = threading.Lock()

    def at(self, sim_min, fn):
        with self.cv:
            self.n += 1; heapq.heappush(self.q, (sim_min, self.n, fn)); self.cv.notify()

    def _fire(self, t, fn):
        lag = self.clock.now() - t
        with self.lag_lock: self.lags["start"].append(lag)
        try: fn()
        except Exception as e: print("scheduler error", e)

    def lag_stats(self):
        out = {}
        with self.lag_lock:
            for k, v in self.lags.items():
                x = sorted(v)
                out[k] = dict(n=len(x), p50=round(x[len(x) // 2], 3), p95=round(x[int(len(x) * 0.95)], 3), max=round(x[-1], 3)) if x \
                    else dict(n=0, p50=0.0, p95=0.0, max=0.0)
        return out

    def run(self):
        while not self.stop:
            with self.cv:
                if not self.q: self.cv.wait(0.2); continue
                t, _, fn = self.q[0]; w = self.clock.wall_for(t)
                if w > 0: self.cv.wait(min(w, 0.2)); continue
                heapq.heappop(self.q)
            with self.lag_lock: self.lags["dispatch"].append(self.clock.now() - t)
            if self.pool: self.pool.submit(self._fire, t, fn)
            else: self._fire(t, fn)
