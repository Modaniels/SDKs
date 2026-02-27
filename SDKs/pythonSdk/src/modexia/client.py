"""Modexia Python SDK client.

This module provides `ModexiaClient` — a small, high‑level HTTP client for
interacting with the Modexia AgentPay HTTP API. It implements reliable
request retrying, basic authentication via `x-modexia-key`, convenience
helpers for reading balance and creating payments, and a `smart_fetch`
helper that can auto-negotiate paywalled resources.

Public surface
- ModexiaClient: main client class
- ModexiaAuthError / ModexiaPaymentError / ModexiaNetworkError: exceptions

The client is intentionally lightweight and synchronous so it is easy to use
from scripts, server-side code, and tests.
"""

import requests
import uuid
import re
import os
import time
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import PaymentReceipt, TransactionHistoryItem, TransactionHistoryResponse

# --- EXCEPTIONS ---
class ModexiaError(Exception): pass
class ModexiaAuthError(ModexiaError): pass
class ModexiaPaymentError(ModexiaError): pass
class ModexiaNetworkError(ModexiaError): pass

logger = logging.getLogger("modexia")
logger.addHandler(logging.NullHandler())

class ModexiaClient:
    """Official Modexia Python client.

    Example:
        client = ModexiaClient(api_key="mx_test_...")
        client.retrieve_balance()
        client.transfer(recipient, amount=1.0)

    Attributes:
        api_key: API key used for `x-modexia-key` header.
        base_url: resolved base URL (live/test/local) for requests.
        session: configured `requests.Session` with retry logic.
    """

    VERSION = "0.4.0"
    DEFAULT_TIMEOUT = 15

    URLS = {
        "live": "https://api.modexia.software",
        "test": "https://sandbox.modexia.software",
        "local": "http://localhost:3000"
    }

    def __init__(self, api_key: str, timeout: int = DEFAULT_TIMEOUT, base_url: Optional[str]=None, validate: bool = True):
        """Create a new `ModexiaClient`.

        Args:
            api_key: Modexia API key (mx_test_... or mx_live_...)
            timeout: per-request timeout in seconds.
            base_url: Optional override for the API URL.
            validate: If True, validate session with the backend during initialization.

        Raises:
            ModexiaAuthError: if initial handshake (/user/me) fails.
            ModexiaNetworkError: on network-level failures.
        """

        self.api_key = api_key
        self.timeout = timeout

        # determine environment from override, env, or key
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
        
        logger.info(f"Resolved base_url to {self.base_url}")

        # HTTP session w/ sensible headers and retry policy
        self.session = requests.Session()
        self.session.headers.update({
            "x-modexia-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": f"Modexia-Python/{self.VERSION}"
        })

        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

        # Handshake: validate API key and cache identity information
        self.identity = {}
        if validate:
            self.identity = self._validate_session()

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Perform an HTTP request against the Modexia API and return JSON.

        This is a thin wrapper around `requests.Session.request` which:
        - applies the configured timeout and session headers
        - raises `ModexiaAuthError` for 401/403
        - raises `ModexiaPaymentError` for 4xx/5xx (except 402 paywall)
        - raises `ModexiaNetworkError` for network errors

        Returns:
            Parsed JSON response as a dict (empty dict for no-content).

        Raises:
            ModexiaAuthError, ModexiaPaymentError, ModexiaNetworkError
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            
            if response.status_code in [401, 403]:
                raise ModexiaAuthError(f"Unauthorized: {response.text}")
            
            if response.status_code >= 400 and response.status_code != 402:
                try: 
                    err = response.json().get('error', response.text)
                except Exception: 
                    # Truncate HTML/plain-text to avoid large exception strings
                    excerpt = response.text[:512]
                    err = f"HTTP {response.status_code} at {url}: {excerpt}"
                raise ModexiaPaymentError(err)
            
            # Return the dictionary, not the response object
            return response.json() if response.content else {}
            
        except requests.exceptions.RequestException as e:
            raise ModexiaNetworkError(f"Connection failed: {str(e)}")

    def _validate_session(self) -> Dict[str, Any]:
        """Validate API key by calling `GET /api/v1/user/me`.

        Returns the parsed `data` payload from the server and caches it on
        the client instance as `identity`.
        """
        res = self._request("GET", "/api/v1/user/me")
        # Ensure we extract the 'data' wrapper if your server uses it
        data = res.get('data', res)
        logger.info(f"Connected to Modexia as: {data.get('username')}")
        return data

    def retrieve_balance(self) -> str:
        """Return the current wallet balance (as a decimal string).

        The server exposes balance via `/api/v1/user/me`; this helper returns
        the `balance` field or string `'0'` when missing.
        """

        data = self._validate_session()
        return data.get("balance", "0")

    def get_balance(self) -> str:
        """Alias for `retrieve_balance()`."""
        return self.retrieve_balance()

    def transfer(self, recipient: str, amount: float, idempotency_key: Optional[str] = None, wait: bool = True) -> PaymentReceipt:
        """Create a payment from the authenticated agent to `recipient`.

        Args:
            recipient: provider/recipient blockchain address (string).
            amount: USD token amount (human decimal, e.g. 1.50).
            idempotency_key: optional idempotency token; autogenerated via intent hashing when not provided.
            wait: if True, poll the transaction status until it completes or times out.

        Returns:
            PaymentReceipt dataclass with the transaction details.

        Raises:
            ModexiaPaymentError on server-declared failures.
        """

        if not idempotency_key:
            intent_str = f"{recipient}_{amount}_{datetime.now().strftime('%Y-%m-%d-%H')}"
            ikey = hashlib.sha256(intent_str.encode()).hexdigest()
        else:
            ikey = idempotency_key
            
        payload = {"providerAddress": recipient, "amount": str(amount), "idempotencyKey": ikey}

        data = self._request("POST", "/api/v1/agent/pay", json=payload)

        if wait and data.get("success"):
            return self._poll_status(data.get("txId"))

        return PaymentReceipt(
            success=data.get("success", False),
            status="PENDING",
            txId=data.get("txId"),
            errorReason=data.get("error")
        )

    def _poll_status(self, tx_id: str) -> PaymentReceipt:
        """Poll the server for transaction status until timeout.

        The method repeatedly queries `/api/v1/agent/transaction/{tx_id}` and
        returns once the server reports a completion or raises when the
        transaction fails.

        Returns a PaymentReceipt on success.
        """
        start = time.time()
        while (time.time() - start) < 30:
            data = self._request("GET", f"/api/v1/agent/transaction/{tx_id}")
            
            state = data.get("state", "").upper()
            # Be flexible with the string
            if state in ["COMPLETE", "COMPLETED"]:
                return PaymentReceipt(success=True, txId=tx_id, status="COMPLETE", txHash=data.get("txHash"))
            
            if state == "FAILED":
                raise ModexiaPaymentError(f"Transfer Failed: {data.get('errorReason')}")
            
            time.sleep(2)
        return PaymentReceipt(success=True, status="PENDING", txId=tx_id)

    def get_history(self, limit: int = 5) -> TransactionHistoryResponse:
        """Fetch the transaction history for the authenticated agent.
        
        Args:
            limit: maximum number of transactions to return.
            
        Returns:
            TransactionHistoryResponse dataclass containing the transactions.
        """
        data = self._request("GET", f"/api/v1/user/transactions?limit={limit}")
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

    def smart_fetch(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
        """Fetch an external resource and auto-pay 402 paywalls.

        Performs a plain GET; if the remote origin responds with 402 and
        a `WWW-Authenticate` header describing an `amount` and `destination`,
        the client will attempt to pay that amount via `transfer()` and retry
        the request with a payment proof header.

        Returns the final `requests.Response`.
        """

        if headers is None: headers = {}
        response = requests.get(url, params=params, headers=headers, timeout=self.timeout)

        if response.status_code == 402:
            receipt = self._negotiate_paywall(response)
            if receipt:
                headers['Authorization'] = f"L402 {receipt.get('txId')}"
                headers['X-Payment-Proof'] = receipt.get('txId')
                return requests.get(url, params=params, headers=headers, timeout=self.timeout)

        return response

    def _negotiate_paywall(self, response_obj) -> Optional[Dict]:
        """Parse a 402 paywall `WWW-Authenticate` header and pay it.

        Returns the receipt dict returned by `transfer()` when payment
        succeeded, otherwise `None`.
        """

        auth_header = response_obj.headers.get("WWW-Authenticate", "")
        amt = re.search(r'amount="([^"]+)"', auth_header)
        dst = re.search(r'destination="([^"]+)"', auth_header)

        if amt and dst:
            return self.transfer(dst.group(1), float(amt.group(1)))

        return None