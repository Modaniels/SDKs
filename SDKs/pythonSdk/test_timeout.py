import time
from modexia import ModexiaClient, ModexiaPaymentError

client = ModexiaClient("mx_test_20034c1bf23240af9644a5a37d7c0e2e")
print("Starting timeout test for pending transaction...\n")

# We want to mock _request to always return a PENDING status,
# avoiding actual HTTP 500 errors from hitting a non-existent txId
original_request = client._request

def mock_request(method, endpoint, **kwargs):
    if "transaction/fake_stuck" in endpoint:
        # Simulate a transaction that is permanently stuck in PENDING
        return {"success": True, "state": "PENDING", "txId": "fake_stuck_tx_id_123"}
    return original_request(method, endpoint, **kwargs)

client._request = mock_request

t0 = time.time()
try:
    print(f"Polling started at T+0.0s")
    client._poll_status("fake_stuck_tx_id_123")
except TimeoutError as e:
    elapsed = time.time() - t0
    print(f"\n✅ Successfully caught TimeoutError after {elapsed:.1f}s")
    print(f"Exception message: {e}")
except Exception as e:
    print(f"\n❌ Failed with wrong error: {e}")
