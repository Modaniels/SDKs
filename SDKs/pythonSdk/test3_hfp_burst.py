#!/usr/bin/env python3
"""
TEST 3: High-Frequency Payment Burst
======================================
Run AFTER test2 passes. Opens a fresh channel and fires
100 consume calls as fast as possible to measure max throughput.
"""

import sys, os, uuid, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import requests as raw_requests

API_KEY  = "mx_test_20034c1bf23240af9644a5a37d7c0e2e"
PROVIDER = "0x1c56cefb98287280f9d94ba569be7aa329bed42d"
BASE     = "http://localhost:3001"

print("=" * 60)
print("  TEST 3: HIGH-FREQUENCY BURST")
print("=" * 60)

HEADERS = {"x-modexia-key": API_KEY, "Content-Type": "application/json"}

# ── Open Channel ──
print("\n[1] Opening channel ($1.00, 1h)...")
resp = raw_requests.post(
    f"{BASE}/api/v1/vault/open",
    json={"providerAddress": PROVIDER, "depositAmount": "1.00", "durationHours": "1"},
    headers=HEADERS, timeout=30
)
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text[:300]}")

if resp.status_code not in (200, 201):
    print("    ❌ Failed. Exiting.")
    sys.exit(1)

channel_id = resp.json().get("data", {}).get("channelId", "")
print(f"    ✅ Channel: {channel_id}")

print("\n[2] Waiting 10s for on-chain deposit...")
time.sleep(10)

# ── HFP Burst ──
print("\n[3] Firing 100 calls MAX SPEED...")
NUM = 100
AMOUNT = 0.001
ok = 0
fail = 0
latencies = []

t0 = time.time()
for i in range(NUM):
    t_call = time.time()
    try:
        r = raw_requests.post(
            f"{BASE}/api/v1/vault/consume",
            json={
                "channelId": channel_id,
                "amount": str(AMOUNT),
                "idempotencyKey": f"t3-hfp-{channel_id[:8]}-{i}"
            },
            headers=HEADERS, timeout=10
        )
        latency_ms = (time.time() - t_call) * 1000
        latencies.append(latency_ms)
        
        if r.status_code == 200:
            ok += 1
        else:
            fail += 1
            if fail <= 3:
                print(f"    ❌ Call {i}: HTTP {r.status_code} → {r.text[:150]}")
    except Exception as e:
        fail += 1
        if fail <= 3:
            print(f"    ❌ Call {i}: {e}")
            
elapsed = time.time() - t0
rate = NUM / elapsed if elapsed > 0 else 0

print(f"\n📊 HFP BURST RESULTS:")
print(f"    Total:      {NUM}")
print(f"    Success:    {ok}")
print(f"    Failed:     {fail}")
print(f"    Duration:   {elapsed:.3f}s")
print(f"    Rate:       {rate:.1f} calls/sec")
if latencies:
    latencies.sort()
    print(f"    Latency p50: {latencies[len(latencies)//2]:.1f}ms")
    print(f"    Latency p95: {latencies[int(len(latencies)*0.95)]:.1f}ms")
    print(f"    Latency p99: {latencies[int(len(latencies)*0.99)]:.1f}ms")
    print(f"    Latency avg: {sum(latencies)/len(latencies):.1f}ms")

# ── Settle ──
print(f"\n[4] Settling channel...")
r = raw_requests.post(
    f"{BASE}/api/v1/vault/settle",
    json={"channelId": channel_id},
    headers=HEADERS, timeout=30
)
print(f"    Status: {r.status_code}")
print(f"    Response: {r.text[:300]}")

print("\n" + "=" * 60)
print("  TEST 3 COMPLETE")
print("=" * 60)
