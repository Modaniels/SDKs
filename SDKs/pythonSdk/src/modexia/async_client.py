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
from .models import PaymentReceipt, TransactionHistoryItem, TransactionHistoryResponse

logger = logging.getLogger("modexia.async")
logger.addHandler(logging.NullHandler())

class AsyncModexiaClient:
    """Official Modexia Python Async Client.

    Example:
        client = AsyncModexiaClient(api_key="mx_test_...")
        await client.retrieve_balance()
        await client.transfer(recipient, amount=1.0)
    """

    VERSION = "0.4.0"
    DEFAULT_TIMEOUT = 15.0

    URLS = {
        "live": "https://api.modexia.software",
        "test": "https://sandbox.modexia.software",
        "local": "http://localhost:3000"
    }

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT, base_url: Optional[str]=None):
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
                
                return response.json() if response.content else {}
                
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
        if not idempotency_key:
            intent_str = f"{recipient}_{amount}_{datetime.now().strftime('%Y-%m-%d-%H')}"
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
            
        return PaymentReceipt(success=True, status="PENDING", txId=tx_id)

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

    async def smart_fetch(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> httpx.Response:
        """Fetch an external resource asynchronously and auto-pay 402 paywalls."""
        if headers is None: headers = {}
        
        # Determine if URL is absolute or needs to be resolved manually since HTTPX client has base_url
        is_absolute = url.startswith("http://") or url.startswith("https://")
        
        try:
            if is_absolute:
                # Need a separate client to ignore base_url
                async with httpx.AsyncClient(timeout=self.timeout) as temp_client:
                    response = await temp_client.get(url, params=params, headers=headers)
            else:
                response = await self.client.get(url, params=params, headers=headers)
                
            if response.status_code == 402:
                receipt = await self._negotiate_paywall(response)
                if receipt and receipt.success:
                    headers['Authorization'] = f"L402 {receipt.txId}"
                    headers['X-Payment-Proof'] = str(receipt.txId)
                    
                    if is_absolute:
                        async with httpx.AsyncClient(timeout=self.timeout) as temp_client:
                            return await temp_client.get(url, params=params, headers=headers)
                    else:
                        return await self.client.get(url, params=params, headers=headers)
                        
            return response
        except httpx.RequestError as e:
            raise ModexiaNetworkError(f"Connection failed: {str(e)}")

    async def _negotiate_paywall(self, response_obj: httpx.Response) -> Optional[PaymentReceipt]:
        """Parse a 402 paywall `WWW-Authenticate` header and pay it asynchronously."""
        auth_header = response_obj.headers.get("WWW-Authenticate", "")
        amt = re.search(r'amount="([^"]+)"', auth_header)
        dst = re.search(r'destination="([^"]+)"', auth_header)

        if amt and dst:
            return await self.transfer(dst.group(1), float(amt.group(1)))

        return None
