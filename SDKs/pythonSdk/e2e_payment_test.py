#!/usr/bin/env python3
"""
Modexia E2E Payment Test — RouterV3 + Vault Payment Channels
=============================================================

Tests all 3 payment flows:
  1. Direct USDC payment (ModexiaRouterV3)
  2. Micro-payments (1000 consume calls via Vault)
  3. High-frequency burst (100 calls as fast as possible)

Usage:
  1. Create 2 users via the frontend (modexia.software or localhost:3001)
  2. Activate wallets for both users
  3. Fund User A's wallet with USDC on Base Sepolia
  4. Set env vars and run:

     AGENT_API_KEY=mx_test_...  PROVIDER_ADDRESS=0x...  python3 e2e_payment_test.py

  Or edit the constants below directly.
"""

import sys
import os
import time
import uuid

# Add the SDK to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from modexia import ModexiaClient, ChannelStatus, ConsumeResponse

# ────────────────────────────────────────────
# CONFIGURATION — Edit these or use env vars
# ────────────────────────────────────────────
AGENT_API_KEY      = os.environ.get("AGENT_API_KEY", "mx_test_20034c1bf23240af9644a5a37d7c0e2e")
PROVIDER_ADDRESS   = os.environ.get("PROVIDER_ADDRESS", "0x1c56cefb98287280f9d94ba569be7aa329bed42d")
BASE_URL           = os.environ.get("MODEXIA_BASE_URL", "http://localhost:3001")

if not AGENT_API_KEY:
    print("❌ Set AGENT_API_KEY env var (mx_test_... from User A)")
    sys.exit(1)
