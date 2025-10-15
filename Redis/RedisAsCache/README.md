# Weather Service with Redis Cache

A FastAPI-based weather service with Redis caching, dogpile protection, and load testing capabilities.

## Architecture

- **FastAPI** web service with Redis cache
- **Cache stampede protection** using distributed locks
- **Stale-while-revalidate** pattern for resilience
- **Load testing** with Locust
- **Docker Compose** for easy deployment

## Quick Start

### 1. Start the Services

```bash
# Build and start all services (app + Redis)
docker compose up -d

# Or rebuild from scratch
docker compose down -v
docker compose build --no-cache app
docker compose up -d
```

### 2. Verify Services

```bash
# Check if services are running
docker compose ps

# Check app health
curl http://localhost:8000/healthz

# Check Redis connection
curl http://localhost:8000/stats
```

### 3. Test the API

```bash
# Get weather for a city
curl "http://localhost:8000/weather?city=San%20Jose"

# Check cache statistics
curl http://localhost:8000/stats
```

## Load Testing with Locust

### 1. Access Locust Web UI

Open your browser and go to: **http://localhost:8089**

### 2. Configure Load Test

- **Number of users**: Start with 10-50
- **Spawn rate**: 2-5 users per second
- **Host**: `http://app:8000` (internal Docker network)

### 3. Start Load Test

Click "Start swarming" to begin the load test.

### 4. Monitor Results

- **Statistics tab**: View request rates, response times, failures
- **Charts tab**: Real-time performance graphs
- **Failures tab**: Any error details
- **Download Data**: Export results as CSV

## API Endpoints

### Weather Endpoint
```
GET /weather?city={city_name}
```

**Example:**
```bash
curl "http://localhost:8000/weather?city=San%20Jose"
```

**Response:**
```json
{
  "temperature": 22.5,
  "humidity": 65,
  "description": "Partly cloudy",
  "city": "San Jose"
}
```

### Statistics Endpoint
```
GET /stats
```

**Response:**
```json
{
  "cache_hits": 150,
  "cache_misses": 25,
  "api_calls": 25,
  "avoided_api_calls": 150,
  "hit_ratio": 0.857
}
```

### Health Check
```
GET /healthz
```

**Response:**
```json
{
  "redis_ok": true,
  "provider_ok": true
}
```

## Cache Configuration

### TTL Settings
- **Fresh TTL**: 5 minutes (300 seconds)
- **Stale TTL**: 24 hours (fallback data)
- **Jitter**: 0-30 seconds (prevents stampede)

### Cache Keys
- **Weather data**: `weather:v1:city:{city_name}`
- **Stale data**: `weather:v1:stale:{city_name}`
- **Statistics**: `stats:cache_hits`, `stats:cache_misses`, `stats:api_calls`

## Load Test Configuration

The Locust test uses an 80/20 split:
- **80%** requests to "hot" cities (San Jose, San Francisco, New York, etc.)
- **20%** requests to "long tail" cities (Topeka, Eugene, Boise, etc.)

This simulates realistic traffic patterns and exercises both cache hits and misses.

## Useful Commands

### Docker Management
```bash
# View logs
docker compose logs -f app
docker compose logs -f redis

# Restart services
docker compose restart app

# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```

### Redis Commands
```bash
# Connect to Redis CLI
docker compose exec redis redis-cli

# View all keys
docker compose exec redis redis-cli KEYS "*"

# Clear cache
docker compose exec redis redis-cli FLUSHDB
```

### Performance Testing
```bash
# Quick API test
curl -w "@curl-format.txt" "http://localhost:8000/weather?city=San%20Jose"

# Multiple requests to test caching
for i in {1..10}; do
  curl -s "http://localhost:8000/weather?city=San%20Jose" > /dev/null
  echo "Request $i completed"
done
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEATHER_TTL` | 300 | Cache TTL in seconds |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection URL |
| `REDIS_POOL_MAX` | 200 | Max Redis connections |

## Troubleshooting

### Service Won't Start
```bash
# Check Docker logs
docker compose logs app
docker compose logs redis

# Verify ports aren't in use
lsof -i :8000
lsof -i :6379
lsof -i :8089
```

### High Response Times
1. Check Redis connection: `curl http://localhost:8000/healthz`
2. Monitor cache hit ratio: `curl http://localhost:8000/stats`
3. Check upstream API status

### Cache Not Working
1. Verify Redis is running: `docker compose ps`
2. Check Redis logs: `docker compose logs redis`
3. Test Redis directly: `docker compose exec redis redis-cli PING`

## Cache Stampede Protection

### What is Cache Stampede?

**Cache stampede** (also called "thundering herd") occurs when multiple requests simultaneously hit a cache miss for the same key, causing all of them to trigger the expensive operation at the same time.

#### Example Scenario:

Imagine 100 users request weather for "San Jose" at the same time:

**Without Protection:**
```
Time: 10:00:00
├── Request 1: Cache MISS → Call weather API
├── Request 2: Cache MISS → Call weather API  
├── Request 3: Cache MISS → Call weather API
├── Request 4: Cache MISS → Call weather API
└── ... (96 more requests all calling the API simultaneously)
```

**Result:** 100 identical API calls to the weather service! This can:
- Overwhelm the upstream API
- Cause rate limiting
- Slow down all requests
- Waste resources

### How the Lock Prevents This:

**With Lock Protection:**
```
Time: 10:00:00
├── Request 1: Cache MISS → Gets LOCK → Calls weather API
├── Request 2: Cache MISS → No lock → WAITS
├── Request 3: Cache MISS → No lock → WAITS  
├── Request 4: Cache MISS → No lock → WAITS
└── ... (96 more requests all WAITING)

Time: 10:00:02 (2 seconds later)
├── Request 1: Stores result in cache → Releases lock
├── Request 2: Finds cached result → Returns immediately
├── Request 3: Finds cached result → Returns immediately
└── ... (all 99 other requests get cached result)
```

**Result:** Only 1 API call instead of 100!

### The Lock Mechanism:

**1. Redis Lock (`SET NX`):**
```python
got_lock = await r.set(lock_key, "1", nx=True, ex=lock_ttl)
```
- `NX` = "set only if key doesn't exist"
- Only ONE process can set this lock
- Others get `False` and must wait

**2. Wait and Poll:**
```python
if not got_lock:
    while time.time() < deadline:
        await asyncio.sleep(0.02)  # Wait 20ms
        val = await cache_get(key)  # Check if result is ready
        if val is not None:
            return val  # Got the result!
```

**3. Lock Expiration:**
- Lock expires after 5 seconds
- Prevents deadlocks if the process crashes
- Ensures the system doesn't hang forever

### Why This Works:

- **Serializes expensive operations** - Only one process does the work
- **Others benefit from the work** - They get the cached result
- **Failsafe mechanism** - Lock expires to prevent deadlocks
- **Efficient waiting** - Short polling intervals (20ms)

This transforms a potential 100x resource waste into a single API call with 99 fast cache hits!

## Architecture Benefits

- **Cache Stampede Protection**: Distributed locks prevent multiple simultaneous API calls
- **Stale-While-Revalidate**: Serves stale data when upstream fails
- **TTL + Jitter**: Prevents simultaneous cache expiration
- **Statistics Tracking**: Monitor cache performance
- **Dockerized**: Easy deployment and scaling
