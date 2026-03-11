import pytest
import httpx
from modexia import AsyncModexiaClient
from modexia.models import PaymentReceipt, TransactionHistoryResponse
import hashlib
from datetime import datetime

API_KEY = "mx_test_0123456789abcdef0123456789abcdef"

@pytest.fixture
def client():
    # Return a fresh async client for testing
    return AsyncModexiaClient(api_key=API_KEY)

@pytest.mark.asyncio
async def test_initialization(client):
    assert client.base_url == "https://sandbox.modexia.software"
    assert client.api_key == API_KEY
    assert client.client.headers["x-modexia-key"] == API_KEY
    await client.aclose()

@pytest.mark.asyncio
async def test_retrieve_balance_async(client, httpx_mock):
    httpx_mock.add_response(
        url="https://sandbox.modexia.software/api/v1/user/me",
        json={"data": {"balance": "500.00", "username": "agent2"}},
        method="GET"
    )
    
    balance = await client.retrieve_balance()
    assert balance == "500.00"
    await client.aclose()

@pytest.mark.asyncio
async def test_intent_based_idempotency_hash_async(client, httpx_mock):
    # Mock the transfer endpoint
    httpx_mock.add_response(
        url="https://sandbox.modexia.software/api/v1/agent/pay",
        json={"success": True, "txId": "tx_mocked_async"},
        method="POST"
    )
    # Mock the wait/polling endpoint
    httpx_mock.add_response(
        url="https://sandbox.modexia.software/api/v1/agent/transaction/tx_mocked_async",
        json={"state": "COMPLETED", "txHash": "0x456"},
        method="GET"
    )
    
    recipient = "0x1234567890123456789012345678901234567890"
    amount = 10.0
    
    receipt = await client.transfer(recipient, amount, wait=True)
    
    # httpx_mock allows us to inspect the requests intercept
    requests = httpx_mock.get_requests()
    post_request = next(r for r in requests if r.method == "POST")
    import json
    payload = json.loads(post_request.content)
    
    assert len(payload["idempotencyKey"]) == 64
    assert isinstance(receipt, PaymentReceipt)
    assert receipt.success is True
    assert receipt.txHash == "0x456"
    
    await client.aclose()
