from locust import HttpUser, task, between, events
import random

HOT = [
    "san jose","san francisco","new york","seattle","austin",
    "boston","chicago","los angeles","houston","dallas"
]
LONG_TAIL = [
    "topeka","eugene","boise","lubbock","wichita","lincoln","reno","tulsa","boulder","santa fe",
    "medford","tacoma","spokane","fresno","modesto","sacramento","riverside","bakersfield","el paso","albuquerque"
]

def pick_city():
    # 80/20 split to exercise cache hits vs misses
    return random.choice(HOT) if random.random() < 0.8 else random.choice(LONG_TAIL)

class WeatherUser(HttpUser):
    wait_time = between(0.01, 0.05)

    @task(1)
    def get_weather(self):
        city = pick_city()
        with self.client.get(f"/weather?city={city}", name="/weather", catch_response=True) as resp:
            if resp.status_code not in (200, 404):
                resp.failure(f"Unexpected status {resp.status_code}")

@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    try:
        r = environment.runner.client.get("/stats")
        print("\n--- /stats ---\n", r.text)
    except Exception:
        pass
