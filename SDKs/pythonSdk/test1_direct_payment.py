#!/usr/bin/env python3
"""
TEST 1: Direct USDC Payment via RouterV3
=========================================
Steps:
  1. Connect + show identity
  2. Register a spending policy (required before any payment)
  3. Send $0.01 USDC to provider
  4. Poll for completion
"""

import sys, os, uuid, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import requests as raw_requests
from modexia import ModexiaClient

API_KEY  = "mx_test_20034c1bf23240af9644a5a37d7c0e2e"
PROVIDER = "0x1c56cefb98287280f9d94ba569be7aa329bed42d"
BASE     = "http://localhost:3001"

print("=" * 60)
print("  TEST 1: DIRECT USDC PAYMENT")
print("=" * 60)

# ── Step 1: Connect ──
print("\n[1] Connecting to Modexia API...")
client = ModexiaClient(api_key=API_KEY, base_url=BASE, validate=True)
print(f"    ✅ User:    {client.identity.get('username')}")
print(f"    💰 Balance: {client.identity.get('balance', '?')} USDC")
print(f"    🏦 Wallet:  {client.identity.get('walletAddress', '?')}")

# ── Step 2: Register spending policy ──
print("\n[2] Registering spending policy...")
# Call the policy endpoint directly with debug
policy_url = f"{BASE}/api/v1/user/policy"
policy_body = {"dailyLimit": "100", "hourlyLimit": "50", "maxPerRequest": "10"}
print(f"    POST {policy_url}")
print(f"    Body: {json.dumps(policy_body)}")

resp = raw_requests.post(
    policy_url,
    json=policy_body,
    headers={"x-modexia-key": API_KEY, "Content-Type": "application/json"},
    timeout=15
)
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text}")

if resp.status_code == 200:
    print("    ✅ Policy registered!")
else:
    print("    ❌ Policy registration failed — direct payment will likely fail too")

# ── Step 3: Direct payment ──
print("\n[3] Sending $0.01 USDC to provider...")
pay_url = f"{BASE}/api/v1/agent/pay"
pay_body = {
    "providerAddress": PROVIDER,
    "amount": "0.01",
    "idempotencyKey": f"test1-direct-{uuid.uuid4()}"
}
print(f"    POST {pay_url}")
print(f"    Body: {json.dumps(pay_body)}")

resp = raw_requests.post(
    pay_url,
    json=pay_body,
    headers={"x-modexia-key": API_KEY, "Content-Type": "application/json"},
    timeout=30
)
print(f"    Status: {resp.status_code}")
print(f"    Response: {resp.text}")

if resp.status_code == 200:
    data = resp.json()
    tx_id = data.get("txId")
    print(f"    ✅ Payment submitted! TX ID: {tx_id}")
    
    if data.get("approveTxId"):
        print(f"    📋 Approve TX: {data['approveTxId']}")
    
    # ── Step 4: Poll status ──
    print(f"\n[4] Polling for tx confirmation (max 60s)...")
    start = time.time()
    while (time.time() - start) < 60:
        try:
            status_resp = raw_requests.get(
                f"{BASE}/api/v1/agent/transaction/{tx_id}",
                headers={"x-modexia-key": API_KEY},
                timeout=10
            )
            state_data = status_resp.json()
            state = state_data.get("state", "UNKNOWN")
            print(f"    ⏳ [{int(time.time()-start):2d}s] State: {state}")
            
            if state in ("COMPLETE", "COMPLETED", "CONFIRMED"):
                print(f"    ✅ PAYMENT CONFIRMED ON-CHAIN!")
                if state_data.get("txHash"):
                    print(f"    🔗 https://sepolia.basescan.org/tx/{state_data['txHash']}")
                break
            elif state == "FAILED":
                print(f"    ❌ PAYMENT FAILED: {state_data.get('errorReason', 'unknown')}")
                break
        except Exception as e:
            print(f"    ⚠️  Poll error: {e}")
        
        time.sleep(3)
    else:
        print(f"    ⏰ Timed out after 60s (tx may still be processing)")
else:
    print(f"    ❌ Payment request failed")

print("\n" + "=" * 60)
print("  TEST 1 COMPLETE")
print("=" * 60)
