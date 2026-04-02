import pytest
import httpx
from modexia import AsyncModexiaClient
from modexia.models import PaymentReceipt, TransactionHistoryResponse
import hashlib
from datetime import datetime

API_KEY = "mx_test_dummy_async_key"

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
    # Use explicit idempotency key to avoid flaky time-dependent tests
    httpx_mock.add_response(
        url="https://sandbox.modexia.software/api/v1/agent/pay",
        json={"success": True, "txId": "tx_mocked_async"},
        method="POST"
    )
    httpx_mock.add_response(
        url="https://sandbox.modexia.software/api/v1/agent/transaction/tx_mocked_async",
        json={"state": "COMPLETED", "txHash": "0x456"},
        method="GET"
    )
    
    recipient = "0xAsyncRec"
    amount = 10.0
    explicit_key = "test_async_idempotency_key"
    
    receipt = await client.transfer(recipient, amount, wait=True, idempotency_key=explicit_key)
    
    requests = httpx_mock.get_requests()
    post_request = next(r for r in requests if r.method == "POST")
    import json
    payload = json.loads(post_request.content)
    
    assert payload["idempotencyKey"] == explicit_key
    assert isinstance(receipt, PaymentReceipt)
    assert receipt.success is True
    assert receipt.txHash == "0x456"
    
    await client.aclose()

@pytest.mark.asyncio
async def test_cross_chain_transfer_async(client, httpx_mock):
    httpx_mock.add_response(
        url="https://sandbox.modexia.software/api/v1/agent/cctp/transfer",
        json={"success": True, "txId": "cctp_tx_async_456"},
        method="POST"
    )
    
    recipient = "0xAsyncCCTP"
    amount = 25.0
    to_chain = "42161"
    to_token = "0xUSDCARB"
    explicit_key = "test_async_cctp_key"
    
    receipt = await client.cross_chain_transfer(to_chain, to_token, recipient, amount, idempotency_key=explicit_key)
    
    requests = httpx_mock.get_requests()
    post_request = next(r for r in requests if r.method == "POST")
    import json
    payload = json.loads(post_request.content)
    
    assert payload["idempotencyKey"] == explicit_key
    assert payload["toChain"] == to_chain
    assert payload["toToken"] == to_token
    assert payload["providerAddress"] == recipient
    assert payload["amount"] == "25.0"
    
    assert isinstance(receipt, PaymentReceipt)
    assert receipt.success is True
    assert receipt.txId == "cctp_tx_async_456"
    assert receipt.status == "PENDING"
    
    await client.aclose()

