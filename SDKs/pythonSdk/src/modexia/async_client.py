"""Modexia Python SDK Async Client.

This module provides `AsyncModexiaClient`, an asynchronous counterpart to `ModexiaClient`.
It leverages `httpx` and `asyncio` for non-blocking I/O, ideal for "Swarm"-style agents
and high-concurrency environments.
"""

import os
import re
import time
import asyncio
import hashlib
import logging
import httpx
from datetime import datetime
from typing import Optional, Dict, Any

from .client import ModexiaAuthError, ModexiaPaymentError, ModexiaNetworkError
from .models import (
    PaymentReceipt, TransactionHistoryItem, TransactionHistoryResponse,
    ChannelReceipt, ConsumeResponse, ChannelStatus
)

import uuid

logger = logging.getLogger("modexia.async")
logger.addHandler(logging.NullHandler())

class AsyncModexiaClient:
    """Official Modexia Python Async Client.

    Example:
        client = AsyncModexiaClient(api_key="mx_test_...")
        await client.retrieve_balance()
        await client.transfer(recipient, amount=1.0)
    """

    VERSION = "0.5.0"
    DEFAULT_TIMEOUT = 15.0

    URLS = {
        "live": "https://api.modexia.software",
        "test": "https://sandbox.modexia.software",
        "local": "http://localhost:3001"
    }

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT, base_url: Optional[str]=None, allow_insecure_http: bool = False):
        self.api_key = api_key
        self.timeout = timeout

        if base_url:
            self.base_url = base_url
        elif os.environ.get("MODEXIA_BASE_URL"):
            self.base_url = os.environ.get("MODEXIA_BASE_URL")
        elif api_key.startswith("mx_live_"):
            self.base_url = self.URLS["live"]
        elif api_key.startswith("mx_test_"):
            self.base_url = self.URLS["test"]
        else:
            self.base_url = self.URLS["local"]
        
        if not re.match(r"^mx_(test|live)_[a-fA-F0-9]{32}$", self.api_key):
            raise ModexiaAuthError("Invalid API key format. Must start with mx_live_ or mx_test_ followed by 32 hex characters.")
            
        if self.base_url.startswith("http://") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            if not allow_insecure_http:
                raise ModexiaNetworkError(f"SECURITY WARNING: Attempting unencrypted HTTP connection to {self.base_url}. API key will be sent in cleartext. Pass allow_insecure_http=True to override.")
            logger.warning(f"SECURITY WARNING: Using unencrypted HTTP connection to {self.base_url}. API key will be sent in cleartext.")
            
        logger.info(f"Resolved base_url to {self.base_url} (Async)")

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "x-modexia-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": f"Modexia-Python-Async/{self.VERSION}"
            }
        )
        self.identity = {}

    async def aclose(self):
        """Close the underlying HTTPX client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    async def validate_session(self) -> Dict[str, Any]:
        """Validate API key and cache identity."""
        res = await self._request("GET", "/api/v1/user/me")
        data = res.get('data', res)
        self.identity = data
        logger.info(f"Connected to Modexia (Async) as: {data.get('username')}")
        return data

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Perform an async HTTP request with basic retry logic."""
        max_retries = 3
        
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.request(method, endpoint, **kwargs)
                
                # Retry on transient server errors
                if response.status_code in [500, 502, 503, 504] and attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                    
                if response.status_code in [401, 403]:
                    raise ModexiaAuthError(f"Unauthorized: {response.text}")
                
                if response.status_code >= 400 and response.status_code != 402:
                    try: 
                        err = response.json().get('error', response.text)
                    except Exception: 
                        excerpt = response.text[:512]
                        err = f"HTTP {response.status_code} at {endpoint}: {excerpt}"
                    raise ModexiaPaymentError(err)
                
                try:
                    data = response.json() if response.content else {}
                except ValueError:
                    excerpt = response.text[:512]
                    raise ModexiaNetworkError(f"HTTP {response.status_code} returned non-JSON data: {excerpt}")
                
                if response.status_code == 200 and isinstance(data, dict) and data.get("success") is False:
                    raise ModexiaPaymentError(data.get("error", data.get("errorReason", "Unknown logical API error")))
                    
                return data
                
            except httpx.RequestError as e:
                if attempt == max_retries:
                    raise ModexiaNetworkError(f"Connection failed: {str(e)}")
                await asyncio.sleep(0.5 * (2 ** attempt))

    async def retrieve_balance(self) -> str:
        """Return the current wallet balance."""
        if not self.identity:
            await self.validate_session()
        return self.identity.get("balance", "0")

    async def get_balance(self) -> str:
        """Alias for `retrieve_balance()`."""
        return await self.retrieve_balance()

    async def transfer(self, recipient: str, amount: float, idempotency_key: Optional[str] = None, wait: bool = True) -> PaymentReceipt:
        """Create a payment from the authenticated agent to `recipient` asynchronously."""
        if not re.match(r"^0x[a-fA-F0-9]{40}$", recipient):
            raise ValueError(f"Invalid recipient address format: {recipient}. Must be a 42-character hex string starting with 0x.")
            
        if not idempotency_key:
            intent_str = f"{recipient}_{amount}_{uuid.uuid4()}"
            ikey = hashlib.sha256(intent_str.encode()).hexdigest()
        else:
            ikey = idempotency_key
            
        payload = {"providerAddress": recipient, "amount": str(amount), "idempotencyKey": ikey}
        data = await self._request("POST", "/api/v1/agent/pay", json=payload)

        if wait and data.get("success"):
            return await self._poll_status(data.get("txId"))

        return PaymentReceipt(
            success=data.get("success", False),
            status="PENDING",
            txId=data.get("txId"),
            errorReason=data.get("error")
        )

    async def _poll_status(self, tx_id: str) -> PaymentReceipt:
        """Poll the server asynchronously for transaction status until timeout."""
        start = time.time()
        while (time.time() - start) < 30:
            data = await self._request("GET", f"/api/v1/agent/transaction/{tx_id}")
            state = data.get("state", "").upper()
            
            if state in ["COMPLETE", "COMPLETED"]:
                return PaymentReceipt(success=True, txId=tx_id, status="COMPLETE", txHash=data.get("txHash"))
            if state == "FAILED":
                raise ModexiaPaymentError(f"Transfer Failed: {data.get('errorReason')}")
            
            await asyncio.sleep(2)
            
        raise TimeoutError(f"Transaction {tx_id} did not settle within 30 seconds. Status remains PENDING.")

    async def get_history(self, limit: int = 5) -> TransactionHistoryResponse:
        """Fetch the transaction history for the authenticated agent."""
        data = await self._request("GET", f"/api/v1/user/transactions?limit={limit}")
        transactions = []
        for t in data.get("transactions", []):
            transactions.append(TransactionHistoryItem(
                txId=t.get("txId", ""),
                type=t.get("type", ""),
                amount=str(t.get("amount", "0")),
                state=t.get("state", ""),
                createdAt=t.get("createdAt", ""),
                providerAddress=t.get("providerAddress"),
                txHash=t.get("txHash")
            ))
            
        return TransactionHistoryResponse(
            transactions=transactions,
            hasMore=data.get("hasMore", False)
        )

    # ═══════════════════════════════════════════════════════════════════
    #  VAULT — Payment Channels for Micro & High-Frequency Transactions
    # ═══════════════════════════════════════════════════════════════════

    async def open_channel(self, provider: str, deposit: float, duration_hours: float = 24.0) -> Dict[str, Any]:
        """Open a payment channel with on-chain deposit asynchronously."""
        if not re.match(r"^0x[a-fA-F0-9]{40}$", provider):
            raise ValueError(f"Invalid provider address format: {provider}. Must be a 42-character hex string starting with 0x.")
            
        payload = {
            "providerAddress": provider,
            "depositAmount": str(deposit),
            "durationHours": str(duration_hours),
        }
        res = await self._request("POST", "/api/v1/vault/open", json=payload)
        return res.get("data", res)

    async def consume_channel(self, channel_id: str, amount: float, idempotency_key: Optional[str] = None) -> ConsumeResponse:
        """Execute an instant, gas-free micro-payment inside a channel asynchronously."""
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        payload = {
            "channelId": channel_id,
            "amount": str(amount),
            "idempotencyKey": idempotency_key,
        }
        res = await self._request("POST", "/api/v1/vault/consume", json=payload)
        data = res.get("data", res)
        receipt_raw = data.get("receipt", {})

        receipt = ChannelReceipt(
            channelId=receipt_raw.get("channelId", channel_id),
            cumulativeTotal=receipt_raw.get("cumulativeTotal", "0"),
            nonce=receipt_raw.get("nonce", 0),
            hmac=receipt_raw.get("hmac", ""),
            timestamp=receipt_raw.get("timestamp", 0),
        )
        return ConsumeResponse(
            success=res.get("success", True),
            receipt=receipt,
            remaining=data.get("remaining", "0"),
            isDuplicate=res.get("duplicate", False),
        )

    async def settle_channel(self, channel_id: str) -> Dict[str, Any]:
        """Settle a channel on-chain asynchronously."""
        res = await self._request("POST", "/api/v1/vault/settle", json={"channelId": channel_id})
        return res.get("data", res)

    async def get_channel(self, channel_id: str) -> ChannelStatus:
        """Get the current status of a payment channel asynchronously."""
        res = await self._request("GET", f"/api/v1/vault/status/{channel_id}")
        d = res.get("data", res)
        return ChannelStatus(
            channelId=d.get("channelId", channel_id),
            providerAddress=d.get("providerAddress", ""),
            deposit=d.get("deposit", "0"),
            cumulativePaid=d.get("cumulativePaid", "0"),
            remaining=d.get("remaining", "0"),
            consumeCount=d.get("consumeCount", 0),
            expiry=d.get("expiry", ""),
            state=d.get("state", ""),
            isExpired=d.get("isExpired", False),
        )

    async def list_channels(self, limit: int = 50) -> list[ChannelStatus]:
        """List all payment channels for the authenticated agent asynchronously."""
        res = await self._request("GET", f"/api/v1/vault/channels?limit={limit}")
        channels = []
        for d in res.get("data", []):
            channels.append(ChannelStatus(
                channelId=d.get("channelId", ""),
                providerAddress=d.get("providerAddress", ""),
                deposit=d.get("deposit", "0"),
                cumulativePaid=d.get("cumulativePaid", "0"),
                remaining=d.get("remaining", "0"),
                consumeCount=d.get("consumeCount", 0),
                expiry=d.get("expiry", ""),
                state=d.get("state", ""),
            ))
        return channels

    async def smart_fetch(self, method: str, url: str, max_auto_pay: Optional[float] = None, **kwargs) -> httpx.Response:
        """Fetch an external resource asynchronously and auto-pay 402 paywalls.

        Sends an HTTP request using the specified ``method``; if the remote
        origin responds with ``402 Payment Required`` and a
        ``WWW-Authenticate`` header describing an ``amount`` and
        ``destination``, the client will attempt to pay that amount via
        ``transfer()`` and retry the request with a payment-proof header.

        If payment fails (e.g. insufficient funds), the original 402 response
        is returned instead of raising — the caller can inspect it and decide
        how to proceed.

        After a successful payment the request is retried up to 3 times with
        a 1-second delay between attempts to handle eventual-consistency
        scenarios where the server hasn't verified the payment yet.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            url: Fully-qualified URL of the resource.
            max_auto_pay: Maximum amount to automatically pay (e.g., 0.50). If the requested amount exceeds this limit, the 402 response is returned without payment.
            **kwargs: Passed directly to ``httpx.AsyncClient.request`` (e.g.
                ``params``, ``headers``, ``json``, ``data``).

        Returns:
            The final ``httpx.Response``.
        """

        kwargs.setdefault("timeout", self.timeout)
        headers = kwargs.pop("headers", {}) or {}
        is_absolute = url.startswith("http://") or url.startswith("https://")

        try:
            if is_absolute:
                async with httpx.AsyncClient(timeout=self.timeout) as temp_client:
                    response = await temp_client.request(method, url, headers=headers, **kwargs)
            else:
                response = await self.client.request(method, url, headers=headers, **kwargs)

            if response.status_code == 402:
                # Let ModexiaAuthError (bad key) and ModexiaNetworkError (no internet) bubble up
                try:
                    receipt = await self._negotiate_paywall(response, max_auto_pay)
                except ModexiaPaymentError:
                    logger.exception("Payment negotiation failed for %s", url)
                    return response

                if receipt and receipt.success:
                    headers["Authorization"] = f"L402 {receipt.txId}"
                    headers["X-Payment-Proof"] = str(receipt.txId)

                    # Retry loop — the server may need a moment to verify payment
                    max_retries = 3
                    for attempt in range(max_retries):
                        if is_absolute:
                            async with httpx.AsyncClient(timeout=self.timeout) as temp_client:
                                retry_resp = await temp_client.request(method, url, headers=headers, **kwargs)
                        else:
                            retry_resp = await self.client.request(method, url, headers=headers, **kwargs)

                        if retry_resp.status_code != 402:
                            return retry_resp
                        logger.warning(
                            "Server still returning 402 after payment (attempt %d/%d)",
                            attempt + 1, max_retries,
                        )
                        await asyncio.sleep(1)
                    return retry_resp

            return response
        except httpx.RequestError as e:
            raise ModexiaNetworkError(f"Connection failed: {str(e)}")

    async def _negotiate_paywall(self, response_obj: httpx.Response, max_auto_pay: Optional[float] = None) -> Optional[PaymentReceipt]:
        """Parse a 402 paywall ``WWW-Authenticate`` header and pay it asynchronously.

        The regex is intentionally lenient — it handles quoted, single-quoted,
        and unquoted values so we work with heterogeneous server
        implementations.

        Returns:
            A ``PaymentReceipt`` on success, otherwise ``None``.

        Raises:
            ModexiaPaymentError: if the transfer itself fails.
        """

        auth_header = response_obj.headers.get("WWW-Authenticate", "")
        amt = re.search(r'amount=["\']?([^"\'\s,;]+)["\']?', auth_header, re.IGNORECASE)
        dst = re.search(r'destination=["\']?([^"\'\s,;]+)["\']?', auth_header, re.IGNORECASE)

        if amt and dst:
            amount_val = float(amt.group(1))
            if max_auto_pay is not None and amount_val > max_auto_pay:
                logger.warning(f"Requested L402 paywall amount ({amount_val}) exceeds max_auto_pay limit ({max_auto_pay}). Declining auto-payment.")
                return None
            return await self.transfer(dst.group(1), amount_val)

        return None
