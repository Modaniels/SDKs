"""Public package exports for the Python SDK.

Expose the same class name used in `client.py` so imports across the
package are consistent (use `ModexiaClient`).
"""
from .client import (
    ModexiaClient,
    ModexiaError,
    ModexiaAuthError,
    ModexiaPaymentError,
    ModexiaNetworkError,
)
from .async_client import AsyncModexiaClient
from .models import (
    PaymentReceipt, TransactionHistoryItem, TransactionHistoryResponse,
    ChannelReceipt, ConsumeResponse, ChannelStatus,
)

__all__ = [
    "ModexiaClient",
    "AsyncModexiaClient",
    "ModexiaError",
    "ModexiaAuthError",
    "ModexiaPaymentError",
    "ModexiaNetworkError",
    "PaymentReceipt",
    "TransactionHistoryItem",
    "TransactionHistoryResponse",
    "ChannelReceipt",
    "ConsumeResponse",
    "ChannelStatus",
]