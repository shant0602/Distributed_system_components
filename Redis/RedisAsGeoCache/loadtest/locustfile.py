# locustfile.py
import hashlib
from locust import HttpUser, task, between, events

def make_uid(name: str, city: str = "") -> str:
    # Stable ID derived from name (+optional city). No lat/lon here.
    base = f"{name.strip().lower()}|{city.strip().lower()}"
    return hashlib.md5(base.encode()).hexdigest()

SEEDS = [
    {"id": make_uid("Cafe A", "San Jose"),         "name":"Cafe A",            "lat":37.3382,"lon":-121.8863,"category":"cafe","tags":["chai"]},
    {"id": make_uid("Cafe B", "San Francisco"),    "name":"Cafe B",            "lat":37.7749,"lon":-122.4194,"category":"cafe","tags":["coffee"]},
    {"id": make_uid("Taco Town", "Palo Alto"),     "name":"Taco Town",         "lat":37.4419,"lon":-122.1430,"category":"food","tags":["mexican"]},
    {"id": make_uid("Curry Spot", "Fremont"),      "name":"Curry Spot",        "lat":37.5483,"lon":-121.9886,"category":"food","tags":["indian"]},
    {"id": make_uid("Palo Alto Bakery", "Palo Alto"),"name":"Palo Alto Bakery","lat":37.4470,"lon":-122.1600,"category":"bakery","tags":["pastry"]},
    {"id": make_uid("MV Coffee Lab", "Mountain View"),"name":"MV Coffee Lab",  "lat":37.3861,"lon":-122.0839,"category":"cafe","tags":["third-wave"]},
    {"id": make_uid("Sunnyvale Tea House","Sunnyvale"),"name":"Sunnyvale Tea House","lat":37.3688,"lon":-122.0363,"category":"cafe","tags":["tea"]},
    {"id": make_uid("San Mateo Boba","San Mateo"), "name":"San Mateo Boba",    "lat":37.5629,"lon":-122.3255,"category":"cafe","tags":["boba"]},
    {"id": make_uid("Oakland Slice","Oakland"),    "name":"Oakland Slice",     "lat":37.8044,"lon":-122.2711,"category":"food","tags":["pizza"]},
    {"id": make_uid("SJ Ramen","San Jose"),        "name":"SJ Ramen",          "lat":37.3352,"lon":-121.8811,"category":"food","tags":["ramen"]},
    {"id": make_uid("Fremont Diner","Fremont"),    "name":"Fremont Diner",     "lat":37.5483,"lon":-121.9886,"category":"food","tags":["diner"]},
    {"id": make_uid("Berkeley Cafe","Berkeley"),   "name":"Berkeley Cafe",     "lat":37.8715,"lon":-122.2730,"category":"cafe","tags":["study"]},
]

@events.test_start.add_listener
def seed_once(env, **_):
    c = env.runner.client
    for s in SEEDS:
        c.post("/poi", json=s)  # server upserts by id

class GeoUser(HttpUser):
    wait_time = between(0.05, 0.2)

    @task(3)
    def search_all(self):
        self.client.get("/poi/nearby", params={"lat":37.33,"lon":-121.90,"radius_km":50,"limit":20})

    @task(1)
    def search_cafe(self):
        self.client.get("/poi/nearby", params={"lat":37.33,"lon":-121.90,"radius_km":50,"limit":10,"category":"cafe"})
