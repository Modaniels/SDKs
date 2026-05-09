from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class PaymentReceipt:
    success: bool
    status: str
    txId: Optional[str] = None
    txHash: Optional[str] = None
    errorReason: Optional[str] = None
    txIds: Optional[List[str]] = None
    axelarScanUrls: Optional[List[str]] = None

    @property
    def squidStatusUrls(self) -> Optional[List[str]]:
        """Deprecated: use axelarScanUrls instead."""
        return self.axelarScanUrls

    
@dataclass
class TransactionHistoryItem:
    txId: str
    type: str
    amount: str
    state: str
    createdAt: str
    providerAddress: Optional[str] = None
    txHash: Optional[str] = None
    memo: Optional[str] = None
    
@dataclass
class TransactionHistoryResponse:
    transactions: List[TransactionHistoryItem]
    hasMore: bool

@dataclass
class ChannelReceipt:
    """HMAC-signed receipt returned by each off-chain consume call."""
    channelId: str
    cumulativeTotal: str
    nonce: int
    hmac: str
    timestamp: int = 0

@dataclass
class ConsumeResponse:
    """Result of a single micro-payment inside a payment channel."""
    success: bool
    receipt: ChannelReceipt
    remaining: str
    isDuplicate: bool = False

@dataclass
class ChannelStatus:
    """Current state of a payment channel."""
    channelId: str
    providerAddress: str
    deposit: str
    cumulativePaid: str
    remaining: str
    consumeCount: int
    expiry: str
    state: str
    isExpired: bool = False


@dataclass
class IntentResult:
    """Rich result returned from the v2 intent-to-pay pipeline.

    Contains the intent status, transaction details (if executed),
    compliance/validation metadata, and actionable suggestions on rejection.
    """
    status: str                          # pending | approved | rejected | executed | failed
    intent_id: Optional[str] = None
    # Transaction details (populated on 'executed')
    txId: Optional[str] = None
    txIds: Optional[List[str]] = None
    txState: Optional[str] = None
    amount: Optional[str] = None
    recipient: Optional[str] = None
    # Compliance & policy metadata
    wallet_balance_after: Optional[str] = None
    daily_spent: Optional[str] = None
    daily_remaining: Optional[str] = None
    # Rejection info
    reason: Optional[str] = None
    code: Optional[str] = None
    suggestion: Optional[str] = None
    # Full validation pipeline results
    validation: Dict[str, Any] = field(default_factory=dict)

