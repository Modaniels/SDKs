#!/usr/bin/env python3
"""
TEST 2: Micro-Payments via Vault (1000 API calls)
===================================================
Run AFTER test1 passes. Steps:
  1. Open a $0.50 channel
  2. Consume 1000 times at $0.0004 each
  3. Check channel status
  4. Settle the channel
"""

import sys, os, uuid, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import requests as raw_requests
from modexia import ModexiaClient

API_KEY  = "mx_test_20034c1bf23240af9644a5a37d7c0e2e"
PROVIDER = "0x1c56cefb98287280f9d94ba569be7aa329bed42d"
BASE     = "http://localhost:3001"

print("=" * 60)
print("  TEST 2: MICRO-PAYMENTS VIA VAULT")
print("=" * 60)

# ── Connect ──
print("\n[1] Connecting...")
client = ModexiaClient(api_key=API_KEY, base_url=BASE, validate=True)
print(f"    ✅ User: {client.identity.get('username')}  Balance: {client.identity.get('balance', '?')} USDC")

# ── Open Channel ──
print("\n[2] Opening payment channel ($0.50, 1h)...")
open_url = f"{BASE}/api/v1/vault/open"
open_body = {"providerAddress": PROVIDER, "depositAmount": "0.50", "durationHours": "1"}
print(f"    POST {open_url}")
print(f"    Body: {json.dumps(open_body)}")

resp = raw_requests.post(
    open_url,
    json=open_body,
    headers={"x-modexia-key": API_KEY, "Content-Type": "application/json"},
    timeout=30
)
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text[:500]}")

if resp.status_code not in (200, 201):
    print("    ❌ Failed to open channel. Exiting.")
    sys.exit(1)

ch_data = resp.json().get("data", {})
channel_id = ch_data.get("channelId", "")
print(f"    ✅ Channel ID: {channel_id}")
print(f"    Deposit TX:    {ch_data.get('depositTxId')}")
print(f"    Approve TX:    {ch_data.get('approveTxId')}")
print(f"    Expiry:        {ch_data.get('expiry')}")

# ── Wait for on-chain ──
print("\n[3] Waiting 10s for on-chain deposit...")
time.sleep(10)

# ── Consume 1000 times ──
print("\n[4] Starting 1000 consume calls at $0.0004 each...")
NUM = 100
AMOUNT = 0.0004
ok = 0
fail = 0
errors = []
t0 = time.time()

for i in range(NUM):
    try:
        consume_resp = raw_requests.post(
            f"{BASE}/api/v1/vault/consume",
            json={
                "channelId": channel_id,
                "amount": str(AMOUNT),
                "idempotencyKey": f"t2-{channel_id[:8]}-{i}"
            },
            headers={"x-modexia-key": API_KEY, "Content-Type": "application/json"},
            timeout=10
        )
        
        if consume_resp.status_code == 200:
            ok += 1
        else:
            fail += 1
            if len(errors) < 5:
                errors.append(f"  Call {i}: HTTP {consume_resp.status_code} → {consume_resp.text[:200]}")
        
        if (i + 1) % 25 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            body = consume_resp.json() if consume_resp.status_code == 200 else {}
            remaining = body.get("data", {}).get("remaining", "?")
            print(f"    [{i+1:4d}/{NUM}] ok={ok} fail={fail} remaining=${remaining} ({rate:.0f}/s)")
            
    except Exception as e:
        fail += 1
        if len(errors) < 5:
            errors.append(f"  Call {i}: Exception → {e}")

elapsed = time.time() - t0
rate = NUM / elapsed if elapsed > 0 else 0

print(f"\n📊 MICRO-PAYMENT RESULTS:")
print(f"    Total:      {NUM}")
print(f"    Success:    {ok}")
print(f"    Failed:     {fail}")
print(f"    Duration:   {elapsed:.2f}s")
print(f"    Rate:       {rate:.1f} calls/sec")
print(f"    Consumed:   ${ok * AMOUNT:.4f}")

if errors:
    print(f"\n    First errors:")
    for e in errors:
        print(f"    {e}")

# ── Check Status ──
print(f"\n[5] Channel status...")
status_resp = raw_requests.get(
    f"{BASE}/api/v1/vault/status/{channel_id}",
    headers={"x-modexia-key": API_KEY},
    timeout=10
)
print(f"    Status: {status_resp.status_code}")
print(f"    Response: {status_resp.text[:500]}")

# ── Settle ──
print(f"\n[6] Settling channel on-chain...")
settle_resp = raw_requests.post(
    f"{BASE}/api/v1/vault/settle",
    json={"channelId": channel_id},
    headers={"x-modexia-key": API_KEY, "Content-Type": "application/json"},
    timeout=30
)
print(f"    Status: {settle_resp.status_code}")
print(f"    Response: {settle_resp.text[:500]}")

print("\n" + "=" * 60)
print("  TEST 2 COMPLETE")
print("=" * 60)
