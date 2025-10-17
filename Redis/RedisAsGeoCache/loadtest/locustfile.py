from locust import HttpUser, task, between
import random

SEEDS = [
    # near San Jose / SF (expanded)
    {"name":"Cafe A","lat":37.3382,"lon":-121.8863,"category":"cafe","tags":["chai"]},
    {"name":"Cafe B","lat":37.7749,"lon":-122.4194,"category":"cafe","tags":["coffee"]},
    {"name":"Taco Town","lat":37.4419,"lon":-122.1430,"category":"food","tags":["mexican"]},
    {"name":"Curry Spot","lat":37.5483,"lon":-121.9886,"category":"food","tags":["indian"]},
    {"name":"Palo Alto Bakery","lat":37.4470,"lon":-122.1600,"category":"bakery","tags":["pastry"]},
    {"name":"MV Coffee Lab","lat":37.3861,"lon":-122.0839,"category":"cafe","tags":["third-wave"]},
    {"name":"Sunnyvale Tea House","lat":37.3688,"lon":-122.0363,"category":"cafe","tags":["tea"]},
    {"name":"San Mateo Boba","lat":37.5629,"lon":-122.3255,"category":"cafe","tags":["boba"]},
    {"name":"Oakland Slice","lat":37.8044,"lon":-122.2711,"category":"food","tags":["pizza"]},
    {"name":"SJ Ramen","lat":37.3352,"lon":-121.8811,"category":"food","tags":["ramen"]},
    {"name":"Fremont Diner","lat":37.5483,"lon":-121.9886,"category":"food","tags":["diner"]},
    {"name":"Berkeley Cafe","lat":37.8715,"lon":-122.2730,"category":"cafe","tags":["study"]},
]

class GeoUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        for s in SEEDS:
            self.client.post("/poi", json=s)

    @task(3)
    def search_all(self):
        self.client.get("/poi/nearby", params={"lat":37.33, "lon":-121.90, "radius_km":50, "limit":20})

    @task(1)
    def search_cafe(self):
        self.client.get("/poi/nearby", params={"lat":37.33, "lon":-121.90, "radius_km":50, "limit":10, "category":"cafe"})
