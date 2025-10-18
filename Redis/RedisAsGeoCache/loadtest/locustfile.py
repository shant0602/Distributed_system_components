# locustfile.py
import os, random, uuid
from locust import HttpUser, task, between

# ------------------- Config -------------------
BASE_LAT = float(os.getenv("BASE_LAT", 37.3382))        # San Jose
BASE_LON = float(os.getenv("BASE_LON", -121.8863))
DRIVERS_PER_USER = int(os.getenv("DRIVERS_PER_USER", 20))
UPDATE_BATCH = int(os.getenv("UPDATE_BATCH", 5))         # how many drivers to move per tick
UPDATE_EVERY = (float(os.getenv("DRIVER_MIN_WAIT", 0.1)),
                float(os.getenv("DRIVER_MAX_WAIT", 0.3)))
SEARCH_EVERY = (float(os.getenv("DISP_MIN_WAIT", 0.5)),
                float(os.getenv("DISP_MAX_WAIT", 1.5)))
RADIUS_KM = float(os.getenv("SEARCH_RADIUS_KM", 10))
LIMIT = int(os.getenv("SEARCH_LIMIT", 100))

# Movement tuning
MAX_SPEED = float(os.getenv("MAX_SPEED_DEG", 0.001))     # ~100 m per tick near equator
TURN_PROB = float(os.getenv("TURN_PROB", 0.1))
BOUND_BOX_KM = float(os.getenv("BOUND_BOX_KM", 8))       # keep drivers around base

# ------------------- Helpers -------------------
def km_to_deg_lat(km: float) -> float:
    return km / 110.574

def km_to_deg_lon(km: float, lat: float) -> float:
    import math
    return km / (111.320 * max(0.01, abs(math.cos(math.radians(lat)))))

LAT_SPAN = km_to_deg_lat(BOUND_BOX_KM)
LON_SPAN = km_to_deg_lon(BOUND_BOX_KM, BASE_LAT)

def clamp(lat, lon):
    lat = max(min(lat, BASE_LAT + LAT_SPAN), BASE_LAT - LAT_SPAN)
    lon = max(min(lon, BASE_LON + LON_SPAN), BASE_LON - LON_SPAN)
    return lat, lon

def make_payload(d):
    return {
        "id": d["id"],
        "name": d["name"],
        "lat": d["lat"],
        "lon": d["lon"],
        "category": "driver",           # keep lowercase, server normalizes
        "tags": d["tags"],
    }

def new_driver(user_prefix: str):
    # start near base with small random offset
    lat = BASE_LAT + random.uniform(-LAT_SPAN * 0.2, LAT_SPAN * 0.2)
    lon = BASE_LON + random.uniform(-LON_SPAN * 0.2, LON_SPAN * 0.2)
    return {
        "id": f"driver-{user_prefix}-{uuid.uuid4().hex[:8]}",
        "name": f"driver-{user_prefix}",
        "lat": lat,
        "lon": lon,
        "tags": ["available"],
        "_dx": random.uniform(-MAX_SPEED, MAX_SPEED),
        "_dy": random.uniform(-MAX_SPEED, MAX_SPEED),
    }

def move_driver(d):
    if random.random() < TURN_PROB:
        d["_dx"] = random.uniform(-MAX_SPEED, MAX_SPEED)
        d["_dy"] = random.uniform(-MAX_SPEED, MAX_SPEED)
    d["lat"] += d["_dy"]
    d["lon"] += d["_dx"]
    d["lat"], d["lon"] = clamp(d["lat"], d["lon"])

print("[INIT] Locustfile loaded")

# ------------------- Single user class (owns 20 drivers) -------------------
class FleetUser(HttpUser):
    # unify wait_time to cover both update & search cadences
    wait_time = between(min(UPDATE_EVERY[0], SEARCH_EVERY[0]),
                        max(UPDATE_EVERY[1], SEARCH_EVERY[1]))

    def on_start(self):
        # unique prefix per user (stable for user lifetime)
        self.user_prefix = uuid.uuid4().hex[:12]
        # create this user's fleet
        self.drivers = [new_driver(self.user_prefix) for _ in range(DRIVERS_PER_USER)]
        self._cursor = 0

        # seed all drivers owned by this user
        ok = 0
        for d in self.drivers:
            r = self.client.post("/poi", json=make_payload(d), name="POST /poi (seed-per-user)")
            if r.status_code < 300:
                ok += 1
        print(f"[SEED] base_url={self.client.base_url} | user={self.user_prefix} | seeded {ok}/{len(self.drivers)}")

    @task(3)
    def move_some_drivers(self):
        # move a batch of drivers each tick (round-robin)
        n = len(self.drivers)
        if n == 0:
            return
        end = self._cursor + max(1, min(UPDATE_BATCH, n))
        for i in range(self._cursor, end):
            d = self.drivers[i % n]
            move_driver(d)
            r = self.client.post("/poi", json=make_payload(d), name="POST /poi (move)")
            if r.status_code >= 300:
                # simple error print; Locust will also record request failure
                print(f"[MOVE][ERR] status={r.status_code} body={r.text[:160]}")
        self._cursor = end % n

    @task(1)
    def nearby_search(self):
        self.client.get(
            "/poi/nearby",
            params={
                "lat": BASE_LAT,
                "lon": BASE_LON,
                "radius_km": RADIUS_KM,
                "limit": LIMIT,
                "category": "driver",
            },
            name="GET /poi/nearby (drivers)"
        )