if not PROVIDER_ADDRESS:
    print("❌ Set PROVIDER_ADDRESS env var (0x... wallet address of User B)")
    sys.exit(1)


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def main():
    # ── INIT ──
    separator("INITIALIZING SDK CLIENT")
    client = ModexiaClient(api_key=AGENT_API_KEY, base_url=BASE_URL, validate=True)
    print(f"✅ Connected as: {client.identity.get('username', '?')}")
    
    balance = client.retrieve_balance()
    print(f"💰 Current USDC balance: {balance}")
    
    wallet_addr = client.identity.get("walletAddress", "unknown")
    print(f"🏦 Agent wallet: {wallet_addr}")
    print(f"📦 Provider:     {PROVIDER_ADDRESS}")

    if float(balance or "0") < 1:
        print(f"\n⚠️  Balance too low for testing. Fund this address with USDC on Base Sepolia:")
        print(f"   {wallet_addr}")
        print(f"   USDC contract: 0x036CbD53842c5426634e7929541eC2318f3dCF7e")
        print(f"   Need at least $1 USDC for the full test suite.")
        sys.exit(1)

    # ══════════════════════════════════════════
    # TEST 1: Direct USDC Payment (RouterV3)
    # ══════════════════════════════════════════
    separator("TEST 1: DIRECT USDC PAYMENT (RouterV3)")
    print("Sending $0.01 USDC directly to provider via RouterV3...")
    
    receipt = None
    try:
        receipt = client.transfer(
            recipient=PROVIDER_ADDRESS,
            amount=0.01,
            idempotency_key=f"e2e-direct-{uuid.uuid4()}",
            wait=True
        )
        print(f"✅ Direct payment {'COMPLETE' if receipt.success else 'FAILED'}")
        print(f"   TX ID:   {receipt.txId}")
        print(f"   Status:  {receipt.status}")
        if receipt.txHash:
            print(f"   TX Hash: {receipt.txHash}")
            print(f"   🔗 https://sepolia.basescan.org/tx/{receipt.txHash}")
    except Exception as e:
        print(f"❌ Direct payment failed: {e}")
        print("   (This might fail if the agent has no USDC or the approve didn't confirm yet)")

    # ══════════════════════════════════════════
    # TEST 2: Micro-Payments (1000 API calls)
    # ══════════════════════════════════════════
    separator("TEST 2: MICRO-PAYMENTS — 1000 API CALLS VIA VAULT")
    
    # Step 2a: Open a channel with $0.50 deposit
    print("Opening payment channel ($0.50 deposit, 1h expiry)...")
    try:
        ch = client.open_channel(
            provider=PROVIDER_ADDRESS,
            deposit=0.50,
            duration_hours=1.0
        )
        channel_id = ch["channelId"]
        print(f"✅ Channel opened!")
        print(f"   Channel ID:    {channel_id}")
        print(f"   Deposit:       ${ch['deposit']} USDC")
        print(f"   Expiry:        {ch['expiry']}")
        print(f"   Deposit TX:    {ch['depositTxId']}")
    except Exception as e:
        print(f"❌ Failed to open channel: {e}")
        print("   Skipping micro-payment and HFP tests.")
        separator("TEST RESULTS")
        print("Test 1 (Direct):         PASSED ✅" if (receipt and receipt.success) else "Test 1 (Direct):         FAILED ❌")
        print("Test 2 (Micro):          SKIPPED ⏭️")
        print("Test 3 (HFP):            SKIPPED ⏭️")
        return

    # Wait a few seconds for on-chain deposit confirmation
    print("\n⏳ Waiting 15s for on-chain deposit to confirm...")
    time.sleep(15)

    # Step 2b: Consume 1000 times at $0.0004 each = $0.40 total
    print(f"\n🔄 Starting 1000 micro-payments at $0.0004 each...")
    MICRO_AMOUNT = 0.0004
    NUM_CALLS = 1000
    success_count = 0
    fail_count = 0
    dedup_count = 0
    start_time = time.time()

    for i in range(NUM_CALLS):
        try:
            resp = client.consume_channel(
                channel_id=channel_id,
                amount=MICRO_AMOUNT,
                idempotency_key=f"e2e-micro-{channel_id}-{i}"
            )
            if resp.isDuplicate:
                dedup_count += 1
            else:
                success_count += 1
            
            # Progress every 100 calls
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(f"   [{i+1:4d}/{NUM_CALLS}] ✅ {success_count} ok, remaining: ${resp.remaining} ({rate:.0f} calls/sec)")
                
        except Exception as e:
            fail_count += 1
            if fail_count <= 3:
                print(f"   ❌ Call {i+1} failed: {e}")
            elif fail_count == 4:
                print(f"   ... suppressing further errors")

    elapsed = time.time() - start_time
    rate = NUM_CALLS / elapsed
    
    print(f"\n📊 MICRO-PAYMENT RESULTS:")
    print(f"   Total calls:    {NUM_CALLS}")
    print(f"   Successful:     {success_count}")
    print(f"   Duplicates:     {dedup_count}")
    print(f"   Failed:         {fail_count}")
    print(f"   Duration:       {elapsed:.2f}s")
    print(f"   Rate:           {rate:.1f} calls/sec")
    print(f"   Total consumed: ${success_count * MICRO_AMOUNT:.4f}")

    # Step 2c: Check channel status
    print(f"\n📋 Channel status after 1000 calls:")
    try:
        status = client.get_channel(channel_id)
        print(f"   Deposit:        ${status.deposit}")
        print(f"   Cumulative:     ${status.cumulativePaid}")
        print(f"   Remaining:      ${status.remaining}")
        print(f"   Consume count:  {status.consumeCount}")
        print(f"   State:          {status.state}")
    except Exception as e:
        print(f"   ❌ Status check failed: {e}")

    # ══════════════════════════════════════════
    # TEST 3: High-Frequency Payment Burst
    # ══════════════════════════════════════════
    separator("TEST 3: HIGH-FREQUENCY BURST — 100 CALLS, MAX SPEED")
    
    print(f"🚀 Firing 100 calls as fast as possible (no sleep)...")
    HFP_AMOUNT = 0.0001
    HFP_CALLS = 100
    hfp_success = 0
    hfp_fail = 0
    hfp_start = time.time()
    
    for i in range(HFP_CALLS):
        try:
            resp = client.consume_channel(
                channel_id=channel_id,
                amount=HFP_AMOUNT,
                idempotency_key=f"e2e-hfp-{channel_id}-{i}"
            )
            hfp_success += 1
        except Exception as e:
            hfp_fail += 1
            if hfp_fail <= 2:
                print(f"   ❌ HFP call {i+1} failed: {e}")
    
    hfp_elapsed = time.time() - hfp_start
    hfp_rate = HFP_CALLS / hfp_elapsed if hfp_elapsed > 0 else 0
    
    print(f"\n📊 HFP BURST RESULTS:")
    print(f"   Total calls:    {HFP_CALLS}")
    print(f"   Successful:     {hfp_success}")
    print(f"   Failed:         {hfp_fail}")
    print(f"   Duration:       {hfp_elapsed:.3f}s")
    print(f"   Rate:           {hfp_rate:.1f} calls/sec")
    print(f"   Total consumed: ${hfp_success * HFP_AMOUNT:.4f}")

    # ══════════════════════════════════════════
    # SETTLE CHANNEL
    # ══════════════════════════════════════════
    separator("SETTLING CHANNEL")
    
    print("Settling channel on-chain...")
    try:
        result = client.settle_channel(channel_id)
        print(f"✅ Channel settled!")
        print(f"   To Provider:  ${result.get('toProvider', '?')}")
        print(f"   Platform Fee: ${result.get('toFee', '?')}")
        print(f"   Refund:       ${result.get('toRefund', '?')}")
        print(f"   Settle TX:    {result.get('settleTxId', '?')}")
    except Exception as e:
        print(f"❌ Settlement failed: {e}")

    # ══════════════════════════════════════════
    # LIST ALL CHANNELS
    # ══════════════════════════════════════════
    separator("ALL CHANNELS")
    try:
        channels = client.list_channels()
        for ch_item in channels:
            print(f"   [{ch_item.state:10s}] {ch_item.channelId[:16]}... deposit=${ch_item.deposit} paid=${ch_item.cumulativePaid}")
    except Exception as e:
        print(f"   ❌ List failed: {e}")

    # ══════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════
    separator("FINAL RESULTS")
    
    final_balance = client.retrieve_balance()
    print(f"💰 Final USDC balance: {final_balance}")
    print()
    print(f"   Test 1 (Direct USDC via RouterV3):      {'PASSED ✅' if receipt.success else 'FAILED ❌'}")
    print(f"   Test 2 (1000 Micro-Payments via Vault): {'PASSED ✅' if success_count >= 950 else 'PARTIAL ⚠️'} ({success_count}/{NUM_CALLS})")
    print(f"   Test 3 (100 HFP Burst):                 {'PASSED ✅' if hfp_success >= 90 else 'PARTIAL ⚠️'} ({hfp_success}/{HFP_CALLS})")
    print(f"\n   Total micro-payment throughput: {rate:.1f} calls/sec (sustained), {hfp_rate:.1f} calls/sec (burst)")
    print()


if __name__ == "__main__":
    main()
