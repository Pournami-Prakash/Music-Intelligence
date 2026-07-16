# Linux 512 MB load test — production readiness gate

The serving footprint was tuned against **macOS RSS**, where `malloc_trim` is a
no-op and mmap'd parquet pages inflate the number. This must be re-measured in
the actual Linux container under a hard 512 MB limit before deploying. Do not
adjust `DUCKDB_*` defaults based on macOS behaviour — measure here first.

## Prereqs

- Docker with cgroup memory limits (Linux host, or Docker Desktop).
- A `.env` with `R2_*`, `GROQ_API_KEY`, `UPSTASH_VECTOR_REST_*`.

## 1. Build + run under a hard 512 MB limit

```bash
docker build -t atlas-api .

docker run --rm --name atlas \
  --memory=512m --memory-swap=512m \        # hard limit, no swap → OOM is real
  --env-file .env \
  -e SKIP_STARTUP_WARMUP=1 \
  -p 7860:7860 \
  atlas-api
```

`--memory-swap=512m` (equal to `--memory`) disables swap so an over-limit
process is OOM-killed rather than silently swapping — that's what a free host
does.

## 2. Cold start + disk

```bash
# cold-start: time from `docker run` to first 200
time curl -sf http://localhost:7860/health -o /dev/null

# disk used by the downloaded lookup parquets (should be a few hundred MB)
docker exec atlas du -sh /tmp | tail -1
docker exec atlas sh -c 'ls -lh /tmp/*.parquet 2>/dev/null'
```

Record: cold-start seconds, disk MB. (Disk matters — the lean lookup artifacts
are downloaded to local disk; the host must allow it.)

## 3. Mixed uncached load at concurrency 1, 2, 5, 10

In a second terminal, sample RSS every second while each run executes:

```bash
# terminal A — RSS/OOM sampler (leave running)
while true; do docker stats --no-stream --format '{{.MemUsage}} {{.MemPerc}}' atlas; sleep 1; done | tee rss.log
```

```bash
# terminal B — one run per concurrency level
for C in 1 2 5 10; do
  echo "=== concurrency $C ==="
  python deploy/loadtest.py --base http://localhost:7860 --concurrency $C --count 300
done
```

`loadtest.py` draws params from a large pool so most requests **miss** the
result cache (worst case). It reports p50/p95/p99 latency, throughput, status
breakdown, and max latency (a proxy for queue-wait when the DuckDB semaphore
throttles). Code `-1` = connection reset = a likely OOM restart.

## 4. Soak (cross cache churn)

```bash
python deploy/loadtest.py --base http://localhost:7860 --concurrency 5 --duration 600
```

Watch `rss.log` for monotonic growth. Flat/saw-tooth = healthy (trim + LRU
working). Steady climb toward 512 MB = a leak or the cache/allocator not
releasing — investigate before deploying.

Also capture the cached fast-path for comparison:

```bash
python deploy/loadtest.py --base http://localhost:7860 --concurrency 10 --count 500 --cached
```

## 5. Record + decide

| metric | source | pass criteria |
|---|---|---|
| peak RSS | `rss.log` max | comfortably < 512 MB (leave headroom, e.g. ≤ ~430) |
| OOM / restarts | `docker inspect atlas` `OOMKilled`; code `-1` count | 0 |
| p95 latency (uncached) | loadtest output | acceptable for the UI (define per page) |
| max latency (queue) | loadtest `max` | bounded, not unbounded growth |
| cold start | §2 | acceptable for the host's health-check window |
| disk | §2 | within the host's disk allowance |

```bash
docker inspect atlas --format '{{.State.OOMKilled}}'   # must be false
```

## If it does NOT survive

Apply in order, re-measuring after each — **don't stack speculatively**:

1. `-e DUCKDB_MAX_CONCURRENCY=1` — serialize DuckDB entirely. Simplest way to
   bound memory; costs throughput on uncached bursts.
2. `-e DUCKDB_MEMORY_LIMIT=96MB` — smaller buffer pool (more spilling to disk).
3. Only after measuring queue-wait (loadtest `max` latency): add a bounded
   semaphore acquire-timeout in `cache.duck_slot` that returns HTTP 503 +
   `Retry-After` instead of queueing indefinitely. Measure first so the timeout
   is grounded in real numbers, not a guess. An unbounded public queue is
   undesirable, but a too-tight timeout sheds load unnecessarily.
4. If none fit: move to a ~1 GB free tier (still no card on some hosts) rather
   than degrading features further.
```
