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

from .models import (
    PaymentReceipt, TransactionHistoryItem, TransactionHistoryResponse,
    ChannelReceipt, ConsumeResponse, ChannelStatus,
)

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

    VERSION = "0.5.0"
    DEFAULT_TIMEOUT = 15

    URLS = {
        "live": "https://api.modexia.software",
        "test": "https://sandbox.modexia.software",
        "local": "http://localhost:3001"
    }

    def __init__(self, api_key: str, timeout: int = DEFAULT_TIMEOUT, base_url: Optional[str]=None, validate: bool = True, allow_insecure_http: bool = False):
        """Create a new `ModexiaClient`.

        Args:
            api_key: Modexia API key (mx_test_... or mx_live_...)
            timeout: per-request timeout in seconds.
            base_url: Optional override for the API URL.
            validate: If True, validate session with the backend during initialization.
            allow_insecure_http: If True, allows connecting via unencrypted HTTP to non-localhost addresses.

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
        
        if not re.match(r"^mx_(test|live)_[a-fA-F0-9]{32}$", self.api_key):
            raise ModexiaAuthError("Invalid API key format. Must start with mx_live_ or mx_test_ followed by 32 hex characters.")
            
        if self.base_url.startswith("http://") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            if not allow_insecure_http:
                raise ModexiaNetworkError(f"SECURITY WARNING: Attempting unencrypted HTTP connection to {self.base_url}. API key will be sent in cleartext. Pass allow_insecure_http=True to override.")
            logger.warning(f"SECURITY WARNING: Using unencrypted HTTP connection to {self.base_url}. API key will be sent in cleartext.")
        
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
            
            # Check for soft failures inside HTTP 200
            try:
                data = response.json() if response.content else {}
            except ValueError:
                # Catch HTML proxy/load-balancer responses on HTTP 200
                excerpt = response.text[:512]
                raise ModexiaNetworkError(f"HTTP {response.status_code} returned non-JSON data: {excerpt}")
            
            if response.status_code == 200 and isinstance(data, dict) and data.get("success") is False:
                raise ModexiaPaymentError(data.get("error", data.get("errorReason", "Unknown logical API error")))
                
            return data
            
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

        if not re.match(r"^0x[a-fA-F0-9]{40}$", recipient):
            raise ValueError(f"Invalid recipient address format: {recipient}. Must be a 42-character hex string starting with 0x.")

        if not idempotency_key:
            intent_str = f"{recipient}_{amount}_{uuid.uuid4()}"
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
            
        raise TimeoutError(f"Transaction {tx_id} did not settle within 30 seconds. Status remains PENDING.")

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

    # ═══════════════════════════════════════════════════════════════════
    #  VAULT — Payment Channels for Micro & High-Frequency Transactions
    # ═══════════════════════════════════════════════════════════════════

    def open_channel(self, provider: str, deposit: float, duration_hours: float = 24.0) -> Dict[str, Any]:
        """Open a payment channel with on-chain deposit.

        Locks `deposit` credits in the ModexiaVault contract. After opening,
        use `consume_channel()` for instant, gas-free micro-payments.

        Args:
            provider: recipient blockchain address (0x...).
            deposit: amount to lock (e.g. 5.0 = $5.00).
            duration_hours: channel lifetime in hours (default 24h).

        Returns:
            Dict with channelId, deposit, expiry, depositTxId, approveTxId.
        """
        if not re.match(r"^0x[a-fA-F0-9]{40}$", provider):
            raise ValueError(f"Invalid provider address format: {provider}. Must be a 42-character hex string starting with 0x.")
            
        payload = {
            "providerAddress": provider,
            "depositAmount": str(deposit),
            "durationHours": str(duration_hours),
        }
        res = self._request("POST", "/api/v1/vault/open", json=payload)
        return res.get("data", res)

    def consume_channel(self, channel_id: str, amount: float, idempotency_key: Optional[str] = None) -> ConsumeResponse:
        """Execute an instant, gas-free micro-payment inside a channel.

        This is the core high-frequency method — call it thousands of
        times per minute with zero blockchain overhead.

        Args:
            channel_id: ID returned by `open_channel()`.
            amount: amount to consume (e.g. 0.002).
            idempotency_key: dedup key; auto-generated if omitted.

        Returns:
            ConsumeResponse with HMAC receipt and remaining balance.
        """
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        payload = {
            "channelId": channel_id,
            "amount": str(amount),
            "idempotencyKey": idempotency_key,
        }
        res = self._request("POST", "/api/v1/vault/consume", json=payload)
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

    def settle_channel(self, channel_id: str) -> Dict[str, Any]:
        """Settle a channel on-chain. Pays provider, takes fee, refunds rest.

        Args:
            channel_id: ID of the channel to close.

        Returns:
            Dict with toProvider, toFee, toRefund, settleTxId.
        """
        res = self._request("POST", "/api/v1/vault/settle", json={"channelId": channel_id})
        return res.get("data", res)

    def get_channel(self, channel_id: str) -> ChannelStatus:
        """Get the current status of a payment channel.

        Args:
            channel_id: ID of the channel.

        Returns:
            ChannelStatus dataclass with deposit, usage, and expiry info.
        """
        res = self._request("GET", f"/api/v1/vault/status/{channel_id}")
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

    def list_channels(self, limit: int = 50) -> List[ChannelStatus]:
        """List all payment channels for the authenticated agent.

        Args:
            limit: max number of channels to return (default 50).

        Returns:
            List of ChannelStatus dataclasses.
        """
        res = self._request("GET", f"/api/v1/vault/channels?limit={limit}")
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

    def smart_fetch(self, method: str, url: str, max_auto_pay: Optional[float] = None, **kwargs) -> requests.Response:
        """Fetch an external resource and auto-pay 402 paywalls.

        Sends an HTTP request using the specified `method`; if the remote
        origin responds with ``402 Payment Required`` and a
        ``WWW-Authenticate`` header describing an ``amount`` and
        ``destination``, the client will attempt to pay that amount via
        ``transfer()`` and retry the request with a payment proof header.

        If payment fails (e.g. insufficient funds), the original 402 response
        is returned instead of raising an exception — this lets caller code
        inspect the response and decide how to proceed.

        After a successful payment the request is retried up to 3 times with
        a 1-second delay between attempts to handle eventual-consistency
        scenarios where the server hasn't verified the payment yet.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            url: Fully-qualified URL of the resource.
            max_auto_pay: Maximum amount to automatically pay (e.g., 0.50). If the requested amount exceeds this limit, the 402 response is returned without payment.
            **kwargs: Passed directly to ``requests.request`` (e.g.
                ``params``, ``headers``, ``json``, ``data``).

        Returns:
            The final ``requests.Response``.
        """

        kwargs.setdefault("timeout", self.timeout)
        headers = kwargs.pop("headers", {}) or {}
        response = requests.request(method, url, headers=headers, **kwargs)

        if response.status_code == 402:
            # If the user's API key is revoked or they have no internet, we WANT it to crash.
            # Only swallow ModexiaPaymentError (e.g. insufficient funds) to return the 402 to the agent.
            try:
                receipt = self._negotiate_paywall(response, max_auto_pay)
            except ModexiaPaymentError:
                logger.exception("Payment negotiation failed for %s", url)
                return response

            if receipt and receipt.success:
                headers["Authorization"] = f"L402 {receipt.txId}"
                headers["X-Payment-Proof"] = str(receipt.txId)

                # Retry loop — the server may need a moment to verify payment
                max_retries = 3
                for attempt in range(max_retries):
                    retry_resp = requests.request(method, url, headers=headers, **kwargs)
                    if retry_resp.status_code != 402:
                        return retry_resp
                    logger.warning(
                        "Server still returning 402 after payment (attempt %d/%d)",
                        attempt + 1, max_retries,
                    )
                    time.sleep(1)
                return retry_resp

        return response

    def _negotiate_paywall(self, response_obj, max_auto_pay: Optional[float] = None) -> Optional[PaymentReceipt]:
        """Parse a 402 paywall ``WWW-Authenticate`` header and pay it.

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
            return self.transfer(dst.group(1), amount_val)

        return None